from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.packaged_build_validation import (
    PackagedBuildValidationPipeline,
    build_package_manifest,
    validate_packaged_build_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_packaged_build_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _contrast_png(path: Path) -> Path:
    image = Image.new("RGB", (160, 100), (14, 18, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 25, 115, 80], fill=(34, 190, 190))
    draw.rectangle([72, 42, 92, 62], fill=(240, 105, 28))
    image.save(path)
    return path


def _package_fixture() -> tuple[Path, Path]:
    package_dir = TMP / "package"
    exe = package_dir / "Windows" / "WanefallGreybox" / "Binaries" / "Win64" / "WanefallGreybox.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes((b"MZ" + b"wanefall-packaged-build-proof") * 2048)
    (package_dir / "Windows" / "WanefallGreybox" / "Content" / "Paks").mkdir(parents=True, exist_ok=True)
    (package_dir / "Windows" / "WanefallGreybox" / "Content" / "Paks" / "WanefallGreybox-Windows.pak").write_bytes(b"pak" * 4096)
    return package_dir, exe


def test_package_manifest_records_executable_size_hash_and_total_bytes():
    package_dir, exe = _package_fixture()
    manifest = build_package_manifest(package_dir, exe)

    assert manifest["package_dir"] == str(package_dir)
    assert manifest["executable"]["path"] == str(exe)
    assert manifest["executable"]["exists"] is True
    assert manifest["executable"]["bytes"] > 10_000
    assert len(manifest["executable"]["sha256"]) == 64
    assert manifest["file_count"] >= 2
    assert manifest["total_bytes"] >= manifest["executable"]["bytes"]


def test_validate_packaged_build_result_blocks_missing_file():
    try:
        validate_packaged_build_result(TMP / "missing_packaged_result.json", max_age_seconds=60)
    except BlockedError as exc:
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("missing packaged-build result must block")


def test_validate_packaged_build_result_accepts_real_packaged_smoke_shape():
    package_dir, exe = _package_fixture()
    manifest = build_package_manifest(package_dir, exe)
    still = _contrast_png(TMP / "packaged_still.png")
    result_path = TMP / "packaged_build_result.json"
    _write_json(result_path, {
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "packaged_build",
        "package": {
            "uat_returncode": 0,
            "archive_dir": str(package_dir),
            "executable": str(exe),
            "manifest": manifest,
        },
        "checks": {
            "package_manifest": {"passed": True, "issues": [], "manifest": manifest},
            "executable_hash": {"passed": True, "issues": [], "sha256": manifest["executable"]["sha256"]},
            "window_found": {"passed": True, "issues": [], "title": "WanefallGreybox"},
            "still_nonblank": {"passed": True, "issues": [], "path": str(still), "metrics": {"contrast": 0.4}},
            "frame_burst_nonblank": {"passed": True, "issues": [], "frame_count": 2},
            "packaged_log_scan": {"passed": True, "issues": [], "fatal_count": 0, "error_count": 0},
            "process_identity": {"passed": True, "issues": [], "captured_pid": 4321,
                                 "expected_pid": 4321, "captured_proc": "WanefallGreybox",
                                 "expected_proc": "WanefallGreybox", "capture_tier": "printwindow"},
            "gameplay_map_loaded": {"passed": True, "issues": [], "map_token": "Wanefall_Arena4v4_Prototype_01"},
            "gameplay_process_identity": {"passed": True, "issues": [], "captured_pid": 4321,
                                          "expected_pid": 4321},
            "gameplay_motion_delta": {"passed": True, "issues": [], "max_mean_delta": 0.11,
                                      "threshold": 0.02, "frame_count": 15},
        },
    })

    result = validate_packaged_build_result(result_path, max_age_seconds=60)
    assert result["suite_pass"] is True
    assert result["runtime_source"] == "packaged_build"
    assert result["package"]["manifest"]["executable"]["sha256"] == manifest["executable"]["sha256"]


def test_validate_packaged_build_result_rejects_editor_runtime_source():
    package_dir, exe = _package_fixture()
    result_path = TMP / "editor_runtime_result.json"
    _write_json(result_path, {
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "editor_standalone",
        "package": {"archive_dir": str(package_dir), "executable": str(exe), "manifest": {}},
        "checks": {
            "package_manifest": {"passed": True, "issues": []},
            "executable_hash": {"passed": True, "issues": []},
            "window_found": {"passed": True, "issues": []},
            "still_nonblank": {"passed": True, "issues": []},
            "frame_burst_nonblank": {"passed": True, "issues": []},
            "packaged_log_scan": {"passed": True, "issues": []},
        },
    })

    result = validate_packaged_build_result(result_path, max_age_seconds=60)
    assert result["suite_pass"] is False
    assert result["checks"]["runtime_source"]["passed"] is False
    assert "packaged_build" in "; ".join(result["checks"]["runtime_source"]["issues"])


def test_pipeline_plan_uses_uat_buildcookrun_and_archive_dir():
    pipeline = PackagedBuildValidationPipeline()
    plan = pipeline.plan({
        "asset_id": "wanefall_win64_development",
        "configuration": "Development",
        "map_url": "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01",
        "timeout_seconds": 123,
        "smoke_seconds": 1,
        "smoke_fps": 2,
    })

    command = " ".join(str(part) for part in plan["uat_command"])
    assert "RunUAT.bat" in str(plan["run_uat"])
    assert "BuildCookRun" in command
    assert "-stage" in plan["uat_command"]
    assert "-archive" in plan["uat_command"]
    assert "-clientconfig=Development" in plan["uat_command"]
    assert "-SkipZenStore" in command
    assert "-DisablePlugins=ModelContextProtocol" in command
    assert "-DDC=InstalledNoZenLocalFallback" in command
    assert "-SharedDataCachePath=None" in command
    assert "-LocalDataCachePath=D:\\WanefallBuild\\DDC" in command
    assert "-CookOutputDir=D:\\WanefallBuild\\CookedOutput\\" in command
    assert "-OutputDir=D:\\WanefallBuild\\CookedOutput\\" in command
    assert str(plan["cook_output_root"]).startswith("D:\\WanefallBuild\\CookedOutput\\")
    assert str(plan["cook_output_dir"]).endswith("\\Windows")
    assert str(plan["stage_dir"]).startswith("D:\\WanefallBuild\\PackagedBuildValidation\\runs\\")
    assert str(plan["archive_dir"]).startswith("D:\\WanefallBuild\\PackagedBuildValidation\\runs\\")
    assert str(plan["temp_dir"]).startswith("D:\\WanefallBuild\\Temp\\")
    assert str(plan["ddc_dir"]) == "D:\\WanefallBuild\\DDC"
    assert plan["archive_dir"].name == "archive"
    assert plan["result_path"].name == "packaged_build_result.json"
    assert plan["gameplay"]["fire_key"] == "f"
    assert plan["gameplay"]["fire_taps"] == 12
    assert plan["gameplay"]["combat_settle_seconds"] == 12.0


def test_pipeline_default_map_uses_command_shell_not_lobby_or_hold():
    pipeline = PackagedBuildValidationPipeline()
    plan = pipeline.plan({"asset_id": "wanefall_win64_development"})

    assert "Wanefall_ModeShell_Prototype_01" in plan["map_url"]
    assert "Wanefall_Lobby" not in plan["map_url"]
    assert "Wanefall_TheHold" not in plan["map_url"]


def test_validation_registry_contains_packaged_build_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "packaged_build"}
    assert {
        "packaged_build_result_fresh",
        "packaged_build_manifest_complete",
        "packaged_build_executable_hash_present",
        "packaged_build_runtime_smoke_nonblank",
        "packaged_build_log_scan_clean",
        "packaged_build_queue_sync",
    }.issubset(gates)


