# Real Game Validation Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Dimwit pipeline and validation-registry gates that prove WANEFALL against the actual running game window.

**Architecture:** Implement a focused `real_game_validation` production pipeline that launches or attaches to WANEFALL, captures the real desktop window, computes deterministic image/log checks, writes a result artifact, and stops at `PROMOTED_TO_REVIEW`. The global validation registry consumes that artifact through fail-closed blockers so every autonomous build loop can depend on real-game evidence.

**Tech Stack:** Python stdlib, Pillow, existing `dimwit.desktop_eyes`, existing `dimwit.pipelines.base`, existing `scripts/pipeline/run_pipeline.py`, existing `scripts/pipeline/run_validation.py`.

---

## File Structure

- Create `C:\Users\developer\Documents\Dimwit\dimwit\tests\test_real_game_validation.py`
  - Self-contained tests for image checks, log checks, freshness checks, and validator behavior.
- Create `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\real_game_validation.py`
  - Pipeline class plus pure helpers for image metrics, nonblank verdicts, log scan, launch/capture orchestration, result writing, and report writing.
- Modify `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\__init__.py`
  - Register `real_game_validation`.
- Modify `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\validation_registry.py`
  - Add `real_game_runtime` validators that consume `artifacts/real_game_validation/real_game_validation_result.json`.
- Modify `C:\Users\developer\Documents\Dimwit\config\director_tasks.json`
  - Add one high-priority real-game validation task.
- Create or update `C:\Users\developer\Desktop\Shared Folder\WANEFALL_REAL_GAME_VALIDATION_LOOP_V1_SESSION_REPORT_20260628.md`
  - Shared Folder session handoff.

No git commit is created because the local `AGENTS.md` says commits require explicit user request and these folders are not git repos.

## Task 1: RED Tests For Pure Validation Helpers

**Files:**
- Create: `C:\Users\developer\Documents\Dimwit\dimwit\tests\test_real_game_validation.py`
- Test: `python -m dimwit.tests.test_real_game_validation`

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.real_game_validation import (
    analyze_capture,
    check_result_fresh,
    scan_log_text,
    validate_real_game_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_realgame_"))


def _solid(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (160, 100), color).save(path)
    return path


def _contrast(path: Path) -> Path:
    image = Image.new("RGB", (160, 100), (20, 22, 25))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 20, 110, 80], fill=(51, 204, 204))
    draw.rectangle([72, 40, 88, 56], fill=(240, 120, 25))
    image.save(path)
    return path


def test_blank_capture_is_rejected():
    result = analyze_capture(_solid(TMP / "blank.png", (255, 255, 255)))
    assert result["passed"] is False
    assert "contrast" in "; ".join(result["issues"])


def test_high_contrast_capture_passes():
    result = analyze_capture(_contrast(TMP / "contrast.png"))
    assert result["passed"] is True
    assert result["metrics"]["contrast"] >= 0.05
    assert result["metrics"]["mean_luminance"] >= 0.05


def test_log_scan_counts_fatal_error_lines():
    scan = scan_log_text("LogTemp: Display: ok\nFatal error: boom\nError: missing asset\n")
    assert scan["fatal_count"] == 1
    assert scan["error_count"] == 1
    assert scan["passed"] is False


def test_fresh_result_passes_and_stale_blocks():
    fresh = {"captured_at": time.time(), "suite_pass": True, "checks": {"still_nonblank": {"passed": True}}}
    assert check_result_fresh(fresh, max_age_seconds=60)["passed"] is True
    stale = {"captured_at": time.time() - 7200, "suite_pass": True, "checks": {}}
    assert check_result_fresh(stale, max_age_seconds=60)["passed"] is False


def test_validate_real_game_result_blocks_missing_file():
    try:
        validate_real_game_result(TMP / "missing.json", max_age_seconds=60)
    except BlockedError as exc:
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("missing result must block")


def test_validate_real_game_result_passes_complete_file():
    path = TMP / "result.json"
    path.write_text(json.dumps({
        "captured_at": time.time(),
        "suite_pass": True,
        "checks": {
            "window_found": {"passed": True},
            "still_nonblank": {"passed": True},
            "log_scan": {"passed": True, "fatal_count": 0, "error_count": 0},
        },
    }), encoding="utf-8")
    result = validate_real_game_result(path, max_age_seconds=60)
    assert result["suite_pass"] is True


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

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m dimwit.tests.test_real_game_validation`

Expected: FAIL with `ModuleNotFoundError: No module named 'dimwit.pipelines.real_game_validation'`.

## Task 2: Implement Real-Game Pipeline Helpers

**Files:**
- Create: `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\real_game_validation.py`
- Test: `python -m dimwit.tests.test_real_game_validation`

- [ ] **Step 1: Write minimal helper implementation**

Implement these public helpers:

```python
analyze_capture(path: Path) -> dict
scan_log_text(text: str) -> dict
check_result_fresh(result: dict, max_age_seconds: int) -> dict
validate_real_game_result(path: Path, max_age_seconds: int) -> dict
```

Rules:

- missing image raises `BlockedError`
- blank/low-contrast image returns `passed=False`
- fatal/error log lines return `passed=False`
- stale result returns `passed=False`
- missing result raises `BlockedError`

- [ ] **Step 2: Run test to verify helpers pass**

Run: `python -m dimwit.tests.test_real_game_validation`

Expected: `6/6 passed`.

## Task 3: Implement Pipeline Class

**Files:**
- Modify: `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\real_game_validation.py`
- Test: `python scripts/pipeline/run_pipeline.py real_game_validation wanefall_default_lobby attach_only=true max_wait_seconds=2`

- [ ] **Step 1: Add `RealGameValidationPipeline`**

Class contract:

```python
class RealGameValidationPipeline(ProductionPipeline):
    name = "real_game_validation"
    kind = "runtime_validation"
