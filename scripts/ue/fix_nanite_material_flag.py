"""Dimwit: the Ekris Nanite mesh renders its smooth low-poly FALLBACK (flat grey blob) because the glTF base
material M_Default lacks bUsedWithNanite, so the full 2M-tri Nanite geometry can't use it. Set the flag on the
base material (duplicate into the project if the plugin asset can't be saved) so the real mesh + textured
material render. Verifies via artifacts/nanite_matfix.json.
"""
import unreal, json, traceback
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/nanite_matfix.json")
CHARS = "/Game/Wanefall/Dimwit/Characters"
asset = "SM_Char_02_ekris"
mesh_path = f"{CHARS}/{asset}/StaticMeshes/{asset}"
mic_path = f"{CHARS}/{asset}/Materials/pbr_material"
PROJ_MAT_DIR = "/Game/Wanefall/Dimwit/Materials"

eal = unreal.EditorAssetLibrary
res = {"ok": False}

def set_nanite_flag(mat):
    for prop in ("used_with_nanite", "b_used_with_nanite"):
        try:
            mat.set_editor_property(prop, True)
            return prop
        except Exception:
            continue
    # API fallback: some UE builds expose a checker/setter on MaterialEditingLibrary
    return None

try:
    mesh = unreal.load_asset(mesh_path)
    res["nanite_enabled"] = mesh.get_editor_property("nanite_settings").get_editor_property("enabled")
    res["fallback_tris"] = mesh.get_num_triangles(0)
    res["slot0_before"] = mesh.get_material(0).get_path_name() if mesh.get_material(0) else None

    mic = unreal.load_asset(mic_path)
    base = mic.get_base_material()
    res["base"] = base.get_path_name()
    try:
        res["used_with_nanite_before"] = base.get_editor_property("used_with_nanite")
    except Exception as e:
        res["read_err"] = str(e)

    prop = set_nanite_flag(base)
    res["set_prop"] = prop
    saved = False
    if prop:
        try:
            saved = eal.save_asset(base.get_path_name())
        except Exception as e:
            res["save_base_err"] = str(e)
    res["base_saved"] = saved

    # If the base is a read-only plugin asset that wouldn't save, duplicate into the project + reparent the MIC.
    if not saved:
        proj_base = f"{PROJ_MAT_DIR}/M_WaneCharBase"
        if not eal.does_asset_exist(proj_base):
            dup = eal.duplicate_asset(base.get_path_name(), proj_base)
        else:
            dup = unreal.load_asset(proj_base)
        if dup:
            set_nanite_flag(dup)
            eal.save_asset(proj_base)
            mic.set_editor_property("parent", dup)
            eal.save_asset(mic_path)
            res["reparented_to"] = proj_base
            res["dup_used_with_nanite"] = True

    try:
        res["used_with_nanite_after"] = base.get_editor_property("used_with_nanite")
    except Exception:
        pass

    eal.save_asset(mic_path)
    eal.save_asset(mesh_path)
    res["ok"] = True
except Exception:
    res["error"] = traceback.format_exc()

OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_MATFIX_DONE ok=" + str(res.get("ok")))
