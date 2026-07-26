"""WANEFALL all-in-one Unreal game-builder engine proof layer.

This module turns "autonomous game builder" into a concrete, fail-closed
scorecard. It does not fabricate assets or promote the game as complete. It
maps every major Unreal production surface to current proof artifacts, ranks
the remaining blockers, and runs through the same Dimwit production pipeline
ceiling as the rest of the system.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dimwit.pipelines.base import Artifact, OPERATOR_ONLY, ProductionPipeline, Verdict


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
ARTIFACT_DIR = ROOT / "artifacts" / "unreal_game_builder"
DOCTRINE_PATH = ARTIFACT_DIR / "unreal_game_builder_doctrine.json"
SCORECARD_PATH = ARTIFACT_DIR / "unreal_game_builder_scorecard.json"
FINAL_REPORT_PATH = ARTIFACT_DIR / "UNREAL_GAME_BUILDER_FINAL_REPORT_20260629.json"
MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
REVIEW_CEILING = "PROMOTED_TO_REVIEW"

REQUIRED_GAME_BUILDER_LANES = [
    "product_vision_design",
    "style_law_reference_intake",
    "source_asset_ingest_provenance",
    "character_asset_generation",
    "metahuman_transformation",
    "rigging_animation_runtime",
    "gameplay_movement_combat",
    "weapons_items_vehicles",
    "maps_world_environment",
    "materials_shaders_lighting",
    "vfx_audio_feedback",
    "modes_gameflow",
    "ui_hud_command_surface",
    "social_rank_stats_settings",
    "backend_multiplayer_services",
    "ai_npc_encounter_design",
    "performance_profiling_optimization",
    "build_packaging_deploy",
    "real_game_playtest_validation",
    "proof_integrity_provenance",
    "recursive_orchestration_learning",
    "tool_discovery_external_reference",
    "license_dependency_security",
    "human_gate_review_ceiling",
]

SEVERITY_WEIGHT = {
    "REJECTED": 100,
    "FAIL": 76,
    "BLOCKED": 72,
    "NEEDS_EVIDENCE": 50,
    "PASS_WITH_NOTES": 12,
    "PASS": 0,
}
MAX_VALIDATION_REPORT_AGE_SECONDS = 15 * 60

LANE_CRITICALITY = {
    "proof_integrity_provenance": 90,
    "metahuman_transformation": 86,
    "ui_hud_command_surface": 60,
    "real_game_playtest_validation": 58,
    "source_asset_ingest_provenance": 34,
    "recursive_orchestration_learning": 54,
    "character_asset_generation": 52,
    "rigging_animation_runtime": 50,
    "gameplay_movement_combat": 48,
    "weapons_items_vehicles": 46,
    "maps_world_environment": 44,
    "build_packaging_deploy": 42,
    "performance_profiling_optimization": 38,
    "vfx_audio_feedback": 36,
    "modes_gameflow": 34,
    "materials_shaders_lighting": 32,
    "license_dependency_security": 30,
    "backend_multiplayer_services": 26,
    "social_rank_stats_settings": 24,
    "ai_npc_encounter_design": 22,
    "tool_discovery_external_reference": 20,
    "style_law_reference_intake": 18,
    "product_vision_design": 16,
    "human_gate_review_ceiling": 14,
}

DOMAIN_TO_LANE = {
    "characters_static_full_nanite": "character_asset_generation",
    "rigged_skeletal_meshes": "rigging_animation_runtime",
    "animation_wiring": "rigging_animation_runtime",
    "combat": "gameplay_movement_combat",
    "gameplay_code": "gameplay_movement_combat",
    "materials_shaders": "materials_shaders_lighting",
    "environment_maps": "maps_world_environment",
    "vfx_audio": "vfx_audio_feedback",
    "intent_conformance": "product_vision_design",
    "design_system": "style_law_reference_intake",
    "proof_integrity": "proof_integrity_provenance",
    "movement_traversal": "gameplay_movement_combat",
    "weapons_inplay": "weapons_items_vehicles",
    "hud_readability": "ui_hud_command_surface",
    "ui_hud": "ui_hud_command_surface",
    "br_loop": "modes_gameflow",
    "pipeline_contracts": "license_dependency_security",
    "metahuman_character_pipeline": "metahuman_transformation",
    "real_game_runtime": "real_game_playtest_validation",
    "packaged_build": "build_packaging_deploy",
    "autonomy_engine": "recursive_orchestration_learning",
}


def _lane_specs() -> list[dict[str, Any]]:
    return [
        {
            "lane_id": "product_vision_design",
            "display_name": "Product Vision And Design",
            "target_standard": "Every build begins from an intent contract, design system, and concrete player-facing goal.",
            "quality_bar": "No feature is accepted without intent conformance and design-system validation.",
            "validation_domains": ["intent_conformance", "design_system"],
            "source_artifacts": ["config/intent_contract_schema.json", "config/design_md/baseline.DESIGN.md"],
            "required_artifacts": ["assets/<id>/intent_contract.json", "DESIGN.md"],
            "production_pipelines": ["design_md", "intent_conformance"],
            "unreal_touchpoints": ["DESIGN.md", "Content/Wanefall", "Source/WanefallGreybox"],
            "next_action": "Keep intent contracts and DESIGN.md constraints attached to every asset, map, mode, and UI slice.",
        },
        {
            "lane_id": "style_law_reference_intake",
            "display_name": "Style Law And Reference Intake",
            "target_standard": "References are classified before use; WANEFALL visual law remains native and enforceable.",
            "quality_bar": "No blind dependency import, no license-unclear reference adoption, no off-style asset promotion.",
            "validation_domains": ["design_system", "autonomy_engine"],
            "source_artifacts": ["config/wanefall_style_law.json", "artifacts/autonomy/autonomy_capability_matrix.json"],
            "required_artifacts": ["WANEFALL style law", "external reference catalog"],
            "production_pipelines": ["autonomy_engine"],
            "unreal_touchpoints": ["Content/Wanefall/Dimwit", "DESIGN.md"],
            "next_action": "Keep reference intake as classified inspiration only until license, version, and dependency gates are green.",
        },
        {
            "lane_id": "source_asset_ingest_provenance",
            "display_name": "Source Asset Ingest And Provenance",
            "target_standard": "Every source asset has provenance, license class, source file evidence, and promotion-safe lineage.",
            "quality_bar": "Missing or unpromotable provenance blocks the lane.",
            "validation_domains": ["proof_integrity", "characters_static_full_nanite"],
            "source_artifacts": ["source_art", "assets", "proofs/dimwit_asset_proof_ledger.jsonl"],
            "required_artifacts": ["source file", "provenance record", "hash-chained proof entry"],
            "production_pipelines": ["character_fidelity", "marble_ingest"],
            "unreal_touchpoints": ["Content/Wanefall/Dimwit/Characters", "SourceAssets"],
            "next_action": "Repair proof-ledger integrity and keep source/license evidence attached before downstream generation.",
        },
        {
            "lane_id": "character_asset_generation",
            "display_name": "Character Asset Generation",
            "target_standard": "Generate and import source-ready high-detail characters with Nanite, materials, topology, optics, and provenance proof.",
            "quality_bar": "A character is not game-ready unless static, topology, optics, material, and provenance gates pass.",
            "validation_domains": ["characters_static_full_nanite", "topology", "optics_semantic"],
            "source_artifacts": ["artifacts/hi3d_*.glb", "artifacts/char_fidelity_result.json"],
            "required_artifacts": ["GLB/FBX", "UE uasset", "material bindings", "render proof"],
            "production_pipelines": ["character_fidelity"],
            "unreal_touchpoints": ["Content/Wanefall/Dimwit/Characters"],
            "next_action": "Keep all eight WANEFALL characters source-ready while MetaHuman transformation evidence is produced separately.",
        },
        {
            "lane_id": "metahuman_transformation",
            "display_name": "MetaHuman Transformation",
            "target_standard": "Transform source 3D characters into MetaHuman-compatible outputs through a UE-version-safe Epic lane.",
            "quality_bar": "Source readiness is insufficient; real MetaHuman character, identity, or DNA-style output evidence must exist.",
            "validation_domains": ["metahuman_character_pipeline"],
            "source_artifacts": ["artifacts/metahuman_utilization/metahuman_utilization_audit.json"],
            "required_artifacts": ["MetaHuman output evidence", "version-gate record", "license-boundary record"],
            "production_pipelines": ["character_fidelity", "rigging"],
            "unreal_touchpoints": ["RigLogic", "HairStrands", "MetaHuman for Maya workflow"],
            "next_action": "Produce real MetaHuman output evidence through the UE 5.8-safe workflow; do not claim conversion before output exists.",
        },
        {
            "lane_id": "rigging_animation_runtime",
            "display_name": "Rigging, Retargeting, And Runtime Animation",
            "target_standard": "Characters deform, retarget, and animate in the actual runtime skeleton path.",
            "quality_bar": "Structural rig checks and live animation proof both pass.",
            "validation_domains": ["rigged_skeletal_meshes", "animation_wiring"],
            "source_artifacts": ["artifacts/rig", "artifacts/validation/anim_live_proof.json"],
            "required_artifacts": ["skeletal mesh", "skeleton compatibility proof", "animation proof"],
            "production_pipelines": ["rigging", "animation"],
            "unreal_touchpoints": ["SK_Mannequin", "ABP_Manny", "Content/Mannequins"],
            "next_action": "Preserve mannequin-compatible skeleton and runtime animation evidence after any character or MetaHuman changes.",
        },
        {
            "lane_id": "gameplay_movement_combat",
            "display_name": "Gameplay Movement And Combat",
            "target_standard": "Movement verbs, traversal, targeting, weakpoints, and combat feedback are proven by runtime-facing gates.",
            "quality_bar": "Signature traversal and combat states trigger in evidence, not only C++ declarations.",
            "validation_domains": ["movement_traversal", "combat", "gameplay_code"],
            "source_artifacts": ["artifacts/traversal_capture_result.json", "artifacts/combat_capture_result.json"],
            "required_artifacts": ["movement proof", "combat proof", "input binding proof"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["WanefallPrototypeCharacter", "DefaultInput.ini"],
            "next_action": "Keep grapple, flip, roll, combat states, and active-game bindings under proof after every gameplay edit.",
        },
        {
            "lane_id": "weapons_items_vehicles",
            "display_name": "Weapons, Items, And Vehicles",
            "target_standard": "Weapons and mobility items resolve to real meshes and usable in-hand behavior.",
            "quality_bar": "No placeholder weapons, dead ADS, or unresolved registry entries.",
            "validation_domains": ["weapons_inplay"],
            "source_artifacts": ["Content/Wanefall/Dimwit/Weapons", "artifacts/weapons_capture_result.json"],
            "required_artifacts": ["weapon registry", "in-hand capture", "ADS proof"],
            "production_pipelines": ["materials_shaders", "real_game_validation"],
            "unreal_touchpoints": ["Content/Wanefall/Dimwit/Weapons", "WanefallPrototypeCharacter"],
            "next_action": "Extend the same proof law from guns to items and vehicles before claiming full sandbox coverage.",
        },
        {
            "lane_id": "maps_world_environment",
            "display_name": "Maps, Worlds, And Environments",
            "target_standard": "Maps are playable, lit, navigable, and visually WANEFALL rather than blockout shells.",
            "quality_bar": "Player starts, lighting, identity geometry, and runtime visibility are validated.",
            "validation_domains": ["environment_maps", "real_game_runtime"],
            "source_artifacts": ["Content/Wanefall/Maps", "artifacts/env_build_result.json"],
            "required_artifacts": ["map package", "spawn proof", "lighting proof", "real-game frame"],
            "production_pipelines": ["environment", "marble_ingest", "real_game_validation"],
            "unreal_touchpoints": ["Content/Wanefall/Maps", "WorldPartition", "PlayerStart"],
            "next_action": "Keep playable map proof green while replacing blockout-looking areas with WANEFALL-native art.",
        },
        {
            "lane_id": "materials_shaders_lighting",
            "display_name": "Materials, Shaders, And Lighting",
            "target_standard": "Materials compile, bind correct textures, avoid legacy Phong regressions, and obey the Wane surface law.",
            "quality_bar": "No grey fallback, broken base color, over-metallic blacking, or unlit game surfaces.",
            "validation_domains": ["materials_shaders", "characters_static_full_nanite", "environment_maps"],
            "source_artifacts": ["artifacts/materials_build_result.json", "config/wanefall_style_law.json"],
            "required_artifacts": ["master material/function", "material instance proof", "lighting proof"],
            "production_pipelines": ["materials_shaders", "character_fidelity", "environment"],
            "unreal_touchpoints": ["Content/Wanefall/Dimwit/Materials", "Interchange glTF material base"],
            "next_action": "Route all generated assets through the same de-chrome and Wane material gates.",
        },
        {
            "lane_id": "vfx_audio_feedback",
            "display_name": "VFX, Audio, And Feedback",
            "target_standard": "Effects and sounds are real assets tied to gameplay verbs, not empty shells or slop banter.",
            "quality_bar": "Niagara and audio assets exist, are non-stubbed, and remain gameplay-addressable.",
            "validation_domains": ["vfx_audio"],
            "source_artifacts": ["Content/Wanefall/Dimwit/VFX", "Content/Wanefall/Dimwit/Audio"],
            "required_artifacts": ["Niagara system", "sound wave", "feedback binding proof"],
            "production_pipelines": ["vfx", "audio"],
            "unreal_touchpoints": ["Niagara", "MetaSound", "SoundWave"],
            "next_action": "Tie VFX and audio feedback to combat, traversal, and UI state captures.",
        },
        {
            "lane_id": "modes_gameflow",
            "display_name": "Modes And Gameflow",
            "target_standard": "BR, arcade, practice, and transition flows are deterministic, playable, and validated.",
            "quality_bar": "A mode must have state progression and resolution proof before it is treated as built.",
            "validation_domains": ["br_loop", "combat"],
            "source_artifacts": ["artifacts/br_loop_result.json", "Source/WanefallGreybox/Private/WanefallArcadeModes.cpp"],
            "required_artifacts": ["mode sim proof", "state transition proof", "resolution proof"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["GameMode", "PlayerController", "WanefallModeSimHarness"],
            "next_action": "Add dedicated arcade and practice-range flow proof using the existing mode simulation law.",
        },
        {
            "lane_id": "ui_hud_command_surface",
            "display_name": "UI, HUD, And Command Surface",
            "target_standard": "The game exposes all modes, settings, social, rank, stats, and runtime HUD state through one fast command surface.",
            "quality_bar": "The UI cannot regress to blank, stock-white, unreadable, or missing gameplay-critical indicators.",
            "validation_domains": ["ui_hud", "hud_readability", "real_game_runtime"],
            "source_artifacts": ["artifacts/hud_capture_result.json", "artifacts/real_game_validation/real_game_validation_result.json"],
            "required_artifacts": ["HUD capture", "command-surface runtime proof", "weakpoint indicator proof"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["WanefallLobbyHUD", "WanefallMatchHUD", "WanefallLobbyPlayerController"],
            "next_action": "Finish weakpoint projection proof while preserving the no-Hold all-in-one command surface.",
        },
        {
            "lane_id": "social_rank_stats_settings",
            "display_name": "Social, Rank, Stats, And Settings",
            "target_standard": "Profiles, party entry, leaderboards, stats, settings, and ranked surfaces have local contracts before live backend use.",
            "quality_bar": "No menu affordance claims a live service until local and backend adapters are validated.",
            "validation_domains": [],
            "source_artifacts": ["codex_handoff.json", "docs/WANEFALL_BACKEND_ADAPTER_SPEC.md"],
            "required_artifacts": ["local social contract", "stats schema", "leaderboard adapter proof"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["WanefallLobbyHUD", "GameInstance", "SaveGame"],
            "next_action": "Add local contracts for settings, stats, rank, party, friends, and leaderboards before service integration.",
            "fallback_state": "NEEDS_EVIDENCE",
        },
        {
            "lane_id": "backend_multiplayer_services",
            "display_name": "Backend And Multiplayer Services",
            "target_standard": "Networking, matchmaking, profiles, parties, storage, and leaderboards are thin-adapter gated.",
            "quality_bar": "No production online readiness claim from mock mode or unvalidated SDK adoption.",
            "validation_domains": [],
            "source_artifacts": ["docs/WANEFALL_BACKEND_ADAPTER_SPEC.md"],
            "required_artifacts": ["thin adapter", "local mock proof", "SDK license/version pin"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["OnlineSubsystem", "GameInstance", "PlayerState"],
            "next_action": "Create the local thin-adapter proof before adopting or wiring any live backend.",
            "fallback_state": "NEEDS_EVIDENCE",
        },
        {
            "lane_id": "ai_npc_encounter_design",
            "display_name": "AI, NPC, And Encounter Design",
            "target_standard": "NPC behavior, encounter pacing, readability, and challenge loops are validated as gameplay systems.",
            "quality_bar": "Combat proof alone is not enough; NPC decision and encounter state evidence must exist.",
            "validation_domains": ["combat"],
            "source_artifacts": ["artifacts/combat_capture_result.json", "Source/WanefallGreybox"],
            "required_artifacts": ["NPC behavior proof", "encounter sim proof", "readability capture"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["AIController", "BehaviorTree", "EQS", "SmartObjects"],
            "next_action": "Add encounter-specific proof that distinguishes target behavior, readable attacks, and state transitions.",
            "force_notes": True,
        },
        {
            "lane_id": "performance_profiling_optimization",
            "display_name": "Performance, Profiling, And Optimization",
            "target_standard": "Performance budgets are captured from the actual runtime and linked to map, asset, and UI changes.",
            "quality_bar": "No release-style package without current runtime performance evidence.",
            "validation_domains": [],
            "source_artifacts": ["Saved/Profiling", "artifacts/validation"],
            "required_artifacts": ["runtime profile", "frame budget", "asset cost report"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["Unreal Insights", "stat unit", "Nanite", "Lumen"],
            "next_action": "Add real runtime performance capture after the remaining proof/HUD/MetaHuman blockers are resolved.",
            "fallback_state": "NEEDS_EVIDENCE",
        },
        {
            "lane_id": "build_packaging_deploy",
            "display_name": "Build, Packaging, And Deploy",
            "target_standard": "Editor, game, packaging, launch shortcut, and Shared Folder handoff are validated as a release-style chain.",
            "quality_bar": "Build success alone is not packaging readiness; a UAT package, executable hash manifest, packaged smoke, and packaged log scan must pass.",
            "validation_domains": ["packaged_build", "pipeline_contracts"],
            "source_artifacts": ["artifacts/packaged_build_validation/packaged_build_result.json", "artifacts/packaged_build_validation/package_manifest.json"],
            "required_artifacts": ["UAT log", "package manifest", "executable hash", "packaged runtime smoke", "packaged log scan"],
            "production_pipelines": ["packaged_build_validation", "unreal_game_builder_engine"],
            "unreal_touchpoints": ["RunUAT BuildCookRun", "UAT", "Windows packaged executable", "Saved/Logs"],
            "next_action": "Keep packaged-build proof fresh before release-style review claims.",
        },
        {
            "lane_id": "real_game_playtest_validation",
            "display_name": "Real Game Playtest Validation",
            "target_standard": "The running WANEFALL window is the source of truth for game validation.",
            "quality_bar": "Fresh desktop capture, frame burst, log scan, and placeholder geometry gates must pass.",
            "validation_domains": ["real_game_runtime"],
            "source_artifacts": ["artifacts/real_game_validation/real_game_validation_result.json"],
            "required_artifacts": ["live still", "frame burst", "UE log scan", "validation result JSON"],
            "production_pipelines": ["real_game_validation"],
            "unreal_touchpoints": ["UnrealEditor -game", "Wanefall_Lobby", "Saved/Logs"],
            "next_action": "Keep the command-surface real-game validation green before expanding new subsystems.",
        },
        {
            "lane_id": "proof_integrity_provenance",
            "display_name": "Proof Integrity And Provenance",
            "target_standard": "All ledgers and promotion evidence are hash-chained, fail-closed, and operator-ceiling safe.",
            "quality_bar": "A broken chain rejects the global suite even if gameplay looks good.",
            "validation_domains": ["proof_integrity"],
            "source_artifacts": ["ledger/validation.jsonl", "dimwit/pipelines/validation.py"],
            "required_artifacts": ["hash-chained ledger", "provenance source evidence", "operator ceiling proof"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["None; orchestration proof surface"],
            "next_action": "Repair validation ledger chain integrity without deleting legacy evidence or weakening validators.",
        },
        {
            "lane_id": "recursive_orchestration_learning",
            "display_name": "Recursive Orchestration And Learning",
            "target_standard": "Dimwit can plan, schedule, execute, validate, learn, and queue the next bounded game-building slice.",
            "quality_bar": "Every queue item has validation, rollback, repeat guard, and review ceiling.",
            "validation_domains": ["autonomy_engine", "pipeline_contracts"],
            "source_artifacts": ["artifacts/autonomy", "config/director_tasks.json", "codex_handoff.json"],
            "required_artifacts": ["autonomy matrix", "ranked queue", "director task", "handoff state"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["ModelContextProtocol", "ShowMeAIBridge", "PythonScriptPlugin"],
            "next_action": "Regenerate this builder report after validation and feed the ranked queue into bounded repair slices.",
        },
        {
            "lane_id": "tool_discovery_external_reference",
            "display_name": "Tool Discovery And External Reference",
            "target_standard": "External tools and references are scored, classified, and adopted only through native WANEFALL contracts.",
            "quality_bar": "No dependency is adopted without license, version, and rollback boundaries.",
            "validation_domains": ["autonomy_engine"],
            "source_artifacts": ["artifacts/autonomy/autonomy_capability_matrix.json"],
            "required_artifacts": ["tool scoring ledger", "license classification", "adoption decision"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["Plugins", "Editor utility tooling", "Blender scripts"],
            "next_action": "Add a dedicated tool scoring ledger before adopting any new asset-generation or Unreal automation tool.",
        },
        {
            "lane_id": "license_dependency_security",
            "display_name": "License, Dependency, And Security",
            "target_standard": "Every pipeline, external reference, plugin, and generated asset preserves license and dependency boundaries.",
            "quality_bar": "GPL, Epic tooling, SDK, and service adoption boundaries must stay explicit and fail-closed.",
            "validation_domains": ["pipeline_contracts", "metahuman_character_pipeline", "autonomy_engine"],
            "source_artifacts": ["config/production_pipelines.json", "artifacts/pipeline_contracts/pipeline_contract_audit.json"],
            "required_artifacts": ["contract audit", "license classification", "dependency version gate"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["WanefallGreybox.uproject", "Plugins"],
            "next_action": "Keep contract, MetaHuman, and external-reference gates green before any dependency or service adoption.",
        },
        {
            "lane_id": "human_gate_review_ceiling",
            "display_name": "Human Gate And Review Ceiling",
            "target_standard": "Autonomy stops at review; only the operator can accept active-slice promotion.",
            "quality_bar": "No report, queue, or pipeline writes operator-only promotion states.",
            "validation_domains": ["pipeline_contracts", "autonomy_engine"],
            "source_artifacts": ["codex_handoff.json", "dimwit/pipelines/base.py"],
            "required_artifacts": ["review ceiling", "operator-only scan", "handoff note"],
            "production_pipelines": ["unreal_game_builder_engine"],
            "unreal_touchpoints": ["Review packages", "Desktop Shared Folder"],
            "next_action": "Preserve PROMOTED_TO_REVIEW as the autonomous ceiling in every generated queue item and pipeline result.",
        },
    ]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"{path}: {exc}"}
    return data if isinstance(data, dict) else {"_error": f"{path}: root is not an object"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _domain_counts(validation_report: dict[str, Any], domain: str) -> dict[str, int]:
    by_domain = validation_report.get("by_domain") if isinstance(validation_report.get("by_domain"), dict) else {}
    counts = by_domain.get(domain) if isinstance(by_domain.get(domain), dict) else {}
    return {
        "PASS": int(counts.get("PASS", 0) or 0),
        "FAIL": int(counts.get("FAIL", 0) or 0),
        "BLOCKED": int(counts.get("BLOCKED", 0) or 0),
        "REJECTED": int(counts.get("REJECTED", 0) or 0),
    }


def _validation_freshness(report: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else float(now)
    try:
        run_ts = float(report.get("run_ts"))
    except (TypeError, ValueError):
        return {"fresh": False, "age_seconds": None,
                "max_age_seconds": MAX_VALIDATION_REPORT_AGE_SECONDS,
                "reason": "full-suite report has no valid run_ts"}
    age = max(0.0, now - run_ts)
    return {"fresh": age <= MAX_VALIDATION_REPORT_AGE_SECONDS,
            "age_seconds": round(age, 3),
            "max_age_seconds": MAX_VALIDATION_REPORT_AGE_SECONDS,
            "reason": None if age <= MAX_VALIDATION_REPORT_AGE_SECONDS else "full-suite report is stale"}


def _state_from_counts(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return "NEEDS_EVIDENCE"
    if counts["REJECTED"] > 0:
        return "REJECTED"
    if counts["FAIL"] > 0:
        return "FAIL"
    if counts["BLOCKED"] > 0:
        return "BLOCKED"
    return "PASS"


def _worst_state(states: list[str], fallback: str = "NEEDS_EVIDENCE") -> str:
    if not states:
        return fallback
    return max(states, key=lambda state: SEVERITY_WEIGHT.get(state, 1))


def _results_for_domain(validation_report: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    results = validation_report.get("results") if isinstance(validation_report.get("results"), list) else []
    return [item for item in results if isinstance(item, dict) and item.get("domain") == domain]


def _blockers_for_domains(validation_report: dict[str, Any], domains: list[str]) -> list[str]:
    blockers: list[str] = []
    for domain in domains:
        for item in _results_for_domain(validation_report, domain):
            if item.get("state") == "PASS":
                continue
            validator_id = str(item.get("validator_id", "unknown_validator"))
            issues = item.get("issues") if isinstance(item.get("issues"), list) else []
            detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
            blocked = str(detail.get("blocked") or detail.get("error") or "")
            text = "; ".join(str(issue) for issue in issues if issue) or blocked or str(item.get("state"))
            blockers.append(f"{validator_id}: {text}")
    return blockers


def _engine_version(project: Path) -> str:
    data = _read_json(project / "WanefallGreybox.uproject")
    value = data.get("EngineAssociation")
    return str(value) if value is not None else ""


def _enabled_plugins(project: Path) -> list[str]:
    data = _read_json(project / "WanefallGreybox.uproject")
    plugins = data.get("Plugins") if isinstance(data.get("Plugins"), list) else []
    names = [
        str(item["Name"])
        for item in plugins
        if isinstance(item, dict) and item.get("Enabled") is True and item.get("Name")
    ]
    return sorted(names)


def _validation_command_for_lane(lane_id: str, domains: list[str]) -> str:
    commands = {
        "product_vision_design": "python scripts/pipeline/run_validation.py --domain intent_conformance --no-ue",
        "style_law_reference_intake": "python scripts/pipeline/run_validation.py --domain design_system --no-ue",
        "source_asset_ingest_provenance": "python scripts/pipeline/run_validation.py --domain proof_integrity --no-ue",
        "character_asset_generation": "python scripts/pipeline/run_validation.py --domain characters_static_full_nanite --no-ue",
        "metahuman_transformation": "python scripts/pipeline/run_validation.py --domain metahuman_character_pipeline --no-ue",
        "rigging_animation_runtime": "python scripts/pipeline/run_validation.py --domain animation_wiring --no-ue",
        "gameplay_movement_combat": "python scripts/pipeline/run_validation.py --domain movement_traversal --no-ue",
        "weapons_items_vehicles": "python scripts/pipeline/run_validation.py --domain weapons_inplay --no-ue",
        "maps_world_environment": "python scripts/pipeline/run_validation.py --domain environment_maps --no-ue",
        "materials_shaders_lighting": "python scripts/pipeline/run_validation.py --domain materials_shaders --no-ue",
        "vfx_audio_feedback": "python scripts/pipeline/run_validation.py --domain vfx_audio --no-ue",
        "modes_gameflow": "python scripts/pipeline/run_validation.py --domain br_loop --no-ue",
        "ui_hud_command_surface": "python scripts/pipeline/run_validation.py --domain ui_hud --no-ue",
        "social_rank_stats_settings": "python scripts/pipeline/run_validation.py --domain unreal_game_builder_engine --no-ue",
        "backend_multiplayer_services": "python scripts/pipeline/run_validation.py --domain unreal_game_builder_engine --no-ue",
        "ai_npc_encounter_design": "python scripts/pipeline/run_validation.py --domain combat --no-ue",
        "performance_profiling_optimization": "python scripts/pipeline/run_validation.py --domain unreal_game_builder_engine --no-ue",
        "build_packaging_deploy": "python scripts/pipeline/run_validation.py --domain packaged_build --no-ue",
        "real_game_playtest_validation": "python scripts/pipeline/run_validation.py --domain real_game_runtime --no-ue",
        "proof_integrity_provenance": "python scripts/pipeline/run_validation.py --domain proof_integrity --no-ue",
        "recursive_orchestration_learning": "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
        "tool_discovery_external_reference": "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
        "license_dependency_security": "python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue",
        "human_gate_review_ceiling": "python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue",
    }
    if lane_id in commands:
        return commands[lane_id]
    if domains:
        return f"python scripts/pipeline/run_validation.py --domain {domains[0]} --no-ue"
    return "python scripts/pipeline/run_validation.py --domain unreal_game_builder_engine --no-ue"


def _rollback_for_lane(lane_id: str) -> str:
    return (
        f"Revert only files touched for {lane_id}, preserve the proof artifacts, "
        "then rerun the lane validation command and this builder engine gate."
    )


def _lane_state(spec: dict[str, Any], validation_report: dict[str, Any]) -> tuple[str, dict[str, dict[str, int]]]:
    domains = list(spec.get("validation_domains") or [])
    domain_counts = {domain: _domain_counts(validation_report, domain) for domain in domains}
    states = [_state_from_counts(counts) for counts in domain_counts.values()]
    fallback = str(spec.get("fallback_state") or "NEEDS_EVIDENCE")
    state = _worst_state(states, fallback=fallback)
    if state == "PASS" and spec.get("force_notes"):
        state = "PASS_WITH_NOTES"
    return state, domain_counts


def _build_lane(spec: dict[str, Any], validation_report: dict[str, Any]) -> dict[str, Any]:
    lane_id = str(spec["lane_id"])
    domains = list(spec.get("validation_domains") or [])
    state, domain_counts = _lane_state(spec, validation_report)
    blockers = _blockers_for_domains(validation_report, domains)
    if state == "NEEDS_EVIDENCE" and not blockers:
        blockers = [f"{lane_id} needs a repo-native proof artifact and validation hook."]
    if state == "PASS_WITH_NOTES" and not blockers:
        blockers = [f"{lane_id} has base proof, but coverage is not yet exhaustive for the target standard."]
    evidence = [f"artifacts/validation/validation_report.json#{domain}" for domain in domains]
    evidence.extend(str(path) for path in spec.get("source_artifacts", []))
    return {
        "lane_id": lane_id,
        "display_name": spec["display_name"],
        "target_standard": spec["target_standard"],
        "quality_bar": spec["quality_bar"],
        "current_state": state,
        "validation_domains": domains,
        "domain_counts": domain_counts,
        "evidence": evidence,
        "blockers": blockers,
        "next_action": spec["next_action"],
        "validation_command": _validation_command_for_lane(lane_id, domains),
        "rollback": _rollback_for_lane(lane_id),
        "required_artifacts": list(spec.get("required_artifacts") or []),
        "production_pipelines": list(spec.get("production_pipelines") or []),
        "unreal_touchpoints": list(spec.get("unreal_touchpoints") or []),
        "promotion_threshold": REVIEW_CEILING,
        "autonomy_boundary": "Autonomous execution can generate, test, validate, and package evidence only up to PROMOTED_TO_REVIEW.",
        "proof_artifact_path": f"artifacts/unreal_game_builder/{lane_id}.json",
    }


def _non_pass_validation_results(validation_report: dict[str, Any]) -> list[dict[str, Any]]:
    results = validation_report.get("results") if isinstance(validation_report.get("results"), list) else []
    blockers = []
    for item in results:
        if not isinstance(item, dict) or item.get("state") == "PASS":
            continue
        blockers.append({
            "validator_id": item.get("validator_id"),
            "domain": item.get("domain"),
            "state": item.get("state"),
            "issues": item.get("issues") if isinstance(item.get("issues"), list) else [],
            "detail": item.get("detail") if isinstance(item.get("detail"), dict) else {},
            "mapped_lane": DOMAIN_TO_LANE.get(str(item.get("domain"))),
        })
    return blockers


def _queue_title(lane: dict[str, Any]) -> str:
    titles = {
        "proof_integrity_provenance": "Repair proof ledger integrity",
        "metahuman_transformation": "Produce real MetaHuman output evidence",
        "ui_hud_command_surface": "Finish HUD weakpoint and command-surface proof",
        "source_asset_ingest_provenance": "Seal source asset provenance",
        "performance_profiling_optimization": "Add runtime performance profile proof",
        "backend_multiplayer_services": "Add local backend adapter proof",
        "social_rank_stats_settings": "Add local social/rank/stats/settings contracts",
    }
    return titles.get(str(lane["lane_id"]), f"Improve {str(lane['lane_id']).replace('_', ' ')}")


def _rank_queue(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for lane in lanes:
        state = str(lane.get("current_state"))
        if state == "PASS":
            continue
        lane_id = str(lane["lane_id"])
        score = SEVERITY_WEIGHT.get(state, 1) + LANE_CRITICALITY.get(lane_id, 0)
        queue.append({
            "rank": 0,
            "priority_score": score,
            "title": _queue_title(lane),
            "affected_lane": lane_id,
            "current_state": state,
            "expected_improvement": lane["next_action"],
            "validation_command": lane["validation_command"],
            "rollback_notes": lane["rollback"],
            "failure_risks": list(lane.get("blockers") or []),
            "required_artifacts": list(lane.get("required_artifacts") or []),
            "production_pipelines": list(lane.get("production_pipelines") or []),
            "promotion_threshold": REVIEW_CEILING,
            "proof_artifact_path": lane["proof_artifact_path"],
            "repeat_guard": "Do not retry this candidate if its cited proof artifact and source validation evidence are unchanged.",
        })
    queue.sort(key=lambda item: (-int(item["priority_score"]), str(item["affected_lane"])))
    for index, item in enumerate(queue, start=1):
        item["rank"] = index
    return queue


def _doctrine_laws() -> dict[str, str]:
    return {
        "real_game_truth": "The running WANEFALL game window outranks static claims, constructor state, and proxy captures.",
        "fail_closed": "Missing evidence blocks; it never becomes a claim.",
        "recursive_loop": "Plan, build, validate, repair, rerank, and repeat through bounded queue items.",
        "review_ceiling": "Autonomous promotion stops at PROMOTED_TO_REVIEW.",
        "asset_truth": "Assets need source files, provenance, style conformance, runtime evidence, and rollback paths.",
        "metahuman_truth": "Source-ready 3D characters are not MetaHumans until real MetaHuman output evidence exists.",
        "license_truth": "Reference-only, GPL, Epic tooling, SDK, and backend boundaries stay explicit before adoption.",
        "unreal_truth": "Every lane names its Unreal touchpoints, validation command, and likely proof artifacts.",
        "no_bloat": "The Hold is not a product surface; command UI and runtime gameflow are the active frontend.",
        "operator_gate": "Human acceptance and active-slice promotion are operator-only states.",
    }


def build_unreal_game_builder_report(root: Path, project: Path) -> dict[str, Any]:
    root = Path(root)
    project = Path(project)
    # Derive lane states from the latest FULL-scope suite report, never the mutable per-run report
    # (a domain-scoped rewrite made all 24 lanes read NEEDS_EVIDENCE — 2026-07-01 audit finding).
    from dimwit.state_sync import load_validation_report_with_provenance
    validation_report, report_provenance = load_validation_report_with_provenance(root)
    validation_freshness = _validation_freshness(validation_report)
    if not validation_freshness["fresh"]:
        validation_report = {
            "suite_verdict": "BLOCKED",
            "counts": {"PASS": 0, "FAIL": 0, "BLOCKED": 1, "REJECTED": 0},
            "total": 1,
            "by_domain": {},
            "results": [{
                "validator_id": "source_full_suite_fresh",
                "domain": "unreal_game_builder_engine",
                "state": "BLOCKED",
                "issues": [validation_freshness["reason"]],
                "detail": validation_freshness,
            }],
        }
    real_game = _read_json(root / "artifacts" / "real_game_validation" / "real_game_validation_result.json")
    packaged = _read_json(root / "artifacts" / "packaged_build_validation" / "packaged_build_result.json")
    metahuman = _read_json(root / "artifacts" / "metahuman_utilization" / "metahuman_utilization_audit.json")
    contracts = _read_json(root / "artifacts" / "pipeline_contracts" / "pipeline_contract_audit.json")
    autonomy = _read_json(root / "artifacts" / "autonomy" / "AUTONOMY_CAPABILITY_FINAL_REPORT_20260628.json")
    handoff = _read_json(root / "codex_handoff.json")
    manifest = _read_json(root / "config" / "production_pipelines.json")
    director_tasks = _read_json(root / "config" / "director_tasks.json")

    lanes = [_build_lane(spec, validation_report) for spec in _lane_specs()]
    queue = _rank_queue(lanes)
    remaining_global_blockers = _non_pass_validation_results(validation_report)
    counts = validation_report.get("counts") if isinstance(validation_report.get("counts"), dict) else {}
    non_pass_count = sum(int(counts.get(key, 0) or 0) for key in ("FAIL", "BLOCKED", "REJECTED"))
    classification = "PASS_WITH_BLOCKERS" if non_pass_count else "PASS"
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": time.time(),
        "source_validation_report": {**report_provenance, **validation_freshness},
        "classification": classification,
        "status": ("UNREAL_GAME_BUILDER_ENGINE_BLOCKED_STALE_VALIDATION"
                   if not validation_freshness["fresh"] else
                   ("UNREAL_GAME_BUILDER_ENGINE_READY_WITH_RANKED_BLOCKERS" if non_pass_count
                    else "UNREAL_GAME_BUILDER_ENGINE_READY")),
        "ceiling": REVIEW_CEILING,
        "engine_name": "Dimwit Unreal Game Builder Engine",
        "engine_goal": "Autonomously orchestrate WANEFALL Unreal production lanes from design through build, validation, packaging, and recursive repair.",
        "unreal_version_detected": _engine_version(project),
        "enabled_project_plugins": _enabled_plugins(project),
        "doctrine_laws": _doctrine_laws(),
        "required_lanes": list(REQUIRED_GAME_BUILDER_LANES),
        "source_truth": {
            "validation_suite_verdict": validation_report.get("suite_verdict"),
            "validation_counts": counts,
            "validation_total": validation_report.get("total"),
            "real_game_state": real_game.get("state"),
            "real_game_suite_pass": real_game.get("suite_pass"),
            "packaged_build_state": packaged.get("state"),
            "packaged_build_suite_pass": packaged.get("suite_pass"),
            "packaged_build_executable": ((packaged.get("package") or {}).get("executable") if isinstance(packaged.get("package"), dict) else None),
            "packaged_build_total_bytes": ((((packaged.get("package") or {}).get("manifest") or {}).get("total_bytes")) if isinstance(packaged.get("package"), dict) else None),
            "metahuman_classification": (metahuman.get("summary") or {}).get("classification") if isinstance(metahuman.get("summary"), dict) else None,
            "metahuman_output_present": (metahuman.get("metahuman_outputs") or {}).get("present") if isinstance(metahuman.get("metahuman_outputs"), dict) else None,
            "contract_summary": contracts.get("summary") if isinstance(contracts.get("summary"), dict) else {},
            "autonomy_classification": autonomy.get("classification"),
            "handoff_ceiling": handoff.get("ceiling"),
            "manifest_pipeline_count": len(manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}),
            "director_task_count": len(director_tasks.get("tasks") if isinstance(director_tasks.get("tasks"), list) else []),
        },
        "game_builder_lanes": lanes,
        "recursive_game_build_queue": queue,
        "remaining_global_blockers": remaining_global_blockers,
        "next_recursive_candidates": queue[:12],
        "validation_commands": [
            "python -m dimwit.tests.test_unreal_game_builder_engine",
            "python scripts/pipeline/run_pipeline.py unreal_game_builder_engine wanefall_autonomous_studio",
            "python scripts/pipeline/run_validation.py --domain unreal_game_builder_engine --no-ue",
            "python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue",
            "python scripts/pipeline/run_director.py --validate --no-ue",
            "python scripts/pipeline/run_validation.py --no-ue",
        ],
        "proof_artifacts": [
            str(DOCTRINE_PATH),
            str(SCORECARD_PATH),
            str(FINAL_REPORT_PATH),
        ],
        "rollback_notes": "Remove the unreal_game_builder_engine pipeline, registry gates, manifest/director task, and artifacts, then rerun pipeline_contracts and autonomy_engine validation.",
        "pass_fail_reasoning": "This engine passes only if it covers every Unreal production lane, exposes current blockers, ranks bounded repair actions, and preserves the review ceiling.",
    }
    report["self_validation"] = validate_unreal_game_builder_report(report)
    if report["self_validation"]["passed"] is not True:
        if validation_freshness["fresh"]:
            report["classification"] = "FAIL"
            report["status"] = "UNREAL_GAME_BUILDER_ENGINE_SELF_VALIDATION_FAILED"
        else:
            report["classification"] = "BLOCKED"
    return report


def write_unreal_game_builder_report(
    root: Path,
    project: Path,
    doctrine_path: Path = DOCTRINE_PATH,
    scorecard_path: Path = SCORECARD_PATH,
    final_report_path: Path = FINAL_REPORT_PATH,
) -> dict[str, Any]:
    report = build_unreal_game_builder_report(root, project)
    report["proof_artifacts"] = [str(doctrine_path), str(scorecard_path), str(final_report_path)]
    report["self_validation"] = validate_unreal_game_builder_report(report)
    doctrine = {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "engine_name": report["engine_name"],
        "ceiling": report["ceiling"],
        "doctrine_laws": report["doctrine_laws"],
        "required_lanes": report["required_lanes"],
        "validation_commands": report["validation_commands"],
    }
    scorecard = {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "source_validation_report": report.get("source_validation_report"),
        "classification": report["classification"],
        "source_truth": report["source_truth"],
        "game_builder_lanes": report["game_builder_lanes"],
        "recursive_game_build_queue": report["recursive_game_build_queue"],
        "remaining_global_blockers": report["remaining_global_blockers"],
    }
    _write_json(Path(doctrine_path), doctrine)
    _write_json(Path(scorecard_path), scorecard)
    _write_json(Path(final_report_path), report)
    return report


def validate_unreal_game_builder_report(report: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(report, dict):
        return {"passed": False, "issues": ["game builder report is not an object"]}
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        issues.append("generated_at missing or not numeric")
    if report.get("ceiling") != REVIEW_CEILING:
        issues.append("report ceiling is not PROMOTED_TO_REVIEW")
    lanes = report.get("game_builder_lanes") if isinstance(report.get("game_builder_lanes"), list) else []
    lane_ids = {str(item.get("lane_id")) for item in lanes if isinstance(item, dict)}
    missing_lanes = sorted(set(REQUIRED_GAME_BUILDER_LANES) - lane_ids)
    if missing_lanes:
        issues.append(f"missing required game-builder lanes: {missing_lanes}")
    for lane in lanes:
        if not isinstance(lane, dict):
            issues.append("game-builder lane entry is not an object")
            continue
        lane_id = str(lane.get("lane_id") or "unknown")
        for field in ("target_standard", "quality_bar", "current_state", "evidence", "next_action", "validation_command", "rollback"):
            if not lane.get(field):
                issues.append(f"{lane_id} missing {field}")
        if lane.get("promotion_threshold") != REVIEW_CEILING:
            issues.append(f"{lane_id} has non-review promotion threshold")
        if not isinstance(lane.get("required_artifacts"), list) or not lane.get("required_artifacts"):
            issues.append(f"{lane_id} missing required_artifacts")
        if not isinstance(lane.get("unreal_touchpoints"), list) or not lane.get("unreal_touchpoints"):
            issues.append(f"{lane_id} missing unreal_touchpoints")
    queue = report.get("recursive_game_build_queue") if isinstance(report.get("recursive_game_build_queue"), list) else []
    ranks = [item.get("rank") for item in queue if isinstance(item, dict)]
    if ranks and ranks != list(range(1, len(ranks) + 1)):
        issues.append("recursive game-build queue ranks are not contiguous from 1")
    for item in queue:
        if not isinstance(item, dict):
            issues.append("queue item is not an object")
            continue
        title = str(item.get("title") or "unknown")
        for field in ("affected_lane", "validation_command", "rollback_notes", "proof_artifact_path"):
            if not item.get(field):
                issues.append(f"queue item {title} missing {field}")
        if item.get("promotion_threshold") != REVIEW_CEILING:
            issues.append(f"queue item {title} has non-review promotion threshold")
    blockers = report.get("remaining_global_blockers") if isinstance(report.get("remaining_global_blockers"), list) else []
    queue_lanes = {str(item.get("affected_lane")) for item in queue if isinstance(item, dict)}
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        lane = blocker.get("mapped_lane")
        if lane and lane not in queue_lanes:
            issues.append(f"current blocker for domain {blocker.get('domain')} is not visible in queue lane {lane}")
    source_truth = report.get("source_truth") if isinstance(report.get("source_truth"), dict) else {}
    source_report = report.get("source_validation_report") if isinstance(report.get("source_validation_report"), dict) else {}
    if source_report.get("fresh") is not True:
        issues.append("source full-suite report is missing freshness proof or is stale")
    if source_truth.get("validation_suite_verdict") not in {"PASS", "REJECTED", "FAIL", "BLOCKED", None}:
        issues.append(f"unknown validation suite verdict: {source_truth.get('validation_suite_verdict')}")
    if source_truth.get("validation_suite_verdict") != "PASS" and not blockers:
        issues.append("non-pass validation suite has no remaining_global_blockers list")
    laws = report.get("doctrine_laws") if isinstance(report.get("doctrine_laws"), dict) else {}
    for key in ("real_game_truth", "fail_closed", "recursive_loop", "review_ceiling", "operator_gate"):
        if not laws.get(key):
            issues.append(f"doctrine missing law: {key}")
    state_field_names = {
        "state",
        "current_state",
        "status",
        "ceiling",
        "promotion_state",
        "promotion_threshold",
        "lifecycle_state",
    }

    def _find_operator_only_values(value: Any, path: str = "report") -> list[tuple[str, str]]:
        matches: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if str(key).lower() in state_field_names and child in OPERATOR_ONLY:
                    matches.append((child_path, str(child)))
                matches.extend(_find_operator_only_values(child, child_path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                matches.extend(_find_operator_only_values(child, f"{path}[{index}]"))
        return matches

    for path, state in _find_operator_only_values(report):
        issues.append(f"operator-only state used at {path}: {state}")
    return {
        "passed": not issues,
        "issues": issues,
        "required_lane_count": len(REQUIRED_GAME_BUILDER_LANES),
        "lane_count": len(lanes),
        "queue_count": len(queue),
        "blocker_count": len(blockers),
    }


class UnrealGameBuilderEnginePipeline(ProductionPipeline):
    name = "unreal_game_builder_engine"
    kind = "autonomous_unreal_game_builder_engine"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        root = Path(task.get("root") or ROOT)
        project = Path(task.get("project") or PROJECT)
        output_dir = Path(task.get("output_dir") or (root / "artifacts" / "unreal_game_builder"))
        return {
            "asset_id": str(task.get("asset_id") or "wanefall_autonomous_studio"),
            "root": root,
            "project": project,
            "doctrine_path": output_dir / "unreal_game_builder_doctrine.json",
            "scorecard_path": output_dir / "unreal_game_builder_scorecard.json",
            "final_report_path": output_dir / "UNREAL_GAME_BUILDER_FINAL_REPORT_20260629.json",
        }

    def execute(self, plan: dict) -> Artifact:
        report = write_unreal_game_builder_report(
            Path(plan["root"]),
            Path(plan["project"]),
            Path(plan["doctrine_path"]),
            Path(plan["scorecard_path"]),
            Path(plan["final_report_path"]),
        )
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={
                "final_report_path": str(plan["final_report_path"]),
                "lane_count": len(report.get("game_builder_lanes") or []),
                "queue_count": len(report.get("recursive_game_build_queue") or []),
                "classification": report.get("classification"),
            },
            provenance={
                "source": "local_dimwit_wanefall_validation_artifacts",
                "license": "operator-owned-game",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        report_path = Path(plan["final_report_path"])
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return Verdict(score=0.0, passed=False, issues=[f"final report unreadable: {exc}"], evidence=[str(report_path)])
        validation = validate_unreal_game_builder_report(report)
        return Verdict(
            score=1.0 if validation["passed"] else 0.0,
            passed=bool(validation["passed"]),
            hard_fail=False,
            issues=list(validation.get("issues") or []),
            detail={
                "classification": report.get("classification"),
                "lane_count": validation.get("lane_count"),
                "queue_count": validation.get("queue_count"),
                "blocker_count": validation.get("blocker_count"),
            },
            evidence=[str(report_path)],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact
