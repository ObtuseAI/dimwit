"""BOT_BALANCE_TELEMETRY_HARNESS_V1 — headless packaged bot-vs-bot matches + drift gates.

Masterplan Horizon 1, bundle 6 (§B2/A2). WANEFALL combat balance was ASSERTED, not measured.
This lane launches the real packaged `WanefallGreybox.exe` straight into the Arena4v4 bot TDM,
headless (`-nullrhi -nosound -unattended`) at fixed 60Hz game time (`-deterministic -fps=60`),
where the flag-gated `UWanefallBotMatchSubsystem` (-WANEFALLBOTMATCH) runs N seeded bot-vs-bot
matches through the REAL game loop (every bot action is the same method the live game calls) and
flushes identity-bound telemetry JSON: per-match TTK, fire uptime, weapon usage, 16x16 position
heatmaps, wane-line progression curves, and session aggregates.

Laws honored:
- Law 5: packaged proof is the only proof — telemetry must come from the archived package,
  exe-sha-bound to the current package manifest, pid-bound to the launched process.
- Recomputation law: every gate is recomputed from the raw telemetry payload at validation time;
  reported aggregates are cross-checked against the per-match array (fabricated headline REJECTED).
- Baseline law (A2 — design gets receipts): drift gates compare against the PINNED committed
  baseline; a missing baseline BLOCKS; re-pinning is an explicit reviewed edit.
- One-variable law: measurement conditions (fixed timestep 60Hz, deterministic, nullrhi, score
  limit 25, WanefallCombat constants) are recorded and gated — an uncomparable capture fails.

Floors are ratchet-only (test_thresholds_are_masterplan_floors): tighten allowed, never loosen.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import time
from pathlib import Path

from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.packaged_build_validation import (
    MANIFEST_PATH as PACKAGED_MANIFEST_PATH,
    RESULT_PATH as PACKAGED_RESULT_PATH,
    _latest_log_text,
    _packaged_log_dirs,
)
from dimwit.pipelines.real_game_validation import scan_log_text


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "artifacts" / "bot_balance"
RESULT_PATH = RESULT_DIR / "bot_balance_result.json"
BASELINE_PATH = RESULT_DIR / "baseline" / "bot_balance_baseline.json"
LOCAL_REPORT = RESULT_DIR / "WANEFALL_BOT_BALANCE_TELEMETRY_REPORT.md"

FLAG = "WANEFALLBOTMATCH"
TELEMETRY_RELATIVE = Path("ShowMeAI") / "WanefallBotMatch" / "bot_match_telemetry.json"
ARENA_MAP = "Wanefall_Arena4v4_Prototype_01"
ARENA_MAP_URL = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"

# Telemetry payload schema versions this validator understands. v2 adds the per-match `player_seat`
# block (PROGRESSION_PERSISTENCE_V1); v1 predates it. Both accepted — the seat block is optional and
# never rejected. A present-but-unknown version fails closed; an absent version is tolerated (legacy
# capture) since the strict schema_version gate lives in the progression domain, not here.
ACCEPTED_TELEMETRY_SCHEMAS = (1, 2)

# ---- FLOORS (BLOCKER thresholds). RATCHET-ONLY: tighten allowed, loosening breaks the ratchet
# test and violates doctrine.
MIN_MATCHES = 10                  # coverage: a couple of matches can't speak for balance
MIN_WANE_MATCHES = 2              # wane-pressure variant coverage
# FOCUS-FIRE physics floor (non-wane): a rifle-only kill needs a 2nd shot, which cannot beat one
# fire cooldown even with a full team concentrating fire — anything faster is a fabricated/instant
# kill. NOT the single-shooter 5-shot time (~5s): 4v4 focus fire legitimately kills in ~2s
# (live-run truth 2026-07-02: non-wane min 2.05s). Bundle-6 authoring correction — the prior 4.0s
# assumed a 1v1 duel and never shipped; documented in the bundle report.
TTK_FLOOR_S = 1.0
MIN_TTK_SAMPLES = 30              # session-wide TTK sample floor
WANE_PROGRESS_MIN = 0.9           # wane-line curves must actually complete the sweep
AGG_TOLERANCE = 0.02              # reported vs recomputed aggregate relative tolerance
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60   # packaged-evidence freshness ceiling
FIXED_FPS = 60
SCORE_LIMIT = 25                  # WanefallArena::ScoreLimit source of truth
BOT_DAMAGE = 20.0                 # WanefallCombat::BotDamage
BOT_FIRE_COOLDOWN = 1.0           # WanefallCombat::BotFireCooldown
BOT_PREFERRED_RANGE = 1200.0      # WanefallCombat::BotPreferredRange

# drift bands vs the pinned baseline (relative, except win_rate = absolute delta)
DRIFT_BANDS = {
    "ttk_avg_s": 0.25,
    "elim_per_minute": 0.30,
    "team_a_win_rate": 0.20,      # absolute delta band; also hard [0.30, 0.70] window
    "fire_uptime": 0.30,
    "heatmap_occupancy_pct": 0.25,
}

CHECK_NAMES = (
    "telemetry_evidence_bound",
    "measurement_conditions",
    "match_coverage",
    "sanity_invariants",
    "aggregate_recompute",
    "baseline_drift",
    "freshness",
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


def _matches_of(telemetry: dict) -> list:
    matches = telemetry.get("matches")
    return [m for m in matches if isinstance(m, dict)] if isinstance(matches, list) else []


def _ttk_samples(match: dict) -> list:
    ttk = match.get("ttk") if isinstance(match.get("ttk"), dict) else {}
    samples = ttk.get("samples") if isinstance(ttk.get("samples"), list) else []
    return [s for s in (_num(v) for v in samples) if s is not None]


# ------------------------------------------------------------------ pure recomputation

def recompute_aggregates(matches: list) -> dict:
    """Session aggregates recomputed from the per-match array. Pure — the ONLY definition of the
    headline numbers; a stored aggregates block that disagrees is a fabricated headline."""
    matches = [m for m in matches if isinstance(m, dict)]
    all_ttk: list[float] = []
    for m in matches:
        all_ttk.extend(_ttk_samples(m))
    decided = [m for m in matches if str(m.get("winner") or "") in ("TeamA", "TeamB")]
    wins_a = sum(1 for m in decided if m.get("winner") == "TeamA")
    total_elims = sum(int(_num(m.get("eliminations")) or 0) for m in matches)
    total_seconds = sum(_num(m.get("duration_s")) or 0.0 for m in matches)
    total_shots = sum(int(_num(m.get("shots_fired")) or 0) for m in matches)
    total_damage_events = sum(int(_num(m.get("damage_events")) or 0) for m in matches)
    uptimes = [u for u in (_num(m.get("fire_uptime")) for m in matches) if u is not None]
    occupied = [
        _num((m.get("heatmap") or {}).get("occupied_cells"))
        for m in matches if isinstance(m.get("heatmap"), dict)
    ]
    occupied = [o for o in occupied if o is not None]
    return {
        "matches_completed": len(matches),
        "draws": len(matches) - len(decided),
        "ttk_avg_s": round(statistics.fmean(all_ttk), 4) if all_ttk else None,
        "ttk_p50_s": round(statistics.median(all_ttk), 4) if all_ttk else None,
        "ttk_samples": len(all_ttk),
        "team_a_win_rate": round(wins_a / len(decided), 4) if decided else None,
        "elim_per_minute": round(total_elims / (total_seconds / 60.0), 4) if total_seconds > 0 else None,
        "accuracy": round(total_damage_events / total_shots, 4) if total_shots > 0 else None,
        "fire_uptime": round(statistics.fmean(uptimes), 4) if uptimes else None,
        "heatmap_occupancy_pct": round(statistics.fmean(occupied) / 256.0 * 100.0, 4) if occupied else None,
    }


def compute_telemetry_checks(telemetry: dict) -> dict:
    """Recompute every payload-derived gate. Pure + fail-closed: an empty or partial payload
    fails every check; stored check objects are never trusted."""
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    checks: dict[str, dict] = {}
    matches = _matches_of(telemetry)

    # measurement conditions — telemetry is only comparable at pinned conditions
    measurement = telemetry.get("measurement") if isinstance(telemetry.get("measurement"), dict) else {}
    issues = []
    if measurement.get("fixed_timestep") is not True:
        issues.append("fixed_timestep must be true (wall-clock ticks are not comparable)")
    if measurement.get("deterministic") is not True:
        issues.append("deterministic mode must be true")
    if measurement.get("nullrhi") is not True:
        issues.append("nullrhi must be true (headless harness contract)")
    if _num(measurement.get("fps")) != float(FIXED_FPS):
        issues.append(f"fps must be {FIXED_FPS}, got {measurement.get('fps')!r}")
    if _num(measurement.get("score_limit")) != float(SCORE_LIMIT):
        issues.append(f"score_limit must be {SCORE_LIMIT}, got {measurement.get('score_limit')!r}")
    for key, expected in (("bot_damage", BOT_DAMAGE), ("bot_fire_cooldown", BOT_FIRE_COOLDOWN),
                          ("bot_preferred_range", BOT_PREFERRED_RANGE)):
        if _num(measurement.get(key)) != expected:
            issues.append(f"{key} must match WanefallCombat:: source of truth "
                          f"({expected}), got {measurement.get(key)!r}")
    checks["measurement_conditions"] = {"passed": not issues, "issues": issues,
                                        "measurement": measurement}

    # telemetry payload schema — v2 carries the optional per-match player_seat block. Tolerant:
    # accept known versions (or absent legacy), fail closed only on a present-but-unknown version.
    sv = telemetry.get("schema_version")
    sv_issues = ([] if (sv is None or sv in ACCEPTED_TELEMETRY_SCHEMAS)
                 else [f"telemetry schema_version {sv!r} not in accepted {ACCEPTED_TELEMETRY_SCHEMAS}"])
    checks["schema_version"] = {"passed": not sv_issues, "issues": sv_issues, "schema_version": sv}

    # match coverage — floors on how much play the session actually contains
    issues = []
    if telemetry.get("finalized") is not True:
        issues.append("telemetry not finalized (session died before completing its matches)")
    if len(matches) < MIN_MATCHES:
        issues.append(f"{len(matches)} matches < floor {MIN_MATCHES}")
    wane_matches = [m for m in matches if m.get("wane_variant") is True]
    if len(wane_matches) < MIN_WANE_MATCHES:
        issues.append(f"{len(wane_matches)} wane-variant matches < floor {MIN_WANE_MATCHES}")
    for m in matches:
        duration = _num(m.get("duration_s"))
        if duration is None or duration <= 0:
            issues.append(f"match {m.get('index')!r}: duration_s missing/non-positive")
        if int(_num(m.get("eliminations")) or 0) <= 0:
            issues.append(f"match {m.get('index')!r}: zero eliminations (no combat happened)")
    decided = [m for m in matches if str(m.get("winner") or "") in ("TeamA", "TeamB")]
    if matches and not decided:
        issues.append("all matches were draws — score/elimination path unproven")
    checks["match_coverage"] = {"passed": not issues, "issues": issues,
                                "matches": len(matches), "wane_matches": len(wane_matches),
                                "draws": len(matches) - len(decided)}

    # sanity invariants — physics/correctness only. Deliberately NOT balance-taste: whether the
    # arena is symmetric or bots roam widely is measured, pinned as a baseline, and drift-gated
    # (compute_drift_check) — V1's job is to EMIT honest receipts, not assert the game is already
    # balanced. These gates catch numbers that are physically impossible or structurally broken.
    issues = []
    all_ttk: list[float] = []
    for m in matches:
        all_ttk.extend(_ttk_samples(m))
    if len(all_ttk) < MIN_TTK_SAMPLES:
        issues.append(f"{len(all_ttk)} TTK samples < floor {MIN_TTK_SAMPLES}")
    # TTK physics floor binds NON-wane matches only. It is a FOCUS-FIRE floor, not a duel floor:
    # up to a full enemy team can concentrate fire on one victim, so first-damage->elimination is
    # bounded below by ~one fire cooldown (a second shot cannot land instantly), NOT by the
    # single-shooter 5-shot time. Sub-floor non-wane TTK = fabricated/instant kill. Wane matches
    # are exempt (hazard damage stacks per overlap tick — live truth: a 0.017s one-tick wane kill).
    rifle_ttk: list[float] = []
    for m in matches:
        if m.get("wane_variant") is not True:
            rifle_ttk.extend(_ttk_samples(m))
    impossible = [s for s in rifle_ttk if s < TTK_FLOOR_S]
    if impossible:
        issues.append(
            f"{len(impossible)} non-wane TTK sample(s) below the {TTK_FLOOR_S}s focus-fire floor "
            f"(min {min(impossible):.2f}s) — a rifle-only kill cannot beat one "
            f"{BOT_FIRE_COOLDOWN:.1f}s cooldown; instant kill = fabricated")
    agg = recompute_aggregates(matches)
    accuracy = agg.get("accuracy")
    if accuracy is None or not (0.0 < accuracy <= 1.0):
        issues.append(f"accuracy {accuracy!r} outside (0, 1]")
    # bilateral combat: BOTH teams must register eliminations across the session. A session where
    # only one team ever kills is a broken harness (one side inert / friendly-fire miswired), not
    # merely an unbalanced arena. This is the correctness floor that replaces a win-rate symmetry
    # ASSERTION (win-rate magnitude is drift-gated vs the pinned baseline instead).
    team_a_elims = 0
    team_b_elims = 0
    for m in matches:
        a, b = _num(m.get("team_a_score")), _num(m.get("team_b_score"))
        team_a_elims += int(a or 0)
        team_b_elims += int(b or 0)
    if matches and (team_a_elims <= 0 or team_b_elims <= 0):
        issues.append(f"one-sided combat: TeamA elims {team_a_elims}, TeamB elims {team_b_elims} "
                      "— a team that never kills is a broken harness, not an imbalance")
    # positional sampling: every match must register at least one heatmap sample (bots existed and
    # were located). The SESSION UNION of occupied cells is RECORDED for the report + drift-gated,
    # NOT hard-floored — current bots strafe in place, and that thinness is honest signal for the
    # feel-tuning bundle, not a reason to reject the telemetry.
    session_cells: set[tuple[int, int]] = set()
    for m in matches:
        heatmap = m.get("heatmap") if isinstance(m.get("heatmap"), dict) else {}
        cells = _num(heatmap.get("occupied_cells"))
        if cells is None or cells < 1:
            issues.append(f"match {m.get('index')!r}: heatmap occupied_cells {cells!r} — "
                          "bots never sampled")
        grid = heatmap.get("grid") if isinstance(heatmap.get("grid"), list) else []
        for x, row in enumerate(grid):
            if not isinstance(row, list):
                continue
            for y, count in enumerate(row):
                if isinstance(count, (int, float)) and count > 0:
                    session_cells.add((x, y))
    for m in matches:
        if m.get("wane_variant") is not True:
            continue
        wane = m.get("wane") if isinstance(m.get("wane"), dict) else {}
        curve = wane.get("progress_curve") if isinstance(wane.get("progress_curve"), list) else []
        points = [(_num(p.get("t")), _num(p.get("p"))) for p in curve if isinstance(p, dict)]
        points = [(t, p) for t, p in points if t is not None and p is not None]
        if len(points) < 3:
            issues.append(f"match {m.get('index')!r}: wane progress curve missing/too short")
            continue
        if any(points[i + 1][1] < points[i][1] for i in range(len(points) - 1)):
            issues.append(f"match {m.get('index')!r}: wane progress curve not monotonic "
                          "non-decreasing — the collapse front went backwards")
        if points[-1][1] < WANE_PROGRESS_MIN:
            issues.append(f"match {m.get('index')!r}: wane sweep ended at {points[-1][1]:.2f} < "
                          f"{WANE_PROGRESS_MIN} — the line never crossed the arena")
    checks["sanity_invariants"] = {"passed": not issues, "issues": issues,
                                   "ttk_samples": len(all_ttk),
                                   "ttk_avg_s": agg.get("ttk_avg_s"),
                                   "team_a_win_rate": agg.get("team_a_win_rate"),
                                   "team_a_elims": team_a_elims, "team_b_elims": team_b_elims,
                                   "heatmap_union_cells": len(session_cells),
                                   "accuracy": accuracy}

    # aggregate cross-check — the reported headline must equal the recomputed truth
    issues = []
    reported = telemetry.get("aggregates") if isinstance(telemetry.get("aggregates"), dict) else {}
    if not reported:
        issues.append("aggregates block missing from telemetry")
    else:
        for key, truth in agg.items():
            got = _num(reported.get(key)) if truth is not None else reported.get(key)
            if truth is None:
                continue
            if got is None:
                issues.append(f"aggregate {key} missing from reported block")
                continue
            tolerance = max(abs(truth) * AGG_TOLERANCE, 1e-9)
            if abs(got - truth) > tolerance:
                issues.append(f"aggregate {key} reported {got!r} diverges from recomputed "
                              f"{truth!r} (tolerance {tolerance:.4f}) — fabricated headline")
    checks["aggregate_recompute"] = {"passed": not issues, "issues": issues,
                                     "recomputed": agg}
    return checks


def compute_drift_check(telemetry: dict, baseline: dict | None) -> dict:
    """Drift gates vs the PINNED baseline. Fail-closed: no baseline -> failed check (the suite
    surfaces it as the blocking reason). Bands are relative except team_a_win_rate (absolute)."""
    current = recompute_aggregates(_matches_of(telemetry if isinstance(telemetry, dict) else {}))
    if not isinstance(baseline, dict) or not isinstance(baseline.get("aggregates"), dict):
        return {"passed": False,
                "issues": ["pinned baseline missing/unreadable — pin "
                           "artifacts/bot_balance/baseline/bot_balance_baseline.json after "
                           "own-eyes review (A2: design gets receipts)"],
                "current": current, "baseline": None}
    base = baseline["aggregates"]
    issues = []
    deltas: dict[str, dict] = {}
    for key, band in DRIFT_BANDS.items():
        cur = _num(current.get(key))
        ref = _num(base.get(key))
        if cur is None or ref is None:
            issues.append(f"drift {key}: current {cur!r} / baseline {ref!r} uncomputable")
            continue
        if key == "team_a_win_rate":
            delta = abs(cur - ref)
            deltas[key] = {"current": cur, "baseline": ref, "abs_delta": round(delta, 4), "band": band}
            if delta > band:
                issues.append(f"drift {key}: |{cur:.3f} - {ref:.3f}| = {delta:.3f} > band {band}")
        else:
            rel = abs(cur - ref) / abs(ref) if ref != 0 else float("inf")
            deltas[key] = {"current": cur, "baseline": ref, "rel_delta": round(rel, 4), "band": band}
            if rel > band:
                issues.append(f"drift {key}: {cur!r} vs baseline {ref!r} — "
                              f"{rel * 100.0:.1f}% > band {band * 100.0:.0f}%")
    return {"passed": not issues, "issues": issues, "deltas": deltas,
            "baseline_pinned_at": baseline.get("pinned_at")}


def _recompute_evidence_binding(result: dict) -> dict:
    """Telemetry must be flag-marked, pid-bound to the launched process, and exe-sha-bound to the
    current package manifest. Recomputed here so a tampered stored check can't survive."""
    issues = []
    telemetry = result.get("telemetry")
    if not isinstance(telemetry, dict):
        return {"passed": False, "issues": ["telemetry payload missing from result"], "pid": None}
    if str(telemetry.get("flag") or "") != FLAG:
        issues.append(f"telemetry flag {telemetry.get('flag')!r} != {FLAG!r}")
    launched_pid = result.get("launched_pid")
    telemetry_pid = telemetry.get("pid")
    if not isinstance(launched_pid, int) or not isinstance(telemetry_pid, int) or telemetry_pid != launched_pid:
        issues.append(f"telemetry pid {telemetry_pid!r} does not match launched pid {launched_pid!r}")
    binding = result.get("package_binding") if isinstance(result.get("package_binding"), dict) else {}
    if binding.get("matches") is not True:
        issues.append("package binding not verified (matches != True)")
    manifest_sha = str(binding.get("manifest_sha256") or "")
    run_sha = str(binding.get("exe_sha256_at_run") or "")
    if len(manifest_sha) != 64 or manifest_sha != run_sha:
        issues.append("executable sha256 at run does not match package manifest sha256")
    archive_dir = str(binding.get("archive_dir") or "")
    executable = str(telemetry.get("executable") or "")
    if not archive_dir or not executable:
        issues.append("archive_dir/executable missing from binding evidence")
    elif Path(archive_dir.lower()) not in Path(executable.lower()).parents:
        issues.append(f"telemetry executable {executable!r} is not inside archive dir {archive_dir!r}")
    return {"passed": not issues, "issues": issues, "pid": telemetry_pid,
            "executable": executable or None, "archive_dir": archive_dir or None}


