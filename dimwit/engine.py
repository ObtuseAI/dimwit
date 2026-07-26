"""Dimwit engine: its OWN append-only proof ledger + task queue, the eight asset validation gates,
the recursive candidate mutation loop, and the lifecycle driver. All state lives under the Dimwit
workspace root — never under Blunder's root.

Mirrors Blunder's loop CONCEPTS (mock-before-execute, bounded recursion, fail-closed human gate,
keep-best, append-only proof) specialized for game ASSETS. Stdlib-only.
"""
from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .core import (
    AssetCandidate, AssetTask, Lifecycle, SCORED_DIMENSIONS,
    evaluate_provenance, evaluate_style_law, sha256_obj,
)
from .ledger.hashchain import GENESIS, chain_entry, chain_verify
from .ledger.locking import ledger_lock
from . import confidence            # the ONE fusion primitive (weakest-link MIN, fail-closed)

try:                                # V2: pixel-truth perception (numpy + Pillow). Guarded so the engine
    from . import perception        # still runs if those libs are absent (falls back to declared scoring).
    _HAS_PERCEPTION = True
except Exception:
    _HAS_PERCEPTION = False

MAX_MUTATION_ITERATIONS = 6
PROMOTE_TO_REVIEW_THRESHOLD = 0.70     # mean score required to package for human review (default profile)
HARD_FAIL_FLOOR = 0.01                 # any hard-failed dimension drops it here


# ----------------------------------------------------------------- per-class promotion profiles (task 1)
_PROMO_DIR = Path(__file__).resolve().parent.parent / "config" / "promotion"


@functools.lru_cache(maxsize=None)
def load_promotion_profile(asset_type: str) -> dict:
    """Data-driven promotion profile for an asset class. `default.json` reproduces current behavior exactly
    (0.70 threshold, empty weights => arithmetic-mean overall). A `<asset_type>.json` overlays it. Thresholds
    RATCHET UP ONLY: the effective threshold is clamped to >= threshold_floor (raise the bar, never lower it).
    Cached; call `load_promotion_profile.cache_clear()` after the learn step rewrites a profile (task 4)."""
    profile = {"promote_threshold": PROMOTE_TO_REVIEW_THRESHOLD,
               "threshold_floor": PROMOTE_TO_REVIEW_THRESHOLD,
               "dimension_weights": {}, "hard_gates": ["style", "provenance"],
               "required_evidence": ["hero_contact_sheet", "player_camera_contact_sheet"]}
    for name in ("default.json", f"{asset_type}.json"):
        f = _PROMO_DIR / name
        if f.exists():
            try:
                profile.update(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    profile["promote_threshold"] = max(float(profile.get("promote_threshold", PROMOTE_TO_REVIEW_THRESHOLD)),
                                       float(profile.get("threshold_floor", PROMOTE_TO_REVIEW_THRESHOLD)))
    return profile


def promotion_threshold(asset_type: str) -> float:
    return load_promotion_profile(asset_type)["promote_threshold"]


# ----------------------------------------------------------------- isolation guard
BLUNDER_ROOT_MARKERS = ("Obtuse", "30-proof-bundles", "run_blunder.py")


def assert_dimwit_path(path: Path) -> None:
    """Fail-closed: Dimwit must never write through a Blunder path. Raises if a Blunder marker appears."""
    p = str(Path(path).resolve()).replace("\\", "/")
    for marker in BLUNDER_ROOT_MARKERS:
        if f"/{marker}".lower() in ("/" + p.lower()) or p.lower().endswith(marker.lower()) or f"/{marker.lower()}/" in p.lower():
            raise RuntimeError(f"REFUSED: Dimwit attempted to write through a Blunder path marker '{marker}': {p}")


# ----------------------------------------------------------------- proof ledger (Dimwit's own)
class DimwitLedger:
    """Append-only JSONL asset proof ledger. Separate from Blunder's ledger."""

    def __init__(self, path: Path):
        self.path = Path(path)
        assert_dimwit_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._head = self._read_head()

    def _read_head(self) -> str:
        ents = self.entries()
        return ents[-1].get("entry_hash", GENESIS) if ents else GENESIS

    def _read_head_from_disk(self) -> str:
        """Current chain head straight from the file tail (same semantics as _read_head: last entry's
        entry_hash, GENESIS when empty/missing/legacy-tail). Fail-closed: an unparseable tail raises
        rather than silently re-chaining from GENESIS."""
        if not self.path.exists():
            return GENESIS
        tail = None
        with self.path.open("rb") as f:
            size = f.seek(0, os.SEEK_END)
            chunk, pos = b"", size
            while pos > 0:
                step = min(65536, pos)
                pos -= step
                f.seek(pos)
                chunk = f.read(step) + chunk
                lines = [ln for ln in chunk.splitlines() if ln.strip()]
                if len(lines) >= 2 or (lines and pos == 0):
                    tail = lines[-1]
                    break
        if tail is None:
            return GENESIS
        try:
            return json.loads(tail.decode("utf-8")).get("entry_hash", GENESIS)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"REFUSED append: ledger tail line is unparseable ({self.path}): {exc}") from exc

    def append(self, entry: dict) -> None:
        # Chain from the CURRENT on-disk head under a cross-process lock. A construction-time cached
        # head goes stale whenever runs overlap — that fork is exactly the 2026-06/07 chain breaks.
        with ledger_lock(self.path):
            head = self._read_head_from_disk()
            chained = chain_entry(entry, head)             # stamp prev_hash + entry_hash (tamper-evident)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(chained, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        self._head = chained["entry_hash"]

    def entries(self) -> list:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def consistency_check(self) -> dict:
        ents = self.entries()
        ok = all(("asset_id" in e and "state" in e and "candidate_hash" in e) for e in ents)
        chain = chain_verify(ents)
        return {"entry_count": len(ents), "schema_ok": ok, "chain_ok": chain["ok"],
                "chained": chain.get("chained", 0), "mid_ledger_legacy": chain.get("mid_ledger_legacy", False),
                "head": chain.get("head"), "chain": chain}


