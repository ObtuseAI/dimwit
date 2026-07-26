"""Cross-engine mobile game factory: Android/iOS build, device, quality, and store-readiness gates.

This module never invents iOS readiness on Windows and never handles signing secrets or store uploads. Android
and iOS distribution signing remain operator-only. Development builds are plan-first and inherit the universal
engine factory's argv-only execution, output confinement, proof hashing, and review ceiling.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Callable

from dimwit.toolchains.common import atomic_json, output_proofs, require_job_id, require_within, run_process
from dimwit.toolchains.engines.universal import plan_build, run_build


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "mobile_game_factory.json"
ARTIFACT_ROOT = ROOT / "artifacts" / "mobile"
PACKAGE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){1,}$")
SAFE_DEVICE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
SAFE_ACTIVITY = re.compile(r"^[A-Za-z0-9_.$/]{1,160}$")


def _policy(path: Path = POLICY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sdk_root() -> Path:
    return Path(os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") or r"C:\Android\Sdk").resolve()


def _latest_version_dir(root: Path) -> Path | None:
    dirs = [path for path in root.iterdir() if path.is_dir()] if root.is_dir() else []
    def key(path: Path) -> tuple[int, ...]:
        return tuple(int(value) for value in re.findall(r"\d+", path.name))
    return max(dirs, key=key) if dirs else None


def discover_android() -> dict:
    sdk = _sdk_root()
    build_tools = _latest_version_dir(sdk / "build-tools")
    adb = sdk / "platform-tools" / "adb.exe"
    sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    aapt2 = build_tools / "aapt2.exe" if build_tools else Path()
    apksigner = build_tools / "apksigner.bat" if build_tools else Path()
    zipalign = build_tools / "zipalign.exe" if build_tools else Path()
    jarsigner = shutil.which("jarsigner")
    platforms = sorted(path.name for path in (sdk / "platforms").glob("android-*") if path.is_dir())
    platform_apis = [int(value) for name in platforms for value in re.findall(r"\d+", name)]
    ndks = sorted(path.name for path in (sdk / "ndk").iterdir()) if (sdk / "ndk").is_dir() else []
    exists = {
        "sdk": sdk.is_dir(), "adb": adb.is_file(), "sdkmanager": sdkmanager.is_file(),
        "aapt2": aapt2.is_file(), "apksigner": apksigner.is_file(), "zipalign": zipalign.is_file(),
        "jarsigner": bool(jarsigner), "platform_api_floor": bool(platform_apis and max(platform_apis) >= 35),
    }
    return {
        "ok": all(exists.values()), "sdk_root": str(sdk), "build_tools": build_tools.name if build_tools else None,
        "platforms": platforms, "maximum_platform_api": max(platform_apis) if platform_apis else None,
        "ndks": ndks, "tools": {
            "adb": str(adb), "sdkmanager": str(sdkmanager), "aapt2": str(aapt2),
            "apksigner": str(apksigner), "zipalign": str(zipalign), "jarsigner": jarsigner,
        }, "exists": exists,
        "capabilities": ["apk_build", "aab_build", "manifest_inspection", "alignment", "signature_verification",
                         "device_install", "device_launch", "log_capture", "screenshot", "performance_probe"],
    }


def discover_ios() -> dict:
    is_macos = platform.system().lower() == "darwin"
    xcodebuild = shutil.which("xcodebuild") if is_macos else None
    xcrun = shutil.which("xcrun") if is_macos else None
    remote_marker = ROOT / "config" / "mobile_remote_macos.json"
    return {
        "ok": bool(is_macos and xcodebuild and xcrun), "host_platform": platform.system(),
        "xcodebuild": xcodebuild, "xcrun": xcrun, "remote_mac_configured": remote_marker.is_file(),
        "state": "READY" if is_macos and xcodebuild and xcrun else "BLOCKED_REQUIRES_MACOS_XCODE",
        "reason": None if is_macos else "iOS archive/export requires a macOS host with Xcode",
        "capabilities": ["simulator_build", "device_build", "xcarchive", "ipa_export", "xctest",
                         "simctl_install", "simctl_launch", "instruments_profile", "testflight_candidate"],
        "distribution_signing": "OPERATOR_ONLY",
    }


def quality_matrix() -> dict:
    policy = _policy()
    lanes = policy.get("quality_lanes", [])
    return {"lane_count": len(lanes), "check_count": sum(len(row.get("checks", [])) for row in lanes),
            "lanes": lanes, "evidence_state": "REQUIRED_PER_GAME_BUILD"}


def validate_mobile_manifest(manifest: dict, target: str) -> dict:
    issues: list[str] = []
    warnings: list[str] = []
    policy = _policy()
    if target not in {"android", "ios"}:
        return {"passed": False, "issues": ["mobile target must be android or ios"], "warnings": []}
    identifier = str(manifest.get("application_id" if target == "android" else "bundle_id") or "")
    if not PACKAGE_ID.fullmatch(identifier):
        issues.append(f"invalid or missing {'application_id' if target == 'android' else 'bundle_id'}")
    if not str(manifest.get("version_name") or "").strip():
        issues.append("version_name is required")
    if int(manifest.get("version_code") or 0) < 1:
        issues.append("version_code must be positive")
    architectures = set(manifest.get("architectures") or [])
    if target == "android":
        rule = policy["android_policy"]
        if int(manifest.get("min_sdk") or 0) < int(rule["minimum_supported_sdk"]):
            issues.append(f"min_sdk below Dimwit floor {rule['minimum_supported_sdk']}")
        if int(manifest.get("target_sdk") or 0) < int(rule["play_target_sdk_floor"]):
            issues.append(f"target_sdk below current Play floor {rule['play_target_sdk_floor']}")
        if not set(rule["required_architectures"]).issubset(architectures):
            issues.append("arm64-v8a architecture is required")
        if manifest.get("store_format") != "aab":
            warnings.append("Google Play release candidates should use AAB")
    else:
        if not manifest.get("privacy_manifest"):
            issues.append("iOS privacy manifest evidence is required")
        if "arm64" not in architectures:
            issues.append("arm64 iOS architecture is required")
    if manifest.get("distribution_signed"):
        issues.append("distribution signing cannot be self-asserted by the autonomous lane")
    return {"passed": not issues, "issues": issues, "warnings": warnings,
            "target": target, "identifier": identifier, "signing": "OPERATOR_ONLY"}


def audit_mobile(manifest: dict | None = None, target: str | None = None) -> dict:
    android, ios, quality = discover_android(), discover_ios(), quality_matrix()
    manifest_result = validate_mobile_manifest(manifest, target) if manifest is not None and target else None
    return {
        "schema_version": 1, "state": "PASS" if android["ok"] else "BLOCKED",
        "android": android, "ios": ios, "quality": quality, "manifest": manifest_result,
        "review_ceiling": "PROMOTED_TO_REVIEW", "store_upload": "OPERATOR_ONLY",
        "invariants": ["no signing secrets", "no store uploads", "no fabricated iOS readiness",
                       "device actions require explicit device id", "every artifact requires hashes"],
    }


def write_mobile_audit(path: Path = ARTIFACT_ROOT / "mobile_audit.json") -> dict:
    report = audit_mobile()
    atomic_json(path, report)
    return report


def plan_mobile_build(project: str, target: str, output: str, *, manifest: dict,
                      engine: str = "auto", profile: str = "release", preset: str | None = None,
                      job_id: str = "mobile_game_build") -> dict:
    if target not in {"android", "ios"}:
        raise ValueError("target must be android or ios")
    validation = validate_mobile_manifest(manifest, target)
    if not validation["passed"]:
        return {"state": "BLOCKED", "issues": validation["issues"], "manifest": validation,
                "mutation_performed": False, "review_ceiling": "PROMOTED_TO_REVIEW"}
    if target == "android" and not discover_android()["ok"]:
        return {"state": "BLOCKED", "issues": ["Android SDK/toolchain incomplete"],
                "mutation_performed": False, "review_ceiling": "PROMOTED_TO_REVIEW"}
    if target == "ios" and not discover_ios()["ok"]:
        return {"state": "BLOCKED_REQUIRES_MACOS_XCODE", "issues": [discover_ios()["reason"]],
                "mutation_performed": False, "review_ceiling": "PROMOTED_TO_REVIEW"}
    plan = plan_build(project, target, output, engine=engine, profile=profile, preset=preset, job_id=job_id)
    plan["mobile_manifest"] = validation
    plan["mobile_quality"] = quality_matrix()
    plan["distribution_signing"] = "OPERATOR_ONLY"
    return plan


def run_mobile_build(project: str, target: str, output: str, *, manifest: dict,
                     allow_mutation: bool = False, runner: Callable | None = None, **kwargs) -> dict:
    planned = plan_mobile_build(project, target, output, manifest=manifest, **kwargs)
    if planned.get("state") != "PLAN_READY" or not allow_mutation:
        return planned
    return run_build(project, target, output, allow_mutation=True, runner=runner, **kwargs)


def inspect_android_artifact(path: str | Path, *, runner: Callable | None = None) -> dict:
    artifact = require_within(Path(path), [ROOT / "artifacts"], "Android artifact")
    proof = output_proofs([artifact])[0]
    if not proof["exists"] or artifact.suffix.lower() not in {".apk", ".aab"}:
        return {"state": "BLOCKED", "issues": ["APK/AAB artifact missing or invalid suffix"], "proof": proof}
    tools = discover_android()["tools"]
    if artifact.suffix.lower() == ".apk":
        command = [tools["apksigner"], "verify", "--verbose", "--print-certs", str(artifact)]
    else:
        command = [tools["jarsigner"], "-verify", "-verbose", "-certs", str(artifact)]
    job_dir = ARTIFACT_ROOT / "inspection" / artifact.stem
    process = run_process(command, job_dir, cwd=artifact.parent, timeout=120, runner=runner)
    return {"state": "PASS" if process["returncode"] == 0 else "FAIL", "artifact": proof,
            "signature_verification": process, "review_ceiling": "PROMOTED_TO_REVIEW"}


def plan_android_device_test(apk: str | Path, package_id: str, *, device_id: str,
                             activity: str = ".MainActivity", job_id: str = "android_device_test") -> dict:
    apk_path = require_within(Path(apk), [ROOT / "artifacts"], "Android APK")
    if apk_path.suffix.lower() != ".apk" or not apk_path.is_file():
        raise ValueError("device test requires an existing APK under artifacts")
    if not PACKAGE_ID.fullmatch(package_id) or not SAFE_DEVICE.fullmatch(device_id) or not SAFE_ACTIVITY.fullmatch(activity):
        raise ValueError("invalid package, device, or activity identifier")
    adb = discover_android()["tools"]["adb"]
    commands = [
        [adb, "-s", device_id, "install", "-r", str(apk_path)],
        [adb, "-s", device_id, "shell", "am", "force-stop", package_id],
        [adb, "-s", device_id, "shell", "am", "start", "-W", "-n", f"{package_id}/{activity}"],
        [adb, "-s", device_id, "shell", "dumpsys", "gfxinfo", package_id],
    ]
    return {"schema_version": 1, "state": "PLAN_READY", "job_id": require_job_id(job_id),
            "commands": commands, "device_id": device_id, "apk_proof": output_proofs([apk_path])[0],
            "mutation_performed": False, "requires_explicit_device_execution": True,
            "review_ceiling": "PROMOTED_TO_REVIEW"}


def audit_store_readiness(manifest: dict, artifact_paths: list[str], target: str) -> dict:
    validation = validate_mobile_manifest(manifest, target)
    proofs = output_proofs([Path(path) for path in artifact_paths])
    required = {
        "icons": bool(manifest.get("icons")), "screenshots": bool(manifest.get("screenshots")),
        "description": bool(manifest.get("description")), "age_rating": bool(manifest.get("age_rating")),
        "privacy_policy": bool(manifest.get("privacy_policy")), "support_url": bool(manifest.get("support_url")),
        "release_notes": bool(manifest.get("release_notes")),
    }
    issues = list(validation["issues"])
    issues.extend(f"missing store field: {name}" for name, present in required.items() if not present)
    if not proofs or any(not proof["exists"] or proof["bytes"] <= 0 for proof in proofs):
        issues.append("release artifact proof missing")
    return {"state": "READY_FOR_OPERATOR_REVIEW" if not issues else "BLOCKED", "issues": issues,
            "manifest": validation, "store_fields": required, "artifacts": proofs,
            "upload_performed": False, "signing": "OPERATOR_ONLY", "review_ceiling": "PROMOTED_TO_REVIEW"}
