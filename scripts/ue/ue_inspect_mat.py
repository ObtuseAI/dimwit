"""Dump the Ekris material instance params (parent, metallic/roughness/base-color/textures) to find why the silver
reads dark in-engine. Writes artifacts/inspect_mat.json."""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/inspect_mat.json")
MICS = [
    "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material",
    "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/Materials/pbr_material",
]
out = {"materials": []}
try:
    for mp in MICS:
        rec = {"path": mp}
        m = unreal.load_asset(mp)
        rec["class"] = type(m).__name__
        if isinstance(m, unreal.MaterialInstanceConstant):
            par = m.get_editor_property("parent")
            rec["parent"] = par.get_path_name() if par else None
            # scalar params
            sc = {}
            for name in ["Metallic", "Roughness", "Specular", "EmissiveStrength", "Emissive", "AO"]:
                try:
                    sc[name] = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(m, name)
                except Exception:
                    pass
            rec["scalars"] = sc
            vp = {}
            for name in ["BaseColor", "Color", "Tint", "BaseColorTint"]:
                try:
                    v = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(m, name)
                    vp[name] = [round(v.r, 3), round(v.g, 3), round(v.b, 3)]
                except Exception:
                    pass
            rec["vectors"] = vp
            tx = {}
            for name in ["BaseColorTexture", "BaseColor", "Diffuse", "NormalTexture", "Normal", "ORM",
                         "MetallicTexture", "RoughnessTexture"]:
                try:
                    t = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(m, name)
                    if t:
                        tx[name] = t.get_path_name()
                except Exception:
                    pass
            rec["textures"] = tx
        elif isinstance(m, unreal.Material):
            rec["is_base_material"] = True
            try:
                rec["base_metallic_const"] = None
            except Exception:
                pass
        out["materials"].append(rec)
    # also report the parent material's static metallic if a MIC points to a master
    for rec in out["materials"]:
        p = rec.get("parent")
        if p:
            base = unreal.load_asset(p)
            rec["parent_class"] = type(base).__name__ if base else None
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_INSPECT_MAT_DONE")