# ----------------------------------------------------------------- task queue (Dimwit's own)
class DimwitQueue:
    """JSONL asset task queue. Separate from Blunder's queue."""

    def __init__(self, path: Path):
        self.path = Path(path)
        assert_dimwit_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def items(self) -> list:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def write_all(self, items: list) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")

    def upsert(self, item: dict) -> None:
        items = self.items()
        for i, ex in enumerate(items):
            if ex.get("asset_task_id") == item.get("asset_task_id"):
                items[i] = item
                self.write_all(items)
                return
        items.append(item)
        self.write_all(items)


# ----------------------------------------------------------------- the 8 validation gates
def _gate(name: str, ok: bool, detail: str, **extra) -> dict:
    return {"gate": name, "verdict": "PASS" if ok else "FAIL", "detail": detail, **extra}


def validate_technical(cand: AssetCandidate) -> dict:
    spec = cand.spec
    slots = spec.get("material_slots", [])
    ok = bool(spec.get("mesh_ref")) and len(slots) >= 1 and bool(spec.get("scale_cm"))
    return _gate("technical", ok, f"mesh_ref={bool(spec.get('mesh_ref'))} slots={len(slots)} scale={spec.get('scale_cm')}")


def validate_style(cand: AssetCandidate) -> dict:
    sl = evaluate_style_law(cand.spec)
    measured_hard = cand.perception.get("hard_fails", []) if cand.perception else []
    all_hard = sl["hard_fails"] + measured_hard
    ok = not all_hard and sl["scores"].get("wanefall_genre_fit", 0) >= 0.5
    detail = sl["summary"] + (f" | MEASURED hard fails: {[h['trait'] for h in measured_hard]}" if measured_hard else "")
    return _gate("style", ok, detail, hard_fails=all_hard, declared_hard=sl["hard_fails"],
                 measured_hard=measured_hard, required_missing=sl["required_missing"])


def validate_hero_capture(cand: AssetCandidate) -> dict:
    ok = bool(cand.evidence.get("hero_contact_sheet"))
    return _gate("hero_capture", ok, f"hero_contact_sheet={cand.evidence.get('hero_contact_sheet')}")


def validate_player_camera(cand: AssetCandidate) -> dict:
    ok = bool(cand.evidence.get("player_camera_contact_sheet"))
    return _gate("player_camera", ok, f"player_camera_contact_sheet={cand.evidence.get('player_camera_contact_sheet')}",
                 note="player-camera evidence cannot be replaced by hero capture")


def validate_performance(cand: AssetCandidate) -> dict:
    tris = int(cand.spec.get("tri_estimate", 0))
    ok = 0 < tris <= 250000
    return _gate("performance", ok, f"tri_estimate={tris}")


