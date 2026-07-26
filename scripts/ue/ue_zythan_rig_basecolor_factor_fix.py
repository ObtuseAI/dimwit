"""Revert the x4 BaseColor multiplier on the active rig materials (bundle: ACTIVE_RIG_MATERIAL_TRUTH_REPAIR_V1).

Root cause of the 2026-07-01 white_debug REJECT: scripts/ue/ue_active_rig_material_repair.py hardcoded
BaseColorFactor/BaseColor vector overrides of LinearColor(4.0, 4.4, 4.8) on the rig render
materials (an over-correction for an earlier too-dark capture). Under the rig_ship capture's
ship lighting that multiplier blows the character to white (white_junk_fraction 0.0658 > 0.06).
The working comparator - the static zythan pbr_material, 48 nanite validators green - carries no
such override. This fix does exactly ONE thing: set those two vector params back to 1.0 on the
two CharactersRigged material instances. Textures, emissive, roughness, slots stay untouched.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_rig_basecolor_factor_fix.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_rig_basecolor_factor_fix_result.json")
MATERIALS = [
    "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat",       # assigned to the rig's render slot
    "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material",     # same bad override from the same repair step
]
NEUTRAL = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
VECTOR_PARAMS = ("BaseColorFactor", "BaseColor")

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
result = {"ok": False, "materials": []}

try:
    for path in MATERIALS:
        rec = {"path": path, "params": {}, "saved": False}
        mic = unreal.load_asset(path)
        if not isinstance(mic, unreal.MaterialInstanceConstant):
            rec["error"] = f"not a MaterialInstanceConstant: {type(mic).__name__ if mic else None}"
            result["materials"].append(rec)
            continue
        for name in VECTOR_PARAMS:
            before = None
            try:
                value = mel.get_material_instance_vector_parameter_value(mic, name)
                before = [value.r, value.g, value.b, value.a] if value else None
            except Exception:
                before = None
            try:
                mel.set_material_instance_vector_parameter_value(mic, name, NEUTRAL)
                after = mel.get_material_instance_vector_parameter_value(mic, name)
                rec["params"][name] = {"before": before, "after": [after.r, after.g, after.b, after.a] if after else None}
            except Exception as exc:
                rec["params"][name] = {"before": before, "error": repr(exc)}
        try:
            mel.update_material_instance(mic)
        except Exception:
            pass
        rec["saved"] = bool(eal.save_asset(path, False))
        result["materials"].append(rec)
    result["ok"] = all(m.get("saved") for m in result["materials"])
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("RESULT:", json.dumps(result)[:600])
