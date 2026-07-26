"""Build a BASE Material for the active rig and assign it (ACTIVE_RIG_MATERIAL_TRUTH_REPAIR_V1).

PROBE-PROVEN ROOT CAUSE: in the tick-less headless capture sessions the validation probe uses,
MaterialInstance parameter overrides never reach the renderer - every MIC-driven surface (all
character materials, static AND rigged, import-baked or scripted) renders with the glTF parent
DEFAULTS: metallic 1.0, white base -> white metal mirroring a white studio = the white_debug
REJECT. Base-Material expression graphs render correctly in the same sessions (the map's floor,
pads, and backdrop prove it in every capture).

Fix: M_ZythanRigShip - a project-owned base Material wiring rig-baked albedo/AO/normal with
metallic 0.1 / roughness 0.55, flagged for skeletal + morph usage, assigned to the rig's slot.
This also makes the rig render identically in game and in captures.

NO EMISSIVE (ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1, 2026-07-02): the earlier constant violet
emissive (0.21,0.15,0.52)x0.25 flooded every pixel, lifting the dark seam lines by ~0.1 and
washing the deep-violet carapace to flat silver - the optics judge failed exactly that. A/B/C/D
saved-display experiment (artifacts/zythan_mat_experiment/): control reproduced the wash;
emissive-removed rendered reference-grade (deep violet, black seams crisp, cyan gems reading
through albedo alone - the hero reference itself has no glow flood). Do not re-add a constant
emissive; if glow is ever wanted, modulate by albedo so seams stay dark.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_rig_base_material_build.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_rig_base_material_build_result.json")
DEST_DIR = "/Game/Wanefall/Dimwit/CharactersRigged"
MAT_NAME = "M_ZythanRigShip"
MAT_PATH = f"{DEST_DIR}/{MAT_NAME}"
RIG = f"{DEST_DIR}/SM_Char_03_zythan_Rig"
# RIG-BAKED texture set: the rig has its own UV layout, so the source mesh's Image_0 samples as
# misaligned noise on it (optics REJECT: "paneling lines missing / low-res noise"). The baked set
# under CharactersRigged/Textures matches the rig UVs.
ALBEDO = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_albedo"
NORMAL = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_normal"
AO = f"{DEST_DIR}/Textures/SM_Char_03_zythan_Rig_ao"

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "material": MAT_PATH, "steps": []}

try:
    if eal.does_asset_exist(MAT_PATH):
        # rebuild from scratch: clearing expressions in-place hard-crashes the headless editor
        eal.delete_asset(MAT_PATH)
        result["steps"].append("previous material deleted for clean rebuild")
    mat = tools.create_asset(MAT_NAME, DEST_DIR, unreal.Material, unreal.MaterialFactoryNew())
    result["steps"].append("material created")
    if not isinstance(mat, unreal.Material):
        raise RuntimeError(f"could not create/load base material: {type(mat).__name__ if mat else None}")

    # base color: the rig-baked albedo straight through (it already carries the reference coloring;
    # a tint multiply on top double-darkens and hides the paneling)
    alb = unreal.load_asset(ALBEDO)
    if not isinstance(alb, unreal.Texture2D):
        raise RuntimeError(f"rig-baked albedo missing: {ALBEDO}")
    tex_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, -200)
    tex_node.set_editor_property("texture", alb)
    mel.connect_material_property(tex_node, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    result["steps"].append("basecolor wired: rig-baked albedo (UV-matched)")

    ao = unreal.load_asset(AO) if eal.does_asset_exist(AO) else None
    if isinstance(ao, unreal.Texture2D):
        ao_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, -20)
        ao_node.set_editor_property("texture", ao)
        mel.connect_material_property(ao_node, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
        result["steps"].append("rig-baked AO wired")

    metal_node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -420, 140)
    metal_node.set_editor_property("r", 0.1)
    mel.connect_material_property(metal_node, "", unreal.MaterialProperty.MP_METALLIC)
    rough_node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -420, 220)
    rough_node.set_editor_property("r", 0.55)
    mel.connect_material_property(rough_node, "", unreal.MaterialProperty.MP_ROUGHNESS)
    result["steps"].append("metallic 0.1 / roughness 0.55 wired")

    # emissive intentionally absent - the constant violet flood washed seam contrast to silver
    # (experiment-proven 2026-07-02, artifacts/zythan_mat_experiment/)
    result["steps"].append("no emissive (E1_EM0 experiment winner)")

    nrm = unreal.load_asset(NORMAL) if eal.does_asset_exist(NORMAL) else None
    if isinstance(nrm, unreal.Texture2D):
        nrm_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -700, 620)
        nrm_node.set_editor_property("texture", nrm)
        nrm_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        mel.connect_material_property(nrm_node, "", unreal.MaterialProperty.MP_NORMAL)
        result["steps"].append("normal map wired")

    for flag in ("used_with_skeletal_mesh", "used_with_morph_targets"):
        try:
            mat.set_editor_property(flag, True)
        except Exception as exc:
            result["steps"].append(f"usage flag {flag} failed: {exc!r}")
    mel.recompile_material(mat)
    saved = eal.save_asset(MAT_PATH, False)
    result["material_saved"] = bool(saved)

    rig = unreal.load_asset(RIG)
    if not isinstance(rig, unreal.SkeletalMesh):
        raise RuntimeError(f"rig not a SkeletalMesh: {type(rig).__name__ if rig else None}")
    mats = rig.materials
    new_mats = []
    for m in mats:
        new_mats.append(unreal.SkeletalMaterial(material_interface=mat,
                                                material_slot_name=m.material_slot_name))
    rig.set_editor_property("materials", new_mats)
    rig_saved = eal.save_asset(RIG, False)
    result["rig_slots_assigned"] = len(new_mats)
    result["rig_saved"] = bool(rig_saved)
    result["ok"] = bool(saved) and bool(rig_saved)
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("BASE_MAT_RESULT:", json.dumps(result)[:500])
