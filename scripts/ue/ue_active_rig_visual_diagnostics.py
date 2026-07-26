"""Collect active rig material, texture, and ModeShell lighting diagnostics."""
import json
import traceback
from pathlib import Path

import unreal


ROOT = Path(r"C:/Users/developer/Documents/Dimwit")
OUT_DIR = ROOT / "artifacts" / "active_rig_visual_diagnostics"
OUT = OUT_DIR / "diagnostics.json"
PROJECT_MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
MAT = "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_01_vorlax_Rig"
RENDER_MATERIAL = "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4"
TEXTURES = {
    "albedo": "/Game/Wanefall/Dimwit/CharactersRigged/Textures/SM_Char_01_vorlax_Rig_albedo",
    "normal": "/Game/Wanefall/Dimwit/CharactersRigged/Textures/SM_Char_01_vorlax_Rig_normal",
    "ao": "/Game/Wanefall/Dimwit/CharactersRigged/Textures/SM_Char_01_vorlax_Rig_ao",
}


def path_name(obj):
    try:
        return obj.get_path_name() if obj else None
    except Exception:
        return None


def safe_prop(obj, name):
    try:
        value = obj.get_editor_property(name)
    except Exception:
        return None
    if hasattr(value, "get_path_name"):
        return value.get_path_name()
    return str(value)


def texture_info(path):
    asset = unreal.load_asset(path)
    info = {"path": path, "loaded": bool(asset), "class": type(asset).__name__ if asset else None}
    if asset:
        for prop in ("blueprint_get_size_x", "blueprint_get_size_y"):
            fn = getattr(asset, prop, None)
            if callable(fn):
                try:
                    info[prop.replace("blueprint_get_", "")] = int(fn())
                except Exception:
                    pass
        for prop in ("srgb", "compression_settings", "lod_group", "address_x", "address_y"):
            info[prop] = safe_prop(asset, prop)
    return info


def material_params(mic):
    info = {"loaded": bool(mic), "class": type(mic).__name__ if mic else None}
    if not mic:
        return info
    mel = unreal.MaterialEditingLibrary
    info["parent"] = path_name(safe_load_parent(mic))
    texture_names = [
        "BaseColorTexture",
        "BaseColor",
        "Diffuse",
        "NormalTexture",
        "OcclusionTexture",
        "AOTexture",
        "AmbientOcclusionTexture",
        "ORMTexture",
        "EmissiveTexture",
    ]
    scalar_names = [
        "Metallic",
        "Roughness",
        "Specular",
        "EmissiveStrength",
        "BaseColorFactor",
        "Opacity",
    ]
    vector_names = [
        "BaseColor",
        "BaseColorFactor",
        "EmissiveColor",
    ]
    info["textures"] = {}
    for name in texture_names:
        try:
            tex = mel.get_material_instance_texture_parameter_value(mic, name)
            if tex:
                info["textures"][name] = path_name(tex)
        except Exception:
            pass
    info["scalars"] = {}
    for name in scalar_names:
        try:
            info["scalars"][name] = float(mel.get_material_instance_scalar_parameter_value(mic, name))
        except Exception:
            pass
    info["vectors"] = {}
    for name in vector_names:
        try:
            color = mel.get_material_instance_vector_parameter_value(mic, name)
            if color:
                info["vectors"][name] = {
                    "r": float(color.r),
                    "g": float(color.g),
                    "b": float(color.b),
                    "a": float(color.a),
                }
        except Exception:
            pass
    return info


def material_asset_info(path):
    asset = unreal.load_asset(path)
    info = {"path": path, "loaded": bool(asset), "class": type(asset).__name__ if asset else None}
    if not asset:
        return info
    for prop in (
        "used_with_skeletal_mesh",
        "used_with_nanite",
        "used_with_static_lighting",
        "blend_mode",
        "shading_model",
        "two_sided",
    ):
        info[prop] = safe_prop(asset, prop)
    try:
        info["path_name"] = asset.get_path_name()
    except Exception:
        pass
    return info


def spawned_component_info():
    info = {"map": PROJECT_MAP}
    unreal.EditorLoadingAndSavingUtils.load_map(PROJECT_MAP)
    rig = unreal.load_asset(RIG)
    mat = unreal.load_asset(RENDER_MATERIAL)
    world = unreal.EditorLevelLibrary.get_editor_world()
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 200))
    try:
        comp = actor.skeletal_mesh_component
        if hasattr(comp, "set_skeletal_mesh_asset"):
            comp.set_skeletal_mesh_asset(rig)
        else:
            comp.set_skeletal_mesh(rig)
        info["num_materials_after_mesh"] = int(comp.get_num_materials())
        info["materials_after_mesh"] = [path_name(comp.get_material(i)) for i in range(comp.get_num_materials())]
        if mat:
            for i in range(comp.get_num_materials()):
                comp.set_material(i, mat)
        info["materials_after_override"] = [path_name(comp.get_material(i)) for i in range(comp.get_num_materials())]
    except Exception:
        info["error"] = traceback.format_exc()
    finally:
        if actor:
            unreal.EditorLevelLibrary.destroy_actor(actor)
    return info


def rig_info():
    rig = unreal.load_asset(RIG)
    info = {"path": RIG, "loaded": bool(rig)}
    if not rig:
        return info
    try:
        info["class"] = type(rig).__name__
        info["materials"] = [
            path_name(slot.get_editor_property("material_interface"))
            for slot in rig.get_editor_property("materials")
        ]
    except Exception as exc:
        info["material_error"] = repr(exc)
    return info


def safe_load_parent(mic):
    try:
        return mic.get_editor_property("parent")
    except Exception:
        return None


def map_lights():
    lights = []
    unreal.EditorLoadingAndSavingUtils.load_map(PROJECT_MAP)
    world = unreal.EditorLevelLibrary.get_editor_world()
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        comps = actor.get_components_by_class(unreal.LightComponentBase)
        if not comps:
            continue
        label = actor.get_actor_label()
        loc = actor.get_actor_location()
        for comp in comps:
            row = {
                "label": label,
                "class": type(comp).__name__,
                "location": {"x": loc.x, "y": loc.y, "z": loc.z},
            }
            for prop in ("intensity", "attenuation_radius", "source_radius", "temperature"):
                value = safe_prop(comp, prop)
                if value is not None:
                    row[prop] = value
            lights.append(row)
    return lights


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "ok": False,
        "material": material_params(unreal.load_asset(MAT)),
        "render_material": material_asset_info(RENDER_MATERIAL),
        "rig": rig_info(),
        "spawned_component": {},
        "textures": {name: texture_info(path) for name, path in TEXTURES.items()},
        "lights": [],
    }
    try:
        result["spawned_component"] = spawned_component_info()
        result["lights"] = map_lights()
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"DIMWIT_ACTIVE_RIG_VISUAL_DIAGNOSTICS ok={result['ok']} out={OUT}")


main()
