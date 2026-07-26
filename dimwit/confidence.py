"""The ONE fusion primitive for Dimwit's hardened intent-contract loop.

Every place that turns a pile of per-signal measurements into a single "are we confident enough to
promote this build to human review?" number calls `fuse()` — base.qa, engine.score_candidate, and
validation.ValidationSuite._assemble all funnel through here. There is exactly one scoring world, not
the two disjoint ones the hardening audit found (a flat mean-of-booleans in the director vs. a rich
weighted score the director never reached).

DOCTRINE (why this is un-gameable):
  * WEAKEST-LINK MIN, never a mean. Confidence = MIN across every required domain, every load-bearing
    dimension, and the declared target-similarity. One weak load-bearing dim CAPS the whole score — it
    cannot be averaged away by fifteen easy dims. This is the property the old `sum(...)/len(...)` lacked.
  * NONE means "cannot certify", and None can never satisfy a gate. You cannot manufacture a high number
    by OMITTING a signal: a missing required domain, a missing required capture stage, a missing
    perception/optics/reference measurement, or an unmeasured load-bearing dim all resolve to None.
    Fail-closed: the absence of evidence is never treated as evidence of confidence.
  * BLOCKED clamps. A signal that could not be evaluated (missing numpy/Pillow, missing GLM, missing
    reference image) in a REQUIRED domain blocks the whole result. It is never silently scored as 1.0.
  * HARD-FAIL floors. Any blocker-severity failure drops confidence to HARD_FAIL_FLOOR (below every gate).
  * AUTHOR CAN ONLY RAISE. The gating knobs come from the frozen ASSET_TYPE_FLOORS row; a per-build
    intent contract may RAISE a floor but never lower it (effective = max(author, frozen_floor)).

`fuse()` is pure and deterministic (no clock, no RNG, no I/O) so it replays byte-identically in the
proof ledger. Reaching a gate is NEVER auto-acceptance — HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE stay
operator-only. This primitive only decides whether a build may be PACKAGED for the human gate.
"""
from __future__ import annotations

from typing import Optional

HARD_FAIL_FLOOR = 0.01     # any blocker-severity failure drops the fused confidence here (below every gate)


def signal(domain: str, score: Optional[float] = None, *, dimension: Optional[str] = None,
           stage: Optional[str] = None, blocked: bool = False, hard_fail: bool = False,
           is_target_similarity: bool = False, id: str = "") -> dict:
    """Convenience constructor for one measurement record fed to `fuse()`.

    domain               — which required-domain bucket this belongs to (perception/optics/design_md/
                           intent_conformance/style/technical/...). Required-domain coverage is checked
                           against the asset_type floor.
    score                — 0..1 measured value, or None if this signal is undefined/not-yet-measured.
    dimension            — one of core.SCORED_DIMENSIONS when this measures a specific dim (load-bearing
                           dims are checked by name); None for a domain-level gate.
    stage                — the capture stage this evidence came from (plan/execute/hero/player_camera/
                           motion); used to enforce required_capture_stages coverage.
    blocked              — True if the signal could NOT be evaluated (missing lib / missing evidence).
    hard_fail            — True if this is a blocker-severity failure (clamps confidence to the floor).
    is_target_similarity — True for the identity/structure match against the declared reference.
    """
    return {"domain": domain, "score": score, "dimension": dimension, "stage": stage,
            "blocked": bool(blocked), "hard_fail": bool(hard_fail),
            "is_target_similarity": bool(is_target_similarity), "id": id}


def _eff_floor(contract: Optional[dict], floors: dict, key: str, default: float) -> float:
    """Effective gating value = max(author-declared, frozen floor). The author may only RAISE."""
    frozen = float(floors.get(key, default))
    author = (contract or {}).get(key)
    try:
        author = float(author)
    except (TypeError, ValueError):
        author = frozen
    return max(author, frozen)


