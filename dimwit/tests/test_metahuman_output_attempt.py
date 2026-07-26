from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.metahuman_utilization import (
    EXPECTED_CHARACTERS,
    audit_metahuman_utilization,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_metahuman_output_attempt_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fixture_roots() -> tuple[Path, Path, Path]:
    root = TMP / "dimwit"
    project = TMP / "wanefall"
    ue_root = TMP / "UE_5.8"
    root.mkdir(parents=True, exist_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    ue_root.mkdir(parents=True, exist_ok=True)
    _write_json(project / "WanefallGreybox.uproject", {
        "EngineAssociation": "5.8",
        "Plugins": [
            {"Name": "PythonScriptPlugin", "Enabled": True},
            {"Name": "RigLogic", "Enabled": True},
            {"Name": "HairStrands", "Enabled": True},
        ],
    })
    for plugin in ("MetaHumanCharacter", "MetaHumanSDK", "MetaHumanAnimator"):
        (ue_root / "Engine" / "Plugins" / "MetaHuman" / plugin).mkdir(parents=True, exist_ok=True)
    _write_character_fixture(root, project)
    return root, project, ue_root


def _write_character_fixture(root: Path, project: Path) -> None:
    records = []
    for item in EXPECTED_CHARACTERS:
        source_glb = root / "artifacts" / f"{item['source_stem']}.glb"
        source_glb.parent.mkdir(parents=True, exist_ok=True)
        source_glb.write_bytes(b"glb")
        asset_id = item["asset_id"]
        retopo = root / "artifacts" / "handcraft" / asset_id / f"{asset_id}_retopo.fbx"
        retopo.parent.mkdir(parents=True, exist_ok=True)
        retopo.write_bytes(b"fbx")
        imported = (
            project / "Content" / "Wanefall" / "Dimwit" / "Characters" /
            str(item["asset_name"]) / "StaticMeshes" / f"{item['asset_name']}.uasset"
        )
        imported.parent.mkdir(parents=True, exist_ok=True)
        imported.write_bytes(b"uasset")
        records.append({
            "asset": item["asset_name"],
            "ok": True,
            "nanite_enabled": True,
            "provenance": {"source": "fixture", "license": "fixture"},
        })
    _write_json(root / "artifacts" / "char_fidelity_result.json", {"records": records})


def test_raw_mh_named_files_do_not_satisfy_transform_output_evidence():
    root, project, ue_root = _fixture_roots()
    (project / "Content" / "Wanefall" / "Dimwit" / "MetaHumans" / "MH_fake.uasset").parent.mkdir(parents=True, exist_ok=True)
    (project / "Content" / "Wanefall" / "Dimwit" / "MetaHumans" / "MH_fake.uasset").write_bytes(b"not a proven transform")
    (root / "artifacts" / "metahuman_output_attempt" / "ekris" / "ekris_raw.dna").parent.mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "metahuman_output_attempt" / "ekris" / "ekris_raw.dna").write_bytes(b"not a proven transform")

    report = audit_metahuman_utilization(root, project, ue_root)

    assert report["metahuman_outputs"]["present"] is False
    assert report["summary"]["classification"] == "PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT"


def test_source_linked_attempt_result_satisfies_transform_output_evidence():
    root, project, ue_root = _fixture_roots()
    dna = root / "artifacts" / "metahuman_output_attempt" / "ekris" / "MH_ekris_posed.dna"
    dna.parent.mkdir(parents=True, exist_ok=True)
    dna.write_bytes(b"source-linked posed dna")
    result = {
        "state": "PROMOTED_TO_REVIEW",
        "asset_id": "ekris",
        "source_character": "ekris",
        "input_mesh": str(project / "Content" / "Wanefall" / "Dimwit" / "Characters" / "SM_Char_02_ekris" / "StaticMeshes" / "SM_Char_02_ekris.uasset"),
        "wanefall_source_linked": True,
        "transform_operations": ["TryAddObjectToEdit", "GetMeshDataForConforming", "ConformBodyToTarget", "ExportPosedDNA"],
        "outputs": [{"path": str(dna), "kind": "posed_dna"}],
    }
    _write_json(root / "artifacts" / "metahuman_output_attempt" / "ekris" / "metahuman_output_attempt_result.json", result)

    report = audit_metahuman_utilization(root, project, ue_root)

    assert report["metahuman_outputs"]["present"] is True
    assert report["summary"]["classification"] == "READY_FOR_REVIEW_METAHUMAN_OUTPUT_PRESENT"
    assert report["metahuman_outputs"]["source_linked_count"] == 1


def test_pipeline_registered_for_dimwit_and_director_use():
    from dimwit.pipelines import PIPELINES

    assert PIPELINES["metahuman_output_attempt"] == "dimwit.pipelines.metahuman_output_attempt:MetaHumanOutputAttemptPipeline"


def test_pipeline_manifest_and_director_queue_include_attempt_lane():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "config" / "production_pipelines.json").read_text(encoding="utf-8"))
    director = json.loads((root / "config" / "director_tasks.json").read_text(encoding="utf-8"))

    assert manifest["pipelines"]["metahuman_output_attempt"]["status"] == "BUILT"
    assert any(task.get("pipeline") == "metahuman_output_attempt" for task in director["tasks"])


