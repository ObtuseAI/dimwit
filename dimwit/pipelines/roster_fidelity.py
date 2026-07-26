"""ROSTER_FIDELITY_V1 — per-character rig+anim+deformation cert store + active-roster coverage.

Fail-closed: a missing/unreadable cert is BLOCKED, never a silent pass. Pure Python (no bpy/unreal at
module top) so it imports under pytest and the suite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import BlockedError
from .character_roster import active_mech_characters, is_quarantined_character

ROOT = Path(__file__).resolve().parents[2]
CERT_DIR = ROOT / "artifacts" / "roster_fidelity"

# ROSTER_FIDELITY_V1 scope: the deformation-cert gate covers the 6 active humanoids. The 8 mechs are ACTIVE
# roster but their rigid-rig skeleton articulates near-origin headless (mech hand_r bind ~z=0.9 vs humanoid
# ~z=104) so the pose-deformation gate can't measure them yet -- deferred to V2 (dedicated mech-rig fix), NOT
# silently dropped. See memory ue-headless-anim-eval-law / wanefall-p0-bundles.
V1_DEFERRED_KINDS = {"mech"}
DEFERRAL_REASON = ("mech rigid-rig skeleton articulates near-origin headless -> deformation unmeasurable; "
                   "deferred to ROSTER_FIDELITY_V2 (dedicated mech-rig scale/bind fix)")

# 6 active humanoids (vorlax/ekris are quarantined and excluded here).
_HUMANOIDS = [
    ("zythan", "SM_Char_03_zythan"), ("qorin", "SM_Char_04_qorin"),
    ("therak", "SM_Char_05_therak"), ("ullio", "SM_Char_06_ullio"),
    ("kelous", "SM_Char_07_kelous"), ("nexor", "SM_Char_08_nexor"),
]


def _mech_targets() -> list[dict[str, Any]]:
    out = []
    for mech in active_mech_characters(ROOT):
        out.append({"key": str(mech["character_id"]), "asset": str(mech["asset_name"]),
                    "kind": "mech", "rigid": True})
    return out


ACTIVE_ROSTER_TARGETS: list[dict[str, Any]] = [
    {"key": k, "asset": a, "kind": "humanoid", "rigid": False} for k, a in _HUMANOIDS
] + _mech_targets()


def active_roster_targets(root: Path = ROOT) -> list[dict[str, Any]]:
    return [t for t in ACTIVE_ROSTER_TARGETS
            if not is_quarantined_character(t["key"], root)
            and not is_quarantined_character(t["asset"], root)]


def certifiable_targets(root: Path = ROOT) -> list[dict[str, Any]]:
    """Active roster characters the V1 deformation-cert gate covers (humanoids). Mechs are deferred."""
    return [t for t in active_roster_targets(root) if t["kind"] not in V1_DEFERRED_KINDS]


def deferred_targets(root: Path = ROOT) -> list[dict[str, Any]]:
    """Active roster characters whose fidelity cert is deferred to V2 (mechs)."""
    return [t for t in active_roster_targets(root) if t["kind"] in V1_DEFERRED_KINDS]


def cert_path(asset: str, root: Path = ROOT) -> Path:
    return Path(root) / "artifacts" / "roster_fidelity" / f"{asset}.json"


def write_cert(asset: str, kind: str, rig_result: dict, anim_result: dict,
               deform_result: dict, root: Path = ROOT) -> dict[str, Any]:
    cert = {
        "schema_version": 1,
        "asset": asset,
        "kind": kind,
        "rig": rig_result,
        "anim": anim_result,
        "deformation": deform_result,
    }
    path = cert_path(asset, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
    return cert


def load_cert(asset: str, root: Path = ROOT) -> dict[str, Any]:
    path = cert_path(asset, root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"roster-fidelity cert missing/unreadable for {asset}: {e}")
    if not isinstance(data, dict):
        raise BlockedError(f"roster-fidelity cert malformed for {asset}")
    return data


def validate_cert(cert: dict) -> dict[str, Any]:
    issues: list[str] = []
    for leg in ("rig", "anim", "deformation"):
        sub = cert.get(leg) or {}
        if not sub.get("passed"):
            issues.append(f"{cert.get('asset', '?')}: {leg} not passed")
    deform = cert.get("deformation") or {}
    score = deform.get("score")
    if deform.get("passed") and (score is None or float(score) < 0.85):
        issues.append(f"{cert.get('asset', '?')}: deformation score {score} < 0.85")
    return {"passed": not issues, "issues": issues}


def roster_fidelity_coverage(root: Path = ROOT) -> dict[str, Any]:
    covered, missing, issues = [], [], []
    for t in certifiable_targets(root):
        asset = t["asset"]
        try:
            cert = load_cert(asset, root)
        except BlockedError:
            missing.append(asset)
            continue
        result = validate_cert(cert)
        if result["passed"]:
            covered.append(asset)
        else:
            missing.append(asset)
            issues.extend(result["issues"])
    deferred = [t["asset"] for t in deferred_targets(root)]
    return {"passed": not missing, "issues": issues, "covered": covered, "missing": missing,
            "deferred": deferred, "deferral_reason": DEFERRAL_REASON if deferred else None}
