"""SELF_METRICS_AND_QUEUE_DIRECTOR_V1 — the recursive loop measures + schedules ITSELF.

Masterplan Horizon 1, bundle 9 (§A2). The director ordered work by hardcoded priority numbers and
nothing predicted the recurring operational failure (heavy evidence silently ageing past its
freshness ceiling and blocking the next suite). This layer computes self-metrics over the validation
report, builds an evidence-freshness RADAR that names the lanes about to decay, and ranks the next
operational action (fix a broken domain / re-run a stale lane) by evidence — with receipts, not a
tuned constant. Pure functions over the report; no UE, no re-cook.

Recomputation law: metrics + queue are re-derived from the cited source report at validation time; a
tampered stored self-grade is caught.
"""
from __future__ import annotations

import json
from pathlib import Path

from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict


ROOT = Path(__file__).resolve().parents[2]
VAL_ART = ROOT / "artifacts" / "validation"
FULL_REPORT_PATH = VAL_ART / "validation_report_full.json"
RESULT_DIR = ROOT / "artifacts" / "self_metrics"
RESULT_PATH = RESULT_DIR / "self_metrics.json"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_SELF_METRICS_REPORT.md"

WARN_HEADROOM_SECONDS = 2 * 60 * 60      # a lane within 2h of its ceiling is a "re-run soon" warn
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60    # fallback ceiling for an aged lane with no known ceiling

# Known freshness ceilings per validator (the heavy, decaying evidence lanes). Kept explicit so the
# radar predicts a block BEFORE the owning validator's own freshness gate trips.
MAX_AGE_BY_VALIDATOR = {
    "perf_baseline_result_fresh": 6 * 60 * 60,
    "bot_balance_result_fresh": 6 * 60 * 60,
    "ui_settings_result_fresh": 6 * 60 * 60,
    "real_game_capture_fresh": 6 * 60 * 60,
    "anim_video_motion_live": 12 * 60 * 60,
    "frontdoor_live_deploy_proof": 12 * 60 * 60,
    "mode_contract_proof_present": 24 * 60 * 60,  # commandlet is pure/fast; cheap to regen every run
}

# Re-run / fix command per domain (what the operational queue tells the loop to do next).
DOMAIN_COMMAND = {
    "performance_baseline": "python scripts/pipeline/run_pipeline.py performance_baseline wanefall_win64_development_perf",
    "bot_balance": "python scripts/pipeline/run_pipeline.py bot_balance_telemetry wanefall_win64_development_botmatch",
    "ui_settings": "python scripts/pipeline/run_pipeline.py ui_settings_persistence wanefall_win64_development_settings",
    "wane_fx": "python scripts/pipeline/run_pipeline.py performance_baseline wanefall_win64_development_perf  # restores packaged [WaneFX] player markers",
    "real_game": "python scripts/pipeline/run_pipeline.py real_game_validation wanefall_default_lobby",
    "anim_live": "python scripts/capture/anim_live_capture.py",
    "frontdoor_live": "python scripts/capture/anim_live_capture.py  (WANEFALL_ANIM_MAP_URL=<ModeShell> WANEFALL_ANIM_DEPLOY_FIRST=1)",
}


def _find_age_seconds(node, depth: int = 0):
    """Recursively locate an age_seconds value in a validator's detail. Returns float or None."""
    if depth > 6 or not isinstance(node, dict):
        return None
    if isinstance(node.get("age_seconds"), (int, float)):
        return float(node["age_seconds"])
    for v in node.values():
        if isinstance(v, dict):
            found = _find_age_seconds(v, depth + 1)
            if found is not None:
                return found
    return None


def _find_max_age_seconds(node, depth: int = 0):
    if depth > 6 or not isinstance(node, dict):
        return None
    if isinstance(node.get("max_age_seconds"), (int, float)):
        return float(node["max_age_seconds"])
    for v in node.values():
        if isinstance(v, dict):
            found = _find_max_age_seconds(v, depth + 1)
            if found is not None:
                return found
    return None


# The self_metrics domain is EXCLUDED from its own measurement: the loop must not measure the act of
# measuring (that self-reference would make every run's report differ from the last, so the artifact
# could never be idempotent). Excluding it keeps the non-self domain set + total stable run-to-run.
SELF_DOMAIN = "self_metrics"


def _measured_results(report: dict) -> list:
    results = report.get("results") if isinstance(report.get("results"), list) else []
    return [r for r in results if isinstance(r, dict) and str(r.get("domain") or "") != SELF_DOMAIN]


