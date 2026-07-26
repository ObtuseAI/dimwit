"""Dimwit SCHEDULER — the always-on autonomous heartbeat (closes G7). Turns Dimwit from one-shot batches into a
continuously self-running builder: each TICK does a fast health heartbeat (pipeline self-check + HUD snapshot,
ledgered), and a FULL tick additionally runs the fail-closed validation suite + a director sweep (autonomous
asset production to the PROMOTED_TO_REVIEW ceiling). Single-instance lockfile, abort sentinel, wall-clock
deadline, and the PERSISTENT circuit breaker keep an always-on loop safe on a disk/RAM-tight box.

  python dimwit.py loop --once               # one fast heartbeat tick
  python dimwit.py loop --ticks 5 --interval 1800     # 5 fast ticks, 30 min apart
  python dimwit.py loop --full --interval 3600        # full autonomous build+validate every hour (until stopped)
  (stop: create artifacts/control/SCHED_STOP, or Ctrl-C)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dimwit.engine import DimwitLedger
from dimwit.core import sha256_obj

ROOT = Path(__file__).resolve().parent.parent
CTRL = ROOT / "artifacts" / "control"
STOP_FILE = CTRL / "SCHED_STOP"
LOCK_FILE = ROOT / "ledger" / "scheduler.lock"


class Scheduler:
    def __init__(self, deadline_s: float = 86400.0):
        CTRL.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.ledger = DimwitLedger(ROOT / "ledger" / "scheduler.jsonl")
        self.deadline_s = deadline_s
        self._t0 = time.time()

    # ---- single-instance lock ------------------------------------------------------------------
    def _acquire(self) -> bool:
        if LOCK_FILE.exists():
            try:
                import psutil
                pid = int(json.loads(LOCK_FILE.read_text()).get("pid", -1))
                if psutil.pid_exists(pid):
                    return False                       # another scheduler is live
            except Exception:
                pass                                   # stale/garbage lock -> take it
        LOCK_FILE.write_text(json.dumps({"pid": os.getpid(), "started": int(time.time())}), encoding="utf-8")
        return True

    def _release(self):
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass

    def _stop_requested(self) -> bool:
        return STOP_FILE.exists() or (time.time() - self._t0) > self.deadline_s

    # ---- ticks -----------------------------------------------------------------------------------
    def heartbeat(self) -> dict:
        """Fast, no-UE: pipeline wiring self-check + HUD snapshot. Cheap enough to run frequently."""
        from dimwit.pipelines.validate import validate_all
        from dimwit import hud
        sc = validate_all()
        snap = hud.snapshot()
        tick = {"kind": "heartbeat", "pipelines_ok": sc.get("ok"), "pipeline_count": sc.get("count"),
                "validation": snap["validation"].get("verdict"),
                "caps_ok": {k: v.get("ok") for k, v in snap["capabilities"].items()},
                "roster": snap["roster"]}
        hud.render_html()
        self._ledger("HEARTBEAT", tick)
        return tick

    def full_tick(self, with_sweep: bool = True) -> dict:
        """Full autonomous tick: validate everything + (optionally) a director sweep. Boots UE/Blender."""
        out = {"kind": "full"}
        try:
            from dimwit.director import Director, load_tasks
            d = Director()
            if with_sweep:
                tasks = load_tasks()
                if tasks:
                    out["sweep"] = {k: d.run_sweep(tasks).get(k) for k in ("review_queue", "validation", "breaker")}
            else:
                out["validation"] = d.validate_everything().get("suite_verdict")
        except Exception as e:
            out["error"] = repr(e)
        self._ledger("FULL_TICK", out)
        return out

    def loop(self, interval_s: float = 1800.0, max_ticks: int | None = None, full: bool = False,
             with_sweep: bool = True) -> dict:
        if not self._acquire():
            return {"ok": False, "error": "another scheduler instance is running (lockfile held)"}
        ticks = 0
        history = []
        try:
            while not self._stop_requested():
                t = self.full_tick(with_sweep) if full else self.heartbeat()
                ticks += 1
                history.append(t.get("kind"))
                if max_ticks and ticks >= max_ticks:
                    break
                # interval sleep, but wake early if a stop is requested
                slept = 0.0
                while slept < interval_s and not self._stop_requested():
                    time.sleep(min(2.0, interval_s - slept))
                    slept += 2.0
        finally:
            self._release()
        reason = "stop_file" if STOP_FILE.exists() else ("max_ticks" if max_ticks and ticks >= max_ticks else "deadline")
        self._ledger("LOOP_END", {"ticks": ticks, "reason": reason})
        return {"ok": True, "ticks": ticks, "stop_reason": reason}

    def _ledger(self, state, detail):
        self.ledger.append({"ts": int(time.time()), "actor": "scheduler", "asset_id": "tick",
                            "state": f"scheduler.{state}", "candidate_hash": sha256_obj({"s": state, "d": detail, "t": detail.get("kind")}),
                            "detail": detail})


def main(argv) -> int:
    s = Scheduler()
    if "--once" in argv:
        full = "--full" in argv
        print(json.dumps(s.full_tick("--no-sweep" not in argv) if full else s.heartbeat(), indent=2, default=str))
        return 0

    def opt(name, default, cast):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    interval = opt("--interval", 1800.0, float)
    ticks = opt("--ticks", None, int)
    r = s.loop(interval_s=interval, max_ticks=ticks, full="--full" in argv, with_sweep="--no-sweep" not in argv)
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
