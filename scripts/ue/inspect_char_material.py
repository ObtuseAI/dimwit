"""Dimwit: inspect the Ekris glTF character material so we know the MINIMAL de-chrome fix.
Writes result to artifacts/ekris_mat_info.json (file-based — headless stdout is unreliable; exit code is the
benign editor-shutdown quirk). Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/inspect_char_material.py"
"""
import unreal, json, traceback
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/ekris_mat_info.json")
MAT = "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/Materials/pbr_material"
MESH = "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/StaticMeshes/SM_Char_02_ekris"

def dump(o):
    info = {"class": type(o).__name__, "path": o.get_path_name()}
    if isinstance(o, unreal.MaterialInstanceConstant):
        par = o.get_editor_property("parent")
        info["parent"] = par.get_path_name() if par else None
        info["scalars"] = [(str(s.get_editor_property("parameter_info").get_editor_property("name")),
                            float(s.get_editor_property("parameter_value")))
                           for s in o.get_editor_property("scalar_parameter_values")]
        info["textures"] = [(str(t.get_editor_property("parameter_info").get_editor_property("name")),
                             t.get_editor_property("parameter_value").get_path_name()
                             if t.get_editor_property("parameter_value") else None)
                            for t in o.get_editor_property("texture_parameter_values")]
        info["vectors"] = [str(v.get_editor_property("parameter_info").get_editor_property("name"))
                           for v in o.get_editor_property("vector_parameter_values")]
    elif isinstance(o, unreal.Material):
        try:
            info["used_textures"] = [t.get_path_name() for t in unreal.MaterialEditingLibrary.get_used_textures(o)]
        except Exception as e:
            info["used_textures_err"] = str(e)
        # base property scalar overrides on a UMaterial
        for prop in ("metallic", "roughness", "specular"):
            try:
                info[prop] = o.get_editor_property(prop)
            except Exception as e:
                info[prop + "_err"] = str(e)
    return info

out = {"ok": False}
try:
    m = unreal.load_asset(MAT)
    out["material"] = dump(m) if m else "MATERIAL_NOT_FOUND"
    sm = unreal.load_asset(MESH)
    if isinstance(sm, unreal.StaticMesh):
        slots = sm.get_editor_property("static_materials")
        out["mesh_slots"] = []
        for i in range(len(slots)):
            cur = sm.get_material(i)
            out["mesh_slots"].append({"index": i,
                                      "material": cur.get_path_name() if cur else None,
                                      "class": type(cur).__name__ if cur else None})
    out["ok"] = True
except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("RM_MAT_INFO_WRITTEN " + str(OUT))
