from __future__ import annotations

import tempfile
from pathlib import Path

from dimwit.improvement import (
    ImprovementPolicy,
    RecursiveImprovementController,
    compare_validation_reports,
    rank_tasks,
    select_budgeted_tasks,
)


def _row(validator_id, domain, state="PASS", severity="blocker"):
    return {"validator_id": validator_id, "domain": domain, "state": state, "severity": severity}


def _report(*rows, verdict="PASS", ts=1):
    return {"suite_verdict": verdict, "run_ts": ts, "results": list(rows)}


def test_delta_accepts_resolved_validator_without_regression():
    before = _report(_row("fresh", "performance_baseline", "FAIL"), verdict="FAIL")
    after = _report(_row("fresh", "performance_baseline", "PASS"), verdict="PASS", ts=2)
    delta = compare_validation_reports(before, after)
    assert delta["disposition"] == "IMPROVED_CANDIDATE"
    assert delta["resolved"][0]["validator"].endswith(":fresh")


def test_delta_quarantines_worsened_or_missing_evidence():
    before = _report(_row("a", "alpha", "PASS"), _row("b", "beta", "BLOCKED"))
    after = _report(_row("a", "alpha", "FAIL"), ts=2)
    delta = compare_validation_reports(before, after)
    assert delta["disposition"] == "REGRESSION_QUARANTINED"
    assert {row["validator"] for row in delta["regressed"]} == {"alpha:a", "beta:b"}


def test_evidence_ranking_beats_high_static_priority():
    tasks = [
        {"pipeline": "audio", "asset_id": "sfx", "priority": 100, "expected_value": 1, "cost": 1},
        {"pipeline": "performance_baseline", "asset_id": "perf", "priority": 1, "expected_value": 1, "cost": 2},
    ]
    report = _report(_row("perf_baseline_result_fresh", "performance_baseline", "REJECTED"))
    ranked = rank_tasks(tasks, report)
    assert ranked[0]["pipeline"] == "performance_baseline"
    assert ranked[0]["evidence_score"] > 0


def test_budget_selection_skips_quarantined_and_over_budget_tasks():
    policy = ImprovementPolicy(max_tasks=2, max_total_cost=3)
    ranked = [
        {"task_key": "a:1", "cost": 1.0, "quarantined": True, "quarantine_reason": "cooldown"},
        {"task_key": "b:1", "cost": 2.0, "quarantined": False},
        {"task_key": "c:1", "cost": 2.0, "quarantined": False},
    ]
    selected = select_budgeted_tasks(ranked, policy)
    assert [row["task_key"] for row in selected["selected"]] == ["b:1"]
    assert len(selected["skipped"]) == 2


class _Result:
    state = "PROMOTED_TO_REVIEW"
    score = 1.0


class _Pipeline:
    def run(self, task):
        return _Result()


def test_controller_only_queues_non_regressing_candidate_for_review():
    tmp = Path(tempfile.mkdtemp(prefix="dimwit_improvement_test_"))
    (tmp / "config").mkdir(parents=True)
    reports = iter([
        _report(_row("x", "performance_baseline", "FAIL"), verdict="FAIL"),
        _report(_row("x", "performance_baseline", "PASS"), verdict="PASS", ts=2),
    ])
    controller = RecursiveImprovementController(
        root=tmp,
        policy=ImprovementPolicy(max_tasks=1, max_total_cost=2),
        pipeline_factory=lambda name: _Pipeline(),
        pipeline_names=lambda: ["performance_baseline"],
        validate_fn=lambda: next(reports),
        ledger_path=tmp / "ledger" / "experiments.jsonl",
        artifact_path=tmp / "artifacts" / "run.json",
    )
    result = controller.run([{"pipeline": "performance_baseline", "asset_id": "perf", "cost": 1}], execute=True)
    assert result["state"] == "CANDIDATES_READY_FOR_REVIEW"
    assert result["eligible_review_queue"][0]["pipeline"] == "performance_baseline"
    assert result["operator_only_states_written"] == []


def test_controller_quarantines_regression_and_withholds_review():
    tmp = Path(tempfile.mkdtemp(prefix="dimwit_improvement_regression_"))
    (tmp / "config").mkdir(parents=True)
    reports = iter([
        _report(_row("x", "performance_baseline", "PASS")),
        _report(_row("x", "performance_baseline", "REJECTED"), verdict="REJECTED", ts=2),
    ])
    controller = RecursiveImprovementController(
        root=tmp,
        policy=ImprovementPolicy(max_tasks=1, max_total_cost=2),
        pipeline_factory=lambda name: _Pipeline(),
        pipeline_names=lambda: ["performance_baseline"],
        validate_fn=lambda: next(reports),
        ledger_path=tmp / "ledger" / "experiments.jsonl",
        artifact_path=tmp / "artifacts" / "run.json",
    )
    result = controller.run([{"pipeline": "performance_baseline", "asset_id": "perf", "cost": 1}], execute=True)
    assert result["state"] == "REGRESSION_QUARANTINED"
    assert result["eligible_review_queue"] == []
    assert result["quarantined"]
