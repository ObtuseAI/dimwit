from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.character_source_sync import (
    audit_character_source_sync,
    evaluate_blender_anatomy_review,
)
from dimwit.pipelines.metahuman_utilization import EXPECTED_CHARACTERS


TMP = Path(tempfile.mkdtemp(prefix="dimwit_character_source_sync_"))


def _review(
    *,
    components: int = 1,
    largest: float = 1.0,
    mesh_scale: list[float] | None = None,
    armature_scale: list[float] | None = None,
    armatures: int = 0,
) -> dict:
    mesh_scale = mesh_scale or [1.0, 1.0, 1.0]
    objects = [{"name": "LOW", "scale": mesh_scale, "verts": 1000, "faces": 900, "parent": None}]
    armature_rows = []
    for idx in range(armatures):
        armature_rows.append({
            "name": f"root{idx}",
            "bones": 141,
            "scale": armature_scale or [1.0, 1.0, 1.0],
            "parent": None,
        })
    return {
        "ok": True,
        "label": "fixture",
        "object_metrics": {
            "mesh_count": 1,
            "armature_count": armatures,
            "vertex_count": 1000,
            "face_count": 900,
            "objects": objects,
            "armatures": armature_rows,
        },
        "anatomy_metrics": {
            "dimensions": [0.7, 0.35, 1.9],
            "up_axis": "z",
            "best_body_symmetry_axis": "x",
            "mirror_mismatch_pct_by_axis": {"x": 0.2, "y": 2.0, "z": 3.0},
            "mirror_mismatch_pct_by_region": {
                "legs": {"samples": 100, "mirror_mismatch_pct": 0.1},
                "torso_arms": {"samples": 200, "mirror_mismatch_pct": 0.2},
                "head_face": {"samples": 80, "mirror_mismatch_pct": 0.1},
            },
        },
        "component_metrics": {
            "measured": True,
            "total_faces": 900,
            "component_count": components,
            "largest_component_face_fraction": largest,
            "small_component_count": max(0, components - 1),
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_fragmented_blender_character_review_fails_even_when_symmetric():
    verdict = evaluate_blender_anatomy_review(_review(components=40, largest=0.05), stage="source")

    assert verdict["passed"] is False, verdict
    assert any("fragmented" in issue for issue in verdict["issues"]), verdict


def test_dirty_rig_transform_review_fails_before_unreal_import():
    verdict = evaluate_blender_anatomy_review(
        _review(components=1, largest=1.0, mesh_scale=[100.0, 100.0, 100.0], armature_scale=[0.01, 0.01, 0.01], armatures=1),
        stage="rig",
    )

    assert verdict["passed"] is False, verdict
    assert any("dirty rig transform" in issue for issue in verdict["issues"]), verdict


def test_hi3d_source_without_blender_review_is_not_sync_ready():
    root = TMP / "missing_review_root"
    project = TMP / "missing_review_project"
    item = EXPECTED_CHARACTERS[1]
    source = root / "artifacts" / f"{item['source_stem']}.glb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"glb")

    report = audit_character_source_sync(root, project, characters=[item])

    char = report["characters"][0]
    assert char["sync_ready"] is False, char
    assert char["stages"]["hi3d_source"]["state"] == "PASS", char
    assert char["stages"]["blender_source_review"]["state"] == "BLOCKED", char
    assert "character_anatomy_review.py" in char["next_action"]["command"], char["next_action"]


def test_full_clean_chain_marks_character_sync_ready_for_review():
    root = TMP / "clean_root"
    project = TMP / "clean_project"
    item = EXPECTED_CHARACTERS[1]
    art = root / "artifacts"
    source = art / f"{item['source_stem']}.glb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"glb")
    token = item["asset_id"]
    retopo = art / "handcraft" / token / f"{token}_retopo.fbx"
    retopo.parent.mkdir(parents=True, exist_ok=True)
    retopo.write_bytes(b"fbx")
    rig = art / "rig" / f"{token}_handcrafted_rig.fbx"
    rig.parent.mkdir(parents=True, exist_ok=True)
    rig.write_bytes(b"fbx")
    imported = project / "Content" / "Wanefall" / "Dimwit" / "Characters" / item["asset_name"] / "StaticMeshes" / f"{item['asset_name']}.uasset"
    imported.parent.mkdir(parents=True, exist_ok=True)
    imported.write_bytes(b"uasset")
    dna = art / "metahuman_output_attempt" / item["key"] / f"MH_{item['key']}_posed.dna"
    dna.parent.mkdir(parents=True, exist_ok=True)
    dna.write_bytes(b"dna")
    _write_json(dna.parent / "metahuman_output_attempt_result.json", {
        "state": "PROMOTED_TO_REVIEW",
        "asset_id": item["key"],
        "source_character": item["key"],
        "input_mesh": str(imported),
        "wanefall_source_linked": True,
        "transform_operations": ["ConformToTargetMeshes", "ExportPosedDNA"],
        "outputs": [{"path": str(dna), "kind": "posed_dna"}],
    })
    _write_json(art / "blender_anatomy_review" / f"{item['source_stem']}_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_retopo_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_handcrafted_rig_review.json", _review(armatures=1))
    _write_json(art / "char_fidelity_result.json", {
        "records": [{
            "asset": item["asset_name"],
            "ok": True,
            "nanite_enabled": True,
            "provenance": {"source": "Hi3D fixture", "license": "Hi3D Essential plan"},
        }]
    })

    report = audit_character_source_sync(root, project, characters=[item])

    char = report["characters"][0]
    assert char["sync_ready"] is True, char
    assert report["summary"]["sync_ready_count"] == 1, report


def test_active_runtime_deformation_defect_blocks_sync_ready():
    root = TMP / "active_defect_root"
    project = TMP / "active_defect_project"
    item = EXPECTED_CHARACTERS[1]
    art = root / "artifacts"
    source = art / f"{item['source_stem']}.glb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"glb")
    token = item["asset_id"]
    retopo = art / "handcraft" / token / f"{token}_retopo.fbx"
    retopo.parent.mkdir(parents=True, exist_ok=True)
    retopo.write_bytes(b"fbx")
    rig = art / "rig" / f"{token}_handcrafted_rig.fbx"
    rig.parent.mkdir(parents=True, exist_ok=True)
    rig.write_bytes(b"fbx")
    imported = project / "Content" / "Wanefall" / "Dimwit" / "Characters" / item["asset_name"] / "StaticMeshes" / f"{item['asset_name']}.uasset"
    imported.parent.mkdir(parents=True, exist_ok=True)
    imported.write_bytes(b"uasset")
    dna = art / "metahuman_output_attempt" / item["key"] / f"MH_{item['key']}_posed.dna"
    dna.parent.mkdir(parents=True, exist_ok=True)
    dna.write_bytes(b"dna")
    _write_json(dna.parent / "metahuman_output_attempt_result.json", {
        "state": "PROMOTED_TO_REVIEW",
        "asset_id": item["key"],
        "source_character": item["key"],
        "input_mesh": str(imported),
        "wanefall_source_linked": True,
        "transform_operations": ["ConformToTargetMeshes"],
        "outputs": [{"path": str(dna), "kind": "posed_dna"}],
    })
    _write_json(art / "blender_anatomy_review" / f"{item['source_stem']}_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_retopo_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_handcrafted_rig_review.json", _review(armatures=1))
    _write_json(art / "char_fidelity_result.json", {
        "records": [{
            "asset": item["asset_name"],
            "ok": True,
            "nanite_enabled": True,
            "provenance": {"source": "Hi3D fixture", "license": "Hi3D Essential plan"},
        }]
    })
    _write_json(art / "validation" / "character_deformation_review.json", {
        "state": "USER_REPORTED_DEFECT",
        "asset": f"{item['asset_name']}_Rig",
        "issues": ["right_arm_deformed"],
    })

    report = audit_character_source_sync(root, project, characters=[item])

    char = report["characters"][0]
    assert char["sync_ready"] is False, char
    assert char["stages"]["runtime_deformation_clearance"]["state"] == "FAIL", char["stages"]
    assert char["next_action"]["action"] == "repair_runtime_deformation_in_unreal", char["next_action"]


def test_fragmented_blender_rig_review_blocks_unreal_runtime_export():
    from dimwit.pipelines.character_source_sync import evaluate_blender_anatomy_review

    review = _review(armatures=1)
    review["component_metrics"] = {
        "measured": True,
        "component_count": 5,
        "largest_component_face_fraction": 0.9991,
    }

    verdict = evaluate_blender_anatomy_review(review, stage="rig")

    assert verdict["passed"] is False, verdict
    assert any("fragmented rig mesh" in issue for issue in verdict["issues"]), verdict["issues"]


def test_quarantined_runtime_defect_retires_character_instead_of_repair_loop():
    root = TMP / "quarantined_defect_root"
    project = TMP / "quarantined_defect_project"
    item = EXPECTED_CHARACTERS[1]
    art = root / "artifacts"
    _write_json(root / "config" / "character_roster.json", {
        "schema_version": 1,
        "active_humanoid_target": 7,
        "active_mech_target": 8,
        "quarantined_humanoids": {
            item["key"]: {
                "state": "QUARANTINED_RETIRED_PROTOTYPE",
                "asset_name": item["asset_name"],
                "reason": "operator retired Ekris after runtime deformation failure",
                "replacement_required": False,
                "capacity_rebalanced_to_mechs": True,
                "evidence": ["artifacts/validation/character_deformation_review.json"],
            }
        },
        "mech_characters": [{"character_id": f"mech_{idx:02d}", "asset_name": f"SM_Char_Mech_{idx:02d}", "active": True} for idx in range(1, 9)],
        "next_lane": "environments_maps_assets",
    })
    _write_json(art / "validation" / "character_deformation_review.json", {
        "state": "USER_REPORTED_DEFECT",
        "asset": f"{item['asset_name']}_Rig",
        "issues": ["right_arm_deformed"],
    })

    report = audit_character_source_sync(root, project, characters=[item])

    char = report["characters"][0]
    assert char["active_state"] == "QUARANTINED_RETIRED_PROTOTYPE", char
    assert char["excluded_from_active_ready"] is True, char
    assert char["next_action"]["action"] == "retired_no_repair_loop", char["next_action"]
    assert report["summary"]["quarantined_humanoid_count"] == 1, report["summary"]


def test_missing_unreal_import_is_prioritized_before_metahuman_attempt():
    root = TMP / "missing_unreal_import_root"
    project = TMP / "missing_unreal_import_project"
    item = EXPECTED_CHARACTERS[1]
    art = root / "artifacts"
    source = art / f"{item['source_stem']}.glb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"glb")
    token = item["asset_id"]
    retopo = art / "handcraft" / token / f"{token}_retopo.fbx"
    retopo.parent.mkdir(parents=True, exist_ok=True)
    retopo.write_bytes(b"fbx")
    rig = art / "rig" / f"{token}_handcrafted_rig.fbx"
    rig.parent.mkdir(parents=True, exist_ok=True)
    rig.write_bytes(b"fbx")
    _write_json(art / "blender_anatomy_review" / f"{item['source_stem']}_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_retopo_review.json", _review())
    _write_json(art / "blender_anatomy_review" / f"{token}_handcrafted_rig_review.json", _review(armatures=1))

    report = audit_character_source_sync(root, project, characters=[item])

    char = report["characters"][0]
    assert char["next_action"]["stage"] == "unreal_import", char["next_action"]
    assert char["next_action"]["action"] == "run_character_fidelity_import", char["next_action"]


def test_pipeline_and_validation_registry_expose_character_source_sync():
    from dimwit.pipelines import PIPELINES
    from dimwit.pipelines.validation_registry import REGISTRY

    assert PIPELINES["character_source_sync"] == "dimwit.pipelines.character_source_sync:CharacterSourceSyncPipeline"
    gates = {validator.id for validator in REGISTRY if validator.domain == "character_source_sync"}
    assert "character_source_sync_chain" in gates


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
