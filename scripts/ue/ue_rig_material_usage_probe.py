"""READ-ONLY probe: why does the zythan rig render as default white clay? (systematic-debugging Phase 1)

Checks, without mutating anything:
1. zythan_mat's parent chain and whether the ROOT Material carries used_with_skeletal_mesh
   (a skeletal mesh rendered with a material lacking that usage falls back to the engine default
   gray-white material, ignoring every instance parameter - matching the byte-identical captures).
2. The rig SkeletalMesh's actual material slot assignments.
3. The project-owned skeletal-ready candidates (M_WaneZythan_SourceReadable, M_WaneSoldierSuit):
   class, usage flags, texture parameter names.
"""
import json
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_material_usage_probe_result.json")
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
MATS = [
    "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat",
    "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material",
]
CANDIDATES = [
    "/Game/Wanefall/Materials/M_WaneZythan_SourceReadable",
    "/Game/Wanefall/Materials/M_WaneSoldierSuit",
]
mel = unreal.MaterialEditingLibrary
result = {"parent_chains": [], "rig_slots": [], "candidates": []}


def describe_chain(path):
    chain = []
    seen = 0
    asset = unreal.load_asset(path)
    while asset is not None and seen < 6:
        entry = {"path": asset.get_path_name(), "class": type(asset).__name__}
        if isinstance(asset, unreal.Material):
            for flag in ("used_with_skeletal_mesh", "used_with_nanite", "used_with_morph_targets"):
                try:
                    entry[flag] = bool(asset.get_editor_property(flag))
                except Exception as exc:
                    entry[flag] = f"unreadable:{exc}"
            chain.append(entry)
            break
        chain.append(entry)
        try:
            asset = asset.get_editor_property("parent")
        except Exception:
            asset = None
        seen += 1
    return chain


for path in MATS:
    result["parent_chains"].append({"material": path, "chain": describe_chain(path)})

rig = unreal.load_asset(RIG)
if isinstance(rig, unreal.SkeletalMesh):
    for i, m in enumerate(rig.materials):
        mi = m.material_interface
        result["rig_slots"].append({
            "slot": i,
            "slot_name": str(m.material_slot_name),
            "material": mi.get_path_name() if mi else None,
        })
else:
    result["rig_slots"] = f"rig not a SkeletalMesh: {type(rig).__name__ if rig else None}"

for path in CANDIDATES:
    asset = unreal.load_asset(path)
    entry = {"path": path, "loaded": bool(asset), "class": type(asset).__name__ if asset else None}
    if isinstance(asset, unreal.Material):
        for flag in ("used_with_skeletal_mesh", "used_with_nanite"):
            try:
                entry[flag] = bool(asset.get_editor_property(flag))
            except Exception as exc:
                entry[flag] = f"unreadable:{exc}"
        try:
            entry["texture_params"] = [str(n) for n in mel.get_texture_parameter_names(asset)]
            entry["scalar_params"] = [str(n) for n in mel.get_scalar_parameter_names(asset)]
            entry["vector_params"] = [str(n) for n in mel.get_vector_parameter_names(asset)]
        except Exception as exc:
            entry["param_error"] = repr(exc)
    result["candidates"].append(entry)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("PROBE_RESULT:", json.dumps(result)[:800])
