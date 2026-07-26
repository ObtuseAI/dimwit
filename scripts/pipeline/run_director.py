"""Dimwit director runner — the autonomous production loop.

  python scripts/pipeline/run_director.py            # run the default sweep (config/director_tasks.json) to PROMOTED_TO_REVIEW
  python scripts/pipeline/run_director.py --dry      # plan-only: validate inputs/tools for every task, run nothing
  python scripts/pipeline/run_director.py --review   # show the standing operator review queue
  python scripts/pipeline/run_director.py --validate # self-validate every registered pipeline
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys

from dimwit.director import Director, load_tasks
from dimwit.pipelines.validate import validate_all


def main(argv):
    d = Director()
    if "--validate" in argv:
        # pipeline self-check (wiring) + the full asset validation suite ("validate everything")
        out = {"pipeline_selfcheck": validate_all()}
        if "--no-ue" not in argv:
            out["validation_suite"] = d.validate_everything()
        print(json.dumps(out, indent=2, default=str))
        return 0
    if "--review" in argv:
        print(json.dumps({"review_queue": d.review_queue(),
                          "validation_summary": d.validation_summary()}, indent=2))
        return 0
    tasks = load_tasks()
    if not tasks:
        print(json.dumps({"error": "no tasks in config/director_tasks.json"}))
        return 2
    result = d.run_sweep(tasks, dry_run="--dry" in argv)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
