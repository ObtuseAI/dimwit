"""Dimwit runner — process the Dimwit asset queue through the lifecycle + recursive mutation loop,
write Dimwit's OWN proof ledger, and package any review-ready asset for human review.

Stdlib-only. All writes are confined to the Dimwit workspace root. Dimwit NEVER writes into Blunder's
ledger/queue/state. Operator-only states (HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE) are never reached
autonomously.

Usage:  python scripts/pipeline/run_dimwit.py [--run-id RID]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dimwit.core import AssetTask, Lifecycle                          # noqa: E402
from dimwit.engine import DimwitLedger, DimwitQueue, assert_dimwit_path  # noqa: E402
from dimwit.build_loop import build_one                               # noqa: E402

LEDGER = ROOT / "proofs" / "dimwit_asset_proof_ledger.jsonl"
QUEUE = ROOT / "queues" / "dimwit_asset_queue.jsonl"
SEEDS = ROOT / "assets"
LESSONS = ROOT / "lessons" / "dimwit_asset_lessons.jsonl"

# Identity/palette dimensions whose lessons apply across ALL asset classes (a black-blob or magenta lesson on
# an enemy should also bias weapons/props). Everything else stays scoped to the class that learned it.
GLOBAL_LESSON_DIMS = {"palette_discipline", "not_magenta_dominant", "not_white_debug_junk",
                      "not_generic_ai_slop", "silhouette_readability", "not_black_blob"}


def _read_lessons() -> list:
    if not LESSONS.exists():
        return []
    return [json.loads(ln) for ln in LESSONS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def learn(report, run_id: str) -> dict | None:
    """Compounding learn step: turn a FAILED run into a deduped, occurrence-counted lesson tagged by domain
    (asset class) + weakest dimension. Global-identity dims are scoped 'global'; others 'class'. Deduped by
    lesson_id `L_<domain>_<dim>` (won't collide with seed lessons L000..). Returns the lesson, or None."""
    if report.final_state not in (Lifecycle.REJECTED, Lifecycle.NEEDS_RECURSION):
        return None
    dim = report.weakest_dimension or "unknown"
    domain = report.asset_type
    cand = report.best_candidate or {}
    hard = [h.get("trait") for h in (cand.get("perception", {}) or {}).get("hard_fails", [])]
    lesson_id = f"L_{domain}_{dim}"
    lessons = _read_lessons()
    found = next((L for L in lessons if L.get("lesson_id") == lesson_id), None)
    if found:
        found["occurrences"] = int(found.get("occurrences", 1)) + 1
        found["last_run"] = run_id
        if hard:
            found["measured_hard_fails"] = sorted(set(found.get("measured_hard_fails", []) + hard))
        lesson = found
    else:
        lesson = {"lesson_id": lesson_id,
                  "lesson": f"{domain}: weakest dimension '{dim}' failed ({report.final_state})",
                  "domain": domain, "dimension": dim,
                  "scope": "global" if dim in GLOBAL_LESSON_DIMS else "class",
                  "occurrences": 1, "measured_hard_fails": hard,
                  "source": "dimwit_runtime_learn", "last_run": run_id, "from_real_run": True}
        lessons.append(lesson)
    assert_dimwit_path(LESSONS)
    with LESSONS.open("w", encoding="utf-8") as f:
        for L in lessons:
            f.write(json.dumps(L, ensure_ascii=False, sort_keys=True) + "\n")
    return lesson


def _load_seed(asset_id: str) -> tuple[dict, dict]:
    """Resolve a queued task's seed spec + evidence from Dimwit/assets/<asset_id>/asset_spec.json (+ provenance)."""
    base = SEEDS / asset_id
    spec = json.loads((base / "asset_spec.json").read_text(encoding="utf-8")) if (base / "asset_spec.json").exists() else {}
    prov = json.loads((base / "provenance.json").read_text(encoding="utf-8")) if (base / "provenance.json").exists() else {}
    evidence = spec.pop("_evidence", {}) if isinstance(spec, dict) else {}
    evidence["provenance"] = prov
    return spec, evidence


def _load_contract(asset_id: str) -> dict | None:
    """Load the per-build intent contract (spec_author.author_intent_contract) if one was authored for this
    asset. Its presence makes the fused gate compare the capture to the declared reference; absence falls back
    to the frozen asset_type floors (still fail-closed, just without an identity target)."""
    f = SEEDS / asset_id / "intent_contract.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def main(run_id: str = "dimwit_run") -> int:
    assert_dimwit_path(LEDGER)
    assert_dimwit_path(QUEUE)
    ledger = DimwitLedger(LEDGER)
    queue = DimwitQueue(QUEUE)
    items = queue.items()
    if not items:
        print("[Dimwit] queue empty — nothing to do")
        return 0

    results = []
    for it in items:
        if it.get("status") in ("PROMOTED_TO_REVIEW", "REJECTED", "BLOCKED"):
            continue
        task = AssetTask(asset_id=it["asset_task_id"], asset_type=it["asset_type"],
                         source_kind=it.get("source_kind", "existing_placeholder"),
                         source_paths=it.get("source_paths", []),
                         intended_gameplay_role=it.get("intended_gameplay_role", ""),
                         promotion_target=it.get("promotion_target", "review_only"))
        spec, evidence = _load_seed(task.asset_id)
        # author-if-missing the intent contract (from the task's source reference), run the hardened fused-gate
        # loop, and package the intent-vs-actual review — one wired path via build_one.
        built = build_one(task, spec, evidence, ledger, run_id=f"{run_id}_{task.asset_id}")
        if built["state"] == Lifecycle.BLOCKED and built["report"] is None:
            # authoring itself was refused (vacuous target / anti-retrofit) — surface and skip the run
            it["status"] = Lifecycle.BLOCKED
            it["attempt_count"] = int(it.get("attempt_count", 0)) + 1
            it["next_action"] = "author_intent_first"
            it["blocked_reason"] = (built["authoring"] or {}).get("reason") if isinstance(built["authoring"], dict) else str(built["authoring"])
            queue.upsert(it)
            results.append({"asset_id": task.asset_id, "state": Lifecycle.BLOCKED,
                            "blocked_reason": it["blocked_reason"]})
            print(f"[Dimwit] {task.asset_id} -> BLOCKED (intent authoring refused: {it['blocked_reason']})")
            continue
        report = built["report"]
        pkg = built["review_package"]
        lesson = learn(report, run_id=f"{run_id}_{task.asset_id}")     # compounding: failure -> deduped lesson
        it["status"] = report.final_state
        it["latest_candidate_id"] = report.best_candidate.get("candidate_id")
        it["attempt_count"] = int(it.get("attempt_count", 0)) + 1
        it["next_action"] = "human_review" if report.final_state == "PROMOTED_TO_REVIEW" else "recurse_or_block"
        queue.upsert(it)
        results.append({"asset_id": task.asset_id, "state": report.final_state, "overall": report.overall,
                        "iterations": report.iterations, "review_package": pkg["package_dir"],
                        "lesson": lesson.get("lesson_id") if lesson else None})
        print(f"[Dimwit] {task.asset_id} -> {report.final_state} (overall={report.overall:.3f}, iters={report.iterations})")

    print(json.dumps({"run_id": run_id, "processed": len(results), "results": results,
                      "ledger_check": ledger.consistency_check()}, indent=2))
    return 0


if __name__ == "__main__":
    rid = "dimwit_run"
    if "--run-id" in sys.argv:
        rid = sys.argv[sys.argv.index("--run-id") + 1]
    raise SystemExit(main(rid))
