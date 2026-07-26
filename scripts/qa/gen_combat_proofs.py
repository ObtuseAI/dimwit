"""Adversarial proof for the combat domain validators (state-clarity + weak-point, anti-rubber-stamp).
  python scripts/qa/gen_combat_proofs.py   # exit 0 only if all proofs pass"""
from __future__ import annotations
import json, os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dimwit.pipelines.validation import ValidationContext, ValidationSuite
from dimwit.pipelines.validation_registry import build_registry

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "combat_capture_result.json")
BAK = ART + ".proofbak"
results = []
def chk(name, cond, detail=""):
    results.append(bool(cond)); print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")
def state_of(vid):
    reg = [v for v in build_registry() if v.id == vid]
    return ValidationSuite(ValidationContext(run_ue=False), reg).run()["results"][0]["state"]

chk("registry == 116", len(build_registry()) == 116, f"n={len(build_registry())}")
assert os.path.exists(ART), "run emit_combat_artifact.py first"
real = json.load(open(ART))
chk("real distinct states -> state_clarity PASS", state_of("combat_state_clarity") == "PASS", f"min_delta={real.get('min_state_delta')}")
chk("real red core -> weakpoint PASS", state_of("combat_weakpoint_in_range") == "PASS", f"red%={real.get('weakpoint_red_pct')}")

shutil.copy(ART, BAK)
try:
    json.dump({**real, "state_deltas": {"live_vs_hit": 0.1, "live_vs_destroyed": 0.1, "hit_vs_destroyed": 0.1}, "min_state_delta": 0.1}, open(ART, "w"), indent=2)
    chk("indistinct states -> state_clarity FAIL/REJECTED", state_of("combat_state_clarity") in ("FAIL", "REJECTED"))
    json.dump({**real, "weakpoint_red_pct": 0.0, "weakpoint_orange_pct": 6.0}, open(ART, "w"), indent=2)
    chk("washed weak-point -> weakpoint FAIL/REJECTED", state_of("combat_weakpoint_in_range") in ("FAIL", "REJECTED"))
    os.remove(ART)
    chk("absent -> state_clarity BLOCKED", state_of("combat_state_clarity") == "BLOCKED")
finally:
    shutil.move(BAK, ART)
chk("restored -> PASS", state_of("combat_state_clarity") == "PASS")

ok = all(results)
print(f"\n{'ALL PASS' if ok else 'FAILURES'} — {sum(results)}/{len(results)}")
sys.exit(0 if ok else 1)
