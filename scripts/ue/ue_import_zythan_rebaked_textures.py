"""Import the 4K re-baked zythan texture set over the existing rig texture assets.

Replaces /Game/Wanefall/Dimwit/CharactersRigged/Textures/SM_Char_03_zythan_Rig_{albedo,normal,ao}
in place so M_ZythanRigShip picks the new content up without any material changes. Normal map gets
explicit TC_Normalmap + sRGB off (a replace-import falls back to name heuristics otherwise).

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_import_zythan_rebaked_textures.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_rebaked_texture_import_result.json")
SRC_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_rebake/SM_Char_03_zythan")
DEST = "/Game/Wanefall/Dimwit/CharactersRigged/Textures"
IMPORTS = [
    ("SM_Char_03_zythan_albedo_4k.png", "SM_Char_03_zythan_Rig_albedo", "color"),
    ("SM_Char_03_zythan_normal_4k.png", "SM_Char_03_zythan_Rig_normal", "normal"),
    ("SM_Char_03_zythan_ao_4k.png", "SM_Char_03_zythan_Rig_ao", "color"),
]
result = {"ok": False, "imports": []}

try:
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    eal = unreal.EditorAssetLibrary
    tasks = []
    for fname, dest_name, kind in IMPORTS:
        src = SRC_DIR / fname
        if not src.exists():
            raise RuntimeError(f"baked map missing: {src}")
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(src))
        task.set_editor_property("destination_path", DEST)
        task.set_editor_property("destination_name", dest_name)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        tasks.append((task, dest_name, kind))
    tools.import_asset_tasks([t for t, _, _ in tasks])

    for task, dest_name, kind in tasks:
        asset_path = f"{DEST}/{dest_name}"
        tex = unreal.load_asset(asset_path)
        rec = {"asset": asset_path, "imported": isinstance(tex, unreal.Texture2D)}
        if isinstance(tex, unreal.Texture2D):
            if kind == "normal":
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                tex.set_editor_property("srgb", False)
                tex.set_editor_property("flip_green_channel", False)
            rec["size"] = [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]
            rec["saved"] = bool(eal.save_asset(asset_path, False))
        result["imports"].append(rec)
    result["ok"] = all(r.get("imported") and r.get("saved") for r in result["imports"])
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("REBAKE_IMPORT_RESULT:", json.dumps(result)[:400])
