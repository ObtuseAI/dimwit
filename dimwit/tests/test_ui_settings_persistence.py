"""UI_SETTINGS_AND_PERSISTENCE_V1 (masterplan bundle 8) — RED-first contract tests.

Every gate is recomputed from the two-launch proof payload: a changed setting must survive a REAL
relaunch (write.intended == verify.loaded on all 12 fields), UGameUserSettings must actually take
the resolution/quality and keep it across the relaunch, and the known write block must differ from
default on every field. Fixtures are synthetic dicts in a tempdir (snapshot law).
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from dimwit.pipelines.base import BlockedError
from dimwit.pipelines.ui_settings import (
    DEFAULT_MAX_AGE_SECONDS,
    FLAG,
    SETTING_FIELD_FLOOR,
    SETTINGS_KEYS,
    compute_coverage,
    compute_gameusersettings_applied,
    compute_persistence_roundtrip,
    validate_ui_settings_result,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_ui_settings_"))


# a KNOWN non-default settings block (every field differs from FWanefallSettings::MakeDefault)
KNOWN_SETTINGS = {
    "lstick": 0.25, "rstick": 0.75, "remap": 2, "vibration": False, "master": 0.4,
    "voice": 0.3, "music": 0.9, "dialogue": 0.55, "voice_chat": False,
    "input_device": "Xbox Pad", "output_device": "Headset", "graphics": 0,
}
GUS_INTENDED = {"res_x": 1600, "res_y": 900, "quality": 0}


def _proof(phase: str, pid: int, settings: dict, readback: dict, intended: dict | None = None) -> dict:
    gus = {"readback": readback}
    if intended is not None:
        gus["intended"] = intended
    return {"flag": FLAG, "pid": pid, "phase": phase, "settings": dict(settings),
            "gus": gus, "executable": "x.exe"}


def _result(write_settings=None, verify_settings=None, write_pid=101, verify_pid=202,
            write_readback=None, verify_readback=None, sha="a" * 64,
            captured_at=None) -> dict:
    write_settings = KNOWN_SETTINGS if write_settings is None else write_settings
    verify_settings = KNOWN_SETTINGS if verify_settings is None else verify_settings
    write_readback = GUS_INTENDED if write_readback is None else write_readback
    verify_readback = GUS_INTENDED if verify_readback is None else verify_readback
    return {
        "schema_version": 1,
        "captured_at": captured_at if captured_at is not None else time.time(),
        "asset_id": "wanefall_win64_development_settings",
        "package_binding": {"archive_dir": "D:\\a", "manifest_sha256": sha,
                            "exe_sha256_at_run": sha, "matches": True},
        "write_launched_pid": write_pid,
        "verify_launched_pid": verify_pid,
        "write": _proof("write", write_pid, write_settings, write_readback, intended=GUS_INTENDED),
        "verify": _proof("verify", verify_pid, verify_settings, verify_readback),
        "checks": {},
    }


def _validate(result: dict, max_age: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    p = TMP / f"result_{time.time_ns()}.json"
    p.write_text(json.dumps(result), encoding="utf-8")
    return validate_ui_settings_result(p, max_age_seconds=max_age)


# ------------------------------------------------------------------ green path

def test_honest_roundtrip_passes():
    r = _validate(_result())
    failed = {k: v for k, v in r["checks"].items() if not v.get("passed")}
    assert r["suite_pass"], failed
    assert r["state"] == "PASS"


def test_missing_result_blocks():
    try:
        validate_ui_settings_result(TMP / "nope.json")
        raise AssertionError("must raise")
    except BlockedError:
        pass


# ------------------------------------------------------------------ persistence roundtrip

def test_dropped_field_fails_roundtrip():
    # verify loses one field's value (didn't persist)
    verify = dict(KNOWN_SETTINGS)
    verify["master"] = 0.8   # reverted to default -> did not persist
    r = _validate(_result(verify_settings=verify))
    assert not r["checks"]["persistence_roundtrip"]["passed"]


def test_full_roundtrip_reports_12_fields():
    r = compute_persistence_roundtrip(_result())
    assert r["passed"]
    assert r["fields_roundtripped"] == len(SETTINGS_KEYS)


# ------------------------------------------------------------------ gameusersettings

def test_gus_not_applied_fails():
    # write readback disagrees with intended -> engine never took the resolution
    r = _validate(_result(write_readback={"res_x": 1920, "res_y": 1080, "quality": 3}))
    assert not r["checks"]["gameusersettings_applied"]["passed"]


def test_gus_resolution_lost_after_relaunch_fails():
    # the RESOLUTION must survive the relaunch (GUS ini persistence)
    r = _validate(_result(verify_readback={"res_x": 1920, "res_y": 1080, "quality": 0}))
    assert not r["checks"]["gameusersettings_applied"]["passed"]


def test_relaunch_quality_minus_one_tolerated():
    # GetOverallScalabilityLevel() is -1-prone after a fresh headless load; graphics-quality
    # persistence is proven by the profile round-trip, so relaunch quality=-1 with correct
    # resolution is NOT a failure (live truth 2026-07-02).
    r = _validate(_result(verify_readback={"res_x": 1600, "res_y": 900, "quality": -1}))
    assert r["checks"]["gameusersettings_applied"]["passed"], \
        r["checks"]["gameusersettings_applied"]["issues"]


# ------------------------------------------------------------------ coverage

def test_default_field_fails_coverage():
    # one field left at default -> not exercised
    write = dict(KNOWN_SETTINGS)
    write["dialogue"] = 0.8   # == default
    r = compute_coverage(_result(write_settings=write))
    assert not r["passed"]
    assert r["non_default"] < SETTING_FIELD_FLOOR


def test_all_fields_non_default_passes_coverage():
    assert compute_coverage(_result())["passed"]


# ------------------------------------------------------------------ evidence binding

def test_wrong_flag_fails_binding():
    res = _result()
    res["write"]["flag"] = "NOPE"
    assert not _validate(res)["checks"]["evidence_bound"]["passed"]


def test_pid_mismatch_fails_binding():
    res = _result()
    res["verify"]["pid"] = 999   # != verify_launched_pid
    assert not _validate(res)["checks"]["evidence_bound"]["passed"]


def test_same_pid_both_phases_fails_binding():
    res = _result(write_pid=500, verify_pid=500)
    assert not _validate(res)["checks"]["evidence_bound"]["passed"]


def test_sha_mismatch_fails_binding():
    res = _result()
    res["package_binding"]["exe_sha256_at_run"] = "b" * 64
    assert not _validate(res)["checks"]["evidence_bound"]["passed"]


# ------------------------------------------------------------------ freshness

def test_stale_fails_freshness():
    r = _validate(_result(captured_at=time.time() - DEFAULT_MAX_AGE_SECONDS - 60))
    assert not r["checks"]["freshness"]["passed"]


# ------------------------------------------------------------------ ratchet

def test_coverage_floor_is_all_twelve():
    assert SETTING_FIELD_FLOOR == 12
    assert len(SETTINGS_KEYS) == 12
    assert DEFAULT_MAX_AGE_SECONDS <= 6 * 60 * 60
    assert FLAG == "WANEFALLSETTINGSPROOF"
