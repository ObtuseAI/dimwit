# MetaHuman Character Utilization Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that WANEFALL’s existing 3D character assets are routed into a MetaHuman-compatible transformation lane, and block honestly until actual MetaHuman output evidence exists.

**Architecture:** Add a pure offline Dimwit auditor for MetaHuman utilization evidence, then expose it through a new validation domain. The auditor reads project config, Dimwit character artifacts, engine plugin layout, and local content paths without launching Unreal or copying external code.

**Tech Stack:** Python stdlib, Dimwit validation registry, existing WANEFALL/Dimwit artifacts, PowerShell validation wrapper.

---

### Task 1: RED Tests

**Files:**
- Create: `dimwit/tests/test_metahuman_utilization.py`

- [ ] **Step 1: Add tests**

Tests must verify:

- UE `5.8` classifies direct DNA Calibration use as `BLOCKED_UNREAL_VERSION`.
- The audit detects all expected source 3D character assets when fake fixture files are present.
- Missing MetaHuman output evidence classifies the report as `PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT`.
- External reference decisions record Character DNA Addon as GPL/reference-only and Epic DNA Calibration as official/version-gated.
- The validation registry contains the five `metahuman_character_pipeline` gates.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m dimwit.tests.test_metahuman_utilization`

Expected: import failure because `dimwit.pipelines.metahuman_utilization` does not exist.

### Task 2: Auditor Module

**Files:**
- Create: `dimwit/pipelines/metahuman_utilization.py`

- [ ] **Step 1: Implement pure helpers**

Implement engine version parsing, DNA Calibration support classification, project plugin detection, engine MetaHuman plugin detection, character source evidence collection, external reference ledger generation, and output-evidence detection.

- [ ] **Step 2: Implement report writer**

Write `artifacts/metahuman_utilization/metahuman_utilization_audit.json`.

- [ ] **Step 3: Run focused tests**

Run: `python -m dimwit.tests.test_metahuman_utilization`

Expected: all tests pass except registry-gate presence until Task 3.

### Task 3: Validation Registry Gates

**Files:**
- Modify: `dimwit/pipelines/validation_registry.py`

- [ ] **Step 1: Add loader**

Regenerate the MetaHuman utilization audit on each validation run and load the JSON artifact.

- [ ] **Step 2: Add validators**

Register:

- `metahuman_audit_fresh`
- `metahuman_source_3d_assets_ready`
- `metahuman_version_gate_respected`
- `metahuman_license_boundaries_clean`
- `metahuman_transform_output_evidence_present`

The output-evidence validator raises `BlockedError` when no real MetaHuman outputs exist.

- [ ] **Step 3: Re-run focused tests**

Run: `python -m dimwit.tests.test_metahuman_utilization`

Expected: all tests pass.

### Task 4: Docs and Wrapper

**Files:**
- Create: `C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\docs\WANEFALL_CHARACTER_PIPELINE_REFERENCE_LEDGER.md`
- Create: `C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\docs\WANEFALL_METAHUMAN_CALIBRATION_CHECKLIST.md`
- Create: `C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\Scripts\WANEFALL\Validate-MetaHumanCalibrationGate.ps1`

- [ ] **Step 1: Add license/version docs**

Record GPL/reference-only, Epic official/version-gated, UE 5.8 route, no copied GPL code, no redistributed Epic tooling.

- [ ] **Step 2: Add wrapper**

The wrapper runs `python scripts/pipeline/run_validation.py --domain metahuman_character_pipeline --no-ue` from the Dimwit directory.

### Task 5: Verification and Handoff

**Files:**
- Update: `codex_handoff.json`
- Copy artifacts to `C:\Users\developer\Desktop\Shared Folder`

- [ ] **Step 1: Run verification**

Run:

```powershell
python -m dimwit.tests.test_metahuman_utilization
python scripts/pipeline/run_validation.py --domain metahuman_character_pipeline --no-ue
python scripts/pipeline/run_director.py --validate --no-ue
```

- [ ] **Step 2: Run broader context check**

Run: `python scripts/pipeline/run_validation.py --no-ue`

Expected: overall suite may remain non-pass due existing blockers; `metahuman_character_pipeline` should show source/version/license PASS and output evidence BLOCKED until real MetaHuman output exists.

- [ ] **Step 3: Mirror handoff**

Copy spec, plan, audit JSON, docs, wrapper, source files, and report into the Shared Folder.
