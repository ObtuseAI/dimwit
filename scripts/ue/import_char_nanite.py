"""Dimwit CHARACTER-FIDELITY fix: re-import the FULL-detail Hi3D mesh (no decimation) as a NANITE static mesh,
replacing the decimated 45k blob. The decimation is what destroyed the crisp armor panels (the coloring/detail
gap: in-game != the Hi3D creation). Nanite renders the full ~1M-vert mesh natively, so in-game matches the
source. Then re-apply the satin de-chrome (MetallicFactor 0.45) the import resets.

Default: Ekris (02). Verifies via artifacts/nanite_import_result.json (NOT exit code).
Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/import_char_nanite.py [name=02_ekris asset=SM_Char_02_ekris]"
"""
import unreal, json, shutil, sys
from pathlib import Path

ART = Path(r"C:/Users/developer/Documents/Dimwit/artifacts")
STAGE = ART / "nanite_staging"
RESULT = ART / "nanite_import_result.json"
CHARS = "/Game/Wanefall/Dimwit/Characters"
METALLIC_TARGET = 0.45

# args
src_name = "hi3d_02_ekris"      # source GLB stem in artifacts/
asset_name = "SM_Char_02_ekris" # destination asset name (must match the lobby C++ path)
for a in sys.argv:
    if a.startswith("src="):
        src_name = a.split("=", 1)[1]
    if a.startswith("asset="):
        asset_name = a.split("=", 1)[1]

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
res = {"ok": False, "asset": asset_name}

try:
    # 1) copy the full Hi3D GLB to a correctly-named staging file so the imported asset name matches
    STAGE.mkdir(parents=True, exist_ok=True)
    src_glb = ART / f"{src_name}.glb"
    staged = STAGE / f"{asset_name}.glb"
    shutil.copyfile(src_glb, staged)
    res["staged_glb"] = str(staged)
    res["src_size_mb"] = round(src_glb.stat().st_size / 1e6, 1)

    # clean up any prior double-nested folder from a bad dest (CHARS/asset/asset/...)
    doubled = f"{CHARS}/{asset_name}/{asset_name}"
    if eal.does_directory_exist(doubled):
        eal.delete_directory(doubled)
        res["cleaned_doubled"] = doubled

    # 2) import (replace the decimated asset in place). dest is the GROUP folder; Interchange nests as
    #    <dest>/<AssetName>/StaticMeshes/<AssetName>  — so dest must NOT include the asset name.
    dest = CHARS
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", str(staged))
    t.set_editor_property("destination_path", dest)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    tools.import_asset_tasks([t])

    # 3) find the imported StaticMesh, enable Nanite
    mesh_path = f"{CHARS}/{asset_name}/StaticMeshes/{asset_name}"
    mesh = unreal.load_asset(mesh_path)
    res["mesh_loaded"] = mesh is not None and isinstance(mesh, unreal.StaticMesh)
    if isinstance(mesh, unreal.StaticMesh):
        try:
            res["tris"] = mesh.get_num_triangles(0)
            res["verts"] = mesh.get_num_vertices(0)
        except Exception as e:
            res["tri_err"] = str(e)
        nanite_mode = None
        try:
            sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
            if hasattr(sub, "set_nanite_enabled"):
                sub.set_nanite_enabled(mesh, True)
                nanite_mode = "subsystem"
        except Exception as e:
            res["nanite_sub_err"] = str(e)
        if nanite_mode is None:
            try:
                ns = mesh.get_editor_property("nanite_settings")
                ns.set_editor_property("enabled", True)
                mesh.set_editor_property("nanite_settings", ns)
                nanite_mode = "property"
            except Exception as e:
                res["nanite_prop_err"] = str(e)
        res["nanite_mode"] = nanite_mode
        try:
            res["nanite_enabled"] = mesh.get_editor_property("nanite_settings").get_editor_property("enabled")
        except Exception:
            pass
        eal.save_asset(mesh_path)

    # 4) re-apply satin de-chrome on the new material instance
    mic_path = f"{CHARS}/{asset_name}/Materials/pbr_material"
    mic = unreal.load_asset(mic_path)
    if isinstance(mic, unreal.MaterialInstanceConstant):
        base = mic.get_base_material()
        names = [str(n) for n in mel.get_scalar_parameter_names(base)] if base else []
        for n in names:
            if n.lower() == "metallicfactor":
                mel.set_material_instance_scalar_parameter_value(mic, n, METALLIC_TARGET)
                res["metallic_set"] = METALLIC_TARGET
        try:
            mel.update_material_instance(mic)
        except Exception:
            pass
        eal.save_asset(mic_path)
    else:
        res["mic_warn"] = f"material not a MIC: {type(mic).__name__ if mic else 'None'}"

    res["ok"] = bool(res.get("mesh_loaded"))
except Exception:
    import traceback
    res["error"] = traceback.format_exc()

RESULT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_NANITE_IMPORT_DONE ok=" + str(res.get("ok")))
