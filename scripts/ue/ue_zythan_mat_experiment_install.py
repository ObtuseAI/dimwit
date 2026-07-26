"""ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1 - session 1: build variant materials + install displays.

The optics judge consistently reads the in-game zythan as "flat silver, seams washed" while the
rig-baked 4K albedo is deep violet with black seam lines and cyan gems. Prime suspect: the
material's CONSTANT violet emissive (0.21,0.15,0.52)x0.25 flooding every pixel - it lifts the
dark seams (~0.03 albedo) by ~0.1 and crushes exactly the contrast that defines the character.
Second suspect: broad specular sheen (metallic 0.1 / roughness 0.55) under the bright menu room.

This installs an A/B/C/D row of SAVED display actors (capture law: only saved map content
renders truthfully) in the exposure-proven PlayerStart menu area, each with one variant:
  E0_CTRL  - current production graph (control)
  E1_EM0   - emissive removed entirely (pure lit albedo)
  E2_EMALB - emissive = albedo x 0.15 (self-colored: cyan gems glow, seams stay dark)
  E3_SHEEN - emissive off + metallic 0.0 / roughness 0.7 (isolates the specular term)

Session 2 (scripts/ue/ue_zythan_mat_experiment_capture.py, -NoTextureStreaming) photographs the row.
Cleanup after the verdict: scripts/ue/ue_zythan_mat_experiment_cleanup.py removes displays + variant assets.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_mat_experiment_install.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_mat_experiment/install_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
DEST_DIR = "/Game/Wanefall/Dimwit/CharactersRigged"
RIG = f"{DEST_DIR}/SM_Char_03_zythan_Rig"
ALBEDO = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_albedo"
NORMAL = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_normal"
AO = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_ao"
IDLE_ANIM = "/Game/Mannequins/Animations/Manny/MM_Idle"

# name -> dict(metallic, roughness, emissive: None | ("const", strength) | ("albedo", strength))
VARIANTS = [
    ("E0_CTRL",  dict(metallic=0.1, roughness=0.55, emissive=("const", 0.25))),
    ("E1_EM0",   dict(metallic=0.1, roughness=0.55, emissive=None)),
    ("E2_EMALB", dict(metallic=0.1, roughness=0.55, emissive=("albedo", 0.15))),
    ("E3_SHEEN", dict(metallic=0.0, roughness=0.70, emissive=None)),
]

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "map": MAP, "variants": {}, "displays": []}


def build_variant(name, spec):
    mat_name = f"M_ZythanRigShip_EXP_{name}"
    mat_path = f"{DEST_DIR}/{mat_name}"
    if eal.does_asset_exist(mat_path):
        eal.delete_asset(mat_path)  # in-place expression clearing hard-crashes headless editors
    mat = tools.create_asset(mat_name, DEST_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if not isinstance(mat, unreal.Material):
        raise RuntimeError(f"variant create failed: {mat_name}")

    alb = unreal.load_asset(ALBEDO)
    tex_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, -200)
    tex_node.set_editor_property("texture", alb)
    mel.connect_material_property(tex_node, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    ao = unreal.load_asset(AO) if eal.does_asset_exist(AO) else None
    if isinstance(ao, unreal.Texture2D):
        ao_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, -20)
        ao_node.set_editor_property("texture", ao)
        mel.connect_material_property(ao_node, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

    metal_node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -420, 140)
    metal_node.set_editor_property("r", spec["metallic"])
    mel.connect_material_property(metal_node, "", unreal.MaterialProperty.MP_METALLIC)
    rough_node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -420, 220)
    rough_node.set_editor_property("r", spec["roughness"])
    mel.connect_material_property(rough_node, "", unreal.MaterialProperty.MP_ROUGHNESS)

    emis = spec["emissive"]
    if emis is not None:
        kind, strength = emis
        emis_strength = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -700, 460)
        emis_strength.set_editor_property("r", strength)
        emis_mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -420, 380)
        if kind == "const":
            emis_col = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -700, 320)
            emis_col.set_editor_property("constant", unreal.LinearColor(0.21, 0.15, 0.52, 1.0))
            mel.connect_material_expressions(emis_col, "", emis_mul, "A")
        else:  # albedo-modulated self-glow: bright cyan gems glow cyan, dark seams stay dark
            emis_tex = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, 320)
            emis_tex.set_editor_property("texture", alb)
            mel.connect_material_expressions(emis_tex, "RGB", emis_mul, "A")
        mel.connect_material_expressions(emis_strength, "", emis_mul, "B")
        mel.connect_material_property(emis_mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    nrm = unreal.load_asset(NORMAL) if eal.does_asset_exist(NORMAL) else None
    if isinstance(nrm, unreal.Texture2D):
        nrm_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, 620)
        nrm_node.set_editor_property("texture", nrm)
        nrm_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        mel.connect_material_property(nrm_node, "", unreal.MaterialProperty.MP_NORMAL)

    for flag in ("used_with_skeletal_mesh", "used_with_morph_targets"):
        try:
            mat.set_editor_property(flag, True)
        except Exception:
            pass
    mel.recompile_material(mat)
    if not eal.save_asset(mat_path, False):
        raise RuntimeError(f"variant save failed: {mat_path}")
    return mat, mat_path


try:
    built = {}
    for name, spec in VARIANTS:
        mat, mat_path = build_variant(name, spec)
        built[name] = mat
        result["variants"][name] = {"path": mat_path, "spec": {k: str(v) for k, v in spec.items()}}

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)
    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location()
            break
    sk = unreal.load_asset(RIG)
    if not isinstance(sk, unreal.SkeletalMesh):
        raise RuntimeError("active rig not a SkeletalMesh")
    anim = unreal.load_asset(IDLE_ANIM)

    existing = {a.get_actor_label(): a for a in eas.get_all_level_actors()
                if isinstance(a, unreal.SkeletalMeshActor)}
    for i, (name, _spec) in enumerate(VARIANTS):
        label = f"RigMatExperiment_{name}"
        # negative-y row, 400 apart: outside each variant's own 42-degree/430-unit frame,
        # same exposure-proven menu area, same rotation as the production displays
        loc = base + unreal.Vector(0.0, -400.0 * (i + 1), 0.0)
        actor = existing.get(label)
        if actor is None:
            actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, loc, unreal.Rotator(0, 0, 180))
            actor.set_actor_label(label)
        else:
            actor.set_actor_location(loc, False, False)
        comp = actor.skeletal_mesh_component
        (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
        if anim:
            comp.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            try:
                data = comp.get_editor_property("animation_data")
                data.set_editor_property("anim_to_play", anim)
                data.set_editor_property("saved_position", 0.3)
                data.set_editor_property("saved_play_rate", 0.0)
                comp.set_editor_property("animation_data", data)
            except Exception as exc:
                result.setdefault("warnings", []).append(f"{label} animation_data: {exc!r}")
        comp.set_material(0, built[name])
        result["displays"].append({"label": label, "location": [loc.x, loc.y, loc.z],
                                   "material": result["variants"][name]["path"]})

    saved = les.save_current_level()
    result["map_saved"] = bool(saved)
    result["ok"] = bool(saved)
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("MAT_EXPERIMENT_INSTALL:", json.dumps(result)[:500])
