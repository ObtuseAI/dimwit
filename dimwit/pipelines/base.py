"""Dimwit Production Pipelines — the unified, fully-proofed, recursively self-improving backbone.

Every WANEFALL production pipeline (character-fidelity, rigging, animation, environment, vfx, audio, materials,
...) subclasses `ProductionPipeline` and inherits, for free, the doctrine loop:

    plan  ->  execute  ->  qa(judge)  ->  repair(<= max_repairs)  ->  hash-chained proof ledger  ->  gate

Doctrine (inherited from Blunder/Dimwit, NEVER weakened):
  - plan/mock before execute; validate before promote.
  - QA is authoritative (GLM vision + pixel-truth + hard metrics). A judge may FAIL but never silently PASS.
  - thresholds ratchet UP only.
  - autonomous terminal ceiling = PROMOTED_TO_REVIEW; HUMAN_ACCEPTED / active-slice promotion is operator-gated.
  - provenance fail-closed; append-only, tamper-evident (hash-chained) ledger.

This module is pure-stdlib + reuses dimwit.engine.DimwitLedger and (optionally) dimwit.llm for GLM QA. It is
import-safe with no side effects; pipelines do the real work in execute()/qa()/repair().
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from dimwit.engine import DimwitLedger          # hash-chained, Dimwit-isolated proof ledger
from dimwit.core import sha256_obj as sha256      # canonical object hash

ROOT = Path(__file__).resolve().parents[2]          # Dimwit/


class State(str, Enum):
    REQUESTED = "REQUESTED"
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    QA_PASS = "QA_PASS"
    REPAIRING = "REPAIRING"
    PROMOTED_TO_REVIEW = "PROMOTED_TO_REVIEW"   # autonomous ceiling
    NEEDS_RECURSION = "NEEDS_RECURSION"         # ran out of repairs but salvageable
    REJECTED = "REJECTED"                       # hard-gate violation (e.g. provenance/style)
    BLOCKED = "BLOCKED"                         # missing input / environment / human input required


# Autonomous code may NEVER set these — operator only.
OPERATOR_ONLY = {"HUMAN_ACCEPTED", "PROMOTED_TO_ACTIVE_SLICE"}


@dataclass
class Verdict:
    """A QA judgement. `passed` gates promotion; `hard_fail` forces REJECTED regardless of score."""
    score: float = 0.0                 # 0..1
    passed: bool = False
    hard_fail: bool = False            # provenance/style/safety violation -> REJECTED, no recursion
    issues: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)   # paths to render/metric evidence (honest; [] if none)


@dataclass
class Artifact:
    """The thing a pipeline produces + proves. `data` carries pipeline-specific payload."""
    asset_id: str
    kind: str
    data: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)   # source + license (fail-closed if missing)

    @property
    def candidate_hash(self) -> str:
        return sha256({"asset_id": self.asset_id, "kind": self.kind, "data": self.data})


@dataclass
class PipelineResult:
    pipeline: str
    asset_id: str
    state: State
    score: float
    attempts: int
    verdict: Optional[Verdict] = None
    artifact: Optional[Artifact] = None
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "pipeline": self.pipeline, "asset_id": self.asset_id, "state": str(self.state),
            "score": self.score, "attempts": self.attempts, "notes": self.notes,
        }
        if self.verdict is not None:
            d["verdict"] = asdict(self.verdict)
        if self.artifact is not None:
            d["candidate_hash"] = self.artifact.candidate_hash
            d["provenance"] = self.artifact.provenance
        return d


class ProductionPipeline:
    """Base class. Subclasses implement plan/execute/qa/repair; run() drives the doctrine loop."""

    name: str = "abstract"
    kind: str = "artifact"

    def __init__(self, threshold: float = 0.70, max_repairs: int = 3, ledger_path: Optional[Path] = None):
        # thresholds ratchet UP only (a subclass/config can raise but base enforces a floor)
        self.threshold = max(0.0, float(threshold))
        self.max_repairs = int(max_repairs)
        self.ledger = DimwitLedger(ledger_path or (ROOT / "ledger" / "pipelines" / f"{self.name}.jsonl"))

    # ---- hooks subclasses implement -------------------------------------------------------------
    def plan(self, task: dict) -> dict:
        """Resolve inputs, validate provenance, produce an execution plan. Raise BlockedError if missing."""
        raise NotImplementedError

    def execute(self, plan: dict) -> Artifact:
        """Produce the artifact (real work: Blender/UE/etc.). Must NOT fabricate proof."""
        raise NotImplementedError

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        """Judge the artifact (GLM vision + pixel-truth + hard metrics). Authoritative."""
        raise NotImplementedError

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        """Mutate toward the threshold using the verdict's issues. Return the improved artifact."""
        raise NotImplementedError

    # ---- the doctrine loop ----------------------------------------------------------------------
    def run(self, task: dict) -> PipelineResult:
        asset_id = str(task.get("asset_id", task.get("name", "asset")))
        self._ledger(asset_id, State.REQUESTED, {"task": task})
        try:
            plan = self.plan(task)
        except BlockedError as e:
            return self._finish(asset_id, State.BLOCKED, 0.0, 0, notes=[f"blocked: {e}"])
        self._ledger(asset_id, State.PLANNED, {"plan_keys": sorted(plan.keys())})

        artifact = self.execute(plan)
        # provenance fail-closed: no promotable license + recorded source -> cannot promote
        if not self._provenance_ok(artifact):
            self._ledger(asset_id, State.REJECTED, {"reason": "provenance_fail_closed",
                                                    "provenance": artifact.provenance}, artifact)
            return self._finish(asset_id, State.REJECTED, 0.0, 0, artifact=artifact,
                                notes=["provenance fail-closed: missing promotable license/source"])
        self._ledger(asset_id, State.EXECUTED, {"hash": artifact.candidate_hash}, artifact)

        verdict = self.qa(artifact, plan)
        attempt = 0
        best = (artifact, verdict)
        while attempt < self.max_repairs:
            if verdict.hard_fail:
                self._ledger(asset_id, State.REJECTED, {"hard_fail": True, "issues": verdict.issues}, artifact)
                return self._finish(asset_id, State.REJECTED, verdict.score, attempt,
                                    verdict=verdict, artifact=artifact, notes=["hard gate failed"])
            if verdict.passed and verdict.score >= self.threshold:
                break
            attempt += 1
            self._ledger(asset_id, State.REPAIRING, {"attempt": attempt, "issues": verdict.issues}, artifact)
            artifact = self.repair(artifact, verdict, attempt, plan)
            verdict = self.qa(artifact, plan)
            if verdict.score >= best[1].score:           # keep-best
                best = (artifact, verdict)

        artifact, verdict = best                          # promote the best candidate seen
        if verdict.passed and verdict.score >= self.threshold and not verdict.hard_fail:
            self._ledger(asset_id, State.QA_PASS, {"score": verdict.score}, artifact)
            self._ledger(asset_id, State.PROMOTED_TO_REVIEW, {"score": verdict.score,
                         "evidence": verdict.evidence}, artifact)
            return self._finish(asset_id, State.PROMOTED_TO_REVIEW, verdict.score, attempt,
                                verdict=verdict, artifact=artifact,
                                notes=["autonomous ceiling reached; active-slice promotion is operator-gated"])
        self._ledger(asset_id, State.NEEDS_RECURSION, {"score": verdict.score, "issues": verdict.issues}, artifact)
        return self._finish(asset_id, State.NEEDS_RECURSION, verdict.score, attempt,
                            verdict=verdict, artifact=artifact, notes=["below threshold after repairs"])

    # ---- helpers --------------------------------------------------------------------------------
    def _provenance_ok(self, artifact: Artifact) -> bool:
        p = artifact.provenance or {}
        return bool(p.get("source")) and bool(p.get("license"))

    def _ledger(self, asset_id: str, state: State, detail: dict, artifact: Optional[Artifact] = None) -> None:
        # consistency_check requires asset_id + state + candidate_hash on every entry
        self.ledger.append({
            "ts": int(time.time()),
            "pipeline": self.name,
            "asset_id": asset_id,
            "state": str(state),
            "candidate_hash": artifact.candidate_hash if artifact else sha256({"asset_id": asset_id, "state": str(state)}),
            "detail": detail,
        })

    def _finish(self, asset_id, state, score, attempts, **kw) -> PipelineResult:
        return PipelineResult(pipeline=self.name, asset_id=asset_id, state=state,
                              score=round(float(score), 4), attempts=attempts, **kw)


class BlockedError(Exception):
    """Raised by plan() when a required input/environment is missing (fail-closed -> BLOCKED, not a fake pass)."""
