"""WANEFALL active character roster policy.

The source catalog can retain failed prototypes for audit, but active readiness
claims must only count characters that are still allowed in the build target.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metahuman_utilization import EXPECTED_CHARACTERS


ROOT = Path(__file__).resolve().parents[2]
ROSTER_PATH = ROOT / "config" / "character_roster.json"

DEFAULT_MECH_CHARACTERS = [
    {"character_id": "mech_01_glaciera", "asset_name": "SM_Char_Mech_01_Glaciera", "active": True},
    {"character_id": "mech_02_voidrunner", "asset_name": "SM_Char_Mech_02_Voidrunner", "active": True},
    {"character_id": "mech_03_aurelion", "asset_name": "SM_Char_Mech_03_Aurelion", "active": True},
    {"character_id": "mech_04_luxorion", "asset_name": "SM_Char_Mech_04_Luxorion", "active": True},
    {"character_id": "mech_05_pyroclast", "asset_name": "SM_Char_Mech_05_Pyroclast", "active": True},
    {"character_id": "mech_06_jadewind", "asset_name": "SM_Char_Mech_06_Jadewind", "active": True},
    {"character_id": "mech_07_ironline", "asset_name": "SM_Char_Mech_07_Ironline", "active": True},
    {"character_id": "mech_08_nightwire", "asset_name": "SM_Char_Mech_08_Nightwire", "active": True},
]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_roster_policy(root: Path = ROOT) -> dict[str, Any]:
    data = _read_json(Path(root) / "config" / "character_roster.json")
    if not data:
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("active_humanoid_target", len(EXPECTED_CHARACTERS))
    data.setdefault("active_mech_target", len(DEFAULT_MECH_CHARACTERS))
    data.setdefault("quarantined_humanoids", {})
    data.setdefault("mech_characters", DEFAULT_MECH_CHARACTERS)
    data.setdefault("next_lane", "characters")
    return data


def _norm(value: Any) -> str:
    return str(value or "").lower().replace("\\", "/").replace(".uasset", "")


def _character_tokens(item: dict[str, Any]) -> set[str]:
    tokens = {
        _norm(item.get("key")),
        _norm(item.get("asset_name")),
        _norm(item.get("asset_id")),
        _norm(item.get("source_stem")),
    }
    return {token for token in tokens if token}


def _quarantine_records(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    policy = load_roster_policy(root)
    raw = policy.get("quarantined_humanoids") if isinstance(policy.get("quarantined_humanoids"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for key, rec in raw.items():
        row = dict(rec) if isinstance(rec, dict) else {"reason": str(rec)}
        row.setdefault("key", key)
        row.setdefault("state", "QUARANTINED")
        for token in {_norm(key), _norm(row.get("asset_name")), _norm(row.get("asset_id"))}:
            if token:
                out[token] = row
    for item in EXPECTED_CHARACTERS:
        for token in _character_tokens(item):
            for qtoken, rec in list(out.items()):
                if qtoken and (qtoken in token or token in qtoken):
                    out[token] = rec
    return out


def quarantine_record(character: Any, root: Path = ROOT) -> dict[str, Any] | None:
    value = _norm(character)
    if value.endswith("_rig"):
        value = value[:-4]
    records = _quarantine_records(root)
    if value in records:
        return records[value]
    for token, rec in records.items():
        if token and (token in value or value in token):
            return rec
    return None


def is_quarantined_character(character: Any, root: Path = ROOT) -> bool:
    return quarantine_record(character, root) is not None


def active_humanoid_characters(root: Path = ROOT) -> list[dict[str, Any]]:
    return [
        item for item in EXPECTED_CHARACTERS
        if not any(quarantine_record(token, root) for token in _character_tokens(item))
    ]


def quarantined_humanoid_characters(root: Path = ROOT) -> list[dict[str, Any]]:
    return [
        item for item in EXPECTED_CHARACTERS
        if any(quarantine_record(token, root) for token in _character_tokens(item))
    ]


def active_humanoid_names(root: Path = ROOT) -> list[str]:
    return [str(item["asset_name"]) for item in active_humanoid_characters(root)]


def active_mech_characters(root: Path = ROOT) -> list[dict[str, Any]]:
    policy = load_roster_policy(root)
    chars = policy.get("mech_characters") if isinstance(policy.get("mech_characters"), list) else DEFAULT_MECH_CHARACTERS
    return [dict(item) for item in chars if isinstance(item, dict) and item.get("active", True)]


def roster_policy_summary(root: Path = ROOT) -> dict[str, Any]:
    policy = load_roster_policy(root)
    active_humans = active_humanoid_characters(root)
    quarantined = quarantined_humanoid_characters(root)
    active_mechs = active_mech_characters(root)
    quarantine_ids = []
    for item in quarantined:
        rec = None
        for token in _character_tokens(item):
            rec = quarantine_record(token, root)
            if rec:
                break
        quarantine_ids.append(str((rec or {}).get("key") or "retired_prototype"))
    return {
        "active_humanoid_target": int(policy.get("active_humanoid_target") or len(active_humans)),
        "active_mech_target": int(policy.get("active_mech_target") or len(active_mechs)),
        "source_humanoid_catalog_count": len(EXPECTED_CHARACTERS),
        "active_humanoid_count": len(active_humans),
        "quarantined_humanoid_count": len(quarantined),
        "active_mech_count": len(active_mechs),
        "active_humanoids": [str(item["key"]) for item in active_humans],
        "quarantined_humanoids": quarantine_ids,
        "active_mechs": [str(item["character_id"]) for item in active_mechs],
        "next_lane": str(policy.get("next_lane") or ""),
    }