def test_installed_metahuman_sample_topology_inputs_are_discovered():
    from dimwit.pipelines.metahuman_output_attempt import discover_metahuman_topology_inputs

    sample_project = TMP / "MetaHumansSampleProject"
    metahumans = sample_project / "Content" / "MetaHumans"
    for character, body, face in (
        ("Ada", "f_med_nrw_body", "Ada_FaceMesh"),
        ("Taro", "m_med_nrw_body", "Taro_FaceMesh"),
    ):
        body_file = metahumans / character / "Body" / f"{body}.uasset"
        face_file = metahumans / character / "Face" / f"{face}.uasset"
        body_file.parent.mkdir(parents=True, exist_ok=True)
        face_file.parent.mkdir(parents=True, exist_ok=True)
        body_file.write_bytes(b"body")
        face_file.write_bytes(b"face")
        (metahumans / character / f"BP_{character}.uasset").write_bytes(b"bp")
    common_face = metahumans / "Common" / "Face" / "SKM_Face_Preview.uasset"
    common_body = metahumans / "Common" / "Common" / "f_med_nrw_body_preview.uasset"
    common_face.parent.mkdir(parents=True, exist_ok=True)
    common_body.parent.mkdir(parents=True, exist_ok=True)
    common_face.write_bytes(b"common face")
    common_body.write_bytes(b"common body")
    (metahumans / "MHAssetVersions.txt").write_text("fixture", encoding="utf-8")

    candidates = discover_metahuman_topology_inputs(TMP / "WanefallProject", [sample_project])

    ada = next(item for item in candidates if item["name"] == "Ada")
    assert ada["kind"] == "installed_metahuman_character_template"
    assert ada["source_project"] == str(sample_project)
    assert ada["body_mesh_file"].endswith(r"MetaHumans\Ada\Body\f_med_nrw_body.uasset")
    assert ada["face_mesh_file"].endswith(r"MetaHumans\Ada\Face\Ada_FaceMesh.uasset")
    assert ada["source_link_status"] == "template_reference_only"
    assert ada["accepted_output_evidence"] is False
    assert any(item["kind"] == "metahuman_common_template_assets" for item in candidates)


def test_unreal_conforming_tuple_selects_vertices_not_triangle_indices():
    from dimwit.pipelines.metahuman_output_attempt import _direct_body_mesh_topology_ready, _select_conforming_vertices

    vertices = [("v0",), ("v1",), ("v2",)]
    triangle_indices = [0, 1, 2]
    selected, detail = _select_conforming_vertices((vertices, triangle_indices))

    assert selected is vertices
    assert detail["source_vertex_count"] == 3
    assert detail["triangle_index_count"] == 3
    assert _direct_body_mesh_topology_ready(6039745) is False
    assert _direct_body_mesh_topology_ready(30455) is True
    assert _direct_body_mesh_topology_ready(54412) is True


def test_ue_probe_script_preflights_topology_before_set_body_mesh():
    from dimwit.pipelines.metahuman_output_attempt import TOPOLOGY_MISMATCH_BLOCKER, _write_ue_probe_script

    script_path = TMP / "script_preflight" / "metahuman_output_attempt_ue.py"
    _write_ue_probe_script(
        script_path,
        TMP / "script_preflight" / "result.json",
        "ekris",
        "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/StaticMeshes/SM_Char_02_ekris.SM_Char_02_ekris",
        TMP / "wanefall" / "Content" / "source.uasset",
        TMP / "script_preflight",
    )
    script = script_path.read_text(encoding="utf-8")

    assert TOPOLOGY_MISMATCH_BLOCKER in script
    assert "import_from_template" in script
    assert "import_from_template_result" in script
    assert "direct body mesh topology preflight failed" in script
    assert "set_body_result = subsystem.set_body_mesh" in script


