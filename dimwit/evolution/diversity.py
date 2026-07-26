"""Advisory quality-diversity planning over Dimwit's experiment ledger.

This module deliberately has no mutation or execution authority.  It turns prior experiment outcomes into
inspectable family-level exploration weights, cooldown advice, and a champion archive.  The recursive
improvement controller remains responsible for budgets, validator comparisons, quarantine, and the hard
PROMOTED_TO_REVIEW ceiling.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


PROTECTED_FAMILIES = frozenset({"validation", "release"})

PIPELINE_FAMILIES = {
    "packaged_build_validation": "release",
    "performance_baseline": "release",
    "real_game_validation": "validation",
    "self_metrics_director": "validation",
    "unreal_game_builder_engine": "validation",
    "bot_balance_telemetry": "gameplay",
    "progression": "gameplay",
    "ui_settings_persistence": "experience",
    "audio": "experience",
    "vfx": "experience",
    "materials_shaders": "world",
    "environment": "world",
    "flagship_arena_art_pass": "world",
    "character_roster_policy": "character",
    "character_source_sync": "character",
    "character_fidelity": "character",
    "rigging": "character",
    "animation": "character",
    "metahuman_output_attempt": "character",
}


def family_for_pipeline(pipeline: str) -> str:
    """Return a stable improvement family without trusting free-form task metadata."""
    name = str(pipeline or "").strip().lower()
    if name in PIPELINE_FAMILIES:
        return PIPELINE_FAMILIES[name]
    for token, family in (
        ("valid", "validation"), ("build", "release"), ("package", "release"),
        ("character", "character"), ("rig", "character"), ("anim", "character"),
        ("world", "world"), ("environment", "world"), ("material", "world"),
        ("ui", "experience"), ("audio", "experience"), ("vfx", "experience"),
        ("game", "gameplay"), ("combat", "gameplay"), ("progress", "gameplay"),
        ("tool", "toolchain"), ("blender", "toolchain"), ("unreal", "toolchain"),
    ):
        if token in name:
            return family
    return "other"


def _fitness_value(detail: dict[str, Any]) -> float:
    after = detail.get("fitness_after") if isinstance(detail.get("fitness_after"), dict) else {}
    blockers = after.get("blocker_counts") if isinstance(after.get("blocker_counts"), dict) else {}
    hard = sum(int(blockers.get(state, 0) or 0) for state in ("BLOCKED", "FAIL", "REJECTED"))
    return round(float(after.get("pass_rate", 0.0) or 0.0) * 1000.0 - hard * 100.0, 6)


def build_diversity_plan(entries: list[dict], now: float | None = None,
                         cooldown_seconds: float = 86400.0) -> dict:
    """Build an advisory family plan from append-only experiment evidence.

    Repeated non-improving attempts increase exploration pressure. Three consecutive regressions advise a
    family cooldown, except validation/release families which are never suppressed. A per-family champion is
    retained only from review-eligible experiments; no outcome is promoted automatically.
    """
    now = float(time.time() if now is None else now)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        pipeline = str(detail.get("pipeline") or "")
        grouped[family_for_pipeline(pipeline)].append(entry)

    families = sorted(set(PIPELINE_FAMILIES.values()) | set(grouped) | {"toolchain", "other"})
    family_rows: dict[str, dict] = {}
    champions: dict[str, dict] = {}
    for family in families:
        rows = sorted(grouped.get(family, []), key=lambda row: float(row.get("ts") or 0))
        attempts = successes = regressions = consecutive_non_success = consecutive_regressions = 0
        last_regression_ts = 0.0
        champion: dict | None = None
        champion_value = float("-inf")
        for entry in rows:
            detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
            attempts += 1
            eligible = bool(detail.get("eligible_for_review"))
            regressed = str(detail.get("disposition") or "") == "REGRESSION_QUARANTINED"
            if eligible:
                successes += 1
                consecutive_non_success = 0
                consecutive_regressions = 0
                value = _fitness_value(detail)
                if champion is None or value >= champion_value:
                    champion_value = value
                    champion = {
                        "task_key": detail.get("task_key"), "pipeline": detail.get("pipeline"),
                        "candidate_hash": entry.get("candidate_hash"), "ts": entry.get("ts"),
                        "fitness_value": value, "status": "REVIEW_ELIGIBLE_ONLY",
                    }
            else:
                consecutive_non_success += 1
                if regressed:
                    regressions += 1
                    consecutive_regressions += 1
                    last_regression_ts = max(last_regression_ts, float(entry.get("ts") or 0))
                else:
                    consecutive_regressions = 0

        novelty = 1.5 if attempts == 0 else 1.0
        pressure = min(3.0, novelty + 0.25 * consecutive_non_success)
        regression_damping = 1.0 / (1.0 + 0.35 * regressions)
        diversity_score = round(pressure * regression_damping, 6)
        advised_cooldown = bool(
            family not in PROTECTED_FAMILIES
            and consecutive_regressions >= 3
            and last_regression_ts
            and now - last_regression_ts < cooldown_seconds
        )
        row = {
            "family": family, "attempts": attempts, "review_eligible": successes,
            "regressions": regressions, "consecutive_non_success": consecutive_non_success,
            "consecutive_regressions": consecutive_regressions, "exploration_pressure": round(pressure, 6),
            "diversity_score": diversity_score, "protected": family in PROTECTED_FAMILIES,
            "advisory_cooldown": advised_cooldown,
            "candidate_budget": max(1, min(4, int(round(pressure)))),
        }
        family_rows[family] = row
        if champion is not None:
            champions[family] = champion

    return {
        "schema_version": 1, "authority": "ADVISORY_ONLY", "review_ceiling": "PROMOTED_TO_REVIEW",
        "protected_families": sorted(PROTECTED_FAMILIES), "families": family_rows,
        "champion_archive": champions,
        "invariants": [
            "diversity weights cannot execute or promote candidates",
            "validator evidence remains lexicographically authoritative",
            "validation and release families are never cooled down",
            "champions are review-eligible evidence, not accepted production state",
        ],
    }
