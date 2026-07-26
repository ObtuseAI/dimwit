from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.metahuman_utilization import (
    EXPECTED_CHARACTERS,
    audit_metahuman_utilization,
    classify_dna_calibration_support,
    external_reference_decisions,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_metahuman_utilization_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fixture_roots() -> tuple[Path, Path, Path]:
    root = TMP / "dimwit"
    project = TMP / "wanefall"
    ue_root = TMP / "UE_5.8"
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    ue_root.mkdir(parents=True, exist_ok=True)
    _write_json(project / "WanefallGreybox.uproject", {
        "EngineAssociation": "5.8",
        "Plugins": [
            {"Name": "RigLogic", "Enabled": True},
            {"Name": "HairStrands", "Enabled": True},
            {"Name": "LiveLinkControlRig", "Enabled": True},
        ],
    })
    for plugin in ("MetaHumanCharacter", "MetaHumanSDK", "MetaHumanAnimator"):
        (ue_root / "Engine" / "Plugins" / "MetaHuman" / plugin).mkdir(parents=True, exist_ok=True)
    return root, project, ue_root


def _write_character_fixture(root: Path) -> None:
    records = []
    for item in EXPECTED_CHARACTERS:
        source_glb = root / "artifacts" / f"{item['source_stem']}.glb"
        source_glb.write_bytes(b"glb")
        asset_id = item["asset_id"]
        handcraft = root / "artifacts" / "handcraft" / asset_id / f"{asset_id}_retopo.fbx"
        handcraft.parent.mkdir(parents=True, exist_ok=True)
        handcraft.write_bytes(b"fbx")
        records.append({
            "asset": item["asset_name"],
            "src": item["source_stem"],
            "ok": True,
            "nanite_enabled": True,
            "provenance": {"source_file": f"{item['source_stem']}.glb", "license": "Hi3D Essential plan"},
        })
    _write_json(root / "artifacts" / "char_fidelity_result.json", {"records": records, "ok_count": len(records)})


def test_ue58_blocks_direct_dna_calibration_and_recommends_metahuman_for_maya():
    gate = classify_dna_calibration_support("5.8")
    assert gate["classification"] == "BLOCKED_UNREAL_VERSION"
    assert gate["recommended_workflow"] == "MetaHuman for Maya"


def test_audit_detects_all_expected_3d_character_sources_ready():
    root, project, ue_root = _fixture_roots()
    _write_character_fixture(root)
    report = audit_metahuman_utilization(root, project, ue_root)
    assert report["summary"]["expected_character_count"] == len(EXPECTED_CHARACTERS)
    assert report["summary"]["source_ready_count"] == len(EXPECTED_CHARACTERS)
    assert all(item["source_ready"] for item in report["characters"])


def test_missing_metahuman_output_blocks_conversion_claim():
    root, project, ue_root = _fixture_roots()
    _write_character_fixture(root)
    report = audit_metahuman_utilization(root, project, ue_root)
    assert report["summary"]["classification"] == "PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT"
    assert report["metahuman_outputs"]["present"] is False
    tooling = report["unreal"]["headless_tooling_evidence"]
    assert tooling["headless_transform_route_proven"] is False
    assert "no project MetaHuman/DNA output exists" in tooling["blocked_reason"]


def test_quarantined_metahuman_output_does_not_satisfy_active_output_gate():
    root, project, ue_root = _fixture_roots()
    _write_character_fixture(root)
    quarantined = EXPECTED_CHARACTERS[0]
    _write_json(root / "config" / "character_roster.json", {
        "schema_version": 1,
        "active_humanoid_target": len(EXPECTED_CHARACTERS) - 1,
        "quarantined_humanoids": {
            quarantined["key"]: {
                "state": "QUARANTINED_OPERATOR_REJECTED_RUNTIME_DEFECT",
                "asset_name": quarantined["asset_name"],
                "asset_id": quarantined["asset_id"],
                "reason": "fixture rejected runtime defect",
                "evidence": ["artifacts/validation/character_deformation_review_fixture.json"],
            }
        },
        "mech_characters": [],
    })
    imported = (
        project / "Content" / "Wanefall" / "Dimwit" / "Characters" /
        quarantined["asset_name"] / "StaticMeshes" / f"{quarantined['asset_name']}.uasset"
    )
    imported.parent.mkdir(parents=True, exist_ok=True)
    imported.write_bytes(b"uasset")
    dna = root / "artifacts" / "metahuman_output_attempt" / quarantined["key"] / f"MH_{quarantined['key']}_posed.dna"
    dna.parent.mkdir(parents=True, exist_ok=True)
    dna.write_bytes(b"dna")
    _write_json(dna.parent / "metahuman_output_attempt_result.json", {
        "state": "PROMOTED_TO_REVIEW",
        "asset_id": quarantined["key"],
        "source_character": quarantined["key"],
        "input_mesh": str(imported),
        "wanefall_source_linked": True,
        "transform_operations": ["ConformToTargetMeshes", "ExportPosedDNA"],
        "outputs": [{"path": str(dna), "kind": "posed_dna"}],
    })

    report = audit_metahuman_utilization(root, project, ue_root)

    assert report["metahuman_outputs"]["present"] is False, report["metahuman_outputs"]
    rejected = report["metahuman_outputs"]["rejected_attempts"]
    assert any("quarantined" in "; ".join(item.get("issues", [])) for item in rejected), rejected


def test_reference_decisions_keep_gpl_and_epic_tools_out_of_runtime():
    decisions = external_reference_decisions()
    by_name = {item["source_name"]: item for item in decisions}
    assert by_name["Character DNA Addon"]["license_class"] == "GPL_REFERENCE_ONLY"
    assert by_name["Character DNA Addon"]["adoption_mode"] == "REFERENCE_ONLY"
    assert by_name["Epic MetaHuman DNA Calibration"]["adoption_mode"] == "OFFICIAL_REFERENCE_WITH_VERSION_GATE"
    assert by_name["Epic MetaHuman DNA Calibration"]["runtime_redistribution"] == "FORBIDDEN"


def test_validation_registry_contains_metahuman_character_pipeline_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "metahuman_character_pipeline"}
    assert {
        "metahuman_audit_fresh",
        "metahuman_source_3d_assets_ready",
        "metahuman_version_gate_respected",
        "metahuman_license_boundaries_clean",
        "metahuman_transform_output_evidence_present",
    }.issubset(gates)


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
