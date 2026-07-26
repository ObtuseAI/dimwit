from __future__ import annotations

from pathlib import Path

import pytest

from dimwit.engine import DimwitLedger
from dimwit.improvement_outcomes import record_outcome, summarize_outcomes


def _eligible(path: Path, task: str, candidate_hash: str) -> None:
    DimwitLedger(path).append({
        "ts": 10,
        "actor": "recursive-improvement-controller",
        "asset_id": task,
        "state": "improvement.STABLE_CANDIDATE",
        "candidate_hash": candidate_hash,
        "detail": {"task_key": task, "pipeline": "performance_baseline", "eligible_for_review": True},
    })


def test_operator_outcomes_measure_hit_rate_without_crossing_review_ceiling(tmp_path):
    experiments = tmp_path / "experiments.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    _eligible(experiments, "task-a", "a" * 64)
    _eligible(experiments, "task-b", "b" * 64)

    row = record_outcome(
        "task-a", "accepted", "Chris", "Improved the held-out proof.",
        experiment_ledger=experiments, outcome_ledger=outcomes, now=20,
    )
    assert row["state"] == "improvement_review.ACCEPTED"
    assert row["actor"] == "human-reviewer:Chris"
    assert "HUMAN_ACCEPTED" not in row["state"]

    summary = summarize_outcomes(experiments, outcomes)
    assert summary == {
        "schema_version": 1, "state": "PASS", "eligible_proposals": 2,
        "decided": 1, "accepted": 1, "rejected": 0, "pending": 1,
        "hit_rate": 1.0, "orphaned_outcomes": 0,
        "authority": "HUMAN_REVIEWER_ONLY", "review_ceiling": "PROMOTED_TO_REVIEW",
    }


def test_outcome_requires_human_identity_and_single_decision(tmp_path):
    experiments = tmp_path / "experiments.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    _eligible(experiments, "task-a", "a" * 64)
    with pytest.raises(ValueError, match="human operator"):
        record_outcome("task-a", "accepted", "codex-agent", "Looks good enough", experiment_ledger=experiments, outcome_ledger=outcomes)
    record_outcome("task-a", "rejected", "Chris", "Regression in packaged proof.", experiment_ledger=experiments, outcome_ledger=outcomes)
    with pytest.raises(ValueError, match="already recorded"):
        record_outcome("task-a", "accepted", "Chris", "Changed my mind after review.", experiment_ledger=experiments, outcome_ledger=outcomes)


def test_outcome_refuses_unknown_or_noneligible_proposal(tmp_path):
    with pytest.raises(ValueError, match="no review-eligible"):
        record_outcome("missing", "rejected", "Chris", "No qualifying evidence.", experiment_ledger=tmp_path / "none.jsonl", outcome_ledger=tmp_path / "out.jsonl")
