"""READ-ONLY probe #2: diff the WORKING static-character material against the BROKEN rig material.

Static /Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Materials/pbr_material renders textured;
rig /Game/Wanefall/Dimwit/CharactersRigged/zythan_mat renders white and is provably parameter-inert
(byte-identical captures across a 4.4x -> 1.0 BaseColorFactor change). Enumerate what the shared
parent chain actually exposes and every override each instance carries, so the divergence is visible.
"""
import json
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_material_param_diff_result.json")
PARENT_INSTANCE = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
ROOT_MATERIAL = "/InterchangeAssets/gltf/M_Default"
WORKING = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Materials/pbr_material"
BROKEN = "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"

mel = unreal.MaterialEditingLibrary
result = {}


def param_names(asset):
    try:
        return {
            "texture": [str(n) for n in mel.get_texture_parameter_names(asset)],
            "scalar": [str(n) for n in mel.get_scalar_parameter_names(asset)],
            "vector": [str(n) for n in mel.get_vector_parameter_names(asset)],
            "static_switch": [str(n) for n in (mel.get_static_switch_parameter_names(asset) if hasattr(mel, "get_static_switch_parameter_names") else [])],
        }
    except Exception as exc:
        return {"error": repr(exc)}


def overrides(mic_path):
    mic = unreal.load_asset(mic_path)
    if not isinstance(mic, unreal.MaterialInstanceConstant):
        return {"error": f"not MIC: {type(mic).__name__ if mic else None}"}
    out = {"path": mic.get_path_name()}
    try:
        out["textures"] = [{
            "name": str(p.parameter_info.name),
            "value": p.parameter_value.get_path_name() if p.parameter_value else None,
        } for p in mic.texture_parameter_values]
    except Exception as exc:
        out["textures"] = f"unreadable:{exc}"
    try:
        out["scalars"] = [{"name": str(p.parameter_info.name), "value": float(p.parameter_value)}
                          for p in mic.scalar_parameter_values]
    except Exception as exc:
        out["scalars"] = f"unreadable:{exc}"
    try:
        out["vectors"] = [{"name": str(p.parameter_info.name),
                           "value": [p.parameter_value.r, p.parameter_value.g, p.parameter_value.b, p.parameter_value.a]}
                          for p in mic.vector_parameter_values]
    except Exception as exc:
        out["vectors"] = f"unreadable:{exc}"
    try:
        overrides_prop = mic.get_editor_property("base_property_overrides")
        out["base_property_overrides"] = str(overrides_prop)[:300]
    except Exception:
        pass
    try:
        parent = mic.get_editor_property("parent")
        out["parent"] = parent.get_path_name() if parent else None
    except Exception:
        out["parent"] = None
    return out


root = unreal.load_asset(ROOT_MATERIAL)
parent_mi = unreal.load_asset(PARENT_INSTANCE)
result["root_material_params"] = param_names(root) if root else "missing"
result["parent_instance_overrides"] = overrides(PARENT_INSTANCE)
result["working_static"] = overrides(WORKING)
result["broken_rig"] = overrides(BROKEN)

rig = unreal.load_asset(RIG)
if isinstance(rig, unreal.SkeletalMesh):
    result["rig_asset"] = {"path": rig.get_path_name()}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("DIFF_PROBE_DONE")
