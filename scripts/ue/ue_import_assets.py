"""UE headless import: bring the Hi3D-generated GLBs into WanefallGreybox as StaticMeshes + materials.
Run via: UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript="<this>" -unattended -nosplash
Imports into isolated /Game/Wanefall/Dimwit/<cat>/ so nothing existing is touched.
"""
import unreal, os, glob, json

STAGING = r"C:/Users/developer/Documents/Dimwit/artifacts/ue_staging"
GROUPS = {
    "Characters": "SM_Char_*.glb",
    "Vehicles":   "SM_Veh_*.glb",
    "Weapons":    "SM_Wpn_*.glb",
}
RESULT = r"C:/Users/developer/Documents/Dimwit/artifacts/ue_import_result.json"
tools = unreal.AssetToolsHelpers.get_asset_tools()
report = {}

for grp, pat in GROUPS.items():
    files = sorted(glob.glob(os.path.join(STAGING, pat)))
    if not files:
        continue
    dest = f"/Game/Wanefall/Dimwit/{grp}"
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    unreal.log(f"[DIMWIT] importing {len(tasks)} -> {dest}")
    tools.import_asset_tasks(tasks)
    try:
        unreal.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=False, recursive=True)
    except Exception as e:
        unreal.log_warning(f"[DIMWIT] save_directory {dest}: {e}")
    assets = list(unreal.EditorAssetLibrary.list_assets(dest, recursive=True)) if unreal.EditorAssetLibrary.does_directory_exist(dest) else []
    report[grp] = assets
    unreal.log(f"[DIMWIT] {grp}: {len(assets)} assets now under {dest}")

try:
    with open(RESULT, "w") as fh:
        json.dump(report, fh, indent=2)
except Exception as e:
    unreal.log_warning(f"[DIMWIT] result write: {e}")
total = sum(len(v) for v in report.values())
unreal.log(f"DIMWIT_IMPORT_DONE total_assets={total} groups={list(report.keys())}")
