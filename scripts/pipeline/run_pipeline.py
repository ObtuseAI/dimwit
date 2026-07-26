"""Dimwit production-pipeline runner.

  python scripts/pipeline/run_pipeline.py --list
  python scripts/pipeline/run_pipeline.py character_fidelity ekris
  python scripts/pipeline/run_pipeline.py character_fidelity ekris --threshold 0.9
  python scripts/pipeline/run_pipeline.py rigging ekris
  python scripts/pipeline/run_pipeline.py marble_ingest src="C:\\path\\world.glb" ref_dim_meters=2.4 license="World Labs Pro"

The first positional after the pipeline name (if it isn't a flag or a key=value) is the asset_id. Any remaining
`key=value` tokens are forwarded into the task dict (src=, license=, ref_dim_meters=, kind=, ...), lightly coerced
to bool/int/float so pipelines like marble_ingest can be driven from the CLI. Pipelines ignore keys they don't use.

Each pipeline shares the fully-proofed recursive backbone (plan->execute->QA->repair->hash-chained ledger->
human-gated promotion). Prints the PipelineResult JSON; the proof trail is appended to ledger/pipelines/<name>.jsonl.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys

from dimwit.pipelines import get_pipeline, list_pipelines


def _coerce(v: str):
    """CLI values arrive as strings; coerce the obvious ones so e.g. playable=0 is falsey and ref_dim_meters=2.4
    is a float. Leave anything ambiguous (paths, license strings) as text."""
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def main(argv):
    if not argv or argv[0] in ("--list", "-l", "list"):
        print(json.dumps({"pipelines": list_pipelines()}, indent=2))
        return 0
    name = argv[0]
    rest = argv[1:]

    # First positional that isn't a flag or a key=value is the asset_id.
    asset = None
    if rest and not rest[0].startswith("--") and "=" not in rest[0]:
        asset = rest[0]

    kw = {}
    if "--threshold" in argv:
        kw["threshold"] = float(argv[argv.index("--threshold") + 1])

    default_asset = {
        "character_source_sync": "active",
        "character_roster_policy": "active_roster",
        "character_fidelity": "vorlax",
        "rigging": "vorlax",
        "animation": "vorlax",
        "metahuman_output_attempt": "vorlax",
    }.get(name, "asset")

    # Forward arbitrary key=value tokens into the task dict (skip the --threshold value).
    task = {"asset_id": asset or default_asset}
    skip_next = False
    for tok in rest:
        if skip_next:
            skip_next = False
            continue
        if tok == "--threshold":
            skip_next = True
            continue
        if tok.startswith("--"):
            continue
        if "=" in tok:
            k, _, val = tok.partition("=")
            task[k.strip()] = _coerce(val.strip())

    if name not in list_pipelines():
        print(json.dumps({"error": f"unknown pipeline '{name}'", "known": list_pipelines()}))
        return 2
    pipe = get_pipeline(name, **kw)
    result = pipe.run(task)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if str(result.state) in ("State.PROMOTED_TO_REVIEW", "PROMOTED_TO_REVIEW") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
