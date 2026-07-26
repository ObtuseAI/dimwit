"""Repair runtime WANE material usage flags exposed by live-game default-material warnings."""
import json
import traceback
from pathlib import Path

import unreal


OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/runtime_material_usage_repair_result.json")
MATERIALS = [
    {"path": "/Game/Wanefall/Materials/M_WaneStructure", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneVisor", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneVisorSubtle", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneRuinTrim_Emissive", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneRelicEmissive", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneSoldierSuit", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneZythan_SourceReadable", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSoldierSuit_Readable", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSilverTealArmor", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneVisorProof", "nanite": True, "skeletal": False},
    {"path": "/Game/Wanefall/Materials/M_WaneAlienCarapace_V2", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Kharvex", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Veydrin", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Drothakai", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Thessar", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_BrakThul", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Ilyr", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Morvane", "nanite": False, "skeletal": True},
    {"path": "/Game/Wanefall/Materials/M_WaneSpecies_Caelrex", "nanite": False, "skeletal": True},
]

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
result = {"ok": False, "materials": []}


def _read_bool(asset, prop):
    try:
        return bool(asset.get_editor_property(prop))
    except Exception as exc:
        return f"unreadable:{exc}"


def _set_flag(asset, prop):
    before = _read_bool(asset, prop)
    try:
        asset.set_editor_property(prop, True)
    except Exception as exc:
        return {"before": before, "after": _read_bool(asset, prop), "error": str(exc)}
    return {"before": before, "after": _read_bool(asset, prop)}


def _repair_one(spec):
    path = spec["path"]
    asset = unreal.load_asset(path)
    rec = {
        "path": path,
        "loaded": bool(asset),
        "class": type(asset).__name__ if asset else None,
        "requested": {"used_with_nanite": spec["nanite"], "used_with_skeletal_mesh": spec["skeletal"]},
        "flags": {},
        "saved": False,
    }
    if not asset:
        rec["error"] = "material missing"
        return rec
    if spec["nanite"]:
        rec["flags"]["used_with_nanite"] = _set_flag(asset, "used_with_nanite")
    if spec["skeletal"]:
        rec["flags"]["used_with_skeletal_mesh"] = _set_flag(asset, "used_with_skeletal_mesh")
    try:
        if hasattr(mel, "recompile_material"):
            mel.recompile_material(asset)
    except Exception as exc:
        rec["recompile_warning"] = str(exc)
    try:
        rec["saved"] = bool(eal.save_asset(path, False))
    except Exception as exc:
        rec["save_error"] = str(exc)
    return rec


try:
    result["materials"] = [_repair_one(spec) for spec in MATERIALS]
    result["ok"] = all(
        rec.get("loaded")
        and rec.get("saved")
        and all(flag.get("after") is True for flag in rec.get("flags", {}).values())
        for rec in result["materials"]
    )
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_RUNTIME_MATERIAL_USAGE_REPAIR ok={result['ok']} out={OUT}")
unreal.log(f"DIMWIT_RUNTIME_MATERIAL_USAGE_REPAIR ok={result['ok']}")
