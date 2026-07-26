"""DESIGN/spec.author (task 15): turn a concept brief into a seed asset_spec.json + provenance.json the engine
can actually run — closing the invent->render dead-end (concept_prompts previously had nowhere to go).

Degrade-safe: with the LLM offline it still emits a valid WANEFALL-native seed (REQUIRED_IDENTITY traits +
class-default scale), so the loop always has something to build. Writes into assets/<asset_id>/ in the format
run_dimwit._load_seed consumes (asset_spec.json with _evidence + provenance.json)."""
from __future__ import annotations

import json
from pathlib import Path

from .core import REQUIRED_IDENTITY, FORBIDDEN_IDENTITY, Lifecycle, sha256_obj
from .pipelines.validation import resolve_asset_type_floors

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# the contract document version — bump only when the schema in config/intent_contract_schema.json changes
INTENT_CONTRACT_VERSION = 1
# hash fields are excluded from the content hash so the hash is stable across (re)stamping
_HASH_EXCLUDED = ("intent_hash", "anchored", "anchor_entry_hash")

CLASS_DEFAULT_SCALE = {
    "hostile_construct_enemy": 270, "weapon": 120, "vehicle_shell": 600,
    "helmet": 40, "arena_prop": 150, "cover_piece": 200, "waneboard_shell": 180,
}


