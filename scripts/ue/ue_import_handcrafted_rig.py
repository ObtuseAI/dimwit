"""Dimwit IMPORT HANDCRAFTED RIG (UE headless) — land the handcrafted clean-topology character in-game: import
the rigged low-poly as a SkeletalMesh bound to SK_Mannequin (so ABP_Manny drives it), import the baked NORMAL
(green-flipped for UE) + AO maps, and wire them into the rigged material. Replaces the old disfigured rig so the
in-game character stops morphing. Writes artifacts/import_handcrafted_result.json.

  UnrealEditor-Cmd <uproj> -ExecutePythonScript="scripts/ue/ue_import_handcrafted_rig.py rig=<rigged.fbx> normal=<n.png> ao=<a.png> name=SM_Char_02_ekris_Rig mat=/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"
"""
import unreal, json, sys, traceback
from pathlib import Path

A = {}
for a in sys.argv:
    if "=" in a and not a.startswith("-"):
        k, v = a.split("=", 1)
        A[k] = v
RIG = A["rig"]
NORMAL = A.get("normal")
AO = A.get("ao")
ALBEDO = A.get("albedo")
NAME = A.get("name", "SM_Char_02_ekris_Rig")
DEST = A.get("dest", "/Game/Wanefall/Dimwit/CharactersRigged")
TEXDEST = DEST + "/Textures"
MAT = A.get("mat", "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material")
SK_MANN = "/Game/Mannequins/Meshes/SK_Mannequin"
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/import_handcrafted_result.json")

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
out = {"ok": False, "name": NAME}


def import_texture(png, name, is_normal):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", png)
    t.set_editor_property("destination_path", TEXDEST)
    t.set_editor_property("destination_name", name)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    tools.import_asset_tasks([t])
    tex = unreal.load_asset(f"{TEXDEST}/{name}")
    if isinstance(tex, unreal.Texture2D):
        try:
            if is_normal:
                tex.set_editor_property("srgb", False)
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                tex.set_editor_property("flip_green_channel", True)   # Blender(OpenGL) -> UE(DirectX)
            else:
                tex.set_editor_property("srgb", False)
            eal.save_asset(f"{TEXDEST}/{name}")
        except Exception:
            pass
    return tex


try:
    # 1) skeletal import bound to SK_Mannequin (so ABP_Manny drives it)
    skel = unreal.load_asset(SK_MANN)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", RIG)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", NAME)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", True)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("import_animations", False)
    if isinstance(skel, unreal.Skeleton):
        ui.set_editor_property("skeleton", skel)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    try:
        sk_data = ui.skeletal_mesh_import_data
        sk_data.set_editor_property("import_morph_targets", False)
        # COMPUTE normals+tangents from the mesh+UVs (Blender FBX lacks tangents; this also guarantees a correct
        # tangent basis for the baked normal map and ensures the UV channel is used).
        sk_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_COMPUTE_NORMALS)
    except Exception:
        pass
    task.set_editor_property("options", ui)
    tools.import_asset_tasks([task])
    rig_path = f"{DEST}/{NAME}"
    rmesh = unreal.load_asset(rig_path)
    out["rig_imported"] = isinstance(rmesh, unreal.SkeletalMesh)
    if isinstance(rmesh, unreal.SkeletalMesh):
        s = rmesh.get_editor_property("skeleton")
        out["rig_skeleton"] = s.get_path_name() if s else None
        out["rig_bounds_cm"] = round(rmesh.get_bounds().box_extent.z * 2.0, 1)

    # 2) baked maps
    ntex = import_texture(NORMAL, f"{NAME}_normal", True) if NORMAL else None
    atex = import_texture(AO, f"{NAME}_ao", False) if AO else None
    btex = import_texture(ALBEDO, f"{NAME}_albedo", False) if ALBEDO else None
    if isinstance(btex, unreal.Texture2D):
        try:
            btex.set_editor_property("srgb", True)        # base color is sRGB
            eal.save_asset(f"{TEXDEST}/{NAME}_albedo")
        except Exception:
            pass
    out["normal_imported"] = isinstance(ntex, unreal.Texture2D)
    out["ao_imported"] = isinstance(atex, unreal.Texture2D)
    out["albedo_imported"] = isinstance(btex, unreal.Texture2D)

    # 3) wire into the rigged material (per-char). Create it from the glTF base if missing (roster batch).
    GLTF_BASE = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
    if not eal.does_asset_exist(MAT):
        try:
            eal.duplicate_asset(GLTF_BASE, MAT)
        except Exception:
            pass
    mic = unreal.load_asset(MAT)
    if isinstance(mic, unreal.MaterialInstanceConstant):
        if btex:
            try:
                mel.set_material_instance_texture_parameter_value(mic, "BaseColorTexture", btex)
            except Exception:
                pass
        if ntex:
            for pn in ("NormalTexture", "Normal"):
                try:
                    mel.set_material_instance_texture_parameter_value(mic, pn, ntex); break
                except Exception:
                    continue
        if atex:
            for pn in ("OcclusionTexture", "AOTexture", "AmbientOcclusionTexture", "ORMTexture"):
                try:
                    mel.set_material_instance_texture_parameter_value(mic, pn, atex); break
                except Exception:
                    continue
        for nm, val in (("Metallic", 0.0), ("Roughness", 0.5), ("Specular", 0.5)):
            try:
                mel.set_material_instance_scalar_parameter_value(mic, nm, val)
            except Exception:
                pass
        # assign the material to the rig's slot
        try:
            if isinstance(rmesh, unreal.SkeletalMesh):
                mats = rmesh.materials
                for i in range(len(mats)):
                    mats[i] = unreal.SkeletalMaterial(material_interface=mic)
                rmesh.set_editor_property("materials", mats)
        except Exception:
            pass
        try:
            mel.update_material_instance(mic)
        except Exception:
            pass
        eal.save_asset(MAT)
        eal.save_asset(rig_path)
        out["material_wired"] = True

    out["ok"] = bool(out.get("rig_imported"))
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_IMPORT_HANDCRAFTED_DONE ok=" + str(out.get("ok")))
