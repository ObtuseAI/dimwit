"""PERFORMANCE_BASELINE_GATES_V1 — packaged performance capture + fail-closed floor gates.

Masterplan Horizon 1, bundle 4 (§B7 / audit bundle 8). WANEFALL performance was UNMEASURED
(score 2/10). This lane machine-plays the real packaged `WanefallGreybox.exe` — command deck
(menu segment) then ENTER-deploy into the Arena4v4 bot TDM (arena segment) — while the
flag-gated in-game `UWanefallPerfProofSubsystem` (-WANEFALLPERFPROOF) samples wall frametime
per frame and memory, and flushes identity-bound JSON evidence into the package's Saved tree.

Laws honored:
- Law 5: packaged proof is the only proof — the evidence must come from the archived package,
  exe-sha-bound to the current package manifest.
- Law 3: captures are pid-bound PrintWindow; runtime_source is EARNED by process identity.
- Law 7: input via posted window messages when the session is unfocusable.
- One-variable law: measurement conditions (vsync off, t.MaxFPS 0, smoothing off, 1920x1080)
  are pinned by the subsystem and RECORDED — a capped/smoothed capture fails its gate.
- Recomputation law: floor checks are recomputed at validation time from the embedded perf
  payload (a stored `passed: true` can never rubber-stamp), and the reported arena p95 is
  cross-checked against the downsampled steady trace.

Floors are ratchet-only: they may tighten, never loosen (test_thresholds_are_masterplan_floors).
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

from dimwit.desktop_eyes import DesktopEyes, process_identity_check
from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.packaged_build_validation import (
    DEFAULT_MAP_URL,
    MANIFEST_PATH as PACKAGED_MANIFEST_PATH,
    RESULT_PATH as PACKAGED_RESULT_PATH,
    _freshness,
    _latest_log_text,
    _packaged_log_dirs,
)
from dimwit.pipelines.real_game_validation import scan_log_text


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "artifacts" / "performance_baseline"
RESULT_PATH = RESULT_DIR / "performance_baseline_result.json"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_PERFORMANCE_BASELINE_REPORT.md"

# The two proof surfaces (masterplan B7): command deck + flagship arena bot TDM.
MENU_MAP = "Wanefall_ModeShell_Prototype_01"
ARENA_MAP = "Wanefall_Arena4v4_Prototype_01"

# ---- FLOORS (BLOCKER thresholds). RATCHET-ONLY: tighten allowed, loosening breaks the ratchet
# test and violates doctrine. 16.6 ms = 60 fps p95 proxy min-spec @1080p per the masterplan.
ARENA_P95_FLOOR_MS = 16.6
MENU_P95_FLOOR_MS = 16.6
HITCH_MS = 100.0
SEVERE_HITCH_MS = 250.0
MEMORY_PEAK_BUDGET_MB = 8192.0
MIN_ARENA_STEADY_SECONDS = 30.0
MIN_ARENA_STEADY_FRAMES = 1000
MIN_MENU_STEADY_SECONDS = 8.0
MIN_MENU_STEADY_FRAMES = 200
# warmup bounds: too small lets map-load spikes pollute steady (fails toward red — safe), too
# large could trim away a genuinely bad early window (fails toward green — forbidden).
WARMUP_MIN_SECONDS = 3.0
WARMUP_MAX_SECONDS = 10.0
MIN_TRACE_POINTS = 100
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60

PERF_FLAG = "WANEFALLPERFPROOF"
PERF_JSON_RELATIVE = Path("ShowMeAI") / "WanefallPerfProof" / "perf_proof_result.json"
PERF_CSV_RELATIVE = Path("ShowMeAI") / "WanefallPerfProof" / "csv"

FLOOR_CHECK_NAMES = (
    "measurement_conditions",
    "segment_coverage",
    "arena_frametime_floor",
    "arena_hitch_free",
    "menu_frametime_floor",
    "memory_budget",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _num(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _percentile(values: list[float], pct: float) -> float | None:
    finite = sorted(v for v in (_num(v) for v in values) if v is not None)
    if not finite:
        return None
    index = max(0, min(len(finite) - 1, math.ceil(pct / 100.0 * len(finite)) - 1))
    return finite[index]


def _pick_segment(perf: dict, map_name: str) -> dict | None:
    segments = perf.get("segments") if isinstance(perf.get("segments"), list) else []
    candidates = [
        seg for seg in segments
        if isinstance(seg, dict) and str(seg.get("map") or "") == map_name
    ]
    if not candidates:
        return None
    def steady_frames(seg: dict) -> float:
        steady = seg.get("steady") if isinstance(seg.get("steady"), dict) else {}
        return _num(steady.get("frames")) or 0.0
    return max(candidates, key=steady_frames)


def _steady(seg: dict | None) -> dict:
    if not isinstance(seg, dict):
        return {}
    steady = seg.get("steady")
    return steady if isinstance(steady, dict) else {}


def _frametime_floor_check(perf: dict, map_name: str, floor_ms: float, label: str) -> dict:
    seg = _pick_segment(perf, map_name)
    steady = _steady(seg)
    issues: list[str] = []
    p95 = _num(steady.get("p95_ms"))
    if seg is None:
        issues.append(f"{label}: no segment for map {map_name!r}")
    elif p95 is None:
        issues.append(f"{label}: steady p95_ms missing/non-numeric")
    else:
        if p95 > floor_ms:
            issues.append(f"{label}: steady p95 {p95:.2f}ms > floor {floor_ms}ms")
        # anti-fabrication cross-check: the reported headline must agree with the raw
        # downsampled steady trace shipped in the same evidence.
        trace = seg.get("steady_trace_ms") if isinstance(seg.get("steady_trace_ms"), list) else []
        trace_p95 = _percentile(trace, 95.0) if len(trace) >= MIN_TRACE_POINTS else None
        if trace_p95 is None:
            issues.append(
                f"{label}: steady trace missing or <{MIN_TRACE_POINTS} points — headline p95 unverifiable")
        else:
            tolerance = max(3.0, 0.5 * p95)
            if abs(trace_p95 - p95) > tolerance:
                issues.append(
                    f"{label}: reported p95 {p95:.2f}ms diverges from trace p95 "
                    f"{trace_p95:.2f}ms (tolerance {tolerance:.2f}ms) — fabricated headline")
    return {
        "passed": not issues,
        "issues": issues,
        "map": map_name,
        "floor_ms": floor_ms,
        "p95_ms": p95,
        "steady": {k: steady.get(k) for k in ("frames", "seconds", "avg_ms", "p50_ms", "p95_ms",
                                              "p99_ms", "max_ms", "fps_avg")},
    }


def compute_floor_checks(perf: dict) -> dict:
    """Recompute every floor gate from the raw perf payload. Pure + fail-closed: an empty or
    partial payload fails every check; stored check objects are never trusted."""
    perf = perf if isinstance(perf, dict) else {}
    checks: dict[str, dict] = {}

    # measurement conditions — the capture is only comparable if uncapped + unsmoothed @1080p
    measurement = perf.get("measurement") if isinstance(perf.get("measurement"), dict) else {}
    issues = []
    if _num(measurement.get("vsync")) != 0.0:
        issues.append(f"vsync must be 0, got {measurement.get('vsync')!r}")
    if _num(measurement.get("t_max_fps")) != 0.0:
        issues.append(f"t.MaxFPS must be 0 (uncapped), got {measurement.get('t_max_fps')!r}")
    if measurement.get("smooth_framerate_disabled") is not True:
        issues.append("frame-rate smoothing not disabled")
    if measurement.get("fixed_framerate_disabled") is not True:
        issues.append("fixed frame rate not disabled")
    if _num(measurement.get("resolution_x")) != 1920.0 or _num(measurement.get("resolution_y")) != 1080.0:
        issues.append(
            f"resolution must be 1920x1080, got "
            f"{measurement.get('resolution_x')!r}x{measurement.get('resolution_y')!r}")
    warmup = _num(measurement.get("warmup_seconds"))
    if warmup is None or not (WARMUP_MIN_SECONDS <= warmup <= WARMUP_MAX_SECONDS):
        issues.append(
            f"warmup_seconds must be within [{WARMUP_MIN_SECONDS}, {WARMUP_MAX_SECONDS}], "
            f"got {measurement.get('warmup_seconds')!r}")
    hitch_ms = _num(measurement.get("hitch_ms"))
    severe_ms = _num(measurement.get("severe_hitch_ms"))
    if hitch_ms is None or hitch_ms > HITCH_MS:
        issues.append(f"hitch threshold must be <= {HITCH_MS}ms, got {measurement.get('hitch_ms')!r}")
    if severe_ms is None or severe_ms > SEVERE_HITCH_MS:
        issues.append(
            f"severe hitch threshold must be <= {SEVERE_HITCH_MS}ms, got {measurement.get('severe_hitch_ms')!r}")
    checks["measurement_conditions"] = {"passed": not issues, "issues": issues,
                                        "measurement": measurement}

    # segment coverage — a too-short capture can't speak for steady-state performance
    menu_seg = _pick_segment(perf, MENU_MAP)
    arena_seg = _pick_segment(perf, ARENA_MAP)
    issues = []
    for label, seg, min_seconds, min_frames in (
        ("menu", menu_seg, MIN_MENU_STEADY_SECONDS, MIN_MENU_STEADY_FRAMES),
        ("arena", arena_seg, MIN_ARENA_STEADY_SECONDS, MIN_ARENA_STEADY_FRAMES),
    ):
        steady = _steady(seg)
        seconds = _num(steady.get("seconds"))
        frames = _num(steady.get("frames"))
        if seg is None:
            issues.append(f"{label} segment missing")
        else:
            if seconds is None or seconds < min_seconds:
                issues.append(f"{label} steady window {seconds!r}s < {min_seconds}s")
            if frames is None or frames < min_frames:
                issues.append(f"{label} steady frames {frames!r} < {min_frames}")
    checks["segment_coverage"] = {
        "passed": not issues,
        "issues": issues,
        "menu_steady": _steady(menu_seg),
        "arena_steady": _steady(arena_seg),
    }

    checks["arena_frametime_floor"] = _frametime_floor_check(perf, ARENA_MAP, ARENA_P95_FLOOR_MS, "arena")
    checks["menu_frametime_floor"] = _frametime_floor_check(perf, MENU_MAP, MENU_P95_FLOOR_MS, "menu")

    # hitch gate — masterplan: hitch count 0 in the steady arena window
    steady = _steady(arena_seg)
    issues = []
    hitches = _num(steady.get("hitch_count"))
    severe = _num(steady.get("severe_hitch_count"))
    if arena_seg is None:
        issues.append(f"no segment for map {ARENA_MAP!r}")
    else:
        if hitches is None:
            issues.append("steady hitch_count missing")
        elif hitches > 0:
            issues.append(f"{int(hitches)} steady frame(s) over {HITCH_MS}ms (hitch count must be 0)")
        if severe is None:
            issues.append("steady severe_hitch_count missing")
        elif severe > 0:
            issues.append(f"{int(severe)} steady frame(s) over {SEVERE_HITCH_MS}ms")
    checks["arena_hitch_free"] = {"passed": not issues, "issues": issues,
                                  "hitch_count": hitches, "severe_hitch_count": severe,
                                  "hitch_ms": HITCH_MS, "severe_hitch_ms": SEVERE_HITCH_MS}

    # memory budget — peak process used-physical across the whole session
    memory = perf.get("memory") if isinstance(perf.get("memory"), dict) else {}
    peak = _num(memory.get("peak_used_physical_mb"))
    issues = []
    if peak is None or peak <= 0:
        issues.append(f"peak_used_physical_mb missing/invalid: {memory.get('peak_used_physical_mb')!r}")
    elif peak > MEMORY_PEAK_BUDGET_MB:
        issues.append(f"peak used physical {peak:.0f}MB > budget {MEMORY_PEAK_BUDGET_MB:.0f}MB")
    checks["memory_budget"] = {"passed": not issues, "issues": issues,
                               "peak_used_physical_mb": peak,
                               "budget_mb": MEMORY_PEAK_BUDGET_MB,
                               "avg_used_physical_mb": _num(memory.get("avg_used_physical_mb"))}
    return checks


def _recompute_evidence_binding(result: dict) -> dict:
    """Perf payload must be pid-bound to the launched process and exe-sha-bound to the current
    package manifest. Recomputed here so a tampered stored check can't survive."""
    issues = []
    perf = result.get("perf")
    if not isinstance(perf, dict):
        return {"passed": False, "issues": ["perf payload missing from result"], "pid": None}
    if str(perf.get("flag") or "") != PERF_FLAG:
        issues.append(f"perf payload flag {perf.get('flag')!r} != {PERF_FLAG!r}")
    launched_pid = result.get("launched_pid")
    perf_pid = perf.get("pid")
    if not isinstance(launched_pid, int) or not isinstance(perf_pid, int) or perf_pid != launched_pid:
        issues.append(f"perf pid {perf_pid!r} does not match launched pid {launched_pid!r}")
    binding = result.get("package_binding") if isinstance(result.get("package_binding"), dict) else {}
    if binding.get("matches") is not True:
        issues.append("package binding not verified (matches != True)")
    manifest_sha = str(binding.get("manifest_sha256") or "")
    run_sha = str(binding.get("exe_sha256_at_run") or "")
    if len(manifest_sha) != 64 or manifest_sha != run_sha:
        issues.append("executable sha256 at run does not match package manifest sha256")
    archive_dir = str(binding.get("archive_dir") or "")
    executable = str(perf.get("executable") or "")
    if not archive_dir or not executable:
        issues.append("archive_dir/executable missing from binding evidence")
    elif Path(archive_dir.lower()) not in Path(executable.lower()).parents:
        issues.append(f"perf executable {executable!r} is not inside archive dir {archive_dir!r}")
    return {"passed": not issues, "issues": issues, "pid": perf_pid,
            "executable": executable or None, "archive_dir": archive_dir or None,
            "exe_sha_matches_manifest": not issues}


