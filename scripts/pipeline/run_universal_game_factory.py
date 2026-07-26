"""Inventory, scan, plan, or run Dimwit's universal game-engine adapters."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys

from dimwit.toolchains.engines.universal import (
    audit_engines,
    plan_build,
    run_build,
    scan_projects,
    write_engine_audit,
)
from dimwit.toolchains.engines.cross_engine import compare_build_receipts


def _value(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv: list[str]) -> int:
    if "--cross-engine" in argv:
        brief = _value(argv, "--brief")
        output = _value(argv, "--proof-output")
        receipts = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "--receipt"]
        if not brief or len(receipts) != 2:
            print(json.dumps({"error": "--cross-engine requires --brief and exactly two --receipt values"}))
            return 2
        result = compare_build_receipts(brief, receipts, output)
    elif "--scan" in argv:
        result = {"state": "PASS", "projects": scan_projects(_value(argv, "--scan"))}
    elif "--project" in argv:
        required = {name: _value(argv, name) for name in ("--project", "--target", "--output")}
        if any(value is None for value in required.values()):
            print(json.dumps({"error": "--project, --target, and --output are required"}))
            return 2
        kwargs = {
            "engine": _value(argv, "--engine", "auto"), "profile": _value(argv, "--profile", "release"),
            "preset": _value(argv, "--preset"), "job_id": _value(argv, "--job-id", "universal_game_build"),
            "brief": _value(argv, "--brief"),
        }
        function = run_build if "--execute" in argv else plan_build
        if function is run_build:
            kwargs["allow_mutation"] = True
        result = function(required["--project"], required["--target"], required["--output"], **kwargs)
    else:
        result = write_engine_audit() if "--write" in argv else audit_engines()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("state") in {"PASS", "PLAN_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
