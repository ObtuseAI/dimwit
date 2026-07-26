"""Dimwit LIVE OPERATOR — the recursively-improving autonomous loop that fuses EYES + OPTICS + HANDS to operate
the live UE5.8 editor / PIE like a tech-artist, for the work the headless channel structurally cannot do.

The loop, per guarded step:  PERCEIVE (eyes: PrintWindow capture) -> THINK (optics: GLM-5V grounding/judgement)
-> ACT (hands: guarded SendInput) -> VERIFY (eyes+optics: did it achieve the intent?) -> LEDGER (hash-chained) ;
and RECURSIVELY IMPROVE: a step retries (bounded) while keeping the best-scoring attempt, so a missed click /
wrong panel self-corrects instead of failing. Every primitive inherits desktop_hands' safety envelope (enable
gate, per-action window-scope clamp, emergency abort, single-editor lock, destructive gate, proof ledger).

Autonomy is fail-closed: if EYES can't see the editor (closed/locked/black) or OPTICS can't ground, the step is
BLOCKED and ledgered — never a blind click. Irreversible ops stay human-gated (allow_destructive=false).

  from dimwit.live_operator import Operator
  op = Operator(goal="open the Animation editor and verify it is showing")
  op.health()                      # are eyes/hands/optics/editor all ready?
  op.self_test()                   # safe end-to-end: perceive editor -> optics describe (no risky input)
  op.run([...steps...])            # a guarded recipe with recursive verify
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from dimwit.desktop_eyes import DesktopEyes
from dimwit.desktop_hands import DesktopHands, live_enabled, allow_destructive, AbortControl
from dimwit.engine import DimwitLedger
from dimwit.core import sha256_obj
from dimwit import optics, llm, perception

ROOT = Path(__file__).resolve().parent.parent
LOOP_ART = ROOT / "artifacts" / "operator"


@dataclass
class Step:
    """One guarded operator step. action(op)->dict performs the hand op; verify(op, after_png)->(ok, score, note)
    judges whether the INTENT was achieved (eyes+optics). intent is a human-readable goal for the ledger."""
    intent: str
    action: "callable"
    verify: "callable" = None
    max_retries: int = 2
    destructive: bool = False


@dataclass
class Operator:
    goal: str = ""
    title: str = "Wanefall"
    proc: str = "UnrealEditor"
    eyes: DesktopEyes = field(default_factory=DesktopEyes)
    hands: DesktopHands = field(default=None)
    ledger: DimwitLedger = field(default=None)
    _n: int = 0

    def __post_init__(self):
        LOOP_ART.mkdir(parents=True, exist_ok=True)
        self.hands = DesktopHands(self.title, self.proc)
        self.ledger = DimwitLedger(ROOT / "ledger" / "operator.jsonl")

    # ---- senses ----------------------------------------------------------------------------------
    def perceive(self, tag: str = "frame") -> dict:
        """Capture the live editor (GPU-correct PrintWindow). Fail-closed: ok=False if not visible/black."""
        self._n += 1
        png = LOOP_ART / f"{self._n:03d}_{tag}.png"
        r = self.eyes.capture_window(self.title, png, proc=self.proc)
        if r.get("ok") and Path(png).exists():
            m = perception.analyze_image(png)
            r["mean_luminance"] = m.get("mean_luminance")
            r["readable"] = bool(m.get("ok")) and m.get("mean_luminance", 0) >= 0.04   # not black
        else:
            r["readable"] = False
        r["png"] = str(png)
        return r

    def think(self, png: str, question: str, response_json: bool = True) -> dict:
        """Optics grounding/judgement of a frame (GLM-5V). Fail-closed if LLM unavailable."""
        if not llm.is_configured():
            return {"blocked": "LLM not configured"}
        return optics.judge_image(png, question, require_semantic=True)

    # ---- the recursive step --------------------------------------------------------------------
    def step(self, s: Step) -> dict:
        """Run ONE step with recursive self-correction: act -> verify -> (retry, keep-best) up to max_retries."""
        attempts = []
        best = None
        for attempt in range(s.max_retries + 1):
            try:
                self.hands._check_abort()
            except AbortControl as e:
                self._ledger(s.intent, "ABORTED", {"reason": str(e), "attempt": attempt})
                return {"ok": False, "state": "ABORTED", "reason": str(e)}
            before = self.perceive(f"before_{attempt}")
            if not before.get("readable"):
                # cannot see the editor -> fail closed, do NOT act blind
                self._ledger(s.intent, "BLOCKED", {"reason": "editor not visible/black", "attempt": attempt})
                return {"ok": False, "state": "BLOCKED", "reason": "editor not visible"}
            act = s.action(self)                       # guarded hand op (preview if control disabled)
            time.sleep(0.4)
            after = self.perceive(f"after_{attempt}")
            ok, score, note = (True, 1.0, "no verify") if s.verify is None else s.verify(self, after)
            rec = {"attempt": attempt, "act_mode": act.get("mode"), "ok": ok, "score": score, "note": note,
                   "after_png": after.get("png")}
            attempts.append(rec)
            self._ledger(s.intent, "ATTEMPT", rec)
            if best is None or score > best["score"]:
                best = rec
            if ok:
                self._ledger(s.intent, "STEP_PASS", {"attempts": attempt + 1, "score": score})
                return {"ok": True, "state": "PASS", "attempts": attempts, "best": best}
        self._ledger(s.intent, "STEP_FAIL", {"attempts": len(attempts), "best": best})
        return {"ok": False, "state": "NEEDS_RECURSION", "attempts": attempts, "best": best}

    def run(self, steps: list) -> dict:
        """Run a recipe of guarded steps. Stops on a hard block/abort; ledgers every step. Recursively-improving
        per step. Returns the session report."""
        out = {"goal": self.goal, "live": live_enabled(), "steps": [], "ok": True}
        with DesktopHands.keep_awake():
            for s in steps:
                r = self.step(s)
                out["steps"].append({"intent": s.intent, **{k: r[k] for k in ("ok", "state") if k in r}})
                if not r["ok"] and r.get("state") in ("ABORTED", "BLOCKED"):
                    out["ok"] = False
                    break
                if not r["ok"]:
                    out["ok"] = False                  # NEEDS_RECURSION: surfaced, continue or stop per recipe
        self._ledger(self.goal or "session", "SESSION_END", {"ok": out["ok"], "n_steps": len(out["steps"])})
        return out

    # ---- health + safe self-test ---------------------------------------------------------------
    def health(self) -> dict:
        tgt = self.hands._resolve_target()
        return {"eyes": True, "hands_live_enabled": live_enabled(), "allow_destructive": allow_destructive(),
                "optics_llm": llm.health().get("ok") if llm.is_configured() else False,
                "editor_found": bool(tgt), "editor_title": (tgt or {}).get("title"),
                "single_editor": self.hands.single_editor()}

    def self_test(self) -> dict:
        """Safe end-to-end: perceive the editor + optics-describe it. No risky input. Proves the see->think path.
        If the editor is closed, returns a clean BLOCKED (honest)."""
        f = self.perceive("selftest")
        if not f.get("readable"):
            return {"ok": False, "state": "BLOCKED", "reason": "editor not open/visible", "frame": f.get("png")}
        desc = self.think(f["png"], "Describe what UE5 editor panel/state is shown. Return JSON: "
                          "{\"editor_visible\": bool, \"active_panel\": str, \"notes\": str, \"score\": 0-1}")
        self._ledger("self_test", "OK", {"frame": f.get("png"), "semantic": desc.get("semantic", desc)})
        return {"ok": True, "frame": f["png"], "perception_mean_lum": f.get("mean_luminance"), "optics": desc}

    def _ledger(self, intent, state, detail):
        self.ledger.append({"ts": int(time.time()), "actor": "live_operator", "asset_id": (intent or "step")[:80],
                            "state": f"operator.{state}", "candidate_hash": sha256_obj({"i": intent, "s": state, "d": detail}),
                            "detail": detail})


if __name__ == "__main__":
    import json
    print(json.dumps(Operator().health(), indent=2, default=str))