def validate_performance_baseline_result(
    path: Path | str = RESULT_PATH,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"performance-baseline result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"performance-baseline result unreadable: {exc}") from exc
    if not isinstance(result, dict):
        raise BlockedError(f"performance-baseline result root is not an object: {result_path}")

    result = dict(result)
    checks = dict(result.get("checks") or {})
    checks["freshness"] = _freshness(result, max_age_seconds=max_age_seconds)

    # recomputation law: floors + evidence binding are derived from the payload every time
    perf = result.get("perf") if isinstance(result.get("perf"), dict) else {}
    checks.update(compute_floor_checks(perf))
    checks["perf_evidence_present"] = _recompute_evidence_binding(result)

    for required in ("window_found", "process_identity", "packaged_log_scan"):
        if required not in checks:
            checks[required] = {"passed": False, "issues": [f"missing check: {required}"]}

    identity = checks.get("process_identity") or {}
    identity_ok = bool(identity.get("passed"))
    runtime_source = "packaged_build" if identity_ok else "unverified_window_capture"
    checks["runtime_source"] = {
        "passed": identity_ok,
        "issues": [] if identity_ok else
        [f"runtime source unverified: {'; '.join(identity.get('issues') or [])}"],
        "runtime_source": runtime_source,
    }
    result["runtime_source"] = runtime_source

    result["checks"] = checks
    result["suite_pass"] = bool(checks) and all(bool(check.get("passed")) for check in checks.values())
    result["state"] = "PASS" if result["suite_pass"] else "BLOCKED"
    return result


def _make_report(result: dict, report_path: Path) -> str:
    checks = result.get("checks") or {}
    perf = result.get("perf") or {}
    lines = [
        "# WANEFALL Performance Baseline Report (PERFORMANCE_BASELINE_GATES_V1)",
        "",
        f"State: {result.get('state')}",
        f"Suite pass: {result.get('suite_pass')}",
        f"Runtime source: {result.get('runtime_source')}",
        f"Launched pid: {result.get('launched_pid')}",
        f"Executable: `{(perf or {}).get('executable')}`",
        "",
        "## Segments",
    ]
    for seg in (perf.get("segments") or []):
        steady = seg.get("steady") or {}
        lines.append(
            f"- `{seg.get('map')}` steady: {steady.get('frames')} frames / "
            f"{steady.get('seconds')}s, avg {steady.get('avg_ms')}ms, p95 {steady.get('p95_ms')}ms, "
            f"p99 {steady.get('p99_ms')}ms, max {steady.get('max_ms')}ms, fps {steady.get('fps_avg')}, "
            f"hitches>{HITCH_MS:.0f}ms: {steady.get('hitch_count')}")
        for hitch in (seg.get("steady_hitch_events") or []):
            lines.append(
                f"    - hitch {hitch.get('ms'):.1f}ms at +{hitch.get('at_segment_seconds'):.1f}s "
                f"into the segment")
    memory = perf.get("memory") or {}
    lines.extend([
        "",
        f"Memory: peak {memory.get('peak_used_physical_mb')} MB / "
        f"avg {memory.get('avg_used_physical_mb')} MB (budget {MEMORY_PEAK_BUDGET_MB:.0f} MB)",
        "",
        "## Checks",
    ])
    for name, check in checks.items():
        lines.append(f"- {name}: passed={check.get('passed')} issues={check.get('issues', [])}")
    lines.extend([
        "",
        "## Boundaries",
        "- Floors are ratchet-only; this report never weakens a gate.",
        "- No HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE state was written.",
        "- Missing/unbound perf evidence stays BLOCKED, never fake green.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class PerformanceBaselinePipeline(ProductionPipeline):
    name = "performance_baseline"
    kind = "performance_baseline"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "wanefall_win64_development_perf")
        output_dir = Path(task.get("output_dir") or RESULT_DIR)
        map_url = str(task.get("map_url") or DEFAULT_MAP_URL)
        launch_args = [
            map_url,
            "-windowed",
            "-ResX=1920",
            "-ResY=1080",
            "-nosound",
            f"-{PERF_FLAG}",
        ]
        return {
            "asset_id": asset_id,
            "output_dir": output_dir,
            "result_path": output_dir / "performance_baseline_result.json",
            "perf_copy_path": output_dir / "perf_proof_result.json",
            "csv_copy_dir": output_dir / "csv",
            "still_path": output_dir / "still.png",
            "local_report": output_dir / LOCAL_REPORT.name,
            "packaged_result_path": Path(task.get("packaged_result_path") or PACKAGED_RESULT_PATH),
            "packaged_manifest_path": Path(task.get("packaged_manifest_path") or PACKAGED_MANIFEST_PATH),
            "archive_dir": task.get("archive_dir"),          # optional override; default from packaged result
            "map_url": map_url,
            "launch_args": launch_args,
            "window_title": str(task.get("window_title") or "WanefallGreybox"),
            "max_wait_seconds": int(task.get("max_wait_seconds") or 120),
            "menu_dwell_seconds": float(task.get("menu_dwell_seconds") or 25.0),
            "deploy_key": str(task.get("deploy_key") or "enter"),
            "arena_map_token": str(task.get("arena_map_token") or ARENA_MAP),
            "map_load_wait_seconds": int(task.get("map_load_wait_seconds") or 60),
            "arena_perf_seconds": float(task.get("arena_perf_seconds") or 100.0),
            "move_key": str(task.get("move_key") or "w"),
            "move_pulse_seconds": float(task.get("move_pulse_seconds") or 3.0),
            "move_pulse_every_seconds": float(task.get("move_pulse_every_seconds") or 20.0),
            # the machine PLAYER also shoots (keyboard Fire binding): muzzle/impact [WaneFX]
            # markers are player-path evidence — bots use their own attack component
            "fire_key": str(task.get("fire_key") or "f"),
            "fire_taps_per_pulse": int(task.get("fire_taps_per_pulse") or 4),
            "perf_poll_extra_seconds": float(task.get("perf_poll_extra_seconds") or 60.0),
        }

    # ------------------------------------------------------------------ execution

    def execute(self, plan: dict) -> Artifact:
        result = self._run_perf_session(plan)
        _write_json(Path(plan["result_path"]), result)
        _make_report(result, Path(plan["local_report"]))
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={
                "result_path": str(plan["result_path"]),
                "suite_pass": bool(result.get("suite_pass")),
                "arena_p95_ms": ((result.get("checks") or {}).get("arena_frametime_floor") or {}).get("p95_ms"),
            },
            provenance={"source": "local_wanefall_packaged_perf_capture", "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_performance_baseline_result(Path(plan["result_path"]),
                                                      max_age_seconds=DEFAULT_MAX_AGE_SECONDS)
        issues = []
        for name, check in (result.get("checks") or {}).items():
            if not check.get("passed"):
                issues.extend([f"{name}: {issue}" for issue in check.get("issues", [])] or [f"{name}: failed"])
        return Verdict(
            score=1.0 if result.get("suite_pass") else self._score_checks(result.get("checks") or {}),
            passed=bool(result.get("suite_pass")),
            hard_fail=False,
            issues=issues,
            detail={"state": result.get("state"), "checks": result.get("checks"),
                    "result_path": str(plan["result_path"])},
            evidence=[str(plan["result_path"]), str(plan["perf_copy_path"])],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact

    # ------------------------------------------------------------------ internals

    def _resolve_package(self, plan: dict) -> tuple[Path, Path, str]:
        """Bind this run to the CURRENT packaged build: archive dir + exe + manifest sha.
        Missing/stale packaged evidence blocks — this lane never builds its own package."""
        packaged_result_path = Path(plan["packaged_result_path"])
        if not packaged_result_path.exists():
            raise BlockedError(f"packaged build result missing: {packaged_result_path} "
                               "(run packaged_build_validation first)")
        try:
            packaged = json.loads(packaged_result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise BlockedError(f"packaged build result unreadable: {exc}") from exc
        archive_dir = Path(plan.get("archive_dir") or (packaged.get("package") or {}).get("archive_dir") or "")
        if not archive_dir or not archive_dir.exists():
            raise BlockedError(f"packaged archive dir missing: {archive_dir}")
        manifest_path = Path(plan["packaged_manifest_path"])
        if not manifest_path.exists():
            raise BlockedError(f"package manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        executable = Path(((manifest.get("executable") or {}).get("path")) or "")
        manifest_sha = str((manifest.get("executable") or {}).get("sha256") or "")
        if not executable or not executable.exists():
            raise BlockedError(f"packaged executable missing: {executable}")
        if len(manifest_sha) != 64:
            raise BlockedError("package manifest sha256 missing")
        return archive_dir, executable, manifest_sha

    def _package_saved_dir(self, archive_dir: Path) -> Path:
        return archive_dir / "Windows" / "WanefallGreybox" / "Saved"

    def _run_perf_session(self, plan: dict) -> dict:
        started_at = time.time()
        output_dir = Path(plan["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        archive_dir, executable, manifest_sha = self._resolve_package(plan)
        exe_sha_at_run = _sha256_file(executable)
        binding = {
            "archive_dir": str(archive_dir),
            "manifest_sha256": manifest_sha,
            "exe_sha256_at_run": exe_sha_at_run,
            "matches": exe_sha_at_run == manifest_sha,
        }
        if not binding["matches"]:
            raise BlockedError("packaged executable on disk does not match manifest sha256 — wrong subject")

        saved_dir = self._package_saved_dir(archive_dir)
        perf_json = saved_dir / PERF_JSON_RELATIVE
        csv_dir = saved_dir / PERF_CSV_RELATIVE
        if perf_json.exists():
            perf_json.unlink()                                   # fresh-run truth: no stale evidence
        if csv_dir.exists():
            shutil.rmtree(csv_dir, ignore_errors=True)

        checks: dict[str, dict] = {}
        observations: dict = {"binding": binding}
        proc = None
        perf_payload: dict = {}
        try:
            cmd = [str(executable)] + [str(a) for a in plan["launch_args"]]
            proc = subprocess.Popen(cmd, cwd=str(executable.parent))
            observations["command"] = cmd
            eyes = DesktopEyes()
            window = self._wait_for_window(eyes, str(plan["window_title"]), int(plan["max_wait_seconds"]))
            if not window:
                checks["window_found"] = {"passed": False,
                                          "issues": [f"packaged window not found: {plan['window_title']}"]}
                checks["process_identity"] = {"passed": False, "issues": ["window never found"]}
            else:
                checks["window_found"] = {"passed": True, "issues": [], "title": window.get("title"),
                                          "width": window.get("width"), "height": window.get("height")}
                still_path = Path(plan["still_path"])
                still = eyes.capture_window(str(plan["window_title"]), still_path, proc=executable.stem)
                observations["still_capture"] = still
                checks["process_identity"] = process_identity_check(
                    still, expected_pid=proc.pid, expected_proc=executable.stem)

                # ---- menu segment dwell (command deck)
                time.sleep(max(0.0, float(plan["menu_dwell_seconds"])))

                # ---- deploy into the arena + hold the perf window
                observations["gameplay"] = self._deploy_and_dwell(plan, proc, archive_dir, checks)

            perf_payload = self._collect_perf_evidence(plan, perf_json, csv_dir, checks)
        except BlockedError:
            raise
        except Exception as exc:
            observations["error"] = repr(exc)
            checks.setdefault("window_found", {"passed": False, "issues": [f"session error: {exc!r}"]})
            checks.setdefault("process_identity", {"passed": False, "issues": [f"session error: {exc!r}"]})
        finally:
            self._terminate_process(proc)

        checks["packaged_log_scan"] = self._scan_packaged_log(archive_dir)
        checks.update(compute_floor_checks(perf_payload))

        result = {
            "schema_version": 1,
            "captured_at": time.time(),
            "run_started_at": started_at,
            "asset_id": plan["asset_id"],
            "launched_pid": (proc.pid if proc else None),
            "package_binding": binding,
            "perf": perf_payload,
            "checks": checks,
            "observations": observations,
            "artifacts": {
                "perf_json": str(plan["perf_copy_path"]) if Path(plan["perf_copy_path"]).exists() else None,
                "csv_dir": str(plan["csv_copy_dir"]) if Path(plan["csv_copy_dir"]).exists() else None,
                "still": str(plan["still_path"]) if Path(plan["still_path"]).exists() else None,
            },
            "result_path": str(plan["result_path"]),
            "local_report": str(plan["local_report"]),
            "operator_only_states_written": [],
        }
        # identity-earned runtime source + suite verdict via the shared validation path
        _write_json(Path(plan["result_path"]), result)
        return validate_performance_baseline_result(Path(plan["result_path"]),
                                                    max_age_seconds=DEFAULT_MAX_AGE_SECONDS)

    def _deploy_and_dwell(self, plan: dict, proc, archive_dir: Path, checks: dict) -> dict:
        obs: dict = {}
        try:
            from dimwit.desktop_hands import DesktopHands
            hands = DesktopHands(title=str(plan["window_title"]), proc="WanefallGreybox",
                                 deadline_s=float(plan["map_load_wait_seconds"]) +
                                 float(plan["arena_perf_seconds"]) + 180.0)
            obs["session_locked"] = hands.session_locked()
            obs["focus"] = hands.focus_target()
            use_post = not obs["focus"].get("ok")
            obs["input_mode"] = "posted_window_messages" if use_post else "sendinput_foreground"
            deploy = (hands.post_key(str(plan["deploy_key"])) if use_post
                      else hands.press(str(plan["deploy_key"])))
            obs["deploy"] = {k: deploy.get(k) for k in ("go", "mode", "reason")}
            if not deploy.get("go"):
                raise RuntimeError(f"deploy input blocked: {deploy.get('reason') or deploy.get('mode')}")
            log_path = archive_dir / "Windows" / "WanefallGreybox" / "Saved" / "Logs" / "WanefallGreybox.log"
            loaded = self._wait_for_log_token(log_path, str(plan["arena_map_token"]),
                                              int(plan["map_load_wait_seconds"]))
            checks["gameplay_map_loaded"] = loaded
            if not loaded.get("passed"):
                return obs
            # arena perf dwell: bots fight on their own; W pulses add player-motion realism
            dwell = float(plan["arena_perf_seconds"])
            pulse = max(0.5, float(plan["move_pulse_seconds"]))
            every = max(pulse + 1.0, float(plan["move_pulse_every_seconds"]))
            move_key = str(plan["move_key"])
            fire_key = str(plan.get("fire_key") or "f")
            fire_taps = max(0, int(plan.get("fire_taps_per_pulse") or 0))
            deadline = time.time() + dwell
            pulses = 0
            fire_taps_live = 0
            while time.time() < deadline:
                down = hands.post_key_down(move_key) if use_post else hands.key_down(move_key)
                time.sleep(min(pulse, max(0.1, deadline - time.time())))
                (hands.post_key_up if use_post else hands.key_up)(move_key)
                pulses += 1 if down.get("go") else 0
                # the machine player SHOOTS each pulse: player-path muzzle/impact FX evidence
                for _ in range(fire_taps):
                    if time.time() >= deadline:
                        break
                    tap = hands.post_key(fire_key) if use_post else hands.press(fire_key)
                    fire_taps_live += 1 if tap.get("go") else 0
                    time.sleep(0.35)
                idle = min(every - pulse, max(0.0, deadline - time.time()))
                if idle > 0:
                    time.sleep(idle)
            obs["move_pulses_live"] = pulses
            obs["fire_taps_live"] = fire_taps_live
        except Exception as exc:
            obs["error"] = repr(exc)
            checks.setdefault("gameplay_map_loaded",
                              {"passed": False, "issues": [f"deploy/dwell error: {exc!r}"]})
        return obs

    def _collect_perf_evidence(self, plan: dict, perf_json: Path, csv_dir: Path, checks: dict) -> dict:
        """Poll the flushed perf JSON until the arena steady window meets coverage (or deadline),
        then copy it (and any CSV sidecars) into artifacts/. Returns the parsed payload ({} if
        never readable — downstream floor checks then fail closed)."""
        deadline = time.time() + float(plan["perf_poll_extra_seconds"])
        payload: dict = {}
        while True:
            candidate = self._read_json_safe(perf_json)
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                arena = _pick_segment(payload, str(plan["arena_map_token"]))
                seconds = _num(_steady(arena).get("seconds")) or 0.0
                if seconds >= MIN_ARENA_STEADY_SECONDS:
                    break
            if time.time() >= deadline:
                break
            time.sleep(3.0)
        if payload:
            _write_json(Path(plan["perf_copy_path"]), payload)
        if csv_dir.exists():
            copy_dir = Path(plan["csv_copy_dir"])
            if copy_dir.exists():
                shutil.rmtree(copy_dir, ignore_errors=True)
            shutil.copytree(csv_dir, copy_dir)
        return payload

    @staticmethod
    def _read_json_safe(path: Path):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    def _wait_for_log_token(self, log_path: Path, token: str, timeout_seconds: int) -> dict:
        if not token:
            return {"passed": False, "issues": ["no arena map token configured"]}
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

    def _score_checks(self, checks: dict) -> float:
        if not checks:
            return 0.0
        passed = sum(1 for check in checks.values() if check.get("passed"))
        return round(passed / len(checks), 4)