```

`plan(task)` resolves:

- `project`
- `ue_exe`
- `map_url`
- `window_title`
- `attach_only`
- `kill_stale`
- `max_wait_seconds`
- output directory

`execute(plan)`:

- finds or launches the game window
- captures still and frame burst through `DesktopEyes`
- scans newest logs under `WanefallGreybox\Saved\Logs`
- writes `real_game_validation_result.json`
- writes `WANEFALL_REAL_GAME_VALIDATION_LOOP_V1_SESSION_REPORT_20260628.md`
- returns an `Artifact` with local-project provenance

`qa(artifact, plan)`:

- promotes only if result `suite_pass` is true
- returns `REJECTED` for captured but blank/fatal evidence
- returns `BLOCKED` for missing environment through plan/execute failures

- [ ] **Step 2: Run attach-only smoke to verify honest blocker**

Run: `python scripts/pipeline/run_pipeline.py real_game_validation wanefall_default_lobby attach_only=true max_wait_seconds=2`

Expected when no game window is open: JSON result with state `State.BLOCKED` or `State.NEEDS_RECURSION`, never `PROMOTED_TO_REVIEW`.

## Task 4: Register Pipeline And Director Task

**Files:**
- Modify: `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\__init__.py`
- Modify: `C:\Users\developer\Documents\Dimwit\config\director_tasks.json`
- Test: `python scripts/pipeline/run_pipeline.py --list`

- [ ] **Step 1: Register pipeline**

Add:

```python
"real_game_validation": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline",
```

- [ ] **Step 2: Add director task**

Add a first task:

```json
{"pipeline": "real_game_validation", "asset_id": "wanefall_default_lobby", "priority": 10, "cost": 1, "expected_value": 4}
```

- [ ] **Step 3: Run list check**

Run: `python scripts/pipeline/run_pipeline.py --list`

Expected: output includes `"real_game_validation"`.

## Task 5: Add Validation Registry Gates

**Files:**
- Modify: `C:\Users\developer\Documents\Dimwit\dimwit\pipelines\validation_registry.py`
- Test: `python scripts/pipeline/run_validation.py --domain real_game_runtime --no-ue`

- [ ] **Step 1: Add registry loader/helper**

Add helpers near the other filesystem-backed validator helpers:

```python
def _real_game_result(ctx):
    from dimwit.pipelines.real_game_validation import validate_real_game_result
    return validate_real_game_result(ROOT / "artifacts" / "real_game_validation" / "real_game_validation_result.json")
```

- [ ] **Step 2: Add validators**

Add domain `real_game_runtime` with:

- `real_game_capture_fresh`
- `real_game_window_nonblank`
- `real_game_no_fatal_log_burst`
- `real_game_runtime_not_placeholder_dominated`

Each validator reads the same result JSON and fails closed.

- [ ] **Step 3: Verify domain is registered**

Run: `python scripts/pipeline/run_validation.py --domain real_game_runtime --no-ue`

Expected before live capture: `BLOCKED` if no result exists, or `PASS/FAIL` matching the current result. Exit code may be `1` if blockers exist; that is honest.

## Task 6: Live Real-Game Run

**Files:**
- Produced: `C:\Users\developer\Documents\Dimwit\artifacts\real_game_validation\real_game_validation_result.json`
- Produced: `C:\Users\developer\Documents\Dimwit\artifacts\real_game_validation\still.png`
- Produced: `C:\Users\developer\Documents\Dimwit\artifacts\real_game_validation\frames\*.png`
- Produced: `C:\Users\developer\Desktop\Shared Folder\WANEFALL_REAL_GAME_VALIDATION_LOOP_V1_SESSION_REPORT_20260628.md`

- [ ] **Step 1: Run real-game pipeline**

Run:

`python scripts/pipeline/run_pipeline.py real_game_validation wanefall_default_lobby max_wait_seconds=90 capture_seconds=2 capture_fps=4`

Expected:

- PASS/promoted if the machine launches and captures a good game frame.
- BLOCKED if Unreal cannot launch or a game window cannot be captured.
- REJECTED if the window is captured but blank/fatal/error-dominated.

- [ ] **Step 2: Run focused validation domain**

Run: `python scripts/pipeline/run_validation.py --domain real_game_runtime --no-ue`

Expected: real-game runtime validators report the pipeline result honestly.

- [ ] **Step 3: Run no-UE pipeline self-check**

Run: `python scripts/pipeline/run_director.py --validate --no-ue`

Expected: JSON output. Full PASS is not required because the existing suite has known fail-closed blockers, but the command must not crash from the new pipeline wiring.

## Self-Review Checklist

- The plan implements the approved design's V1 scope.
- The plan starts with failing tests before helper implementation.
- The plan does not weaken validators, thresholds, or operator-only states.
- The plan uses existing `ProductionPipeline` and `DesktopEyes` patterns.
- The plan writes Shared Folder handoff output.
- The plan avoids commits because local instructions and repo state disallow them.
