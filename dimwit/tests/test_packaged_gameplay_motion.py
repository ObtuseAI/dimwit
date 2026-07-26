"""Regression tests for packaged gameplay motion proof (bundle: PACKAGED_GAMEPLAY_MOTION_PROOF_V1).

Audit finding 2026-07-01: the packaged cook contained only the command-surface menu map and every
runtime frame burst was byte-identical stills - zero evidence of PLAY existed anywhere. Pinned
behavior: (1) the packaged cook includes gameplay maps; (2) packaged validation requires a
gameplay phase - deploy input, map load, and a motion-delta gate that static frames can never
satisfy; (3) desktop hands can guard against the PACKAGED game process, not just UnrealEditor.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.desktop_hands import VK, DesktopHands
from dimwit.pipelines.packaged_build_validation import (
    PackagedBuildValidationPipeline,
    frame_motion_delta,
    validate_packaged_build_result,
)

TMP = Path(tempfile.mkdtemp(prefix="dimwit_packaged_gameplay_"))


def _frame(path: Path, box_x: int) -> Path:
    image = Image.new("RGB", (320, 200), (14, 18, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle([box_x, 60, box_x + 70, 140], fill=(34, 190, 190))
    image.save(path)
    return path


def test_frame_motion_delta_rejects_static_frames_and_passes_motion():
    static = [_frame(TMP / f"static_{i}.png", 100) for i in range(3)]
    verdict = frame_motion_delta(static, threshold=0.01)
    assert verdict["passed"] is False, "byte-identical frames must never satisfy the motion gate"
    assert any("motion" in issue.lower() or "delta" in issue.lower() for issue in verdict["issues"])

    moving = [_frame(TMP / f"move_{i}.png", 60 + i * 60) for i in range(3)]
    verdict = frame_motion_delta(moving, threshold=0.01)
    assert verdict["passed"] is True, f"visible motion must pass: {verdict}"
    assert verdict["max_mean_delta"] > 0.01

    verdict = frame_motion_delta([static[0]], threshold=0.01)
    assert verdict["passed"] is False, "a single frame proves nothing"


def test_plan_cooks_gameplay_maps_into_the_package():
    pipeline = PackagedBuildValidationPipeline()
    plan = pipeline.plan({"asset_id": "wanefall_win64_development"})
    command = " ".join(str(part) for part in plan["uat_command"])
    map_arg = next(part for part in plan["uat_command"] if str(part).startswith("-map="))
    assert "Wanefall_ModeShell_Prototype_01" in map_arg, "front door stays first in the cook"
    assert "Wanefall_Arena4v4_Prototype_01" in map_arg, "flagship gameplay map must be cooked"
    assert "Wanefall_WaneTrialJailCell_01" in map_arg, "wane trial map must be cooked"
    assert plan["gameplay"]["enabled"] is True
    assert plan["gameplay"]["map_token"] == "Wanefall_Arena4v4_Prototype_01"


def _base_checks() -> dict:
    return {
        "package_manifest": {"passed": True, "issues": []},
        "executable_hash": {"passed": True, "issues": []},
        "window_found": {"passed": True, "issues": []},
        "still_nonblank": {"passed": True, "issues": []},
        "frame_burst_nonblank": {"passed": True, "issues": []},
        "packaged_log_scan": {"passed": True, "issues": []},
        "process_identity": {"passed": True, "issues": [], "captured_pid": 1, "expected_pid": 1},
    }


def _write_result(name: str, checks: dict) -> Path:
    path = TMP / name
    path.write_text(json.dumps({
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "packaged_build",
        "checks": checks,
    }, indent=2), encoding="utf-8")
    return path


def test_validate_requires_packaged_gameplay_evidence():
    result = validate_packaged_build_result(_write_result("no_gameplay.json", _base_checks()), max_age_seconds=60)
    assert result["suite_pass"] is False, "menu-only packaged evidence must no longer pass"
    assert result["checks"]["gameplay_map_loaded"]["passed"] is False
    assert result["checks"]["gameplay_motion_delta"]["passed"] is False

    checks = _base_checks()
    checks["gameplay_map_loaded"] = {"passed": True, "issues": [], "map_token": "Wanefall_Arena4v4_Prototype_01"}
    checks["gameplay_motion_delta"] = {"passed": True, "issues": [], "max_mean_delta": 0.09, "threshold": 0.02}
    checks["gameplay_process_identity"] = {"passed": True, "issues": []}
    result = validate_packaged_build_result(_write_result("with_gameplay.json", checks), max_age_seconds=60)
    assert result["suite_pass"] is True, f"gameplay-proven package must pass: " \
        f"{[k for k, v in result['checks'].items() if not v.get('passed')]}"


def test_desktop_hands_guards_against_configured_target_process():
    hands = DesktopHands(title="WanefallGreybox", proc="WanefallGreybox")
    ok_one = hands.single_target(names=["WanefallGreybox.exe", "chrome.exe", "explorer.exe"])
    assert ok_one["ok"] is True and ok_one["count"] == 1

    none = hands.single_target(names=["chrome.exe"])
    assert none["ok"] is False and none["count"] == 0

    editor_hands = DesktopHands()   # default editor target keeps its semantics
    two = editor_hands.single_target(names=["UnrealEditor.exe", "UnrealEditor.exe"])
    assert two["ok"] is False and two["count"] == 2


def test_validation_registry_contains_gameplay_motion_gate():
    from dimwit.pipelines.validation_registry import build_registry
    by_id = {validator.id: validator for validator in build_registry()}
    gate = by_id.get("packaged_build_gameplay_motion_proven")
    assert gate is not None, "packaged_build domain must gate on gameplay motion proof"
    assert gate.domain == "packaged_build"
    assert gate.severity.value == "blocker"


def test_movement_keys_exist_in_vk_map():
    for key in ("w", "a", "s", "d", "enter"):
        assert key in VK and VK[key], f"missing VK mapping for {key!r}"


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
