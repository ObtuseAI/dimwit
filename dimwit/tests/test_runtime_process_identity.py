"""Regression tests for runtime-capture process identity (bundle: RUNTIME_PROCESS_IDENTITY_GATE_V1).

Audit finding 2026-07-01: packaged/runtime captures matched windows by title substring with
proc=None and a tautological runtime_source check, so a stale editor-game window could in
principle satisfy the flagship packaged proof; real_game_validation also never terminated the
processes it launched. These tests pin the required behavior: captures must be provably bound
to the launched process (fail-closed when unprovable), and launched game processes are cleaned up.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from dimwit.desktop_eyes import process_identity_check
from dimwit.pipelines.packaged_build_validation import validate_packaged_build_result
from dimwit.pipelines.real_game_validation import RealGameValidationPipeline

TMP = Path(tempfile.mkdtemp(prefix="dimwit_process_identity_"))


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_process_identity_check_binds_capture_to_launched_pid():
    good = {"ok": True, "tier": "printwindow", "pid": 4321, "proc": "WanefallGreybox", "matches": 1}
    verdict = process_identity_check(good, expected_pid=4321, expected_proc="WanefallGreybox")
    assert verdict["passed"] is True, verdict
    assert verdict["captured_pid"] == 4321

    wrong_pid = dict(good, pid=9999)
    verdict = process_identity_check(wrong_pid, expected_pid=4321, expected_proc="WanefallGreybox")
    assert verdict["passed"] is False
    assert any("pid" in issue.lower() for issue in verdict["issues"])

    wrong_proc = dict(good, proc="UnrealEditor")
    verdict = process_identity_check(wrong_proc, expected_pid=4321, expected_proc="WanefallGreybox")
    assert verdict["passed"] is False


def test_process_identity_check_fails_closed_without_pid_evidence():
    # region-grab fallback carries no pid: identity is unprovable -> must fail, never pass silently
    region = {"ok": True, "tier": "region", "window_title": "WanefallGreybox"}
    verdict = process_identity_check(region, expected_pid=4321, expected_proc="WanefallGreybox")
    assert verdict["passed"] is False
    assert any("pid" in issue.lower() for issue in verdict["issues"])


def test_process_identity_check_attach_mode_requires_proc_name():
    # attach mode (no launched pid): the captured window must still belong to the expected process
    attached = {"ok": True, "tier": "printwindow", "pid": 777, "proc": "UnrealEditor", "matches": 1}
    verdict = process_identity_check(attached, expected_pid=None, expected_proc="UnrealEditor")
    assert verdict["passed"] is True, verdict

    foreign = dict(attached, proc="chrome")
    verdict = process_identity_check(foreign, expected_pid=None, expected_proc="UnrealEditor")
    assert verdict["passed"] is False


def _packaged_fixture_checks() -> dict:
    return {
        "package_manifest": {"passed": True, "issues": []},
        "executable_hash": {"passed": True, "issues": []},
        "window_found": {"passed": True, "issues": []},
        "still_nonblank": {"passed": True, "issues": []},
        "frame_burst_nonblank": {"passed": True, "issues": []},
        "packaged_log_scan": {"passed": True, "issues": []},
    }


def test_validate_packaged_build_result_requires_process_identity_check():
    result_path = _write_json(TMP / "no_identity_result.json", {
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "packaged_build",
        "checks": _packaged_fixture_checks(),      # note: no process_identity
    })
    result = validate_packaged_build_result(result_path, max_age_seconds=60)
    assert result["suite_pass"] is False, "identity-free packaged evidence must not pass"
    assert result["checks"]["process_identity"]["passed"] is False


def test_validate_packaged_build_result_rejects_failed_process_identity():
    checks = _packaged_fixture_checks()
    checks["process_identity"] = {"passed": False, "issues": ["captured window pid 111 != launched pid 222"],
                                  "captured_pid": 111, "expected_pid": 222}
    result_path = _write_json(TMP / "wrong_pid_result.json", {
        "captured_at": time.time(),
        "state": "PASS",
        "suite_pass": True,
        "runtime_source": "packaged_build",
        "checks": checks,
    })
    result = validate_packaged_build_result(result_path, max_age_seconds=60)
    assert result["suite_pass"] is False


class _FakeProc:
    def __init__(self, alive: bool = True):
        self._alive = alive
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
        self._alive = False


def test_real_game_pipeline_terminates_launched_process():
    pipeline = RealGameValidationPipeline()
    fake = _FakeProc(alive=True)
    pipeline._terminate_process(fake)
    assert fake.terminated is True

    pipeline._terminate_process(None)              # no-op, must not raise
    already_dead = _FakeProc(alive=False)
    pipeline._terminate_process(already_dead)      # no-op on exited process
    assert already_dead.terminated is False


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
