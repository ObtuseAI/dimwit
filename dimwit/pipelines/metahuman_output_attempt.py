"""Executable MetaHuman output attempt lane for WANEFALL.

This pipeline is intentionally conservative: it may create/probe editor assets,
but QA only passes if the result records a WANEFALL source-linked MetaHuman
transform operation and a real output file.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.character_roster import is_quarantined_character
from dimwit.pipelines.metahuman_utilization import (
    EXPECTED_CHARACTERS,
    PROJECT,
    ROOT,
    UE_ROOT,
    _is_valid_source_linked_attempt,
    audit_metahuman_utilization,
)


RESULT_ROOT = ROOT / "artifacts" / "metahuman_output_attempt"
UE_CMD = UE_ROOT / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
UPROJECT = PROJECT / "WanefallGreybox.uproject"
REQUIRED_PROJECT_PLUGINS = ("PythonScriptPlugin", "MetaHumanCharacter")
DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS = (30455, 54412)
TOPOLOGY_MISMATCH_BLOCKER = "BLOCKED_TOPOLOGY_MISMATCH_NEEDS_METAHUMAN_TEMPLATE_OR_CONFORM_SOLVER"
CONFORM_SOLVER_BLOCKER = "BLOCKED_CONFORM_SOLVER_REJECTED_SOURCE_LINKED_INPUT"
MISSING_SOURCE_LINKED_OUTPUT_BLOCKER = "BLOCKED_MISSING_SOURCE_LINKED_METAHUMAN_OUTPUT"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _as_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _direct_body_mesh_topology_ready(vertex_count: Any) -> bool:
    actual = _as_int(vertex_count)
    return actual in DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS


def _content_root_candidates(project: Path, external_roots: Iterable[Path] | None = None) -> list[Path]:
    roots: list[Path] = [
        project / "Content" / "MetaHumans",
        project.parent / "MetaHumans" / "Content" / "MetaHumans",
    ]
    for root in external_roots or []:
        path = Path(root)
        roots.extend([
            path,
            path / "MetaHumans",
            path / "Content" / "MetaHumans",
        ])
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        key = str(resolved).lower()
        if key not in seen and ((resolved / "MHAssetVersions.txt").exists() or (resolved / "Common").exists()):
            seen.add(key)
            out.append(resolved)
    return out


def _source_project_for_content_root(content_root: Path) -> Path:
    if content_root.name == "MetaHumans" and content_root.parent.name == "Content":
        return content_root.parent.parent
    return content_root


def _unreal_asset_path_for_content_file(path: Path, content_root: Path) -> str | None:
    try:
        relative = path.relative_to(content_root.parent)
    except ValueError:
        return None
    without_suffix = relative.with_suffix("")
    package_path = "/" + "/".join(without_suffix.parts)
    return f"{package_path}.{without_suffix.name}"


def _first_match(root: Path, patterns: tuple[str, ...], reject: tuple[str, ...] = ()) -> Path | None:
    if not root.exists():
        return None
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            name = path.name.lower()
            if path.is_file() and not any(item.lower() in name for item in reject):
                return path
    return None


def discover_metahuman_topology_inputs(
    project: Path = PROJECT,
    external_roots: Iterable[Path] | None = None,
) -> list[dict[str, Any]]:
    """Find local MetaHuman sample/template inputs without treating them as outputs."""

    candidates: list[dict[str, Any]] = []
    for content_root in _content_root_candidates(project, external_roots):
        source_project = _source_project_for_content_root(content_root)
        for character_dir in sorted(path for path in content_root.iterdir() if path.is_dir() and path.name != "Common"):
            body = _first_match(character_dir / "Body", ("*_body.uasset", "*Body*.uasset"), reject=("basecolor",))
            face = _first_match(character_dir / "Face", ("*FaceMesh.uasset", "*_Face.uasset", "*Face*.uasset"), reject=("material", "texture"))
            blueprint = _first_match(character_dir, (f"BP_{character_dir.name}.uasset", "BP_*.uasset"))
            if not any((body, face, blueprint)):
                continue
            candidates.append({
                "kind": "installed_metahuman_character_template",
                "name": character_dir.name,
                "source_project": str(source_project),
                "content_root": str(content_root),
                "blueprint_file": str(blueprint) if blueprint else None,
                "body_mesh_file": str(body) if body else None,
                "face_mesh_file": str(face) if face else None,
                "body_asset_path": _unreal_asset_path_for_content_file(body, content_root) if body else None,
                "face_asset_path": _unreal_asset_path_for_content_file(face, content_root) if face else None,
                "usable_in_wanefall_project": source_project.resolve() == project.resolve(),
                "source_link_status": "template_reference_only",
                "accepted_output_evidence": False,
            })
        common_assets = []
        for pattern in (
            "Common/Face/SKM_Face_Preview.uasset",
            "Common/Common/*body_preview.uasset",
            "Common/Common/MetaHuman_ControlRig.uasset",
            "Common/Female/**/metahuman_base_skel.uasset",
        ):
            common_assets.extend(sorted(content_root.glob(pattern)))
        if common_assets:
            candidates.append({
                "kind": "metahuman_common_template_assets",
                "name": "Common",
                "source_project": str(source_project),
                "content_root": str(content_root),
                "asset_files": [str(path) for path in common_assets],
                "asset_paths": [_unreal_asset_path_for_content_file(path, content_root) for path in common_assets],
                "usable_in_wanefall_project": source_project.resolve() == project.resolve(),
                "source_link_status": "template_reference_only",
                "accepted_output_evidence": False,
            })
    return candidates


def classify_attempt_blocker(payload: dict[str, Any]) -> dict[str, Any]:
    unreal = payload.get("unreal") if isinstance(payload.get("unreal"), dict) else {}
    operations = payload.get("transform_operations") if isinstance(payload.get("transform_operations"), list) else []
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), list) else []
    if payload.get("wanefall_source_linked") is True and outputs:
        return {
            "blocker": None,
            "state": "PROMOTED_TO_REVIEW",
            "source_vertex_count": _as_int(unreal.get("source_vertex_count")),
            "expected_vertex_counts": list(DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS),
            "next_lane": None,
            "summary": "Source-linked MetaHuman output is present.",
            "evidence": outputs,
            "recommended_operations": [],
        }
    expected = unreal.get("direct_body_mesh_expected_vertex_counts")
    if not isinstance(expected, list) or not expected:
        expected = list(DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS)
    actual = _as_int(unreal.get("source_vertex_count"))
    set_body_mesh = unreal.get("set_body_mesh")
    conform_input = payload.get("conform_solver_input") if isinstance(payload.get("conform_solver_input"), dict) else {}

    if (
        conform_input.get("created") is True
        and conform_input.get("source_linked") is True
        and "BuildSourceLinkedConformTargetParams" in operations
        and "ConformToTargetMeshes" in operations
        and payload.get("wanefall_source_linked") is not True
    ):
        conform_error = unreal.get("conform_to_target_meshes_exception") or unreal.get("conform_to_target_meshes")
        return {
            "blocker": CONFORM_SOLVER_BLOCKER,
            "state": "BLOCKED",
            "source_vertex_count": actual,
            "expected_vertex_counts": expected,
            "next_lane": "metahuman_keypoint_tracking_or_template_retopology",
            "summary": "Unreal received a WANEFALL source-linked conform solver input, but did not produce a MetaHuman output.",
            "evidence": [
                f"source-linked conform solver input: {conform_input.get('path')}",
                f"ConformToTargetMeshes result: {conform_error}",
            ],
            "recommended_operations": [
                "add face/body keypoint or tracking evidence for the target mesh",
                "generate a MetaHuman-topology retopology/template mesh before conform",
                "try a lower-density source target mesh that preserves WANEFALL provenance",
            ],
        }

    if (
        actual
        and not _direct_body_mesh_topology_ready(actual)
        and (set_body_mesh is False or "SetBodyMesh" not in operations)
        and "GetMeshDataForConforming" in operations
    ):
        return {
            "blocker": TOPOLOGY_MISMATCH_BLOCKER,
            "state": "BLOCKED",
            "source_vertex_count": actual,
            "expected_vertex_counts": expected,
            "next_lane": "metahuman_topology_template_or_conform_solver",
            "summary": (
                f"Direct MetaHuman SetBodyMesh rejected the source mesh topology: "
                f"{actual} vertices, expected one of {expected}."
            ),
            "evidence": [
                "MetaHumanCharacterEditorSubsystem.SetBodyMesh returned false",
                "BodyShapeEditor SetNeutralMesh enforces MetaHuman body topology counts",
            ],
            "recommended_operations": [
                "route through a MetaHuman-topology template mesh",
                "route through the conform solver with target keypoints/tracking evidence",
                "route through a valid MetaHuman DNA/whole-rig import if source DNA exists",
            ],
        }

    return {
        "blocker": MISSING_SOURCE_LINKED_OUTPUT_BLOCKER,
        "state": "BLOCKED",
        "source_vertex_count": actual,
        "expected_vertex_counts": expected,
        "next_lane": "metahuman_source_linked_output_attempt",
        "summary": "No source-linked MetaHuman output exists yet.",
        "evidence": [],
        "recommended_operations": [
            "produce a source-linked MetaHumanCharacter asset, posed DNA, or equivalent project output",
        ],
    }


def _annotate_attempt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    classification = classify_attempt_blocker(payload)
    if classification.get("blocker"):
        payload["blocker"] = classification["blocker"]
        payload["blocker_detail"] = classification
    else:
        payload.pop("blocker", None)
        payload.pop("blocker_detail", None)
    if classification["blocker"] in {TOPOLOGY_MISMATCH_BLOCKER, CONFORM_SOLVER_BLOCKER}:
        unreal = payload.setdefault("unreal", {})
        if isinstance(unreal, dict):
            unreal["direct_body_mesh_expected_vertex_counts"] = classification["expected_vertex_counts"]
        issue = f"{classification['blocker']}: {classification['summary']}"
        issues = payload.setdefault("issues", [])
        if isinstance(issues, list) and issue not in issues:
            issues.append(issue)
    return payload


def _asset_for_id(asset_id: str) -> dict[str, Any] | None:
    wanted = asset_id.lower()
    for item in EXPECTED_CHARACTERS:
        if wanted in {str(item["key"]).lower(), str(item["asset_name"]).lower(), str(item["asset_id"]).lower()}:
            return item
    return None


def _enabled_plugins(project: Path) -> dict[str, bool]:
    data = _read_json(project / "WanefallGreybox.uproject")
    plugins = data.get("Plugins") if isinstance(data.get("Plugins"), list) else []
    out: dict[str, bool] = {}
    for plugin in plugins:
        if isinstance(plugin, dict) and plugin.get("Name"):
            out[str(plugin["Name"])] = bool(plugin.get("Enabled"))
    return out


def _content_path_for_static_mesh(item: dict[str, Any]) -> str:
    asset_name = str(item["asset_name"])
    return f"/Game/Wanefall/Dimwit/Characters/{asset_name}/StaticMeshes/{asset_name}.{asset_name}"


def _project_file_for_static_mesh(project: Path, item: dict[str, Any]) -> Path:
    asset_name = str(item["asset_name"])
    return project / "Content" / "Wanefall" / "Dimwit" / "Characters" / asset_name / "StaticMeshes" / f"{asset_name}.uasset"


def _select_conforming_vertices(mesh_data: Any) -> tuple[Any | None, dict[str, Any]]:
    detail: dict[str, Any] = {"mesh_data_type": str(type(mesh_data))}
    if isinstance(mesh_data, tuple):
        detail["mesh_data_tuple_len"] = len(mesh_data)
        if len(mesh_data) >= 3 and isinstance(mesh_data[0], bool):
            detail["mesh_data_success"] = bool(mesh_data[0])
            vertices = mesh_data[1]
            triangles = mesh_data[2]
        elif len(mesh_data) >= 2:
            detail["mesh_data_success"] = True
            vertices = mesh_data[0]
            triangles = mesh_data[1]
        else:
            detail["mesh_data_success"] = False
            return None, detail
        try:
            detail["source_vertex_count"] = len(vertices)
        except Exception:
            pass
        try:
            detail["triangle_index_count"] = len(triangles)
        except Exception:
            pass
        return vertices, detail
    detail["mesh_data_success"] = bool(mesh_data)
    return None, detail


def _write_ue_probe_script(path: Path, result_path: Path, asset_id: str, source_mesh_path: str, input_mesh_file: Path, output_dir: Path) -> None:
    script = f'''from __future__ import annotations

import json
import os
import time
import traceback

import unreal


RESULT_PATH = r"{result_path}"
ASSET_ID = {asset_id!r}
SOURCE_MESH_PATH = {source_mesh_path!r}
INPUT_MESH_FILE = r"{input_mesh_file}"
OUTPUT_DIR = r"{output_dir}"
SOURCE_LINKED_CONFORM_INPUT_PATH = os.path.join(OUTPUT_DIR, "source_linked_conform_solver_input_manifest.json")
DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS = {list(DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS)!r}
TOPOLOGY_MISMATCH_BLOCKER = {TOPOLOGY_MISMATCH_BLOCKER!r}
CONFORM_SOLVER_BLOCKER = {CONFORM_SOLVER_BLOCKER!r}


def _write(payload):
    os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_json_path(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _select_conforming_mesh_data(mesh_data):
    detail = {{"mesh_data_type": str(type(mesh_data))}}
    if isinstance(mesh_data, tuple):
        detail["mesh_data_tuple_len"] = len(mesh_data)
        if len(mesh_data) >= 3 and isinstance(mesh_data[0], bool):
            detail["mesh_data_success"] = bool(mesh_data[0])
            vertices = mesh_data[1]
            triangles = mesh_data[2]
        elif len(mesh_data) >= 2:
            detail["mesh_data_success"] = True
            vertices = mesh_data[0]
            triangles = mesh_data[1]
        else:
            detail["mesh_data_success"] = False
            return None, detail
        try:
            detail["source_vertex_count"] = len(vertices)
        except Exception:
            pass
        try:
            detail["triangle_index_count"] = len(triangles)
        except Exception:
            pass
        return vertices, triangles, detail
    detail["mesh_data_success"] = bool(mesh_data)
    return None, None, detail


result = {{
    "schema_version": 1,
    "generated_at": time.time(),
    "state": "BLOCKED",
    "asset_id": ASSET_ID,
    "source_character": ASSET_ID,
    "input_mesh": INPUT_MESH_FILE,
    "source_mesh_asset": SOURCE_MESH_PATH,
    "wanefall_source_linked": False,
    "transform_operations": [],
    "outputs": [],
    "issues": [],
    "unreal": {{}},
}}

try:
    result["unreal"]["python_api_available"] = True
    result["unreal"]["has_metahuman_character"] = hasattr(unreal, "MetaHumanCharacter")
    result["unreal"]["has_metahuman_factory"] = hasattr(unreal, "MetaHumanCharacterFactoryNew")
    result["unreal"]["has_metahuman_editor_subsystem"] = hasattr(unreal, "MetaHumanCharacterEditorSubsystem")
    result["unreal"]["has_export_library"] = hasattr(unreal, "MetaHumanCharacterExportBlueprintLibrary")
    source_mesh = unreal.load_asset(SOURCE_MESH_PATH)
    result["unreal"]["source_mesh_loaded"] = bool(source_mesh)
    if not source_mesh:
        result["issues"].append("source mesh could not be loaded")
        _write(result)
        raise SystemExit(0)
    if not (hasattr(unreal, "MetaHumanCharacter") and hasattr(unreal, "MetaHumanCharacterFactoryNew")):
        result["issues"].append("MetaHumanCharacter Python classes are unavailable; MetaHumanCharacter plugin is not loaded")
        _write(result)
        raise SystemExit(0)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    package_path = "/Game/Wanefall/Dimwit/MetaHumanAttempts"
    asset_name = "MH_WANEFALL_" + ASSET_ID + "_Attempt"
    character_path = package_path + "/" + asset_name + "." + asset_name
    character = unreal.load_asset(character_path)
    if not character:
        factory = unreal.MetaHumanCharacterFactoryNew()
        character = asset_tools.create_asset(asset_name, package_path, unreal.MetaHumanCharacter, factory)
        result["transform_operations"].append("CreateMetaHumanCharacterAsset")
    else:
        result["transform_operations"].append("LoadExistingMetaHumanCharacterAsset")
    result["unreal"]["metahuman_character_asset"] = character_path
    if not character:
        result["issues"].append("failed to create/load MetaHumanCharacter asset")
        _write(result)
        raise SystemExit(0)

    subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem) if hasattr(unreal, "MetaHumanCharacterEditorSubsystem") else None
    result["unreal"]["editor_subsystem_loaded"] = bool(subsystem)
    if not subsystem:
        result["issues"].append("MetaHumanCharacterEditorSubsystem unavailable")
        unreal.EditorAssetLibrary.save_loaded_asset(character)
        _write(result)
        raise SystemExit(0)

    added = bool(subsystem.try_add_object_to_edit(character))
    result["transform_operations"].append("TryAddObjectToEdit")
    result["unreal"]["try_add_object_to_edit"] = added
    if not added:
        result["issues"].append("MetaHuman character could not be registered for editing")

    source_linked_transform = False
    result["unreal"]["has_import_from_template_params"] = hasattr(unreal, "ImportFromTemplateParams")
    result["unreal"]["has_import_from_template_method"] = hasattr(subsystem, "import_from_template")
    if result["unreal"]["has_import_from_template_params"] and result["unreal"]["has_import_from_template_method"]:
        try:
            import_params = unreal.ImportFromTemplateParams()
            if hasattr(import_params, "b_match_vertices_by_uvs"):
                import_params.b_match_vertices_by_uvs = True
            if hasattr(import_params, "b_use_eye_meshes"):
                import_params.b_use_eye_meshes = False
            if hasattr(import_params, "b_use_teeth_mesh"):
                import_params.b_use_teeth_mesh = False
            template_result = subsystem.import_from_template(character, source_mesh, None, None, None, import_params)
            result["transform_operations"].append("ImportFromTemplate")
            result["unreal"]["import_from_template_result"] = str(template_result)
            template_result_text = str(template_result).lower()
            template_success = template_result_text.endswith("success") or template_result_text == "0"
            result["unreal"]["import_from_template_success"] = template_success
            if template_success:
                source_linked_transform = True
                result["unreal"]["source_linked_operation"] = "ImportFromTemplate"
        except Exception as exc:
            result["transform_operations"].append("ImportFromTemplate")
            result["unreal"]["import_from_template_exception"] = repr(exc)
            result["issues"].append("ImportFromTemplate failed: " + repr(exc))
    else:
        result["issues"].append("ImportFromTemplate Python API route is unavailable")

    source_vertices = None
    source_vertex_indices = None
    try:
        mesh_data = unreal.MetaHumanCharacterEditorSubsystem.get_mesh_data_for_conforming(source_mesh)
        result["transform_operations"].append("GetMeshDataForConforming")
        source_vertices, source_vertex_indices, mesh_detail = _select_conforming_mesh_data(mesh_data)
        result["unreal"].update(mesh_detail)
    except Exception as exc:
        result["issues"].append("GetMeshDataForConforming failed: " + repr(exc))

    if source_vertices and not source_linked_transform:
        source_vertex_count = result["unreal"].get("source_vertex_count")
        triangle_index_count = result["unreal"].get("triangle_index_count")
        result["unreal"]["has_conform_target_params"] = hasattr(unreal, "ConformTargetParams")
        result["unreal"]["has_conform_target_mesh"] = hasattr(unreal, "ConformTargetMesh")
        result["unreal"]["has_target_mesh_key"] = hasattr(unreal, "MetaHumanCharacterTargetMeshKey")
        result["unreal"]["has_conform_to_target_meshes"] = hasattr(subsystem, "conform_to_target_meshes")
        if (
            source_vertex_indices
            and result["unreal"]["has_conform_target_params"]
            and result["unreal"]["has_conform_target_mesh"]
            and result["unreal"]["has_target_mesh_key"]
            and result["unreal"]["has_conform_to_target_meshes"]
        ):
            conform_manifest = {{
                "created": True,
                "source_linked": True,
                "path": SOURCE_LINKED_CONFORM_INPUT_PATH,
                "asset_id": ASSET_ID,
                "source_character": ASSET_ID,
                "source_mesh_asset": SOURCE_MESH_PATH,
                "input_mesh": INPUT_MESH_FILE,
                "target_parts_type": "BODY_ONLY",
                "body_vertex_count": source_vertex_count,
                "body_vertex_index_count": triangle_index_count,
                "operation": "ConformToTargetMeshes",
                "solver_settings": {{
                    "iterations": 1,
                    "face_iterations": 0,
                    "pipeline_name": "body_only",
                    "auto_solve": False,
                    "estimate_body_joints_from_mesh": False,
                }},
                "notes": [
                    "The full vertex/index arrays were passed in memory to Unreal ConformTargetParams.",
                    "The manifest stores counts and provenance only to avoid multi-million-entry JSON artifacts.",
                ],
            }}
            _write_json_path(SOURCE_LINKED_CONFORM_INPUT_PATH, conform_manifest)
            result["conform_solver_input"] = conform_manifest
            result["transform_operations"].append("BuildSourceLinkedConformTargetParams")
            try:
                target_key = unreal.MetaHumanCharacterTargetMeshKey()
                target_key.set_editor_property("body_mesh", source_mesh)
                conform_target_mesh = unreal.ConformTargetMesh()
                conform_target_mesh.set_editor_property("target_parts_type", unreal.TargetPartsType.BODY_ONLY)
                conform_target_mesh.set_editor_property("body_vertices", source_vertices)
                conform_target_mesh.set_editor_property("body_vertex_indices", source_vertex_indices)
                target_params = unreal.ConformTargetParams()
                target_params.set_editor_property("conform_target_mesh", conform_target_mesh)
                target_params.set_editor_property("auto_solve", False)
                target_params.set_editor_property("estimate_body_joints_from_mesh", False)
                body_settings = target_params.get_editor_property("body_conform_solve_settings")
                body_settings.set_editor_property("iterations", 1)
                body_settings.set_editor_property("face_iterations", 0)
                body_settings.set_editor_property("pipeline_name", "body_only")
                target_params.set_editor_property("body_conform_solve_settings", body_settings)
                result["transform_operations"].append("ConformToTargetMeshes")
                conform_result = subsystem.conform_to_target_meshes(character, target_key, target_params)
                result["unreal"]["conform_to_target_meshes"] = bool(conform_result)
                source_linked_transform = bool(conform_result)
                if source_linked_transform:
                    result["unreal"]["source_linked_operation"] = "ConformToTargetMeshes"
            except Exception as exc:
                if "ConformToTargetMeshes" not in result["transform_operations"]:
                    result["transform_operations"].append("ConformToTargetMeshes")
                result["unreal"]["conform_to_target_meshes_exception"] = repr(exc)
                result["blocker"] = CONFORM_SOLVER_BLOCKER
                result["issues"].append("ConformToTargetMeshes failed: " + repr(exc))
        else:
            result["issues"].append("ConformToTargetMeshes Python API route is unavailable or source indices are missing")

    if source_vertices and not source_linked_transform:
        source_vertex_count = result["unreal"].get("source_vertex_count")
        result["unreal"]["direct_body_mesh_expected_vertex_counts"] = DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS
        if source_vertex_count not in DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS:
            result["blocker"] = TOPOLOGY_MISMATCH_BLOCKER
            result["issues"].append(
                "direct body mesh topology preflight failed: "
                + str(source_vertex_count)
                + " vertices, expected one of "
                + str(DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS)
            )
        else:
            try:
                set_body_result = subsystem.set_body_mesh(character, source_vertices, True)
                result["transform_operations"].append("SetBodyMesh")
                result["unreal"]["set_body_mesh"] = bool(set_body_result)
                source_linked_transform = bool(set_body_result)
            except Exception as exc:
                result["issues"].append("SetBodyMesh failed: " + repr(exc))

    if source_linked_transform:
        result["wanefall_source_linked"] = True
        try:
            unreal.EditorAssetLibrary.save_loaded_asset(character)
            result["outputs"].append({{"path": unreal.SystemLibrary.get_project_content_directory().replace("/", "\\\\") + "Wanefall\\\\Dimwit\\\\MetaHumanAttempts\\\\" + asset_name + ".uasset", "kind": "metahuman_character_asset"}})
        except Exception as exc:
            result["issues"].append("saving source-linked MetaHuman asset failed: " + repr(exc))

    existing_outputs = []
    for output in result["outputs"]:
        if isinstance(output, dict) and os.path.exists(str(output.get("path", ""))):
            existing_outputs.append(output)
    result["outputs"] = existing_outputs
    if source_linked_transform and existing_outputs:
        result["state"] = "PROMOTED_TO_REVIEW"
        result["score"] = 1.0
    else:
        result["score"] = 0.25 if character else 0.0
        if not result["issues"]:
            result["issues"].append("no source-linked MetaHuman transform output was produced")
    _write(result)
except Exception:
    result["state"] = "BLOCKED"
    result["score"] = 0.0
    result["issues"].append("unhandled exception")
    result["traceback"] = traceback.format_exc()
    _write(result)
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")


def validate_attempt_result(result_path: Path) -> tuple[bool, list[str], dict[str, Any]]:
    payload = _read_json(result_path)
    if not payload:
        return False, ["attempt result is missing or invalid JSON"], {}
    payload = _annotate_attempt_payload(payload)
    ok, issues = _is_valid_source_linked_attempt(payload)
    if not ok and payload.get("blocker"):
        classification = payload.get("blocker_detail") if isinstance(payload.get("blocker_detail"), dict) else {}
        issue = f"{payload['blocker']}: {classification.get('summary', 'attempt did not produce source-linked output')}"
        if issue not in issues:
            issues = [issue] + issues
    return ok, issues, payload


class MetaHumanOutputAttemptPipeline(ProductionPipeline):
    name = "metahuman_output_attempt"
    kind = "metahuman_source_linked_output_attempt"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "zythan").lower()
        item = _asset_for_id(asset_id)
        if item is None:
            raise BlockedError(f"unknown WANEFALL character asset_id '{asset_id}'")
        if is_quarantined_character(item["key"]) or is_quarantined_character(item["asset_name"]):
            raise BlockedError(f"quarantined character '{asset_id}' is failure-fixture only")
        audit = audit_metahuman_utilization(ROOT, PROJECT, UE_ROOT)
        character = next((entry for entry in audit["characters"] if entry["key"] == item["key"]), None)
        if not character or not character.get("source_ready"):
            raise BlockedError(f"{asset_id} source mesh evidence is not ready")
        input_mesh_file = _project_file_for_static_mesh(PROJECT, item)
        if not input_mesh_file.exists():
            raise BlockedError(f"imported source mesh uasset is missing: {input_mesh_file}")
        if not UE_CMD.exists() or not UPROJECT.exists():
            raise BlockedError("UnrealEditor-Cmd.exe or WanefallGreybox.uproject is missing")
        output_dir = RESULT_ROOT / str(item["key"])
        source_mesh_path = _content_path_for_static_mesh(item)
        script_path = output_dir / "metahuman_output_attempt_ue.py"
        result_path = output_dir / "metahuman_output_attempt_result.json"
        extra_roots = task.get("metahuman_project_roots") or task.get("external_metahuman_roots") or []
        if isinstance(extra_roots, (str, Path)):
            extra_roots = [Path(extra_roots)]
        elif isinstance(extra_roots, list):
            extra_roots = [Path(str(root)) for root in extra_roots]
        else:
            extra_roots = []
        metahuman_topology_inputs = discover_metahuman_topology_inputs(PROJECT, extra_roots)
        enabled_plugins = _enabled_plugins(PROJECT)
        missing_plugins = [name for name in REQUIRED_PROJECT_PLUGINS if not enabled_plugins.get(name)]
        return {
            "asset_id": str(item["key"]),
            "asset_name": item["asset_name"],
            "source_mesh_path": source_mesh_path,
            "input_mesh_file": str(input_mesh_file),
            "output_dir": str(output_dir),
            "script_path": str(script_path),
            "result_path": str(result_path),
            "ue_cmd": str(UE_CMD),
            "uproject": str(UPROJECT),
            "enabled_plugins": enabled_plugins,
            "missing_plugins": missing_plugins,
            "metahuman_topology_inputs": metahuman_topology_inputs,
            "run_unreal": bool(task.get("run_unreal", True)),
            "timeout_seconds": int(task.get("timeout_seconds", 420)),
            "audit_classification_before": audit["summary"]["classification"],
        }

    def execute(self, plan: dict) -> Artifact:
        output_dir = Path(plan["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = Path(plan["result_path"])
        script_path = Path(plan["script_path"])
        _write_ue_probe_script(
            script_path,
            result_path,
            str(plan["asset_id"]),
            str(plan["source_mesh_path"]),
            Path(plan["input_mesh_file"]),
            output_dir,
        )
        topology_inputs_path = output_dir / "metahuman_topology_inputs.json"
        topology_inputs_path.write_text(
            json.dumps({
                "schema_version": 1,
                "generated_at": time.time(),
                "asset_id": plan["asset_id"],
                "accepted_output_evidence": False,
                "inputs": plan.get("metahuman_topology_inputs", []),
            }, indent=2),
            encoding="utf-8",
        )
        subprocess_info: dict[str, Any] = {"skipped": not plan.get("run_unreal")}
        if plan.get("run_unreal"):
            cmd = [
                str(plan["ue_cmd"]),
                str(plan["uproject"]),
                f"-ExecutePythonScript={script_path}",
                "-unattended",
                "-nosplash",
                "-nopause",
                "-stdout",
                "-FullStdOutLogOutput",
            ]
            started = time.time()
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=int(plan["timeout_seconds"]),
                )
                subprocess_info = {
                    "command": cmd,
                    "returncode": completed.returncode,
                    "elapsed_seconds": round(time.time() - started, 3),
                    "stdout_tail": completed.stdout.splitlines()[-80:],
                    "stderr_tail": completed.stderr.splitlines()[-80:],
                }
                (output_dir / "ue_stdout.log").write_text(completed.stdout, encoding="utf-8", errors="ignore")
                (output_dir / "ue_stderr.log").write_text(completed.stderr, encoding="utf-8", errors="ignore")
            except subprocess.TimeoutExpired as exc:
                subprocess_info = {
                    "command": cmd,
                    "timeout_seconds": int(plan["timeout_seconds"]),
                    "elapsed_seconds": round(time.time() - started, 3),
                    "error": f"timeout: {exc}",
                }
        if not result_path.exists():
            payload = {
                "schema_version": 1,
                "generated_at": time.time(),
                "state": "BLOCKED",
                "asset_id": plan["asset_id"],
                "source_character": plan["asset_id"],
                "input_mesh": plan["input_mesh_file"],
                "source_mesh_asset": plan["source_mesh_path"],
                "wanefall_source_linked": False,
                "transform_operations": [],
                "outputs": [],
                "issues": ["UE probe did not write metahuman_output_attempt_result.json"],
                "subprocess": subprocess_info,
                "metahuman_topology_inputs": plan.get("metahuman_topology_inputs", []),
                "metahuman_topology_inputs_path": str(topology_inputs_path),
            }
            payload = _annotate_attempt_payload(payload)
            result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            payload = _read_json(result_path)
            payload["subprocess"] = subprocess_info
            payload["metahuman_topology_inputs"] = plan.get("metahuman_topology_inputs", [])
            payload["metahuman_topology_inputs_path"] = str(topology_inputs_path)
            payload = _annotate_attempt_payload(payload)
            result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return Artifact(
            asset_id=str(plan["asset_id"]),
            kind=self.kind,
            data={
                "result_path": str(result_path),
                "script_path": str(script_path),
                "output_dir": str(output_dir),
                "metahuman_topology_inputs_path": str(topology_inputs_path),
                "missing_plugins": plan.get("missing_plugins", []),
            },
            provenance={
                "source": str(plan["input_mesh_file"]),
                "license": "Hi3D Essential plan / WANEFALL generated character provenance, inherited from source audit",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result_path = Path(artifact.data["result_path"])
        ok, issues, payload = validate_attempt_result(result_path)
        evidence = [str(result_path), str(artifact.data["script_path"])]
        if ok:
            return Verdict(score=1.0, passed=True, issues=[], detail=payload, evidence=evidence)
        score = float(payload.get("score") or 0.0) if payload else 0.0
        if plan.get("missing_plugins"):
            issues = [f"project plugins not enabled: {', '.join(plan['missing_plugins'])}"] + issues
        return Verdict(score=score, passed=False, issues=issues, detail=payload, evidence=evidence)

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact
