"""Production-readiness proof for the single hardened-loop entry point (build_loop.build_one). Unlike the
other suites (which inject perception by hand), THIS one drives REAL perception over real PNGs end-to-end,
so it proves the wired flow can actually:
  * PROMOTE a genuinely WANEFALL-compliant capture that matches its declared reference (the success path —
    proving the 0.95 floor is achievable, not a brick wall);
  * BLOCK a high-quality render of the WRONG asset (identity gate, real pixels);
  * stay fail-closed with declared-only data (no captures -> NEEDS_RECURSION, never promoted);
  * REFUSE to even run when intent can't be declared (strict type, no reference);
  * author the contract once, then reuse it (idempotent, anti-retrofit safe on recursion).

Run:  python -m dimwit.tests.test_build_loop
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.build_loop import build_one, ensure_intent_contract
from dimwit.core import AssetTask, Lifecycle
from dimwit.engine import DimwitLedger

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_buildloop_"))


def _compliant(path):
    """A WANEFALL-compliant capture: dark-ish mid bg, large TEAL readable body, ORANGE weak-point, clean
    silhouette. Real perception scores the load-bearing dims (silhouette + tp-camera) at the top of the range."""
    im = Image.new("RGB", (360, 360), (70, 70, 74)); d = ImageDraw.Draw(im)
    d.ellipse([150, 40, 210, 100], fill=(51, 204, 204))      # head
    d.rectangle([130, 100, 230, 250], fill=(51, 204, 204))   # torso
    d.rectangle([135, 250, 175, 340], fill=(45, 180, 180))   # leg
    d.rectangle([185, 250, 225, 340], fill=(45, 180, 180))   # leg
    d.rectangle([165, 140, 205, 190], fill=(230, 120, 30))   # orange weak-point
    im.save(path); return str(path)


def _wrong_shape(path):
    """Same WANEFALL palette + readability (high contrast teal + orange), but a single round BLOB — the wrong
    identity. Perception is happy; the capture-vs-reference identity match is what must reject it."""
    im = Image.new("RGB", (360, 360), (70, 70, 74)); d = ImageDraw.Draw(im)
    d.ellipse([80, 90, 280, 300], fill=(51, 204, 204))       # big round teal blob
    d.ellipse([160, 170, 200, 210], fill=(230, 120, 30))     # orange dot
    im.save(path); return str(path)


REF = _compliant(_TMP / "ref.png")
CAP_FAITHFUL = _compliant(_TMP / "cap_faithful.png")
CAP_WRONG = _wrong_shape(_TMP / "cap_wrong.png")

_SPEC = {"traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
         "collision_proxy": "convex_decomp", "scale_cm": 270, "material_slots": ["M_Body", "M_Core"],
         "mesh_ref": "SM_Char_test", "tri_estimate": 120000, "hit_destroy_clarity": 0.97,
         "camera_readability": 0.97, "gameplay_readability": 0.97}
_PROV = {"license_class": "owned_reference", "reference_license": "owned", "source_prompt": "concept sheet"}
_AUTHK = {"provenance": dict(_PROV)}


def _task(asset_id):
    return AssetTask(asset_id=asset_id, asset_type="character", source_kind="design_need")


def _ws():
    d = Path(tempfile.mkdtemp(dir=_TMP)); (d / "assets").mkdir(); return d


def test_build_one_promotes_compliant_matching_capture():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    ev = {"hero_contact_sheet": CAP_FAITHFUL, "player_camera_contact_sheet": CAP_FAITHFUL, "provenance": dict(_PROV)}
    out = build_one(_task("char_good"), dict(_SPEC), ev, led, run_id="r", reference=REF,
                    assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["state"] == Lifecycle.PROMOTED_TO_REVIEW, (out["state"], out["fused"])
    assert out["promoted"] is True and out["fused"]["meets_gate"] is True, out["fused"]
    assert out["fused"]["target_similarity"] >= 0.85, out["fused"]
    # the review package carries the intent-vs-actual diff and says it MET the intent
    man = json.loads(Path(out["review_package"]["manifest"]).read_text("utf-8"))
    assert man["intent_vs_actual"]["actual_meets_gate"] is True, man["intent_vs_actual"]


def test_build_one_blocks_wrong_identity_capture():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    ev = {"hero_contact_sheet": CAP_WRONG, "player_camera_contact_sheet": CAP_WRONG, "provenance": dict(_PROV)}
    out = build_one(_task("char_wrong"), dict(_SPEC), ev, led, run_id="r", reference=REF,
                    assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["promoted"] is False, "a high-quality render of the WRONG shape must not promote"
    assert out["fused"]["target_similarity"] is not None and out["fused"]["target_similarity"] < 0.85, out["fused"]


def test_build_one_fail_closed_declared_only():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    ev = {"provenance": dict(_PROV)}      # NO captures
    out = build_one(_task("char_declonly"), dict(_SPEC), ev, led, run_id="r", reference=REF,
                    assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["promoted"] is False and out["state"] == Lifecycle.NEEDS_RECURSION, out["state"]
    assert out["fused"]["blocked"] is True, out["fused"]


def test_build_one_refuses_without_reference():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    ev = {"hero_contact_sheet": CAP_FAITHFUL, "player_camera_contact_sheet": CAP_FAITHFUL, "provenance": dict(_PROV)}
    out = build_one(_task("char_noref"), dict(_SPEC), ev, led, run_id="r", reference=None,  # strict type, no ref
                    assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["state"] == Lifecycle.BLOCKED and out["report"] is None, "must refuse to run without a declared target"
    assert out["contract"] is None, out


def test_build_one_idempotent_contract_reused():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    ev = {"hero_contact_sheet": CAP_FAITHFUL, "player_camera_contact_sheet": CAP_FAITHFUL, "provenance": dict(_PROV)}
    a = build_one(_task("char_idem"), dict(_SPEC), ev, led, run_id="r1", reference=REF,
                  assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert a["state"] == Lifecycle.PROMOTED_TO_REVIEW
    # second run: contract already on disk -> loaded, not re-authored (and not anti-retrofit-blocked)
    c2, p2, status = ensure_intent_contract("char_idem", "character", assets_root=ws / "assets", ledger=led)
    assert status == "loaded" and c2["intent_hash"] == a["contract"]["intent_hash"], status


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
