"""Data-driven UE level builder (task 12). Reads a level_spec JSON (see config/level_spec.schema.json) and
builds a level from the modular kit + the validated Movable/lumens light recipe — generalizing the hardcoded
scripts/ue/build_hold_room.py / scripts/ue/build_kit_arena.py into JSON-authored layouts the agent can produce.

Headless:  UnrealEditor-Cmd <proj> -ExecutePythonScript=scripts/ue/build_level.py -- <spec.json>
       or  set DIMWIT_LEVEL_SPEC=<spec.json> then run the script.
"""
import unreal
import json
import os
import sys

_LIGHT_CLS = {"point": unreal.PointLight, "spot": unreal.SpotLight, "directional": unreal.DirectionalLight}
_LIGHT_COMP = {"point": unreal.PointLightComponent, "spot": unreal.SpotLightComponent,
               "directional": unreal.DirectionalLightComponent}


def _spec_path():
    if "--" in sys.argv:
        rest = sys.argv[sys.argv.index("--") + 1:]
        if rest:
            return rest[0]
    return os.environ.get("DIMWIT_LEVEL_SPEC", "")


def _kit(n):
    return unreal.load_asset(f"/Game/Wanefall/Dimwit/MapKit/{n}/StaticMeshes/{n}")


def build_from_spec(spec):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level = spec["level_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(level):
        les.load_level(level)
        for a in list(eas.get_all_level_actors()):
            try:
                eas.destroy_actor(a)
            except Exception:
                pass
    else:
        les.new_level(level)

    n = [0]
    T = float(spec.get("tile_size", 400))

    def spawn(mesh, loc, yaw=0.0, scale=None):
        if not mesh:
            return
        a = eas.spawn_actor_from_object(mesh, unreal.Vector(loc[0], loc[1], loc[2]), unreal.Rotator(0, 0, yaw))
        if scale:
            a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        n[0] += 1

    fg = spec.get("floor_grid")
    if fg:
        for ix in range(fg["x"][0], fg["x"][1] + 1):
            for iy in range(fg["y"][0], fg["y"][1] + 1):
                spawn(_kit(fg.get("piece", "SM_Kit_Floor")), (ix * T, iy * T, 0))
        if spec.get("perimeter_walls"):
            for ix in range(fg["x"][0], fg["x"][1] + 1):
                spawn(_kit("SM_Kit_Wall"), (ix * T, (fg["y"][1] + 0.5) * T, 0), 0.0)
                spawn(_kit("SM_Kit_Wall"), (ix * T, (fg["y"][0] - 0.5) * T, 0), 0.0)
            for iy in range(fg["y"][0], fg["y"][1] + 1):
                spawn(_kit("SM_Kit_Wall"), ((fg["x"][1] + 0.5) * T, iy * T, 0), 90.0)
                spawn(_kit("SM_Kit_Wall"), ((fg["x"][0] - 0.5) * T, iy * T, 0), 90.0)

    for p in spec.get("props", []):
        mesh = _kit(p["piece"]) if p["piece"].startswith("SM_Kit_") else unreal.load_asset(p["piece"])
        spawn(mesh, p.get("loc", [0, 0, 0]), float(p.get("yaw", 0.0)), p.get("scale"))

    for L in spec.get("lights", []):
        cls = _LIGHT_CLS.get(L["type"])
        if not cls:
            continue
        act = eas.spawn_actor_from_class(cls, unreal.Vector(*L.get("loc", [0, 0, 500])),
                                         unreal.Rotator(*L.get("rot", [0, 0, 0])))
        comp = act.get_component_by_class(_LIGHT_COMP[L["type"]])
        try:
            comp.set_mobility(unreal.ComponentMobility.MOVABLE)
        except Exception:
            pass
        if L["type"] in ("point", "spot"):
            try:
                comp.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
            except Exception:
                pass
        comp.set_intensity(float(L.get("intensity", 8000)))

    if spec.get("sky_atmosphere", True):
        try:
            eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
            sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1100))
            sc = sky.get_component_by_class(unreal.SkyLightComponent)
            sc.set_mobility(unreal.ComponentMobility.MOVABLE)
            sc.set_editor_property("real_time_capture", True)
            sc.set_intensity(2.0)
        except Exception:
            pass

    ps = spec.get("player_start")
    if ps:
        eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*ps.get("loc", [0, 0, 60])),
                                   unreal.Rotator(*ps.get("rot", [0, 0, 0])))

    les.save_current_level()
    unreal.log(f"DIMWIT_LEVEL_BUILT {level} actors={n[0]}")


_sp = _spec_path()
if _sp and os.path.exists(_sp):
    build_from_spec(json.loads(open(_sp, encoding="utf-8").read()))
else:
    unreal.log_warning("build_level: no level spec (pass -- <spec.json> or set DIMWIT_LEVEL_SPEC)")
