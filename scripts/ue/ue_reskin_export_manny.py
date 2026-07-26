"""scripts/ue/ue_reskin_export_manny.py — export the runtime SK_Mannequin body to FBX (weight-transfer source).

Produces artifacts/reskin_manny/manny_src/SKM_Manny.fbx = SK_Mannequin armature + skinned reference mesh
(110 vgroups). scripts/blender/reskin_manny_blender.py transfers these proven Epic weights onto the alien geometry.

MUST run with FULL RHI. `-nullrhi` hard-crashes FBX skeletal export (native crash, no python exception).
  UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript="scripts/ue/ue_reskin_export_manny.py" -stdout -unattended -nosplash
"""
import unreal, os
OUT_DIR = r"C:\Users\developer\Documents\Dimwit\artifacts\reskin_manny\manny_src"
os.makedirs(OUT_DIR, exist_ok=True)
ASSET = "/Game/Mannequins/Meshes/SKM_Manny"   # the runtime baseline body (WanefallPrototypeCharacter)
OUT = os.path.join(OUT_DIR, "SKM_Manny.fbx")
mesh = unreal.load_asset(ASSET)
task = unreal.AssetExportTask()
task.set_editor_property("object", mesh)
task.set_editor_property("filename", OUT)
task.set_editor_property("automated", True)
task.set_editor_property("prompt", False)
task.set_editor_property("replace_identical", True)
opt = unreal.FbxExportOption()
opt.set_editor_property("ascii", False)
opt.set_editor_property("collision", False)
opt.set_editor_property("level_of_detail", False)
task.set_editor_property("options", opt)
ok = unreal.Exporter.run_asset_export_task(task)
unreal.log("RESKIN_EXPORT ok=%s exists=%s skeleton=%s" % (ok, os.path.exists(OUT), mesh.skeleton.get_name()))
