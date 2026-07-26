"""Proof for the SUITE-level rig deformation validator (v_rig_deformation) — #32 deformation QA extended into
the permanent 112-validator harness, same pattern as intent_conformance. Stdlib + numpy/Pillow.
Run:  python -m dimwit.tests.test_suite_rig_deform

It reads artifacts/pose_capture_result.json, so each test writes a temp result there and restores it.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.pipelines import validation_registry as VR
from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.validation import ROOT, ValidationContext

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_suiterig_"))
_RES = ROOT / "artifacts" / "pose_capture_result.json"
# live suite evidence — snapshot at import so tests can NEVER destroy it (they used to delete it)
_ORIG = _RES.read_bytes() if _RES.exists() else None
_TEAL, _BG = (80, 190, 190), (60, 62, 66)


def _humanoid(path, arms_up=False):
    im = Image.new("RGB", (240, 320), _BG); d = ImageDraw.Draw(im)
    d.ellipse([100, 24, 140, 64], fill=_TEAL); d.rectangle([95, 64, 145, 200], fill=_TEAL)
    ay = (30, 130) if arms_up else (70, 170)
    d.rectangle([70, ay[0], 100, ay[1]], fill=_TEAL); d.rectangle([140, ay[0], 170, ay[1]], fill=_TEAL)
    d.rectangle([98, 200, 118, 300], fill=_TEAL); d.rectangle([122, 200, 142, 300], fill=_TEAL)
    im.save(path); return str(path)


def _collapse(path):
    im = Image.new("RGB", (240, 320), _BG); ImageDraw.Draw(im).rectangle([116, 40, 128, 300], fill=_TEAL)
    im.save(path); return str(path)


BIND = _humanoid(_TMP / "bind.png")
GOOD = _humanoid(_TMP / "good.png", arms_up=True)
BAD = _collapse(_TMP / "collapse.png")
_CTX = ValidationContext(run_ue=False)


def _write_result(obj):
    _RES.parent.mkdir(parents=True, exist_ok=True)
    if obj is None:
        if _RES.exists():
            _RES.unlink()
    else:
        _RES.write_text(json.dumps(obj), encoding="utf-8")


def _restore():
    # leave the artifacts dir EXACTLY as we found it — the pose capture is live suite evidence
    if _ORIG is None:
        if _RES.exists():
            _RES.unlink()
    else:
        _RES.write_bytes(_ORIG)


def test_no_capture_blocks_fail_closed():
    # Z1a hardening: a motion-gated rig with NO deformation capture is UNPROVEN, never "n/a PASS"
    _write_result(None)
    try:
        try:
            VR.v_rig_deformation(_CTX)
        except BlockedError as exc:
            assert "pose_capture_result.json" in str(exc)
        else:
            raise AssertionError("missing pose capture must BLOCK, not pass vacuously")
    finally:
        _restore()


def test_clean_capture_passes():
    _write_result({"bind": BIND, "poses": {"bind": BIND, "idle": GOOD, "walk": GOOD, "run": BIND}})
    try:
        v = VR.v_rig_deformation(_CTX)
        assert v.passed, (v.issues, v.detail)
    finally:
        _restore()


def test_frozen_capture_hard_fails():
    # every pose identical to bind (the real Ekris failure) -> anti-frozen gate -> hard fail at the SUITE level
    _write_result({"bind": BIND, "poses": {"bind": BIND, "idle": BIND, "walk": BIND, "run": BIND}})
    try:
        v = VR.v_rig_deformation(_CTX)
        assert v.hard_fail and not v.passed, v.detail
        assert any("certifiable" in i or "FROZEN" in str(v.detail) for i in v.issues), v.issues
    finally:
        _restore()


def test_collapsing_capture_fails():
    _write_result({"bind": BIND, "poses": {"bind": BIND, "idle": GOOD, "walk": GOOD, "twist": BAD}})
    try:
        v = VR.v_rig_deformation(_CTX)
        assert not v.passed, "a collapsing pose must fail the suite deformation gate"
    finally:
        _restore()


def test_incomplete_capture_hard_fails():
    _write_result({"bind": BIND, "poses": {"bind": BIND, "idle": GOOD}})   # <3 stress poses
    try:
        v = VR.v_rig_deformation(_CTX)
        assert v.hard_fail and not v.passed, v.detail
    finally:
        _restore()


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
    _restore()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