def validate_collision(cand: AssetCandidate) -> dict:
    ok = bool(cand.spec.get("collision_proxy"))
    return _gate("collision", ok, f"collision_proxy={cand.spec.get('collision_proxy')}")


def validate_provenance_gate(cand: AssetCandidate) -> dict:
    pv = evaluate_provenance(cand.evidence.get("provenance", {}))
    return _gate("provenance", pv["promotable"], "; ".join(pv["reasons"]) or "provenance promotable", **pv)


def validate_promotion(cand: AssetCandidate, gates: list, fused: dict | None = None) -> dict:
    blockers = [g["gate"] for g in gates if g["verdict"] == "FAIL"]
    style_fail = any(g["gate"] == "style" and g["verdict"] == "FAIL" for g in gates)
    prov_fail = any(g["gate"] == "provenance" and g["verdict"] == "FAIL" for g in gates)
    threshold = promotion_threshold(cand.asset_type)
    if fused is not None:
        # HARDENED GATE: the authoritative decision is the weakest-link FUSED confidence, not the mean.
        # A single weak load-bearing dim (or a wrong-identity capture, or missing pixels) caps it below the
        # 0.95-start gate no matter how high the other fifteen dims average.
        fused_ok = bool(fused.get("meets_gate"))
        ok = fused_ok and not style_fail and not prov_fail
        detail = (f"FUSED confidence={fused.get('confidence')} >= gate={fused.get('gate')}? {fused_ok} "
                  f"| binding={fused.get('binding_constraint')} target_sim={fused.get('target_similarity')} "
                  f"| (mean {cand.overall:.3f}/{threshold} is advisory only) blockers={blockers}")
        return _gate("promotion", ok, detail, blockers=blockers, threshold=threshold, review_only=True,
                     fused_confidence=fused.get("confidence"), fused_gate=fused.get("gate"),
                     fused_meets_gate=fused_ok, fused_blocked=bool(fused.get("blocked")),
                     fused_binding_constraint=fused.get("binding_constraint"),
                     fused_target_similarity=fused.get("target_similarity"),
                     fused_blocked_reasons=fused.get("blocked_reasons", []),
                     mean_overall=cand.overall, gate_kind="fused_weakest_link")
    # legacy fallback: no fused gate supplied (kept only so unit callers without a contract still run);
    # flagged so an auditor can see the weakest-link gate did NOT run.
    ok = cand.overall >= threshold and not style_fail and not prov_fail
    return _gate("promotion", ok,
                 f"overall={cand.overall:.3f} threshold={threshold} blockers={blockers} (NO FUSED GATE RAN)",
                 blockers=blockers, threshold=threshold, review_only=True, gate_kind="legacy_mean",
                 fused_gate_ran=False)


def run_all_gates(cand: AssetCandidate, fused: dict | None = None) -> list:
    gates = [
        validate_technical(cand), validate_style(cand), validate_hero_capture(cand),
        validate_player_camera(cand), validate_performance(cand), validate_collision(cand),
        validate_provenance_gate(cand),
    ]
    gates.append(validate_promotion(cand, gates, fused=fused))
    return gates


