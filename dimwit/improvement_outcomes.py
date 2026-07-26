"""Operator-owned outcomes for recursive-improvement proposals.

Automation may create review-eligible proposals, but only an identified human reviewer may
record whether a proposal was accepted or rejected.  Outcomes are chained in a separate ledger
so experiment history stays immutable and the controller's hit rate can be measured honestly.
"""
from __future__ import annotations

import time
from pathlib import Path

from dimwit.engine import DimwitLedger


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = frozenset({"ACCEPTED", "REJECTED"})
AUTOMATION_ACTOR_TOKENS = ("codex", "claude", "agent", "automation", "recursive", "bot")


def _entries(path: Path) -> list[dict]:
    try:
        return DimwitLedger(path).entries()
    except (OSError, ValueError, TypeError):
        return []


def _eligible_proposals(entries: list[dict]) -> dict[str, dict]:
    proposals: dict[str, dict] = {}
    for row in entries:
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        task_key = str(detail.get("task_key") or "").strip()
        candidate_hash = str(row.get("candidate_hash") or "").strip()
        if task_key and candidate_hash and detail.get("eligible_for_review") is True:
            proposals[candidate_hash] = {
                "task_key": task_key,
                "candidate_hash": candidate_hash,
                "pipeline": detail.get("pipeline"),
                "experiment_ts": row.get("ts"),
            }
    return proposals


def summarize_outcomes(
    experiment_ledger: Path | None = None,
    outcome_ledger: Path | None = None,
) -> dict:
    experiment_path = Path(experiment_ledger or ROOT / "ledger" / "improvement_experiments.jsonl")
    outcome_path = Path(outcome_ledger or ROOT / "ledger" / "improvement_outcomes.jsonl")
    proposals = _eligible_proposals(_entries(experiment_path))
    decisions: dict[str, dict] = {}
    orphaned = 0
    for row in _entries(outcome_path):
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        proposal_hash = str(detail.get("proposal_hash") or "")
        decision = str(detail.get("decision") or "").upper()
        if proposal_hash not in proposals or decision not in DECISIONS:
            orphaned += 1
            continue
        decisions[proposal_hash] = row
    accepted = sum((row.get("detail") or {}).get("decision") == "ACCEPTED" for row in decisions.values())
    rejected = sum((row.get("detail") or {}).get("decision") == "REJECTED" for row in decisions.values())
    decided = accepted + rejected
    return {
        "schema_version": 1,
        "state": "PASS" if orphaned == 0 else "BLOCKED",
        "eligible_proposals": len(proposals),
        "decided": decided,
        "accepted": accepted,
        "rejected": rejected,
        "pending": max(0, len(proposals) - decided),
        "hit_rate": round(accepted / decided, 4) if decided else None,
        "orphaned_outcomes": orphaned,
        "authority": "HUMAN_REVIEWER_ONLY",
        "review_ceiling": "PROMOTED_TO_REVIEW",
    }


def record_outcome(
    task_key: str,
    decision: str,
    reviewer: str,
    rationale: str,
    *,
    experiment_ledger: Path | None = None,
    outcome_ledger: Path | None = None,
    now: float | None = None,
) -> dict:
    """Append one human decision for the latest eligible proposal matching ``task_key``."""
    task_key = str(task_key or "").strip()
    decision = str(decision or "").strip().upper()
    reviewer = str(reviewer or "").strip()
    rationale = str(rationale or "").strip()
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    if not task_key:
        raise ValueError("task_key is required")
    if len(reviewer) < 2 or any(token in reviewer.lower() for token in AUTOMATION_ACTOR_TOKENS):
        raise ValueError("reviewer must identify a human operator, not an automated actor")
    if len(rationale) < 8:
        raise ValueError("rationale must contain at least 8 characters")

    experiment_path = Path(experiment_ledger or ROOT / "ledger" / "improvement_experiments.jsonl")
    outcome_path = Path(outcome_ledger or ROOT / "ledger" / "improvement_outcomes.jsonl")
    matches = [row for row in _eligible_proposals(_entries(experiment_path)).values() if row["task_key"] == task_key]
    if not matches:
        raise ValueError(f"no review-eligible experiment exists for task {task_key!r}")
    proposal = sorted(matches, key=lambda row: float(row.get("experiment_ts") or 0))[-1]
    prior = _entries(outcome_path)
    if any((row.get("detail") or {}).get("proposal_hash") == proposal["candidate_hash"] for row in prior):
        raise ValueError("an outcome is already recorded for this proposal")

    timestamp = int(now if now is not None else time.time())
    entry = {
        "ts": timestamp,
        "actor": f"human-reviewer:{reviewer}",
        "asset_id": task_key,
        "state": f"improvement_review.{decision}",
        "candidate_hash": proposal["candidate_hash"],
        "detail": {
            "task_key": task_key,
            "pipeline": proposal.get("pipeline"),
            "proposal_hash": proposal["candidate_hash"],
            "decision": decision,
            "reviewer": reviewer,
            "rationale": rationale,
            "operator_recorded": True,
        },
    }
    DimwitLedger(outcome_path).append(entry)
    return entry
