"""Evidence-driven, fail-closed recursive improvement controller.

The older autonomy layers inventory capabilities and rank static queues.  This controller closes the
experiment loop: select work from current validator evidence, enforce cost/time/attempt budgets, execute one
bounded candidate, rerun the authoritative gate, compare before/after validator states, remember the outcome,
and quarantine regressions.  It never writes an operator-only state and never auto-rolls back opaque Unreal
side effects; a regression is stopped, preserved as evidence, and surfaced for bounded repair/review.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from dimwit.core import sha256_obj
from dimwit.engine import DimwitLedger
from dimwit.evolution.diversity import build_diversity_plan, family_for_pipeline
from dimwit.pipelines import get_pipeline, list_pipelines


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "improvement_policy.json"
FULL_REPORT_PATH = ROOT / "artifacts" / "validation" / "validation_report_full.json"
ARTIFACT_PATH = ROOT / "artifacts" / "autonomy" / "recursive_improvement_run.json"
LEDGER_PATH = ROOT / "ledger" / "improvement_experiments.jsonl"
REVIEW_CEILING = "PROMOTED_TO_REVIEW"

OPERATOR_ONLY_STATES = {"HUMAN_ACCEPTED", "PROMOTED_TO_ACTIVE_SLICE"}
NON_PASS_WEIGHT = {"BLOCKED": 35.0, "FAIL": 60.0, "REJECTED": 90.0}
STATE_RANK = {"PASS": 0, "BLOCKED": 1, "FAIL": 2, "REJECTED": 3}

# A pipeline can repair several validation domains.  Explicit mappings make the ranking inspectable and
# deterministic; unknown pipelines still retain their configured priority/EV/cost score.
PIPELINE_DOMAINS = {
    "packaged_build_validation": {"packaged_build"},
    "performance_baseline": {"performance_baseline", "wane_fx"},
    "bot_balance_telemetry": {"bot_balance"},
    "ui_settings_persistence": {"ui_settings"},
    "progression": {"progression"},
    "self_metrics_director": {"self_metrics"},
    "flagship_arena_art_pass": {"flagship_arena", "environment_maps"},
    "real_game_validation": {"real_game_runtime", "environment_maps"},
    "character_roster_policy": {"character_roster_policy"},
    "character_source_sync": {"character_source_sync", "character_anatomy"},
    "character_fidelity": {"characters_static_full_nanite", "character_roster_fidelity"},
    "rigging": {"rigged_skeletal_meshes"},
    "animation": {"animation_wiring"},
    "environment": {"environment_maps"},
    "vfx": {"vfx_audio", "wane_fx"},
    "audio": {"vfx_audio", "audio_foundation"},
    "materials_shaders": {"materials_shaders"},
    "metahuman_output_attempt": {"metahuman_character_pipeline"},
    "unreal_game_builder_engine": {"unreal_game_builder_engine", "autonomy_engine"},
}


@dataclass(frozen=True)
class ImprovementPolicy:
    max_tasks: int = 3
    max_total_cost: float = 6.0
    max_wall_seconds: float = 10800.0
    max_attempts_per_task: int = 2
    regression_cooldown_seconds: float = 86400.0
    validate_after_each_task: bool = True
    stop_on_regression: bool = True
    stop_on_execution_error: bool = False
    review_ceiling: str = REVIEW_CEILING

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> "ImprovementPolicy":
        raw = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
        fields = cls.__dataclass_fields__
        return cls(**{key: raw[key] for key in fields if key in raw})

    def validate(self) -> None:
        if self.review_ceiling != REVIEW_CEILING:
            raise ValueError(f"review ceiling must remain {REVIEW_CEILING}")
        if self.max_tasks < 1 or self.max_total_cost <= 0 or self.max_wall_seconds <= 0:
            raise ValueError("improvement budgets must be positive")
        if self.max_attempts_per_task < 1 or self.regression_cooldown_seconds < 0:
            raise ValueError("attempt/cooldown policy is invalid")


def _results(report: dict) -> list[dict]:
    rows = report.get("results") if isinstance(report, dict) else None
    return [row for row in (rows or []) if isinstance(row, dict)]


def _key(row: dict) -> str:
    return f"{row.get('domain', '')}:{row.get('validator_id', '')}"


def _state(row: dict) -> str:
    state = str(row.get("state") or "BLOCKED").upper()
    return state if state in STATE_RANK else "BLOCKED"


def fitness_snapshot(report: dict) -> dict:
    """Compact, reproducible fitness vector. Lower hard non-pass counts are better."""
    rows = _results(report)
    counts = {state: 0 for state in STATE_RANK}
    blocker_counts = {state: 0 for state in STATE_RANK}
    for row in rows:
        state = _state(row)
        counts[state] += 1
        if str(row.get("severity") or "blocker").lower() == "blocker":
            blocker_counts[state] += 1
    total = len(rows)
    return {
        "suite_verdict": report.get("suite_verdict") if isinstance(report, dict) else None,
        "run_ts": report.get("run_ts") if isinstance(report, dict) else None,
        "total": total,
        "counts": counts,
        "blocker_counts": blocker_counts,
        "pass_rate": round(counts["PASS"] / total, 6) if total else 0.0,
    }


def compare_validation_reports(before: dict, after: dict) -> dict:
    """Fail-closed validator-level delta. Missing post evidence for a baseline validator is a regression."""
    before_rows, after_rows = _results(before), _results(after)
    base, post = {_key(row): row for row in before_rows}, {_key(row): row for row in after_rows}
    if not base or not post:
        return {
            "disposition": "EVALUATION_BLOCKED",
            "issues": ["baseline or candidate validation report has no validator results"],
            "resolved": [], "regressed": [], "added_passes": [],
            "before": fitness_snapshot(before), "after": fitness_snapshot(after),
        }

    resolved, regressed, added_passes = [], [], []
    for key, prior in base.items():
        current = post.get(key)
        if current is None:
            regressed.append({"validator": key, "before": _state(prior), "after": "MISSING"})
            continue
        old_state, new_state = _state(prior), _state(current)
        if STATE_RANK[new_state] > STATE_RANK[old_state]:
            regressed.append({"validator": key, "before": old_state, "after": new_state})
        elif STATE_RANK[new_state] < STATE_RANK[old_state]:
            resolved.append({"validator": key, "before": old_state, "after": new_state})
    for key, current in post.items():
        if key in base:
            continue
        state = _state(current)
        if state == "PASS":
            added_passes.append(key)
        else:
            regressed.append({"validator": key, "before": "ABSENT", "after": state})

    if regressed:
        disposition = "REGRESSION_QUARANTINED"
    elif resolved or added_passes:
        disposition = "IMPROVED_CANDIDATE"
    else:
        disposition = "STABLE_CANDIDATE"
    return {
        "disposition": disposition, "issues": [],
        "resolved": resolved, "regressed": regressed, "added_passes": added_passes,
        "before": fitness_snapshot(before), "after": fitness_snapshot(after),
    }


def _history_stats(entries: list[dict], now: float, cooldown: float) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for entry in entries:
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        task_key = str(detail.get("task_key") or "")
        if not task_key:
            continue
        row = stats.setdefault(task_key, {"attempts": 0, "regressions": 0, "last_regression_ts": None})
        # Successful review-eligible experiments reset the retry budget.  The budget is for consecutive
        # unsuccessful attempts, not a lifetime ban on refreshing a lane whose evidence naturally expires.
        if detail.get("eligible_for_review"):
            row.update({"attempts": 0, "regressions": 0, "last_regression_ts": None})
            continue
        row["attempts"] += 1
        if detail.get("disposition") == "REGRESSION_QUARANTINED":
            row["regressions"] += 1
            row["last_regression_ts"] = max(float(entry.get("ts") or 0), row["last_regression_ts"] or 0)
    for row in stats.values():
        last = row.get("last_regression_ts")
        row["cooldown_active"] = bool(last and now - last < cooldown)
    return stats


def rank_tasks(tasks: list[dict], report: dict, history: list[dict] | None = None,
               policy: ImprovementPolicy | None = None, now: float | None = None) -> list[dict]:
    """Rank by current evidence first, then configured value/cost, then failure memory."""
    policy = policy or ImprovementPolicy()
    policy.validate()
    now = float(time.time() if now is None else now)
    stats = _history_stats(history or [], now, policy.regression_cooldown_seconds)
    diversity = build_diversity_plan(history or [], now=now,
                                     cooldown_seconds=policy.regression_cooldown_seconds)
    by_domain: dict[str, list[dict]] = {}
    for row in _results(report):
        if _state(row) != "PASS":
            by_domain.setdefault(str(row.get("domain") or ""), []).append(row)
    pipeline_counts: dict[str, int] = {}
    for task in tasks:
        pipeline = str(task.get("pipeline") or "")
        pipeline_counts[pipeline] = pipeline_counts.get(pipeline, 0) + 1

    ranked = []
    for task in tasks:
        pipeline, asset = str(task.get("pipeline") or ""), str(task.get("asset_id") or "")
        task_key = f"{pipeline}:{asset}"
        family = family_for_pipeline(pipeline)
        family_plan = diversity["families"].get(family, {})
        hist = stats.get(task_key, {"attempts": 0, "regressions": 0, "cooldown_active": False})
        domains = sorted(PIPELINE_DOMAINS.get(pipeline, set()))
        evidence = []
        evidence_score = 0.0
        worst_state_rank = 0
        for domain in domains:
            for row in by_domain.get(domain, []):
                # When one pipeline has per-asset tasks, bind evidence to the named asset instead of giving
                # every character credit for every other character's blockers.
                if pipeline_counts.get(pipeline, 0) > 1:
                    searchable = json.dumps(row, sort_keys=True, default=str).lower()
                    if asset.lower() not in searchable:
                        continue
                state = _state(row)
                severity_scale = 1.0 if str(row.get("severity") or "blocker").lower() == "blocker" else 0.25
                evidence_score += NON_PASS_WEIGHT.get(state, 0.0) * severity_scale
                worst_state_rank = max(worst_state_rank, STATE_RANK[state])
                evidence.append({"domain": domain, "validator_id": row.get("validator_id"), "state": state})
        cost = max(0.1, float(task.get("cost", 1.0) or 1.0))
        configured = float(task.get("priority", 0) or 0) + float(task.get("expected_value", 1) or 1) - cost
        failure_penalty = 8.0 * int(hist.get("regressions", 0)) + 2.0 * int(hist.get("attempts", 0))
        score = round(evidence_score + configured - failure_penalty, 4)
        quarantined = bool(hist.get("cooldown_active")) or int(hist.get("attempts", 0)) >= policy.max_attempts_per_task
        ranked.append({
            "task": dict(task), "task_key": task_key, "pipeline": pipeline, "asset_id": asset,
            "family": family, "diversity_score": float(family_plan.get("diversity_score", 1.0)),
            "family_advisory_cooldown": bool(family_plan.get("advisory_cooldown", False)),
            "domains": domains, "evidence": evidence, "evidence_score": round(evidence_score, 4),
            "evidence_count": len(evidence), "worst_state_rank": worst_state_rank,
            "configured_score": round(configured, 4), "failure_penalty": round(failure_penalty, 4),
            "score": score, "cost": cost, "attempts": int(hist.get("attempts", 0)),
            "quarantined": quarantined,
            "quarantine_reason": ("regression cooldown active" if hist.get("cooldown_active")
                                  else ("attempt budget exhausted" if quarantined else None)),
        })
    # Evidence is lexicographically authoritative: a configured priority cannot drown out a real current
    # REJECTED/FAIL/BLOCKED validator.  Within the evidence class, breadth and configured value break ties.
    ranked.sort(key=lambda row: (-int(bool(row["evidence_count"])), -row["worst_state_rank"],
                                 -row["evidence_score"], -row["diversity_score"], -row["score"],
                                 row["cost"], row["task_key"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def select_budgeted_tasks(ranked: list[dict], policy: ImprovementPolicy) -> dict:
    policy.validate()
    selected, skipped, spent = [], [], 0.0
    for row in ranked:
        reason = None
        if row.get("quarantined"):
            reason = row.get("quarantine_reason") or "quarantined"
        elif len(selected) >= policy.max_tasks:
            reason = "task budget exhausted"
        elif spent + float(row["cost"]) > policy.max_total_cost:
            reason = "cost budget exhausted"
        if reason:
            skipped.append({**row, "skip_reason": reason})
            continue
        selected.append(row)
        spent += float(row["cost"])
    return {"selected": selected, "skipped": skipped, "cost": round(spent, 4)}


class RecursiveImprovementController:
    """Execute bounded experiments with injected validation/pipeline hooks for deterministic testing."""

    def __init__(self, root: Path = ROOT, policy: ImprovementPolicy | None = None,
                 pipeline_factory: Callable[[str], Any] = get_pipeline,
                 pipeline_names: Callable[[], list[str]] = list_pipelines,
                 validate_fn: Callable[[], dict] | None = None,
                 ledger_path: Path | None = None, artifact_path: Path | None = None):
        self.root = Path(root)
        self.policy = policy or ImprovementPolicy.load(self.root / "config" / "improvement_policy.json")
        self.policy.validate()
        self.pipeline_factory = pipeline_factory
        self.pipeline_names = pipeline_names
        if validate_fn is None:
            from dimwit.director import Director
            validate_fn = Director().validate_everything
        self.validate_fn = validate_fn
        self.ledger = DimwitLedger(ledger_path or (self.root / "ledger" / "improvement_experiments.jsonl"))
        self.artifact_path = Path(artifact_path or (self.root / "artifacts" / "autonomy" / "recursive_improvement_run.json"))

    def _history(self) -> list[dict]:
        try:
            return self.ledger.entries()
        except Exception:
            return []

    def plan(self, tasks: list[dict], report: dict, now: float | None = None) -> dict:
        history = self._history()
        ranked = rank_tasks(tasks, report, history, self.policy, now=now)
        budget = select_budgeted_tasks(ranked, self.policy)
        return {
            "policy": asdict(self.policy), "baseline": fitness_snapshot(report),
            "diversity_plan": build_diversity_plan(history, now=now,
                                                     cooldown_seconds=self.policy.regression_cooldown_seconds),
            "selected": budget["selected"], "skipped": budget["skipped"],
            "planned_cost": budget["cost"], "review_ceiling": REVIEW_CEILING,
        }

    def run(self, tasks: list[dict], execute: bool = False) -> dict:
        started = time.time()
        baseline = self.validate_fn() if execute else self._read_latest_report()
        plan = self.plan(tasks, baseline, now=started)
        out = {
            "schema_version": 1, "mode": "execute" if execute else "plan", "started_at": started,
            "review_ceiling": REVIEW_CEILING, "policy": plan["policy"], "baseline": plan["baseline"],
            "diversity_plan": plan["diversity_plan"],
            "selection": {"selected": plan["selected"], "skipped": plan["skipped"],
                          "planned_cost": plan["planned_cost"]},
            "experiments": [], "eligible_review_queue": [], "quarantined": [],
            "operator_only_states_written": [],
        }
        if not execute:
            out["state"] = "PLAN_ONLY"
            out["finished_at"] = time.time()
            return out

        if not _results(baseline):
            out["state"] = "BASELINE_BLOCKED"
            out["issues"] = ["authoritative baseline validation produced no validator results"]
            out["finished_at"] = time.time()
            self._write_artifact(out)
            return out

        current_report = baseline
        known = set(self.pipeline_names())
        for candidate in plan["selected"]:
            if time.time() - started >= self.policy.max_wall_seconds:
                out["experiments"].append({"task_key": candidate["task_key"], "state": "BUDGET_BLOCKED",
                                           "reason": "wall-clock budget exhausted"})
                break
            experiment_started = time.time()
            pipeline_name = candidate["pipeline"]
            if pipeline_name not in known:
                experiment = {"task_key": candidate["task_key"], "pipeline": pipeline_name,
                              "state": "EXECUTION_BLOCKED", "disposition": "EVALUATION_BLOCKED",
                              "error": "unknown pipeline"}
                out["experiments"].append(experiment)
                self._record(experiment, experiment_started)
                continue
            try:
                result = self.pipeline_factory(pipeline_name).run(candidate["task"])
                pipeline_state = str(result.state).split(".")[-1]
                pipeline_score = float(result.score)
                pipeline_error = None
            except Exception as exc:
                pipeline_state, pipeline_score = "EXECUTION_ERROR", 0.0
                pipeline_error = f"{type(exc).__name__}: {exc}"

            if pipeline_error:
                delta = {"disposition": "EVALUATION_BLOCKED", "issues": [pipeline_error],
                         "resolved": [], "regressed": [], "added_passes": [],
                         "before": fitness_snapshot(current_report), "after": fitness_snapshot(current_report)}
                post_report = current_report
            elif self.policy.validate_after_each_task:
                post_report = self.validate_fn()
                delta = compare_validation_reports(current_report, post_report)
            else:
                post_report = current_report
                delta = {"disposition": "EVALUATION_BLOCKED",
                         "issues": ["policy disabled validation_after_each_task; candidate cannot be trusted"],
                         "resolved": [], "regressed": [], "added_passes": [],
                         "before": fitness_snapshot(current_report), "after": fitness_snapshot(current_report)}

            eligible = (pipeline_state == REVIEW_CEILING
                        and delta["disposition"] in {"IMPROVED_CANDIDATE", "STABLE_CANDIDATE"})
            experiment = {
                "task_key": candidate["task_key"], "pipeline": pipeline_name,
                "asset_id": candidate["asset_id"], "pipeline_state": pipeline_state,
                "pipeline_score": pipeline_score, "disposition": delta["disposition"],
                "eligible_for_review": eligible, "validation_delta": delta,
                "elapsed_seconds": round(time.time() - experiment_started, 3),
                "error": pipeline_error,
            }
            out["experiments"].append(experiment)
            self._record(experiment, experiment_started)
            if eligible:
                out["eligible_review_queue"].append({"pipeline": pipeline_name,
                                                     "asset_id": candidate["asset_id"],
                                                     "score": pipeline_score})
            if delta["disposition"] == "REGRESSION_QUARANTINED":
                out["quarantined"].append({"task_key": candidate["task_key"],
                                           "regressions": delta["regressed"]})
                current_report = post_report
                if self.policy.stop_on_regression:
                    break
            elif pipeline_error and self.policy.stop_on_execution_error:
                break
            else:
                current_report = post_report

        out["finished_at"] = time.time()
        out["elapsed_seconds"] = round(out["finished_at"] - started, 3)
        out["final_fitness"] = fitness_snapshot(current_report)
        out["state"] = ("REGRESSION_QUARANTINED" if out["quarantined"] else
                        ("CANDIDATES_READY_FOR_REVIEW" if out["eligible_review_queue"] else
                         "COMPLETED_NO_REVIEW_CANDIDATE"))
        self._write_artifact(out)
        return out

    def _read_latest_report(self) -> dict:
        path = self.root / "artifacts" / "validation" / "validation_report_full.json"
        if not path.exists():
            return {"suite_verdict": "NOT_RUN", "results": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _record(self, experiment: dict, started: float) -> None:
        disposition = str(experiment.get("disposition") or "EVALUATION_BLOCKED")
        if disposition in OPERATOR_ONLY_STATES:
            raise RuntimeError("operator-only state refused")
        self.ledger.append({
            "ts": int(time.time()), "actor": "recursive-improvement-controller",
            "asset_id": str(experiment.get("asset_id") or experiment.get("task_key") or "experiment"),
            "state": f"improvement.{disposition}",
            "candidate_hash": sha256_obj({"task": experiment.get("task_key"), "started": started,
                                           "pipeline_state": experiment.get("pipeline_state")}),
            "detail": {"task_key": experiment.get("task_key"), "pipeline": experiment.get("pipeline"),
                       "disposition": disposition, "eligible_for_review": experiment.get("eligible_for_review", False),
                       "regressed": (experiment.get("validation_delta") or {}).get("regressed", []),
                       "fitness_before": (experiment.get("validation_delta") or {}).get("before"),
                       "fitness_after": (experiment.get("validation_delta") or {}).get("after"),
                       "error": experiment.get("error")},
        })

    def _write_artifact(self, payload: dict) -> None:
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.artifact_path.with_suffix(self.artifact_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        temp.replace(self.artifact_path)