# ----------------------------------------------------------------- scoring + mutation
def score_candidate(cand: AssetCandidate) -> AssetCandidate:
    """Deterministic 16-dimension score. Style-law dims come from the style law; capture/tech dims come
    from declared evidence/spec. Pure (replayable)."""
    sl = evaluate_style_law(cand.spec)
    s = {d: 0.5 for d in SCORED_DIMENSIONS}
    s.update(sl["scores"])
    ev, spec = cand.evidence, cand.spec
    s["hero_readability"] = 0.9 if ev.get("hero_contact_sheet") else 0.3
    s["third_person_camera_readability"] = float(spec.get("camera_readability", 0.5))
    s["gameplay_readability"] = float(spec.get("gameplay_readability", 0.5))
    s["collision_sanity"] = 1.0 if spec.get("collision_proxy") else 0.2
    s["scale_sanity"] = 1.0 if spec.get("scale_cm") else 0.3
    s["material_sanity"] = 1.0 if spec.get("material_slots") else 0.3
    s["import_correctness"] = 1.0 if spec.get("mesh_ref") else 0.2
    tris = int(spec.get("tri_estimate", 0))
    s["performance_risk"] = 1.0 if 0 < tris <= 250000 else 0.3
    s["hit_destroy_state_clarity"] = float(spec.get("hit_destroy_clarity", 0.5))
    # hard fails floor the offending dimension
    for hf in sl["hard_fails"]:
        s[hf["dimension"]] = HARD_FAIL_FLOOR
    # ---- V2 PIXEL-TRUTH OVERRIDE ----
    # If the candidate declares REAL evidence images that exist on disk, MEASURE them and override the
    # affected dimensions with what the screen actually shows. Measured pixels beat declared spec fields.
    if _HAS_PERCEPTION:
        seen = perception.perceive_evidence(cand.evidence)
        if seen:
            cand.perception = seen
            hero = seen.get("hero_contact_sheet", {}).get("style", {}).get("scores", {})
            lane = seen.get("player_camera_contact_sheet", {}).get("style", {}).get("scores", {})
            hard = []
            for k in ("hero_contact_sheet", "player_camera_contact_sheet"):
                hard += seen.get(k, {}).get("style", {}).get("hard_fails", [])
            cand.perception["hard_fails"] = hard
            if hero:
                s["hero_readability"] = hero.get("silhouette_readability", s["hero_readability"])
                s["silhouette_readability"] = max(s.get("silhouette_readability", 0.5), hero.get("silhouette_readability", 0.5))
            if lane:  # the gameplay/player-camera track drives the in-game readability dims
                s["gameplay_readability"] = lane.get("third_person_camera_readability", s["gameplay_readability"])
                s["third_person_camera_readability"] = lane.get("third_person_camera_readability", s["third_person_camera_readability"])
                s["not_black_blob"] = min(s["not_black_blob"], lane.get("not_black_blob", 1.0))
                s["palette_discipline"] = lane.get("palette_discipline", s["palette_discipline"])
            # any measured hard fail floors its dimension (real magenta / white-junk / black-blob on screen)
            for hf in hard:
                s[hf["dimension"]] = HARD_FAIL_FLOOR

    cand.scores = {k: round(float(v), 4) for k, v in s.items()}
    # weighted overall per the class profile; empty weights => arithmetic mean (byte-identical to default)
    weights = load_promotion_profile(cand.asset_type).get("dimension_weights") or {}
    if weights:
        num = sum(cand.scores[d] * float(weights.get(d, 1.0)) for d in cand.scores)
        den = sum(float(weights.get(d, 1.0)) for d in cand.scores)
        cand.overall = round(num / den, 4) if den else 0.0
    else:
        cand.overall = round(sum(cand.scores.values()) / len(cand.scores), 4)
    cand.weakest_dimension = min(cand.scores, key=cand.scores.get)
    return cand


# ----------------------------------------------------------------- FUSED engine checkpoint (closes the mean gap)
# The old gate (validate_promotion) tested cand.overall — an ARITHMETIC MEAN — against 0.70, so one weak
# load-bearing dim was averaged away by fifteen strong ones (the headline audit defect). This checkpoint
# routes the candidate through confidence.fuse() instead: a WEAKEST-LINK MIN over the load-bearing dims +
# the identity match to the declared reference, fail-closed on missing pixels. It is a STRICT SUBSET of the
# full validation-suite gate (_assemble) — perception + target + load-bearing + hard-fail only; optics /
# design_md / intent_conformance are the suite's required domains, gated again there. ANDing a subset
# checkpoint with the full suite gate can only TIGHTEN the promotion bar, never loosen it.
_PERCEPTION_DIMS = {"silhouette_readability", "third_person_camera_readability", "hero_readability",
                    "gameplay_readability", "not_black_blob", "palette_discipline"}
STAGE_OF = {"hero_contact_sheet": "hero", "player_camera_contact_sheet": "player_camera"}


def _contract_reference(contract: dict | None):
    """First declared reference image from a (nested-schema) intent contract; tolerates a flat target_reference."""
    imgs = (((contract or {}).get("expected_appearance") or {}).get("reference_images")) or []
    if not imgs:
        tr = (contract or {}).get("target_reference")
        imgs = [tr] if isinstance(tr, str) else (list(tr) if isinstance(tr, (list, tuple)) else [])
    return imgs[0] if imgs else None


