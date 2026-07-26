"""Dimwit DIRECTOR — the autonomous production loop that ties every pipeline into one self-driving engine.

It schedules pipeline tasks by priority/expected-value, runs each through its fully-proofed loop to the autonomous
ceiling (PROMOTED_TO_REVIEW), trips a per-pipeline circuit breaker after repeated failures (so it never spins), and
surfaces an operator REVIEW QUEUE (active-slice promotion stays human-gated). All on its own hash-chained ledger.

  python scripts/pipeline/run_director.py                 # run the default sweep (config/director_tasks.json)
  python scripts/pipeline/run_director.py --dry           # plan-only: validate every task's inputs/tools, run nothing
  python scripts/pipeline/run_director.py --review        # show the standing review queue (PROMOTED_TO_REVIEW awaiting operator)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from dimwit.pipelines import get_pipeline, list_pipelines, BlockedError
from dimwit.engine import DimwitLedger
from dimwit.core import sha256_obj

ROOT = Path(__file__).resolve().parents[1]              # Dimwit/
TASKS_CFG = ROOT / "config" / "director_tasks.json"
PIPE_LEDGER_DIR = ROOT / "ledger" / "pipelines"


class Director:
    def __init__(self, breaker_threshold: int = 3, ledger_path: Path | None = None,
                 breaker_path: Path | None = None):
        self.breaker_threshold = int(breaker_threshold)
        self.ledger = DimwitLedger(ledger_path or (ROOT / "ledger" / "director.jsonl"))
        self.breaker_path = Path(breaker_path or (ROOT / "ledger" / "breaker.json"))

    # ---- scheduling -----------------------------------------------------------------------------
    def order(self, tasks: list) -> list:
        # expected value = priority + expected_value - cost - fail_penalty; near-pass cheap wins first.
        def score(t):
            return (t.get("priority", 0) + t.get("expected_value", 1.0)
                    - t.get("cost", 1.0) - t.get("fail_penalty", 0.0))
        return sorted(tasks, key=score, reverse=True)

    # ---- the sweep ------------------------------------------------------------------------------
    def _breaker_path(self):
        return self.breaker_path

    @staticmethod
    def _task_key(pipeline: str, asset: str) -> str:
        # A failed character must not suppress every other asset using the same pipeline.
        return f"{pipeline}:{asset}"

    def _load_breaker(self) -> dict:
        p = self._breaker_path()
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                # Pre-v2 breaker keys were pipeline-wide and could suppress unrelated assets forever.  The
                # safe migration is to discard those coarse keys and learn per-task failures going forward.
                return {str(key): int(value) for key, value in raw.items() if ":" in str(key)}
            except Exception:
                return {}
        return {}

    def _save_breaker(self, breaker: dict):
        path = self._breaker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(breaker, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    def run_sweep(self, tasks: list, dry_run: bool = False) -> dict:
        out = {"ran": [], "review_queue": [], "blocked": [], "breaker": {}, "dry_run": dry_run}
        # G6 fix: the breaker PERSISTS across sweeps (an always-on loop must not re-burn UE boots on a doomed
        # pipeline every cron tick). Dry runs don't mutate the persisted breaker.
        breaker: dict = {} if dry_run else self._load_breaker()
        for t in self.order(tasks):
            name = t.get("pipeline")
            asset = t.get("asset_id")
            task_key = self._task_key(str(name), str(asset))
            if name not in list_pipelines():
                out["blocked"].append({"pipeline": name, "asset": asset, "why": "unknown pipeline"})
                continue
            failures = int(breaker.get(task_key, 0) or 0)
            if failures >= self.breaker_threshold:
                self._log(name, asset, "SKIPPED_BREAKER", {"task_key": task_key, "failures": failures})
                continue
            try:
                pipe = get_pipeline(name)
            except Exception as e:
                out["blocked"].append({"pipeline": name, "asset": asset, "why": f"import error: {e}"})
                breaker[task_key] = failures + 1
                continue

            if dry_run:
                try:
                    plan = pipe.plan({"asset_id": asset})
                    out["ran"].append({"pipeline": name, "asset": asset, "state": "PLAN_OK",
                                       "plan_keys": sorted(plan.keys())})
                    self._log(name, asset, "PLAN_OK", {})
                except BlockedError as e:
                    out["blocked"].append({"pipeline": name, "asset": asset, "why": str(e)})
                    self._log(name, asset, "BLOCKED", {"why": str(e)})
                except Exception as e:
                    out["blocked"].append({"pipeline": name, "asset": asset, "why": f"plan error: {e}"})
                continue

            try:
                res = pipe.run({"asset_id": asset})
            except Exception as e:
                # One broken optional pipeline must not abort the entire autonomous sweep.  Persist its
                # per-task breaker and continue; the final global validation remains authoritative.
                why = f"execution error: {type(e).__name__}: {e}"
                out["blocked"].append({"pipeline": name, "asset": asset, "why": why})
                breaker[task_key] = failures + 1
                self._log(name, asset, "EXECUTION_ERROR", {"task_key": task_key, "why": why})
                continue
            st = str(res.state).split(".")[-1]
            out["ran"].append({"pipeline": name, "asset": asset, "state": st, "score": res.score})
            self._log(name, asset, st, {"score": res.score})
            if st == "PROMOTED_TO_REVIEW":
                out["review_queue"].append({"pipeline": name, "asset": asset, "score": res.score})
                breaker[task_key] = 0
            else:
                breaker[task_key] = failures + 1
        out["breaker"] = breaker
        if not dry_run:
            self._save_breaker(breaker)              # persist for the next sweep/cron tick
        # "validate everything going forward": after a real sweep, validate every produced asset/feature.
        # The suite verdict gates whether the operator should trust the review queue.
        if not dry_run:
            rep = self.validate_everything()
            out["validation"] = {"suite_verdict": rep.get("suite_verdict"), "counts": rep.get("counts"),
                                 "error": rep.get("error")}
        return out

    # ---- validate everything (the permanent asset-validation suite) -----------------------------
    def validate_everything(self, domains=None) -> dict:
        """Run the full fail-closed validation suite over every produced asset/feature. Never raises
        (a harness error is reported, not fatal). Returns the suite report (or an error envelope)."""
        try:
            from dimwit.pipelines.validation import ValidationContext, ValidationSuite
            from dimwit.pipelines.validation_registry import REGISTRY
            suite = ValidationSuite(ValidationContext(), REGISTRY)
            rep = suite.run(domains)
            self._log("validation_suite", "*", rep.get("suite_verdict", "ERROR"),
                      {"counts": rep.get("counts")})
            return rep
        except Exception as e:
            return {"suite_verdict": "ERROR", "error": repr(e)}

    def validation_summary(self) -> dict:
        """Cheap read of the latest validation report (no run) for --review."""
        from dimwit.pipelines.validation import VAL_ART
        rp = VAL_ART / "validation_report.json"
        if not rp.exists():
            return {"suite_verdict": "NOT_RUN", "hint": "python scripts/pipeline/run_validation.py"}
        import json as _j
        r = _j.loads(rp.read_text(encoding="utf-8"))
        return {"suite_verdict": r.get("suite_verdict"), "counts": r.get("counts"), "run_ts": r.get("run_ts")}

    # ---- standing review queue (scan every pipeline ledger) -------------------------------------
    def review_queue(self) -> list:
        queue = []
        if not PIPE_LEDGER_DIR.exists():
            return queue
        for lf in sorted(PIPE_LEDGER_DIR.glob("*.jsonl")):
            seen_promoted = {}
            accepted = set()
            for ln in lf.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                e = json.loads(ln)
                st = e.get("state", "")
                aid = e.get("asset_id")
                if st.endswith("PROMOTED_TO_REVIEW"):
                    seen_promoted[aid] = e
                if "HUMAN_ACCEPTED" in st or "ACTIVE_SLICE" in st:
                    accepted.add(aid)
            for aid, e in seen_promoted.items():
                if aid not in accepted:
                    queue.append({"pipeline": lf.stem, "asset": aid,
                                  "candidate_hash": e.get("candidate_hash"),
                                  "score": (e.get("detail") or {}).get("score")})
        return queue

    def _log(self, pipeline, asset, state, detail):
        self.ledger.append({
            "ts": int(time.time()), "actor": "director", "pipeline": pipeline,
            "asset_id": asset or "*", "state": f"director.{state}",
            "candidate_hash": sha256_obj({"d": "director", "p": pipeline, "a": asset, "s": state}),
            "detail": detail,
        })


def load_tasks() -> list:
    if TASKS_CFG.exists():
        return json.loads(TASKS_CFG.read_text(encoding="utf-8")).get("tasks", [])
    return []
