"""Fix the RIGGED Ekris material: it came in as an FBX legacy-Phong material (renders the silver dark), while the
static char uses the proper glTF PBR base (MI_Default_Opaque). Reparent the rigged material to that same good base,
re-point BaseColorTexture at the brightened albedo, and force metallic low so the bright silver albedo DRIVES the
look (a de-chromed satin metal goes dark without an HDRI to reflect). Writes artifacts/fix_rigmat.json."""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/fix_rigmat.json")
RIG_MAT = "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"
GOOD_BASE = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
ALBEDO = "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/Textures/T_ekris_albedo_bright"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
out = {"ok": False}
try:
    m = unreal.load_asset(RIG_MAT)
    base = unreal.load_asset(GOOD_BASE)
    tex = unreal.load_asset(ALBEDO)
    out["before_parent"] = m.get_editor_property("parent").get_path_name()
    m.set_editor_property("parent", base)
    out["after_parent"] = m.get_editor_property("parent").get_path_name()
    if tex:
        mel.set_material_instance_texture_parameter_value(m, "BaseColorTexture", tex)
    # force albedo-dominant silver: metallic 0, sensible roughness, full specular (dielectric)
    for name, val in [("Metallic", 0.0), ("Roughness", 0.55), ("Specular", 0.5)]:
        try:
            mel.set_material_instance_scalar_parameter_value(m, name, val)
        except Exception:
            pass
    try:
        mel.update_material_instance(m)
    except Exception:
        pass
    eal.save_asset(RIG_MAT)
    out["ok"] = out["after_parent"] == base.get_path_name()
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_FIX_RIGMAT_DONE ok=" + str(out.get("ok")))