def build_fusion_signals(cand: AssetCandidate, contract: dict | None, floors: dict) -> list:
    """Turn a scored candidate into confidence.signal() records for the ENGINE checkpoint. Honest about
    measured-vs-declared: a perception dim is only fed when REAL pixels measured it; with no pixels a strict
    type emits a BLOCKED perception signal so fuse() fails closed instead of certifying declared data."""
    sigs: list = []
    load_dims = list(floors.get("min_load_bearing_dims", []))
    perc = cand.perception or {}
    has_pixels = any(k in perc for k in STAGE_OF)
    # (1) measured perception dims, tagged by the capture stage that produced them.
    # The GATE is the declared min_load_bearing_dims (silhouette/tp-camera/...) + hard-fails — faithful to the
    # frozen floor. Load-bearing perception dims go in the required "perception" domain (they gate at the full
    # floor); cosmetic sub-metrics (palette/weak-point read/not-black-blob when not hard-failing) go in
    # "perception_info" so they are MEASURED and reported but don't independently veto at 0.95 — a small
    # weak-point should not block a clean readable silhouette. Bad cosmetics still floor via their HARD-FAIL.
    for evkey, stage in STAGE_OF.items():
        blk = (perc.get(evkey) or {}) if has_pixels else {}
        scores = (blk.get("style") or {}).get("scores") or {}
        for dim, val in scores.items():
            dom = "perception" if dim in load_dims else "perception_info"
            sigs.append(confidence.signal(dom, float(val), dimension=dim, stage=stage, id=f"{stage}:{dim}"))
        for hf in (blk.get("style") or {}).get("hard_fails", []):
            sigs.append(confidence.signal("perception", 0.0, dimension=hf.get("dimension"), stage=stage,
                                          hard_fail=True, id=f"{stage}:hf:{hf.get('trait')}"))
    if not has_pixels:
        sigs.append(confidence.signal("perception", None, blocked=True, id="no-pixels-measured"))
    # (1b) rig DEFORMATION evidence (#32): when the candidate carries pose captures (bind + stress poses), the
    # WEAKEST stress pose feeds the gate as a load-bearing perception signal — a candy-wrapper collapse or a
    # skinning blowup caps the fused confidence, so a rig that deforms badly cannot promote no matter how clean
    # its hero shot is. Fail-closed: declared-but-unmeasurable deformation BLOCKS.
    dcap = (cand.evidence or {}).get("deformation_capture") or {}
    dbind = dcap.get("bind")
    dposes = {n: p for n, p in (dcap.get("poses") or {}).items() if n != "bind"}
    if dbind and dposes:
        dr = perception.rig_deformation_over_poses(dbind, dposes) if _HAS_PERCEPTION else {"blocked": True}
        if dr.get("ok") and not dr.get("blocked") and dr.get("deformation_score") is not None:
            sigs.append(confidence.signal("perception", float(dr["deformation_score"]),
                                          dimension="deformation_health", id="deformation"))
        else:
            sigs.append(confidence.signal("perception", None, dimension="deformation_health",
                                          blocked=True, id="deformation-unmeasured"))

    # (2) declared (non-perception) load-bearing dims — e.g. hit_destroy_state_clarity has no pixel metric yet
    measured = {s["dimension"] for s in sigs if s.get("dimension")}
    for dim in load_dims:
        if dim not in _PERCEPTION_DIMS and dim not in measured:
            sigs.append(confidence.signal("spec", float(cand.scores.get(dim, 0.0)), dimension=dim,
                                          stage="execute", id=f"spec:{dim}"))
    # (3) declared style-law hard fails (the spec itself names a forbidden identity trait)
    for hf in evaluate_style_law(cand.spec)["hard_fails"]:
        sigs.append(confidence.signal("style", 0.0, dimension=hf["dimension"], hard_fail=True,
                                      id=f"declared_hf:{hf['trait']}"))
    # (4) identity/structure match to the declared reference (closes the wrong-asset-rendered-flawlessly gap)
    if contract and (contract.get("declares_target") or contract.get("target_reference")):
        ref = _contract_reference(contract)
        cap = cand.evidence.get("player_camera_contact_sheet") or cand.evidence.get("hero_contact_sheet")
        ts = None
        if _HAS_PERCEPTION and ref and cap and Path(ref).exists() and Path(cap).exists():
            cmp = perception.compare_to_target(cap, ref)
            ts = cmp.get("target_similarity") if cmp.get("ok") else None
        if ts is not None:
            sigs.append(confidence.signal("perception", float(ts), is_target_similarity=True, id="target_similarity"))
        else:
            sigs.append(confidence.signal("perception", None, is_target_similarity=True, blocked=True,
                                          id="target-no-capture-or-ref"))
    return sigs


