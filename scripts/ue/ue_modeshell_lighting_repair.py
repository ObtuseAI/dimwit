"""Repair authoritative ModeShell lighting for validator-visible rig captures.

This script edits only Wanefall_ModeShell_Prototype_01. It is intentionally
idempotent: previously spawned validation lights are removed by label before
the current proof lights are recreated.
"""
import json
import traceback
from pathlib import Path

import unreal


MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/modeshell_lighting_repair_result.json")
LABEL_PREFIX = "ModeShellValidation"
LOBBY_GAME_MODE = "/Script/WanefallGreybox.WanefallLobbyGameMode"

result = {
    "ok": False,
    "map": MAP,
    "removed_validation_actors": [],
    "disabled_realtime_capture": [],
    "world_game_mode": None,
    "lights": [],
    "backdrops": [],
    "base": None,
    "errors": [],
}


def log_error(label, exc):
    result["errors"].append({"step": label, "error": repr(exc)})


def actor_label(actor):
    try:
        return actor.get_actor_label()
    except Exception:
        return str(actor.get_name())


def set_label(actor, label):
    try:
        actor.set_actor_label(label)
    except Exception as exc:
        log_error(f"label:{label}", exc)


def set_movable(component):
    if not component:
        return
    try:
        component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    except Exception:
        try:
            component.set_mobility(unreal.ComponentMobility.MOVABLE)
        except Exception as exc:
            log_error(f"movable:{type(component).__name__}", exc)


def set_intensity(component, value):
    if not component:
        return
    try:
        component.set_intensity(value)
    except Exception:
        component.set_editor_property("intensity", value)


def set_color(component, rgba):
    if not component:
        return
    try:
        component.set_light_color(unreal.LinearColor(rgba[0] / 255.0, rgba[1] / 255.0, rgba[2] / 255.0, rgba[3] / 255.0))
    except Exception as exc:
        log_error(f"color:{type(component).__name__}", exc)


def record_light(actor, component, kind):
    entry = {
        "label": actor_label(actor),
        "kind": kind,
        "location": str(actor.get_actor_location()),
        "rotation": str(actor.get_actor_rotation()),
    }
    try:
        entry["intensity"] = component.get_editor_property("intensity")
    except Exception:
        pass
    try:
        entry["attenuation_radius"] = component.get_editor_property("attenuation_radius")
    except Exception:
        pass
    result["lights"].append(entry)


def disable_realtime_skylight_capture(actor):
    component = actor.get_component_by_class(unreal.SkyLightComponent)
    if not component:
        return
    before = None
    try:
        before = bool(component.get_editor_property("real_time_capture"))
    except Exception:
        pass
    try:
        component.set_editor_property("real_time_capture", False)
        result["disabled_realtime_capture"].append({
            "label": actor_label(actor),
            "before": before,
            "after": False,
        })
    except Exception as exc:
        log_error(f"disable_realtime_capture:{actor_label(actor)}", exc)


def set_world_game_mode(world):
    settings = world.get_world_settings() if world else None
    if not settings:
        log_error("world_game_mode", RuntimeError("world settings unavailable"))
        return
    before = None
    try:
        current = settings.get_editor_property("default_game_mode")
        before = current.get_path_name() if current else None
    except Exception:
        pass
    game_mode_class = unreal.load_class(None, LOBBY_GAME_MODE)
    if not game_mode_class:
        log_error("world_game_mode", RuntimeError(f"game mode class not found: {LOBBY_GAME_MODE}"))
        return
    try:
        settings.set_editor_property("default_game_mode", game_mode_class)
        result["world_game_mode"] = {
            "before": before,
            "after": game_mode_class.get_path_name(),
        }
    except Exception as exc:
        log_error("world_game_mode", exc)


def record_backdrop(actor, kind):
    result["backdrops"].append({
        "label": actor_label(actor),
        "kind": kind,
        "location": str(actor.get_actor_location()),
        "rotation": str(actor.get_actor_rotation()),
        "scale": str(actor.get_actor_scale3d()),
    })


