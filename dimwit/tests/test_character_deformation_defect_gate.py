from __future__ import annotations

import json
import sys

from dimwit.pipelines import validation_registry as VR
from dimwit.pipelines.validation import ValidationContext


_DEFECT = VR.VAL_ART / "character_deformation_review.json"


def test_user_reported_character_deformation_hard_fails_before_llm():
    original = _DEFECT.read_text(encoding="utf-8") if _DEFECT.exists() else None
    try:
        _DEFECT.parent.mkdir(parents=True, exist_ok=True)
        _DEFECT.write_text(json.dumps({
            "state": "USER_REPORTED_DEFECT",
            "subject": str(VR.VAL_ART / "char_still_focused.png"),
            "issues": ["right_arm_deformed"],
            "reported_by": "operator",
        }), encoding="utf-8")

        verdict = VR.v_optics_character_semantic(ValidationContext(run_ue=False))

        assert verdict.hard_fail is True, verdict
        assert verdict.passed is False, verdict
        assert any("right_arm_deformed" in issue for issue in verdict.issues), verdict.issues
    finally:
        if original is None:
            if _DEFECT.exists():
                _DEFECT.unlink()
        else:
            _DEFECT.write_text(original, encoding="utf-8")


def test_quarantined_character_still_is_not_selected_as_active_optics_subject():
    meta_path = VR.VAL_ART / "char_still_metadata.json"
    original = meta_path.read_text(encoding="utf-8") if meta_path.exists() else None
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({
            "subject_type": "character_optics_candidate",
            "subject_character": "ekris",
            "asset_name": "SM_Char_02_ekris",
            "source_stem": "hi3d_02_ekris",
            "focused_frame": str(VR.VAL_ART / "char_still_focused.png"),
        }), encoding="utf-8")

        selected = VR._best_optics_subject()

        assert selected != str(VR.VAL_ART / "char_still_focused.png")
    finally:
        if original is None:
            if meta_path.exists():
                meta_path.unlink()
        else:
            meta_path.write_text(original, encoding="utf-8")


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