def _engine_floor_view(floors: dict) -> dict:
    """The engine checkpoint enforces the SUBSET of the suite gate that the asset loop can actually measure:
    perception presence, the load-bearing weakest-link, the target-identity match and hard-fails. The
    suite-only required domains (optics/design_md/intent_conformance) are gated again in _assemble."""
    v = dict(floors)
    v["min_required_domains"] = ["perception"]
    v["require_optics_semantic"] = False
    v["required_capture_stages"] = [s for s in floors.get("required_capture_stages", []) if s in STAGE_OF.values()]
    return v


def fuse_candidate(cand: AssetCandidate, contract: dict | None, asset_type: str) -> dict:
    """Run the engine-checkpoint fusion for a candidate. Pure given the candidate's already-measured scores."""
    from .pipelines.validation import resolve_asset_type_floors      # lazy: validation imports engine
    floors = resolve_asset_type_floors(asset_type)
    sigs = build_fusion_signals(cand, contract, floors)
    fused = confidence.fuse(sigs, contract, _engine_floor_view(floors))
    fused["asset_type"] = asset_type
    fused["frozen_floor"] = floors.get("confidence_floor")
    return fused


# mutation rules: weakest dimension -> a concrete spec delta (review-only proposal, never applied to game)
def mutate_candidate(cand: AssetCandidate, new_id: str) -> AssetCandidate:
    spec = json.loads(json.dumps(cand.spec))  # deep copy
    dim = cand.weakest_dimension
    note = ""
    traits = set(spec.get("traits", []))
    if dim in ("gameplay_readability", "third_person_camera_readability"):
        spec["gameplay_readability"] = min(1.0, float(spec.get("gameplay_readability", 0.5)) + 0.2)
        spec["camera_readability"] = min(1.0, float(spec.get("camera_readability", 0.5)) + 0.2)
        traits.add("per_enemy_rim_light"); traits.add("body_value_lift")
        note = "lift body value + add per-enemy rim light for gameplay-camera separation (review-only proposal)"
    elif dim == "not_black_blob":
        traits.discard("near_black_metallic_body"); traits.discard("black_blob"); traits.add("dark_alien")
        note = "raise body value, reduce metallic, add edge-light response (un-blob the body)"
    elif dim == "not_magenta_dominant":
        for bad in ("magenta", "purple_core"):
            traits.discard(bad)
        traits.add("red_or_orange_weak_point"); traits.add("teal_wane_energy")
        note = "retint magenta/purple -> red weak-point + teal Wane energy"
    elif dim == "not_generic_ai_slop":
        for bad in ("cartoon", "plastic_toy", "generic_fantasy", "ornament_clutter"):
            traits.discard(bad)
        traits.add("clean_silhouette")
        note = "strip AI-slop ornament clutter / cartoon-plastic traits; favour a clean readable silhouette"
    elif dim in ("not_white_debug_junk",):
        for bad in ("white_debug", "white_blob"):
            traits.discard(bad)
        traits.add("dark_alien")
        note = "remove white/debug junk material; return to a dark WANEFALL body"
    elif dim in ("silhouette_readability", "wanefall_genre_fit"):
        traits.add("clean_silhouette"); traits.add("dark_alien"); traits.add("teal_wane_energy"); traits.add("red_or_orange_weak_point")
        note = "strengthen silhouette + add missing WANEFALL identity traits"
    elif dim == "collision_sanity":
        spec["collision_proxy"] = "convex_decomp"; note = "add convex collision proxy"
    elif dim == "hit_destroy_state_clarity":
        spec["hit_destroy_clarity"] = min(1.0, float(spec.get("hit_destroy_clarity", 0.5)) + 0.25)
        note = "make hit-flash + destroyed state visibly distinct"
    else:
        spec["camera_readability"] = min(1.0, float(spec.get("camera_readability", 0.5)) + 0.1)
        note = f"general nudge on weakest dim '{dim}'"
    spec["traits"] = sorted(traits)
    nxt = AssetCandidate(candidate_id=new_id, asset_id=cand.asset_id, asset_type=cand.asset_type,
                         iteration=cand.iteration + 1, spec=spec, evidence=json.loads(json.dumps(cand.evidence)),
                         mutation_note=note)
    return score_candidate(nxt)


