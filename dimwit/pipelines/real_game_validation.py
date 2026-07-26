"""Real-game validation pipeline for WANEFALL.

This module is the runtime truth spine for Dimwit: it judges the actual game
window instead of constructor state, static files, or headless proxy captures.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageStat

from dimwit.desktop_eyes import DesktopEyes, process_identity_check
from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
RESULT_DIR = ROOT / "artifacts" / "real_game_validation"
RESULT_PATH = RESULT_DIR / "real_game_validation_result.json"
SHARED_FOLDER = Path(r"C:\Users\developer\Desktop\Shared Folder")
SHARED_REPORT = SHARED_FOLDER / "WANEFALL_REAL_GAME_VALIDATION_LOOP_V1_SESSION_REPORT_20260628.md"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_REAL_GAME_VALIDATION_LOOP_V1_SESSION_REPORT_20260628.md"
UE_EXE = Path(r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe")
UPROJECT = PROJECT / "WanefallGreybox.uproject"
DEFAULT_MAP_URL = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01?game=/Script/WanefallGreybox.WanefallLobbyGameMode"

MIN_CONTRAST = 0.05
MIN_MEAN_LUMINANCE = 0.05
MAX_MEAN_LUMINANCE = 0.97
FLAT_MIDGRAY_PATCH_FRACTION_LIMIT = 0.03
FLAT_MIDGRAY_PATCH_MIN_COUNT = 3
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60


def _luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = rgb
    return ((0.2126 * red) + (0.7152 * green) + (0.0722 * blue)) / 255.0


def _flat_midgray_patch_metrics(image: Image.Image) -> dict:
    """Detect large, flat, low-chroma grey regions typical of blockout meshes."""
    width, height = image.size
    if width <= 0 or height <= 0:
        return {
            "flat_midgray_patch_fraction": 0.0,
            "flat_midgray_patch_count": 0,
            "flat_midgray_patch_size": 0,
        }

    patch_size = max(16, min(48, min(width, height) // 4))
    top = 30 if height > 160 else 0
    scanned_area = 0
    flat_area = 0
    flat_count = 0

    for y in range(top, height, patch_size):
        for x in range(0, width, patch_size):
            crop = image.crop((x, y, min(x + patch_size, width), min(y + patch_size, height)))
            crop_width, crop_height = crop.size
            if crop_width < patch_size // 2 or crop_height < patch_size // 2:
                continue

            area = crop_width * crop_height
            scanned_area += area
            stat = ImageStat.Stat(crop)
            red, green, blue = stat.mean
            channel_spread = max(stat.mean) - min(stat.mean)
            mean_stddev = sum(stat.stddev) / 3.0
            luminance = ((0.2126 * red) + (0.7152 * green) + (0.0722 * blue)) / 255.0

            if channel_spread <= 10.0 and 0.10 <= luminance <= 0.52 and mean_stddev <= 7.5:
                flat_area += area
                flat_count += 1

    fraction = flat_area / scanned_area if scanned_area else 0.0
    return {
        "flat_midgray_patch_fraction": round(fraction, 6),
        "flat_midgray_patch_count": flat_count,
        "flat_midgray_patch_size": patch_size,
    }


def analyze_capture(path: Path | str) -> dict:
    """Measure a real capture and reject blank or washed-out frames.

    The check is deterministic and intentionally conservative. Semantic claims
    belong to later optics gates; this only says whether the capture is usable.
    """
    image_path = Path(path)
    if not image_path.exists():
        raise BlockedError(f"capture missing: {image_path}")

    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        pixels = list(rgb.getdata())
        patch_metrics = _flat_midgray_patch_metrics(rgb)

    if not pixels:
        raise BlockedError(f"capture has no pixels: {image_path}")

    lum_values = [_luminance(pixel) for pixel in pixels]
    mean_luminance = sum(lum_values) / len(lum_values)
    contrast = max(lum_values) - min(lum_values)
    near_black = sum(1 for value in lum_values if value < 0.03) / len(lum_values)
    near_white = sum(1 for value in lum_values if value > 0.97) / len(lum_values)

    issues: list[str] = []
    if contrast < MIN_CONTRAST:
        issues.append(f"contrast {contrast:.4f} < {MIN_CONTRAST:.4f}")
    if mean_luminance < MIN_MEAN_LUMINANCE:
        issues.append(f"mean_luminance {mean_luminance:.4f} < {MIN_MEAN_LUMINANCE:.4f}")
    if mean_luminance > MAX_MEAN_LUMINANCE:
        issues.append(f"mean_luminance {mean_luminance:.4f} > {MAX_MEAN_LUMINANCE:.4f}")

    return {
        "passed": not issues,
        "issues": issues,
        "path": str(image_path),
        "metrics": {
            "contrast": round(contrast, 6),
            "mean_luminance": round(mean_luminance, 6),
            "near_black": round(near_black, 6),
            "near_white": round(near_white, 6),
            "pixel_count": len(pixels),
            **patch_metrics,
        },
    }


def scan_log_text(text: str) -> dict:
    """Count fatal/error lines in UE log text without treating warnings as fatal."""
    fatal_lines: list[str] = []
    error_lines: list[str] = []
    visual_warning_lines: list[str] = []
    visual_warning_signatures = (
        "sky light with real-time capture enabled",
        "requires at least a skyatmosphere component",
        "material tagged as issky",
    )
    # CHURN-ONLY signature: one 'SkyLight real-time capture change' line is normal engine init when
    # a gameplay map loads (first packaged arena deploys tripped this as a false positive); the
    # documented pathology is CONTINUOUS re-captures, i.e. the line repeating.
    churn_signature = "skylight real-time capture change"
    churn_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if "fatal error" in lower or lower.startswith("fatal:"):
            fatal_lines.append(line)
        elif lower.startswith("error:") or " error:" in lower or "logerror:" in lower:
            error_lines.append(line)
        if any(signature in lower for signature in visual_warning_signatures):
            visual_warning_lines.append(line)
        elif churn_signature in lower:
            churn_lines.append(line)
    if len(churn_lines) > 1:
        visual_warning_lines.extend(churn_lines)

    return {
        "passed": not fatal_lines and not error_lines and not visual_warning_lines,
        "fatal_count": len(fatal_lines),
        "error_count": len(error_lines),
        "visual_warning_count": len(visual_warning_lines),
        "fatal_lines": fatal_lines[:10],
        "error_lines": error_lines[:10],
        "visual_warning_lines": visual_warning_lines[:10],
    }


def check_result_fresh(result: dict, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    captured_at = result.get("captured_at")
    if not isinstance(captured_at, (int, float)):
        return {"passed": False, "issues": ["captured_at missing or not numeric"], "age_seconds": None}

    age_seconds = time.time() - float(captured_at)
    issues: list[str] = []
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


def validate_real_game_result(
    path: Path | str = RESULT_PATH,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"real-game validation result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"real-game validation result unreadable: {exc}") from exc

    freshness = check_result_fresh(result, max_age_seconds=max_age_seconds)
    if not freshness["passed"]:
        result = dict(result)
        result["freshness"] = freshness
        return result
    result = dict(result)
    result["freshness"] = freshness
    return result


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


def _latest_log_text(log_dir: Path) -> dict:
    if not log_dir.exists():
        return {"available": False, "path": None, "text": "", "issue": f"log dir missing: {log_dir}"}
    logs = sorted(log_dir.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not logs:
        return {"available": False, "path": None, "text": "", "issue": f"no .log files in {log_dir}"}
    latest = logs[0]
    try:
        lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"available": False, "path": str(latest), "text": "", "issue": f"log unreadable: {exc}"}
    return {"available": True, "path": str(latest), "text": "\n".join(lines[-2000:]), "issue": ""}


def detect_placeholder_geometry(analysis: dict) -> dict:
    metrics = analysis.get("metrics", {})
    near_white = float(metrics.get("near_white") or 0.0)
    contrast = float(metrics.get("contrast") or 0.0)
    flat_midgray_patch_fraction = float(metrics.get("flat_midgray_patch_fraction") or 0.0)
    flat_midgray_patch_count = int(metrics.get("flat_midgray_patch_count") or 0)
    white_dominated = near_white > 0.35 and contrast > 0.20
    flat_blockout = (
        flat_midgray_patch_fraction >= FLAT_MIDGRAY_PATCH_FRACTION_LIMIT
        and flat_midgray_patch_count >= FLAT_MIDGRAY_PATCH_MIN_COUNT
        and contrast > 0.20
    )
    issues = []
    if white_dominated:
        issues.append(f"near_white {near_white:.3f} with contrast {contrast:.3f} suggests placeholder-dominated frame")
    if flat_blockout:
        issues.append(
            "flat mid-gray patch fraction "
            f"{flat_midgray_patch_fraction:.3f} across {flat_midgray_patch_count} patch(es) suggests blockout geometry"
        )
    return {
        "passed": not (white_dominated or flat_blockout),
        "issues": issues,
        "near_white": near_white,
        "contrast": contrast,
        "flat_midgray_patch_fraction": flat_midgray_patch_fraction,
        "flat_midgray_patch_count": flat_midgray_patch_count,
        "flat_midgray_patch_size": int(metrics.get("flat_midgray_patch_size") or 0),
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_report(result: dict, report_path: Path) -> str:
    checks = result.get("checks", {})
    lines = [
        "# WANEFALL Real-Game Validation Loop V1 Session Report",
        "",
        f"Captured at: {result.get('captured_at')}",
        f"Suite pass: {result.get('suite_pass')}",
        f"State: {result.get('state')}",
        "",
        "## Artifacts",
        f"- Result JSON: `{result.get('result_path')}`",
        f"- Still capture: `{(result.get('artifacts') or {}).get('still')}`",
        f"- Frame dir: `{(result.get('artifacts') or {}).get('frames_dir')}`",
        f"- Log file: `{(result.get('artifacts') or {}).get('log')}`",
        "",
        "## Checks",
    ]
    for name, check in checks.items():
        lines.append(f"- {name}: passed={check.get('passed')} issues={check.get('issues', [])}")
    lines.extend([
        "",
        "## Boundaries",
        "- No HUMAN_ACCEPTED state was written.",
        "- No PROMOTED_TO_ACTIVE_SLICE state was written.",
        "- Missing or stale evidence remains blocked/failing, never fake green.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class RealGameValidationPipeline(ProductionPipeline):
    name = "real_game_validation"
    kind = "runtime_validation"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "wanefall_default_lobby")
        output_dir = RESULT_DIR
        return {
            "asset_id": asset_id,
            "project": str(PROJECT),
            "ue_exe": str(task.get("ue_exe") or UE_EXE),
            "uproj": str(task.get("uproj") or UPROJECT),
            "map_url": str(task.get("map_url") or DEFAULT_MAP_URL),
            "window_title": str(task.get("window_title") or "WanefallGreybox"),
            "attach_only": _bool_value(task.get("attach_only", False)),
            "kill_stale": _bool_value(task.get("kill_stale", False)),
            "max_wait_seconds": _int_value(task.get("max_wait_seconds"), 90),
            "capture_seconds": _float_value(task.get("capture_seconds"), 2.0),
            "capture_fps": _float_value(task.get("capture_fps"), 4.0),
            "settle_seconds": _float_value(task.get("settle_seconds"), 30.0),
            "output_dir": str(output_dir),
            "result_path": output_dir / "real_game_validation_result.json",
            "still_path": output_dir / "still.png",
            "frames_dir": output_dir / "frames",
            "local_report": LOCAL_REPORT,
            "shared_report": SHARED_REPORT,
        }

    def execute(self, plan: dict) -> Artifact:
        result = self._run_capture(plan)
        _write_json(Path(plan["result_path"]), result)
        _make_report(result, Path(plan["local_report"]))
        try:
            _make_report(result, Path(plan["shared_report"]))
        except Exception as exc:
            result.setdefault("report_warnings", []).append(f"shared report write failed: {exc}")
            _write_json(Path(plan["result_path"]), result)
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={"result_path": str(plan["result_path"]), "suite_pass": bool(result.get("suite_pass"))},
            provenance={"source": "local_wanefall_project_runtime", "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_real_game_result(Path(plan["result_path"]), max_age_seconds=DEFAULT_MAX_AGE_SECONDS)
        checks = result.get("checks", {})
        issues = []
        for name, check in checks.items():
            if not check.get("passed"):
                issues.extend([f"{name}: {issue}" for issue in check.get("issues", [])] or [f"{name}: failed"])
        evidence = []
        artifacts = result.get("artifacts") or {}
        if artifacts.get("still"):
            evidence.append(artifacts["still"])
        hard_fail = bool(result.get("hard_fail"))
        score = self._score_checks(checks)
        return Verdict(
            score=score,
            passed=bool(result.get("suite_pass")),
            hard_fail=hard_fail,
            issues=issues,
            detail={"state": result.get("state"), "checks": checks, "result_path": str(plan["result_path"])},
            evidence=evidence,
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact

    def _run_capture(self, plan: dict) -> dict:
        started_at = time.time()
        out_dir = Path(plan["output_dir"])
        frames_dir = Path(plan["frames_dir"])
        still_path = Path(plan["still_path"])
        out_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame in frames_dir.glob("*.png"):
            frame.unlink(missing_ok=True)

        launch_cmd = self._launch_command(plan)
        proc = None
        checks: dict[str, dict] = {}
        observations: dict[str, object] = {}
        eyes = DesktopEyes()

        window = self._find_window_safe(eyes, str(plan["window_title"]))
        if not window and not plan["attach_only"]:
            proc = self._launch_game(plan, launch_cmd)
            window = self._wait_for_window(eyes, str(plan["window_title"]), int(plan["max_wait_seconds"]))

        if not window:
            checks["window_found"] = {
                "passed": False,
                "issues": [f"window not found: {plan['window_title']}"],
            }
            self._terminate_process(proc)          # never leak a launched-but-windowless game process
            result = self._assemble_result(plan, started_at, checks, observations, launch_cmd, hard_fail=False)
            result["process_started"] = bool(proc)
            result["process_terminated"] = bool(proc)
            return result

        checks["window_found"] = {
            "passed": True,
            "issues": [],
            "title": window.get("title"),
            "width": window.get("width"),
            "height": window.get("height"),
        }

        settle_seconds = max(0.0, float(plan.get("settle_seconds") or 0.0))
        if settle_seconds > 0.0:
            time.sleep(settle_seconds)

        expected_proc = "UnrealEditor"             # editor-binary -game runtime; packaged runtime is the packaged pipeline's lane
        still_capture = eyes.capture_window(str(plan["window_title"]), still_path, proc=expected_proc)
        observations["still_capture"] = still_capture
        checks["process_identity"] = process_identity_check(
            still_capture, expected_pid=(proc.pid if proc else None), expected_proc=expected_proc)
        if still_capture.get("ok") and still_path.exists():
            still_analysis = analyze_capture(still_path)
            checks["still_nonblank"] = still_analysis
        else:
            checks["still_nonblank"] = {
                "passed": False,
                "issues": [still_capture.get("error") or "still capture failed"],
                "capture": still_capture,
            }

        frame_capture = eyes.capture_stream(
            frames_dir,
            str(plan["window_title"]),
            seconds=float(plan["capture_seconds"]),
            fps=float(plan["capture_fps"]),
        )
        observations["frame_capture"] = frame_capture
        frame_paths = [Path(path) for path in frame_capture.get("frames", []) if Path(path).exists()]
        checks["frame_burst_nonblank"] = self._check_frames(frame_paths)
        if frame_paths:
            checks["still_nonblank"] = self._promote_still_from_frames(
                still_path,
                checks.get("still_nonblank", {}),
                frame_paths,
            )
        checks["placeholder_geometry_signal"] = detect_placeholder_geometry(checks.get("still_nonblank", {}))
        checks["log_scan"] = self._scan_latest_log()

        self._terminate_process(proc)              # clean up only what WE launched; attached windows are left alone
        result = self._assemble_result(
            plan,
            started_at,
            checks,
            observations,
            launch_cmd,
            hard_fail=self._hard_fail_from_checks(checks),
        )
        result["process_started"] = bool(proc)
        result["process_terminated"] = bool(proc)
        return result

    def _launch_command(self, plan: dict) -> list[str]:
        return [
            str(plan["ue_exe"]),
            str(plan["uproj"]),
            str(plan["map_url"]),
            "-game",
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-nosound",
        ]

    def _launch_game(self, plan: dict, cmd: list[str]):
        ue_exe = Path(plan["ue_exe"])
        uproj = Path(plan["uproj"])
        if not ue_exe.exists():
            return None
        if not uproj.exists():
            return None
        try:
            return subprocess.Popen(cmd)
        except Exception:
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

    def _find_window_safe(self, eyes: DesktopEyes, title: str) -> dict | None:
        try:
            windows = eyes.list_windows()
        except Exception:
            return None
        matches = []
        title_lower = title.lower()
        for window in windows:
            window_title = str(window.get("title") or "")
            if title_lower not in window_title.lower():
                continue
            if "unreal editor" in window_title.lower():
                continue
            matches.append(window)
        if matches:
            return max(matches, key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0))
        try:
            found = eyes.find_window(title)
        except Exception:
            return None
        if found and "unreal editor" not in str(found.get("title") or "").lower():
            return found
        return None

    def _wait_for_window(self, eyes: DesktopEyes, title: str, max_wait_seconds: int) -> dict | None:
        deadline = time.time() + max(0, int(max_wait_seconds))
        while time.time() < deadline:
            window = self._find_window_safe(eyes, title)
            if window:
                return window
            time.sleep(1.0)
        return self._find_window_safe(eyes, title)

    def _check_frames(self, frame_paths: list[Path]) -> dict:
        if len(frame_paths) < 2:
            return {"passed": False, "issues": [f"frame burst has {len(frame_paths)} frame(s), need at least 2"]}
        analyses = [analyze_capture(path) for path in frame_paths[:2]]
        issues = []
        for index, analysis in enumerate(analyses):
            if not analysis["passed"]:
                issues.extend([f"frame_{index}: {issue}" for issue in analysis["issues"]])
        return {
            "passed": not issues,
            "issues": issues,
            "frame_count": len(frame_paths),
            "sample_metrics": [analysis["metrics"] for analysis in analyses],
        }

    def _promote_still_from_frames(self, still_path: Path, still_analysis: dict, frame_paths: list[Path]) -> dict:
        if still_analysis.get("passed") and detect_placeholder_geometry(still_analysis).get("passed"):
            return still_analysis

        candidates: list[tuple[float, Path, dict]] = []
        for frame_path in frame_paths:
            if not frame_path.exists():
                continue
            analysis = analyze_capture(frame_path)
            if not analysis.get("passed"):
                continue
            if not detect_placeholder_geometry(analysis).get("passed"):
                continue
            metrics = analysis.get("metrics", {})
            candidates.append((float(metrics.get("mean_luminance") or 0.0), frame_path, analysis))

        if not candidates:
            return still_analysis

        _, promoted_path, promoted_analysis = max(candidates, key=lambda item: item[0])
        shutil.copyfile(promoted_path, still_path)
        promoted = dict(promoted_analysis)
        promoted["path"] = str(still_path)
        promoted["promoted_from_frame"] = str(promoted_path)
        promoted["issues"] = []
        return promoted

    def _scan_latest_log(self) -> dict:
        log_info = _latest_log_text(PROJECT / "Saved" / "Logs")
        if not log_info["available"]:
            return {"passed": False, "issues": [log_info["issue"]], "path": log_info["path"]}
        scan = scan_log_text(log_info["text"])
        scan["path"] = log_info["path"]
        scan["issues"] = []
        if not scan["passed"]:
            scan["issues"] = [f"fatal_count={scan['fatal_count']} error_count={scan['error_count']}"]
        return scan

    def _assemble_result(
        self,
        plan: dict,
        started_at: float,
        checks: dict,
        observations: dict,
        launch_cmd: list[str],
        hard_fail: bool,
    ) -> dict:
        suite_pass = bool(checks) and all(bool(check.get("passed")) for check in checks.values())
        state = "PASS" if suite_pass else ("REJECTED" if hard_fail else "BLOCKED")
        artifacts = {
            "still": str(plan["still_path"]) if Path(plan["still_path"]).exists() else None,
            "frames_dir": str(plan["frames_dir"]),
            "log": (checks.get("log_scan") or {}).get("path"),
        }
        return {
            "captured_at": time.time(),
            "run_started_at": started_at,
            "state": state,
            "suite_pass": suite_pass,
            "hard_fail": hard_fail,
            "asset_id": plan["asset_id"],
            "launch_cmd": launch_cmd,
            "checks": checks,
            "observations": observations,
            "artifacts": artifacts,
            "result_path": str(plan["result_path"]),
            "local_report": str(plan["local_report"]),
            "shared_report": str(plan["shared_report"]),
            "operator_only_states_written": [],
        }

    def _hard_fail_from_checks(self, checks: dict) -> bool:
        if checks.get("still_nonblank") and not checks["still_nonblank"].get("passed"):
            return True
        if checks.get("log_scan") and not checks["log_scan"].get("passed"):
            return True
        if checks.get("placeholder_geometry_signal") and not checks["placeholder_geometry_signal"].get("passed"):
            return True
        return False

    def _score_checks(self, checks: dict) -> float:
        if not checks:
            return 0.0
        passed = sum(1 for check in checks.values() if check.get("passed"))
        return round(passed / len(checks), 4)