def compute_freshness_radar(report: dict, warn_headroom: float = WARN_HEADROOM_SECONDS) -> list:
    """Every result carrying an age_seconds becomes a radar entry with headroom vs its ceiling.
    Deterministic: sorted by (status severity, least headroom, validator_id)."""
    results = _measured_results(report)
    radar = []
    for r in results:
        if not isinstance(r, dict):
            continue
        detail = r.get("detail") if isinstance(r.get("detail"), dict) else {}
        age = _find_age_seconds(detail)
        if age is None:
            continue
        vid = str(r.get("validator_id") or "")
        max_age = (_find_max_age_seconds(detail)
                   or MAX_AGE_BY_VALIDATOR.get(vid)
                   or DEFAULT_MAX_AGE_SECONDS)
        headroom = max_age - age
        status = "stale" if headroom <= 0 else ("warn" if headroom < warn_headroom else "fresh")
        radar.append({
            "validator_id": vid, "domain": str(r.get("domain") or ""),
            "age_seconds": round(age, 1), "max_age_seconds": round(max_age, 1),
            "headroom_seconds": round(headroom, 1), "status": status,
        })
    order = {"stale": 0, "warn": 1, "fresh": 2}
    radar.sort(key=lambda e: (order.get(e["status"], 3), e["headroom_seconds"], e["validator_id"]))
    return radar


def compute_self_metrics(report: dict, source_ref: dict | None = None,
                         warn_headroom: float = WARN_HEADROOM_SECONDS) -> dict:
    """Pure self-assessment of the validator suite from its own report."""
    report = report if isinstance(report, dict) else {}
    results = _measured_results(report)

    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0}
    domains: dict = {}
    probe_mix: dict = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        state = str(r.get("state") or "")
        counts[state] = counts.get(state, 0) + 1
        dom = str(r.get("domain") or "")
        d = domains.setdefault(dom, {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0})
        d[state] = d.get(state, 0) + 1
        probe = str(r.get("probe_type") or "")
        probe_mix[probe] = probe_mix.get(probe, 0) + 1
    for dom, d in domains.items():
        d["healthy"] = (d.get("FAIL", 0) == 0 and d.get("BLOCKED", 0) == 0
                        and d.get("REJECTED", 0) == 0)
    total = len(results)
    pass_rate = round(counts.get("PASS", 0) / total, 4) if total else 0.0

    return {
        "schema_version": 1,
        "source": source_ref or {},
        "suite": {
            "verdict": report.get("suite_verdict"),
            "run_ts": report.get("run_ts"),
            "total": total,
            "counts": counts,
            "pass_rate": pass_rate,
        },
        "domains": domains,
        "probe_mix": probe_mix,
        "freshness_radar": compute_freshness_radar(report, warn_headroom=warn_headroom),
        "operator_only_states_written": [],
    }


def rank_operational_queue(metrics: dict) -> list:
    """Deterministic, evidence-cited next-action queue. Buckets: broken domains first (real work),
    then stale evidence, then warn (re-run before it blocks). Every item cites its evidence."""
    metrics = metrics if isinstance(metrics, dict) else {}
    domains = metrics.get("domains") if isinstance(metrics.get("domains"), dict) else {}
    radar = metrics.get("freshness_radar") if isinstance(metrics.get("freshness_radar"), list) else []

    items = []
    # bucket 0: broken domains (any non-PASS result)
    for dom in sorted(domains):
        d = domains[dom]
        broken = d.get("FAIL", 0) + d.get("BLOCKED", 0) + d.get("REJECTED", 0)
        if broken > 0:
            items.append({
                "bucket": "broken", "bucket_rank": 0, "domain": dom,
                "action": f"fix broken domain {dom} ({broken} non-PASS validator(s))",
                "evidence": {"domain_counts": d},
                "command": DOMAIN_COMMAND.get(dom, f"python scripts/pipeline/run_validation.py --domain {dom}"),
                "sort_key": -broken,
            })
    # bucket 1 (stale) + 2 (warn): decaying evidence, worst headroom first
    for entry in radar:
        if entry.get("status") == "fresh":
            continue
        bucket = entry["status"]     # stale | warn
        bucket_rank = 1 if bucket == "stale" else 2
        items.append({
            "bucket": bucket, "bucket_rank": bucket_rank, "domain": entry.get("domain", ""),
            "action": f"re-run {entry.get('domain')} lane ({entry.get('validator_id')} {bucket})",
            "evidence": {"validator_id": entry.get("validator_id"),
                         "age_seconds": entry.get("age_seconds"),
                         "max_age_seconds": entry.get("max_age_seconds"),
                         "headroom_seconds": entry.get("headroom_seconds")},
            "command": DOMAIN_COMMAND.get(entry.get("domain", ""),
                                          f"python scripts/pipeline/run_validation.py --domain {entry.get('domain')}"),
            "sort_key": entry.get("headroom_seconds", 0.0),
        })

    items.sort(key=lambda it: (it["bucket_rank"], it["sort_key"], it["domain"],
                               (it.get("evidence") or {}).get("validator_id", "")))
    for i, it in enumerate(items, start=1):
        it["rank"] = i
        it.pop("sort_key", None)
    return items


