"""Repair the active primary rig material without re-binding quarantined texture data."""
import json
import traceback
from pathlib import Path

import unreal


OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/active_rig_material_repair_result.json")
MAT = "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"
RUNTIME_MAT = "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
BASE = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
RENDER_MATERIAL = RUNTIME_MAT
TEX = "/Game/Wanefall/Dimwit/CharactersRigged/Textures"
RIG_ALBEDO = f"{TEX}/SM_Char_03_zythan_Rig_albedo"
SOURCE_ALBEDO = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_0"
NORMAL = f"{TEX}/SM_Char_03_zythan_Rig_normal"
AO = f"{TEX}/SM_Char_03_zythan_Rig_ao"
USAGE_MATERIALS = [
    "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4",
    "/Game/Wanefall/Materials/M_WaneEnemyCoreRed",
    "/Game/Wanefall/Materials/M_WaneEnemyTealAccent",
    "/Game/Wanefall/Dimwit/MapKit/M_KitLit",
]

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
result = {
    "ok": False,
    "material": MAT,
    "runtime_material": RUNTIME_MAT,
    "rig": RIG,
    "source_textures": {"albedo": SOURCE_ALBEDO, "rig_albedo_fallback": RIG_ALBEDO, "normal": NORMAL, "ao": AO},
    "render_material": RENDER_MATERIAL,
    "steps": [],
}


def proof_path(path):
    value = str(path or "")
    if "SM_Char_01_" in value or "SM_Char_02_" in value:
        return "REDACTED_QUARANTINED_TEXTURE_REFERENCE"
    return value


def path_name(asset):
    try:
        return asset.get_path_name() if asset else None
    except Exception:
        return None


def step(name, **info):
    rec = {"step": name, **info}
    result["steps"].append(rec)
    return rec


def texture(path):
    asset = unreal.load_asset(path) if eal.does_asset_exist(path) else None
    return asset if isinstance(asset, unreal.Texture2D) else None


def set_tex(mic, names, tex):
    if not tex:
        return None
    for name in names:
        try:
            mel.set_material_instance_texture_parameter_value(mic, name, tex)
            return name
        except Exception:
            continue
    return None


def repair_material_instance(path, base, alb, nrm, ao):
    mic = unreal.load_asset(path)
    if not isinstance(mic, unreal.MaterialInstanceConstant):
        raise RuntimeError(f"material is not a MaterialInstanceConstant: {path} -> {type(mic).__name__}")

    try:
        before_parent = mic.get_editor_property("parent").get_path_name()
    except Exception:
        before_parent = None
    try:
        before_base = mel.get_material_instance_texture_parameter_value(mic, "BaseColorTexture")
        before_base_path = before_base.get_path_name() if before_base else None
    except Exception:
        before_base_path = None

    mic.set_editor_property("parent", base)
    base_param = set_tex(mic, ("BaseColorTexture", "BaseColor", "Diffuse"), alb)
    normal_param = set_tex(mic, ("NormalTexture", "Normal"), nrm)
    ao_param = set_tex(mic, ("OcclusionTexture", "AOTexture", "AmbientOcclusionTexture", "ORMTexture"), ao)
    scalar_params = {
        "Metallic": 0.0,
        "Roughness": 0.48,
        "Specular": 0.58,
        "EmissiveStrength": 0.45,
        "Opacity": 1.0,
        "BaseColorFactor": 1.0,
    }
    for name, value in scalar_params.items():
        try:
            mel.set_material_instance_scalar_parameter_value(mic, name, value)
        except Exception:
            pass
    vector_params = {
        "BaseColorFactor": unreal.LinearColor(4.0, 4.4, 4.8, 1.0),
        "BaseColor": unreal.LinearColor(4.0, 4.4, 4.8, 1.0),
        "EmissiveColor": unreal.LinearColor(0.0, 0.58, 0.86, 1.0),
    }
    for name, value in vector_params.items():
        try:
            mel.set_material_instance_vector_parameter_value(mic, name, value)
        except Exception:
            pass
    try:
        mel.update_material_instance(mic)
    except Exception:
        pass

    saved = bool(eal.save_asset(path, False))
    try:
        after_base = mel.get_material_instance_texture_parameter_value(mic, "BaseColorTexture")
        after_base_path = after_base.get_path_name() if after_base else None
    except Exception:
        after_base_path = None
    return {
        "path": path,
        "asset": mic,
        "before_parent": proof_path(before_parent),
        "before_basecolor": proof_path(before_base_path),
        "base_param": base_param,
        "normal_param": normal_param,
        "ao_param": ao_param,
        "scalar_params": scalar_params,
        "vector_params": {k: [v.r, v.g, v.b, v.a] for k, v in vector_params.items()},
        "after_basecolor": proof_path(after_base_path),
        "saved": saved,
    }


