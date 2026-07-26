from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.autonomy_capability_matrix import (
    build_autonomy_capability_matrix,
    external_reference_catalog,
    validate_autonomy_report,
)
from dimwit.pipelines.base import OPERATOR_ONLY


TMP = Path(tempfile.mkdtemp(prefix="dimwit_autonomy_matrix_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fixture_roots() -> tuple[Path, Path]:
    root = TMP / "dimwit"
    project = TMP / "wanefall"
    (root / "artifacts" / "validation").mkdir(parents=True, exist_ok=True)
    (project / "Config").mkdir(parents=True, exist_ok=True)
    _write_json(project / "WanefallGreybox.uproject", {
        "EngineAssociation": "5.8",
        "Plugins": [
            {"Name": "RigLogic", "Enabled": True},
            {"Name": "HairStrands", "Enabled": True},
            {"Name": "LiveLinkControlRig", "Enabled": True},
        ],
    })
    _write_json(root / "config" / "director_tasks.json", {
        "tasks": [
            {"pipeline": "real_game_validation", "asset_id": "wanefall_default_lobby", "priority": 10, "cost": 1, "expected_value": 4},
            {"pipeline": "character_fidelity", "asset_id": "ekris", "priority": 8, "cost": 3, "expected_value": 2},
        ],
    })
    return root, project


def _write_autonomy_fixtures(root: Path) -> None:
    _write_json(root / "artifacts" / "validation" / "validation_report.json", {
        "suite_verdict": "REJECTED",
        "run_ts": 1782691497,
        "counts": {"PASS": 117, "FAIL": 1, "BLOCKED": 32, "REJECTED": 3},
        "total": 153,
        "by_domain": {
            "real_game_runtime": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "REJECTED": 2},
            "metahuman_character_pipeline": {"PASS": 4, "FAIL": 0, "BLOCKED": 1, "REJECTED": 0},
            "pipeline_contracts": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "proof_integrity": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1},
            "ui_hud": {"PASS": 4, "FAIL": 1, "BLOCKED": 0, "REJECTED": 0},
            "movement_traversal": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "weapons_inplay": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "br_loop": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        },
        "results": [
            {
                "validator_id": "real_game_no_fatal_log_burst",
                "domain": "real_game_runtime",
                "severity": "blocker",
                "state": "REJECTED",
                "issues": ["fatal_count=0 error_count=10"],
                "detail": {"fatal_count": 0, "error_count": 10},
            },
            {
                "validator_id": "real_game_runtime_not_placeholder_dominated",
                "domain": "real_game_runtime",
                "severity": "blocker",
                "state": "REJECTED",
                "issues": ["flat mid-gray patch fraction 0.049"],
                "detail": {"flat_midgray_patch_fraction": 0.049383},
            },
            {
                "validator_id": "metahuman_transform_output_evidence_present",
                "domain": "metahuman_character_pipeline",
                "severity": "blocker",
                "state": "BLOCKED",
                "issues": [],
                "detail": {"blocked": "no MetaHuman output evidence found"},
            },
            {
                "validator_id": "ledger_chain_actually_chained",
                "domain": "proof_integrity",
                "severity": "blocker",
                "state": "REJECTED",
                "issues": ["broken chain validation.jsonl"],
                "detail": {},
            },
            {
                "validator_id": "hud_weakpoint_indicator_pending",
                "domain": "ui_hud",
                "severity": "warn",
                "state": "FAIL",
                "issues": ["weakpoint indicator pending"],
                "detail": {},
            },
        ],
    })
    _write_json(root / "artifacts" / "real_game_validation" / "real_game_validation_result.json", {
        "state": "REJECTED",
        "hard_fail": True,
        "checks": {
            "log_scan": {"passed": False, "fatal_count": 0, "error_count": 10, "issues": ["fatal_count=0 error_count=10"]},
            "placeholder_geometry_signal": {"passed": False, "flat_midgray_patch_fraction": 0.049383, "issues": ["flat mid-gray patch fraction 0.049"]},
            "window_found": {"passed": True},
            "still_nonblank": {"passed": True},
        },
    })
    _write_json(root / "artifacts" / "metahuman_utilization" / "metahuman_utilization_audit.json", {
        "summary": {
            "classification": "PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT",
            "source_ready_count": 8,
            "expected_character_count": 8,
            "metahuman_output_present": False,
            "engine_version": "5.8",
        },
        "unreal": {
            "dna_calibration_version_gate": {
                "classification": "BLOCKED_UNREAL_VERSION",
                "recommended_workflow": "MetaHuman for Maya",
            }
        },
        "metahuman_outputs": {"present": False, "paths": [], "count": 0},
        "boundaries": {"no_gpl_code_copied": True, "no_epic_tooling_redistributed": True},
    })
    _write_json(root / "artifacts" / "pipeline_contracts" / "pipeline_contract_audit.json", {
        "summary": {"passed": True, "registered_count": 9, "blocking_issue_count": 0},
        "checks": {
            "registry_clean": {"passed": True, "issues": []},
            "manifest_parity": {"passed": True, "issues": []},
            "director_tasks": {"passed": True, "issues": []},
            "operator_only_writes": {"passed": True, "issues": []},
        },
    })
    _write_json(root / "codex_handoff.json", {
        "ceiling": "PROMOTED_TO_REVIEW",
        "work_queue": [
            {"id": "real-game-runtime-loop", "facet": "runtime_validation", "state": "INSTALLED_REJECTED_PENDING_GAME_REPAIR", "need": "clear UE log errors and blockout geometry"},
            {"id": "metahuman-character-utilization-gate", "facet": "character_pipeline", "state": "INSTALLED_PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT", "need": "produce real MetaHuman output evidence"},
        ],
    })


