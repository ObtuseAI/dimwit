"""Run Dimwit's evidence-driven recursive improvement controller.

Plan-only is the safe default:
  python scripts/pipeline/run_recursive_improvement.py
  python scripts/pipeline/run_recursive_improvement.py --execute
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys
from dataclasses import replace

from dimwit.director import load_tasks
from dimwit.improvement import ImprovementPolicy, RecursiveImprovementController
from dimwit.improvement_outcomes import record_outcome, summarize_outcomes


def _value(argv: list[str], name: str, default, cast):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main(argv: list[str]) -> int:
    if "--outcomes" in argv:
        print(json.dumps(summarize_outcomes(), indent=2, default=str))
        return 0
    if "--record-outcome" in argv:
        required = {name: _value(argv, name, "", str) for name in
                    ("--record-outcome", "--decision", "--reviewer", "--rationale")}
        if any(not value for value in required.values()):
            print(json.dumps({"error": "--record-outcome TASK requires --decision, --reviewer, and --rationale"}))
            return 2
        result = record_outcome(required["--record-outcome"], required["--decision"],
                                required["--reviewer"], required["--rationale"])
        print(json.dumps(result, indent=2, default=str))
        return 0
    policy = ImprovementPolicy.load()
    policy = replace(
        policy,
        max_tasks=_value(argv, "--max-tasks", policy.max_tasks, int),
        max_total_cost=_value(argv, "--max-cost", policy.max_total_cost, float),
        max_wall_seconds=_value(argv, "--max-seconds", policy.max_wall_seconds, float),
    )
    tasks = load_tasks()
    if not tasks:
        print(json.dumps({"error": "no tasks in config/director_tasks.json"}))
        return 2
    result = RecursiveImprovementController(policy=policy).run(tasks, execute="--execute" in argv)
    print(json.dumps(result, indent=2, default=str))
    if result.get("state") in {"REGRESSION_QUARANTINED", "BASELINE_BLOCKED"}:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