def build_artifact(report: dict, source_ref: dict) -> dict:
    metrics = compute_self_metrics(report, source_ref=source_ref)
    metrics["operational_queue"] = rank_operational_queue(metrics)
    return metrics


# ---- validation-time recomputation (used by the registry validators) ----

def load_full_report(path: Path = FULL_REPORT_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recompute_and_compare(stored: dict, report: dict) -> dict:
    """Recompute suite/domains/probe_mix from the report and compare to the stored artifact."""
    fresh = compute_self_metrics(report, source_ref=stored.get("source"))
    issues = []
    for key in ("suite", "domains", "probe_mix"):
        if stored.get(key) != fresh.get(key):
            issues.append(f"stored {key} != recomputed {key} (fabricated/stale self-metrics)")
    return {"passed": not issues, "issues": issues}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_self_metrics(report_path: Path = FULL_REPORT_PATH,
                          out_path: Path = RESULT_PATH) -> dict:
    """Read the last full audit, build the self-metrics + operational queue artifact, write it."""
    rp = Path(report_path)
    if not rp.exists():
        raise BlockedError(f"no full validation report to self-measure: {rp} "
                           "(run `python scripts/pipeline/run_validation.py` once first)")
    report = json.loads(rp.read_text(encoding="utf-8"))
    source_ref = {"path": str(rp.relative_to(ROOT)) if rp.is_relative_to(ROOT) else str(rp),
                  "run_ts": report.get("run_ts"), "scope": report.get("scope"),
                  "used_full_report": rp.name == "validation_report_full.json"}
    artifact = build_artifact(report, source_ref)
    _write_json(Path(out_path), artifact)
    return artifact


def _make_report(metrics: dict, report_path: Path) -> str:
    suite = metrics.get("suite") or {}
    radar = metrics.get("freshness_radar") or []
    queue = metrics.get("operational_queue") or []
    lines = [
        "# WANEFALL Self-Metrics + Queue Director Report (SELF_METRICS_AND_QUEUE_DIRECTOR_V1)",
        "",
        f"Suite verdict: {suite.get('verdict')}  total: {suite.get('total')}  "
        f"pass_rate: {suite.get('pass_rate')}",
        f"Source: {metrics.get('source')}",
        "",
        "## Evidence-freshness radar (decaying lanes)",
    ]
    decaying = [e for e in radar if e.get("status") != "fresh"]
    if not decaying:
        lines.append("- all aged lanes fresh")
    for e in decaying:
        lines.append(f"- {e['status'].upper()} {e['validator_id']} ({e['domain']}) "
                     f"headroom {e['headroom_seconds'] / 3600:.1f}h")
    lines.extend(["", "## Operational queue (next action by evidence)"])
    if not queue:
        lines.append("- nothing queued — suite green + all evidence fresh")
    for it in queue:
        lines.append(f"{it['rank']}. [{it['bucket']}] {it['action']}  →  `{it['command']}`")
    lines.extend(["", "## Boundaries",
                  "- Metrics + queue recomputed from the cited report; no fabricated self-grade.",
                  "- Deterministic ranking; no operator-only states written."])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class SelfMetricsDirectorPipeline(ProductionPipeline):
    name = "self_metrics_director"
    kind = "self_metrics_director"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        return {
            "asset_id": str(task.get("asset_id") or "wanefall_self_metrics"),
            "report_path": Path(task.get("report_path") or FULL_REPORT_PATH),
            "result_path": Path(task.get("result_path") or RESULT_PATH),
            "local_report": Path(task.get("local_report") or LOCAL_REPORT),
        }

    def execute(self, plan: dict) -> Artifact:
        metrics = generate_self_metrics(Path(plan["report_path"]), Path(plan["result_path"]))
        _make_report(metrics, Path(plan["local_report"]))
        return Artifact(
            asset_id=str(plan["asset_id"]), kind=self.kind,
            data={"result_path": str(plan["result_path"]),
                  "suite_total": (metrics.get("suite") or {}).get("total"),
                  "queued": len(metrics.get("operational_queue") or [])},
            provenance={"source": "dimwit_self_metrics_over_validation_report",
                        "license": "internal"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        try:
            stored = json.loads(Path(plan["result_path"]).read_text(encoding="utf-8"))
            report = json.loads(Path(plan["report_path"]).read_text(encoding="utf-8"))
        except Exception as exc:
            return Verdict(score=0.0, passed=False, hard_fail=False,
                           issues=[f"self-metrics unreadable: {exc}"], detail={})
        cmp = recompute_and_compare(stored, report)
        return Verdict(score=1.0 if cmp["passed"] else 0.0, passed=bool(cmp["passed"]),
                       hard_fail=False, issues=cmp["issues"],
                       detail={"queued": len(stored.get("operational_queue") or [])},
                       evidence=[str(plan["result_path"])])

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact
