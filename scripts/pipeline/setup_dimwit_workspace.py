"""One-shot Dimwit workspace generator: creates the directory tree, all config/policy JSON, validators,
the seeded lessons memory, the seeded asset queue, and the controlled test-workload seed asset. Idempotent.

Stdlib-only. Confined to the Dimwit root. Does NOT touch Blunder.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TS = sys.argv[1] if len(sys.argv) > 1 else "latest"

SUBDIRS = ["config", "state", "memory", "queues", "proofs", "artifacts", "assets", "source_art",
           "unreal_imports", "blender_scripts", "captures", "review_packages", "reports", "bundles",
           "lessons", "validators"]
for d in SUBDIRS:
    (ROOT / d).mkdir(parents=True, exist_ok=True)


def w(rel, obj):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- identity + state
w("state/dimwit_identity.json", {
    "canonical_name": "Dimwit",
    "role": "WANEFALL-specific autonomous asset/build operator",
    "version": "1.0.0-foundation",
    "scope": ["Unreal automation", "Blender automation", "image/reference-to-asset conversion",
              "mesh generation", "material generation", "asset import", "collision setup", "asset validation",
              "hero capture", "player-camera validation", "recursive asset mutation", "human review packaging",
              "WANEFALL style enforcement"],
    "is_not": ["Blunder replacement", "a shared branch", "a generic asset scraper", "a random AI content dumper",
               "allowed to auto-promote unvalidated assets", "allowed to bypass dual-gate validation"],
    "derived_from": "Blunder (concepts only — no shared mutable state)",
    "workspace_root": str(ROOT),
})

w("state/dimwit_state.json", {"engine": "Dimwit", "status": "FOUNDATION_READY", "active_run": None,
                               "ledger": "proofs/dimwit_asset_proof_ledger.jsonl",
                               "queue": "queues/dimwit_asset_queue.jsonl"})

# ---------------------------------------------------------------- asset lifecycle
w("config/asset_lifecycle.json", {
    "states": ["REQUESTED", "REFERENCE_ANALYZED", "SPEC_CREATED", "GENERATED", "IMPORTED", "TECH_VALIDATED",
               "HERO_CAPTURED", "PLAYER_CAMERA_VALIDATED", "REJECTED", "NEEDS_RECURSION", "MUTATING",
               "PROMOTED_TO_REVIEW", "HUMAN_ACCEPTED", "HUMAN_REJECTED", "PROMOTED_TO_ACTIVE_SLICE", "BLOCKED"],
    "autonomous_terminals": ["PROMOTED_TO_REVIEW", "NEEDS_RECURSION", "REJECTED", "BLOCKED"],
    "operator_only_states": ["HUMAN_ACCEPTED", "HUMAN_REJECTED", "PROMOTED_TO_ACTIVE_SLICE"],
    "rule": "Dimwit may autonomously reach PROMOTED_TO_REVIEW; HUMAN_ACCEPTED and PROMOTED_TO_ACTIVE_SLICE require an explicit operator gate.",
})

# ---------------------------------------------------------------- asset task schema
w("config/asset_task_schema.json", {
    "$schema": "dimwit/asset_task/v1",
    "required": ["asset_id", "asset_type", "source_kind", "intended_gameplay_role", "promotion_target", "human_review_required"],
    "fields": {
        "asset_id": "string", "asset_type": "string",
        "source_kind": "image|text_spec|screenshot_failure|design_need|existing_placeholder",
        "source_paths": "array<string>", "intended_gameplay_role": "string",
        "wanefall_style_requirements": "array<string>", "forbidden_traits": "array<string>",
        "technical_requirements": "array<string>", "validation_requirements": "array<string>",
        "promotion_target": "review_only", "human_review_required": "bool",
    },
    "supported_asset_types": [
        "hostile_construct_enemy", "player_armor", "helmet", "weapon", "vehicle_shell", "waneboard_shell",
        "arena_prop", "cover_piece", "door_gate", "chamber_module", "target_dummy", "destructible",
        "HUD_icon", "objective_marker", "VFX_mesh", "VFX_material", "tracer", "muzzle_flash",
        "impact_effect", "damage_effect", "audio_placeholder_spec", "music_prompt_spec",
    ],
})

# ---------------------------------------------------------------- WANEFALL style law
w("config/wanefall_style_law.json", {
    "required": ["dark alien combat", "mature sci-fi", "teal/cyan Wane energy", "red/orange hostile weak points",
                 "third-person gameplay readability", "controller-first visual clarity", "clean silhouettes"],
    "forbidden": ["magenta target identity", "white debug junk", "generic fantasy", "cheerful cartoon plastic",
                  "random AI ornament clutter", "unreadable black blobs", "copyrighted direct copying"],
    "required_identity_traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
    "forbidden_identity_traits": ["magenta", "purple_core", "white_debug", "white_blob", "black_blob",
                                  "near_black_metallic_body", "cartoon", "plastic_toy", "generic_fantasy", "ornament_clutter"],
    "enforced_by": "dimwit.core.evaluate_style_law (deterministic, hard-fails on forbidden identity traits)",
})

# ---------------------------------------------------------------- provenance / license policy
w("config/provenance_policy.json", {
    "classes": ["owned_reference", "generated_concept", "licensed_reference", "public_domain", "open_license",
                "unknown_license", "forbidden"],
    "promotable_classes": ["owned_reference", "generated_concept", "licensed_reference", "public_domain", "open_license"],
    "rules": ["unknown_license cannot be directly copied", "copyrighted designs cannot be cloned",
              "external references can inspire transformed WANEFALL-native assets only when lawful",
              "generated assets need source prompt/file/provenance recorded",
              "commercial use uncertainty must be flagged"],
    "hard_fail": "Dimwit cannot promote an asset without a promotable provenance class + a recorded source.",
    "enforced_by": "dimwit.core.evaluate_provenance (fail-closed pre-gate before generation)",
})

# ---------------------------------------------------------------- reference intake schema
w("validators/reference_intake_schema.json", {
    "accepts": ["image reference", "AI-generated concept", "screenshot", "failed gameplay screenshot",
                "moodboard image", "existing placeholder actor", "text asset spec", "design doc need"],
    "extracts": ["asset_class", "silhouette", "dominant_shapes", "palette", "materials", "useful_traits",
                 "forbidden_traits", "gameplay_role", "scale_estimate", "camera_readability_risk", "wanefall_translation_plan"],
    "output": "a WANEFALL-native asset_spec (never a literal copy of the source)",
})

# ---------------------------------------------------------------- WANEFALL translation rules
w("config/wanefall_translation_rules.json", {
    "law": "Dimwit must never copy an image literally; it translates references into WANEFALL-native specs.",
    "example": {
        "source_read": "angular armored alien drone with glowing core",
        "wanefall_translation": "dark hostile Wane construct with teal vents and red weak point",
        "keep": ["wide shoulders", "head silhouette", "central weak point"],
        "reject": ["cartoon proportions", "magenta glow", "ornament clutter"],
        "asset_output_type": "hostile_construct_enemy",
    },
    "always_keep_if_present": ["clean silhouette", "central weak point", "readable head"],
    "always_reject": ["magenta glow", "cartoon proportions", "ornament clutter", "literal copyrighted shapes"],
})

# ---------------------------------------------------------------- generation backends
w("config/generation_backends.json", {
    "initial": ["blender_procedural_mesh", "blender_kitbash", "unreal_import_build_commandlet",
                "unreal_material_assignment", "unreal_collision_setup", "unreal_preview_placement",
                "hero_capture", "player_camera_validation"],
    "optional_future": ["image_to_3d_model", "mesh_cleanup_library", "texture_generation", "normal_map_generation",
                        "lod_generator", "vfx_generator", "hud_icon_generator", "audio_placeholder_generator"],
    "availability_note": "V1 requires NO unavailable external models; backends are adapters that record intent and call existing WANEFALL pipeline steps when present.",
    "existing_wanefall_pipeline_hooks": {
        "blender": "SourceAssets/Blender/scripts/gen_*.py -> exports/*.fbx",
        "unreal_import": "WanefallBlenderImport commandlet -> /Game/Wanefall/Imported/Blender/",
        "material_author": "WanefallMaterialAuthorCommandlet",
        "hero_capture": "-WANEFALLHEROCAPTURE (AWanefallSculptedEnemyHeroCaptureDirector)",
        "player_camera": "-WANEFALLMOVEMENTCAPTURE (AWanefallMovementCaptureDirector)",
        "dual_gate": "WanefallDualGateLiveQA commandlet",
    },
})

# ---------------------------------------------------------------- blender builder contract
w("config/blender_asset_builder_contract.json", {
    "input": "asset_spec.json", "outputs": [".blend", ".fbx_or_glb", "mesh_metadata.json"],
    "must_define": ["material_slot_definitions", "scale_units_cm", "origin_pivot_convention", "collision_proxy_suggestion"],
    "origin_convention": "feet at z=0, facing -X (front toward player), single welded mesh, ordered material slots",
    "v1_note": "may adapt the existing hostile-construct Blender script but must generalize to future asset classes",
})

# ---------------------------------------------------------------- unreal import contract
w("config/unreal_import_contract.json", {
    "input_fields": ["source_art_path", "destination_game_path", "asset_type", "material_mapping", "collision_mode",
                     "scale", "socket_attach_metadata", "preview_placement_metadata", "validation_commandlet_path"],
    "staging_destination": "/Game/Wanefall/Dimwit/Staging/",
    "integrates_with": "WanefallBlenderImport commandlet path when safe",
    "rule": "Dimwit imports to a STAGING path only; active-slice import requires operator approval.",
})

# ---------------------------------------------------------------- validation gates
w("config/asset_validation_gates.json", {
    "gates": ["technical", "style", "hero_capture", "player_camera", "performance", "collision", "provenance", "promotion"],
    "outputs": ["technical_validation.json", "style_validation.json", "hero_capture_validation.json",
                "player_camera_validation.json", "performance_sanity.json", "collision_sanity.json",
                "provenance_validation.json", "promotion_verdict.json"],
    "hard_gates": ["style", "provenance"],
    "promotion_threshold": 0.70,
    "rule": "player_camera evidence cannot be replaced by hero_capture; both are required for a full promotion verdict.",
})

# ---------------------------------------------------------------- recursive mutation loop
w("config/recursive_asset_mutation_loop.json", {
    "loop": ["generate candidate", "import candidate", "capture candidate", "score candidate",
             "classify weakest dimension", "mutate candidate", "reimport", "recapture", "rescore",
             "compare to previous best", "keep best", "repeat until threshold/blocker/max", "promote to review only if thresholds pass"],
    "scored_dimensions": ["wanefall_genre_fit", "silhouette_readability", "third_person_camera_readability",
                          "hero_readability", "gameplay_readability", "palette_discipline", "not_generic_ai_slop",
                          "not_magenta_dominant", "not_white_debug_junk", "not_black_blob", "collision_sanity",
                          "scale_sanity", "material_sanity", "performance_risk", "import_correctness", "hit_destroy_state_clarity"],
    "max_iterations": 6, "promote_threshold": 0.70, "keep_best": True,
    "implemented_by": "dimwit.engine.recursive_mutation_loop",
})

# ---------------------------------------------------------------- human review package schema
w("config/human_review_package_schema.json", {
    "includes": ["asset spec", "source/provenance", "hero contact sheet", "player-camera contact sheet",
                 "technical proof", "style proof", "promotion verdict", "known weaknesses",
                 "accept/reject/taste-adjust checklist"],
    "human_decisions": ["ACCEPT_FOR_ACTIVE_SLICE", "REJECT", "REQUEST_TASTE_ADJUSTMENT", "KEEP_AS_FALLBACK", "ARCHIVE"],
    "rule": "Dimwit cannot choose the final human decision automatically.",
})

# ---------------------------------------------------------------- human screenshot override
w("config/human_screenshot_override_policy.json", {
    "rule": "If a human live screenshot shows an asset or scene is visually unacceptable, that OVERRIDES automated PASS/PASS_WITH_NOTES.",
    "precedence": ["human_live_screenshot_override", "player_camera_validation", "hero_capture_validation", "automated_score"],
    "mandatory": True,
})

# ---------------------------------------------------------------- active game bridge policy
w("config/active_game_bridge_policy.json", {
    "dimwit_may": ["write source art and review packages", "import to a STAGING path", "validate in preview scenes",
                    "propose active-slice promotion"],
    "dimwit_may_not": ["automatically promote assets into the WANEFALL active slice"],
    "human_approval_required_for": "active-slice promotion",
    "staging_paths": ["/Game/Wanefall/Dimwit/Staging/", "SourceArt/WANEFALL/Dimwit/"],
})

# ---------------------------------------------------------------- lessons memory (seeded)
LESSONS = [
    "near-black metallic enemies read as black blobs",
    "magenta core material contaminated targets, beacon, tracer, and map identity",
    "teal enemies camouflage against teal environments",
    "hero capture cannot replace gameplay-lane validation",
    "gameplay-lane validation cannot replace hero mesh validation",
    "primitive kitbash has a ceiling",
    "player-camera evidence beats commandlet proof",
    "human screenshot override beats automated PASS",
    "white debug junk is a hard visual blocker",
    "cave/rock Wane Trial contamination is forbidden",
    "debug HUD visible by default is a blocker",
    "a bright HDR red emissive (>=2.6) clips through ACES and desaturates toward orange; keep emissive in-range (~1.0)",
    "fixed-camera no-pawn no-HUD no-motion-blur hero capture is the way to prove a mesh fairly",
]
lp = ROOT / "lessons" / "dimwit_asset_lessons.jsonl"
with lp.open("w", encoding="utf-8") as f:
    for i, l in enumerate(LESSONS):
        f.write(json.dumps({"lesson_id": f"L{i:03d}", "lesson": l, "source": "WANEFALL passes V1..V35", "from_real_run": True}) + "\n")

# ---------------------------------------------------------------- test workload seed asset
# hostile_construct_enemy_variant_001 references the EXISTING validated sculpted enemy (owned), with a
# deliberately-weak gameplay-readability score so the recursive loop has something real to improve.
HERO_SHEET = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\Saved\ShowMeAI\WanefallSculptedEnemyHeroCapture\20260625T053611Z_final_hero_enemy_contact_sheet.png"
LANE_SHEET = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\Saved\ShowMeAI\WanefallGameplayLaneEnemyRead\Captures\20260625T012606Z_baseline_gameplay_lane_contact_sheet.png"
asset_dir = ROOT / "assets" / "hostile_construct_enemy_variant_001"
asset_dir.mkdir(parents=True, exist_ok=True)
(asset_dir / "asset_spec.json").write_text(json.dumps({
    "asset_type": "hostile_construct_enemy",
    "mesh_ref": "/Game/Wanefall/Imported/Blender/SM_WaneHostileConstruct_Prototype",
    "scale_cm": 270,
    "tri_estimate": 4200,
    "collision_proxy": "capsule+box",
    "material_slots": ["M_WaneEnemyDarkBody4", "M_WaneEnemyCoreRed", "M_WaneEnemyCoreRed", "M_WaneEnemyTealAccent"],
    "palette": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point"],
    "traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
    "camera_readability": 0.45,
    "gameplay_readability": 0.40,
    "hit_destroy_clarity": 0.8,
    "_evidence": {"hero_contact_sheet": HERO_SHEET, "player_camera_contact_sheet": LANE_SHEET},
}, indent=2), encoding="utf-8")
(asset_dir / "provenance.json").write_text(json.dumps({
    "license_class": "owned_reference",
    "derived_from": "WANEFALL existing sculpted hostile construct (SM_WaneHostileConstruct_Prototype), validated in V35 hero capture",
    "source_file": "SourceAssets/Blender/scripts (project-owned)",
    "direct_copy_of_copyright": False,
    "commercial_use_uncertain": False,
}, indent=2), encoding="utf-8")
(asset_dir / "style_analysis.json").write_text(json.dumps({
    "source_read": "existing dark hostile Wane construct, validated coherent + red weak point in hero capture",
    "wanefall_native": True,
    "known_weakness": "gameplay-lane camera readability (dark body camouflages in the busy teal lane)",
    "translation_plan": "keep silhouette + red weak point; propose per-enemy rim light + body value lift for gameplay separation (review-only)",
}, indent=2), encoding="utf-8")

# ---------------------------------------------------------------- seed queue
qp = ROOT / "queues" / "dimwit_asset_queue.jsonl"
with qp.open("w", encoding="utf-8") as f:
    f.write(json.dumps({
        "asset_task_id": "hostile_construct_enemy_variant_001",
        "asset_type": "hostile_construct_enemy",
        "priority": 1,
        "source_kind": "existing_placeholder",
        "source_paths": ["/Game/Wanefall/Imported/Blender/SM_WaneHostileConstruct_Prototype"],
        "intended_gameplay_role": "first-encounter hostile construct, Wane Trial lane",
        "status": "REQUESTED",
        "attempt_count": 0,
        "latest_candidate_id": None,
        "blockers": [],
        "promotion_target": "review_only",
        "next_action": "run_lifecycle",
    }, sort_keys=True) + "\n")

# empty ledger (created on first append) — touch the proofs dir
(ROOT / "proofs").mkdir(parents=True, exist_ok=True)

print(json.dumps({"dimwit_root": str(ROOT), "subdirs": SUBDIRS, "lessons_seeded": len(LESSONS),
                  "test_asset": "hostile_construct_enemy_variant_001", "configs_written": True}, indent=2))
