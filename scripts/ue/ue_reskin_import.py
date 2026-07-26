"""scripts/ue/ue_reskin_import.py — import the re-skinned alien FBXs onto the EXISTING SK_Mannequin skeleton.

Imports each artifacts/reskin_manny/<char>_reskin.fbx to /Game/Wanefall/Dimwit/CharactersRigged/<Char>_ReskinManny,
selecting the existing /Game/Mannequins/Meshes/SK_Mannequin skeleton so they share ABP_Manny + hand sockets.
NON-DESTRUCTIVE: distinct *_ReskinManny names — never overwrites the certified SM_Char_0X_*_Rig.

Expected result per char: shares_SKMannequin=True, extent z~=90 (=~180cm; meter->cm round-trip). Run with FULL RHI.
"""
import unreal, os, traceback
RESKIN_DIR = r"C:\Users\developer\Documents\Dimwit\artifacts\reskin_manny"
DEST = "/Game/Wanefall/Dimwit/CharactersRigged"
SKELETON = "/Game/Mannequins/Meshes/SK_Mannequin"
CHARS = ["zythan","qorin","therak","ullio","kelous","nexor"]
skel = unreal.load_asset(SKELETON)
tools = unreal.AssetToolsHelpers.get_asset_tools()
for c in CHARS:
    fbx = os.path.join(RESKIN_DIR, c + "_reskin.fbx")
    name = c.capitalize() + "_ReskinManny"
    if not os.path.exists(fbx):
        unreal.log_warning("RESKIN_IMPORT [%s] missing fbx" % c); continue
    try:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", fbx)
        task.set_editor_property("destination_path", DEST)
        task.set_editor_property("destination_name", name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        ui = unreal.FbxImportUI()
        ui.set_editor_property("import_mesh", True)
        ui.set_editor_property("import_as_skeletal", True)
        ui.set_editor_property("import_animations", False)
        ui.set_editor_property("import_materials", False)
        ui.set_editor_property("import_textures", False)
        ui.set_editor_property("create_physics_asset", True)
        ui.set_editor_property("skeleton", skel)
        ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        sid = ui.skeletal_mesh_import_data
        sid.set_editor_property("import_morph_targets", False)
        sid.set_editor_property("use_t0_as_ref_pose", True)
        sid.set_editor_property("convert_scene", True)
        sid.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        task.set_editor_property("options", ui)
        tools.import_asset_tasks([task])
        m = unreal.load_asset(DEST + "/" + name)
        if m and isinstance(m, unreal.SkeletalMesh):
            b = m.get_bounds().box_extent
            unreal.log("RESKIN_IMPORT [%s] OK skeleton=%s extent_z=%.1f shares=%s" % (
                c, m.skeleton.get_name(), b.z, m.skeleton.get_name()=="SK_Mannequin"))
        else:
            unreal.log_error("RESKIN_IMPORT [%s] load-back fail" % c)
    except Exception:
        unreal.log_error("RESKIN_IMPORT [%s] %s" % (c, traceback.format_exc()))