def spawn_directional(eas, base):
    actor = eas.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(base.x + 120.0, base.y - 180.0, base.z + 700.0),
        unreal.Rotator(-32.0, 180.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_KeySun")
    component = actor.get_component_by_class(unreal.DirectionalLightComponent)
    set_movable(component)
    set_intensity(component, 4.0)
    set_color(component, (255, 248, 236, 255))
    try:
        component.set_editor_property("cast_shadows", True)
    except Exception:
        pass
    record_light(actor, component, "directional")


def spawn_camera_fill(eas, base):
    actor = eas.spawn_actor_from_class(
        unreal.PointLight,
        unreal.Vector(base.x + 250.0, base.y + 35.0, base.z + 215.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_CameraFill")
    component = actor.get_component_by_class(unreal.PointLightComponent)
    set_movable(component)
    set_intensity(component, 1100.0)
    set_color(component, (244, 250, 255, 255))
    try:
        component.set_attenuation_radius(1350.0)
    except Exception:
        component.set_editor_property("attenuation_radius", 1350.0)
    try:
        component.set_editor_property("cast_shadows", False)
    except Exception:
        pass
    record_light(actor, component, "point_camera_fill")


def spawn_top_fill(eas, base):
    actor = eas.spawn_actor_from_class(
        unreal.PointLight,
        unreal.Vector(base.x + 20.0, base.y, base.z + 520.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_TopFill")
    component = actor.get_component_by_class(unreal.PointLightComponent)
    set_movable(component)
    set_intensity(component, 350.0)
    set_color(component, (210, 230, 255, 255))
    try:
        component.set_attenuation_radius(1600.0)
    except Exception:
        component.set_editor_property("attenuation_radius", 1600.0)
    try:
        component.set_editor_property("cast_shadows", False)
    except Exception:
        pass
    record_light(actor, component, "point_top_fill")


def spawn_neutral_backdrop(eas, base):
    mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    material = (
        unreal.EditorAssetLibrary.load_asset("/Game/Wanefall/Dimwit/MapKit/M_KitLit")
        or unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/BasicShapeMaterial")
    )
    actor = eas.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(base.x - 360.0, base.y, base.z + 260.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_NeutralBackdrop")
    comp = actor.static_mesh_component
    if mesh:
        comp.set_static_mesh(mesh)
    comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    comp.set_editor_property("cast_shadow", False)
    actor.set_actor_scale3d(unreal.Vector(0.08, 18.0, 5.2))
    if material:
        comp.set_material(0, material)
    record_backdrop(actor, "neutral_validation_backdrop")


def spawn_skylight(eas, base):
    actor = eas.spawn_actor_from_class(
        unreal.SkyLight,
        unreal.Vector(base.x, base.y, base.z + 850.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_SkyFill")
    component = actor.get_component_by_class(unreal.SkyLightComponent)
    set_movable(component)
    set_intensity(component, 2.0)
    try:
        component.set_editor_property("real_time_capture", False)
    except Exception:
        pass
    record_light(actor, component, "skylight")


def spawn_sky_atmosphere(eas):
    actor = eas.spawn_actor_from_class(
        unreal.SkyAtmosphere,
        unreal.Vector(0.0, 0.0, 0.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    set_label(actor, f"{LABEL_PREFIX}_SkyAtmosphere")
    result["lights"].append({"label": actor_label(actor), "kind": "sky_atmosphere"})


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    les.load_level(MAP)
    world = ues.get_editor_world()
    set_world_game_mode(world)

    for actor in list(eas.get_all_level_actors()):
        label = actor_label(actor)
        if label.startswith(LABEL_PREFIX):
            result["removed_validation_actors"].append(label)
            try:
                eas.destroy_actor(actor)
            except Exception as exc:
                log_error(f"destroy:{label}", exc)
        elif isinstance(actor, unreal.SkyLight):
            disable_realtime_skylight_capture(actor)

    base = unreal.Vector(0.0, 0.0, 0.0)
    for actor in eas.get_all_level_actors():
        if isinstance(actor, unreal.PlayerStart):
            base = actor.get_actor_location()
            break
    result["base"] = str(base)

    spawn_camera_fill(eas, base)
    spawn_top_fill(eas, base)
    spawn_neutral_backdrop(eas, base)

    try:
        world.modify()
    except Exception as exc:
        log_error("world_modify", exc)
    if hasattr(world, "mark_package_dirty"):
        try:
            world.mark_package_dirty()
        except Exception as exc:
            log_error("world_mark_package_dirty", exc)

    save_ok = False
    try:
        save_ok = bool(les.save_current_level())
    except Exception as exc:
        log_error("save_current_level", exc)
    save_asset_ok = False
    try:
        save_asset_ok = bool(unreal.EditorAssetLibrary.save_asset(MAP, False))
    except TypeError:
        try:
            save_asset_ok = bool(unreal.EditorAssetLibrary.save_asset(MAP))
        except Exception as exc:
            log_error("save_asset", exc)
    except Exception as exc:
        log_error("save_asset", exc)
    save_dirty_ok = False
    try:
        save_dirty_ok = bool(unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))
    except Exception as exc:
        log_error("save_dirty_packages", exc)

    result["save_current_level"] = save_ok
    result["save_asset"] = save_asset_ok
    result["save_dirty_packages"] = save_dirty_ok
    result["ok"] = bool(result["lights"]) and bool(result["backdrops"]) and (save_ok or save_asset_ok or save_dirty_ok) and not any(
        err["step"].startswith(("destroy", "save")) for err in result["errors"]
    )
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_MODESHELL_LIGHTING_REPAIR ok={result['ok']} lights={len(result['lights'])}")
unreal.log(f"DIMWIT_MODESHELL_LIGHTING_REPAIR ok={result['ok']} lights={len(result['lights'])}")
