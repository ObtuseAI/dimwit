"""Regression tests for state truth sync (bundle: WANEFALL_STATE_TRUTH_SYNC_V1).

Audit findings 2026-07-01: codex_handoff.json was 2 days stale (claimed a green 173-validator suite
and 7 active humanoids while disk truth was a REJECTED 162-validator suite and 6 humanoids); the
WANEFALL-side autonomy queue copy had drifted since 06-28; and the builder/autonomy meta-artifacts
regenerated mid-suite from whatever validation_report.json contained (often a domain-scoped report),
producing all-NEEDS_EVIDENCE artifacts that contradicted the same run's 158 PASS.

Pinned behavior: (1) full-scope suite runs persist validation_report_full.json and sync a
generated_truth block into the handoff from disk truth; (2) meta-artifact generators derive from the
latest FULL report and stamp source provenance; (3) the autonomy queue is mirrored to the WANEFALL
Config copy by the same writer that regenerates it.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.state_sync import sync_state_truth, load_validation_report_with_provenance
from dimwit.pipelines.autonomy_capability_matrix import build_autonomy_capability_matrix, write_autonomy_capability_matrix

TMP = Path(tempfile.mkdtemp(prefix="dimwit_state_truth_sync_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _full_report(run_ts: int = 1782940000) -> dict:
    return {
        "suite_verdict": "PASS",
        "run_ts": run_ts,
        "scope": "full",
        "run_ue": True,
        "counts": {"PASS": 160, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        "total": 160,
        "by_domain": {
            "proof_integrity": {"PASS": 8, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
            "packaged_build": {"PASS": 6, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0},
        },
        "results": [],
    }


def _fixture_root(name: str) -> tuple[Path, Path]:
    root = TMP / name / "dimwit"
    project = TMP / name / "wanefall"
    (root / "artifacts" / "validation").mkdir(parents=True, exist_ok=True)
    (project / "Config").mkdir(parents=True, exist_ok=True)
    _write_json(root / "config" / "character_roster.json", {
        "active_humanoid_target": 6,
        "active_mech_target": 8,
        "next_lane": "environments_maps_assets",
        "quarantined_humanoids": {"bad_runtime_01": {}, "retired_prototype_02": {}},
        "mech_characters": [],
    })
    _write_json(root / "artifacts" / "autonomy" / "recursive_improvement_queue.json", {
        "schema_version": 1,
        "generated_at": 1782940000.0,
        "recursive_improvement_queue": [
            {"rank": 1, "title": "Repair validation ledger chain integrity"},
            {"rank": 2, "title": "Improve movement traversal proof"},
        ],
    })
    _write_json(root / "codex_handoff.json", {
        "updated": "2026-06-29 (stale)",
        "driver": "codex",
        "ceiling": "PROMOTED_TO_REVIEW",
        "registry": "173 validators across 25 domains (stale claim)",
        "work_queue": [],
    })
    return root, project


def test_sync_state_truth_updates_handoff_and_writes_summary():
    root, project = _fixture_root("sync_ok")
    _write_json(root / "artifacts" / "validation" / "validation_report_full.json", _full_report(run_ts=1782940123))

    summary = sync_state_truth(root, project)

    handoff = json.loads((root / "codex_handoff.json").read_text(encoding="utf-8"))
    truth = handoff.get("generated_truth") or {}
    assert truth.get("source_report", {}).get("run_ts") == 1782940123
    assert truth.get("suite_verdict") == "PASS"
    assert truth.get("counts", {}).get("PASS") == 160
    assert truth.get("active_humanoid_target") == 6
    assert "bad_runtime_01" in (truth.get("quarantined_humanoids") or [])
    assert truth.get("queue_top") and "ledger" in truth["queue_top"][0].lower()
    # the human-facing registry line must state current disk truth, not the stale claim
    assert "160 validators" in handoff.get("registry", "")
    assert "PASS" in handoff.get("registry", "")
    # doctrine fields must survive the sync untouched
    assert handoff.get("ceiling") == "PROMOTED_TO_REVIEW"
    assert summary.get("ok") is True
    assert (root / "artifacts" / "state_sync" / "state_truth_sync.json").exists()


def test_sync_state_truth_fails_closed_without_full_report():
    root, project = _fixture_root("sync_missing_report")
    try:
        sync_state_truth(root, project)
    except FileNotFoundError as exc:
        assert "validation_report_full" in str(exc)
    else:
        raise AssertionError("sync without a full-suite report must fail closed, not fabricate truth")


def test_load_validation_report_prefers_full_report_with_provenance():
    root, project = _fixture_root("prefer_full")
    # a domain-scoped run rewrote validation_report.json AFTER the last full run
    _write_json(root / "artifacts" / "validation" / "validation_report.json", {
        "suite_verdict": "REJECTED", "run_ts": 1782949999, "scope": {"domains": ["proof_integrity"]},
        "counts": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1}, "total": 8,
        "by_domain": {"proof_integrity": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1}}, "results": [],
    })
    _write_json(root / "artifacts" / "validation" / "validation_report_full.json", _full_report(run_ts=1782940123))

    report, provenance = load_validation_report_with_provenance(root)
    assert report["run_ts"] == 1782940123, "generators must derive from the latest FULL report"
    assert provenance["used_full_report"] is True
    assert provenance["run_ts"] == 1782940123
    assert provenance["scope"] == "full"


def test_autonomy_matrix_stamps_source_report_and_mirrors_queue_to_project():
    root, project = _fixture_root("matrix_mirror")
    _write_json(project / "WanefallGreybox.uproject", {"EngineAssociation": "5.8", "Plugins": []})
    _write_json(root / "config" / "director_tasks.json", {"tasks": [
        {"pipeline": "real_game_validation", "asset_id": "wanefall_default_lobby", "priority": 10, "cost": 1, "expected_value": 4},
    ]})
    # stale domain-scoped latest report + good full report: matrix must use the full one
    _write_json(root / "artifacts" / "validation" / "validation_report.json", {
        "suite_verdict": "REJECTED", "run_ts": 1782949999, "scope": {"domains": ["proof_integrity"]},
        "counts": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1}, "total": 8,
        "by_domain": {"proof_integrity": {"PASS": 7, "FAIL": 0, "BLOCKED": 0, "REJECTED": 1}}, "results": [],
    })
    _write_json(root / "artifacts" / "validation" / "validation_report_full.json", _full_report(run_ts=1782940123))

    report = build_autonomy_capability_matrix(root, project)
    stamped = report.get("source_validation_report") or {}
    assert stamped.get("run_ts") == 1782940123, f"matrix derived from the wrong report: {stamped}"
    assert stamped.get("used_full_report") is True

    matrix_path = root / "artifacts" / "autonomy" / "autonomy_capability_matrix.json"
    queue_path = root / "artifacts" / "autonomy" / "recursive_improvement_queue.json"
    final_path = root / "artifacts" / "autonomy" / "FINAL.json"
    write_autonomy_capability_matrix(root, project, matrix_path, queue_path, final_path)

    mirror = project / "Config" / "WANEFALL_AutonomyQueue" / "recursive_improvement_queue.json"
    assert mirror.exists(), "queue must be mirrored to the WANEFALL Config copy by its own writer"
    assert mirror.read_bytes() == queue_path.read_bytes(), "mirror must be byte-identical to the source queue"
    matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert (matrix_payload.get("source_validation_report") or {}).get("run_ts") == 1782940123


def test_validation_registry_contains_state_truth_gates():
    from dimwit.pipelines.validation_registry import build_registry
    registry = build_registry()
    by_id = {validator.id: validator for validator in registry}
    for validator_id in ("handoff_generated_truth_matches_disk", "wanefall_autonomy_queue_copy_synced"):
        assert validator_id in by_id, f"missing registry gate: {validator_id}"
        validator = by_id[validator_id]
        assert validator.domain == "pipeline_contracts"
        assert validator.severity.value == "blocker"


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