# ----------------------------------------------------------------- recursive mutation loop
def _fused_rank(cand: AssetCandidate, fused: dict) -> tuple:
    """Order candidates by the HARDENED gate: meets-gate first, then weakest-link fused confidence, then the
    mean only as a last tiebreak (so when no pixels exist and every candidate is blocked, ranking degrades
    gracefully to the legacy mean — identical keep-best as before)."""
    meets = 1 if (fused and fused.get("meets_gate")) else 0
    conf = fused.get("confidence") if fused else None
    return (meets, conf if conf is not None else -1.0, cand.overall)


def recursive_mutation_loop(seed: AssetCandidate, max_iters: int = MAX_MUTATION_ITERATIONS, render_fn=None,
                            contract: dict | None = None, asset_type: str | None = None) -> dict:
    """generate(seed) -> score -> classify weakest -> mutate -> rescore -> keep best -> repeat until the
    FUSED weakest-link gate is met / no-improvement / max. Returns the best candidate, its fused result, and
    the full history.

    The stop condition + keep-best are the weakest-link confidence.fuse() gate — NOT the arithmetic mean — so
    the loop actively fine-tunes toward the declared 0.95→0.99 target ("adjusted until the confidence threshold
    is met"), fixing the binding constraint each round rather than inflating an easy dimension. When no real
    pixels exist every candidate is fail-closed BLOCKED, so ranking falls back to the mean and the loop ends in
    NEEDS_RECURSION (correct: it cannot certify without evidence).

    task 6: when `render_fn` is supplied, each candidate REGENERATES its evidence (new geometry/pixels) before
    scoring, so a measured failure is recoverable."""
    at = asset_type or seed.asset_type
    score_candidate(seed)
    if render_fn is not None:
        render_fn(seed); score_candidate(seed)              # fresh evidence for the seed, then re-score
    mean_threshold = promotion_threshold(at)
    best = seed
    best_fused = fuse_candidate(seed, contract, at)
    history = [seed]
    stale = 0
    for i in range(max_iters):
        if best_fused.get("meets_gate"):                    # the REAL stop condition is the fused gate
            break
        cand = mutate_candidate(best, new_id=f"{seed.asset_id}_cand_{best.iteration + 1:02d}")
        if render_fn is not None:
            render_fn(cand); score_candidate(cand)          # NEW evidence per candidate, then re-score
        cand_fused = fuse_candidate(cand, contract, at)
        history.append(cand)
        if _fused_rank(cand, cand_fused) > _fused_rank(best, best_fused):
            best = cand
            best_fused = cand_fused
            stale = 0
        else:
            stale += 1
            if stale >= 2:
                break
    return {
        "best": best,
        "best_fused": best_fused,
        "history": history,
        "iterations": len(history),
        "reached_threshold": best.overall >= mean_threshold,        # legacy mean (meaning unchanged)
        "reached_fused_gate": bool(best_fused.get("meets_gate")),   # the hardened weakest-link gate
    }


# ----------------------------------------------------------------- lifecycle driver
@dataclass
class AssetRunReport:
    asset_id: str
    asset_type: str
    final_state: str
    overall: float
    iterations: int
    gates: list = field(default_factory=list)
    weakest_dimension: str = ""
    best_candidate: dict = field(default_factory=dict)
    lifecycle_trace: list = field(default_factory=list)
    review_only: bool = True
    fused: dict = field(default_factory=dict)        # the weakest-link engine-checkpoint fusion result

    def to_dict(self) -> dict:
        return asdict(self)