def fuse(records: list, contract: Optional[dict], floors: dict) -> dict:
    """Collapse a list of per-signal measurement records into ONE weakest-link confidence.

    records  — list of signal() dicts (or equivalent plain dicts).
    contract — the per-build intent contract (may RAISE floors; declares the target reference). May be None.
    floors   — the frozen ASSET_TYPE_FLOORS row (validation.resolve_asset_type_floors(asset_type)).

    Returns a dict whose `confidence` is a float in [0,1] or None. None / blocked can never meet a gate.
    `meets_gate` is the single authoritative "may this be packaged for human review?" boolean.
    """
    floors = floors or {}
    req_domains = list(floors.get("min_required_domains", []))
    load_dims = list(floors.get("min_load_bearing_dims", []))
    req_stages = list(floors.get("required_capture_stages", []))
    gate = _eff_floor(contract, floors, "confidence_floor", 0.95)
    target_floor = _eff_floor(contract, floors, "target_match_floor", 0.80)
    require_perception = bool(floors.get("require_perception", True))
    require_optics = bool(floors.get("require_optics_semantic", True))

    blocked_reasons: list = []
    clamps: list = []

    # ---- partition records ------------------------------------------------------------------------
    live = [r for r in records if not r.get("blocked")]
    blocked_recs = [r for r in records if r.get("blocked")]

    # ---- (1) hard-fail floor: a single blocker-severity failure floors everything ------------------
    hard = [r for r in records if r.get("hard_fail")]
    has_hard_fail = bool(hard)
    for r in hard:
        clamps.append(f"hard_fail:{r.get('domain')}:{r.get('dimension') or r.get('id') or 'gate'}")

    # ---- (2) fail-closed coverage: required domains / capture stages / perception / optics ----------
    live_by_domain: dict = {}
    for r in live:
        if r.get("score") is None:
            continue
        if r.get("is_target_similarity"):
            continue   # identity/structure match is its OWN axis, not a per-domain quality score
        live_by_domain.setdefault(r["domain"], []).append(float(r["score"]))

    for d in req_domains:
        if d not in live_by_domain:
            blocked_reasons.append(f"required domain '{d}' has no usable (non-blocked, scored) signal")
    if require_perception and "perception" not in live_by_domain:
        blocked_reasons.append("require_perception: no live perception measurement (pixel-truth missing)")
    if require_optics and "optics" not in live_by_domain:
        blocked_reasons.append("require_optics_semantic: no live optics/GLM judgement")

    live_stages = {r.get("stage") for r in live if r.get("stage")}
    for st in req_stages:
        if st not in live_stages:
            blocked_reasons.append(f"required capture stage '{st}' has no live evidence")

    # any blocked record sitting in a REQUIRED domain blocks the whole result (cannot certify around it)
    for r in blocked_recs:
        if r.get("domain") in req_domains or \
           (r.get("domain") == "perception" and require_perception) or \
           (r.get("domain") == "optics" and require_optics):
            blocked_reasons.append(f"blocked signal in required domain '{r.get('domain')}': {r.get('id') or '?'}")

    # ---- (3) target similarity (identity/structure to the declared reference) -----------------------
    target_vals = [float(r["score"]) for r in live
                   if r.get("is_target_similarity") and r.get("score") is not None]
    target_similarity = min(target_vals) if target_vals else None
    declares_target = bool((contract or {}).get("target_reference") or (contract or {}).get("declares_target"))
    if declares_target and target_similarity is None:
        blocked_reasons.append("contract declares a target reference but no target-similarity was measured")

    # ---- (4) load-bearing dimensions: each MUST be measured; value = MIN across its records ----------
    dim_scores: dict = {}
    for dim in load_dims:
        vals = [float(r["score"]) for r in live
                if r.get("dimension") == dim and r.get("score") is not None]
        dim_scores[dim] = min(vals) if vals else None
        if dim_scores[dim] is None:
            blocked_reasons.append(f"load-bearing dimension '{dim}' was never measured")

    # ---- per-domain weakest link ------------------------------------------------------------------
    by_domain = {d: (min(v) if v else None) for d, v in live_by_domain.items()}

    # ---- terminal: blocked / undefined => None (can never meet a gate) -----------------------------
    if blocked_reasons:
        return {"confidence": None, "blocked": True, "blocked_reasons": blocked_reasons,
                "by_domain": by_domain, "by_load_bearing_dim": dim_scores, "clamps": clamps,
                "binding_constraint": blocked_reasons[0], "target_similarity": target_similarity,
                "gate": gate, "target_floor": target_floor, "meets_gate": False}

    # ---- (5) the cross-level weakest-link MIN ------------------------------------------------------
    # confidence = MIN over { every required-domain weakest link, every load-bearing dim, target sim }.
    # No mean anywhere. The single smallest member is the binding constraint = exactly what to fix.
    # Members are ordered most-specific-first (dims, then target, then domain buckets) so that on a tie
    # the reported binding_constraint is the actionable one ("fix silhouette", not "fix perception").
    members: list = []  # (value, label)
    for dim, v in dim_scores.items():
        members.append((v, f"dim:{dim}"))
    if target_similarity is not None:
        members.append((target_similarity, "target_similarity"))
        if target_similarity < target_floor:
            clamps.append(f"target_similarity {target_similarity:.3f} < floor {target_floor:.3f}")
    for d in req_domains:
        members.append((by_domain[d], f"domain:{d}"))

    if not members:
        # nothing load-bearing was declared to measure against — refuse to certify (fail-closed)
        return {"confidence": None, "blocked": True,
                "blocked_reasons": ["no required domains / load-bearing dims / target declared to fuse over"],
                "by_domain": by_domain, "by_load_bearing_dim": dim_scores, "clamps": clamps,
                "binding_constraint": "nothing to measure", "target_similarity": target_similarity,
                "gate": gate, "target_floor": target_floor, "meets_gate": False}

    weakest_val, weakest_label = min(members, key=lambda m: m[0])
    confidence = float(weakest_val)

    if has_hard_fail:
        confidence = min(confidence, HARD_FAIL_FLOOR)
        weakest_label = clamps[0] if clamps else "hard_fail"

    confidence = round(confidence, 4)
    meets_gate = (confidence >= gate) and (target_similarity is None or target_similarity >= target_floor) \
        and not has_hard_fail

    return {"confidence": confidence, "blocked": False, "blocked_reasons": [],
            "by_domain": by_domain, "by_load_bearing_dim": dim_scores, "clamps": clamps,
            "binding_constraint": weakest_label, "target_similarity": target_similarity,
            "gate": gate, "target_floor": target_floor, "meets_gate": meets_gate}