def _freshness(result: dict, max_age_seconds: int) -> dict:
    captured = _num(result.get("captured_at"))
    if captured is None:
        return {"passed": False, "issues": ["captured_at missing/non-numeric"], "age_seconds": None}
    age = time.time() - captured
    if age > max_age_seconds:
        return {"passed": False,
                "issues": [f"telemetry is {age / 3600.0:.1f}h old > ceiling "
                           f"{max_age_seconds / 3600.0:.1f}h — rerun the bot-balance lane"],
                "age_seconds": round(age, 1)}
    return {"passed": True, "issues": [], "age_seconds": round(age, 1)}


def validate_bot_balance_result(
    path: Path | str = RESULT_PATH,
    baseline_path: Path | str = BASELINE_PATH,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict:
    result_path = Path(path)
    if not result_path.exists():
        raise BlockedError(f"bot-balance result missing: {result_path}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"bot-balance result unreadable: {exc}") from exc
    if not isinstance(result, dict):
        raise BlockedError(f"bot-balance result root is not an object: {result_path}")

    baseline = None
    bp = Path(baseline_path)
    if bp.exists():
        try:
            baseline = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:
            baseline = None

    result = dict(result)
    checks = dict(result.get("checks") or {})
    telemetry = result.get("telemetry") if isinstance(result.get("telemetry"), dict) else {}

    # recomputation law: every gate is derived from the payload every time
    checks["freshness"] = _freshness(result, max_age_seconds=max_age_seconds)
    checks["telemetry_evidence_bound"] = _recompute_evidence_binding(result)
    checks.update(compute_telemetry_checks(telemetry))
    checks["baseline_drift"] = compute_drift_check(telemetry, baseline)

    result["checks"] = checks
    result["aggregates_recomputed"] = recompute_aggregates(_matches_of(telemetry))
    result["suite_pass"] = bool(checks) and all(bool(check.get("passed")) for check in checks.values())
    result["state"] = "PASS" if result["suite_pass"] else "BLOCKED"
    return result


def _make_report(result: dict, report_path: Path) -> str:
    checks = result.get("checks") or {}
    agg = result.get("aggregates_recomputed") or {}
    lines = [
        "# WANEFALL Bot-Balance Telemetry Report (BOT_BALANCE_TELEMETRY_HARNESS_V1)",
        "",
        f"State: {result.get('state')}",
        f"Suite pass: {result.get('suite_pass')}",
        f"Launched pid: {result.get('launched_pid')}",
        "",
        "## Aggregates (recomputed from per-match telemetry)",
    ]
    for key, value in agg.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Checks"])
    for name, check in checks.items():
        lines.append(f"- {name}: passed={check.get('passed')} issues={check.get('issues', [])}")
    lines.extend([
        "",
        "## Boundaries",
        "- Floors + drift bands are ratchet-only; this report never weakens a gate.",
        "- No HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE state was written.",
        "- Missing/unbound telemetry or a missing pinned baseline stays BLOCKED, never fake green.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


class BotBalanceTelemetryPipeline(ProductionPipeline):
    name = "bot_balance_telemetry"
    kind = "bot_balance_telemetry"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "wanefall_win64_development_botmatch")
        output_dir = Path(task.get("output_dir") or RESULT_DIR)
        matches = int(task.get("matches") or 12)
        seed = int(task.get("seed") or 20260702)
        wane_every = int(task.get("wane_every") or 3)
        max_seconds = int(task.get("max_seconds") or 180)
        # -abslog to our OWN file: this is a player-neutralized bot-vs-bot session, so if it wrote
        # to the packaged archive's Saved/Logs/WanefallGreybox.log it would clobber the packaged
        # gameplay-smoke log that the wane_fx packaged-marker gate scans for PLAYER muzzle/impact
        # [WaneFX] spawns (live truth 2026-07-02: the bot session overwrote it and REJECTED
        # wane_fx). Keeping our log outside the packaged log dirs leaves the smoke evidence intact.
        bot_log = Path(output_dir) / "logs" / "bot_match_session.log"
        launch_args = [
            f"{ARENA_MAP_URL}",
            "-nullrhi",
            "-nosound",
            "-unattended",
            "-deterministic",
            f"-fps={FIXED_FPS}",
            f"-abslog={bot_log}",
            f"-{FLAG}",
            f"-BotMatchCount={matches}",
            f"-BotMatchSeed={seed}",
            f"-BotMatchMaxSeconds={max_seconds}",
            f"-BotMatchWaneEvery={wane_every}",
        ]
        return {
            "asset_id": asset_id,
            "output_dir": output_dir,
            "result_path": output_dir / RESULT_PATH.name,
            "telemetry_copy_path": output_dir / "bot_match_telemetry.json",
            "local_report": output_dir / LOCAL_REPORT.name,
            "baseline_path": Path(task.get("baseline_path") or BASELINE_PATH),
            "packaged_result_path": Path(task.get("packaged_result_path") or PACKAGED_RESULT_PATH),
            "packaged_manifest_path": Path(task.get("packaged_manifest_path") or PACKAGED_MANIFEST_PATH),
            "archive_dir": task.get("archive_dir"),
            "launch_args": launch_args,
            "matches": matches,
            # generous ceiling: fixed-timestep headless matches run much faster than game time,
            # but a slow box must not turn a good session into a truncated one
            "session_timeout_seconds": int(task.get("session_timeout_seconds")
                                           or (matches * max_seconds + 600)),
            "poll_seconds": float(task.get("poll_seconds") or 5.0),
        }

    # ------------------------------------------------------------------ execution

    def execute(self, plan: dict) -> Artifact:
        result = self._run_bot_match_session(plan)
        _write_json(Path(plan["result_path"]), result)
        _make_report(result, Path(plan["local_report"]))
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={
                "result_path": str(plan["result_path"]),
                "suite_pass": bool(result.get("suite_pass")),
                "aggregates": result.get("aggregates_recomputed"),
            },
            provenance={"source": "local_wanefall_packaged_bot_match_telemetry",
                        "license": "operator-owned-game"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_bot_balance_result(Path(plan["result_path"]),
                                             baseline_path=Path(plan["baseline_path"]),
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
            evidence=[str(plan["result_path"]), str(plan["telemetry_copy_path"])],
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

    def _run_bot_match_session(self, plan: dict) -> dict:
        started_at = time.time()
        output_dir = Path(plan["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "logs").mkdir(parents=True, exist_ok=True)   # -abslog target parent

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
        telemetry_json = saved_dir / TELEMETRY_RELATIVE
        if telemetry_json.exists():
            telemetry_json.unlink()                          # fresh-run truth: no stale evidence

        observations: dict = {"binding": binding}
        proc = None
        telemetry_payload: dict = {}
        try:
            cmd = [str(executable)] + [str(a) for a in plan["launch_args"]]
            proc = subprocess.Popen(cmd, cwd=str(executable.parent))
            observations["command"] = cmd
            telemetry_payload = self._wait_for_telemetry(plan, telemetry_json, proc)
        except BlockedError:
            raise
        except Exception as exc:
            observations["error"] = repr(exc)
        finally:
            self._terminate_process(proc)

        if telemetry_payload:
            _write_json(Path(plan["telemetry_copy_path"]), telemetry_payload)

        result = {
            "schema_version": 1,
            "captured_at": time.time(),
            "run_started_at": started_at,
            "asset_id": plan["asset_id"],
            "launched_pid": (proc.pid if proc else None),
            "package_binding": binding,
            "telemetry": telemetry_payload,
            "packaged_log_scan": self._scan_packaged_log(archive_dir),
            "observations": observations,
            "result_path": str(plan["result_path"]),
            "local_report": str(plan["local_report"]),
            "operator_only_states_written": [],
        }
        _write_json(Path(plan["result_path"]), result)
        return validate_bot_balance_result(Path(plan["result_path"]),
                                           baseline_path=Path(plan["baseline_path"]),
                                           max_age_seconds=DEFAULT_MAX_AGE_SECONDS)

    def _wait_for_telemetry(self, plan: dict, telemetry_json: Path, proc) -> dict:
        """Poll the flushed telemetry until finalized with the requested match count (or the
        session process exits / deadline passes). Returns the last parsed payload ({} if never
        readable — downstream gates then fail closed)."""
        deadline = time.time() + float(plan["session_timeout_seconds"])
        payload: dict = {}
        while time.time() < deadline:
            candidate = self._read_json_safe(telemetry_json)
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                if payload.get("finalized") is True and \
                        len(payload.get("matches") or []) >= int(plan["matches"]):
                    break
            if proc is not None and proc.poll() is not None:
                # session exited: give the final flush a beat, read once more, stop
                time.sleep(2.0)
                candidate = self._read_json_safe(telemetry_json)
                if isinstance(candidate, dict) and candidate:
                    payload = candidate
                break
            time.sleep(float(plan["poll_seconds"]))
        return payload

    @staticmethod
    def _read_json_safe(path: Path):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
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
