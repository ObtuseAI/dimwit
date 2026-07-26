from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.real_game_validation import (
    RealGameValidationPipeline,
    analyze_capture,
    check_result_fresh,
    detect_placeholder_geometry,
    scan_log_text,
    validate_real_game_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_realgame_"))


def _solid(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (160, 100), color).save(path)
    return path


def _contrast(path: Path) -> Path:
    image = Image.new("RGB", (160, 100), (20, 22, 25))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 20, 110, 80], fill=(51, 204, 204))
    draw.rectangle([72, 40, 88, 56], fill=(240, 120, 25))
    image.save(path)
    return path


def _grey_blockout(path: Path) -> Path:
    image = Image.new("RGB", (240, 140), (30, 36, 42))
    draw = ImageDraw.Draw(image)
    draw.rectangle([15, 90, 225, 136], fill=(92, 88, 82))
    draw.rectangle([45, 25, 105, 72], fill=(50, 50, 48))
    draw.rectangle([135, 18, 205, 66], fill=(55, 55, 53))
    draw.rectangle([60, 72, 83, 112], fill=(48, 47, 45))
    draw.rectangle([160, 66, 188, 118], fill=(47, 46, 44))
    draw.line([0, 0, 239, 139], fill=(120, 180, 190), width=2)
    image.save(path)
    return path


def test_blank_capture_is_rejected():
    result = analyze_capture(_solid(TMP / "blank.png", (255, 255, 255)))
    assert result["passed"] is False
    assert "contrast" in "; ".join(result["issues"])


def test_high_contrast_capture_passes():
    result = analyze_capture(_contrast(TMP / "contrast.png"))
    assert result["passed"] is True
    assert result["metrics"]["contrast"] >= 0.05
    assert result["metrics"]["mean_luminance"] >= 0.05
    assert detect_placeholder_geometry(result)["passed"] is True


def test_flat_grey_blockout_geometry_is_rejected():
    result = analyze_capture(_grey_blockout(TMP / "grey_blockout.png"))
    placeholder = detect_placeholder_geometry(result)
    assert placeholder["passed"] is False
    assert placeholder["flat_midgray_patch_fraction"] >= 0.03
    assert "flat mid-gray" in "; ".join(placeholder["issues"])


def test_log_scan_counts_fatal_error_lines():
    scan = scan_log_text("LogTemp: Display: ok\nFatal error: boom\nError: missing asset\n")
    assert scan["fatal_count"] == 1
    assert scan["error_count"] == 1
    assert scan["passed"] is False


def test_log_scan_rejects_skylight_realtime_capture_visual_warning():
    # churn-aware contract: the zero-tolerance "requires at least a SkyAtmosphere" line fails the
    # scan on its own; a SINGLE "real-time capture change" churn line is normal map-load init and
    # does not count (only repetition does — see test below).
    scan = scan_log_text(
        "LogRenderer: Forcing update for all mesh draw commands: SkyLight real-time capture change\n"
        "A sky light with real-time capture enabled is in the scene. It requires at least a SkyAtmosphere component.\n"
    )
    assert scan["passed"] is False
    assert scan["fatal_count"] == 0
    assert scan["error_count"] == 0
    assert scan["visual_warning_count"] == 1
    assert "skyatmosphere" in "; ".join(scan["visual_warning_lines"]).lower()


def test_log_scan_single_skylight_churn_line_is_benign_but_repetition_fails():
    churn = "LogRenderer: Forcing update for all mesh draw commands: SkyLight real-time capture change\n"
    assert scan_log_text(churn)["passed"] is True
    repeated = scan_log_text(churn * 2)
    assert repeated["passed"] is False
    assert repeated["visual_warning_count"] >= 1


def test_fresh_result_passes_and_stale_blocks():
    fresh = {"captured_at": time.time(), "suite_pass": True, "checks": {"still_nonblank": {"passed": True}}}
    assert check_result_fresh(fresh, max_age_seconds=60)["passed"] is True
    stale = {"captured_at": time.time() - 7200, "suite_pass": True, "checks": {}}
    assert check_result_fresh(stale, max_age_seconds=60)["passed"] is False


