"""Fail-closed open-source intake and adoption scoring for Dimwit.

The registry is planning evidence, not an installer.  This module performs no network access, package install,
download, arbitrary command execution, or source mutation.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "opensource_adoption_candidates.json"
DEFAULT_ARTIFACT = ROOT / "artifacts" / "ecosystem" / "opensource_adoption_report.json"
ALLOWED_MODES = {"ADOPT_NOW", "EVALUATE", "REFERENCE_ONLY", "USE_ENGINE_BUILTIN", "HOLD"}
PERMISSIVE_LICENSES = {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE"}


def _local_probe(probe: dict[str, Any]) -> dict:
    kind = str(probe.get("kind") or "none")
    value = str(probe.get("value") or "")
    if kind == "python_module":
        return {"kind": kind, "value": value, "present": importlib.util.find_spec(value) is not None}
    if kind == "path":
        path = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value)
        return {"kind": kind, "value": str(path), "present": path.exists()}
    return {"kind": "none", "value": "", "present": False}


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = ("id", "name", "source_url", "license", "adoption_mode", "value", "risk", "integration_cost")
    for key in required:
        if key not in candidate or candidate[key] in (None, ""):
            issues.append(f"missing {key}")
    source = str(candidate.get("source_url") or "")
    if not source.startswith("https://github.com/"):
        issues.append("source_url must be a direct GitHub repository URL")
    mode = str(candidate.get("adoption_mode") or "")
    if mode not in ALLOWED_MODES:
        issues.append(f"unsupported adoption_mode {mode!r}")
    license_id = str(candidate.get("license") or "UNKNOWN").upper()
    if license_id in {"UNKNOWN", "UNVERIFIED", ""}:
        issues.append("license is unknown or unverified")
    elif license_id not in PERMISSIVE_LICENSES and mode not in {"REFERENCE_ONLY", "HOLD"}:
        issues.append("non-permissive or mixed license may only be REFERENCE_ONLY or HOLD")
    for key in ("value", "risk", "integration_cost"):
        try:
            number = float(candidate.get(key))
            if not 0 <= number <= 5:
                issues.append(f"{key} must be between 0 and 5")
        except (TypeError, ValueError):
            issues.append(f"{key} must be numeric")
    return issues


def audit_ecosystem(config_path: Path = DEFAULT_CONFIG, output_path: Path | None = None) -> dict:
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    rows, rejected = [], []
    for candidate in raw.get("candidates", []):
        issues = validate_candidate(candidate)
        if issues:
            rejected.append({"id": candidate.get("id"), "issues": issues})
            continue
        probe = _local_probe(candidate.get("local_probe") or {})
        score = round(
            float(candidate["value"]) * 2.0 - float(candidate["risk"]) - float(candidate["integration_cost"])
            + (0.5 if probe["present"] else 0.0), 4,
        )
        rows.append({**candidate, "local_evidence": probe, "adoption_score": score})
    rows.sort(key=lambda row: (-row["adoption_score"], row["id"]))
    report = {
        "schema_version": 1, "as_of": raw.get("as_of"), "state": "PASS" if not rejected else "FAIL_CLOSED",
        "authority": "PLAN_ONLY_NO_INSTALL_OR_EXECUTION", "candidate_count": len(rows),
        "rejected_count": len(rejected), "ranked_candidates": rows, "rejected": rejected,
        "recommended_now": [row["id"] for row in rows if row["adoption_mode"] == "ADOPT_NOW"],
        "evaluation_queue": [row["id"] for row in rows if row["adoption_mode"] == "EVALUATE"],
        "invariants": [
            "unknown licenses are rejected",
            "registry audit performs no network access, downloads, installs, or execution",
            "REFERENCE_ONLY sources do not receive runtime authority",
            "engine-native interchange is preferred over duplicate source builds",
        ],
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    return report


def write_default_report() -> dict:
    return audit_ecosystem(output_path=DEFAULT_ARTIFACT)
