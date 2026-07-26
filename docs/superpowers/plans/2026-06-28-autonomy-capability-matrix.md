# Autonomy Capability Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed autonomy capability matrix and recursive improvement queue that ranks WANEFALL repair candidates from current proof artifacts.

**Architecture:** Add a pure Python matrix builder under `dimwit/pipelines`, focused tests under `dimwit/tests`, and `autonomy_engine` validators inside the existing validation registry. The builder writes JSON artifacts and a final report; validators load or regenerate them and verify required lanes, references, queue quality, and promotion boundaries.

**Tech Stack:** Python stdlib, existing Dimwit validation harness, JSON proof artifacts, PowerShell copy/package for Shared Folder handoff.

---

### Task 1: Red Tests

**Files:**
- Create: `dimwit/tests/test_autonomy_capability_matrix.py`

- [ ] **Step 1: Write tests for matrix coverage and queue safety**

Add tests that import `build_autonomy_capability_matrix`, `external_reference_catalog`, and `validate_autonomy_report`; create temporary proof artifacts for validation, MetaHuman, real-game, contracts, handoff, and director tasks; then assert that:

- runtime blockers rank above lower-risk candidates
- required lanes are represented
- reference classifications preserve license/adoption boundaries
- every queue item has validation and rollback
- operator-only states are absent
- registry contains `autonomy_engine` validators

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m dimwit.tests.test_autonomy_capability_matrix`

Expected: FAIL because `dimwit.pipelines.autonomy_capability_matrix` does not exist yet.

### Task 2: Matrix Builder

**Files:**
- Create: `dimwit/pipelines/autonomy_capability_matrix.py`

- [ ] **Step 1: Implement artifact readers and reference catalog**

Create explicit JSON readers, timestamp helpers, source report extraction, and a hard-coded reference catalog that records license class, adoption mode, rejected concepts, and version/dependency risks.

- [ ] **Step 2: Implement capability row builders**

Derive capability rows from validation domains and known artifacts. Use real-game and MetaHuman audits for high-signal blockers, contract audit for orchestration state, handoff queue for known repair needs, and registry/domain coverage for broad subsystem presence.

- [ ] **Step 3: Implement ranked queue generation**

Convert non-pass or missing-evidence capabilities into queue candidates. Rank by severity, gameplay criticality, evidence quality, license/dependency risk, and current blockers. Always include `validation_command`, `rollback_notes`, and `promotion_threshold`.

- [ ] **Step 4: Implement artifact writing and validation helpers**

Write matrix, queue, and final report under `artifacts/autonomy`. Add `validate_autonomy_report` to enforce required lanes, ranked queue, reference classifications, action validation, rollback, and operator-only ceiling.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m dimwit.tests.test_autonomy_capability_matrix`

Expected: PASS.

### Task 3: Validation Registry

**Files:**
- Modify: `dimwit/pipelines/validation_registry.py`

- [ ] **Step 1: Add helper that loads or regenerates autonomy artifacts**

The helper calls `write_autonomy_capability_matrix(ctx.root, ctx.project, ...)`, reads the final report, and raises `BlockedError` on malformed JSON.

- [ ] **Step 2: Add six validators under `autonomy_engine`**

Register validators for freshness, lane coverage, external reference classification, ranked actions, validation/rollback commands, and operator-only promotion guard.

- [ ] **Step 3: Run focused validation**

Run: `python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue`

Expected: PASS for `autonomy_engine` only.

### Task 4: Handoff and Shared Artifacts

**Files:**
- Modify: `codex_handoff.json`
- Create or copy: Shared Folder session report and zip package

- [ ] **Step 1: Update handoff**

Add `codex_autonomy_latest` with artifact paths, validation commands, result, current top candidates, and ceiling.

- [ ] **Step 2: Copy artifacts to Shared Folder**

Copy matrix, queue, final report, design spec, implementation plan, and session report into `C:\Users\developer\Desktop\Shared Folder`.

- [ ] **Step 3: Package changed files**

Create `WANEFALL_AUTONOMY_CAPABILITY_MATRIX_V1_CODEX_PACKAGE_20260628.zip` in Shared Folder with the new/modified Dimwit files and proof artifacts.

### Task 5: Final Verification

- [ ] **Step 1: Run focused tests**

Run: `python -m dimwit.tests.test_autonomy_capability_matrix`

Expected: all tests pass.

- [ ] **Step 2: Run focused validation**

Run: `python scripts/pipeline/run_validation.py --domain autonomy_engine --no-ue`

Expected: `suite_verdict` is `PASS` for the autonomy domain.

- [ ] **Step 3: Run director validation**

Run: `python scripts/pipeline/run_director.py --validate --no-ue`

Expected: registered pipelines remain valid.

- [ ] **Step 4: Run full no-UE validation**

Run: `python scripts/pipeline/run_validation.py --no-ue`

Expected: existing non-pass blockers may remain, but `autonomy_engine` passes and no new operator-only or contract regressions are introduced.