def run_asset_task(task: AssetTask, seed_spec: dict, seed_evidence: dict,
                   ledger: DimwitLedger, run_id: str, operator_approved_active_slice: bool = False,
                   render_fn=None, contract: dict | None = None) -> AssetRunReport:
    """Drive ONE asset task through the lifecycle to an AUTONOMOUS terminal (PROMOTED_TO_REVIEW /
    NEEDS_RECURSION / REJECTED / BLOCKED). Operator-only states are never reached autonomously.

    `contract` is the per-build intent contract (spec_author.author_intent_contract). When supplied it
    declares the target reference the capture is matched against and may RAISE the frozen floors. The
    promotion decision is the weakest-link FUSED confidence (confidence.fuse), never the arithmetic mean."""
    trace = [Lifecycle.REQUESTED, Lifecycle.REFERENCE_ANALYZED, Lifecycle.SPEC_CREATED]
    if contract is not None:
        trace.insert(1, Lifecycle.INTENT_DECLARED)

    # provenance is a fail-closed pre-gate (cannot even enter generation without it)
    pv = evaluate_provenance(seed_evidence.get("provenance", {}))
    if not pv["promotable"] and pv["license_class"] in ("forbidden", "unknown_license"):
        report = AssetRunReport(task.asset_id, task.asset_type, Lifecycle.BLOCKED, 0.0, 0,
                                gates=[{"gate": "provenance", "verdict": "FAIL", "detail": "; ".join(pv["reasons"])}],
                                lifecycle_trace=trace + [Lifecycle.BLOCKED])
        ledger.append(_ledger_entry(task, report, run_id, None))
        return report

    seed = AssetCandidate(candidate_id=f"{task.asset_id}_cand_00", asset_id=task.asset_id,
                          asset_type=task.asset_type, iteration=0, spec=seed_spec, evidence=seed_evidence)
    trace += [Lifecycle.GENERATED, Lifecycle.IMPORTED]

    loop = recursive_mutation_loop(seed, render_fn=render_fn, contract=contract, asset_type=task.asset_type)
    best = loop["best"]
    trace += [Lifecycle.MUTATING] if loop["iterations"] > 1 else []

    fused = loop["best_fused"]                                # the loop optimized toward this weakest-link gate
    gates = run_all_gates(best, fused=fused)
    if any(g["gate"] == "technical" and g["verdict"] == "PASS" for g in gates):
        trace.append(Lifecycle.TECH_VALIDATED)
    if any(g["gate"] == "hero_capture" and g["verdict"] == "PASS" for g in gates):
        trace.append(Lifecycle.HERO_CAPTURED)
    if any(g["gate"] == "player_camera" and g["verdict"] == "PASS" for g in gates):
        trace.append(Lifecycle.PLAYER_CAMERA_VALIDATED)

    promo = next(g for g in gates if g["gate"] == "promotion")
    style_gate = next(g for g in gates if g["gate"] == "style")
    declared_hard = style_gate.get("declared_hard", [])
    measured_hard = style_gate.get("measured_hard", [])
    if declared_hard:
        final = Lifecycle.REJECTED               # the spec itself violates the WANEFALL style law
    elif measured_hard:
        final = Lifecycle.NEEDS_RECURSION         # asset spec is fine but the RENDERED evidence hard-fails (e.g. in-game black-blob) -> iterate presentation
    elif promo["verdict"] == "PASS":
        final = Lifecycle.PROMOTED_TO_REVIEW
    else:
        final = Lifecycle.NEEDS_RECURSION
    trace.append(final)

    report = AssetRunReport(task.asset_id, task.asset_type, final, best.overall, loop["iterations"],
                            gates=gates, weakest_dimension=best.weakest_dimension,
                            best_candidate=best.to_dict(), lifecycle_trace=trace, review_only=True,
                            fused=fused)
    ledger.append(_ledger_entry(task, report, run_id, best, contract))
    return report


def _ledger_entry(task: AssetTask, report: AssetRunReport, run_id: str, best, contract: dict | None = None) -> dict:
    fused = report.fused or {}
    return {
        "run_id": run_id,
        "asset_id": task.asset_id,
        "asset_type": task.asset_type,
        "state": report.final_state,
        "source_paths": task.source_paths,
        "task_hash": task.task_hash(),
        "candidate_hash": best.candidate_hash() if best else "none",
        "intent_hash": (contract or {}).get("intent_hash"),     # binds the run to the anchored intent contract
        "fused_confidence": fused.get("confidence"),
        "fused_gate": fused.get("gate"),
        "fused_meets_gate": bool(fused.get("meets_gate")),
        "fused_blocked": bool(fused.get("blocked")),
        "fused_binding_constraint": fused.get("binding_constraint"),
        "fused_target_similarity": fused.get("target_similarity"),
        "overall_score": report.overall,
        "iterations": report.iterations,
        "weakest_dimension": report.weakest_dimension,
        "gate_verdicts": {g["gate"]: g["verdict"] for g in report.gates},
        "promotion_target": task.promotion_target,
        "human_review_required": task.human_review_required,
        "human_review_status": "PENDING" if report.final_state == Lifecycle.PROMOTED_TO_REVIEW else "N/A",
        "review_only": True,
        "perception_measured": bool(best and best.perception),
        "perception_hard_fails": [h.get("trait") for h in (best.perception.get("hard_fails", []) if best and best.perception else [])],
        "perception_metrics": {k: v.get("metrics", {}) for k, v in (best.perception.items() if best and best.perception else {}) if isinstance(v, dict) and "metrics" in v},
    }
