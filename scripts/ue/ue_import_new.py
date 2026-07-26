import unreal, glob, os
tools=unreal.AssetToolsHelpers.get_asset_tools()
GROUPS={"SM_Char_":"/Game/Wanefall/Dimwit/Characters","SM_Wpn_":"/Game/Wanefall/Dimwit/Weapons","SM_Veh_":"/Game/Wanefall/Dimwit/Vehicles"}
files=sorted(glob.glob(r"C:/Users/developer/Documents/Dimwit/artifacts/ue_staging_new/*.glb"))
done=0
for f in files:
    base=os.path.basename(f)
    dest=next((d for p,d in GROUPS.items() if base.startswith(p)), None)
    if not dest: continue
    t=unreal.AssetImportTask()
    t.set_editor_property("filename",f); t.set_editor_property("destination_path",dest)
    t.set_editor_property("automated",True); t.set_editor_property("replace_existing",True); t.set_editor_property("save",True)
    tools.import_asset_tasks([t])  # one-at-a-time + save (avoids async-build truncation)
    unreal.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=True, recursive=True)
    done+=1
unreal.log(f"DIMWIT_NEW_IMPORT_DONE imported={done}")
