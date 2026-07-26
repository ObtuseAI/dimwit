"""Regression tests for packaged-build retention pruning (audit GAP-013).

D:\\WanefallBuild accumulates per-run cook/stage/archive trees (multi-GB each) with no policy -
storage exhaustion would eventually fail packaging confusingly. Pinned behavior: newest N runs are
kept, the run referenced by the CURRENT package manifest is always kept, dry-run is the default
and deletes nothing, and every pruned run leaves a tombstone manifest (fail-closed evidence trail).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.build_retention import check_retention, plan_retention, prune_packaged_runs

TMP = Path(tempfile.mkdtemp(prefix="dimwit_build_retention_"))


def _workspace(name: str, run_ids: list[str]) -> Path:
    ws = TMP / name
    for area in ("PackagedBuildValidation/runs", "CookedOutput", "Temp"):
        for run_id in run_ids:
            d = ws / area / run_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "payload.bin").write_bytes(b"x" * 128)
    return ws


def test_plan_keeps_newest_and_current_manifest_run():
    runs = ["20260628_010101", "20260629_010101", "20260630_010101", "20260701_010101", "20260701_020202"]
    ws = _workspace("plan", runs)
    manifest = TMP / "plan_manifest.json"
    manifest.write_text(json.dumps({
        "package_dir": str(ws / "PackagedBuildValidation" / "runs" / "20260628_010101" / "archive"),
    }), encoding="utf-8")

    plan = plan_retention(ws, keep_last=2, current_manifest_path=manifest)
    kept = {p["run_id"] for p in plan["kept"]}
    pruned = {p["run_id"] for p in plan["pruned"]}
    assert "20260701_020202" in kept and "20260701_010101" in kept, "newest N stay"
    assert "20260628_010101" in kept, "the run the CURRENT manifest points at is always kept"
    assert pruned == {"20260629_010101", "20260630_010101"}


def test_dry_run_deletes_nothing_and_apply_prunes_with_tombstones():
    runs = ["20260628_010101", "20260629_010101", "20260701_020202"]
    ws = _workspace("apply", runs)
    tombstones = TMP / "apply_tombstones"

    report = prune_packaged_runs(ws, keep_last=1, dry_run=True, tombstone_dir=tombstones)
    assert report["dry_run"] is True
    assert all((ws / "PackagedBuildValidation" / "runs" / r).exists() for r in runs), "dry-run must not delete"

    report = prune_packaged_runs(ws, keep_last=1, dry_run=False, tombstone_dir=tombstones)
    assert report["dry_run"] is False
    assert (ws / "PackagedBuildValidation" / "runs" / "20260701_020202").exists()
    for pruned_run in ("20260628_010101", "20260629_010101"):
        assert not (ws / "PackagedBuildValidation" / "runs" / pruned_run).exists()
        assert not (ws / "CookedOutput" / pruned_run).exists()
        tomb = tombstones / f"{pruned_run}.json"
        assert tomb.exists(), "pruned runs must leave a tombstone manifest"
        data = json.loads(tomb.read_text(encoding="utf-8"))
        assert data["run_id"] == pruned_run and data["total_bytes"] > 0


def test_keep_last_floor_is_enforced():
    ws = _workspace("floor", ["20260701_010101", "20260701_020202"])
    try:
        prune_packaged_runs(ws, keep_last=0, dry_run=True)
    except ValueError as exc:
        assert "keep_last" in str(exc)
    else:
        raise AssertionError("keep_last below the floor must refuse, never prune everything")


def test_check_passes_when_within_keep():
    ws = _workspace("check_ok", ["20260701_010101", "20260701_020202"])
    r = check_retention(ws, keep_last=3, current_manifest_path=None)
    assert r["passed"], r["issues"]
    assert r["blocked"] is False


def test_check_fails_when_over_keep():
    runs = ["20260628_010101", "20260629_010101", "20260630_010101", "20260701_010101"]
    ws = _workspace("check_over", runs)
    r = check_retention(ws, keep_last=2, current_manifest_path=None)
    assert not r["passed"]
    assert r["over_ceiling"], "runs beyond the keep set must be reported"


def test_check_blocks_when_workspace_missing():
    r = check_retention(TMP / "nope_missing_ws", keep_last=3, current_manifest_path=None)
    assert r["blocked"] is True
    assert not r["passed"]  # BLOCKED, never a silent pass


def test_check_compliant_after_prune():
    ws = _workspace("check_after", ["20260628_010101", "20260629_010101", "20260701_020202"])
    prune_packaged_runs(ws, keep_last=1, dry_run=False,
                        tombstone_dir=TMP / "after_tomb", current_manifest_path=None)
    r = check_retention(ws, keep_last=1, current_manifest_path=None)
    assert r["passed"], r["issues"]  # prune made it self-consistent


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
