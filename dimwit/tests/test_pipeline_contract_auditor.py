from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.contract_auditor import (
    OPERATOR_ONLY_STATES,
    audit_registered_pipelines,
    detect_operator_only_writes,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_pipeline_contracts_"))


def test_audit_includes_every_registered_pipeline():
    from dimwit.pipelines import list_pipelines

    report = audit_registered_pipelines(Path.cwd())
    assert report["summary"]["registered_count"] == len(list_pipelines())
    assert {item["name"] for item in report["pipelines"]} == set(list_pipelines())


def test_manifest_parity_catches_missing_registered_pipeline():
    manifest = {"pipelines": {"known": {"module": "x:y"}}}
    report = audit_registered_pipelines(
        Path.cwd(),
        registry={
            "known": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline",
            "missing": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline",
        },
        manifest=manifest,
        director_tasks={
            "tasks": [{"pipeline": "known", "asset_id": "asset", "priority": 1, "cost": 1, "expected_value": 1}]
        },
    )
    parity = report["checks"]["manifest_parity"]
    assert parity["passed"] is False
    assert "missing" in parity["missing_from_manifest"]


def test_director_task_validation_catches_unknown_pipeline():
    report = audit_registered_pipelines(
        Path.cwd(),
        registry={"known": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline"},
        manifest={
            "pipelines": {
                "known": {"module": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline"}
            }
        },
        director_tasks={
            "tasks": [{"pipeline": "ghost", "asset_id": "asset", "priority": 1, "cost": 1, "expected_value": 1}]
        },
    )
    director = report["checks"]["director_tasks"]
    assert director["passed"] is False
    assert "ghost" in director["unknown_pipelines"]


def test_operator_only_scan_ignores_comments_and_boundary_strings_but_rejects_writes():
    source = TMP / "operator_state_probe.py"
    source.write_text(
        "# HUMAN_ACCEPTED appears in a comment\n"
        "HUMAN_ACCEPTED = 'HUMAN_ACCEPTED'\n"
        "message = 'No HUMAN_ACCEPTED state was written.'\n"
        "state = 'HUMAN_ACCEPTED'\n",
        encoding="utf-8",
    )
    findings = detect_operator_only_writes(source, OPERATOR_ONLY_STATES)
    assert len(findings) == 1
    assert findings[0]["state"] == "HUMAN_ACCEPTED"


def test_validation_registry_contains_pipeline_contract_gates():
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {validator.id for validator in REGISTRY if validator.domain == "pipeline_contracts"}
    assert {
        "pipeline_contract_audit_fresh",
        "pipeline_contract_registry_clean",
        "pipeline_contract_manifest_parity",
        "pipeline_contract_director_tasks_known",
        "pipeline_contract_no_operator_only_writes",
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
