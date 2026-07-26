"""Fail-closed comparison of two real engine-build receipts for one production brief."""
from __future__ import annotations

import json
from pathlib import Path

from dimwit.toolchains.common import atomic_json, require_within, sha256_file, sha256_tree


REVIEW_CEILING = "PROMOTED_TO_REVIEW"
ROOT = Path(__file__).resolve().parents[3]


def _receipt(path: Path) -> tuple[dict, list[str]]:
    issues: list[str] = []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return {}, [f"receipt unreadable: {path}: {type(exc).__name__}"]
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    engine = str(plan.get("engine") or "")
    if payload.get("state") != "PASS" or payload.get("ok") is not True:
        issues.append(f"{engine or path.name}: build receipt is not PASS")
    if payload.get("review_ceiling") != REVIEW_CEILING:
        issues.append(f"{engine or path.name}: review ceiling mismatch")
    if not engine:
        issues.append(f"{path.name}: engine missing")
    proofs = payload.get("output_proofs") if isinstance(payload.get("output_proofs"), list) else []
    if not proofs:
        issues.append(f"{engine or path.name}: no output proofs")
    for proof in proofs:
        output = Path(str(proof.get("path") or ""))
        actual_hash = sha256_tree(output)
        if not proof.get("exists") or int(proof.get("bytes") or 0) <= 0 or not actual_hash:
            issues.append(f"{engine or path.name}: proof output missing or empty: {output}")
        elif actual_hash != proof.get("sha256"):
            issues.append(f"{engine or path.name}: proof hash mismatch: {output}")
    return payload, issues


def compare_build_receipts(brief: str | Path, receipts: list[str | Path], output: str | Path | None = None,
                           *, allowed_output_roots: list[Path] | None = None) -> dict:
    brief_path = Path(brief).resolve()
    brief_hash = sha256_file(brief_path)
    issues = [] if brief_hash else [f"production brief missing or empty: {brief_path}"]
    if len(receipts) != 2:
        issues.append("exactly two build receipts are required")
    rows = []
    for receipt_path in receipts[:2]:
        payload, row_issues = _receipt(Path(receipt_path).resolve())
        issues.extend(row_issues)
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
        if brief_hash and metadata.get("brief_sha256") != brief_hash:
            issues.append(f"{plan.get('engine') or receipt_path}: receipt is not bound to the supplied brief")
        rows.append({
            "engine": plan.get("engine"), "target": plan.get("target"),
            "profile": plan.get("profile"), "receipt": str(Path(receipt_path).resolve()),
            "proof_count": len(payload.get("output_proofs") or []),
            "proof_bytes": sum(int(item.get("bytes") or 0) for item in payload.get("output_proofs") or []),
        })
    engines = {row.get("engine") for row in rows if row.get("engine")}
    targets = {row.get("target") for row in rows if row.get("target")}
    if len(engines) != 2:
        issues.append("receipts must come from two distinct engines")
    if len(targets) != 1:
        issues.append("receipts must target the same platform for a comparable proof")
    report = {
        "schema_version": 1,
        "state": "PASS" if not issues else "BLOCKED",
        "brief": str(brief_path),
        "brief_sha256": brief_hash,
        "builds": rows,
        "engines": sorted(engines),
        "target": next(iter(targets)) if len(targets) == 1 else None,
        "comparable": not issues,
        "issues": issues,
        "review_ceiling": REVIEW_CEILING,
        "claim": "same brief, distinct engines, same target, verified non-empty hashed outputs",
    }
    if output:
        output_path = require_within(Path(output), allowed_output_roots or [ROOT / "artifacts"],
                                     "cross-engine proof output")
        atomic_json(output_path, report)
    return report
