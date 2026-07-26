"""Audit Dimwit's curated open-source adoption registry without installing anything."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys

from dimwit.opensource_adoption import audit_ecosystem, write_default_report


def main(argv: list[str]) -> int:
    report = write_default_report() if "--write" in argv else audit_ecosystem()
    print(json.dumps(report, indent=2))
    return 0 if report["state"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
