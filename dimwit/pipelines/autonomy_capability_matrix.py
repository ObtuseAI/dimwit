"""WANEFALL autonomy capability matrix and recursive repair queue.

This is an offline proof aggregator. It reads existing Dimwit/WANEFALL
evidence and emits machine-readable next actions. It does not execute repairs
or promote anything past the autonomous review ceiling.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dimwit.pipelines.base import OPERATOR_ONLY


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
ARTIFACT_DIR = ROOT / "artifacts" / "autonomy"
MATRIX_PATH = ARTIFACT_DIR / "autonomy_capability_matrix.json"
QUEUE_PATH = ARTIFACT_DIR / "recursive_improvement_queue.json"
FINAL_REPORT_PATH = ARTIFACT_DIR / "AUTONOMY_CAPABILITY_FINAL_REPORT_20260628.json"
MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
REVIEW_CEILING = "PROMOTED_TO_REVIEW"

REQUIRED_LANES = [
    "runtime_validation",
    "movement_traversal",
    "animation_feel",
    "weapon_feel",
    "controller_input",
    "character_pipeline",
    "metahuman_calibration",
    "environment_maps",
    "vfx_audio",
    "ui_hud",
    "backend_social",
    "arcade_mode",
    "practice_range",
    "br_loop",
    "action_transitions",
    "tool_discovery",
    "external_references",
    "license_dependency_gates",
    "recursive_orchestration",
    "proof_integrity",
    "build_packaging",
    "performance",
]

SEVERITY_WEIGHT = {
    "REJECTED": 100,
    "FAIL": 76,
    "BLOCKED": 72,
    "NEEDS_EVIDENCE": 64,
    "PARTIAL": 52,
    "NEEDS_REVIEW": 48,
    "PLANNED": 34,
    "PASS_WITH_NOTES": 10,
    "PASS": 0,
}

LANE_CRITICALITY = {
    "runtime_validation": 55,
    "proof_integrity": 52,
    "movement_traversal": 48,
    "weapon_feel": 46,
    "character_pipeline": 44,
    "metahuman_calibration": 43,
    "animation_feel": 42,
    "controller_input": 40,
    "ui_hud": 36,
    "environment_maps": 34,
    "br_loop": 33,
    "build_packaging": 32,
    "performance": 30,
    "vfx_audio": 28,
    "recursive_orchestration": 26,
    "backend_social": 22,
    "arcade_mode": 20,
    "practice_range": 20,
    "action_transitions": 18,
    "license_dependency_gates": 18,
    "tool_discovery": 12,
    "external_references": 10,
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"{path}: {exc}"}
    if not isinstance(data, dict):
        return {"_error": f"{path}: root is not an object"}
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _engine_version(project: Path) -> str:
    data = _read_json(project / "WanefallGreybox.uproject")
    value = data.get("EngineAssociation")
    return str(value) if value is not None else ""


def _enabled_plugins(project: Path) -> list[str]:
    data = _read_json(project / "WanefallGreybox.uproject")
    plugins = data.get("Plugins") if isinstance(data.get("Plugins"), list) else []
    names: list[str] = []
    for item in plugins:
        if isinstance(item, dict) and item.get("Enabled") is True and item.get("Name"):
            names.append(str(item["Name"]))
    return sorted(names)


def external_reference_catalog() -> list[dict[str, Any]]:
    return [
        {
            "source_name": "Embody Unreal Engine Source",
            "source_url": "https://github.com/snorkelingcode/Embody-Unreal-Engine-Source",
            "license": "Upstream license must be verified before code adoption",
            "license_class": "REFERENCE_REVIEW_REQUIRED",
            "adoption_mode": "REFERENCE_ONLY",
            "wanefall_subsystem_mapping": ["movement_traversal", "animation_feel", "controller_input", "runtime_validation"],
            "extracted_concepts": ["runtime command architecture", "embodiment debug state", "camera and pose inspection"],
            "rejected_concepts": ["companion avatar scope", "TTS/social-avatar bloat", "blind source import"],
            "dependency_risk": "MEDIUM",
            "license_risk": "NEEDS_REVIEW",
            "version_risk": "UNREAL_API_REVIEW_REQUIRED",
            "proof_artifact_path": "artifacts/autonomy/autonomy_capability_matrix.json",
            "final_classification": "REFERENCE_ONLY",
        },
        {
            "source_name": "Character DNA Addon",
            "source_url": "https://github.com/poly-hammer/character-dna-addon/pulls",
            "license": "GPLv3 unless separately proven otherwise",
            "license_class": "GPL_REFERENCE_ONLY",
            "adoption_mode": "REFERENCE_ONLY",
            "wanefall_subsystem_mapping": ["character_pipeline", "metahuman_calibration"],
            "extracted_concepts": ["Blender to Unreal character iteration", "groom export workflow shape", "DNA validation concepts"],
            "rejected_concepts": ["GPL implementation copy", "runtime redistribution", "bundled addon dependency"],
            "dependency_risk": "HIGH_IF_IMPORTED",
            "license_risk": "HIGH_IF_COPIED",
            "version_risk": "METAHUMAN_GENERATION_DEPENDENT",
            "proof_artifact_path": "artifacts/metahuman_utilization/metahuman_utilization_audit.json",
            "final_classification": "REFERENCE_ONLY",
        },
        {
            "source_name": "Epic MetaHuman DNA Calibration",
            "source_url": "https://github.com/EpicGames/MetaHuman-DNA-Calibration",
            "license": "Epic MetaHuman DNA Calibration custom license",
            "license_class": "EPIC_CUSTOM_VERSION_GATED",
            "adoption_mode": "OFFICIAL_REFERENCE_WITH_VERSION_GATE",
            "wanefall_subsystem_mapping": ["character_pipeline", "metahuman_calibration"],
            "extracted_concepts": ["DNA inspection", "neutral pose validation", "LOD cleanup", "joint and mesh naming checks"],
            "rejected_concepts": ["runtime embedding", "redistributing Epic tooling", "claiming UE 5.6+ support without proof"],
            "dependency_risk": "MEDIUM_TOOLCHAIN_ONLY",
            "license_risk": "EPIC_TOOLING_BOUNDARY",
            "version_risk": "BLOCKED_UNREAL_VERSION_FOR_DIRECT_UE_5_6_PLUS_DNA_ROUTE",
            "proof_artifact_path": "artifacts/metahuman_utilization/metahuman_utilization_audit.json",
            "final_classification": "OFFICIAL_REFERENCE_WITH_VERSION_GATE",
        },
        {
            "source_name": "Claude-Code-Game-Studios",
            "source_url": "https://github.com/Donchitos/Claude-Code-Game-Studios",
            "license": "MIT as published upstream at review time",
            "license_class": "PERMISSIVE_REFERENCE",
            "adoption_mode": "REFERENCE_ONLY",
            "wanefall_subsystem_mapping": ["recursive_orchestration", "proof_integrity", "build_packaging"],
            "extracted_concepts": ["role lanes", "path-scoped rules", "QA hooks", "session state"],
            "rejected_concepts": ["manual-heavy approval sprawl", "wholesale agent import", "unbounded template bloat"],
            "dependency_risk": "LOW_REFERENCE_ONLY",
            "license_risk": "LOW_IF_REFERENCE_ONLY",
            "version_risk": "WORKFLOW_DRIFT_REVIEW_REQUIRED",
            "proof_artifact_path": "artifacts/autonomy/autonomy_capability_matrix.json",
            "final_classification": "REFERENCE_ONLY",
        },
        {
            "source_name": "Nakama",
            "source_url": "https://github.com/heroiclabs/nakama",
            "license": "Apache-2.0 server project; Unreal adapter license must be verified per component",
            "license_class": "PERMISSIVE_WITH_ADAPTER_REVIEW",
            "adoption_mode": "THIN_ADAPTER",
            "wanefall_subsystem_mapping": ["backend_social"],
            "extracted_concepts": ["profiles", "friends", "parties", "matchmaking", "leaderboards", "storage", "local dev mode"],
            "rejected_concepts": ["mandatory live backend", "combat authority handoff", "production readiness claims from mock mode"],
            "dependency_risk": "MEDIUM_OPTIONAL_SERVICE",
            "license_risk": "LOW_WITH_COMPONENT_REVIEW",
            "version_risk": "SDK_VERSION_PIN_REQUIRED",
            "proof_artifact_path": "artifacts/autonomy/autonomy_capability_matrix.json",
            "final_classification": "THIN_ADAPTER",
        },
        {
            "source_name": "Cocos2d-x",
            "source_url": "https://github.com/cocos2d/cocos2d-x",
            "license": "MIT",
            "license_class": "PERMISSIVE_REFERENCE",
            "adoption_mode": "REFERENCE_ONLY",
            "wanefall_subsystem_mapping": ["action_transitions", "arcade_mode", "practice_range", "ui_hud"],
            "extracted_concepts": ["action sequences", "spawn/repeat/reverse composition", "scene transitions", "deterministic samples"],
            "rejected_concepts": ["parallel engine", "Cocos dependency", "Unreal loop rewrite"],
            "dependency_risk": "HIGH_IF_IMPORTED_LOW_IF_REFERENCE_ONLY",
            "license_risk": "LOW_REFERENCE_ONLY",
            "version_risk": "NOT_AN_UNREAL_DEPENDENCY",
            "proof_artifact_path": "artifacts/autonomy/autonomy_capability_matrix.json",
            "final_classification": "REFERENCE_ONLY",
        },
        {
            "source_name": "MagicTools",
            "source_url": "https://github.com/ellisonleao/magictools",
            "license": "MIT",
            "license_class": "PERMISSIVE_REFERENCE_INDEX",
            "adoption_mode": "REFERENCE_ONLY",
            "wanefall_subsystem_mapping": ["tool_discovery", "license_dependency_gates"],
            "extracted_concepts": ["tool scoring categories", "asset pipeline discovery", "license review before adoption"],
            "rejected_concepts": ["blind tool adoption", "unrelated tool sprawl", "discovery replacing implementation"],
            "dependency_risk": "LOW_REFERENCE_ONLY",
            "license_risk": "PER_CANDIDATE_REVIEW_REQUIRED",
            "version_risk": "FRESHNESS_REVIEW_REQUIRED",
            "proof_artifact_path": "artifacts/autonomy/autonomy_capability_matrix.json",
            "final_classification": "REFERENCE_ONLY",
        },
    ]


def _domain_counts(validation_report: dict[str, Any], domain: str) -> dict[str, int]:
    by_domain = validation_report.get("by_domain") if isinstance(validation_report.get("by_domain"), dict) else {}
    counts = by_domain.get(domain) if isinstance(by_domain.get(domain), dict) else {}
    return {
        "PASS": int(counts.get("PASS", 0) or 0),
        "FAIL": int(counts.get("FAIL", 0) or 0),
        "BLOCKED": int(counts.get("BLOCKED", 0) or 0),
        "REJECTED": int(counts.get("REJECTED", 0) or 0),
    }


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


def _results_for_domain(validation_report: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    results = validation_report.get("results") if isinstance(validation_report.get("results"), list) else []
    return [item for item in results if isinstance(item, dict) and item.get("domain") == domain]


def _blockers_for_domain(validation_report: dict[str, Any], domain: str) -> list[str]:
    blockers: list[str] = []
    for item in _results_for_domain(validation_report, domain):
        if item.get("state") == "PASS":
            continue
        validator_id = str(item.get("validator_id", "unknown_validator"))
        issues = item.get("issues") if isinstance(item.get("issues"), list) else []
        detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
        blocked = str(detail.get("blocked") or detail.get("error") or "")
        text = "; ".join(str(issue) for issue in issues if issue) or blocked
        blockers.append(f"{validator_id}: {text}".strip())
    return blockers


def _reference_names_for_lane(lane: str, catalog: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in catalog:
        mapping = item.get("wanefall_subsystem_mapping") if isinstance(item.get("wanefall_subsystem_mapping"), list) else []
        if lane in mapping:
            names.append(str(item["source_name"]))
    return names


def _validation_command_for_lane(lane: str) -> str:
    commands = {
        "runtime_validation": "python scripts/pipeline/run_validation.py --domain real_game_runtime --no-ue",
        "movement_traversal": "python scripts/pipeline/run_validation.py --domain movement_traversal --no-ue",
        "animation_feel": "python scripts/pipeline/run_validation.py --domain animation_wiring --no-ue",
        "weapon_feel": "python scripts/pipeline/run_validation.py --domain weapons_inplay --no-ue",
        "controller_input": "python scripts/pipeline/run_validation.py --domain gameplay_code --no-ue",
        "character_pipeline": "python scripts/pipeline/run_validation.py --domain characters_static_full_nanite --no-ue",
        "metahuman_calibration": "python scripts/pipeline/run_validation.py --domain metahuman_character_pipeline --no-ue",
        "environment_maps": "python scripts/pipeline/run_validation.py --domain environment_maps --no-ue",
        "vfx_audio": "python scripts/pipeline/run_validation.py --domain vfx_audio --no-ue",
        "ui_hud": "python scripts/pipeline/run_validation.py --domain ui_hud --no-ue",
        "backend_social": "python scripts/pipeline/run_validation.py --domain gameplay_code --no-ue",
        "arcade_mode": "python scripts/pipeline/run_validation.py --domain br_loop --no-ue",
        "practice_range": "python scripts/pipeline/run_validation.py --domain combat --no-ue",
        "br_loop": "python scripts/pipeline/run_validation.py --domain br_loop --no-ue",
        "action_transitions": "python scripts/pipeline/run_validation.py --domain gameplay_code --no-ue",
        "tool_discovery": "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
        "external_references": "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
        "license_dependency_gates": "python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue",
        "recursive_orchestration": "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
        "proof_integrity": "python scripts/pipeline/run_validation.py --domain proof_integrity --no-ue",
        "build_packaging": "python scripts/pipeline/run_validation.py --domain packaged_build --no-ue",
        "performance": "python scripts/pipeline/run_validation.py --no-ue",
    }
    return commands[lane]


def _files_for_lane(lane: str) -> list[str]:
    files = {
        "runtime_validation": ["Saved/Logs/WanefallGreybox.log", "Content/Wanefall/Maps", "dimwit/pipelines/real_game_validation.py"],
        "movement_traversal": ["Source/WanefallGreybox/Private/WanefallPrototypeCharacter.cpp", "artifacts/traversal_capture_result.json"],
        "animation_feel": ["Source/WanefallGreybox/Private/WanefallPrototypeCharacter.cpp", "Content/Mannequins/Animations"],
        "weapon_feel": ["Source/WanefallGreybox/Private/WanefallPrototypeCharacter.cpp", "Content/Wanefall/Dimwit/Weapons"],
        "controller_input": ["Config/DefaultInput.ini", "Source/WanefallGreybox/Private/WanefallPrototypeCharacter.cpp"],
        "character_pipeline": ["Content/Wanefall/Dimwit/Characters", "artifacts/char_fidelity_result.json"],
        "metahuman_calibration": ["docs/WANEFALL_METAHUMAN_CALIBRATION_CHECKLIST.md", "artifacts/metahuman_utilization"],
        "environment_maps": ["Content/Wanefall/Maps", "artifacts/env_build_result.json"],
        "vfx_audio": ["Content/Wanefall/Dimwit/VFX", "Content/Wanefall/Dimwit/Audio"],
        "ui_hud": ["Source/WanefallGreybox/Private/WanefallMatchHUD.cpp", "artifacts/hud_capture_result.json"],
        "backend_social": ["Source/WanefallGreybox/Private/WanefallNetworkSocialCombat.cpp", "docs/WANEFALL_BACKEND_ADAPTER_SPEC.md"],
        "arcade_mode": ["Source/WanefallGreybox/Private/WanefallArcadeModes.cpp", "docs/WANEFALL_PLAYABLE_WANE_TRIAL_SYSTEMS_V1.md"],
        "practice_range": ["docs/WANEFALL_PLAYABLE_PRACTICE_RANGE_SYSTEMS_V1.md", "Source/WanefallGreybox/Private"],
        "br_loop": ["Source/WanefallGreybox/Private/WanefallModeSimHarness.cpp", "artifacts/br_loop_result.json"],
        "action_transitions": ["Config/WANEFALL_ActionPatterns", "docs/WANEFALL_ACTION_TRANSITION_PATTERN_SPEC.md"],
        "tool_discovery": ["Docs/WANEFALL_TOOL_DISCOVERY_LEDGER.md", "Config/WANEFALL_ToolScoring"],
        "external_references": ["Docs/WANEFALL_EXTERNAL_REFERENCE_LEDGER.md", "artifacts/autonomy/autonomy_capability_matrix.json"],
        "license_dependency_gates": ["dimwit/pipelines/contract_auditor.py", "config/production_pipelines.json"],
        "recursive_orchestration": ["config/director_tasks.json", "codex_handoff.json", "artifacts/autonomy"],
        "proof_integrity": ["ledger/validation.jsonl", "dimwit/pipelines/validation.py"],
        "build_packaging": [
            "dimwit/pipelines/packaged_build_validation.py",
            "artifacts/packaged_build_validation/packaged_build_result.json",
            "artifacts/packaged_build_validation/package_manifest.json",
            "Source/*.Target.cs",
        ],
        "performance": ["artifacts/validation", "Saved/Profiling", "Source/WanefallGreybox"],
    }
    return files[lane]


def _rollback_for_lane(lane: str) -> str:
    return (
        "Revert only the files listed for this candidate, preserve proof artifacts, "
        "then rerun the listed validation command before considering another queue item."
    )


def _row(
    lane: str,
    subsystem: str,
    state: str,
    classification: str,
    evidence: list[str],
    blockers: list[str],
    source_references: list[str],
    next_action: str,
    adoption_mode: str,
    license_risk: str,
    dependency_risk: str,
    version_risk: str,
) -> dict[str, Any]:
    return {
        "capability_id": f"wanefall.{lane}",
        "subsystem": subsystem,
        "required_lane": lane,
        "state": state,
        "classification": classification,
        "evidence": evidence,
        "blockers": blockers,
        "source_references": source_references,
        "next_action": next_action,
        "validation_command": _validation_command_for_lane(lane),
        "rollback": _rollback_for_lane(lane),
        "files_likely_affected": _files_for_lane(lane),
        "adoption_mode": adoption_mode,
        "license_risk": license_risk,
        "dependency_risk": dependency_risk,
        "version_risk": version_risk,
        "promotion_threshold": REVIEW_CEILING,
        "proof_artifact_path": f"artifacts/autonomy/{lane}.json",
    }


def _domain_row(
    lane: str,
    subsystem: str,
    validation_domain: str,
    validation_report: dict[str, Any],
    catalog: list[dict[str, Any]],
    next_action: str,
    adoption_mode: str,
) -> dict[str, Any]:
    counts = _domain_counts(validation_report, validation_domain)
    state = _state_from_counts(counts)
    blockers = _blockers_for_domain(validation_report, validation_domain)
    classification = "PASS" if state == "PASS" else f"{state}_FROM_VALIDATION"
    evidence = [f"artifacts/validation/validation_report.json#{validation_domain}", f"domain_counts={counts}"]
    return _row(
        lane,
        subsystem,
        state,
        classification,
        evidence,
        blockers,
        _reference_names_for_lane(lane, catalog),
        next_action,
        adoption_mode,
        "LOW",
        "LOW",
        "NONE",
    )


def _real_game_row(real_game: dict[str, Any], validation_report: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    checks = real_game.get("checks") if isinstance(real_game.get("checks"), dict) else {}
    blockers = _blockers_for_domain(validation_report, "real_game_runtime")
    for name, check in checks.items():
        if isinstance(check, dict) and check.get("passed") is False:
            issues = check.get("issues") if isinstance(check.get("issues"), list) else []
            blockers.append(f"{name}: {'; '.join(str(issue) for issue in issues)}")
    state = str(real_game.get("state") or _state_from_counts(_domain_counts(validation_report, "real_game_runtime")))
    if state not in SEVERITY_WEIGHT:
        state = _state_from_counts(_domain_counts(validation_report, "real_game_runtime"))
    return _row(
        "runtime_validation",
        "real_game_runtime",
        state,
        "REAL_GAME_REJECTED_PENDING_GAME_REPAIR" if state == "REJECTED" else state,
        ["artifacts/real_game_validation/real_game_validation_result.json", "artifacts/validation/validation_report.json#real_game_runtime"],
        sorted(set(blockers)),
        _reference_names_for_lane("runtime_validation", catalog),
        "Repair real game runtime log errors and replace or justify placeholder/blockout geometry before further expansion.",
        "WANEFALL_NATIVE",
        "LOW",
        "LOW",
        "NONE",
    )


def _metahuman_row(metahuman: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    summary = metahuman.get("summary") if isinstance(metahuman.get("summary"), dict) else {}
    unreal = metahuman.get("unreal") if isinstance(metahuman.get("unreal"), dict) else {}
    version_gate = unreal.get("dna_calibration_version_gate") if isinstance(unreal.get("dna_calibration_version_gate"), dict) else {}
    output_present = bool(summary.get("metahuman_output_present"))
    version_risk = str(version_gate.get("classification") or "NEEDS_REVIEW")
    state = "PASS" if output_present else "BLOCKED"
    blockers = []
    if not output_present:
        blockers.append("No MetaHuman character/identity/DNA-style output evidence is present.")
    if version_risk == "BLOCKED_UNREAL_VERSION":
        blockers.append("UE 5.8 requires MetaHuman for Maya/current Epic lane unless older DNA source is proven.")
    return _row(
        "metahuman_calibration",
        "character_pipeline",
        state,
        str(summary.get("classification") or "BLOCKED_MISSING_METAHUMAN_OUTPUT"),
        ["artifacts/metahuman_utilization/metahuman_utilization_audit.json"],
        blockers,
        _reference_names_for_lane("metahuman_calibration", catalog),
        "Produce real MetaHuman output evidence through the UE 5.8-safe Epic workflow, then rerun the MetaHuman gate.",
        "OFFICIAL_REFERENCE_WITH_VERSION_GATE",
        "EPIC_TOOLING_BOUNDARY",
        "MEDIUM_TOOLCHAIN_ONLY",
        version_risk,
    )


def _packaged_build_row(packaged: dict[str, Any], validation_report: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _domain_counts(validation_report, "packaged_build")
    state = _state_from_counts(counts)
    blockers = _blockers_for_domain(validation_report, "packaged_build")
    package = packaged.get("package") if isinstance(packaged.get("package"), dict) else {}
    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    executable = manifest.get("executable") if isinstance(manifest.get("executable"), dict) else {}
    evidence = [
        "artifacts/validation/validation_report.json#packaged_build",
        "artifacts/packaged_build_validation/packaged_build_result.json",
        "artifacts/packaged_build_validation/package_manifest.json",
        f"domain_counts={counts}",
    ]
    if executable.get("sha256"):
        evidence.append(f"packaged_exe_sha256={executable.get('sha256')}")
    return _row(
        "build_packaging",
        "build_package",
        state,
        "PACKAGED_BUILD_PROOF_PRESENT" if state == "PASS" else f"{state}_FROM_PACKAGED_BUILD_VALIDATION",
        evidence,
        sorted(set(blockers)),
        _reference_names_for_lane("build_packaging", catalog),
        "Keep a fresh UAT package, executable hash manifest, packaged runtime smoke, and packaged log scan before release-style review claims.",
        "WANEFALL_NATIVE",
        "LOW",
        "LOW",
        "UE_TOOLCHAIN_REQUIRED",
    )


def _contract_row(contract: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    summary = contract.get("summary") if isinstance(contract.get("summary"), dict) else {}
    passed = bool(summary.get("passed"))
    issues: list[str] = []
    checks = contract.get("checks") if isinstance(contract.get("checks"), dict) else {}
    for check_name, check in checks.items():
        if isinstance(check, dict) and check.get("passed") is not True:
            found = check.get("issues") if isinstance(check.get("issues"), list) else []
            issues.extend(f"{check_name}: {issue}" for issue in found)
    return _row(
        "license_dependency_gates",
        "orchestration_integrity",
        "PASS" if passed else "BLOCKED",
        "PIPELINE_CONTRACTS_GREEN" if passed else "PIPELINE_CONTRACTS_BLOCKED",
        ["artifacts/pipeline_contracts/pipeline_contract_audit.json"],
        issues,
        _reference_names_for_lane("license_dependency_gates", catalog),
        "Keep pipeline contracts green after any registry, manifest, director task, or source boundary change.",
        "WANEFALL_NATIVE",
        "LOW",
        "LOW",
        "NONE",
    )


def _static_lane_row(
    lane: str,
    subsystem: str,
    catalog: list[dict[str, Any]],
    classification: str,
    next_action: str,
    adoption_mode: str,
    license_risk: str,
    dependency_risk: str,
    version_risk: str,
) -> dict[str, Any]:
    state = "PASS_WITH_NOTES" if classification.startswith("INSTALLED") else "NEEDS_EVIDENCE"
    return _row(
        lane,
        subsystem,
        state,
        classification,
        ["artifacts/autonomy/autonomy_capability_matrix.json"],
        [] if state == "PASS_WITH_NOTES" else [f"{lane} needs repo-native proof artifact and validation hook."],
        _reference_names_for_lane(lane, catalog),
        next_action,
        adoption_mode,
        license_risk,
        dependency_risk,
        version_risk,
    )


def _queue_title(row: dict[str, Any]) -> str:
    titles = {
        "runtime_validation": "Repair real game runtime blockers",
        "proof_integrity": "Repair validation ledger chain integrity",
        "metahuman_calibration": "Produce MetaHuman output proof through version-safe lane",
        "ui_hud": "Finish HUD weakpoint indicator proof",
        "backend_social": "Add thin local backend/social adapter proof",
        "action_transitions": "Add deterministic action and transition pattern proof",
        "tool_discovery": "Add tool discovery scoring ledger proof",
        "recursive_orchestration": "Keep autonomy queue and director in sync",
    }
    lane = str(row["required_lane"])
    return titles.get(lane, f"Improve {lane.replace('_', ' ')} proof")


def _queue_item(row: dict[str, Any], priority_score: int) -> dict[str, Any]:
    lane = str(row["required_lane"])
    refs = row.get("source_references") if isinstance(row.get("source_references"), list) else []
    return {
        "rank": 0,
        "priority_score": priority_score,
        "title": _queue_title(row),
        "affected_subsystem": lane,
        "source_reference": refs[0] if refs else "WANEFALL internal proof artifacts",
        "expected_improvement": row["next_action"],
        "files_likely_affected": list(row.get("files_likely_affected") or []),
        "validation_command": row["validation_command"],
        "failure_risks": list(row.get("blockers") or []),
        "rollback_notes": row["rollback"],
        "promotion_threshold": REVIEW_CEILING,
        "proof_artifact_path": row["proof_artifact_path"],
        "adoption_mode": row["adoption_mode"],
        "dependency_risk": row["dependency_risk"],
        "license_risk": row["license_risk"],
        "version_risk": row["version_risk"],
        "repeat_guard": "Do not retry this candidate if the cited proof artifact is unchanged from the last failed attempt.",
    }


def _rank_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("state"))
        if state == "PASS":
            continue
        lane = str(row["required_lane"])
        score = SEVERITY_WEIGHT.get(state, 45) + LANE_CRITICALITY.get(lane, 0)
        if row.get("version_risk") == "BLOCKED_UNREAL_VERSION":
            score += 5
        candidates.append(_queue_item(row, score))
    candidates.sort(key=lambda item: (-int(item["priority_score"]), str(item["title"])))
    for index, item in enumerate(candidates, start=1):
        item["rank"] = index
    return candidates


def _union_catalog_field(catalog: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for item in catalog:
        current = item.get(key)
        if isinstance(current, list):
            values.extend(str(value) for value in current)
        elif current:
            values.append(str(current))
    return sorted(set(values))


def build_autonomy_capability_matrix(root: Path, project: Path) -> dict[str, Any]:
    # Derive from the latest FULL-scope report, never the mutable per-run report: a domain-scoped
    # run rewriting validation_report.json mid-cycle made every other domain read as zero evidence
    # (the all-NEEDS_EVIDENCE meta-artifacts found by the 2026-07-01 audit).
    from dimwit.state_sync import load_validation_report_with_provenance
    validation_report, report_provenance = load_validation_report_with_provenance(root)
    real_game = _read_json(root / "artifacts" / "real_game_validation" / "real_game_validation_result.json")
    packaged = _read_json(root / "artifacts" / "packaged_build_validation" / "packaged_build_result.json")
    metahuman = _read_json(root / "artifacts" / "metahuman_utilization" / "metahuman_utilization_audit.json")
    contract = _read_json(root / "artifacts" / "pipeline_contracts" / "pipeline_contract_audit.json")
    handoff = _read_json(root / "codex_handoff.json")
    director_tasks = _read_json(root / "config" / "director_tasks.json")
    catalog = external_reference_catalog()

    rows: list[dict[str, Any]] = [
        _real_game_row(real_game, validation_report, catalog),
        _domain_row("movement_traversal", "gameplay_movement", "movement_traversal", validation_report, catalog,
                    "Use proof verbs to validate crouch, sprint, double-tap flip, evasive roll, and traversal feel.", "WANEFALL_NATIVE"),
        _domain_row("animation_feel", "animation", "animation_wiring", validation_report, catalog,
                    "Validate gun/arms/spine animation alignment with runtime pose evidence.", "WANEFALL_NATIVE"),
        _domain_row("weapon_feel", "weapons", "weapons_inplay", validation_report, catalog,
                    "Keep ADS, muzzle, visibility, and in-hand weapon captures green.", "WANEFALL_NATIVE"),
        _domain_row("controller_input", "input", "gameplay_code", validation_report, catalog,
                    "Keep controller-native active gameplay bindings proven and menu-only mouse/keyboard boundaries intact.", "WANEFALL_NATIVE"),
        _domain_row("character_pipeline", "characters", "characters_static_full_nanite", validation_report, catalog,
                    "Preserve source-ready full-detail character assets and add silhouette proof before claiming readability repair.", "WANEFALL_NATIVE"),
        _metahuman_row(metahuman, catalog),
        _domain_row("environment_maps", "maps", "environment_maps", validation_report, catalog,
                    "Replace blockout-looking surfaces with readable WANEFALL geometry while preserving map gates.", "WANEFALL_NATIVE"),
        _domain_row("vfx_audio", "vfx_audio", "vfx_audio", validation_report, catalog,
                    "Keep Niagara/audio assets real, non-stubbed, and tied to gameplay proof.", "WANEFALL_NATIVE"),
        _domain_row("ui_hud", "hud", "ui_hud", validation_report, catalog,
                    "Finish HUD weakpoint indicator evidence without adding settings/UI bloat.", "WANEFALL_NATIVE"),
        _domain_row("br_loop", "large_modes", "br_loop", validation_report, catalog,
                    "Keep BR ring collapse and match resolution proof green.", "WANEFALL_NATIVE"),
        _contract_row(contract, catalog),
        _domain_row("proof_integrity", "proof_ledger", "proof_integrity", validation_report, catalog,
                    "Repair validation ledger chain integrity without deleting legacy evidence.", "WANEFALL_NATIVE"),
        _static_lane_row("backend_social", "backend_social", catalog, "NEEDS_LOCAL_THIN_ADAPTER_PROOF",
                         "Create local/mock backend contracts for profile, friends, parties, chat, matchmaking, leaderboards, and storage.",
                         "THIN_ADAPTER", "LOW_WITH_REVIEW", "MEDIUM_OPTIONAL_SERVICE", "SDK_VERSION_PIN_REQUIRED"),
        _static_lane_row("arcade_mode", "arcade_modes", catalog, "NEEDS_FLOW_SEQUENCE_PROOF",
                         "Add deterministic arcade mode sequence proof without adding a parallel engine.", "REFERENCE_ONLY", "LOW", "LOW", "NONE"),
        _static_lane_row("practice_range", "practice_range", catalog, "NEEDS_MINI_DRILL_SEQUENCE_PROOF",
                         "Add practice-range mini-drill sequencing proof tied to existing combat captures.", "REFERENCE_ONLY", "LOW", "LOW", "NONE"),
        _static_lane_row("action_transitions", "gameflow", catalog, "NEEDS_ACTION_PATTERN_SPEC_AND_VALIDATION",
                         "Add WANEFALL-native action/transition pattern manifests and deterministic validation.", "REFERENCE_ONLY", "LOW", "LOW", "NONE"),
        _static_lane_row("tool_discovery", "tools_assets", catalog, "NEEDS_TOOL_SCORING_LEDGER",
                         "Add tool scoring ledger before any MagicTools-derived adoption can be considered.", "REFERENCE_ONLY", "PER_CANDIDATE_REVIEW_REQUIRED", "LOW_REFERENCE_ONLY", "FRESHNESS_REVIEW_REQUIRED"),
        _static_lane_row("external_references", "references", catalog, "INSTALLED_REFERENCE_CATALOG_PASS_WITH_NOTES",
                         "Keep external references classified before implementation or dependency adoption.", "REFERENCE_ONLY", "LOW_REFERENCE_ONLY", "LOW_REFERENCE_ONLY", "FRESHNESS_REVIEW_REQUIRED"),
        _static_lane_row("recursive_orchestration", "autonomy", catalog, "INSTALLED_AUTONOMY_MATRIX_PASS_WITH_NOTES",
                         "Regenerate this matrix after every validation run and feed ranked candidates back into bounded repair slices.", "WANEFALL_NATIVE", "LOW", "LOW", "NONE"),
        _packaged_build_row(packaged, validation_report, catalog),
        _static_lane_row("performance", "performance", catalog, "NEEDS_RUNTIME_PERF_CAPTURE",
                         "Add runtime performance capture only after real-game errors and blockout geometry are resolved.", "WANEFALL_NATIVE", "LOW", "LOW", "NONE"),
    ]

    queue = _rank_queue(rows)
    engine_version = _engine_version(project)
    metahuman_summary = metahuman.get("summary") if isinstance(metahuman.get("summary"), dict) else {}
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": time.time(),
        "source_validation_report": report_provenance,
        "classification": "PASS_WITH_NOTES",
        "status": "AUTONOMY_MATRIX_GENERATED_REMAINING_GAME_BLOCKERS",
        "ceiling": REVIEW_CEILING,
        "repo_state_before": {
            "validation_suite_verdict": validation_report.get("suite_verdict"),
            "validation_counts": validation_report.get("counts"),
            "handoff_queue_count": len(handoff.get("work_queue") if isinstance(handoff.get("work_queue"), list) else []),
            "director_task_count": len(director_tasks.get("tasks") if isinstance(director_tasks.get("tasks"), list) else []),
        },
        "repo_state_after": {
            "autonomy_matrix_generated": True,
            "capability_count": len(rows),
            "queue_candidate_count": len(queue),
            "top_candidate": queue[0]["title"] if queue else "",
        },
        "unreal_version_detected": engine_version,
        "enabled_project_plugins": _enabled_plugins(project),
        "metahuman_version_status_if_detected": metahuman_summary.get("classification"),
        "required_lanes": list(REQUIRED_LANES),
        "references_studied": [{"source_name": item["source_name"], "source_url": item["source_url"]} for item in catalog],
        "concepts_extracted": _union_catalog_field(catalog, "extracted_concepts"),
        "concepts_rejected": _union_catalog_field(catalog, "rejected_concepts"),
        "license_risks": _union_catalog_field(catalog, "license_risk"),
        "dependency_risks": _union_catalog_field(catalog, "dependency_risk"),
        "version_risks": _union_catalog_field(catalog, "version_risk"),
        "adoption_modes": sorted({str(item["adoption_mode"]) for item in catalog}),
        "external_references": catalog,
        "capability_matrix": rows,
        "recursive_improvement_queue": queue,
        "validation_commands": [
            "python -m dimwit.tests.test_autonomy_capability_matrix",
            "python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue",
            "python scripts/pipeline/run_director.py --validate --no-ue",
            "python scripts/pipeline/run_validation.py --no-ue",
        ],
        "validation_results": {},
        "proof_artifacts": [
            str(MATRIX_PATH),
            str(QUEUE_PATH),
            str(FINAL_REPORT_PATH),
        ],
        "remaining_blockers": [item["title"] for item in queue[:8]],
        "rollback_notes": "Remove the autonomy matrix files and validation registry additions, then rerun scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue.",
        "next_recursive_candidates": queue[:12],
        "pass_fail_reasoning": "The autonomy layer is valid if it ranks real blockers from current evidence, preserves license/version boundaries, and stops at PROMOTED_TO_REVIEW.",
        "files_changed_by_slice": [
            "dimwit/pipelines/autonomy_capability_matrix.py",
            "dimwit/tests/test_autonomy_capability_matrix.py",
            "dimwit/pipelines/validation_registry.py",
            "docs/superpowers/specs/2026-06-28-autonomy-capability-matrix-design.md",
            "docs/superpowers/plans/2026-06-28-autonomy-capability-matrix.md",
            "WanefallGreybox/docs/WANEFALL_EXTERNAL_REFERENCE_LEDGER.md",
            "WanefallGreybox/docs/WANEFALL_AUTONOMOUS_GAME_STUDIO_WORKFLOW.md",
            "WanefallGreybox/Config/WANEFALL_AutonomyQueue/recursive_improvement_queue.json",
        ],
    }
    report["validation_results"] = {
        "source_validation_suite": validation_report.get("suite_verdict"),
        "source_validation_counts": validation_report.get("counts"),
    }
    report["self_validation"] = validate_autonomy_report(report)
    report["validation_results"]["autonomy_self_validation"] = "PASS" if report["self_validation"]["passed"] else "FAIL"
    if report["self_validation"]["passed"] is not True:
        report["classification"] = "FAIL"
        report["status"] = "AUTONOMY_MATRIX_SELF_VALIDATION_FAILED"
    return report


def write_autonomy_capability_matrix(root: Path, project: Path, matrix_path: Path, queue_path: Path, final_report_path: Path) -> dict[str, Any]:
    report = build_autonomy_capability_matrix(root, project)
    _write_json(matrix_path, {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "source_validation_report": report.get("source_validation_report"),
        "required_lanes": report["required_lanes"],
        "capability_matrix": report["capability_matrix"],
        "external_references": report["external_references"],
    })
    _write_json(queue_path, {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "source_validation_report": report.get("source_validation_report"),
        "recursive_improvement_queue": report["recursive_improvement_queue"],
    })
    _write_json(final_report_path, report)
    # Mirror the queue into the WANEFALL Config copy from the SAME writer so the two files can
    # never drift within a run (the game-side copy had been stale since 2026-06-28).
    try:
        from dimwit.state_sync import mirror_queue_to_project
        mirror_queue_to_project(queue_path, project)
    except Exception:
        pass  # parity is enforced fail-closed by the pipeline_contracts queue-sync validator
    return report


def validate_autonomy_report(report: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(report, dict):
        return {"passed": False, "issues": ["autonomy report is not an object"]}
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        issues.append("generated_at missing or not numeric")
    lanes = {
        str(item.get("required_lane"))
        for item in report.get("capability_matrix", [])
        if isinstance(item, dict) and item.get("required_lane")
    }
    missing_lanes = sorted(set(REQUIRED_LANES) - lanes)
    if missing_lanes:
        issues.append(f"missing required lanes: {missing_lanes}")
    references = report.get("external_references") if isinstance(report.get("external_references"), list) else []
    reference_names = {str(item.get("source_name")) for item in references if isinstance(item, dict)}
    for name in ("Embody Unreal Engine Source", "Character DNA Addon", "Epic MetaHuman DNA Calibration", "Claude-Code-Game-Studios", "Nakama", "Cocos2d-x", "MagicTools"):
        if name not in reference_names:
            issues.append(f"external reference missing: {name}")
    for item in references:
        if not isinstance(item, dict):
            issues.append("external reference entry is not an object")
            continue
        for field in ("license_class", "adoption_mode", "license_risk", "dependency_risk", "final_classification"):
            if not item.get(field):
                issues.append(f"{item.get('source_name', 'unknown reference')} missing {field}")
    queue = report.get("recursive_improvement_queue") if isinstance(report.get("recursive_improvement_queue"), list) else []
    if not queue:
        issues.append("recursive improvement queue is empty")
    ranks = [item.get("rank") for item in queue if isinstance(item, dict)]
    if ranks and ranks != list(range(1, len(ranks) + 1)):
        issues.append("queue ranks are not contiguous from 1")
    for item in queue:
        if not isinstance(item, dict):
            issues.append("queue item is not an object")
            continue
        if not item.get("validation_command"):
            issues.append(f"queue item {item.get('title', 'unknown')} missing validation_command")
        if not item.get("rollback_notes"):
            issues.append(f"queue item {item.get('title', 'unknown')} missing rollback_notes")
        if item.get("promotion_threshold") != REVIEW_CEILING:
            issues.append(f"queue item {item.get('title', 'unknown')} has non-review promotion threshold")
    serialized = json.dumps(report)
    for state in OPERATOR_ONLY:
        if state in serialized:
            issues.append(f"operator-only state leaked into autonomy report: {state}")
    return {
        "passed": not issues,
        "issues": issues,
        "required_lane_count": len(REQUIRED_LANES),
        "queue_count": len(queue),
        "reference_count": len(references),
    }
