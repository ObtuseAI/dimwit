"""Dimwit color fix: import the brightened Ekris albedo and set it as BaseColorTexture on the character materials
(static full-Nanite + rigged-skeletal) so the silver armor + orange Wane seams READ in-engine (no glow hacks).
Verifies via artifacts/apply_albedo_result.json."""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/apply_albedo_result.json")
PNG = r"C:/Users/developer/Documents/Dimwit/artifacts/char_fix/ekris_albedo_bright.png"
TEX_DEST = "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/Textures"
TEX_NAME = "T_ekris_albedo_bright"
MICS = [
    "/Game/Wanefall/Dimwit/Characters/SM_Char_02_ekris/Materials/pbr_material",
    "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material",
]
tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
out = {"ok": False, "records": []}
try:
    # import the brightened PNG as a Texture2D (sRGB on for base color)
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", PNG)
    t.set_editor_property("destination_path", TEX_DEST)
    t.set_editor_property("destination_name", TEX_NAME)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    tools.import_asset_tasks([t])
    tex_path = f"{TEX_DEST}/{TEX_NAME}"
    tex = unreal.load_asset(tex_path)
    out["texture"] = tex_path
    out["texture_ok"] = isinstance(tex, unreal.Texture2D)
    if isinstance(tex, unreal.Texture2D):
        try:
            tex.set_editor_property("srgb", True)
            eal.save_asset(tex_path)
        except Exception:
            pass
    # set it as BaseColorTexture on each character material instance
    for mp in MICS:
        rec = {"mic": mp}
        mic = unreal.load_asset(mp)
        if isinstance(mic, unreal.MaterialInstanceConstant) and isinstance(tex, unreal.Texture2D):
            mel.set_material_instance_texture_parameter_value(mic, "BaseColorTexture", tex)
            try:
                mel.update_material_instance(mic)
            except Exception:
                pass
            eal.save_asset(mp)
            rec["applied"] = True
        else:
            rec["applied"] = False
            rec["why"] = f"mic={type(mic).__name__ if mic else None}"
        out["records"].append(rec)
    out["ok"] = out.get("texture_ok") and all(r.get("applied") for r in out["records"])
except Exception:
    out["error"] = traceback.format_exc()
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_APPLY_ALBEDO_DONE ok=" + str(out.get("ok")))
