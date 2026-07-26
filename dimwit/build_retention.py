"""Packaged-build retention pruning (audit GAP-013).

D:\\WanefallBuild accumulates a cook + stage + archive tree per packaging run (multi-GB each,
12 runs within the first three days) with no retention policy. This tool keeps the newest N runs
plus whichever run the CURRENT package manifest points at, and prunes the rest - leaving a
tombstone manifest (file counts/bytes per area) for every pruned run so the evidence trail stays
intact after the bytes are gone.

Fail-closed defaults: dry_run=True (reports, deletes nothing); actual deletion requires the
explicit --apply flag; keep_last has a hard floor of 1 so the tool can never empty the workspace.

  python -m dimwit.build_retention                 # dry-run report with defaults
  python -m dimwit.build_retention --keep 3 --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = Path(r"D:\WanefallBuild")
DEFAULT_MANIFEST = ROOT / "artifacts" / "packaged_build_validation" / "package_manifest.json"
DEFAULT_TOMBSTONE_DIR = ROOT / "artifacts" / "build_retention" / "pruned"
RUN_AREAS = ("PackagedBuildValidation/runs", "CookedOutput", "Temp")


import re

_RUN_ID = re.compile(r"^\d{8}_\d{6}$")   # only timestamped packaging runs are retention-managed


def _run_dirs(workspace: Path) -> dict[str, dict[str, Path]]:
    """{run_id: {area: path}} across every retention-managed area. Named capture dirs (e.g.
    EkrisCleanCapture) are NOT runs - they must neither consume keep-slots nor ever be pruned."""
    runs: dict[str, dict[str, Path]] = {}
    for area in RUN_AREAS:
        base = workspace / Path(area)
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.is_dir() and _RUN_ID.match(child.name):
                runs.setdefault(child.name, {})[area] = child
    return runs


def _current_manifest_run_id(manifest_path: Path | None) -> str | None:
    if not manifest_path or not Path(manifest_path).exists():
        return None
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    package_dir = str(manifest.get("package_dir") or "")
    parts = [p for p in Path(package_dir).parts]
    if "runs" in parts:
        idx = parts.index("runs")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _dir_stats(path: Path) -> dict:
    files = 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            files += 1
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return {"files": files, "bytes": total}


def plan_retention(workspace: Path, keep_last: int = 3,
                   current_manifest_path: Path | None = DEFAULT_MANIFEST) -> dict:
    if int(keep_last) < 1:
        raise ValueError(f"keep_last must be >= 1 (got {keep_last}); refusing to plan an empty workspace")
    workspace = Path(workspace)
    runs = _run_dirs(workspace)
    ordered = sorted(runs.keys(), reverse=True)          # timestamped names sort newest-first
    keep = set(ordered[: int(keep_last)])
    current = _current_manifest_run_id(current_manifest_path)
    if current and current in runs:
        keep.add(current)                                # the run live proofs point at is untouchable
    kept, pruned = [], []
    for run_id in ordered:
        entry = {"run_id": run_id, "areas": {area: str(path) for area, path in runs[run_id].items()},
                 "current_manifest_run": run_id == current}
        (kept if run_id in keep else pruned).append(entry)
    return {"workspace": str(workspace), "keep_last": int(keep_last),
            "current_manifest_run": current, "kept": kept, "pruned": pruned}


def prune_packaged_runs(workspace: Path = DEFAULT_WORKSPACE, keep_last: int = 3, dry_run: bool = True,
                        tombstone_dir: Path = DEFAULT_TOMBSTONE_DIR,
                        current_manifest_path: Path | None = DEFAULT_MANIFEST) -> dict:
    plan = plan_retention(workspace, keep_last=keep_last, current_manifest_path=current_manifest_path)
    report = {**plan, "dry_run": bool(dry_run), "tombstones": [], "pruned_bytes": 0, "ts": int(time.time())}
    tombstone_dir = Path(tombstone_dir)
    for entry in plan["pruned"]:
        areas = {}
        total = 0
        for area, path_str in entry["areas"].items():
            stats = _dir_stats(Path(path_str))
            areas[area] = {**stats, "path": path_str}
            total += stats["bytes"]
        tombstone = {"run_id": entry["run_id"], "areas": areas, "total_bytes": total,
                     "pruned_at": int(time.time()), "dry_run": bool(dry_run)}
        report["pruned_bytes"] += total
        if not dry_run:
            tombstone_dir.mkdir(parents=True, exist_ok=True)
            tomb_path = tombstone_dir / f"{entry['run_id']}.json"
            tomb_path.write_text(json.dumps(tombstone, indent=2), encoding="utf-8")
            report["tombstones"].append(str(tomb_path))
            for area, path_str in entry["areas"].items():
                shutil.rmtree(path_str, ignore_errors=True)
    return report


def check_retention(workspace: Path = DEFAULT_WORKSPACE, keep_last: int = 3,
                    current_manifest_path: Path | None = DEFAULT_MANIFEST) -> dict:
    """Fail-closed retention gate. BLOCKED if the workspace is unreachable (never a silent pass);
    FAIL if any managed run beyond the keep set still exists (i.e. plan_retention would prune it).
    Compliant iff the self-sustaining prune has kept the workspace bounded."""
    ws = Path(workspace)
    if not ws.exists():
        return {"passed": False, "blocked": True, "keep_last": int(keep_last),
                "issues": [f"build workspace unreachable: {ws}"]}
    plan = plan_retention(ws, keep_last=keep_last, current_manifest_path=current_manifest_path)
    over = [e["run_id"] for e in plan["pruned"]]
    issues = [f"{len(over)} packaged run(s) exceed retention (keep_last={keep_last}): {over}"] if over else []
    return {"passed": not over, "blocked": False, "keep_last": int(keep_last),
            "kept": [e["run_id"] for e in plan["kept"]], "over_ceiling": over, "issues": issues}


def _main() -> int:
    parser = argparse.ArgumentParser(description="Prune old packaged-build run trees (dry-run by default).")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--keep", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="actually delete (default is dry-run report)")
    args = parser.parse_args()
    report = prune_packaged_runs(args.workspace, keep_last=args.keep, dry_run=not args.apply)
    print(json.dumps({k: report[k] for k in ("workspace", "keep_last", "dry_run", "current_manifest_run",
                                             "pruned_bytes")}, indent=2))
    print(f"kept: {[e['run_id'] for e in report['kept']]}")
    print(f"pruned{' (dry-run, nothing deleted)' if report['dry_run'] else ''}: "
          f"{[e['run_id'] for e in report['pruned']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
