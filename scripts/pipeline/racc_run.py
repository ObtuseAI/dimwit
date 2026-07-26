"""Dimwit Autonomous Compounding Controller (RACC) — the OUTER director (task 5).

Wraps the existing per-asset engine: pick_next -> run one asset (untouched `run_asset_task`) -> learn (task 3)
-> upsert queue -> hash-chained ATTEMPT ledger -> repeat until no actionable work / budget / circuit breaker.
At the end of a sweep it applies accrued lessons to class-profile weights (task 4) — so the bar compounds.

Doctrine preserved: deterministic priority first (brain only tie-breaks, schema-validated, advisory); never
auto-promotes past PROMOTED_TO_REVIEW; thresholds ratchet up only; operator-only states never reached.

Usage:  python scripts/pipeline/racc_run.py [--run-id RID] [--max-assets N]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.pipeline import run_dimwit as R                                                  # reuse _load_seed, learn, paths  # noqa: E402
from dimwit.core import AssetTask, Lifecycle                           # noqa: E402
from dimwit.engine import (DimwitLedger, DimwitQueue, run_asset_task,  # noqa: E402
                            assert_dimwit_path, promotion_threshold)

DIRECTOR_LEDGER = ROOT / "proofs" / "dimwit_director_ledger.jsonl"     # separate, hash-chained autonomy log
MAX_ATTEMPTS = 3                                                        # per-asset circuit breaker (mirror Blunder <=3)
SKIP_STATES = {Lifecycle.PROMOTED_TO_REVIEW, Lifecycle.REJECTED, Lifecycle.BLOCKED} | set(Lifecycle.OPERATOR_ONLY)
PW = {"explicit": 1.0, "value": 1.0, "cost": 0.3, "fail_penalty": 0.5}


def _criticality(asset_type: str) -> float:
    t = (asset_type or "").lower()
    if any(k in t for k in ("enemy", "construct", "hostile")): return 1.0
    if any(k in t for k in ("weapon", "gun")): return 0.9
    if "vehicle" in t: return 0.7
    if any(k in t for k in ("prop", "kit", "env")): return 0.4
    return 0.6


def _priority(it: dict) -> float:
    explicit = float(it.get("priority", 0.5))
    last = float(it.get("last_overall", 0.0))
    thr = promotion_threshold(it.get("asset_type", ""))
    # near-passing cheap wins score high; never-run items fall back to class criticality
    expected_value = _criticality(it.get("asset_type", "")) if last <= 0 else max(0.0, 1.0 - max(0.0, thr - last))
    cost = float(it.get("est_cost", 0.3))
    fail_penalty = float(it.get("attempt_count", 0))
    return (PW["explicit"] * explicit + PW["value"] * expected_value
            - PW["cost"] * cost - PW["fail_penalty"] * fail_penalty)


def pick_next(items: list):
    """Deterministic-first selection: actionable, under the attempt cap, highest priority. Returns one item or None."""
    actionable = [it for it in items
                  if it.get("status") not in SKIP_STATES and int(it.get("attempt_count", 0)) < MAX_ATTEMPTS]
    if not actionable:
        return None
    ranked = sorted(actionable, key=_priority, reverse=True)
    # (brain tie-break hook: when ranked[0]/ranked[1] are within epsilon, cloud_brain.plan_queue may advise —
    #  accepted only if schema-valid; offline/degraded => deterministic order. Advisory, never dispatching.)
    return ranked[0]


def main(run_id: str = "racc", max_assets: int | None = None) -> int:
    assert_dimwit_path(R.LEDGER); assert_dimwit_path(DIRECTOR_LEDGER)
    ledger = DimwitLedger(R.LEDGER)
    director = DimwitLedger(DIRECTOR_LEDGER)
    queue = DimwitQueue(R.QUEUE)
    processed = []

    while True:
        if max_assets is not None and len(processed) >= max_assets:
            break
        item = pick_next(queue.items())
        if item is None:
            break                                                       # clean HALT — no actionable work
        asset_id = item["asset_task_id"]
        rid = f"{run_id}_{asset_id}"
        director.append({"asset_id": asset_id, "state": "ATTEMPT_STARTED", "candidate_hash": "n/a",
                         "kind": "director", "run_id": rid, "attempt": int(item.get("attempt_count", 0)) + 1})
        try:
            task = AssetTask(asset_id=asset_id, asset_type=item["asset_type"],
                             source_kind=item.get("source_kind", "existing_placeholder"),
                             source_paths=item.get("source_paths", []),
                             intended_gameplay_role=item.get("intended_gameplay_role", ""),
                             promotion_target=item.get("promotion_target", "review_only"))
            spec, evidence = R._load_seed(asset_id)
            report = run_asset_task(task, spec, evidence, ledger, run_id=rid)
            R.learn(report, run_id=rid)                                  # compounding capture (task 3)
            item["status"] = report.final_state
            item["attempt_count"] = int(item.get("attempt_count", 0)) + 1
            item["last_overall"] = report.overall
            if report.final_state == Lifecycle.NEEDS_RECURSION and item["attempt_count"] >= MAX_ATTEMPTS:
                item["status"] = Lifecycle.BLOCKED                      # circuit breaker -> leave the queue
                item["redo_reason"] = f"circuit breaker: {MAX_ATTEMPTS} attempts, no promotion"
            queue.upsert(item)
            director.append({"asset_id": asset_id, "state": "ATTEMPT_FINISHED", "kind": "director",
                             "candidate_hash": report.best_candidate.get("candidate_hash", "none"),
                             "final": item["status"], "overall": report.overall, "run_id": rid})
            processed.append({"asset_id": asset_id, "final": item["status"], "overall": report.overall})
        except Exception as e:                                          # failure isolation — one asset can't halt the loop
            item["status"] = Lifecycle.BLOCKED
            item["redo_reason"] = f"exception: {e}"
            queue.upsert(item)
            director.append({"asset_id": asset_id, "state": "BLOCKED", "candidate_hash": "none",
                             "kind": "director", "error": str(e), "run_id": rid})
            processed.append({"asset_id": asset_id, "final": "BLOCKED", "error": str(e)})

    # end-of-sweep compounding: turn accrued lessons into ratcheted class-profile weights (task 4)
    from dimwit.learning.lesson_loop import apply_lessons_to_profiles
    weights = apply_lessons_to_profiles()

    out = {"run_id": run_id, "processed": processed, "count": len(processed),
           "weight_update": weights,
           "proof_ledger": ledger.consistency_check(),
           "director_ledger": director.consistency_check()}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    rid = sys.argv[sys.argv.index("--run-id") + 1] if "--run-id" in sys.argv else "racc"
    mx = int(sys.argv[sys.argv.index("--max-assets") + 1]) if "--max-assets" in sys.argv else None
    raise SystemExit(main(rid, mx))
