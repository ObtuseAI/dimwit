"""Dimwit elite full-game studio runner. Plan-only unless --execute is supplied."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys

from dimwit.toolchains.studio import StudioController


def _value(argv: list[str], name: str, default, cast):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main(argv: list[str]) -> int:
    controller = StudioController()
    if "--status" in argv:
        result = controller.plan()
    else:
        result = controller.run(execute="--execute" in argv,
                                max_nodes=_value(argv, "--max-nodes", 3, int),
                                max_cost=_value(argv, "--max-cost", 6.0, float),
                                max_seconds=_value(argv, "--max-seconds", 14400.0, float))
    print(json.dumps(result, indent=2, default=str))
    return 1 if result.get("state") in {"BLOCKED", "FAILED"} else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
