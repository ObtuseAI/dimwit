# Packaged Build Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add autonomous WANEFALL packaged-build proof, packaged runtime smoke evidence, and recursive queue sync so release-style readiness requires a real package artifact.

**Architecture:** Add a dedicated `packaged_build_validation` Dimwit pipeline that runs Unreal UAT `BuildCookRun`, stages/archives a Win64 Development package, computes file count/size/hash evidence, launches the packaged executable, captures a desktop still/frame burst, scans packaged logs, and writes fail-closed JSON/report artifacts. Add validator gates under a new `packaged_build` domain, register the pipeline in the manifest/director, and map the new domain into the autonomy and Unreal game-builder queues.

**Tech Stack:** Python stdlib, Dimwit `ProductionPipeline`, Unreal `RunUAT.bat`, existing `DesktopEyes` capture helpers, existing validation registry and pipeline contract auditor.

---

### Task 1: Test Packaged Build Contracts

**Files:**
- Create: `dimwit/tests/test_packaged_build_validation.py`

- [ ] Write tests for package result validation, manifest hash/size requirements, packaged smoke checks, registry/manifest/director registration, and builder/autonomy queue sync.
- [ ] Run `python -m dimwit.tests.test_packaged_build_validation` and confirm the tests fail because the pipeline does not exist yet.

### Task 2: Implement Packaged Build Pipeline

**Files:**
- Create: `dimwit/pipelines/packaged_build_validation.py`
- Modify: `dimwit/pipelines/__init__.py`
- Modify: `config/production_pipelines.json`
- Modify: `config/director_tasks.json`

- [ ] Implement `PackagedBuildValidationPipeline` with plan, UAT execution, manifest generation, packaged executable launch/capture/log scan, report writing, and QA.
- [ ] Register the pipeline and director task.
- [ ] Run `python -m dimwit.tests.test_packaged_build_validation` and confirm it passes.

### Task 3: Add Fail-Closed Validation Gates

**Files:**
- Modify: `dimwit/pipelines/validation_registry.py`

- [ ] Add `packaged_build` validators for fresh package result, package artifact manifest, executable/hash evidence, packaged runtime smoke, packaged log scan, and queue sync.
- [ ] Run `python scripts/pipeline/run_validation.py --domain packaged_build --no-ue` and confirm it blocks until real package evidence exists.

### Task 4: Sync Recursive Queues

**Files:**
- Modify: `dimwit/pipelines/autonomy_capability_matrix.py`
- Modify: `dimwit/pipelines/unreal_game_builder_engine.py`

- [ ] Map `packaged_build` into the autonomy `build_packaging` lane and Unreal builder `build_packaging_deploy` lane.
- [ ] Require packaged proof as a source truth and queue input.
- [ ] Run autonomy and builder tests.

### Task 5: Run Real Package And Smoke

**Files/Artifacts:**
- Create: `artifacts/packaged_build_validation/packaged_build_result.json`
- Create: `artifacts/packaged_build_validation/package_manifest.json`
- Create: `artifacts/packaged_build_validation/still.png`
- Create: `artifacts/packaged_build_validation/frames/*.png`
- Create: `artifacts/packaged_build_validation/WANEFALL_PACKAGED_BUILD_PROOF_REPORT_20260629.md`

- [ ] Run `python scripts/pipeline/run_pipeline.py packaged_build_validation wanefall_win64_development timeout_seconds=3600`.
- [ ] Run `python scripts/pipeline/run_validation.py --domain packaged_build --no-ue`.
- [ ] Run `python scripts/pipeline/run_validation.py`.
- [ ] Copy the report/package summary to `C:\Users\developer\Desktop\Shared Folder`.

