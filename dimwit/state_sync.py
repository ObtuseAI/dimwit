"""State truth sync (bundle: WANEFALL_STATE_TRUTH_SYNC_V1).

Keeps the human/driver-facing state files consistent with disk truth so a baton pass never starts
from a stale claim. Audit 2026-07-01 found codex_handoff.json asserting a green 173-validator suite
and 7 active humanoids while the disk truth was a REJECTED 162-validator suite and 6 humanoids, and
found the builder/autonomy meta-artifacts regenerating mid-suite from domain-scoped reports.

Two primitives live here:

- load_validation_report_with_provenance(root): the ONE way meta-artifact generators should read
  suite truth. Prefers artifacts/validation/validation_report_full.json (written only by full-scope
  suite runs) over the mutable validation_report.json (rewritten by every domain-scoped run), and
  returns a provenance stamp generators must embed in what they write.

- sync_state_truth(root, project): regenerates the handoff's `generated_truth` block and its
  human-facing `registry` line from the latest FULL report + roster + queue. Fail-closed: refuses
  to run without a full report rather than fabricating truth. Doctrine fields are never touched.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

FULL_REPORT_REL = Path("artifacts") / "validation" / "validation_report_full.json"
LATEST_REPORT_REL = Path("artifacts") / "validation" / "validation_report.json"
QUEUE_REL = Path("artifacts") / "autonomy" / "recursive_improvement_queue.json"
ROSTER_REL = Path("config") / "character_roster.json"
HANDOFF_REL = Path("codex_handoff.json")
SUMMARY_REL = Path("artifacts") / "state_sync" / "state_truth_sync.json"


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root is not an object")
    return data


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_validation_report_with_provenance(root: Path) -> tuple[dict, dict]:
    """Load suite truth for meta-artifact generation, preferring the latest FULL-scope report.

    Returns (report, provenance). Falls back to the mutable latest report only when no full report
    exists yet (bootstrap) — the provenance stamp makes that visible instead of silent.
    """
    root = Path(root)
    full_path = root / FULL_REPORT_REL
    latest_path = root / LATEST_REPORT_REL
    used_full = full_path.exists()
    path = full_path if used_full else latest_path
    report = _read_json(path) if path.exists() else {}
    provenance = {
        "path": str(path.relative_to(root)) if path.exists() else None,
        "used_full_report": used_full,
        "run_ts": report.get("run_ts"),
        "scope": report.get("scope"),
        "run_ue": report.get("run_ue"),
        "suite_verdict": report.get("suite_verdict"),
    }
    return report, provenance


def mirror_queue_to_project(queue_path: Path, project: Path) -> dict:
    """Byte-identical mirror of the recursive improvement queue into the WANEFALL Config copy.

    Called by the SAME writer that regenerates the queue (write_autonomy_capability_matrix) so the
    two files can never drift within a run — an end-of-suite copy would always lag the mid-suite
    regeneration and trip the parity gate."""
    queue_path = Path(queue_path)
    dst = Path(project) / "Config" / "WANEFALL_AutonomyQueue" / "recursive_improvement_queue.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = queue_path.read_bytes()
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)
    return {"src": str(queue_path), "dst": str(dst), "bytes": len(data)}


def sync_state_truth(root: Path, project: Path) -> dict:
    """Regenerate handoff truth from disk. Raises FileNotFoundError when no full-suite report exists."""
    root, project = Path(root), Path(project)
    full_path = root / FULL_REPORT_REL
    if not full_path.exists():
        raise FileNotFoundError(f"validation_report_full.json missing ({full_path}); "
                                "run a full-scope suite before syncing state truth")
    report = _read_json(full_path)
    roster = _read_json(root / ROSTER_REL) if (root / ROSTER_REL).exists() else {}
    queue_doc = _read_json(root / QUEUE_REL) if (root / QUEUE_REL).exists() else {}
    queue_entries = queue_doc.get("recursive_improvement_queue") or []

    counts = report.get("counts") or {}
    by_domain = report.get("by_domain") or {}
    truth = {
        "generated_at": time.time(),
        "source_report": {
            "path": str(FULL_REPORT_REL).replace("\\", "/"),
            "run_ts": report.get("run_ts"),
            "scope": report.get("scope"),
            "run_ue": report.get("run_ue"),
        },
        "suite_verdict": report.get("suite_verdict"),
        "counts": counts,
        "total_validators": report.get("total"),
        "domain_count": len(by_domain),
        "active_humanoid_target": roster.get("active_humanoid_target"),
        "active_mech_target": roster.get("active_mech_target"),
        "quarantined_humanoids": sorted((roster.get("quarantined_humanoids") or {}).keys()),
        "next_lane": roster.get("next_lane"),
        "queue_top": [str(item.get("title")) for item in queue_entries[:5]],
        "note": "machine-generated from disk truth at the end of every full-scope suite run; "
                "validator totals vary with the active roster",
    }

    handoff_path = root / HANDOFF_REL
    handoff = _read_json(handoff_path) if handoff_path.exists() else {}
    handoff["generated_truth"] = truth
    ue_desc = "with UE probes" if report.get("run_ue") else "no-UE (UE/eyes validators blocked)"
    handoff["registry"] = (
        f"{report.get('total')} validators across {len(by_domain)} domains; latest full suite "
        f"{report.get('suite_verdict')} (PASS {counts.get('PASS', 0)} / FAIL {counts.get('FAIL', 0)} / "
        f"BLOCKED {counts.get('BLOCKED', 0)} / REJECTED {counts.get('REJECTED', 0)}) at run_ts "
        f"{report.get('run_ts')} ({ue_desc}); validator count varies with the active roster; "
        "validate via `python scripts/pipeline/run_validation.py`"
    )
    _write_json_atomic(handoff_path, handoff)

    summary = {"ok": True, "generated_at": truth["generated_at"], "truth": truth,
               "handoff_path": str(handoff_path)}
    _write_json_atomic(root / SUMMARY_REL, summary)
    return summary


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Sync codex_handoff truth block from disk state.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--project", type=Path,
                        default=Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox"))
    args = parser.parse_args()
    summary = sync_state_truth(args.root, args.project)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
