"""Adversarial proof for the mrq_capture_advanced validator (Z2 motion gate, anti-rubber-stamp).

  python scripts/qa/gen_mrq_capture_proofs.py   # exit 0 only if all proofs pass

Proves: registry grew to 114; an ADVANCING MRQ capture PASSES; a FROZEN one FAILS; an ABSENT one BLOCKS.
Runs the validator through the real ValidationSuite (no internals assumed). Restores the real artifact."""
from __future__ import annotations
import json, os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dimwit.pipelines.validation import ValidationContext, ValidationSuite
from dimwit.pipelines.validation_registry import build_registry

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "mrq_capture_result.json")
BAK = ART + ".proofbak"
results = []
def chk(name, cond, detail=""):
    results.append(bool(cond)); print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")

def state_of():
    reg = [v for v in build_registry() if v.id == "mrq_capture_advanced"]
    rep = ValidationSuite(ValidationContext(run_ue=False), reg).run()
    return rep["results"][0]["state"]

chk("registry == 114", len(build_registry()) == 114, f"n={len(build_registry())}")
assert os.path.exists(ART), "run emit_mrq_artifacts.py first"
real = json.load(open(ART))
chk("ADVANCING capture -> PASS", state_of() == "PASS", f"avg_delta={real.get('avg_consecutive_delta')}")

shutil.copy(ART, BAK)
try:
    json.dump({**real, "avg_consecutive_delta": 0.02, "max_consecutive_delta": 0.05, "advancing": False},
              open(ART, "w"), indent=2)
    chk("FROZEN capture -> FAIL/REJECTED (anti-rubber-stamp)", state_of() in ("FAIL", "REJECTED"))
    os.remove(ART)
    chk("ABSENT capture -> BLOCKED (fail-closed)", state_of() == "BLOCKED")
finally:
    shutil.move(BAK, ART)
chk("real artifact restored -> PASS", state_of() == "PASS")

ok = all(results)
print(f"\n{'ALL PASS' if ok else 'FAILURES'} — {sum(results)}/{len(results)}")
sys.exit(0 if ok else 1)