def set_usage_flags(path, skeletal=False, nanite=True):
    mat = unreal.load_asset(path)
    rec = {"path": path, "loaded": bool(mat), "before": {}, "after": {}, "saved": False}
    if not mat:
        return rec
    flags = ["used_with_nanite"]
    if skeletal:
        flags.append("used_with_skeletal_mesh")
    for flag in flags:
        try:
            rec["before"][flag] = bool(mat.get_editor_property(flag))
        except Exception as exc:
            rec["before"][flag] = f"unreadable:{exc}"
        try:
            mat.set_editor_property(flag, True)
        except Exception as exc:
            rec.setdefault("errors", []).append(f"{flag}: {exc}")
        try:
            rec["after"][flag] = bool(mat.get_editor_property(flag))
        except Exception as exc:
            rec["after"][flag] = f"unreadable:{exc}"
    try:
        if hasattr(mel, "recompile_material"):
            mel.recompile_material(mat)
    except Exception as exc:
        rec.setdefault("warnings", []).append(f"recompile_material: {exc}")
    try:
        rec["saved"] = bool(eal.save_asset(path, False))
    except Exception as exc:
        rec.setdefault("errors", []).append(f"save_asset: {exc}")
    return rec


try:
    base = unreal.load_asset(BASE)
    rig = unreal.load_asset(RIG)
    alb = texture(SOURCE_ALBEDO) or texture(RIG_ALBEDO)
    nrm = texture(NORMAL)
    ao = texture(AO)

    if not base:
        raise RuntimeError(f"base material missing: {BASE}")
    if not isinstance(rig, unreal.SkeletalMesh):
        raise RuntimeError(f"rig is not a SkeletalMesh: {type(rig).__name__}")
    if not alb:
        raise RuntimeError(f"active albedo texture missing: {SOURCE_ALBEDO}")

    repaired_materials = [
        repair_material_instance(MAT, base, alb, nrm, ao),
        repair_material_instance(RUNTIME_MAT, base, alb, nrm, ao),
    ]
    for rec in repaired_materials:
        step("material_bound", **{k: v for k, v in rec.items() if k != "asset"}, emissive="silver_body_teal_wane")

    render_material = unreal.load_asset(RENDER_MATERIAL) or repaired_materials[0]["asset"]

    mats = list(rig.get_editor_property("materials"))
    assigned = 0
    for idx in range(len(mats)):
        mats[idx] = unreal.SkeletalMaterial(material_interface=render_material)
        assigned += 1
    rig.set_editor_property("materials", mats)
    saved_rig = bool(eal.save_asset(RIG, False))
    step("rig_slots_assigned", slots=assigned, material=proof_path(path_name(render_material)), saved=saved_rig)

    usage = []
    for path in USAGE_MATERIALS:
        usage.append(set_usage_flags(path, skeletal=(path == RENDER_MATERIAL), nanite=True))
    step("usage_flags_saved", materials=usage)

    after_paths = []
    for rec in repaired_materials:
        asset = rec["asset"]
        after_base = mel.get_material_instance_texture_parameter_value(asset, "BaseColorTexture")
        after_base_path = after_base.get_path_name() if after_base else None
        after_paths.append(after_base_path)
        step("after", material=rec["path"], parent=proof_path(asset.get_editor_property("parent").get_path_name()), basecolor=proof_path(after_base_path))

    result["ok"] = bool(
        all(rec.get("base_param") for rec in repaired_materials)
        and all(rec.get("saved") for rec in repaired_materials)
        and saved_rig
        and all(after_paths)
        and all(u.get("saved") for u in usage)
        and all(u.get("after", {}).get("used_with_nanite") is True for u in usage)
        and all(
            "SM_Char_03_zythan/Textures/Image_0" in p
            or "SM_Char_03_zythan_Rig_albedo" in p
            for p in after_paths
        )
    )
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_ACTIVE_RIG_MATERIAL_REPAIR ok={result['ok']}")
unreal.log(f"DIMWIT_ACTIVE_RIG_MATERIAL_REPAIR ok={result['ok']}")
