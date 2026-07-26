"""Compounding learning applier (task 4).

Two strengths of learning, by design:
  * SOFT (automatic, capped, ratchet-UP): once a lesson has been seen >= MIN_OCCURRENCES times, bump the
    weight of its weak dimension in the relevant CLASS promotion profile(s). Global-scope lessons bump every
    class profile; class-scope lessons bump only their own. We NEVER touch default.json (the identity baseline
    stays byte-identical) and NEVER lower a weight — compounding can only make the bar harder. Capped at CAP.
  * HARD (operator-gated, never automatic): a recurring on-screen forbidden trait is surfaced as a PROPOSED
    identity law (add to FORBIDDEN_IDENTITY). It is returned for a human to accept in the review package —
    this module never edits core.FORBIDDEN_IDENTITY / REQUIRED_IDENTITY itself.

Pure stdlib. Reuses the task-1 profile files + task-3 lessons file.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]              # Dimwit/
PROMO_DIR = ROOT / "config" / "promotion"
LESSONS = ROOT / "lessons" / "dimwit_asset_lessons.jsonl"

MIN_OCCURRENCES = 3
WEIGHT_STEP = 0.5
WEIGHT_CAP = 3.0
LAW_MIN_OCCURRENCES = 4


def _lessons() -> list:
    if not LESSONS.exists():
        return []
    return [json.loads(ln) for ln in LESSONS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _class_profiles() -> list:
    return [p for p in PROMO_DIR.glob("*.json") if p.name != "default.json"]


def apply_lessons_to_profiles(min_occurrences: int = MIN_OCCURRENCES,
                              step: float = WEIGHT_STEP, cap: float = WEIGHT_CAP) -> dict:
    """Bump dimension weights in class profiles from repeated lessons. Ratchet-up + capped. Returns changes."""
    changes = []
    for L in _lessons():
        occ = int(L.get("occurrences", 0) or 0)
        dim = L.get("dimension")
        if occ < min_occurrences or not dim:
            continue
        if L.get("scope") == "global":
            targets = _class_profiles()
        else:
            t = PROMO_DIR / f"{L.get('domain')}.json"
            targets = [t] if t.exists() else []
        for pf in targets:
            try:
                prof = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                continue
            weights = dict(prof.get("dimension_weights") or {})
            cur = float(weights.get(dim, 1.0))
            new = round(min(cap, cur + step), 3)
            if new > cur:                                   # ratchet-up only
                weights[dim] = new
                prof["dimension_weights"] = weights
                pf.write_text(json.dumps(prof, indent=2) + "\n", encoding="utf-8")
                changes.append({"profile": pf.name, "dimension": dim, "old": cur, "new": new,
                                "lesson_id": L.get("lesson_id"), "occurrences": occ})
    if changes:
        try:                                                # so scoring picks the new weights up this process
            from ..engine import load_promotion_profile
            load_promotion_profile.cache_clear()
        except Exception:
            pass
    return {"applied": len(changes), "changes": changes, "min_occurrences": min_occurrences, "cap": cap}


def propose_identity_laws(min_occurrences: int = LAW_MIN_OCCURRENCES) -> list:
    """Surface recurring on-screen forbidden traits as PROPOSED identity laws — operator-gated, never applied."""
    proposals = []
    for L in _lessons():
        if int(L.get("occurrences", 0) or 0) < min_occurrences:
            continue
        for trait in L.get("measured_hard_fails", []) or []:
            proposals.append({
                "proposed_action": "add_to_FORBIDDEN_IDENTITY",
                "trait": trait, "dimension": L.get("dimension"), "domain": L.get("domain"),
                "occurrences": L.get("occurrences"), "lesson_id": L.get("lesson_id"),
                "status": "PROPOSED_OPERATOR_GATED",
                "note": "A human must accept this before it becomes a hard veto; Dimwit never self-applies identity laws.",
            })
    return proposals


if __name__ == "__main__":
    out = {"weight_apply": apply_lessons_to_profiles(), "proposed_laws": propose_identity_laws()}
    print(json.dumps(out, indent=2))
