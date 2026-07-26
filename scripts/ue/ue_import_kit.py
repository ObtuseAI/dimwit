import unreal, glob, os
tools = unreal.AssetToolsHelpers.get_asset_tools()
DEST = "/Game/Wanefall/Dimwit/MapKit"
files = sorted(glob.glob(r"C:/Users/developer/Documents/Dimwit/artifacts/kit_out/*.glb"))
done = 0
for f in files:
    name = os.path.splitext(os.path.basename(f))[0]
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", f); t.set_editor_property("destination_path", DEST)
    t.set_editor_property("automated", True); t.set_editor_property("replace_existing", True); t.set_editor_property("save", True)
    tools.import_asset_tasks([t])
    # Make the kit solid: use the render geometry as collision so floor/walls/cover block (survives re-import).
    m = unreal.load_asset(f"{DEST}/{name}/StaticMeshes/{name}")
    if m:
        try:
            bs = m.get_editor_property("body_setup")
            if bs:
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                unreal.EditorAssetLibrary.save_loaded_asset(m)
        except Exception as e:
            unreal.log_warning(f"collision {name}: {e}")
    unreal.EditorAssetLibrary.save_directory(DEST, only_if_is_dirty=True, recursive=True)
    done += 1
unreal.log(f"WANEFALL_KIT_IMPORT_DONE imported={done}")