def test_matrix_covers_required_lanes_and_prioritizes_real_game_blockers():
    root, project = _fixture_roots()
    _write_autonomy_fixtures(root)
    report = build_autonomy_capability_matrix(root, project)
    lanes = {item["required_lane"] for item in report["capability_matrix"]}
    assert {
        "runtime_validation",
        "character_pipeline",
        "proof_integrity",
        "backend_social",
        "external_references",
        "tool_discovery",
        "recursive_orchestration",
    }.issubset(lanes)
    queue = report["recursive_improvement_queue"]
    assert queue[0]["affected_subsystem"] == "runtime_validation"
    assert "real game" in queue[0]["title"].lower()
    assert any(item["version_risk"] == "BLOCKED_UNREAL_VERSION" for item in queue)
    validation = validate_autonomy_report(report)
    assert validation["passed"] is True


def test_external_reference_catalog_preserves_license_and_adoption_boundaries():
    catalog = external_reference_catalog()
    by_name = {item["source_name"]: item for item in catalog}
    assert by_name["Character DNA Addon"]["adoption_mode"] == "REFERENCE_ONLY"
    assert by_name["Character DNA Addon"]["license_class"] == "GPL_REFERENCE_ONLY"
    assert by_name["Epic MetaHuman DNA Calibration"]["adoption_mode"] == "OFFICIAL_REFERENCE_WITH_VERSION_GATE"
    assert by_name["Nakama"]["adoption_mode"] == "THIN_ADAPTER"
    assert by_name["Cocos2d-x"]["adoption_mode"] == "REFERENCE_ONLY"
    assert by_name["MagicTools"]["adoption_mode"] == "REFERENCE_ONLY"


def test_queue_actions_have_validation_and_rollback_commands():
    root, project = _fixture_roots()
    _write_autonomy_fixtures(root)
    report = build_autonomy_capability_matrix(root, project)
    for item in report["recursive_improvement_queue"]:
        assert item["validation_command"]
        assert item["rollback_notes"]
        assert item["promotion_threshold"] == "PROMOTED_TO_REVIEW"


def test_autonomy_report_contains_no_operator_only_promotion_states():
    root, project = _fixture_roots()
    _write_autonomy_fixtures(root)
    report = build_autonomy_capability_matrix(root, project)
    payload = json.dumps(report)
    for state in OPERATOR_ONLY:
        assert state not in payload


def test_validation_registry_contains_autonomy_engine_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "autonomy_engine"}
    assert {
        "autonomy_matrix_fresh",
        "autonomy_matrix_covers_required_lanes",
        "autonomy_external_references_classified",
        "autonomy_queue_ranked_actions",
        "autonomy_queue_actions_have_validation_and_rollback",
        "autonomy_no_operator_only_promotions",
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
