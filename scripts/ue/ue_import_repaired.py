"""Dimwit: import the 3 repaired meshes (grenades 03/04 base-trimmed, nightwire leg-symmetrized) into UE,
replacing the defective assets. Verifies via artifacts/import_repaired_result.json (not exit code)."""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/import_repaired_result.json")
REP = r"C:/Users/developer/Documents/Dimwit/artifacts/repaired"
JOBS = [
    ("SM_Wpn_Gren_03_Wane_Spike", "/Game/Wanefall/Dimwit/Weapons"),
    ("SM_Wpn_Gren_04_Null_Pin", "/Game/Wanefall/Dimwit/Weapons"),
    ("SM_Char_Mech_08_Nightwire", "/Game/Wanefall/Dimwit/Characters"),
]
tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
out = {"records": []}
try:
    for name, dest in JOBS:
        glb = f"{REP}/{name}.glb"
        rec = {"name": name, "dest": dest, "glb_exists": Path(glb).exists()}
        if rec["glb_exists"]:
            doubled = f"{dest}/{name}/{name}"
            if eal.does_directory_exist(doubled):
                eal.delete_directory(doubled)
            t = unreal.AssetImportTask()
            t.set_editor_property("filename", glb)
            t.set_editor_property("destination_path", dest)
            t.set_editor_property("automated", True)
            t.set_editor_property("replace_existing", True)
            t.set_editor_property("save", True)
            tools.import_asset_tasks([t])
            rec["imported"] = eal.does_asset_exist(f"{dest}/{name}/StaticMeshes/{name}")
        out["records"].append(rec)
    out["ok"] = all(r.get("imported") for r in out["records"])
except Exception:
    out["error"] = traceback.format_exc()
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_IMPORT_REPAIRED_DONE ok=" + str(out.get("ok")))