def test_pipeline_registry_manifest_and_director_include_packaged_build():
    from dimwit.pipelines import PIPELINES

    manifest = json.loads(Path("config/production_pipelines.json").read_text(encoding="utf-8"))
    director = json.loads(Path("config/director_tasks.json").read_text(encoding="utf-8"))
    assert "packaged_build_validation" in PIPELINES
    assert "packaged_build_validation" in manifest["pipelines"]
    assert any(task.get("pipeline") == "packaged_build_validation" for task in director["tasks"])


def test_autonomy_and_game_builder_lanes_require_packaged_proof_domain():
    from dimwit.pipelines.autonomy_capability_matrix import build_autonomy_capability_matrix
    from dimwit.pipelines.unreal_game_builder_engine import build_unreal_game_builder_report

    root = TMP / "queue_root"
    project = TMP / "queue_project"
    _write_json(project / "WanefallGreybox.uproject", {"EngineAssociation": "5.8", "Plugins": []})
    _write_json(root / "artifacts" / "validation" / "validation_report.json", {
        "suite_verdict": "PASS",
        "run_ts": int(time.time()),
        "counts": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        "total": 6,
        "by_domain": {
            "packaged_build": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "real_game_runtime": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "autonomy_engine": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "pipeline_contracts": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        },
        "results": [],
    })
    _write_json(root / "artifacts" / "packaged_build_validation" / "packaged_build_result.json", {
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "packaged_build",
    })
    _write_json(root / "artifacts" / "real_game_validation" / "real_game_validation_result.json", {"state": "PASS", "suite_pass": True})
    _write_json(root / "artifacts" / "metahuman_utilization" / "metahuman_utilization_audit.json", {
        "summary": {"classification": "READY_FOR_REVIEW_METAHUMAN_OUTPUT_PRESENT", "metahuman_output_present": True},
        "metahuman_outputs": {"present": True},
    })
    _write_json(root / "artifacts" / "pipeline_contracts" / "pipeline_contract_audit.json", {
        "summary": {"passed": True},
        "checks": {},
    })
    _write_json(root / "codex_handoff.json", {"ceiling": "PROMOTED_TO_REVIEW", "work_queue": []})
    _write_json(root / "config" / "director_tasks.json", {"tasks": []})
    _write_json(root / "config" / "production_pipelines.json", {"pipelines": {}})

    autonomy = build_autonomy_capability_matrix(root, project)
    build_packaging = {row["required_lane"]: row for row in autonomy["capability_matrix"]}["build_packaging"]
    assert build_packaging["state"] == "PASS"
    assert "packaged_build" in build_packaging["validation_command"]
    assert any("packaged_build_validation" in item for item in build_packaging["evidence"])

    builder = build_unreal_game_builder_report(root, project)
    lane = {row["lane_id"]: row for row in builder["game_builder_lanes"]}["build_packaging_deploy"]
    assert "packaged_build" in lane["validation_domains"]
    assert lane["current_state"] == "PASS"
    assert builder["source_truth"]["packaged_build_state"] == "PASS"


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
