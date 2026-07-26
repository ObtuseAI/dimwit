"""Dimwit — VALIDATE EVERYTHING.

  python scripts/pipeline/run_validation.py                 # full fail-closed suite (static+fs+ledger+compile + ONE UE batch + perception)
  python scripts/pipeline/run_validation.py --no-ue         # skip the UE batch (UE/perception validators -> BLOCKED, suite cannot PASS)
  python scripts/pipeline/run_validation.py --domain <d>    # one domain (substring match)
  python scripts/pipeline/run_validation.py --list          # list every registered validator
  python scripts/pipeline/run_validation.py --report        # print the latest validation_report.json (no run)

Exit code 0 only if suite_verdict == PASS (so it gates CI/cron/director).
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys
from pathlib import Path

from dimwit.pipelines.validation import ValidationContext, ValidationSuite, VAL_ART
from dimwit.pipelines.validation_registry import REGISTRY


def main(argv) -> int:
    if "--list" in argv:
        for v in sorted(REGISTRY, key=lambda x: (x.domain, x.id)):
            print(f"{v.severity.value:8} {v.probe_type.value:13} {v.domain[:34]:34} {v.id}")
        print(f"\ntotal: {len(REGISTRY)} validators")
        return 0
    if "--report" in argv:
        rp = VAL_ART / "validation_report.json"
        if not rp.exists():
            print(json.dumps({"error": "no validation_report.json yet; run `python scripts/pipeline/run_validation.py`"}))
            return 2
        print(rp.read_text(encoding="utf-8"))
        return 0
    domains = None
    if "--domain" in argv:
        domains = [argv[argv.index("--domain") + 1]]
    ctx = ValidationContext(run_ue=("--no-ue" not in argv))
    suite = ValidationSuite(ctx, REGISTRY)
    report = suite.run(domains)
    summary = {k: report[k] for k in ("suite_verdict", "counts", "by_domain", "ue_error", "total")}
    print(json.dumps(summary, indent=2))
    # also list the non-PASS validators for quick triage
    bad = [r for r in report["results"] if r["state"] != "PASS"]
    if bad:
        print("\nNON-PASS:")
        for r in bad:
            det = r.get("detail", {}) or {}
            iss = "; ".join(r.get("issues", []) or []) or det.get("blocked") or det.get("error", "")
            print(f"  [{r['state']:8}] {r['severity']:7} {r['validator_id']}  -- {iss[:120]}")
    return 0 if report["suite_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
