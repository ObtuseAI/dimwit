"""BOT_BALANCE_TELEMETRY_HARNESS_V1 (masterplan Horizon 1, bundle 6) — RED-first contract tests.

The bot-balance lane must be fail-closed and tamper-resistant: every gate is RECOMPUTED from the
embedded telemetry payload at validation time (a stored `passed: true` can never rubber-stamp),
reported aggregates are cross-checked against the per-match array (fabricated headlines are
caught), evidence is flag/pid/exe-sha bound to the launched packaged process, and drift gates
compare against a PINNED baseline that blocks when missing. All fixtures live in tempdirs
(tests never mutate live artifacts — snapshot law).
"""
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.bot_balance_telemetry import (
    AGG_TOLERANCE,
    DEFAULT_MAX_AGE_SECONDS,
    DRIFT_BANDS,
    FIXED_FPS,
    FLAG,
    MIN_MATCHES,
    MIN_TTK_SAMPLES,
    MIN_WANE_MATCHES,
    SCORE_LIMIT,
    TTK_FLOOR_S,
    WANE_PROGRESS_MIN,
    compute_drift_check,
    compute_telemetry_checks,
    recompute_aggregates,
    validate_bot_balance_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_bot_balance_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _match(index: int, winner: str = "TeamA", wane: bool = False,
           ttk_samples: list | None = None, duration_s: float = 95.0,
           eliminations: int = 43, shots: int = 260, damage_events: int = 260,
           occupied_cells: int = 40, wane_curve: list | None = None,
           fire_uptime: float = 0.42) -> dict:
    samples = ttk_samples if ttk_samples is not None else [5.0 + 0.1 * (i % 30) for i in range(43)]
    curve = None
    if wane:
        curve = wane_curve if wane_curve is not None else [
            {"t": float(t), "p": min(1.0, t / 60.0)} for t in range(0, 66, 5)]
    return {
        "index": index,
        "seed": 20260702 + index,
        "wane_variant": wane,
        "duration_s": duration_s,
        "winner": winner,
        "team_a_score": SCORE_LIMIT if winner == "TeamA" else 18,
        "team_b_score": SCORE_LIMIT if winner == "TeamB" else 18,
        "eliminations": eliminations,
        "ttk": {
            "samples": samples,
            "avg_s": round(statistics.fmean(samples), 4) if samples else None,
            "p50_s": round(statistics.median(samples), 4) if samples else None,
            "min_s": min(samples) if samples else None,
            "max_s": max(samples) if samples else None,
        },
        "shots_fired": shots,
        "damage_events": damage_events,
        "damage_total": damage_events * 20.0,
        "accuracy": (damage_events / shots) if shots else None,
        "fire_uptime": fire_uptime,
        "weapon_usage": {"bot_rifle_shots": shots, "melee_attack_events": 6},
        # grid: `occupied_cells` cells marked hot, offset by match index so the session union
        # (the gated quantity) spreads across matches like jittered live runs do
        "heatmap": {"grid_size": 16, "occupied_cells": occupied_cells, "samples": 5400,
                    "grid": [[1 if (x * 16 + y) in {(index * 3 + k) % 256 for k in range(occupied_cells)}
                              else 0 for y in range(16)] for x in range(16)],
                    "bounds": {"min_x": -3200.0, "max_x": 3200.0, "min_y": -3200.0, "max_y": 3200.0}},
        "wane": ({"progress_curve": curve, "flee_events": 9} if wane else None),
    }


def _matches(count: int = 12, wane_every: int = 3) -> list:
    out = []
    for i in range(count):
        winner = "TeamA" if i % 2 == 0 else "TeamB"          # symmetric-arena honest split
        out.append(_match(i, winner=winner, wane=(wane_every > 0 and i % wane_every == 0)))
    return out


def _telemetry(matches: list | None = None, pid: int = 4321, flag: str = FLAG,
               fixed_timestep: bool = True, fps: int = FIXED_FPS, nullrhi: bool = True,
               deterministic: bool = True, score_limit: int = SCORE_LIMIT,
               aggregates: dict | None = None) -> dict:
    matches = matches if matches is not None else _matches()
    return {
        "schema_version": 1,
        "flag": flag,
        "pid": pid,
        "executable": ("D:\\WanefallBuild\\PackagedBuildValidation\\runs\\x\\archive\\Windows"
                       "\\WanefallGreybox\\Binaries\\Win64\\WanefallGreybox.exe"),
        "seed": 20260702,
        "requested_matches": len(matches),
        "measurement": {
            "fixed_timestep": fixed_timestep,
            "fps": fps,
            "nullrhi": nullrhi,
            "deterministic": deterministic,
            "score_limit": score_limit,
            "bot_damage": 20.0,
            "bot_fire_cooldown": 1.0,
            "bot_preferred_range": 1200.0,
            "max_seconds": 180.0,
        },
        "harness_interventions": ["player_neutralized"],
        "matches": matches,
        "aggregates": aggregates if aggregates is not None else recompute_aggregates(matches),
        "finalized": True,
    }


def _result(telemetry: dict | None = None, pid: int = 4321,
            captured_at: float | None = None, sha: str = "a" * 64,
            binding_matches: bool = True) -> dict:
    telemetry = telemetry if telemetry is not None else _telemetry(pid=pid)
    return {
        "schema_version": 1,
        "captured_at": captured_at if captured_at is not None else time.time(),
        "asset_id": "wanefall_win64_development_botmatch",
        "launched_pid": pid,
        "package_binding": {
            "archive_dir": "D:\\WanefallBuild\\PackagedBuildValidation\\runs\\x\\archive",
            "manifest_sha256": sha,
            "exe_sha256_at_run": sha,
            "matches": binding_matches,
        },
        "telemetry": telemetry,
        "checks": {},
        "operator_only_states_written": [],
    }


def _validate(result: dict, baseline: dict | None = None, max_age: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    rp = _write_json(TMP / f"result_{time.time_ns()}.json", result)
    bp = TMP / f"baseline_{time.time_ns()}.json"
    if baseline is not None:
        _write_json(bp, baseline)
    return validate_bot_balance_result(rp, baseline_path=bp, max_age_seconds=max_age)


def _baseline_from(telemetry: dict) -> dict:
    return {"schema_version": 1, "pinned_at": time.time(),
            "aggregates": dict(telemetry["aggregates"])}


# ------------------------------------------------------------------ green path

def test_honest_payload_passes():
    telemetry = _telemetry()
    result = _validate(_result(telemetry), baseline=_baseline_from(telemetry))
    failed = {k: v for k, v in result["checks"].items() if not v.get("passed")}
    assert result["suite_pass"], f"honest payload must pass; failed: {failed}"
    assert result["state"] == "PASS"


def test_missing_result_blocks():
    try:
        validate_bot_balance_result(TMP / "nope.json", baseline_path=TMP / "nope_base.json")
        raise AssertionError("missing result must raise BlockedError")
    except BlockedError:
        pass


# ------------------------------------------------------------------ identity binding

def test_wrong_flag_fails_binding():
    result = _validate(_result(_telemetry(flag="SOMETHINGELSE")))
    assert not result["checks"]["telemetry_evidence_bound"]["passed"]


def test_pid_mismatch_fails_binding():
    result = _validate(_result(_telemetry(pid=999), pid=4321))
    assert not result["checks"]["telemetry_evidence_bound"]["passed"]


def test_sha_mismatch_fails_binding():
    bad = _result()
    bad["package_binding"]["exe_sha256_at_run"] = "b" * 64
    result = _validate(bad)
    assert not result["checks"]["telemetry_evidence_bound"]["passed"]


# ------------------------------------------------------------------ measurement conditions

def test_measurement_conditions_required():
    for kw in ({"fixed_timestep": False}, {"deterministic": False},
               {"nullrhi": False}, {"fps": 30}, {"score_limit": 5}):
        result = _validate(_result(_telemetry(**kw)))
        assert not result["checks"]["measurement_conditions"]["passed"], f"must fail for {kw}"


# ------------------------------------------------------------------ coverage floors

def test_too_few_matches_fails():
    result = _validate(_result(_telemetry(matches=_matches(count=MIN_MATCHES - 1))))
    assert not result["checks"]["match_coverage"]["passed"]


def test_too_few_wane_variants_fails():
    result = _validate(_result(_telemetry(matches=_matches(count=12, wane_every=0))))
    assert not result["checks"]["match_coverage"]["passed"]


def test_zero_elimination_match_fails():
    matches = _matches()
    matches[3]["eliminations"] = 0
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["match_coverage"]["passed"]


# ------------------------------------------------------------------ sanity invariants

def test_ttk_below_theoretical_floor_fails():
    matches = _matches()
    non_wane = next(m for m in matches if not m["wane_variant"])
    non_wane["ttk"]["samples"][0] = TTK_FLOOR_S - 1.0
    non_wane["ttk"]["min_s"] = TTK_FLOOR_S - 1.0
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_wane_match_ttk_exempt_from_rifle_floor():
    """Wane-line hazard damage stacks per overlap tick — sub-floor TTK in a WANE match is real
    data, not a lie (live-run truth: one-tick 0.017s wane kill)."""
    matches = _matches()
    wane_match = next(m for m in matches if m["wane_variant"])
    wane_match["ttk"]["samples"][0] = 0.02
    wane_match["ttk"]["min_s"] = 0.02
    telemetry = _telemetry(matches=matches)
    result = _validate(_result(telemetry), baseline=_baseline_from(telemetry))
    assert result["checks"]["sanity_invariants"]["passed"]


def test_too_few_ttk_samples_fails():
    matches = [_match(i, winner="TeamA" if i % 2 == 0 else "TeamB",
                      ttk_samples=[5.5], eliminations=1, wane=(i % 3 == 0))
               for i in range(12)]
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_one_sided_win_rate_passes_sanity_but_drifts():
    """A 100% TeamA win rate is REAL signal (deterministic AI / arena asymmetry), not a sanity
    violation — both teams still eliminate, so combat is bilateral. It is caught by DRIFT vs the
    pinned baseline, not by a symmetric-band assertion. Live-run truth 2026-07-02."""
    matches = [_match(i, winner="TeamA", wane=(i % 3 == 0)) for i in range(12)]
    telemetry = _telemetry(matches=matches)
    # sanity passes (bilateral: both teams score on the loser's board)
    result = _validate(_result(telemetry), baseline=_baseline_from(telemetry))
    assert result["checks"]["sanity_invariants"]["passed"]
    # but a baseline pinned at 50/50 makes this 100% run trip the drift gate
    baseline = _baseline_from(telemetry)
    baseline["aggregates"]["team_a_win_rate"] = 0.5
    drifted = _validate(_result(telemetry), baseline=baseline)
    assert not drifted["checks"]["baseline_drift"]["passed"]


def test_one_sided_combat_fails_sanity():
    """A session where only ONE team ever kills (loser scoreboard flat 0) is a broken harness,
    not an imbalance — that IS a sanity violation."""
    matches = []
    for i in range(12):
        m = _match(i, winner="TeamA", wane=(i % 3 == 0))
        m["team_b_score"] = 0          # TeamB never eliminated anyone
        matches.append(m)
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_accuracy_out_of_range_fails():
    matches = _matches()
    for m in matches:
        m["damage_events"] = 0
        m["accuracy"] = 0.0
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_heatmap_underspread_passes_sanity_recorded():
    """A thin session union (bots strafe in place, all in the same 1-2 cells) is HONEST signal
    for the feel-tuning bundle, not a telemetry-rejecting violation — every match still sampled.
    The union is RECORDED + drift-gated, not hard-floored. Live-run truth 2026-07-02."""
    matches = _matches()
    same_cells_grid = [[1 if (x, y) in {(8, 8), (8, 9)} else 0 for y in range(16)]
                       for x in range(16)]
    for m in matches:
        m["heatmap"]["grid"] = [row[:] for row in same_cells_grid]
        m["heatmap"]["occupied_cells"] = 2
    telemetry = _telemetry(matches=matches)
    result = _validate(_result(telemetry), baseline=_baseline_from(telemetry))
    assert result["checks"]["sanity_invariants"]["passed"]
    assert result["checks"]["sanity_invariants"]["heatmap_union_cells"] == 2


def test_heatmap_unsampled_match_fails():
    matches = _matches()
    matches[2]["heatmap"]["occupied_cells"] = 0
    matches[2]["heatmap"]["grid"] = [[0] * 16 for _ in range(16)]
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_non_monotonic_wane_curve_fails():
    matches = _matches()
    wane_match = next(m for m in matches if m["wane_variant"])
    wane_match["wane"]["progress_curve"] = [{"t": 0.0, "p": 0.0}, {"t": 5.0, "p": 0.6},
                                            {"t": 10.0, "p": 0.3}, {"t": 60.0, "p": 1.0}]
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


def test_wane_curve_never_completing_fails():
    matches = _matches()
    for m in matches:
        if m["wane_variant"]:
            m["wane"]["progress_curve"] = [{"t": float(t), "p": min(WANE_PROGRESS_MIN - 0.2, t / 100.0)}
                                           for t in range(0, 66, 5)]
    result = _validate(_result(_telemetry(matches=matches)))
    assert not result["checks"]["sanity_invariants"]["passed"]


# ------------------------------------------------------------------ anti-fabrication

def test_fabricated_aggregates_rejected():
    telemetry = _telemetry()
    telemetry["aggregates"]["ttk_avg_s"] = telemetry["aggregates"]["ttk_avg_s"] * 2.0
    result = _validate(_result(telemetry))
    check = result["checks"]["aggregate_recompute"]
    assert not check["passed"]


def test_aggregate_recompute_is_pure():
    matches = _matches()
    a = recompute_aggregates(matches)
    b = recompute_aggregates(json.loads(json.dumps(matches)))
    assert a == b
    assert a["matches_completed"] == len(matches)
    assert 0.0 < a["team_a_win_rate"] < 1.0


# ------------------------------------------------------------------ baseline drift

def test_missing_baseline_blocks_drift_gate():
    result = _validate(_result())     # no baseline written
    check = result["checks"]["baseline_drift"]
    assert not check["passed"]
    assert any("baseline" in issue.lower() for issue in check["issues"])


def test_drift_beyond_band_fails():
    telemetry = _telemetry()
    baseline = _baseline_from(telemetry)
    band = DRIFT_BANDS["ttk_avg_s"]
    baseline["aggregates"]["ttk_avg_s"] = telemetry["aggregates"]["ttk_avg_s"] / (1.0 + band + 0.2)
    result = _validate(_result(telemetry), baseline=baseline)
    assert not result["checks"]["baseline_drift"]["passed"]


def test_drift_within_band_passes():
    telemetry = _telemetry()
    baseline = _baseline_from(telemetry)
    baseline["aggregates"]["ttk_avg_s"] *= 1.05          # 5% << 25% band
    result = _validate(_result(telemetry), baseline=baseline)
    assert result["checks"]["baseline_drift"]["passed"]


# ------------------------------------------------------------------ freshness

def test_stale_result_fails_freshness():
    result = _validate(_result(captured_at=time.time() - DEFAULT_MAX_AGE_SECONDS - 60))
    assert not result["checks"]["freshness"]["passed"]


# ------------------------------------------------------------------ ratchet

def test_thresholds_are_masterplan_floors():
    """Floors may only TIGHTEN (ratchet law). Loosening any of these is a doctrine violation."""
    assert MIN_MATCHES >= 10
    assert MIN_WANE_MATCHES >= 2
    # focus-fire floor: a rifle kill cannot beat one fire cooldown. > 0 (guards fabricated-instant)
    # and >= one cooldown. NOT the 1v1 5-shot time — 4v4 focus fire legitimately kills in ~2s.
    assert TTK_FLOOR_S >= 1.0
    assert MIN_TTK_SAMPLES >= 30
    assert WANE_PROGRESS_MIN >= 0.9
    assert AGG_TOLERANCE <= 0.02
    assert DEFAULT_MAX_AGE_SECONDS <= 6 * 60 * 60
    assert FIXED_FPS == 60
    assert FLAG == "WANEFALLBOTMATCH"
    assert "team_a_win_rate" in DRIFT_BANDS   # balance symmetry is drift-gated, not asserted
    for key, band in DRIFT_BANDS.items():
        assert band <= 0.30, f"drift band {key} loosened past 30%"
