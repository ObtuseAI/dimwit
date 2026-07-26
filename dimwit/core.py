"""Dimwit core: asset lifecycle states, the asset task/candidate data model, hashing, and the two
pure WANEFALL gates every candidate must satisfy — the style law and the provenance/license policy.

Stdlib-only. No engine state lives here (no file writes); this module is pure data + pure checks so it
can be unit-tested and reused by validators, the mutation loop, and the review packager.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any


# --------------------------------------------------------------------------- lifecycle
class Lifecycle:
    """Machine-readable asset lifecycle. Dimwit may autonomously reach PROMOTED_TO_REVIEW; it may NOT
    autonomously reach HUMAN_ACCEPTED or PROMOTED_TO_ACTIVE_SLICE (those require an operator gate)."""
    REQUESTED = "REQUESTED"
    INTENT_DECLARED = "INTENT_DECLARED"           # per-build intent contract anchored BEFORE any pixel exists
    REFERENCE_ANALYZED = "REFERENCE_ANALYZED"
    SPEC_CREATED = "SPEC_CREATED"
    GENERATED = "GENERATED"
    IMPORTED = "IMPORTED"
    TECH_VALIDATED = "TECH_VALIDATED"
    HERO_CAPTURED = "HERO_CAPTURED"
    PLAYER_CAMERA_VALIDATED = "PLAYER_CAMERA_VALIDATED"
    REJECTED = "REJECTED"
    NEEDS_RECURSION = "NEEDS_RECURSION"
    MUTATING = "MUTATING"
    PROMOTED_TO_REVIEW = "PROMOTED_TO_REVIEW"
    HUMAN_ACCEPTED = "HUMAN_ACCEPTED"             # operator-gated
    HUMAN_REJECTED = "HUMAN_REJECTED"             # operator-gated
    PROMOTED_TO_ACTIVE_SLICE = "PROMOTED_TO_ACTIVE_SLICE"  # operator-gated
    BLOCKED = "BLOCKED"

    AUTONOMOUS_TERMINALS = {PROMOTED_TO_REVIEW, NEEDS_RECURSION, REJECTED, BLOCKED}
    OPERATOR_ONLY = {HUMAN_ACCEPTED, HUMAN_REJECTED, PROMOTED_TO_ACTIVE_SLICE}


SCORED_DIMENSIONS = [
    "wanefall_genre_fit",
    "silhouette_readability",
    "third_person_camera_readability",
    "hero_readability",
    "gameplay_readability",
    "palette_discipline",
    "not_generic_ai_slop",
    "not_magenta_dominant",
    "not_white_debug_junk",
    "not_black_blob",
    "collision_sanity",
    "scale_sanity",
    "material_sanity",
    "performance_risk",
    "import_correctness",
    "hit_destroy_state_clarity",
]

PROVENANCE_CLASSES = [
    "owned_reference", "generated_concept", "licensed_reference",
    "public_domain", "open_license", "unknown_license", "forbidden",
]
PROVENANCE_PROMOTABLE = {"owned_reference", "generated_concept", "licensed_reference",
                         "public_domain", "open_license"}


# --------------------------------------------------------------------------- hashing
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))


# --------------------------------------------------------------------------- data model
@dataclass
class AssetTask:
    """One Dimwit asset request (matches Dimwit/config/asset_task_schema.json)."""
    asset_id: str
    asset_type: str
    source_kind: str = "design_need"           # image|text_spec|screenshot_failure|design_need|existing_placeholder
    source_paths: list = field(default_factory=list)
    intended_gameplay_role: str = ""
    wanefall_style_requirements: list = field(default_factory=list)
    forbidden_traits: list = field(default_factory=list)
    technical_requirements: list = field(default_factory=list)
    validation_requirements: list = field(default_factory=list)
    promotion_target: str = "review_only"
    human_review_required: bool = True

    def task_hash(self) -> str:
        return sha256_obj(asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AssetCandidate:
    """A generated/mutated candidate: a WANEFALL-native spec + the evidence + per-dimension scores."""
    candidate_id: str
    asset_id: str
    asset_type: str
    iteration: int
    spec: dict                                  # palette, silhouette, materials, scale, traits...
    evidence: dict = field(default_factory=dict)  # mesh path, hero contact sheet, lane contact sheet...
    scores: dict = field(default_factory=dict)
    overall: float = 0.0
    weakest_dimension: str = ""
    mutation_note: str = ""
    perception: dict = field(default_factory=dict)   # V2: measured-from-pixels metrics + hard fails (when real evidence exists)

    def candidate_hash(self) -> str:
        return sha256_obj({"spec": self.spec, "evidence": self.evidence})

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- WANEFALL style law (pure gate)
# A candidate spec declares palette/traits; the style law scores how WANEFALL-native it is and HARD-FAILS
# on forbidden identity traits. Scores are 0..1. This is deterministic so the mutation loop is replayable.
FORBIDDEN_IDENTITY = {
    "magenta": "not_magenta_dominant",
    "purple_core": "not_magenta_dominant",
    "white_debug": "not_white_debug_junk",
    "white_blob": "not_white_debug_junk",
    "black_blob": "not_black_blob",
    "near_black_metallic_body": "not_black_blob",
    "cartoon": "not_generic_ai_slop",
    "plastic_toy": "not_generic_ai_slop",
    "generic_fantasy": "not_generic_ai_slop",
    "ornament_clutter": "not_generic_ai_slop",
}
REQUIRED_IDENTITY = ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"]


def evaluate_style_law(spec: dict) -> dict:
    """Return {scores: {dim: 0..1}, hard_fails: [...], summary}. Pure; no IO."""
    traits = {str(t).lower() for t in spec.get("traits", [])}
    palette = {str(p).lower() for p in spec.get("palette", [])}
    present = traits | palette
    hard_fails = []
    for bad, dim in FORBIDDEN_IDENTITY.items():
        if bad in present:
            hard_fails.append({"trait": bad, "dimension": dim})
    have_required = [r for r in REQUIRED_IDENTITY if r in present]
    genre_fit = round(len(have_required) / len(REQUIRED_IDENTITY), 4)
    scores = {
        "wanefall_genre_fit": genre_fit,
        "palette_discipline": 1.0 if ("teal_wane_energy" in present and "magenta" not in present) else 0.4,
        "not_magenta_dominant": 0.0 if ("magenta" in present or "purple_core" in present) else 1.0,
        "not_white_debug_junk": 0.0 if ("white_debug" in present or "white_blob" in present) else 1.0,
        "not_black_blob": 0.0 if ("black_blob" in present or "near_black_metallic_body" in present) else 1.0,
        "not_generic_ai_slop": 0.0 if any(t in present for t in ("cartoon", "plastic_toy", "generic_fantasy", "ornament_clutter")) else 1.0,
        "silhouette_readability": 1.0 if "clean_silhouette" in present else 0.5,
    }
    return {
        "scores": scores,
        "hard_fails": hard_fails,
        "required_present": have_required,
        "required_missing": [r for r in REQUIRED_IDENTITY if r not in present],
        "summary": "style-law HARD FAIL: " + ", ".join(h["trait"] for h in hard_fails) if hard_fails else "style-law clean",
    }


# --------------------------------------------------------------------------- provenance gate (pure)
def evaluate_provenance(provenance: dict) -> dict:
    """A candidate cannot be promoted without a promotable provenance class + a recorded source."""
    cls = str(provenance.get("license_class", "unknown_license"))
    has_source = bool(provenance.get("source_prompt") or provenance.get("source_file") or provenance.get("source_url") or provenance.get("derived_from"))
    promotable = cls in PROVENANCE_PROMOTABLE and has_source and cls != "forbidden"
    reasons = []
    if cls not in PROVENANCE_CLASSES:
        reasons.append(f"unknown provenance class '{cls}'")
    if cls == "forbidden":
        reasons.append("forbidden source — cannot be used")
    if cls == "unknown_license":
        reasons.append("unknown_license cannot be directly copied/promoted")
    if not has_source:
        reasons.append("no recorded source prompt/file/url/derived_from")
    if provenance.get("direct_copy_of_copyright"):
        reasons.append("direct copy of a copyrighted design — forbidden")
        promotable = False
    return {"license_class": cls, "promotable": promotable, "has_source": has_source, "reasons": reasons}
