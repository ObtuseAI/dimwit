"""Dimwit RIGGING UE I/O helper.
  mode=export_mannequin out=<fbx>            -> export SK_Mannequin skeleton+mesh to FBX (Blender reference rig)
  mode=import_skeletal fbx=<fbx> asset=<name> -> import a rigged FBX as a Skeletal Mesh on the UE5 skeleton

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_rig_io.py mode=... ..."
Result -> artifacts/rig_io_result.json
"""
import unreal, json, sys, traceback
from pathlib import Path

RESULT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_io_result.json")
SK_MANN = "/Game/Mannequins/Meshes/SKM_Manny"                    # the UE5 SkeletalMesh (mesh, not skeleton)
SK_MANN_SKEL = "/Game/Mannequins/Meshes/SK_Mannequin"            # the shared USkeleton asset
DEST = "/Game/Wanefall/Dimwit/CharactersRigged"

A = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv if "=" in a}
res = {"mode": A.get("mode"), "ok": False}
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def export_mannequin(out):
    sk = unreal.load_asset(SK_MANN)
    assert isinstance(sk, unreal.SkeletalMesh), f"SK_Mannequin not found at {SK_MANN}"
    task = unreal.AssetExportTask()
    task.set_editor_property("object", sk)
    task.set_editor_property("filename", out)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    try:
        task.set_editor_property("exporter", unreal.SkeletalMeshExporterFBX())
        task.set_editor_property("options", unreal.FbxExportOption())
    except Exception as e:
        res["exporter_warn"] = str(e)
    unreal.Exporter.run_asset_export_task(task)
    res["out"] = out
    res["exists"] = Path(out).exists()
    return res["exists"]


def import_skeletal(fbx, asset):
    skel = None
    for cand in (SK_MANN_SKEL, "/Game/Mannequins/Meshes/SK_Mannequin",
                 "/Game/Characters/Mannequins/Meshes/SK_Mannequin"):
        o = unreal.load_asset(cand)
        if isinstance(o, unreal.Skeleton):
            skel = o
            break
    if skel is None:
        sk = unreal.load_asset(SK_MANN)
        skel = sk.get_editor_property("skeleton") if sk else None
    res["skeleton"] = skel.get_path_name() if skel else None

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", asset)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", True)
    ui.set_editor_property("import_materials", True)
    ui.set_editor_property("import_animations", False)
    if skel:
        ui.set_editor_property("skeleton", skel)
    ui.skeletal_mesh_import_data.set_editor_property("import_morph_targets", False)
    task.set_editor_property("options", ui)
    tools.import_asset_tasks([task])
    imported = list(task.get_editor_property("imported_object_paths") or [])
    res["imported"] = imported
    return bool(imported)


try:
    mode = A.get("mode")
    if mode == "export_mannequin":
        res["ok"] = export_mannequin(A["out"])
    elif mode == "import_skeletal":
        res["ok"] = import_skeletal(A["fbx"], A.get("asset", "SK_RChar"))
    else:
        res["error"] = f"unknown mode: {mode}"
except Exception:
    res["error"] = traceback.format_exc()

RESULT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_RIG_IO_DONE ok=" + str(res.get("ok")))
