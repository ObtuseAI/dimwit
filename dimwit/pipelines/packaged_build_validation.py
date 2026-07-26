"""Packaged-build validation pipeline for WANEFALL.

This lane proves release-style build readiness with a real UAT package and a
smoke-tested packaged executable. Editor standalone validation remains useful,
but it cannot satisfy this package gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from dimwit.desktop_eyes import DesktopEyes, process_identity_check
from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.real_game_validation import (
    analyze_capture,
    detect_placeholder_geometry,
    scan_log_text,
)


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
UE_ROOT = Path(r"C:\UE_5.8")
RUN_UAT = UE_ROOT / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
UPROJECT = PROJECT / "WanefallGreybox.uproject"
RESULT_DIR = ROOT / "artifacts" / "packaged_build_validation"
RESULT_PATH = RESULT_DIR / "packaged_build_result.json"
MANIFEST_PATH = RESULT_DIR / "package_manifest.json"
BUILD_ROOT = Path(r"D:\WanefallBuild")
PACKAGE_WORKSPACE = BUILD_ROOT / "PackagedBuildValidation"
DEFAULT_DDC_DIR = BUILD_ROOT / "DDC"
DEFAULT_TEMP_ROOT = BUILD_ROOT / "Temp"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_PACKAGED_BUILD_PROOF_REPORT_20260629.md"
SHARED_FOLDER = Path(r"C:\Users\developer\Desktop\Shared Folder")
SHARED_REPORT = SHARED_FOLDER / "WANEFALL_PACKAGED_BUILD_PROOF_REPORT_20260629.md"
DEFAULT_MAP_URL = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01?game=/Script/WanefallGreybox.WanefallLobbyGameMode"
# gameplay maps cooked into every package: the QUICK DEPLOY target first (its name doubles as the
# map-load log token for the gameplay smoke), then the Wane Trial duel chamber
DEFAULT_GAMEPLAY_MAPS = [
    "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01",
    "/Game/Wanefall/Maps/Wanefall_WaneTrialJailCell_01",
]
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60
MIN_PACKAGE_FILES = 2


def frame_motion_delta(frame_paths, threshold: float = 0.02) -> dict:
    """Fail-closed motion gate: consecutive gameplay frames must visibly differ.

    The 2026-07-01 audit found every runtime 'burst' was byte-identical stills - nonblank gates
    can never distinguish a frozen menu from play. Mean absolute pixel delta (0..1) between
    consecutive frames; the MAX pair must clear `threshold`. Static or single-frame input fails."""
    from PIL import Image, ImageChops, ImageStat

    paths = [Path(p) for p in frame_paths if Path(p).exists()]
    if len(paths) < 2:
        return {"passed": False, "issues": [f"need >=2 frames for motion evidence, got {len(paths)}"],
                "max_mean_delta": 0.0, "threshold": threshold, "pairs": []}
    pairs = []
    prev = Image.open(paths[0]).convert("L")
    for path in paths[1:]:
        cur = Image.open(path).convert("L")
        if cur.size != prev.size:
            cur = cur.resize(prev.size)
        delta = ImageStat.Stat(ImageChops.difference(prev, cur)).mean[0] / 255.0
        pairs.append(round(delta, 5))
        prev = cur
    max_delta = max(pairs)
    passed = max_delta >= threshold
    issues = [] if passed else [
        f"no visible motion between frames: max mean delta {max_delta:.5f} < threshold {threshold}"]
    return {"passed": passed, "issues": issues, "max_mean_delta": round(max_delta, 5),
            "threshold": threshold, "pairs": pairs, "frame_count": len(paths)}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _float_value(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _int_value(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def build_package_manifest(package_dir: Path | str, executable_path: Path | str | None = None) -> dict:
    """Return deterministic size/hash evidence for a packaged build directory."""
    package_root = Path(package_dir)
    exe = Path(executable_path) if executable_path else _find_packaged_executable(package_root)
    files: list[dict] = []
    total_bytes = 0
    if package_root.exists():
        for path in sorted(item for item in package_root.rglob("*") if item.is_file()):
            rel = path.relative_to(package_root).as_posix()
            size = path.stat().st_size
            total_bytes += size
            record = {"path": rel, "bytes": size}
            if path == exe or path.suffix.lower() in {".exe", ".pak", ".ucas", ".utoc"}:
                record["sha256"] = _sha256_file(path)
            files.append(record)

    exe_exists = bool(exe and exe.exists())
    executable = {
        "path": str(exe) if exe else None,
        "exists": exe_exists,
        "bytes": exe.stat().st_size if exe_exists else 0,
        "sha256": _sha256_file(exe) if exe_exists else "",
    }
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "package_dir": str(package_root),
        "exists": package_root.exists(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "executable": executable,
        "files": files[:400],
        "truncated_file_list": len(files) > 400,
    }


def _find_packaged_executable(package_dir: Path) -> Path | None:
    if not package_dir.exists():
        return None
    matches = [
        path for path in package_dir.rglob("WanefallGreybox.exe")
        if path.is_file() and "Binaries" in path.parts
    ]
    if not matches:
        matches = [path for path in package_dir.rglob("WanefallGreybox.exe") if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_size)


def _freshness(result: dict, max_age_seconds: int) -> dict:
    captured_at = result.get("captured_at")
    if not isinstance(captured_at, (int, float)):
        return {"passed": False, "issues": ["captured_at missing or not numeric"], "age_seconds": None}
    age_seconds = time.time() - float(captured_at)
    issues = []
    if age_seconds < -5:
        issues.append(f"captured_at is in the future by {abs(age_seconds):.1f}s")
    if age_seconds > max_age_seconds:
        issues.append(f"result age {age_seconds:.1f}s > {max_age_seconds}s")
    return {
        "passed": not issues,
        "issues": issues,
        "age_seconds": round(age_seconds, 3),
        "max_age_seconds": int(max_age_seconds),
    }


def _validate_runtime_source(result: dict) -> dict:
    if result.get("runtime_source") != "packaged_build":
        return {
            "passed": False,
            "issues": [f"runtime_source must be packaged_build, got {result.get('runtime_source')!r}"],
        }
    return {"passed": True, "issues": [], "runtime_source": "packaged_build"}


def validate_packaged_build_result(
    path: Path | str = RESULT_PATH,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"packaged-build result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"packaged-build result unreadable: {exc}") from exc
    if not isinstance(result, dict):
        raise BlockedError(f"packaged-build result root is not an object: {result_path}")

    result = dict(result)
    checks = dict(result.get("checks") or {})
    checks["freshness"] = _freshness(result, max_age_seconds=max_age_seconds)
    checks["runtime_source"] = _validate_runtime_source(result)

    for required in (
        "package_manifest",
        "executable_hash",
        "window_found",
        "still_nonblank",
        "frame_burst_nonblank",
        "packaged_log_scan",
        "process_identity",
        "gameplay_map_loaded",
        "gameplay_motion_delta",
        "gameplay_process_identity",
    ):
        if required not in checks:
            checks[required] = {"passed": False, "issues": [f"missing check: {required}"]}

    result["checks"] = checks
    result["suite_pass"] = bool(checks) and all(bool(check.get("passed")) for check in checks.values())
    if result["suite_pass"]:
        result["state"] = "PASS"
    elif result.get("state") == "PASS":
        result["state"] = "BLOCKED"
    return result


def _latest_log_text(paths: list[Path]) -> dict:
    logs: list[Path] = []
    for folder in paths:
        if folder.exists():
            logs.extend(path for path in folder.rglob("*.log") if path.is_file())
    if not logs:
        return {"available": False, "path": None, "text": "", "issue": "no packaged log files found"}
    latest = max(logs, key=lambda path: path.stat().st_mtime)
    try:
        lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"available": False, "path": str(latest), "text": "", "issue": f"log unreadable: {exc}"}
    return {"available": True, "path": str(latest), "text": "\n".join(lines[-2000:]), "issue": ""}


def _packaged_log_dirs(package_dir: Path) -> list[Path]:
    dirs = [package_dir / "Windows" / "WanefallGreybox" / "Saved" / "Logs"]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "WanefallGreybox" / "Saved" / "Logs")
    return dirs


def _make_report(result: dict, report_path: Path) -> str:
    checks = result.get("checks") or {}
    package = result.get("package") or {}
    env = result.get("packaging_environment") or {}
    lines = [
        "# WANEFALL Packaged Build Proof Report - 2026-06-29",
        "",
        f"State: {result.get('state')}",
        f"Suite pass: {result.get('suite_pass')}",
        f"Runtime source: {result.get('runtime_source')}",
        f"Archive dir: `{package.get('archive_dir')}`",
        f"Stage dir: `{env.get('stage_dir')}`",
        f"Cook output dir: `{env.get('cook_output_dir')}`",
        f"DDC dir: `{env.get('ddc_dir')}`",
        f"Executable: `{package.get('executable')}`",
        f"UAT return code: `{package.get('uat_returncode')}`",
        "",
        "## Artifacts",
        f"- Result JSON: `{result.get('result_path')}`",
        f"- Manifest JSON: `{result.get('manifest_path')}`",
        f"- Still capture: `{(result.get('artifacts') or {}).get('still')}`",
        f"- Frame dir: `{(result.get('artifacts') or {}).get('frames_dir')}`",
        f"- UAT stdout: `{(result.get('artifacts') or {}).get('uat_stdout')}`",
        f"- Packaged log: `{(checks.get('packaged_log_scan') or {}).get('path')}`",
        "",
        "## Checks",
    ]
    for name, check in checks.items():
        lines.append(f"- {name}: passed={check.get('passed')} issues={check.get('issues', [])}")
    lines.extend([
        "",
        "## Boundaries",
        "- This proves a packaged Win64 Development build and packaged-runtime smoke only.",
        "- No HUMAN_ACCEPTED state was written.",
        "- No PROMOTED_TO_ACTIVE_SLICE state was written.",
        "- Missing package or smoke evidence remains blocked, never fake green.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class PackagedBuildValidationPipeline(ProductionPipeline):
    name = "packaged_build_validation"
    kind = "packaged_build_validation"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "wanefall_win64_development")
        configuration = str(task.get("configuration") or "Development")
        platform = str(task.get("platform") or "Win64")
        map_url = str(task.get("map_url") or DEFAULT_MAP_URL)
        # gameplay maps ship IN the package: a menu-only cook meant "packaged proof" could never
        # contain evidence of play (2026-07-01 audit; ENTER-deploy targeted an uncooked map)
        gameplay_maps = [str(m) for m in (task.get("gameplay_maps") or DEFAULT_GAMEPLAY_MAPS)]
        run_id = str(task.get("run_id") or time.strftime("%Y%m%d_%H%M%S"))
        output_dir = Path(task.get("output_dir") or RESULT_DIR)
        build_root = Path(task.get("build_root") or BUILD_ROOT)
        package_workspace = Path(task.get("package_workspace") or build_root / "PackagedBuildValidation")
        ddc_dir = Path(task.get("ddc_dir") or build_root / "DDC")
        temp_dir = Path(task.get("temp_dir") or build_root / "Temp" / run_id)
        run_dir = output_dir / "runs" / run_id
        package_run_dir = Path(task.get("package_run_dir") or package_workspace / "runs" / run_id)
        archive_dir = Path(task.get("archive_dir") or package_run_dir / "archive")
        stage_dir = Path(task.get("stage_dir") or package_run_dir / "stage")
        cook_output_root = Path(task.get("cook_output_root") or build_root / "CookedOutput" / run_id)
        cook_output_dir = Path(task.get("cook_output_dir") or cook_output_root / "Windows")
        uat_stdout = run_dir / "uat_stdout.log"
        uat_stderr = run_dir / "uat_stderr.log"
        cooker_options = [
            "-SkipZenStore",
            # The editor-side MCP plugin owns a local HTTP listener and is not
            # required to cook game content. Disable it for the cook commandlet
            # so an unrelated IDE/MCP service on port 8000 cannot break builds.
            "-DisablePlugins=ModelContextProtocol",
            "-DDC=InstalledNoZenLocalFallback",
            f"-LocalDataCachePath={ddc_dir}",
            "-SharedDataCachePath=None",
            f"-OutputDir={cook_output_dir}",
        ]
        command = [
            str(task.get("run_uat") or RUN_UAT),
            "BuildCookRun",
            f"-project={task.get('uproj') or UPROJECT}",
            "-noP4",
            f"-platform={platform}",
            f"-clientconfig={configuration}",
            "-build",
            "-cook",
            "-stage",
            "-pak",
            "-archive",
            f"-archivedirectory={archive_dir}",
            f"-stagingdirectory={stage_dir}",
            f"-CookOutputDir={cook_output_dir}",
            "-map=" + "+".join([map_url.split("?")[0]] + gameplay_maps),
            f"-AdditionalCookerOptions={' '.join(cooker_options)}",
            "-unattended",
            "-utf8output",
        ]
        return {
            "asset_id": asset_id,
            "configuration": configuration,
            "platform": platform,
            "project": Path(task.get("project") or PROJECT),
            "uproj": Path(task.get("uproj") or UPROJECT),
            "run_uat": Path(task.get("run_uat") or RUN_UAT),
            "map_url": map_url,
            "output_dir": output_dir,
            "run_dir": run_dir,
            "build_root": build_root,
            "package_workspace": package_workspace,
            "package_run_dir": package_run_dir,
            "archive_dir": archive_dir,
            "stage_dir": stage_dir,
            "cook_output_root": cook_output_root,
            "cook_output_dir": cook_output_dir,
            "ddc_dir": ddc_dir,
            "temp_dir": temp_dir,
            "result_path": output_dir / "packaged_build_result.json",
            "manifest_path": output_dir / "package_manifest.json",
            "still_path": output_dir / "still.png",
            "frames_dir": output_dir / "frames",
            "uat_stdout": uat_stdout,
            "uat_stderr": uat_stderr,
            "local_report": output_dir / "WANEFALL_PACKAGED_BUILD_PROOF_REPORT_20260629.md",
            "shared_report": SHARED_REPORT,
            "window_title": str(task.get("window_title") or "WanefallGreybox"),
            "timeout_seconds": _int_value(task.get("timeout_seconds"), 3600),
            "max_wait_seconds": _int_value(task.get("max_wait_seconds"), 120),
            "settle_seconds": _float_value(task.get("settle_seconds"), 20.0),
            "smoke_seconds": _float_value(task.get("smoke_seconds"), 2.0),
            "smoke_fps": _float_value(task.get("smoke_fps"), 4.0),
            "skip_uat": _bool_value(task.get("skip_uat", False)),
            "skip_smoke": _bool_value(task.get("skip_smoke", False)),
            "cooker_options": cooker_options,
            "uat_command": command,
            "gameplay_maps": gameplay_maps,
            "gameplay": {
                "enabled": _bool_value(task.get("gameplay_smoke", True)),
                "deploy_key": str(task.get("deploy_key") or "enter"),
                "map_token": Path(str(gameplay_maps[0])).name if gameplay_maps else "",
                "map_load_wait_seconds": _int_value(task.get("map_load_wait_seconds"), 60),
                "move_key": str(task.get("move_key") or "w"),
                "move_seconds": _float_value(task.get("move_seconds"), 2.5),
                "fire_key": str(task.get("fire_key") or "f"),
                "fire_taps": _int_value(task.get("fire_taps"), 12),
                "fire_interval_seconds": _float_value(task.get("fire_interval_seconds"), 0.25),
                "combat_settle_seconds": _float_value(task.get("combat_settle_seconds"), 12.0),
                "motion_threshold": _float_value(task.get("motion_threshold"), 0.02),
                "gameplay_fps": _float_value(task.get("gameplay_fps"), 6.0),
                "gameplay_still_path": output_dir / "gameplay" / "gameplay_still.png",
                "gameplay_frames_dir": output_dir / "gameplay" / "frames",
            },
        }

    def execute(self, plan: dict) -> Artifact:
        result = self._run_packaging_and_smoke(plan)
        _write_json(Path(plan["result_path"]), result)
        _make_report(result, Path(plan["local_report"]))
        try:
            _make_report(result, Path(plan["shared_report"]))
        except Exception as exc:
            result.setdefault("report_warnings", []).append(f"shared report write failed: {exc}")
            _write_json(Path(plan["result_path"]), result)
        # Self-sustaining D: retention: bound the packaged-build workspace to the newest few runs
        # (+ this run, via the just-written manifest) so the ~4.8G/run pileup can't exhaust D:.
        try:
            from dimwit.build_retention import prune_packaged_runs
            prune_packaged_runs(dry_run=False)
        except Exception as exc:
            result.setdefault("report_warnings", []).append(f"retention prune skipped: {exc}")
            _write_json(Path(plan["result_path"]), result)
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={
                "result_path": str(plan["result_path"]),
                "suite_pass": bool(result.get("suite_pass")),
                "archive_dir": (result.get("package") or {}).get("archive_dir"),
                "executable": (result.get("package") or {}).get("executable"),
            },
            provenance={"source": "local_wanefall_unreal_uat_packaged_build", "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_packaged_build_result(Path(plan["result_path"]), max_age_seconds=DEFAULT_MAX_AGE_SECONDS)
        issues = []
        for name, check in (result.get("checks") or {}).items():
            if not check.get("passed"):
                issues.extend([f"{name}: {issue}" for issue in check.get("issues", [])] or [f"{name}: failed"])
        evidence = [str(plan["result_path"]), str(plan["manifest_path"])]
        artifacts = result.get("artifacts") or {}
        if artifacts.get("still"):
            evidence.append(artifacts["still"])
        return Verdict(
            score=1.0 if result.get("suite_pass") else self._score_checks(result.get("checks") or {}),
            passed=bool(result.get("suite_pass")),
            hard_fail=False,
            issues=issues,
            detail={"state": result.get("state"), "checks": result.get("checks"), "result_path": str(plan["result_path"])},
            evidence=evidence,
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact

    def _run_packaging_and_smoke(self, plan: dict) -> dict:
        started_at = time.time()
        output_dir = Path(plan["output_dir"])
        run_dir = Path(plan["run_dir"])
        archive_dir = Path(plan["archive_dir"])
        stage_dir = Path(plan["stage_dir"])
        cook_output_root = Path(plan["cook_output_root"])
        cook_output_dir = Path(plan["cook_output_dir"])
        ddc_dir = Path(plan["ddc_dir"])
        temp_dir = Path(plan["temp_dir"])
        frames_dir = Path(plan["frames_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        stage_dir.mkdir(parents=True, exist_ok=True)
        cook_output_root.mkdir(parents=True, exist_ok=True)
        cook_output_dir.mkdir(parents=True, exist_ok=True)
        ddc_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        if frames_dir.exists():
            for frame in frames_dir.glob("*.png"):
                frame.unlink(missing_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        uat_result = self._run_uat(plan)
        executable = _find_packaged_executable(archive_dir)
        manifest = build_package_manifest(archive_dir, executable)
        _write_json(Path(plan["manifest_path"]), manifest)
        checks = {
            "package_manifest": self._check_package_manifest(uat_result, manifest),
            "executable_hash": self._check_executable_hash(manifest),
        }
        observations = {"uat": uat_result}
        smoke = self._run_smoke(plan, executable, checks) if executable and not plan["skip_smoke"] else {}
        observations["smoke"] = smoke
        checks["packaged_log_scan"] = self._scan_packaged_log(archive_dir)
        result = self._assemble_result(plan, started_at, uat_result, executable, manifest, checks, observations)
        return result

    def _run_uat(self, plan: dict) -> dict:
        stdout_path = Path(plan["uat_stdout"])
        stderr_path = Path(plan["uat_stderr"])
        if plan["skip_uat"]:
            return {
                "command": list(plan["uat_command"]),
                "returncode": 0,
                "elapsed_seconds": 0.0,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "skipped": True,
            }
        if not Path(plan["run_uat"]).exists():
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(f"RunUAT missing: {plan['run_uat']}\n", encoding="utf-8")
            return {
                "command": list(plan["uat_command"]),
                "returncode": 9009,
                "elapsed_seconds": 0.0,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "error": f"RunUAT missing: {plan['run_uat']}",
            }
        started = time.time()
        temp_dir = Path(plan["temp_dir"])
        ddc_dir = Path(plan["ddc_dir"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        ddc_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["TMP"] = str(temp_dir)
        env["TEMP"] = str(temp_dir)
        env["UE-LocalDataCachePath"] = str(ddc_dir)
        env["UE-SharedDataCachePath"] = "None"
        try:
            completed = subprocess.run(
                list(plan["uat_command"]),
                capture_output=True,
                text=True,
                timeout=int(plan["timeout_seconds"]),
                env=env,
            )
            stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
            stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
            return {
                "command": list(plan["uat_command"]),
                "returncode": int(completed.returncode),
                "elapsed_seconds": round(time.time() - started, 3),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "stdout_tail": (completed.stdout or "").splitlines()[-80:],
                "stderr_tail": (completed.stderr or "").splitlines()[-80:],
                "environment_overrides": {
                    "TMP": str(temp_dir),
                    "TEMP": str(temp_dir),
                    "UE-LocalDataCachePath": str(ddc_dir),
                    "UE-SharedDataCachePath": "None",
                },
            }
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
            stderr_path.write_text((exc.stderr or "") + "\nUAT timed out\n", encoding="utf-8", errors="replace")
            return {
                "command": list(plan["uat_command"]),
                "returncode": 124,
                "elapsed_seconds": round(time.time() - started, 3),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "error": f"UAT timed out after {plan['timeout_seconds']}s",
                "environment_overrides": {
                    "TMP": str(temp_dir),
                    "TEMP": str(temp_dir),
                    "UE-LocalDataCachePath": str(ddc_dir),
                    "UE-SharedDataCachePath": "None",
                },
            }

    def _run_smoke(self, plan: dict, executable: Path | None, checks: dict) -> dict:
        if executable is None or not executable.exists():
            checks["window_found"] = {"passed": False, "issues": ["packaged executable missing"]}
            checks["still_nonblank"] = {"passed": False, "issues": ["packaged executable missing"]}
            checks["frame_burst_nonblank"] = {"passed": False, "issues": ["packaged executable missing"]}
            return {"started": False, "reason": "missing executable"}

        cmd = [
            str(executable),
            str(plan["map_url"]),
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-nosound",
        ]
        proc = None
        try:
            proc = subprocess.Popen(cmd, cwd=str(executable.parent))
        except Exception as exc:
            checks["window_found"] = {"passed": False, "issues": [f"packaged executable launch failed: {exc}"]}
            checks["still_nonblank"] = {"passed": False, "issues": ["packaged executable launch failed"]}
            checks["frame_burst_nonblank"] = {"passed": False, "issues": ["packaged executable launch failed"]}
            return {"started": False, "command": cmd, "error": repr(exc)}

        eyes = DesktopEyes()
        window = self._wait_for_window(eyes, str(plan["window_title"]), int(plan["max_wait_seconds"]))
        if not window:
            checks["window_found"] = {"passed": False, "issues": [f"packaged window not found: {plan['window_title']}"]}
            checks["still_nonblank"] = {"passed": False, "issues": ["packaged window not found"]}
            checks["frame_burst_nonblank"] = {"passed": False, "issues": ["packaged window not found"]}
            self._terminate_process(proc)
            return {"started": True, "command": cmd, "window_found": False}

        checks["window_found"] = {
            "passed": True,
            "issues": [],
            "title": window.get("title"),
            "width": window.get("width"),
            "height": window.get("height"),
        }
        settle_seconds = max(0.0, float(plan.get("settle_seconds") or 0.0))
        if settle_seconds:
            time.sleep(settle_seconds)

        still_path = Path(plan["still_path"])
        expected_proc = executable.stem
        still_capture = eyes.capture_window(str(plan["window_title"]), still_path, proc=expected_proc)
        checks["process_identity"] = process_identity_check(
            still_capture, expected_pid=(proc.pid if proc else None), expected_proc=expected_proc)
        if still_capture.get("ok") and still_path.exists():
            still = analyze_capture(still_path)
            placeholder = detect_placeholder_geometry(still)
            if not placeholder.get("passed"):
                still = dict(still)
                still["passed"] = False
                still["issues"] = list(still.get("issues") or []) + list(placeholder.get("issues") or [])
                still["placeholder"] = placeholder
            checks["still_nonblank"] = still
        else:
            checks["still_nonblank"] = {
                "passed": False,
                "issues": [still_capture.get("error") or "packaged still capture failed"],
                "capture": still_capture,
            }

        burst = eyes.capture_stream(
            Path(plan["frames_dir"]),
            str(plan["window_title"]),
            seconds=float(plan["smoke_seconds"]),
            fps=float(plan["smoke_fps"]),
        )
        frames = [Path(path) for path in burst.get("frames", []) if Path(path).exists()]
        checks["frame_burst_nonblank"] = self._check_frames(frames)
        gameplay_obs = self._run_gameplay_smoke(plan, proc, eyes, checks, executable)
        self._terminate_process(proc)
        return {"started": True, "command": cmd, "window": checks["window_found"],
                "still_capture": still_capture, "frame_capture": burst, "gameplay": gameplay_obs}

    def _run_gameplay_smoke(self, plan: dict, proc, eyes: DesktopEyes, checks: dict, executable: Path) -> dict:
        """Evidence of PLAY inside the package: deploy from the command surface, confirm the
        gameplay map loaded (packaged log token), then capture frames WHILE holding movement input
        and require a visible motion delta. Fail-closed: blocked input, unloaded map, or static
        frames all fail their checks - a menu screenshot can never satisfy this phase again."""
        gp = dict(plan.get("gameplay") or {})
        gameplay_check_names = ("gameplay_map_loaded", "gameplay_motion_delta", "gameplay_process_identity")
        if not gp.get("enabled", True):
            for name in gameplay_check_names:
                checks[name] = {"passed": False, "issues": ["gameplay smoke disabled for this run"]}
            return {"enabled": False}
        obs: dict = {"enabled": True}
        try:
            from dimwit.desktop_hands import DesktopHands
            hands = DesktopHands(title=str(plan["window_title"]), proc=executable.stem,
                                 deadline_s=float(gp.get("map_load_wait_seconds", 60)) +
                                 float(gp.get("move_seconds", 2.5)) + 120.0)
            obs["session_locked"] = hands.session_locked()
            obs["focus"] = hands.focus_target()
            # focused session -> real SendInput; unfocusable (e.g. locked workstation, foreground
            # denial) -> keys POSTED directly to the game window's message queue, which never leaks
            # input anywhere else. Either way the map-load log token is the arbiter of delivery.
            use_post = not obs["focus"].get("ok")
            obs["input_mode"] = "posted_window_messages" if use_post else "sendinput_foreground"
            deploy = (hands.post_key(str(gp.get("deploy_key", "enter"))) if use_post
                      else hands.press(str(gp.get("deploy_key", "enter"))))
            obs["deploy"] = {k: deploy.get(k) for k in ("go", "mode", "reason")}
            if not deploy.get("go"):
                raise BlockedError(f"deploy input blocked: {deploy.get('reason') or deploy.get('mode')}")
            log_path = (Path(plan["archive_dir"]) / "Windows" / "WanefallGreybox" / "Saved" /
                        "Logs" / "WanefallGreybox.log")
            loaded = self._wait_for_log_token(log_path, str(gp.get("map_token") or ""),
                                              int(gp.get("map_load_wait_seconds", 60)))
            checks["gameplay_map_loaded"] = loaded
            if not loaded.get("passed"):
                checks["gameplay_process_identity"] = {"passed": False, "issues": ["gameplay map never loaded"]}
                checks["gameplay_motion_delta"] = {"passed": False, "issues": ["gameplay map never loaded"]}
                return obs
            time.sleep(3.0)                                     # spawn + camera settle
            still_path = Path(gp["gameplay_still_path"])
            still_path.parent.mkdir(parents=True, exist_ok=True)
            still = eyes.capture_window(str(plan["window_title"]), still_path, proc=executable.stem)
            obs["gameplay_still"] = still
            checks["gameplay_process_identity"] = process_identity_check(
                still, expected_pid=(proc.pid if proc else None), expected_proc=executable.stem)
            fire_key = str(gp.get("fire_key", "f"))
            fire_taps = max(0, int(gp.get("fire_taps", 12)))
            fire_results = []
            for _ in range(fire_taps):
                fired = hands.post_key(fire_key) if use_post else hands.press(fire_key)
                fire_results.append({k: fired.get(k) for k in ("go", "mode", "reason")})
                if not fired.get("go"):
                    break
                time.sleep(max(0.05, float(gp.get("fire_interval_seconds", 0.25))))
            obs["combat_input"] = {
                "key": fire_key,
                "requested_taps": fire_taps,
                "live_taps": sum(1 for item in fire_results if item.get("go")),
                "results": fire_results,
            }
            time.sleep(max(0.0, float(gp.get("combat_settle_seconds", 12.0))))
            frames_dir = Path(gp["gameplay_frames_dir"])
            frames_dir.mkdir(parents=True, exist_ok=True)
            for old in frames_dir.glob("*.png"):
                old.unlink()
            move_key = str(gp.get("move_key", "w"))
            down = hands.post_key_down(move_key) if use_post else hands.key_down(move_key)
            try:
                # per-frame PrintWindow burst, NOT screen-region streaming: region grabs photograph
                # whatever covers those screen coordinates (a covered/locked window yielded 15
                # byte-identical frames); PrintWindow binds to the window regardless of z-order,
                # and its ~1s per-shot latency spaces frames while the move key is held.
                frame_paths = []
                for i in range(int(gp.get("gameplay_frame_count", 6))):
                    frame_path = frames_dir / f"frame_{i:03d}.png"
                    cap = eyes.capture_window(str(plan["window_title"]), frame_path, proc=executable.stem)
                    if cap.get("ok") and frame_path.exists():
                        frame_paths.append(str(frame_path))
                gameplay_burst = {"frames": frame_paths, "count": len(frame_paths),
                                  "tier": "printwindow_burst"}
            finally:
                (hands.post_key_up if use_post else hands.key_up)(move_key)
            obs["move_input"] = {"key": move_key, "went_live": bool(down.get("go"))}
            obs["gameplay_frames"] = gameplay_burst
            frame_paths = [p for p in gameplay_burst.get("frames", []) if Path(p).exists()]
            checks["gameplay_motion_delta"] = frame_motion_delta(
                frame_paths, float(gp.get("motion_threshold", 0.02)))
            if not down.get("go"):
                checks["gameplay_motion_delta"]["passed"] = False
                checks["gameplay_motion_delta"].setdefault("issues", []).append(
                    f"movement input blocked: {down.get('reason') or down.get('mode')} "
                    "(any motion would be unattributable)")
        except Exception as exc:
            for name in gameplay_check_names:
                checks.setdefault(name, {"passed": False, "issues": [f"gameplay smoke error: {exc!r}"]})
            obs["error"] = repr(exc)
        return obs

    def _wait_for_log_token(self, log_path: Path, token: str, timeout_seconds: int) -> dict:
        if not token:
            return {"passed": False, "issues": ["no gameplay map token configured"]}
        deadline = time.time() + max(1, int(timeout_seconds))
        while time.time() < deadline:
            try:
                if log_path.exists() and token in log_path.read_text(encoding="utf-8", errors="replace"):
                    return {"passed": True, "issues": [], "map_token": token, "log": str(log_path)}
            except Exception:
                pass
            time.sleep(2.0)
        return {"passed": False,
                "issues": [f"map token {token!r} not found in packaged log within {timeout_seconds}s"],
                "map_token": token, "log": str(log_path)}

    def _wait_for_window(self, eyes: DesktopEyes, title: str, max_wait_seconds: int) -> dict | None:
        deadline = time.time() + max(0, int(max_wait_seconds))
        while time.time() < deadline:
            window = self._find_window_safe(eyes, title)
            if window:
                return window
            time.sleep(1.0)
        return self._find_window_safe(eyes, title)

    def _find_window_safe(self, eyes: DesktopEyes, title: str) -> dict | None:
        try:
            windows = eyes.list_windows()
        except Exception:
            return None
        title_lower = title.lower()
        matches = [
            window for window in windows
            if title_lower in str(window.get("title") or "").lower()
            and "unreal editor" not in str(window.get("title") or "").lower()
        ]
        if matches:
            return max(matches, key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0))
        return None

    def _terminate_process(self, proc) -> None:
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass

    def _check_frames(self, frame_paths: list[Path]) -> dict:
        if len(frame_paths) < 2:
            return {"passed": False, "issues": [f"packaged frame burst has {len(frame_paths)} frame(s), need at least 2"]}
        analyses = []
        issues = []
        for index, frame_path in enumerate(frame_paths[:2]):
            analysis = analyze_capture(frame_path)
            placeholder = detect_placeholder_geometry(analysis)
            analyses.append(analysis)
            if not analysis.get("passed"):
                issues.extend([f"frame_{index}: {issue}" for issue in analysis.get("issues", [])])
            if not placeholder.get("passed"):
                issues.extend([f"frame_{index}: {issue}" for issue in placeholder.get("issues", [])])
        return {
            "passed": not issues,
            "issues": issues,
            "frame_count": len(frame_paths),
            "sample_metrics": [analysis.get("metrics") for analysis in analyses],
        }

    def _scan_packaged_log(self, archive_dir: Path) -> dict:
        info = _latest_log_text(_packaged_log_dirs(archive_dir))
        if not info["available"]:
            return {"passed": False, "issues": [info["issue"]], "path": info["path"]}
        scan = scan_log_text(info["text"])
        scan["path"] = info["path"]
        scan["issues"] = []
        if not scan["passed"]:
            scan["issues"] = [f"fatal_count={scan['fatal_count']} error_count={scan['error_count']}"]
        return scan

    def _check_package_manifest(self, uat_result: dict, manifest: dict) -> dict:
        issues = []
        if int(uat_result.get("returncode", 1)) != 0:
            issues.append(f"UAT returncode {uat_result.get('returncode')}")
        if not manifest.get("exists"):
            issues.append(f"archive dir missing: {manifest.get('package_dir')}")
        if int(manifest.get("file_count") or 0) < MIN_PACKAGE_FILES:
            issues.append(f"package file_count {manifest.get('file_count')} < {MIN_PACKAGE_FILES}")
        if not (manifest.get("executable") or {}).get("exists"):
            issues.append("packaged executable missing")
        return {"passed": not issues, "issues": issues, "manifest": manifest}

    def _check_executable_hash(self, manifest: dict) -> dict:
        executable = manifest.get("executable") if isinstance(manifest.get("executable"), dict) else {}
        issues = []
        if executable.get("exists") is not True:
            issues.append("executable missing")
        if int(executable.get("bytes") or 0) <= 0:
            issues.append("executable has zero bytes")
        if len(str(executable.get("sha256") or "")) != 64:
            issues.append("executable sha256 missing")
        return {
            "passed": not issues,
            "issues": issues,
            "path": executable.get("path"),
            "bytes": executable.get("bytes"),
            "sha256": executable.get("sha256"),
        }

    def _assemble_result(
        self,
        plan: dict,
        started_at: float,
        uat_result: dict,
        executable: Path | None,
        manifest: dict,
        checks: dict,
        observations: dict,
    ) -> dict:
        # runtime_source is EARNED by the process-identity assertion, never declared: the packaged
        # claim holds only when the captured window provably belonged to the launched packaged exe.
        checks = dict(checks)
        identity = checks.get("process_identity") or {"passed": False,
                                                      "issues": ["process_identity check missing"]}
        identity_ok = bool(identity.get("passed"))
        runtime_source = "packaged_build" if identity_ok else "unverified_window_capture"
        checks["runtime_source"] = {
            "passed": identity_ok,
            "issues": [] if identity_ok else [f"runtime source unverified: {'; '.join(identity.get('issues') or [])}"],
            "runtime_source": runtime_source,
        }
        suite_pass = bool(checks) and all(bool(check.get("passed")) for check in checks.values())
        state = "PASS" if suite_pass else "BLOCKED"
        result = {
            "schema_version": 1,
            "captured_at": time.time(),
            "run_started_at": started_at,
            "state": state,
            "suite_pass": suite_pass,
            "asset_id": plan["asset_id"],
            "runtime_source": runtime_source,
            "configuration": plan["configuration"],
            "platform": plan["platform"],
            "package": {
                "uat_returncode": uat_result.get("returncode"),
                "archive_dir": str(plan["archive_dir"]),
                "executable": str(executable) if executable else None,
                "manifest": manifest,
            },
            "packaging_environment": {
                "build_root": str(plan["build_root"]),
                "package_workspace": str(plan["package_workspace"]),
                "package_run_dir": str(plan["package_run_dir"]),
                "stage_dir": str(plan["stage_dir"]),
                "cook_output_root": str(plan["cook_output_root"]),
                "cook_output_dir": str(plan["cook_output_dir"]),
                "temp_dir": str(plan["temp_dir"]),
                "ddc_dir": str(plan["ddc_dir"]),
                "cooker_options": list(plan["cooker_options"]),
            },
            "checks": checks,
            "observations": observations,
            "artifacts": {
                "still": str(plan["still_path"]) if Path(plan["still_path"]).exists() else None,
                "frames_dir": str(plan["frames_dir"]),
                "uat_stdout": str(plan["uat_stdout"]),
                "uat_stderr": str(plan["uat_stderr"]),
            },
            "result_path": str(plan["result_path"]),
            "manifest_path": str(plan["manifest_path"]),
            "local_report": str(plan["local_report"]),
            "shared_report": str(plan["shared_report"]),
            "operator_only_states_written": [],
        }
        result["freshness"] = _freshness(result, DEFAULT_MAX_AGE_SECONDS)
        return result

    def _score_checks(self, checks: dict) -> float:
        if not checks:
            return 0.0
        passed = sum(1 for check in checks.values() if check.get("passed"))
        return round(passed / len(checks), 4)