def test_ue_probe_script_builds_source_linked_conform_solver_input():
    from dimwit.pipelines.metahuman_output_attempt import CONFORM_SOLVER_BLOCKER, _write_ue_probe_script

    script_path = TMP / "script_conform" / "metahuman_output_attempt_ue.py"
    _write_ue_probe_script(
        script_path,
        TMP / "script_conform" / "result.json",
        "ekris",
        "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/StaticMeshes/SM_Char_02_ekris.SM_Char_02_ekris",
        TMP / "wanefall" / "Content" / "source.uasset",
        TMP / "script_conform",
    )
    script = script_path.read_text(encoding="utf-8")

    assert CONFORM_SOLVER_BLOCKER in script
    assert "SOURCE_LINKED_CONFORM_INPUT_PATH" in script
    assert "unreal.ConformTargetParams()" in script
    assert "unreal.MetaHumanCharacterTargetMeshKey()" in script
    assert "BuildSourceLinkedConformTargetParams" in script
    assert "target_parts_type" in script
    assert "unreal.TargetPartsType.BODY_ONLY" in script
    assert "body_vertex_indices" in script
    assert "conform_to_target_meshes" in script


def test_topology_mismatch_is_classified_as_template_or_solver_blocker():
    from dimwit.pipelines.metahuman_output_attempt import (
        DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS,
        TOPOLOGY_MISMATCH_BLOCKER,
        classify_attempt_blocker,
    )

    classification = classify_attempt_blocker({
        "state": "BLOCKED",
        "wanefall_source_linked": False,
        "transform_operations": ["TryAddObjectToEdit", "GetMeshDataForConforming", "SetBodyMesh"],
        "outputs": [],
        "unreal": {
            "source_vertex_count": 6039745,
            "set_body_mesh": False,
        },
    })

    assert classification["blocker"] == TOPOLOGY_MISMATCH_BLOCKER
    assert classification["source_vertex_count"] == 6039745
    assert classification["expected_vertex_counts"] == list(DIRECT_BODY_MESH_EXPECTED_VERTEX_COUNTS)
    assert classification["next_lane"] == "metahuman_topology_template_or_conform_solver"


def test_conform_solver_rejection_is_distinct_from_missing_template_lane():
    from dimwit.pipelines.metahuman_output_attempt import CONFORM_SOLVER_BLOCKER, classify_attempt_blocker

    classification = classify_attempt_blocker({
        "state": "BLOCKED",
        "wanefall_source_linked": False,
        "transform_operations": [
            "TryAddObjectToEdit",
            "GetMeshDataForConforming",
            "BuildSourceLinkedConformTargetParams",
            "ConformToTargetMeshes",
        ],
        "outputs": [],
        "conform_solver_input": {
            "created": True,
            "source_linked": True,
            "path": str(TMP / "attempt" / "source_linked_conform_solver_input_manifest.json"),
        },
        "unreal": {
            "source_vertex_count": 6039745,
            "triangle_index_count": 6048351,
            "conform_to_target_meshes": False,
        },
    })

    assert classification["blocker"] == CONFORM_SOLVER_BLOCKER
    assert classification["next_lane"] == "metahuman_keypoint_tracking_or_template_retopology"
    assert any("source-linked conform solver input" in item for item in classification["evidence"])


def test_validate_attempt_result_reports_topology_mismatch_blocker():
    from dimwit.pipelines.metahuman_output_attempt import TOPOLOGY_MISMATCH_BLOCKER, validate_attempt_result

    result_path = _write_json(TMP / "attempt_result" / "metahuman_output_attempt_result.json", {
        "state": "BLOCKED",
        "asset_id": "ekris",
        "source_character": "ekris",
        "input_mesh": str(TMP / "wanefall" / "Content" / "Wanefall" / "Dimwit" / "Characters" / "SM_Char_02_ekris" / "StaticMeshes" / "SM_Char_02_ekris.uasset"),
        "wanefall_source_linked": False,
        "transform_operations": ["TryAddObjectToEdit", "GetMeshDataForConforming", "SetBodyMesh"],
        "outputs": [],
        "unreal": {
            "source_vertex_count": 6039745,
            "set_body_mesh": False,
        },
    })

    ok, issues, payload = validate_attempt_result(result_path)

    assert ok is False
    assert payload["blocker"] == TOPOLOGY_MISMATCH_BLOCKER
    assert any(TOPOLOGY_MISMATCH_BLOCKER in issue for issue in issues)


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
