"""Proof tests for the target identity/structure metric (perception.compare_to_target +
optics.target_confidence). Stdlib + numpy/Pillow. Run:  python -m dimwit.tests.test_target_match

The headline property: a flawlessly-rendered WRONG asset (right palette, clean render, but wrong shape)
must score BELOW the character identity floor (0.85). Identity is structure-first; palette can't fake it.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from dimwit import perception
from dimwit.pipelines.validation import resolve_asset_type_floors

TARGET_FLOOR = resolve_asset_type_floors("character")["target_match_floor"]   # 0.85
_TMP = Path(tempfile.mkdtemp(prefix="dimwit_target_"))


def _bg(size=(300, 420), color=(40, 44, 50)):
    return Image.new("RGB", size, color)


def _humanoid(path, body=(150, 160, 170), accent=(220, 120, 40)):
    """A simple readable humanoid silhouette: head + torso + two legs, with an orange weak-point accent."""
    im = _bg()
    d = ImageDraw.Draw(im)
    d.ellipse([130, 40, 175, 90], fill=body)            # head
    d.rectangle([120, 90, 185, 230], fill=body)         # torso
    d.rectangle([122, 230, 148, 360], fill=body)        # left leg
    d.rectangle([158, 230, 184, 360], fill=body)        # right leg
    d.rectangle([135, 120, 170, 150], fill=accent)      # weak-point
    im.save(path)
    return str(path)


def _wrong_blob(path, color=(150, 160, 170), accent=(220, 120, 40)):
    """Same palette + same accent, but a single round blob — the WRONG shape. The recolor/quality is fine;
    only identity is wrong, which is exactly the failure the metric must catch."""
    im = _bg()
    d = ImageDraw.Draw(im)
    d.ellipse([90, 120, 210, 300], fill=color)          # big round blob
    d.ellipse([130, 180, 170, 220], fill=accent)        # same accent color, wrong placement
    im.save(path)
    return str(path)


REF = _humanoid(_TMP / "ref_humanoid.png")
SAME = _humanoid(_TMP / "render_humanoid.png")          # a faithful re-render of the same shape
BLOB = _wrong_blob(_TMP / "render_blob.png")            # wrong shape, right palette


def test_self_match_is_high():
    r = perception.compare_to_target(REF, REF)
    assert r["ok"] and r["target_similarity"] >= 0.95, r


def test_faithful_render_matches():
    r = perception.compare_to_target(SAME, REF)
    assert r["ok"], r
    assert r["target_similarity"] >= TARGET_FLOOR, (r, "a faithful re-render should clear the identity floor")


def test_wrong_blob_below_floor():
    r = perception.compare_to_target(BLOB, REF)
    assert r["ok"], r
    assert r["target_similarity"] < TARGET_FLOOR, (r, "wrong-shape blob must fall below the identity floor")
    # structure, not palette, is what tanks it: silhouette IoU should be poor
    assert r["silhouette_iou"] < 0.7, r


def test_missing_reference_blocks():
    r = perception.compare_to_target(REF, _TMP / "does_not_exist.png")
    assert r["ok"] is False and r["blocked"] is True and r["target_similarity"] is None, r


def test_missing_capture_blocks():
    r = perception.compare_to_target(_TMP / "nope.png", REF)
    assert r["ok"] is False and r["blocked"] is True, r


def test_target_confidence_no_reference_blocks():
    # optics.target_confidence is fail-closed without a reference, regardless of LLM availability
    from dimwit import optics
    r = optics.target_confidence(REF, None, require_semantic=True)
    assert r["blocked"] is True and r["target_confidence"] is None, r


def test_target_confidence_pixel_only_when_semantic_not_required():
    from dimwit import optics
    # require_semantic=False => identity certified on the pixel structural match alone (no LLM needed)
    r = optics.target_confidence(SAME, REF, require_semantic=False)
    # whether LLM is configured or not, with require_semantic False we get a pixel-grounded number
    assert r["target_confidence"] is not None, r
    assert r["target_confidence"] >= TARGET_FLOOR, r
    r2 = optics.target_confidence(BLOB, REF, require_semantic=False)
    assert r2["target_confidence"] < TARGET_FLOOR, r2


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
