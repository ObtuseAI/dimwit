"""Proof that the hardened LOOP is deformation-aware (#32 gated through the loop): a rigged character with a
clean, identity-matching hero shot still must NOT promote if a stress pose COLLAPSES. The deformation signal
feeds the same weakest-link fused gate. Stdlib + numpy/Pillow.  Run: python -m dimwit.tests.test_loop_deform
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.build_loop import build_one
from dimwit.core import AssetTask, Lifecycle
from dimwit.engine import DimwitLedger

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_loopdeform_"))


def _compliant(path):
    im = Image.new("RGB", (360, 360), (70, 70, 74)); d = ImageDraw.Draw(im)
    d.ellipse([150, 40, 210, 100], fill=(51, 204, 204)); d.rectangle([130, 100, 230, 250], fill=(51, 204, 204))
    d.rectangle([135, 250, 175, 340], fill=(45, 180, 180)); d.rectangle([185, 250, 225, 340], fill=(45, 180, 180))
    d.rectangle([165, 140, 205, 190], fill=(230, 120, 30)); im.save(path); return str(path)


def _pose(path, arms_up=False):
    im = Image.new("RGB", (240, 320), (60, 62, 66)); d = ImageDraw.Draw(im)
    d.ellipse([100, 24, 140, 64], fill=(80, 190, 190)); d.rectangle([95, 64, 145, 200], fill=(80, 190, 190))
    ay = (30, 130) if arms_up else (70, 170)
    d.rectangle([70, ay[0], 100, ay[1]], fill=(80, 190, 190)); d.rectangle([140, ay[0], 170, ay[1]], fill=(80, 190, 190))
    d.rectangle([98, 200, 118, 300], fill=(80, 190, 190)); d.rectangle([122, 200, 142, 300], fill=(80, 190, 190))
    im.save(path); return str(path)


def _collapse(path):
    im = Image.new("RGB", (240, 320), (60, 62, 66)); ImageDraw.Draw(im).rectangle([116, 40, 128, 300], fill=(80, 190, 190))
    im.save(path); return str(path)


REF = _compliant(_TMP / "ref.png")
CAP = _compliant(_TMP / "cap.png")
P_BIND = _pose(_TMP / "p_bind.png")
P_GOOD = _pose(_TMP / "p_good.png", arms_up=True)
P_BAD = _collapse(_TMP / "p_bad.png")

_SPEC = {"traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
         "collision_proxy": "convex", "scale_cm": 270, "material_slots": ["m"], "mesh_ref": "SM_x",
         "tri_estimate": 120000, "hit_destroy_clarity": 0.97, "camera_readability": 0.97, "gameplay_readability": 0.97}
_PROV = {"license_class": "owned_reference", "reference_license": "owned", "source_prompt": "p"}
_AUTHK = {"provenance": dict(_PROV)}


def _evidence(deform):
    ev = {"hero_contact_sheet": CAP, "player_camera_contact_sheet": CAP, "provenance": dict(_PROV)}
    if deform is not None:
        ev["deformation_capture"] = deform
    return ev


def _ws():
    d = Path(tempfile.mkdtemp(dir=_TMP)); (d / "assets").mkdir(); return d


def test_clean_deformation_still_promotes():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    cap = {"bind": P_BIND, "poses": {"idle": P_GOOD, "walk": P_GOOD, "run": P_BIND}}
    out = build_one(AssetTask(asset_id="rig_good", asset_type="character"), dict(_SPEC), _evidence(cap), led,
                    reference=REF, assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["state"] == Lifecycle.PROMOTED_TO_REVIEW, (out["state"], out["fused"])


def test_collapsing_pose_blocks_promotion_despite_clean_hero():
    ws = _ws(); led = DimwitLedger(ws / "ledger.jsonl")
    cap = {"bind": P_BIND, "poses": {"idle": P_GOOD, "twist": P_BAD}}   # one pose collapses
    out = build_one(AssetTask(asset_id="rig_bad", asset_type="character"), dict(_SPEC), _evidence(cap), led,
                    reference=REF, assets_root=ws / "assets", review_root=ws, author_kwargs=_AUTHK)
    assert out["promoted"] is False, "a collapsing stress pose must block promotion even with a clean hero shot"
    # the deformation signal lives in the perception domain, so a collapse caps the perception weakest-link
    # below the gate even though silhouette/tp-camera/identity are all perfect (1.0 / target 1.0)
    f = out["fused"]
    assert f["by_domain"].get("perception", 1.0) < 0.85, ("deformation must cap the perception domain", f["by_domain"])
    assert f["by_load_bearing_dim"]["silhouette_readability"] == 1.0 and f["target_similarity"] >= 0.99, \
        ("identity/silhouette are perfect — proving it's deformation that blocked it", f)


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
