import unreal, glob, os
tools=unreal.AssetToolsHelpers.get_asset_tools()
files=sorted(glob.glob(r"C:/Users/developer/Documents/Dimwit/artifacts/ue_staging_fix/*.glb"))
dest="/Game/Wanefall/Dimwit/Weapons"
tasks=[]
for f in files:
    t=unreal.AssetImportTask()
    t.set_editor_property("filename",f); t.set_editor_property("destination_path",dest)
    t.set_editor_property("automated",True); t.set_editor_property("replace_existing",True); t.set_editor_property("save",True)
    tasks.append(t)
for t in tasks:  # import ONE at a time + save each (avoids the batch async-build truncation)
    tools.import_asset_tasks([t])
    unreal.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=True, recursive=True)
unreal.log(f"DIMWIT_FIX_DONE imported={len(tasks)}")
