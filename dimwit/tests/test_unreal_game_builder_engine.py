from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from dimwit.pipelines.base import OPERATOR_ONLY
from dimwit.pipelines.unreal_game_builder_engine import (
    REQUIRED_GAME_BUILDER_LANES,
    UnrealGameBuilderEnginePipeline,
    build_unreal_game_builder_report,
    validate_unreal_game_builder_report,
    write_unreal_game_builder_report,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_unreal_game_builder_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fixture_roots() -> tuple[Path, Path]:
    root = TMP / "dimwit"
    project = TMP / "wanefall"
    _write_json(project / "WanefallGreybox.uproject", {
        "EngineAssociation": "5.8",
        "Plugins": [
            {"Name": "RigLogic", "Enabled": True},
            {"Name": "HairStrands", "Enabled": True},
            {"Name": "ModelContextProtocol", "Enabled": True},
        ],
    })
    _write_json(root / "config" / "production_pipelines.json", {
        "pipelines": {
            "real_game_validation": {"status": "BUILT"},
            "character_fidelity": {"status": "BUILT"},
            "unreal_game_builder_engine": {"status": "BUILT"},
        }
    })
    _write_json(root / "config" / "director_tasks.json", {
        "tasks": [
            {"pipeline": "unreal_game_builder_engine", "asset_id": "wanefall_autonomous_studio", "priority": 11, "cost": 1, "expected_value": 5},
            {"pipeline": "real_game_validation", "asset_id": "wanefall_default_lobby", "priority": 10, "cost": 1, "expected_value": 4},
        ]
    })
    return root, project


def _write_builder_fixtures(root: Path) -> None:
    _write_json(root / "artifacts" / "validation" / "validation_report.json", {
        "suite_verdict": "REJECTED",
        "run_ts": int(time.time()),
        "counts": {"PASS": 158, "FAIL": 1, "BLOCKED": 1, "REJECTED": 1},
        "total": 161,
        "by_domain": {
            "characters_static_full_nanite": {"PASS": 64, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "rigged_skeletal_meshes": {"PASS": 10, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "animation_wiring": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "combat": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "gameplay_code": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "materials_shaders": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "environment_maps": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "vfx_audio": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "intent_conformance": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "design_system": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "proof_integrity": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1},
            "movement_traversal": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "weapons_inplay": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "hud_readability": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "ui_hud": {"PASS": 4, "FAIL": 1, "BLOCKED": 0, "REJECTED": 0},
            "br_loop": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "pipeline_contracts": {"PASS": 5, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "metahuman_character_pipeline": {"PASS": 4, "FAIL": 0, "BLOCKED": 1, "REJECTED": 0},
            "real_game_runtime": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "autonomy_engine": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        },
        "results": [
            {
                "validator_id": "ledger_chain_actually_chained",
                "domain": "proof_integrity",
                "severity": "blocker",
                "state": "REJECTED",
                "issues": ["broken chains: ['validation.jsonl']"],
                "detail": {},
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
                "validator_id": "hud_weakpoint_indicator_pending",
                "domain": "ui_hud",
                "severity": "warn",
                "state": "FAIL",
                "issues": ["weakpoint_indicator not in HUD capture"],
                "detail": {},
            },
        ],
    })
    _write_json(root / "artifacts" / "real_game_validation" / "real_game_validation_result.json", {
        "state": "PASS",
        "suite_pass": True,
        "checks": {
            "window_found": {"passed": True},
            "still_nonblank": {"passed": True},
            "frame_burst_nonblank": {"passed": True},
            "placeholder_geometry_signal": {"passed": True},
            "log_scan": {"passed": True},
        },
        "artifacts": {"still": "artifacts/real_game_validation/still.png"},
    })
    _write_json(root / "artifacts" / "metahuman_utilization" / "metahuman_utilization_audit.json", {
        "summary": {
            "classification": "PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT",
            "source_ready_count": 8,
            "expected_character_count": 8,
            "metahuman_output_present": False,
        },
        "metahuman_outputs": {"present": False, "paths": [], "count": 0},
        "unreal": {
            "dna_calibration_version_gate": {
                "classification": "BLOCKED_UNREAL_VERSION",
                "recommended_workflow": "MetaHuman for Maya",
            }
        },
    })
    _write_json(root / "artifacts" / "pipeline_contracts" / "pipeline_contract_audit.json", {
        "summary": {"passed": True, "registered_count": 10, "blocking_issue_count": 0},
        "checks": {
            "registry_clean": {"passed": True, "issues": []},
            "manifest_parity": {"passed": True, "issues": []},
            "director_tasks": {"passed": True, "issues": []},
            "operator_only_writes": {"passed": True, "issues": []},
        },
    })
    _write_json(root / "artifacts" / "autonomy" / "AUTONOMY_CAPABILITY_FINAL_REPORT_20260628.json", {
        "classification": "PASS_WITH_NOTES",
        "capability_matrix": [{"required_lane": "runtime_validation", "state": "PASS"}],
        "recursive_improvement_queue": [
            {
                "rank": 1,
                "affected_subsystem": "proof_integrity",
                "title": "Repair validation ledger chain integrity",
                "validation_command": "python scripts/pipeline/run_validation.py --domain proof_integrity --no-ue",
                "rollback_notes": "Revert only proof ledger repair files.",
                "promotion_threshold": "PROMOTED_TO_REVIEW",
            }
        ],
    })
    _write_json(root / "codex_handoff.json", {
        "ceiling": "PROMOTED_TO_REVIEW",
        "work_queue": [
            {"id": "metahuman-character-utilization-gate", "state": "INSTALLED_PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT"},
            {"id": "real-game-runtime-loop", "state": "INSTALLED_PASS_PROMOTED_TO_REVIEW"},
        ],
    })


def _lane_by_id(report: dict) -> dict:
    return {item["lane_id"]: item for item in report["game_builder_lanes"]}


def test_game_builder_report_covers_s_tier_unreal_lanes_and_current_blockers():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    report = build_unreal_game_builder_report(root, project)
    lanes = _lane_by_id(report)
    assert set(REQUIRED_GAME_BUILDER_LANES).issubset(lanes)
    assert lanes["real_game_playtest_validation"]["current_state"] == "PASS"
    assert lanes["proof_integrity_provenance"]["current_state"] == "REJECTED"
    assert lanes["metahuman_transformation"]["current_state"] == "BLOCKED"
    assert lanes["ui_hud_command_surface"]["current_state"] == "FAIL"
    assert report["source_truth"]["validation_suite_verdict"] == "REJECTED"
    validation = validate_unreal_game_builder_report(report)
    assert validation["passed"] is True


def test_game_builder_queue_prioritizes_validation_blockers_without_operator_promotions():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    report = build_unreal_game_builder_report(root, project)
    queue = report["recursive_game_build_queue"]
    affected = [item["affected_lane"] for item in queue[:3]]
    assert affected == [
        "proof_integrity_provenance",
        "metahuman_transformation",
        "ui_hud_command_surface",
    ]
    for item in queue:
        assert item["validation_command"]
        assert item["rollback_notes"]
        assert item["promotion_threshold"] == "PROMOTED_TO_REVIEW"
    payload = json.dumps(report)
    for state in OPERATOR_ONLY:
        assert state not in payload


def test_game_builder_validator_distinguishes_descriptive_names_from_state_values():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    report = build_unreal_game_builder_report(root, project)
    forbidden = next(iter(OPERATOR_ONLY))
    report["remaining_global_blockers"][0]["regression_caught"] = (
        f"autonomous code writes {forbidden}"
    )
    assert validate_unreal_game_builder_report(report)["passed"] is True

    report["game_builder_lanes"][0]["current_state"] = forbidden
    validation = validate_unreal_game_builder_report(report)
    assert validation["passed"] is False
    assert any("operator-only state used" in issue for issue in validation["issues"])


def test_stale_full_suite_cannot_produce_ready_or_self_validated_report():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    report_path = root / "artifacts" / "validation" / "validation_report.json"
    stale = json.loads(report_path.read_text(encoding="utf-8"))
    stale["run_ts"] = int(time.time()) - 3600
    _write_json(report_path, stale)

    report = build_unreal_game_builder_report(root, project)

    assert report["status"] == "UNREAL_GAME_BUILDER_ENGINE_BLOCKED_STALE_VALIDATION"
    assert report["source_validation_report"]["fresh"] is False
    assert validate_unreal_game_builder_report(report)["passed"] is False


def test_write_outputs_doctrine_scorecard_and_final_report():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    out = root / "tmp_out"
    report = write_unreal_game_builder_report(
        root,
        project,
        out / "doctrine.json",
        out / "scorecard.json",
        out / "final.json",
    )
    doctrine = json.loads((out / "doctrine.json").read_text(encoding="utf-8"))
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    final = json.loads((out / "final.json").read_text(encoding="utf-8"))
    assert doctrine["doctrine_laws"]["fail_closed"] == "Missing evidence blocks; it never becomes a claim."
    assert len(scorecard["game_builder_lanes"]) == len(REQUIRED_GAME_BUILDER_LANES)
    assert final["self_validation"]["passed"] is True
    assert report["proof_artifacts"] == [str(out / "doctrine.json"), str(out / "scorecard.json"), str(out / "final.json")]


def test_pipeline_runs_through_production_backbone_to_review():
    root, project = _fixture_roots()
    _write_builder_fixtures(root)
    pipe = UnrealGameBuilderEnginePipeline(ledger_path=root / "ledger" / "pipelines" / "unreal_game_builder_engine.jsonl")
    result = pipe.run({
        "asset_id": "wanefall_autonomous_studio",
        "root": str(root),
        "project": str(project),
        "output_dir": str(root / "artifacts" / "unreal_game_builder"),
    })
    assert str(result.state).endswith("PROMOTED_TO_REVIEW")
    assert result.score == 1.0
    assert (root / "artifacts" / "unreal_game_builder" / "UNREAL_GAME_BUILDER_FINAL_REPORT_20260629.json").exists()


def test_validation_registry_contains_unreal_game_builder_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "unreal_game_builder_engine"}
    assert {
        "unreal_game_builder_fresh",
        "unreal_game_builder_covers_required_lanes",
        "unreal_game_builder_lane_validation_and_rollback",
        "unreal_game_builder_current_blockers_visible",
        "unreal_game_builder_queue_prioritizes_blockers",
        "unreal_game_builder_no_operator_only_promotions",
    }.issubset(gates)


def test_pipeline_registry_manifest_and_director_include_game_builder():
    from dimwit.pipelines import PIPELINES

    manifest = json.loads(Path("config/production_pipelines.json").read_text(encoding="utf-8"))
    director = json.loads(Path("config/director_tasks.json").read_text(encoding="utf-8"))
    assert "unreal_game_builder_engine" in PIPELINES
    assert "unreal_game_builder_engine" in manifest["pipelines"]
    assert any(task.get("pipeline") == "unreal_game_builder_engine" for task in director["tasks"])


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
