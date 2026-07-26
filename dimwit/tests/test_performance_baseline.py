"""PERFORMANCE_BASELINE_GATES_V1 (masterplan Horizon 1, bundle 4) — RED-first contract tests.

The perf lane must be fail-closed and tamper-resistant: floors are RECOMPUTED from the embedded
perf payload at validation time (a stored `passed: true` can never rubber-stamp), the reported
arena p95 is cross-checked against the downsampled steady trace, and identity/freshness/
measurement-condition checks gate the evidence itself. All fixtures live in a tempdir (tests
never mutate live artifacts — snapshot law).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.performance_baseline import (
    ARENA_MAP,
    ARENA_P95_FLOOR_MS,
    HITCH_MS,
    MEMORY_PEAK_BUDGET_MB,
    MENU_MAP,
    MENU_P95_FLOOR_MS,
    MIN_ARENA_STEADY_FRAMES,
    MIN_ARENA_STEADY_SECONDS,
    MIN_MENU_STEADY_FRAMES,
    MIN_MENU_STEADY_SECONDS,
    SEVERE_HITCH_MS,
    PerformanceBaselinePipeline,
    compute_floor_checks,
    validate_performance_baseline_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_perf_baseline_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _segment(map_name: str, steady_seconds: float, steady_frames: int, p95_ms: float,
             hitch_count: int = 0, severe_hitch_count: int = 0,
             trace_p95_ms: float | None = None) -> dict:
    """Fabricate a consistent segment: steady trace built so its p95 ~= trace_p95_ms (defaults
    to the reported p95, i.e. an honest capture)."""
    trace_target = p95_ms if trace_p95_ms is None else trace_p95_ms
    base = max(1.0, trace_target * 0.55)
    trace = [base] * 950 + [trace_target] * 50          # p95 lands on trace_target
    avg = sum(trace) / len(trace)
    stats = {
        "frames": steady_frames,
        "seconds": steady_seconds,
        "avg_ms": round(avg, 3),
        "p50_ms": base,
        "p95_ms": p95_ms,
        "p99_ms": max(p95_ms, trace_target),
        "max_ms": max(p95_ms, trace_target),
        "fps_avg": round(1000.0 / avg, 2),
        "hitch_count": hitch_count,
        "severe_hitch_count": severe_hitch_count,
    }
    total = dict(stats)
    total["frames"] = steady_frames + 60
    total["seconds"] = steady_seconds + 5.0
    return {
        "map": map_name,
        "started_at": time.time() - 200.0,
        "total": total,
        "steady": stats,
        "steady_trace_ms": trace,
        "trace_stride": 1,
    }


def _perf_payload(arena_p95: float = 8.0, menu_p95: float = 6.0,
                  arena_hitches: int = 0, arena_severe: int = 0,
                  peak_mb: float = 3200.0, vsync: int = 0, t_max_fps: float = 0.0,
                  smooth_disabled: bool = True,
                  arena_steady_seconds: float = 45.0, arena_steady_frames: int = 4000,
                  menu_steady_seconds: float = 20.0, menu_steady_frames: int = 1500,
                  pid: int = 4321, arena_trace_p95: float | None = None) -> dict:
    return {
        "schema_version": 1,
        "flag": "WANEFALLPERFPROOF",
        "pid": pid,
        "executable": "D:\\WanefallBuild\\PackagedBuildValidation\\runs\\x\\archive\\Windows\\WanefallGreybox\\Binaries\\Win64\\WanefallGreybox.exe",
        "session_started_at": time.time() - 300.0,
        "captured_at": time.time(),
        "finalized": False,
        "measurement": {
            "vsync": vsync,
            "t_max_fps": t_max_fps,
            "smooth_framerate_disabled": smooth_disabled,
            "fixed_framerate_disabled": True,
            "resolution_x": 1920,
            "resolution_y": 1080,
            "warmup_seconds": 5.0,
            "hitch_ms": HITCH_MS,
            "severe_hitch_ms": SEVERE_HITCH_MS,
        },
        "memory": {"peak_used_physical_mb": peak_mb, "avg_used_physical_mb": peak_mb * 0.9, "samples": 200},
        "segments": [
            _segment(MENU_MAP, menu_steady_seconds, menu_steady_frames, menu_p95),
            _segment(ARENA_MAP, arena_steady_seconds, arena_steady_frames, arena_p95,
                     hitch_count=arena_hitches, severe_hitch_count=arena_severe,
                     trace_p95_ms=arena_trace_p95),
        ],
    }


def _result_payload(perf: dict, pid: int = 4321) -> dict:
    return {
        "schema_version": 1,
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "asset_id": "wanefall_win64_development_perf",
        "runtime_source": "packaged_build",
        "launched_pid": pid,
        "perf": perf,
        "package_binding": {
            "archive_dir": "D:\\WanefallBuild\\PackagedBuildValidation\\runs\\x\\archive",
            "manifest_sha256": "a" * 64,
            "exe_sha256_at_run": "a" * 64,
            "matches": True,
        },
        "checks": {
            "window_found": {"passed": True, "issues": [], "title": "WanefallGreybox"},
            "process_identity": {"passed": True, "issues": [], "captured_pid": pid,
                                 "expected_pid": pid, "capture_tier": "printwindow"},
            "perf_evidence_present": {"passed": True, "issues": [], "pid": pid,
                                      "executable_in_archive": True, "exe_sha_matches_manifest": True},
            "packaged_log_scan": {"passed": True, "issues": [], "fatal_count": 0, "error_count": 0},
        },
    }


# ---------------------------------------------------------------- fail-closed evidence handling

def test_missing_result_blocks():
    try:
        validate_performance_baseline_result(TMP / "missing_perf_result.json", max_age_seconds=60)
    except BlockedError as exc:
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("missing performance result must block")


def test_unreadable_result_blocks():
    path = TMP / "garbage_perf_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    try:
        validate_performance_baseline_result(path, max_age_seconds=60)
    except BlockedError:
        pass
    else:
        raise AssertionError("unreadable performance result must block")


def test_result_without_perf_payload_fails_evidence_check():
    payload = _result_payload(_perf_payload())
    payload.pop("perf")
    path = _write_json(TMP / "no_perf_payload.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["suite_pass"] is False


# ---------------------------------------------------------------- happy path + recomputation law

def test_honest_capture_passes_all_floors():
    path = _write_json(TMP / "honest.json", _result_payload(_perf_payload()))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    checks = result["checks"]
    for name in ("measurement_conditions", "segment_coverage", "arena_frametime_floor",
                 "arena_hitch_free", "menu_frametime_floor", "memory_budget"):
        assert checks[name]["passed"] is True, f"{name}: {checks[name].get('issues')}"
    assert result["suite_pass"] is True
    assert result["runtime_source"] == "packaged_build"


def test_tampered_stored_checks_cannot_rubber_stamp_bad_p95():
    payload = _result_payload(_perf_payload(arena_p95=22.0))
    payload["checks"]["arena_frametime_floor"] = {"passed": True, "issues": []}
    path = _write_json(TMP / "tampered.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["arena_frametime_floor"]["passed"] is False
    assert result["suite_pass"] is False


def test_fabricated_headline_p95_diverging_from_trace_fails():
    # reported steady p95 says 5ms; the steady trace says ~30ms — cross-check must reject
    payload = _result_payload(_perf_payload(arena_p95=5.0, arena_trace_p95=30.0))
    path = _write_json(TMP / "fabricated.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["arena_frametime_floor"]["passed"] is False
    assert result["suite_pass"] is False


# ---------------------------------------------------------------- individual floors

def test_arena_hitch_gate_fails_on_any_steady_hitch():
    path = _write_json(TMP / "hitchy.json", _result_payload(_perf_payload(arena_hitches=2)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["arena_hitch_free"]["passed"] is False
    assert result["suite_pass"] is False


def test_arena_severe_hitch_gate_fails():
    path = _write_json(TMP / "severe.json", _result_payload(_perf_payload(arena_severe=1)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["arena_hitch_free"]["passed"] is False


def test_menu_floor_fails_on_slow_menu():
    path = _write_json(TMP / "slowmenu.json", _result_payload(_perf_payload(menu_p95=25.0)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["menu_frametime_floor"]["passed"] is False


def test_memory_budget_fails_over_peak():
    path = _write_json(TMP / "fatmem.json",
                       _result_payload(_perf_payload(peak_mb=MEMORY_PEAK_BUDGET_MB + 500)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["memory_budget"]["passed"] is False


def test_segment_coverage_fails_on_short_arena_window():
    path = _write_json(TMP / "shortarena.json",
                       _result_payload(_perf_payload(arena_steady_seconds=10.0,
                                                     arena_steady_frames=300)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["segment_coverage"]["passed"] is False


def test_segment_coverage_fails_when_menu_segment_missing():
    perf = _perf_payload()
    perf["segments"] = [seg for seg in perf["segments"] if seg["map"] == ARENA_MAP]
    path = _write_json(TMP / "nomenu.json", _result_payload(perf))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["segment_coverage"]["passed"] is False


def test_measurement_conditions_fail_on_vsync_or_cap():
    path = _write_json(TMP / "vsynced.json", _result_payload(_perf_payload(vsync=1)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["measurement_conditions"]["passed"] is False

    path = _write_json(TMP / "capped.json", _result_payload(_perf_payload(t_max_fps=60.0)))
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["measurement_conditions"]["passed"] is False


# ---------------------------------------------------------------- identity + freshness law

def test_runtime_source_must_be_earned_by_process_identity():
    payload = _result_payload(_perf_payload())
    payload["checks"]["process_identity"] = {"passed": False, "issues": ["pid mismatch"]}
    path = _write_json(TMP / "unbound.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["runtime_source"]["passed"] is False
    assert result["suite_pass"] is False


def test_perf_pid_mismatch_fails_evidence_binding():
    payload = _result_payload(_perf_payload(pid=9999), pid=4321)
    path = _write_json(TMP / "pidmismatch.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=60)
    assert result["checks"]["perf_evidence_present"]["passed"] is False
    assert result["suite_pass"] is False


def test_stale_result_fails_freshness():
    payload = _result_payload(_perf_payload())
    payload["captured_at"] = time.time() - 7200
    path = _write_json(TMP / "stale.json", payload)
    result = validate_performance_baseline_result(path, max_age_seconds=3600)
    assert result["checks"]["freshness"]["passed"] is False
    assert result["suite_pass"] is False


# ---------------------------------------------------------------- floors are the masterplan floors

def test_thresholds_are_masterplan_floors_ratchet_anchor():
    # Ratchet law: these may TIGHTEN, never loosen. A loosening edit must break this test.
    assert ARENA_P95_FLOOR_MS <= 16.6
    assert MENU_P95_FLOOR_MS <= 16.6
    assert HITCH_MS <= 100.0
    assert SEVERE_HITCH_MS <= 250.0
    assert MEMORY_PEAK_BUDGET_MB <= 8192.0
    assert MIN_ARENA_STEADY_SECONDS >= 30.0
    assert MIN_ARENA_STEADY_FRAMES >= 1000
    assert MIN_MENU_STEADY_SECONDS >= 8.0
    assert MIN_MENU_STEADY_FRAMES >= 200


def test_compute_floor_checks_is_pure_and_fail_closed_on_empty():
    checks = compute_floor_checks({})
    for name in ("measurement_conditions", "segment_coverage", "arena_frametime_floor",
                 "arena_hitch_free", "menu_frametime_floor", "memory_budget"):
        assert checks[name]["passed"] is False, f"{name} must fail closed on empty perf payload"


# ---------------------------------------------------------------- pipeline plan contract

def test_pipeline_plan_launches_flagged_1080p_menu_map():
    pipeline = PerformanceBaselinePipeline()
    plan = pipeline.plan({"asset_id": "wanefall_win64_development_perf"})
    launch = " ".join(str(part) for part in plan["launch_args"])
    assert "-WANEFALLPERFPROOF" in launch
    assert "-ResX=1920" in launch
    assert "-ResY=1080" in launch
    assert "-windowed" in launch
    assert "-nosound" in launch
    assert MENU_MAP in launch
    assert plan["arena_map_token"] == ARENA_MAP
    assert float(plan["arena_perf_seconds"]) >= 60.0
    assert float(plan["menu_dwell_seconds"]) >= 15.0
    assert plan["result_path"].name == "performance_baseline_result.json"


# ---------------------------------------------------------------- registration parity

def test_validation_registry_contains_performance_gates_all_blockers():
    from dimwit.pipelines.validation import Severity
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {v.id: v for v in REGISTRY if v.domain == "performance_baseline"}
    expected = {
        "perf_baseline_result_fresh",
        "perf_baseline_identity_bound",
        "perf_baseline_measurement_conditions",
        "perf_baseline_segment_coverage",
        "perf_arena_frametime_floor",
        "perf_arena_hitch_free",
        "perf_menu_frametime_floor",
        "perf_memory_budget",
        "perf_baseline_queue_sync",
    }
    assert expected.issubset(set(gates)), f"missing: {expected - set(gates)}"
    for name in expected:
        assert gates[name].severity == Severity.BLOCKER, f"{name} must be a BLOCKER"


def test_pipeline_registry_manifest_and_director_include_performance_baseline():
    from dimwit.pipelines import PIPELINES

    manifest = json.loads(Path("config/production_pipelines.json").read_text(encoding="utf-8"))
    director = json.loads(Path("config/director_tasks.json").read_text(encoding="utf-8"))
    assert "performance_baseline" in PIPELINES
    assert "performance_baseline" in manifest["pipelines"]
    assert any(task.get("pipeline") == "performance_baseline" for task in director["tasks"])


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
