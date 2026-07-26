from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.pipelines import validation_registry as VR


def _write_angle(path: Path, angle: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (240, 320), (18, 20, 24))
    d = ImageDraw.Draw(im)
    if angle == "front":
        d.rectangle([95, 58, 145, 210], fill=(190, 190, 190))
        d.ellipse([100, 25, 140, 65], fill=(210, 210, 210))
        d.rectangle([68, 70, 95, 190], fill=(180, 180, 180))
        d.rectangle([145, 70, 172, 190], fill=(180, 180, 180))
        d.rectangle([100, 210, 118, 300], fill=(170, 170, 170))
        d.rectangle([122, 210, 140, 300], fill=(170, 170, 170))
    elif angle == "side":
        d.rectangle([105, 58, 142, 210], fill=(190, 190, 190))
        d.ellipse([103, 25, 143, 65], fill=(210, 210, 210))
        d.rectangle([75, 72, 104, 188], fill=(180, 180, 180))
        d.rectangle([143, 86, 158, 168], fill=(150, 150, 150))
        d.rectangle([106, 210, 124, 300], fill=(170, 170, 170))
        d.rectangle([129, 210, 148, 298], fill=(165, 165, 165))
    elif angle == "threequarter":
        d.rectangle([92, 58, 144, 210], fill=(190, 190, 190))
        d.ellipse([98, 25, 138, 65], fill=(210, 210, 210))
        d.rectangle([58, 72, 89, 188], fill=(180, 180, 180))
        d.rectangle([140, 78, 160, 176], fill=(170, 170, 170))
        d.rectangle([98, 210, 118, 300], fill=(170, 170, 170))
        d.rectangle([126, 210, 150, 298], fill=(165, 165, 165))
    im.save(path)


def test_multiview_symmetry_requires_all_angles():
    root = Path(tempfile.mkdtemp(prefix="dimwit_multiview_missing_"))
    _write_angle(root / "artifacts" / "01_vorlax_textured" / "mview_front.png", "front")

    audit = VR._character_multiview_symmetry_audit(root, ["SM_Char_01_Vorlax"])

    assert audit["passed"] is False, audit
    assert any("missing side" in issue for issue in audit["issues"]), audit["issues"]
    assert any("missing threequarter" in issue for issue in audit["issues"]), audit["issues"]


def test_multiview_symmetry_passes_front_side_threequarter_evidence():
    root = Path(tempfile.mkdtemp(prefix="dimwit_multiview_ok_"))
    base = root / "artifacts" / "01_vorlax_textured"
    for angle in ("front", "side", "threequarter"):
        _write_angle(base / f"mview_{angle}.png", angle)

    audit = VR._character_multiview_symmetry_audit(root, ["SM_Char_01_Vorlax"])

    assert audit["passed"] is True, audit
    assert audit["characters_checked"] == 1, audit
    assert set(audit["per_character"]["SM_Char_01_Vorlax"]["angles"]) == {"front", "side", "threequarter"}


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
