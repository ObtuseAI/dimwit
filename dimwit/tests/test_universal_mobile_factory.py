from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

import pytest

from dimwit.toolchains.engines import universal
from dimwit.toolchains.mobile import (
    audit_mobile,
    audit_store_readiness,
    discover_android,
    discover_ios,
    quality_matrix,
    validate_mobile_manifest,
)


def _project(tmp_path: Path, engine: str) -> Path:
    root = tmp_path / engine
    root.mkdir()
    if engine == "unreal":
        (root / "Game.uproject").write_text("{}", encoding="utf-8")
    elif engine == "unity":
        (root / "Assets").mkdir()
        (root / "ProjectSettings").mkdir()
        (root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000", encoding="utf-8")
    elif engine == "godot":
        (root / "project.godot").write_text("[application]", encoding="utf-8")
    elif engine == "defold":
        (root / "game.project").write_text("[project]", encoding="utf-8")
    elif engine == "bevy":
        (root / "Cargo.toml").write_text('[dependencies]\nbevy = "0.18"', encoding="utf-8")
    elif engine == "web":
        (root / "package.json").write_text(json.dumps({"dependencies": {"phaser": "3"}}), encoding="utf-8")
    elif engine == "flutter_flame":
        (root / "pubspec.yaml").write_text("dependencies:\n  flame: any", encoding="utf-8")
    elif engine == "cmake":
        (root / "CMakeLists.txt").write_text("project(Game)", encoding="utf-8")
    return root


@pytest.mark.parametrize("engine", ["unreal", "unity", "godot", "defold", "bevy", "web", "flutter_flame", "cmake"])
def test_detects_all_executable_engine_project_contracts(tmp_path, engine):
    project = universal.detect_project(_project(tmp_path, engine))
    assert project.engine == engine
    assert project.confidence >= 0.75


def test_universal_audit_advertises_extension_contract_and_targets():
    result = universal.audit_engines()
    assert result["state"] == "PASS"
    assert result["adapter_count"] == 8
    assert {"windows", "web", "android", "ios", "xr"}.issubset(result["targets"])
    assert result["extension_contract"].endswith("EngineAdapter")


def test_godot_plan_requires_declared_preset_and_is_headless_confined(tmp_path, monkeypatch):
    root = _project(tmp_path, "godot")
    executable = tmp_path / "Godot.exe"
    executable.write_bytes(b"tool")
    (root / "export_presets.cfg").write_text('[preset.0]\nname="Android"\nplatform="Android"', encoding="utf-8")
    monkeypatch.setattr(universal, "_godot_executable", lambda: str(executable))
    output = tmp_path / "artifacts" / "game.apk"
    plan = universal.plan_build(str(root), "android", str(output), preset="Android",
                                allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"])
    command = plan["plan"]["command"]
    assert plan["state"] == "PLAN_READY"
    assert "--headless" in command and "--export-release" in command
    assert plan["plan"]["shell"] is False


def test_universal_run_hashes_real_output_with_injected_runner(tmp_path, monkeypatch):
    root = _project(tmp_path, "godot")
    executable = tmp_path / "Godot.exe"
    executable.write_bytes(b"tool")
    (root / "export_presets.cfg").write_text('[preset.0]\nname="Windows"\nplatform="Windows Desktop"', encoding="utf-8")
    monkeypatch.setattr(universal, "_godot_executable", lambda: str(executable))
    output = tmp_path / "artifacts" / "game.exe"

    def runner(command, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"real game binary")
        return subprocess.CompletedProcess(command, 0, stdout="built", stderr="")

    result = universal.run_build(
        str(root), "windows", str(output), preset="Windows", allow_mutation=True, runner=runner,
        artifact_job_root=tmp_path / "jobs", allowed_project_roots=[tmp_path],
        allowed_output_roots=[tmp_path / "artifacts"],
    )
    assert result["state"] == "PASS"
    assert result["output_proofs"][0]["sha256"]
    assert (tmp_path / "jobs/universal_game_build/result.json").is_file()


def _valid_manifest(target: str) -> dict:
    base = {"version_name": "1.0.0", "version_code": 1, "distribution_signed": False}
    if target == "android":
        return {**base, "application_id": "com.dimwit.game", "min_sdk": 26, "target_sdk": 35,
                "architectures": ["arm64-v8a"], "store_format": "aab"}
    return {**base, "bundle_id": "com.dimwit.game", "architectures": ["arm64"],
            "privacy_manifest": "PrivacyInfo.xcprivacy"}


def test_mobile_manifests_enforce_android_and_ios_hard_requirements():
    assert validate_mobile_manifest(_valid_manifest("android"), "android")["passed"]
    assert validate_mobile_manifest(_valid_manifest("ios"), "ios")["passed"]
    bad = _valid_manifest("android") | {"target_sdk": 34, "architectures": ["x86_64"]}
    result = validate_mobile_manifest(bad, "android")
    assert not result["passed"]
    assert any("target_sdk" in issue for issue in result["issues"])
    assert any("arm64" in issue for issue in result["issues"])


def test_mobile_quality_matrix_covers_end_to_end_mobile_game_concerns():
    matrix = quality_matrix()
    assert matrix["lane_count"] == 12
    assert matrix["check_count"] >= 60
    ids = {row["id"] for row in matrix["lanes"]}
    assert {"touch", "performance", "accessibility", "privacy", "store", "monetization"}.issubset(ids)


def test_android_and_ios_discovery_are_honest_for_current_host():
    android = discover_android()
    assert "platform_api_floor" in android["exists"]
    ios = discover_ios()
    if platform.system().lower() != "darwin":
        assert not ios["ok"]
        assert ios["state"] == "BLOCKED_REQUIRES_MACOS_XCODE"
    assert audit_mobile()["store_upload"] == "OPERATOR_ONLY"


def test_store_readiness_blocks_missing_metadata_and_accepts_proven_artifact(tmp_path):
    artifact = tmp_path / "game.aab"
    artifact.write_bytes(b"real bundle")
    complete = _valid_manifest("android") | {
        "icons": ["icon.png"], "screenshots": ["screen.png"], "description": "A game",
        "age_rating": "pending operator questionnaire", "privacy_policy": "https://example.invalid/privacy",
        "support_url": "https://example.invalid/support", "release_notes": "Initial candidate",
    }
    assert audit_store_readiness(complete, [str(artifact)], "android")["state"] == "READY_FOR_OPERATOR_REVIEW"
    assert audit_store_readiness(_valid_manifest("android"), [str(artifact)], "android")["state"] == "BLOCKED"
