"""Proof tests for Step 5b — the intent contract wired into the validation SUITE:
  * v_intent_contract_no_drift   — tamper / DESIGN.md-drift / not-anchored / swapped-on-disk all REJECT;
  * v_intent_target_conformance  — matching capture PASSes, wrong-shape capture FAILs below the floor;
  * motion escalation            — a failing motion validator becomes a BLOCKER when the contract requires motion;
  * suite fuse                    — the four evidence domains collapse via confidence.fuse() (weakest-link).

Stdlib + numpy/Pillow. Run:  python -m dimwit.tests.test_suite_intent
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit import spec_author
from dimwit.pipelines import validation as V
from dimwit.pipelines import validation_registry as VR

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_suiteintent_"))


class _FakeLedger:
    def __init__(self): self.entries = []; self._head = "0" * 64
    def append(self, e): self.entries.append(e); self._head = spec_author.sha256_obj({"p": self._head, "e": e}); return self._head


def _humanoid(path, body=(150, 160, 170)):
    im = Image.new("RGB", (300, 420), (40, 44, 50)); d = ImageDraw.Draw(im)
    d.ellipse([130, 40, 175, 90], fill=body); d.rectangle([120, 90, 185, 230], fill=body)
    d.rectangle([122, 230, 148, 360], fill=body); d.rectangle([158, 230, 184, 360], fill=body)
    d.rectangle([135, 120, 170, 150], fill=(220, 120, 40)); im.save(path); return str(path)


def _blob(path):
    im = Image.new("RGB", (300, 420), (40, 44, 50)); d = ImageDraw.Draw(im)
    d.ellipse([90, 120, 210, 300], fill=(150, 160, 170)); im.save(path); return str(path)


REF = _humanoid(_TMP / "ref.png")
CAP_GOOD = _humanoid(_TMP / "cap_good.png")
CAP_WRONG = _blob(_TMP / "cap_wrong.png")
DESIGN_MD = _TMP / "DESIGN.md"
DESIGN_MD.write_text("# WANEFALL visual law v1\ncarapace metallic 0.0\nweakpoint emissive 1.0\n", encoding="utf-8")


def _author(asset_id, out, design_md_path=str(DESIGN_MD), refs=REF):
    led = _FakeLedger()
    r = spec_author.author_intent_contract(
        asset_id, "character", refs, declared_intent="dark alien melee enemy",
        design_md_path=design_md_path,
        provenance={"license_class": "owned_reference", "reference_license": "owned", "source_prompt": "p"},
        ledger=led, out_root=out)
    assert r["ok"], r
    return r["contract"], Path(r["contract_path"])


def _ctx(contract=None, contract_path=None, capture=None, asset_type="character"):
    c = V.ValidationContext(root=_TMP, run_ue=False)
    c.contract = contract; c.contract_path = contract_path
    c.capture_png = Path(capture) if capture else None; c.asset_type = asset_type
    return c


# ---------------------------------------------------------------------------- no-drift validator

def test_no_drift_clean_passes():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("c_clean", out)
    v = VR.v_intent_contract_no_drift(_ctx(contract, cp))
    assert v.passed and not v.hard_fail, v.detail


def test_no_drift_no_contract_is_na():
    v = VR.v_intent_contract_no_drift(_ctx(None))
    assert v.passed, v.detail        # project-wide mode: not applicable, never blocks the sweep


def test_no_drift_tampered_intent_hash_rejects():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("c_tamper", out)
    contract["goals"]["summary"] = "a DIFFERENT build entirely"   # rubric changed, intent_hash now stale
    v = VR.v_intent_contract_no_drift(_ctx(contract, cp))
    assert v.hard_fail, "a tampered scored rubric must hard-fail"


def test_no_drift_design_md_drift_rejects():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("c_drift", out)
    DESIGN_MD.write_text("# WANEFALL visual law v2 — CHANGED under the build\n", encoding="utf-8")
    try:
        v = VR.v_intent_contract_no_drift(_ctx(contract, cp))
        assert v.hard_fail, "DESIGN.md drift under the build must hard-fail"
    finally:
        DESIGN_MD.write_text("# WANEFALL visual law v1\ncarapace metallic 0.0\nweakpoint emissive 1.0\n", encoding="utf-8")


def test_no_drift_unanchored_rejects():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("c_anchor", out)
    contract["anchored"] = False; contract["anchor_entry_hash"] = None
    v = VR.v_intent_contract_no_drift(_ctx(contract, cp))
    assert v.hard_fail, "a contract never anchored in the ledger must hard-fail (anti-retrofit)"


def test_no_drift_swapped_on_disk_rejects():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("c_swap", out)
    disk = json.loads(cp.read_text("utf-8")); disk["intent_hash"] = "deadbeef"; cp.write_text(json.dumps(disk), "utf-8")
    v = VR.v_intent_contract_no_drift(_ctx(contract, cp))
    assert v.hard_fail, "on-disk contract swapped after authoring must hard-fail"


# ---------------------------------------------------------------------------- target conformance validator

def test_target_conformance_matching_passes():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("t_good", out)
    v = VR.v_intent_target_conformance(_ctx(contract, cp, capture=CAP_GOOD))
    assert v.passed, v.detail
    assert v.detail["target_similarity"] >= 0.85, v.detail


def test_target_conformance_wrong_asset_fails():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("t_wrong", out)
    v = VR.v_intent_target_conformance(_ctx(contract, cp, capture=CAP_WRONG))
    assert not v.passed, "a flawless render of the WRONG asset must FAIL target conformance"
    assert v.detail["target_similarity"] < 0.85, v.detail


# ---------------------------------------------------------------------------- motion escalation in _assemble

def _res(vid, domain, state, severity="warn", probe="static", score=1.0, detail=None, hard=False):
    return {"validator_id": vid, "domain": domain, "severity": severity, "probe_type": probe,
            "state": state, "score": score, "passed": state == "PASS", "hard_fail": hard,
            "issues": [], "evidence": {}, "detail": detail or {}, "regression_caught": "", "target": ""}


def test_motion_failure_escalates_to_blocker_when_contract_requires_motion():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("m_req", out)
    assert "motion" in (contract["validation_plan"]["required_capture_stages"])
    suite = V.ValidationSuite(_ctx(contract, cp, capture=CAP_GOOD), registry=[])
    results = [_res("anim_video_motion_live", "anim", "FAIL", severity="warn")]
    report = suite._assemble(results, None)
    assert report["motion_escalated"] is True, report
    assert results[0]["severity"] == "blocker", results[0]
    assert report["suite_verdict"] == "FAIL", report["suite_verdict"]


def test_motion_failure_stays_warn_without_motion_contract():
    # a contract whose required stages do NOT include motion leaves the motion validator a non-blocking WARN
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("m_noreq", out)
    contract["validation_plan"]["required_capture_stages"] = ["plan", "execute", "hero"]
    suite = V.ValidationSuite(_ctx(contract, cp, capture=CAP_GOOD), registry=[])
    results = [_res("anim_video_motion_live", "anim", "FAIL", severity="warn")]
    report = suite._assemble(results, None)
    assert report["motion_escalated"] is False, report
    assert results[0]["severity"] == "warn", results[0]
    assert report["suite_verdict"] == "PASS", report["suite_verdict"]


# ---------------------------------------------------------------------------- suite fuse (four domains -> one)

def test_suite_fuse_all_strong_meets_gate():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("f_strong", out)
    suite = V.ValidationSuite(_ctx(contract, cp, capture=CAP_GOOD), registry=[])
    results = [
        _res("rig_perception_ship_lighting", "rigged_skeletal_meshes", "PASS", probe="perception", score=0.98),
        _res("optics_character_semantic", "optics_semantic", "PASS", probe="perception", score=0.97),
        _res("design_md_lint", "design_md", "PASS", score=0.99),
        _res("intent_target_conformance", "intent_conformance", "PASS", probe="perception", score=0.95,
             detail={"target_similarity": 0.95}),
    ]
    report = suite._assemble(results, None)
    f = report["suite_fused"]
    assert f["meets_gate"] is True, f
    assert report["review_gate_met"] is True, report


def test_suite_fuse_missing_domain_blocks():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("f_missing", out)
    suite = V.ValidationSuite(_ctx(contract, cp, capture=CAP_GOOD), registry=[])
    # optics domain absent entirely -> fuse cannot certify (fail-closed)
    results = [
        _res("rig_perception_ship_lighting", "rigged_skeletal_meshes", "PASS", probe="perception", score=0.98),
        _res("design_md_lint", "design_md", "PASS", score=0.99),
        _res("intent_target_conformance", "intent_conformance", "PASS", probe="perception", score=0.95,
             detail={"target_similarity": 0.95}),
    ]
    report = suite._assemble(results, None)
    assert report["suite_fused"]["meets_gate"] is False, report["suite_fused"]
    assert report["review_gate_met"] is False, report


def test_suite_fuse_weak_domain_caps_confidence():
    out = Path(tempfile.mkdtemp(dir=_TMP)); contract, cp = _author("f_weak", out)
    suite = V.ValidationSuite(_ctx(contract, cp, capture=CAP_GOOD), registry=[])
    results = [
        _res("rig_perception_ship_lighting", "rigged_skeletal_meshes", "PASS", probe="perception", score=0.98),
        _res("optics_character_semantic", "optics_semantic", "PASS", probe="perception", score=0.40),  # weak
        _res("design_md_lint", "design_md", "PASS", score=0.99),
        _res("intent_target_conformance", "intent_conformance", "PASS", probe="perception", score=0.95,
             detail={"target_similarity": 0.95}),
    ]
    f = suite._assemble(results, None)["suite_fused"]
    assert f["meets_gate"] is False and f["confidence"] == 0.40, f
    assert f["binding_constraint"] == "domain:optics", f


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
