"""Enable the glTF static texture switches on the rig render material (ACTIVE_RIG_MATERIAL_TRUTH_REPAIR_V1).

ROOT CAUSE (probe-proven): /InterchangeAssets/gltf/M_Default gates every texture sample behind
static switches (bHasBaseColorTexture, ...). The Interchange importer baked those switches TRUE
into the WORKING static-character instance; the rig's zythan_mat was assembled programmatically
with the switches all FALSE, so the shader permutation samples nothing and renders glTF-default
flat white - which is why captures were byte-identical across every prior parameter change.

Fix = mirror the WORKING instance (Characters/SM_Char_03_zythan/Materials/pbr_material) exactly:
  switches: bHasBaseColorTexture=True, bHasMetallicRoughnessTexture=True
  textures: BaseColorTexture=Image_0, MetallicRoughnessTexture=Image_1
  scalars:  MetallicFactor=0.1, EmissiveStrength=1.8
  vectors:  BaseColorFactor=[0.10,0.11,0.14,1] (dark carapace), EmissiveFactor=[0.21,0.15,0.52,1] (violet)

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_rig_static_switch_fix.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_rig_static_switch_fix_result.json")
TARGET = "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat"
BASECOLOR_TEX = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_0"
METALROUGH_TEX = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_1"

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
result = {"ok": False, "target": TARGET, "steps": []}

try:
    mic = unreal.load_asset(TARGET)
    if not isinstance(mic, unreal.MaterialInstanceConstant):
        raise RuntimeError(f"not a MaterialInstanceConstant: {type(mic).__name__ if mic else None}")

    for switch in ("bHasBaseColorTexture", "bHasMetallicRoughnessTexture"):
        before = None
        try:
            before = bool(mel.get_material_instance_static_switch_parameter_value(mic, switch))
        except Exception:
            before = None
        mel.set_material_instance_static_switch_parameter_value(mic, switch, True)
        after = bool(mel.get_material_instance_static_switch_parameter_value(mic, switch))
        result["steps"].append({"static_switch": switch, "before": before, "after": after})

    for name, path in (("BaseColorTexture", BASECOLOR_TEX), ("MetallicRoughnessTexture", METALROUGH_TEX)):
        tex = unreal.load_asset(path)
        if not isinstance(tex, unreal.Texture2D):
            raise RuntimeError(f"texture missing: {path}")
        mel.set_material_instance_texture_parameter_value(mic, name, tex)
        result["steps"].append({"texture": name, "value": path})

    for name, value in (("MetallicFactor", 0.1), ("EmissiveStrength", 1.8)):
        mel.set_material_instance_scalar_parameter_value(mic, name, value)
        result["steps"].append({"scalar": name, "value": value})

    for name, rgba in (("BaseColorFactor", (0.10, 0.11, 0.14, 1.0)), ("EmissiveFactor", (0.21, 0.15, 0.52, 1.0))):
        mel.set_material_instance_vector_parameter_value(mic, name, unreal.LinearColor(*rgba))
        result["steps"].append({"vector": name, "value": list(rgba)})

    mel.update_material_instance(mic)
    result["saved"] = bool(eal.save_asset(TARGET, False))
    result["ok"] = bool(result["saved"])
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("FIX_RESULT:", json.dumps(result)[:500])