def test_validate_real_game_result_blocks_missing_file():
    try:
        validate_real_game_result(TMP / "missing.json", max_age_seconds=60)
    except BlockedError as exc:
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("missing result must block")


def test_validate_real_game_result_passes_complete_file():
    path = TMP / "result.json"
    path.write_text(json.dumps({
        "captured_at": time.time(),
        "suite_pass": True,
        "checks": {
            "window_found": {"passed": True},
            "still_nonblank": {"passed": True},
            "log_scan": {"passed": True, "fatal_count": 0, "error_count": 0},
        },
    }), encoding="utf-8")
    result = validate_real_game_result(path, max_age_seconds=60)
    assert result["suite_pass"] is True


def test_pipeline_plan_resolves_attach_only_runtime_config():
    pipeline = RealGameValidationPipeline()
    plan = pipeline.plan({
        "asset_id": "wanefall_default_lobby",
        "attach_only": True,
        "max_wait_seconds": 2,
        "capture_seconds": 1,
        "capture_fps": 2,
        "settle_seconds": 3,
    })
    assert plan["asset_id"] == "wanefall_default_lobby"
    assert plan["attach_only"] is True
    assert plan["max_wait_seconds"] == 2
    assert plan["capture_seconds"] == 1.0
    assert plan["capture_fps"] == 2.0
    assert plan["settle_seconds"] == 3.0
    assert plan["result_path"].name == "real_game_validation_result.json"


def test_pipeline_default_map_uses_command_shell_not_lobby_or_hold():
    pipeline = RealGameValidationPipeline()
    plan = pipeline.plan({"asset_id": "wanefall_default_command"})

    assert "Wanefall_ModeShell_Prototype_01" in plan["map_url"]
    assert "Wanefall_Lobby" not in plan["map_url"]
    assert "Wanefall_TheHold" not in plan["map_url"]


def test_modeshell_lighting_repair_does_not_enable_realtime_skylight_capture():
    script = Path("scripts/ue/ue_modeshell_lighting_repair.py").read_text(encoding="utf-8")
    assert 'set_editor_property("real_time_capture", True)' not in script
    assert "disabled_realtime_capture" in script


def test_modeshell_lighting_repair_sets_lobby_world_game_mode():
    script = Path("scripts/ue/ue_modeshell_lighting_repair.py").read_text(encoding="utf-8")
    assert "/Script/WanefallGreybox.WanefallLobbyGameMode" in script
    assert 'set_editor_property("default_game_mode"' in script
    assert "world_game_mode" in script


def test_pipeline_promotes_passing_stream_frame_over_black_still():
    pipeline = RealGameValidationPipeline()
    still = _solid(TMP / "black_still.png", (0, 0, 0))
    frame = _contrast(TMP / "good_stream_frame.png")
    still_analysis = analyze_capture(still)
    promoted = pipeline._promote_still_from_frames(still, still_analysis, [frame])

    assert promoted["passed"] is True
    assert promoted["promoted_from_frame"] == str(frame)
    assert analyze_capture(still)["passed"] is True
    assert detect_placeholder_geometry(promoted)["passed"] is True


def test_pipeline_does_not_promote_placeholder_dominated_stream_frame():
    pipeline = RealGameValidationPipeline()
    still = _solid(TMP / "black_still_placeholder_guard.png", (0, 0, 0))
    frame = _grey_blockout(TMP / "grey_stream_frame.png")
    still_analysis = analyze_capture(still)
    promoted = pipeline._promote_still_from_frames(still, still_analysis, [frame])

    assert promoted["passed"] is False
    assert "promoted_from_frame" not in promoted


def test_validation_registry_contains_real_game_runtime_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "real_game_runtime"}
    assert {
        "real_game_capture_fresh",
        "real_game_window_nonblank",
        "real_game_no_fatal_log_burst",
        "real_game_runtime_not_placeholder_dominated",
        "real_game_gamefeaturedata_asset_rule",
        "real_game_no_broken_toolsets_boot_path",
    }.issubset(gates)


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
