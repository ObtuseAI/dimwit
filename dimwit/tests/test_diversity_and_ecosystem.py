from __future__ import annotations

import json

from dimwit.evolution.diversity import build_diversity_plan, family_for_pipeline
from dimwit.opensource_adoption import audit_ecosystem, validate_candidate


def _entry(ts: int, pipeline: str, disposition: str, eligible: bool = False, pass_rate: float = 0.0) -> dict:
    return {
        "ts": ts,
        "candidate_hash": f"hash-{ts}",
        "detail": {
            "task_key": f"{pipeline}:asset", "pipeline": pipeline, "disposition": disposition,
            "eligible_for_review": eligible,
            "fitness_after": {"pass_rate": pass_rate, "blocker_counts": {}},
        },
    }


def test_diversity_plan_cools_repeated_regressions_but_never_protected_families():
    history = [
        _entry(90, "audio", "REGRESSION_QUARANTINED"),
        _entry(95, "audio", "REGRESSION_QUARANTINED"),
        _entry(99, "audio", "REGRESSION_QUARANTINED"),
        _entry(90, "performance_baseline", "REGRESSION_QUARANTINED"),
        _entry(95, "performance_baseline", "REGRESSION_QUARANTINED"),
        _entry(99, "performance_baseline", "REGRESSION_QUARANTINED"),
    ]
    plan = build_diversity_plan(history, now=100, cooldown_seconds=100)
    assert plan["families"]["experience"]["advisory_cooldown"] is True
    assert plan["families"]["release"]["protected"] is True
    assert plan["families"]["release"]["advisory_cooldown"] is False
    assert plan["authority"] == "ADVISORY_ONLY"


def test_diversity_champion_is_review_eligible_only_and_resets_stagnation():
    plan = build_diversity_plan([
        _entry(1, "rigging", "EVALUATION_BLOCKED"),
        _entry(2, "rigging", "IMPROVED_CANDIDATE", eligible=True, pass_rate=0.9),
    ], now=3)
    assert family_for_pipeline("rigging") == "character"
    assert plan["families"]["character"]["consecutive_non_success"] == 0
    assert plan["champion_archive"]["character"]["status"] == "REVIEW_ELIGIBLE_ONLY"


def test_unknown_license_is_rejected_even_for_high_value_source():
    issues = validate_candidate({
        "id": "x", "name": "x", "source_url": "https://github.com/example/x",
        "license": "UNKNOWN", "adoption_mode": "EVALUATE", "value": 5, "risk": 0, "integration_cost": 0,
    })
    assert "license is unknown or unverified" in issues


def test_default_ecosystem_registry_passes_without_installing_or_executing():
    report = audit_ecosystem()
    assert report["state"] == "PASS"
    assert report["candidate_count"] >= 10
    assert report["authority"] == "PLAN_ONLY_NO_INSTALL_OR_EXECUTION"
    assert "triposr" in report["evaluation_queue"]


def test_ecosystem_audit_fails_closed_on_invalid_registry(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"candidates": [{
        "id": "bad", "name": "bad", "source_url": "https://github.com/example/bad",
        "license": "UNKNOWN", "adoption_mode": "ADOPT_NOW", "value": 5, "risk": 0, "integration_cost": 0,
    }]}), encoding="utf-8")
    report = audit_ecosystem(path)
    assert report["state"] == "FAIL_CLOSED"
    assert report["rejected_count"] == 1