def author_seed(asset_id: str, asset_type: str, brief: str = "", provenance: dict | None = None,
                use_brain: bool = True, out_root: Path | None = None) -> dict:
    scale = CLASS_DEFAULT_SCALE.get(asset_type, 200)
    concept = ""
    if use_brain:
        try:
            from . import cloud_brain, llm
            if llm.is_configured():
                r = cloud_brain.concept_prompts(brief or f"{asset_type} for WANEFALL", n=1)
                chars = r.get("characters") or r.get("prompts") or []
                concept = chars[0] if chars else ""
        except Exception:
            concept = ""
    spec = {
        "asset_type": asset_type, "scale_cm": scale,
        "palette": ["teal_wane_energy"], "traits": list(REQUIRED_IDENTITY),
        "material_slots": ["M_DarkBody", "M_RedCore", "M_TealWane"],
        "collision_proxy": "convex_decomp", "tri_estimate": 0,
        "camera_readability": 0.6, "gameplay_readability": 0.6, "hit_destroy_clarity": 0.6,
        "concept_prompt": concept, "brief": brief, "_evidence": {},
    }
    prov = provenance or {"license_class": "generated_concept",
                          "source_prompt": concept or brief or f"{asset_type} concept"}
    base = (out_root or ASSETS) / asset_id
    base.mkdir(parents=True, exist_ok=True)
    (base / "asset_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (base / "provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return {"asset_id": asset_id, "asset_type": asset_type, "spec_path": str(base / "asset_spec.json"),
            "provenance_path": str(base / "provenance.json"), "used_brain": bool(concept)}


# --------------------------------------------------------------------------- the per-build INTENT CONTRACT
# The user's law: "the initial picture/goals/design for any of the builds is what should be compared against
# the final capture and throughout the process." This is that document — declared UP FRONT, hash-anchored in
# the proof ledger BEFORE any pixel exists, and read back at every gate. It is what the captures are judged
# against; it is NOT where the GATING KNOBS live (those are the frozen ASSET_TYPE_FLOORS) — the author may
# only RAISE a floor here, never lower it, and fuse() enforces max(author, frozen).
# the SCORED part of the contract — what the intent_hash covers (per config/intent_contract_schema.json:83)
_SCORED_KEYS = ("goals", "design_law", "expected_appearance", "acceptance", "validation_plan")
DESIGN_MD_DEFAULT = Path("C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/DESIGN.md")


def intent_hash_of(contract: dict) -> str:
    """Content hash over the SCORED part of the contract (goals/design_law/expected_appearance/acceptance/
    validation_plan). Excludes ids, timestamps and the hash/anchor fields, so it is stable across
    re-stamping yet changes the instant the rubric the capture is judged against changes."""
    return sha256_obj({k: contract.get(k) for k in _SCORED_KEYS})


def _existing_capture_artifacts(base: Path) -> list:
    """Any rendered pixels already on disk for this asset — their presence forbids authoring intent
    (you cannot reverse-engineer 'intent' to match captures you already have). Fail-closed anti-retrofit."""
    if not base.exists():
        return []
    found = []
    for sub in (base, base / "captures", base / "evidence"):
        if sub.exists():
            found += [str(p) for p in sub.glob("*.png")]
            found += [str(p) for p in sub.glob("*.jpg")]
    # also honor declared evidence in an existing asset_spec.json
    spec_f = base / "asset_spec.json"
    if spec_f.exists():
        try:
            ev = (json.loads(spec_f.read_text(encoding="utf-8")) or {}).get("_evidence", {}) or {}
            for v in ev.values():
                if isinstance(v, str) and v.lower().endswith((".png", ".jpg")) and Path(v).exists():
                    found.append(v)
        except Exception:
            pass
    return sorted(set(found))


def _design_md_hash(path: Path | str | None) -> str:
    p = Path(path) if path else DESIGN_MD_DEFAULT
    try:
        return sha256_obj(p.read_text(encoding="utf-8")) if p.exists() else ""
    except Exception:
        return ""


def author_intent_contract(asset_id: str, asset_type: str, target_reference,
                           declared_intent: str = "", description: str = "",
                           intended_gameplay_role: str = "",
                           target_dimensions: dict | None = None, load_bearing_dimensions=None,
                           required_capture_stages=None, validator_domains=None,
                           required_identity_traits=None, forbidden_traits=None,
                           confidence_floor=None, target_match_floor=None,
                           design_md_path: str | None = None, token_slice=None,
                           canon_expectations: dict | None = None, local_overrides: dict | None = None,
                           provenance: dict | None = None, golden_corpus_refs=None,
                           authored_ts: int = 0, authored_by: str = "spec_author",
                           out_root: Path | None = None, ledger=None, run_id: str = "") -> dict:
    """Author the per-build INTENT CONTRACT (config/intent_contract_schema.json shape) and, when a `ledger`
    is given, ANCHOR its intent_hash in the proof ledger BEFORE generation — so it can never be retro-fitted
    to the result. This is the user's "initial picture/goals/design" that the final capture is judged against.

    Fail-closed refusals (return {ok: False, blocked: True, ...}; nothing written, nothing anchored):
      * ANY capture artifact already on disk for this asset  -> anti-retrofit (no authoring after pixels);
      * a strict asset_type (require_optics_semantic / no text-only target) with NO real on-disk reference
        image                                                 -> vacuous-target block;
      * reference image(s) present but no `reference_license` in provenance -> unusable target;
      * empty required_capture_stages                         -> nothing would ever be compared;
      * a local_override with no justification                -> silent deviation from the global law.

    Gating knobs may only be RAISED above the frozen ASSET_TYPE_FLOORS (confidence/target floors via max(),
    capture stages via union). fuse() re-applies max(author, frozen) defensively. review_only is always True;
    reaching this contract only ever gates PROMOTED_TO_REVIEW — never HUMAN_ACCEPTED.
    """
    floors = resolve_asset_type_floors(asset_type)
    base = (out_root or ASSETS) / asset_id

    def _block(reason, **extra):
        return {"ok": False, "blocked": True, "state": Lifecycle.BLOCKED, "reason": reason, **extra}

    # --- anti-retrofit: refuse if pixels already exist -------------------------------------------------
    existing = _existing_capture_artifacts(base)
    if existing:
        return _block("capture artifacts already exist — intent cannot be authored after pixels",
                      existing=existing[:8])

    # --- references + vacuous-target / license blocks -------------------------------------------------
    refs = [str(r) for r in (target_reference if isinstance(target_reference, (list, tuple)) else
                             ([target_reference] if target_reference else []))]
    refs_on_disk = [r for r in refs if r and Path(r).exists()]
    declares_target = bool(refs_on_disk)
    require_optics = bool(floors.get("require_optics_semantic", True))
    allow_textonly = not require_optics      # strict (optics-required) types may NOT use a text-only target
    if not declares_target and not allow_textonly:
        return _block("strict asset_type requires a real on-disk target_reference (the declared picture); "
                      "none of the given references exist", given_references=refs)
    prov = dict(provenance or {"license_class": "generated_concept",
                               "source_prompt": declared_intent or f"{asset_type} concept"})
    if refs_on_disk and not prov.get("reference_license"):
        return _block("reference image(s) declared but no provenance.reference_license — target unusable",
                      references=refs_on_disk)

    # --- capture stages (union, may only ADD) + non-empty requirement ---------------------------------
    eff_stages = sorted(set(floors.get("required_capture_stages", [])) | set(required_capture_stages or []))
    if not eff_stages:
        return _block("required_capture_stages is empty — nothing would ever be compared to the target")

    # --- local overrides each need a justification ----------------------------------------------------
    for tok, ov in (local_overrides or {}).items():
        just = ov.get("justification") if isinstance(ov, dict) else None
        if not just:
            return _block(f"local_override '{tok}' has no justification — silent deviation from the global law",
                          token=tok)

    # --- author may only RAISE the frozen floors ------------------------------------------------------
    eff_conf = max(float(confidence_floor or 0.0), float(floors["confidence_floor"]))
    eff_tmatch = max(float(target_match_floor or 0.0), float(floors["target_match_floor"]))
    load_dims = sorted(set(load_bearing_dimensions or floors.get("min_load_bearing_dims", [])))
    domains = list(validator_domains or floors.get("min_required_domains", []))
    rubric = "character" if asset_type in ("character", "enemy", "hostile_construct_enemy") else "image"

    contract = {
        "intent_id": f"{asset_id}__intent",
        "asset_id": asset_id, "asset_type": asset_type,
        "schema_version": "dimwit/intent_contract/v1",
        "authored_ts": int(authored_ts), "authored_by": authored_by,
        "goals": {
            "summary": declared_intent or f"{asset_type} for WANEFALL",
            "intended_gameplay_role": intended_gameplay_role,
            "target_dimensions": dict(target_dimensions or {}),
            "load_bearing_dimensions": load_dims,
        },
        "design_law": {
            "design_md_path": str(design_md_path or DESIGN_MD_DEFAULT),
            "design_md_hash": _design_md_hash(design_md_path),
            "token_slice": list(token_slice or []),
            "canon_expectations": dict(canon_expectations or {}),
            "local_overrides": dict(local_overrides or {}),
        },
        "expected_appearance": {
            "description": description or declared_intent or f"{asset_type} for WANEFALL",
            "reference_images": refs_on_disk,
            "must_have_traits": sorted(set(required_identity_traits or REQUIRED_IDENTITY)),
            "forbidden_traits": sorted(set(forbidden_traits or list(FORBIDDEN_IDENTITY.keys()))),
            "silhouette_note": "",
        },
        "acceptance": {
            "confidence_target": eff_conf,
            "dimension_floors": {d: eff_conf for d in load_dims},
            "target_match_floor": eff_tmatch,
            "allow_textonly_target": allow_textonly,
            "require_perception": bool(floors.get("require_perception", True)),
            "require_optics_semantic": require_optics,
        },
        "validation_plan": {
            "validator_domains": domains,
            "optics_rubric": rubric,
            "required_capture_stages": eff_stages,
            "golden_corpus_refs": list(golden_corpus_refs or []),
        },
        "provenance": prov,
        "declares_target": declares_target,
        "review_only": True,
    }
    contract["intent_hash"] = intent_hash_of(contract)
    contract["anchored"] = False
    contract["anchor_entry_hash"] = None

    ledger_entry = {
        "run_id": run_id, "asset_id": asset_id, "asset_type": asset_type,
        "state": Lifecycle.INTENT_DECLARED, "candidate_hash": "intent:" + contract["intent_hash"],
        "intent_hash": contract["intent_hash"], "declares_target": declares_target,
        "confidence_target": eff_conf, "target_match_floor": eff_tmatch,
        "required_capture_stages": eff_stages, "review_only": True,
    }
    if ledger is not None:
        ledger.append(ledger_entry)
        contract["anchored"] = True
        contract["anchor_entry_hash"] = getattr(ledger, "_head", None)

    base.mkdir(parents=True, exist_ok=True)
    (base / "intent_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    return {"ok": True, "blocked": False, "state": Lifecycle.INTENT_DECLARED,
            "asset_id": asset_id, "asset_type": asset_type,
            "contract": contract, "contract_path": str(base / "intent_contract.json"),
            "intent_hash": contract["intent_hash"], "ledger_entry": ledger_entry,
            "anchored": contract["anchored"]}
