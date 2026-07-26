"""Audit or plan Dimwit's cross-engine mobile game factory."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys
from pathlib import Path

from dimwit.toolchains.mobile import audit_mobile, plan_mobile_build, run_mobile_build, write_mobile_audit


def _value(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv: list[str]) -> int:
    if "--project" not in argv:
        result = write_mobile_audit() if "--write" in argv else audit_mobile()
    else:
        values = {name: _value(argv, name) for name in ("--project", "--target", "--output", "--manifest")}
        if any(value is None for value in values.values()):
            print(json.dumps({"error": "--project, --target, --output, and --manifest are required"}))
            return 2
        manifest = json.loads(Path(values["--manifest"]).read_text(encoding="utf-8"))
        kwargs = {"manifest": manifest, "engine": _value(argv, "--engine", "auto"),
                  "profile": _value(argv, "--profile", "release"), "preset": _value(argv, "--preset"),
                  "job_id": _value(argv, "--job-id", "mobile_game_build")}
        if "--execute" in argv:
            result = run_mobile_build(values["--project"], values["--target"], values["--output"],
                                      allow_mutation=True, **kwargs)
        else:
            result = plan_mobile_build(values["--project"], values["--target"], values["--output"], **kwargs)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("state") in {"PASS", "PLAN_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
