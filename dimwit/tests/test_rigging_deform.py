"""Proof that RiggingPipeline.qa is NO LONGER structural-only (#32). A rig with perfect weights/influences/
bones must still FAIL if it deforms badly, and is fail-closed when deformation was never captured.
Stdlib + numpy/Pillow.  Run:  python -m dimwit.tests.test_rigging_deform
"""
from __future__ import annotations

import sys
import tempfile
import json
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.core import evaluate_provenance
from dimwit.pipelines.base import Artifact
from dimwit.pipelines.rigging import RiggingPipeline

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_rigqa_"))
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

_STRUCT = {"mannequin_fbx_exists": True,
           "stages": {"blender_rig": {"weight_coverage": 1.0, "max_influences": 4, "bones": 60},
                      "import_skeletal": {"ok": True}}}


def _artifact(deform_capture):
    data = {**_STRUCT}
    data["stages"] = {**_STRUCT["stages"]}
    if deform_capture is not None:
        data["stages"]["deformation_capture"] = deform_capture
    return Artifact(asset_id="ekris", kind="skeletal_mesh", data=data, provenance={"source": "x", "license": "y"})


def test_clean_rig_passes_structural_and_deformation():
    cap = {"bind": BIND, "poses": {"idle": GOOD, "walk": GOOD, "run": BIND}}
    v = RiggingPipeline().qa(_artifact(cap), {"asset": "SM_Char_02_ekris", "key": "ekris"})
    assert v.passed, (v.issues, v.detail.get("deformation"))
    assert v.detail["deformation"]["passed"] is True


def test_structural_perfect_but_bad_deformation_fails():
    # weights/influences/bones all perfect, but a pose COLLAPSES -> qa must FAIL (the whole point of #32)
    cap = {"bind": BIND, "poses": {"idle": GOOD, "walk": GOOD, "twist": BAD}}
    v = RiggingPipeline().qa(_artifact(cap), {"asset": "SM_Char_02_ekris", "key": "ekris"})
    assert v.passed is False, "structurally perfect rig with a collapsing pose must not pass"
    assert v.detail["checks"]["deformation_validated"] is False
    assert any("deformation FAIL" in i for i in v.issues), v.issues
    # and structural checks DID pass — proving it's the deformation layer that caught it
    assert all(v.detail["structural"].values()), v.detail["structural"]


def test_no_deformation_capture_is_fail_closed():
    v = RiggingPipeline().qa(_artifact(None), {"asset": "SM_Char_02_ekris", "key": "ekris"})
    assert v.passed is False, "a rig with no deformation captures must not be certified (fail-closed)"
    assert v.detail["deformation"]["validated"] is False
    assert any("deformation NOT validated" in i for i in v.issues), v.issues


def test_too_few_poses_is_fail_closed():
    cap = {"bind": BIND, "poses": {"idle": GOOD}}      # only 1 stress pose (<3)
    v = RiggingPipeline().qa(_artifact(cap), {"asset": "SM_Char_02_ekris", "key": "ekris"})
    assert v.passed is False and v.detail["deformation"]["validated"] is False, v.detail["deformation"]


def test_active_handcrafted_rig_artifact_records_promotable_provenance():
    root = Path(__file__).resolve().parents[2]
    rig_json = root / "artifacts" / "rig" / "SM_Char_01_vorlax_handcrafted_rig.fbx.rig.json"
    data = json.loads(rig_json.read_text(encoding="utf-8"))

    provenance = data.get("provenance")
    assert isinstance(provenance, dict), "active handcrafted rig JSON must record provenance"
    verdict = evaluate_provenance(provenance)
    assert verdict["promotable"], verdict


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
