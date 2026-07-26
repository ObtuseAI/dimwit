# Cross-Pipeline Contract Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline contract auditor that hardens every registered Dimwit pipeline and exposes the result through the fail-closed validation suite.

**Architecture:** Add `dimwit/pipelines/contract_auditor.py` as a pure structural auditor over the pipeline registry, manifest, director task config, ledger consistency, and operator-only source writes. Add focused tests and register new `pipeline_contracts` validators that consume `artifacts/pipeline_contracts/pipeline_contract_audit.json`.

**Tech Stack:** Python stdlib, existing Dimwit pipeline registry, existing `ValidationSuite`/`Validator` framework, JSON artifacts.

---

### Task 1: Add Failing Contract Auditor Tests

**Files:**
- Create: `dimwit/tests/test_pipeline_contract_auditor.py`

- [ ] **Step 1: Write tests for the desired API**

```python
from __future__ import annotations

import json
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
        registry={"known": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline",
                  "missing": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline"},
        manifest=manifest,
        director_tasks={"tasks": [{"pipeline": "known", "asset_id": "asset", "priority": 1, "cost": 1, "expected_value": 1}]},
    )
    parity = report["checks"]["manifest_parity"]
    assert parity["passed"] is False
    assert "missing" in parity["missing_from_manifest"]


def test_director_task_validation_catches_unknown_pipeline():
    report = audit_registered_pipelines(
        Path.cwd(),
        registry={"known": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline"},
        manifest={"pipelines": {"known": {"module": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline"}}},
        director_tasks={"tasks": [{"pipeline": "ghost", "asset_id": "asset", "priority": 1, "cost": 1, "expected_value": 1}]},
    )
    director = report["checks"]["director_tasks"]
    assert director["passed"] is False
    assert "ghost" in director["unknown_pipelines"]


def test_operator_only_scan_ignores_comments_and_boundary_strings_but_rejects_writes():
    source = TMP / "operator_state_probe.py"
    source.write_text(
        "# HUMAN_ACCEPTED appears in a comment\n"
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
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m dimwit.tests.test_pipeline_contract_auditor`

Expected: import failure because `dimwit.pipelines.contract_auditor` does not exist.

### Task 2: Implement the Auditor Module

**Files:**
- Create: `dimwit/pipelines/contract_auditor.py`

- [ ] **Step 1: Implement report generation**

Create pure helpers that import registered classes, instantiate them, inspect hook ownership, validate name/kind/threshold/max_repairs/ledger, load config JSON, compare registry to manifest, validate director tasks, and scan source files.

- [ ] **Step 2: Run focused tests**

Run: `python -m dimwit.tests.test_pipeline_contract_auditor`

Expected: all tests pass except registry gate presence until Task 3 is complete.

### Task 3: Add Validation Registry Gates

**Files:**
- Modify: `dimwit/pipelines/validation_registry.py`

- [ ] **Step 1: Add helper to load or create audit report**

The helper must call the auditor if the JSON is missing, then read `artifacts/pipeline_contracts/pipeline_contract_audit.json`. Missing or unreadable result raises `BlockedError`.

- [ ] **Step 2: Add validators**

Register five blockers under domain `pipeline_contracts`:

- `pipeline_contract_audit_fresh`
- `pipeline_contract_registry_clean`
- `pipeline_contract_manifest_parity`
- `pipeline_contract_director_tasks_known`
- `pipeline_contract_no_operator_only_writes`

- [ ] **Step 3: Run focused tests**

Run: `python -m dimwit.tests.test_pipeline_contract_auditor`

Expected: all tests pass.

### Task 4: Run Auditor and Fix First Real Contract Drift

**Files:**
- Modify only drifted config/docs if the auditor exposes real contract gaps.

- [ ] **Step 1: Run auditor through validation**

Run: `python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue`

Expected: either PASS or explicit blockers.

- [ ] **Step 2: Fix real drift with minimal edits**

If `production_pipelines.json` is missing `real_game_validation`, add that manifest entry. If director task fields are absent, fill only the missing fields.

- [ ] **Step 3: Re-run validation**

Run: `python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue`

Expected: PASS for the pipeline contract domain.

### Task 5: Final Verification and Handoff

**Files:**
- Copy artifacts to `C:\Users\developer\Desktop\Shared Folder`
- Update: `codex_handoff.json`

- [ ] **Step 1: Run verification commands**

Run:

```powershell
python -m dimwit.tests.test_pipeline_contract_auditor
python -m dimwit.tests.test_real_game_validation
python scripts/pipeline/run_director.py --validate --no-ue
python scripts/pipeline/run_validation.py --domain pipeline_contracts --no-ue
python scripts/pipeline/run_validation.py --no-ue
```

- [ ] **Step 2: Mirror outputs**

Copy the spec, plan, audit JSON, session report, and changed source files into the Shared Folder.

- [ ] **Step 3: Update handoff**

Record the contract auditor state, latest validation result, and remaining blockers in `codex_handoff.json`.
