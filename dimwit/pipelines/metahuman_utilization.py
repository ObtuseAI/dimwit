"""MetaHuman utilization audit for WANEFALL character assets.

This is an offline evidence gate. It does not run Epic tools or claim a
MetaHuman conversion without output artifacts.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
UE_ROOT = Path(r"C:\UE_5.8")
ARTIFACT_DIR = ROOT / "artifacts" / "metahuman_utilization"
RESULT_PATH = ARTIFACT_DIR / "metahuman_utilization_audit.json"
MAX_AUDIT_AGE_SECONDS = 6 * 60 * 60
OUTPUT_ATTEMPT_DIR = ROOT / "artifacts" / "metahuman_output_attempt"
VALID_ATTEMPT_STATES = {"PROMOTED_TO_REVIEW", "State.PROMOTED_TO_REVIEW"}
SOURCE_LINKED_TRANSFORM_OPS = {
    "ConformBodyToTarget",
    "ConformToTargetMeshes",
    "ImportFromTemplate",
    "ImportFromIdentity",
    "ImportFromFaceDna",
    "SetBodyMesh",
    "ExportPosedDNA",
}

EXPECTED_CHARACTERS = [
    {"key": "vorlax", "index": "01", "asset_name": "SM_Char_01_Vorlax", "asset_id": "SM_Char_01_vorlax", "source_stem": "hi3d_01_vorlax"},
    {"key": "ekris", "index": "02", "asset_name": "SM_Char_02_ekris", "asset_id": "SM_Char_02_ekris", "source_stem": "hi3d_02_ekris"},
    {"key": "zythan", "index": "03", "asset_name": "SM_Char_03_zythan", "asset_id": "SM_Char_03_zythan", "source_stem": "hi3d_03_zythan"},
    {"key": "qorin", "index": "04", "asset_name": "SM_Char_04_qorin", "asset_id": "SM_Char_04_qorin", "source_stem": "hi3d_04_qorin"},
    {"key": "therak", "index": "05", "asset_name": "SM_Char_05_therak", "asset_id": "SM_Char_05_therak", "source_stem": "hi3d_05_therak"},
    {"key": "ullio", "index": "06", "asset_name": "SM_Char_06_ullio", "asset_id": "SM_Char_06_ullio", "source_stem": "hi3d_06_ullio"},
    {"key": "kelous", "index": "07", "asset_name": "SM_Char_07_kelous", "asset_id": "SM_Char_07_kelous", "source_stem": "hi3d_07_kelous"},
    {"key": "nexor", "index": "08", "asset_name": "SM_Char_08_nexor", "asset_id": "SM_Char_08_nexor", "source_stem": "hi3d_08_nexor"},
]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _engine_association(project: Path) -> str:
    data = _read_json(project / "WanefallGreybox.uproject")
    value = data.get("EngineAssociation")
    return str(value) if value is not None else ""


def _version_tuple(version: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)(?:\.(\d+))?", version)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return major, minor


def classify_dna_calibration_support(engine_version: str) -> dict[str, Any]:
    parsed = _version_tuple(engine_version)
    if parsed is None:
        return {
            "engine_version": engine_version,
            "classification": "NEEDS_REVIEW",
            "recommended_workflow": "Verify MetaHuman source version before using DNA Calibration",
            "reason": "Unreal Engine version could not be parsed.",
        }
    major, minor = parsed
    if major > 5 or (major == 5 and minor >= 6):
        return {
            "engine_version": engine_version,
            "classification": "BLOCKED_UNREAL_VERSION",
            "recommended_workflow": "MetaHuman for Maya",
            "reason": "UE 5.6+ MetaHumans require the newer MetaHuman for Maya lane unless older DNA source is proven.",
        }
    if major == 5 and minor <= 5:
        return {
            "engine_version": engine_version,
            "classification": "POTENTIALLY_USABLE_INTERNAL_TOOLING",
            "recommended_workflow": "MetaHuman DNA Calibration",
            "reason": "DNA Calibration may be usable for MetaHumans created in UE 5.5 or earlier, subject to license and source proof.",
        }
    return {
        "engine_version": engine_version,
        "classification": "NEEDS_REVIEW",
        "recommended_workflow": "Verify Epic MetaHuman workflow for this engine version",
        "reason": "Version is outside the expected UE5 range.",
    }


def external_reference_decisions() -> list[dict[str, Any]]:
    return [
        {
            "source_name": "Character DNA Addon",
            "source_url": "https://github.com/poly-hammer/character-dna-addon/pulls",
            "license": "GPLv3 unless separately proven otherwise",
            "license_class": "GPL_REFERENCE_ONLY",
            "adoption_mode": "REFERENCE_ONLY",
            "runtime_redistribution": "FORBIDDEN",
            "extracted_concepts": ["DNA pipeline shape", "groom export concepts", "Blender to Unreal iteration checks"],
            "rejected_concepts": ["copying GPL implementation", "bundling addon code"],
        },
        {
            "source_name": "Epic MetaHuman DNA Calibration",
            "source_url": "https://github.com/EpicGames/MetaHuman-DNA-Calibration",
            "license": "Epic MetaHuman DNA Calibration custom license",
            "license_class": "EPIC_CUSTOM_VERSION_GATED",
            "adoption_mode": "OFFICIAL_REFERENCE_WITH_VERSION_GATE",
            "runtime_redistribution": "FORBIDDEN",
            "extracted_concepts": ["DNA inspection", "LOD cleanup", "joint naming checks", "neutral pose validation"],
            "rejected_concepts": ["runtime embedding", "redistributing Epic tooling", "claiming UE 5.6+ support without proof"],
        },
        {
            "source_name": "Epic MetaHuman for Maya",
            "source_url": "https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-for-maya",
            "license": "Epic tools and EULA boundaries",
            "license_class": "EPIC_OFFICIAL_TOOLING",
            "adoption_mode": "OFFICIAL_REFERENCE",
            "runtime_redistribution": "FORBIDDEN",
            "extracted_concepts": ["UE 5.6+ MetaHuman character iteration lane", "Maya calibration workflow"],
            "rejected_concepts": ["requiring tool output before evidence exists"],
        },
    ]


def _enabled_project_plugins(project: Path) -> dict[str, bool]:
    data = _read_json(project / "WanefallGreybox.uproject")
    plugins = data.get("Plugins") if isinstance(data.get("Plugins"), list) else []
    out: dict[str, bool] = {}
    for plugin in plugins:
        if isinstance(plugin, dict) and plugin.get("Name"):
            out[str(plugin["Name"])] = bool(plugin.get("Enabled"))
    return out


def _engine_metahuman_plugins(ue_root: Path) -> dict[str, bool]:
    base = ue_root / "Engine" / "Plugins" / "MetaHuman"
    names = [
        "MetaHumanAnimationTools",
        "MetaHumanAnimator",
        "MetaHumanCalibrationProcessing",
        "MetaHumanCharacter",
        "MetaHumanCoreML",
        "MetaHumanCoreTechLib",
        "MetaHumanCrowd",
        "MetaHumanLiveLink",
        "MetaHumanSDK",
    ]
    return {name: (base / name).exists() for name in names}


def _metahuman_headless_tooling_evidence(ue_root: Path) -> dict[str, Any]:
    character_source = ue_root / "Engine" / "Plugins" / "MetaHuman" / "MetaHumanCharacter" / "Source" / "MetaHumanCharacterEditor"
    export_header = character_source / "Public" / "MetaHumanCharacterExportBlueprintLibrary.h"
    mesh_tool = character_source / "Private" / "Tools" / "MetaHumanCharacterEditorMeshImportTool.cpp"
    export_text = export_header.read_text(encoding="utf-8", errors="ignore") if export_header.exists() else ""
    mesh_tool_text = mesh_tool.read_text(encoding="utf-8", errors="ignore") if mesh_tool.exists() else ""
    maya_candidates = [shutil.which(name) for name in ("maya", "maya.exe", "mayapy", "mayapy.exe")]
    return {
        "metahuman_character_editor_source_present": character_source.exists(),
        "export_posed_dna_blueprint_callable": "ExportPosedDNA" in export_text and "BlueprintCallable" in export_text,
        "export_posed_dna_requires_previous_conform": "ConformToTargetMeshes must have run" in export_text,
        "mesh_import_export_uses_modal_save_dialog": "CreateModalSaveAssetDialog" in mesh_tool_text,
        "maya_or_mayapy_on_path": any(bool(item) for item in maya_candidates),
        "maya_candidates": [item for item in maya_candidates if item],
        "headless_transform_route_proven": False,
        "blocked_reason": (
            "WANEFALL source meshes are ready, but no project MetaHuman/DNA output exists. "
            "Local UE 5.8 tooling exposes export after a conformed target mesh state; no completed conform state, "
            "no project MetaHuman asset, and no maya/mayapy command are available for the recommended MetaHuman for Maya lane."
        ),
    }


def _char_records_by_asset(root: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(root / "artifacts" / "char_fidelity_result.json")
    records = data.get("records") if isinstance(data.get("records"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("asset"):
            out[str(record["asset"]).lower()] = record
    return out


def _first_existing(paths: list[Path]) -> str | None:
    for path in paths:
        if path.exists():
            return str(path)
    return None


def _character_evidence(root: Path, project: Path) -> list[dict[str, Any]]:
    records = _char_records_by_asset(root)
    characters = []
    for item in EXPECTED_CHARACTERS:
        asset_id = str(item["asset_id"])
        source_stem = str(item["source_stem"])
        record = records.get(str(item["asset_name"]).lower()) or records.get(asset_id.lower()) or {}
        source_glb = root / "artifacts" / f"{source_stem}.glb"
        backup_glb = root / "artifacts" / "char_backup" / f"{source_stem}.glb"
        retopo_fbx = root / "artifacts" / "handcraft" / asset_id / f"{asset_id}_retopo.fbx"
        staged_glb = root / "artifacts" / "ue_staging_sym" / f"{item['asset_name']}.glb"
        handcrafted_rig = root / "artifacts" / "rig" / f"{asset_id}_handcrafted_rig.fbx"
        rigged_fbx = root / "artifacts" / "rig" / f"{asset_id}_rigged.fbx"
        imported_uasset = (
            project / "Content" / "Wanefall" / "Dimwit" / "Characters" /
            str(item["asset_name"]) / "StaticMeshes" / f"{item['asset_name']}.uasset"
        )
        evidence = {
            "key": item["key"],
            "asset_name": item["asset_name"],
            "source_glb": _first_existing([source_glb, backup_glb]),
            "char_fidelity_record": bool(record and record.get("ok") and record.get("nanite_enabled")),
            "retopo_fbx": str(retopo_fbx) if retopo_fbx.exists() else None,
            "staged_glb": str(staged_glb) if staged_glb.exists() else None,
            "rig_fbx": _first_existing([rigged_fbx, handcrafted_rig]),
            "imported_uasset": str(imported_uasset) if imported_uasset.exists() else None,
            "provenance": record.get("provenance") if isinstance(record.get("provenance"), dict) else {},
        }
        evidence["source_ready"] = bool(evidence["source_glb"] and evidence["char_fidelity_record"] and evidence["retopo_fbx"])
        characters.append(evidence)
    return characters


def _raw_metahuman_output_candidates(project: Path, root: Path) -> list[str]:
    search_roots = [project / "Content", root / "artifacts"]
    matches: list[str] = []
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for pattern in ("*.dna", "*MetaHuman*.uasset", "*Metahuman*.uasset", "*MH_*.uasset"):
            matches.extend(str(path) for path in search_root.rglob(pattern))
    return [
        path for path in sorted(set(matches))
        if "Engine\\Plugins" not in path and "Intermediate" not in path
    ]


def _is_valid_source_linked_attempt(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    state = str(payload.get("state") or "")
    if state not in VALID_ATTEMPT_STATES:
        issues.append(f"state {state or '<missing>'} is not promotable")
    if payload.get("wanefall_source_linked") is not True:
        issues.append("wanefall_source_linked is not true")
    source_character = str(payload.get("source_character") or payload.get("asset_id") or "").lower()
    if source_character not in {str(item["key"]).lower() for item in EXPECTED_CHARACTERS}:
        issues.append("source_character is not a known WANEFALL character key")
    input_mesh_value = str(payload.get("input_mesh") or "")
    input_mesh = Path(input_mesh_value)
    if not input_mesh_value or not input_mesh.exists():
        issues.append("input_mesh path does not exist")
    operations = payload.get("transform_operations")
    if not isinstance(operations, list) or not (SOURCE_LINKED_TRANSFORM_OPS & {str(item) for item in operations}):
        issues.append("no accepted source-linked MetaHuman transform operation recorded")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        issues.append("outputs list is empty")
    else:
        existing = []
        for output in outputs:
            if not isinstance(output, dict):
                continue
            path = Path(str(output.get("path") or ""))
            if path.exists() and path.suffix.lower() in {".dna", ".uasset", ".json"}:
                existing.append(str(path))
        if not existing:
            issues.append("no existing accepted output file is listed")
    return not issues, issues


def _source_linked_attempt_outputs(root: Path) -> dict[str, Any]:
    attempt_root = root / "artifacts" / "metahuman_output_attempt"
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not attempt_root.exists():
        return {"accepted": accepted, "rejected": rejected}
    for result_path in sorted(attempt_root.rglob("metahuman_output_attempt_result.json")):
        payload = _read_json(result_path)
        ok, issues = _is_valid_source_linked_attempt(payload)
        try:
            from dimwit.pipelines.character_roster import is_quarantined_character
            source_key = str(payload.get("source_character") or payload.get("asset_id") or "")
            if source_key and is_quarantined_character(source_key, root):
                ok = False
                issues.append(f"source_character {source_key} is quarantined and cannot satisfy active MetaHuman output proof")
        except Exception:
            pass
        entry = {
            "result_path": str(result_path),
            "asset_id": payload.get("asset_id"),
            "source_character": payload.get("source_character"),
            "input_mesh": payload.get("input_mesh"),
            "transform_operations": payload.get("transform_operations") if isinstance(payload.get("transform_operations"), list) else [],
            "outputs": payload.get("outputs") if isinstance(payload.get("outputs"), list) else [],
        }
        if ok:
            accepted.append(entry)
        else:
            entry["issues"] = issues
            rejected.append(entry)
    return {"accepted": accepted, "rejected": rejected}


def _metahuman_output_evidence(project: Path, root: Path) -> dict[str, Any]:
    raw_candidates = _raw_metahuman_output_candidates(project, root)
    attempts = _source_linked_attempt_outputs(root)
    accepted_paths: list[str] = []
    for attempt in attempts["accepted"]:
        for output in attempt["outputs"]:
            if isinstance(output, dict) and output.get("path"):
                accepted_paths.append(str(output["path"]))
    filtered = sorted(set(accepted_paths))
    return {
        "present": bool(filtered),
        "paths": filtered[:50],
        "count": len(filtered),
        "source_linked_count": len(attempts["accepted"]),
        "source_linked_attempts": attempts["accepted"],
        "rejected_attempts": attempts["rejected"][:20],
        "raw_candidates_ignored_without_source_linked_attempt": raw_candidates[:50],
        "raw_candidate_count": len(raw_candidates),
    }


def audit_metahuman_utilization(root: Path, project: Path, ue_root: Path) -> dict[str, Any]:
    engine_version = _engine_association(project)
    version_gate = classify_dna_calibration_support(engine_version)
    project_plugins = _enabled_project_plugins(project)
    engine_plugins = _engine_metahuman_plugins(ue_root)
    characters = _character_evidence(root, project)
    outputs = _metahuman_output_evidence(project, root)
    ready_count = sum(1 for item in characters if item["source_ready"])
    if outputs["present"]:
        classification = "READY_FOR_REVIEW_METAHUMAN_OUTPUT_PRESENT"
    elif ready_count == len(EXPECTED_CHARACTERS):
        classification = "PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT"
    else:
        classification = "BLOCKED_MISSING_SOURCE_CHARACTER_ASSET"
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "summary": {
            "classification": classification,
            "expected_character_count": len(EXPECTED_CHARACTERS),
            "source_ready_count": ready_count,
            "metahuman_output_present": outputs["present"],
            "engine_version": engine_version,
        },
        "unreal": {
            "project": str(project),
            "engine_association": engine_version,
            "dna_calibration_version_gate": version_gate,
            "enabled_project_plugins": project_plugins,
            "engine_metahuman_plugins": engine_plugins,
            "headless_tooling_evidence": _metahuman_headless_tooling_evidence(ue_root),
        },
        "characters": characters,
        "metahuman_outputs": outputs,
        "external_references": external_reference_decisions(),
        "boundaries": {
            "no_gpl_code_copied": True,
            "no_epic_tooling_redistributed": True,
            "no_metahuman_conversion_claim_without_output": not outputs["present"],
            "direct_dna_calibration_use": "blocked_for_ue_5_6_plus_without_older_dna_source",
        },
    }


def write_metahuman_utilization_audit(root: Path, project: Path, ue_root: Path, output_path: Path) -> dict[str, Any]:
    report = audit_metahuman_utilization(root, project, ue_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
