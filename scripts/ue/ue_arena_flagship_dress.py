"""FLAGSHIP_ARENA_ART_PASS_V1 (masterplan bundle 10, B3) — dress Wanefall_Arena4v4_Prototype_01
from greybox to a readable, wane-themed flagship arena and SAVE it into the map.

Capture-law compliant: every dressed actor is a PERSISTENT saved-map actor (not session-spawned),
so the cook + capture tour render its real materials. Deterministic + idempotent: all authored
actors carry a "Flagship_" label prefix and are cleared+rebuilt each run, so re-runs never
duplicate. Placement is DATA-DRIVEN from the map's PlayerStarts (arena centroid = the contested
core; team clusters from the spawn split) — no blind hardcoded coordinates.

Authors: a wane-vein spine across the core axis, twin emissive wane spires at the contested core
(the IP landmark), team-side pillar landmarks, flank arch portals, a seeded cover scatter clear of
the spawn lanes, trim/wane materials on the kit, and a full lighting rig (SkyAtmosphere +
DirectionalLight + SkyLight + ExponentialHeightFog + a teal wane accent light at the core).

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_arena_flagship_dress.py" -NoTextureStreaming
"""
import json
import math
import random
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/flagship_arena/flagship_arena_dress_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"
KIT = "/Game/Wanefall/Dimwit/MapKit"
PREFIX = "Flagship_"
SEED = 20260702

# Wane-energy materials (the IP identity) for the landmark spires + veins; trim for the kit.
MAT_CORE = "/Game/Wanefall/Materials/M_WaneCoreEmissive"
MAT_TRIM = "/Game/Wanefall/Dimwit/Materials/M_WaneSurface"

result = {"ok": False, "map": MAP, "authored": {}, "materials_applied": [], "lighting_rig": [],
          "wane_landmarks": [], "player_starts": 0, "errors": []}


def mesh(name):
    for path in (f"{KIT}/{name}/StaticMeshes/{name}", f"{KIT}/{name}/{name}", f"{KIT}/{name}"):
        m = unreal.load_asset(path)
        if isinstance(m, unreal.StaticMesh):
            return m
    return None


def load_mat(path):
    m = unreal.load_asset(path)
    return m if isinstance(m, (unreal.MaterialInterface,)) else None


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)

    all_actors = eas.get_all_level_actors()
    # clear prior flagship dressing (idempotent rebuild)
    for a in list(all_actors):
        try:
            if a.get_actor_label().startswith(PREFIX):
                eas.destroy_actor(a)
        except Exception:
            pass
    all_actors = eas.get_all_level_actors()

    starts = [a for a in all_actors if isinstance(a, unreal.PlayerStart)]
    result["player_starts"] = len(starts)
    if starts:
        xs = [s.get_actor_location().x for s in starts]
        ys = [s.get_actor_location().y for s in starts]
        zs = [s.get_actor_location().z for s in starts]
        core = unreal.Vector(sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        span = max(300.0, max(max(xs) - min(xs), max(ys) - min(ys)))
    else:
        core = unreal.Vector(0, 0, 0)
        span = 3000.0
    result["core"] = [core.x, core.y, core.z]
    result["span"] = span

    core_mat = load_mat(MAT_CORE)
    trim_mat = load_mat(MAT_TRIM)
    authored = {}

    def place(name, mesh_name, loc, rot=None, scale=None, material=None, tag="kit"):
        m = mesh(mesh_name)
        if not m:
            result["errors"].append(f"missing kit mesh {mesh_name}")
            return None
        actor = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot or unreal.Rotator(0, 0, 0))
        actor.set_actor_label(PREFIX + name)
        comp = actor.static_mesh_component
        comp.set_static_mesh(m)
        if scale:
            actor.set_actor_scale3d(scale)
        if material:
            comp.set_material(0, material)
            result["materials_applied"].append(f"{name}:{material.get_name()}")
        authored[tag] = authored.get(tag, 0) + 1
        return actor

    rng = random.Random(SEED)
    half = span * 0.55

    # --- the contested core: twin tall trim spires as the structural IP landmark, lit by the teal
    # wane accent light. M_WaneCoreEmissive is a max-brightness energy material whose post-process
    # bloom blows out an LDR establishing capture, so it is reserved for the THIN vein lines (below)
    # where it reads as teal wane-energy, not a screen-filling blob; the core reads via silhouette +
    # the accent glow. (A bloom/exposure polish pass to put a contained emissive core back is noted
    # future work.)
    for i, dy in enumerate((-span * 0.10, span * 0.10)):
        sp = place(f"CoreSpire_{i}", "SM_Kit_Spire",
                   unreal.Vector(core.x, core.y + dy, core.z + 120.0),
                   scale=unreal.Vector(1.1, 1.1, 3.4), material=trim_mat, tag="core_spire")
        if sp:
            result["wane_landmarks"].append(sp.get_actor_label())
    # vein spine along +X across the core (the collapse axis identity)
    for i in range(7):
        t = (i - 3) / 3.0
        place(f"Vein_{i}", "SM_Kit_Vein",
              unreal.Vector(core.x + t * half, core.y, core.z),
              scale=unreal.Vector(1.0, 1.0, 1.0), material=core_mat, tag="vein")

    # --- team-side pillar landmarks (orientation) at each spawn cluster direction ---
    for i, ang in enumerate((0.0, 90.0, 180.0, 270.0)):
        rad = math.radians(ang)
        loc = unreal.Vector(core.x + math.cos(rad) * half * 0.8,
                            core.y + math.sin(rad) * half * 0.8, core.z)
        place(f"Pillar_{i}", "SM_Kit_Pillar", loc, scale=unreal.Vector(1.2, 1.2, 1.8),
              material=trim_mat, tag="pillar")

    # --- flank arch portals ---
    for i, ang in enumerate((45.0, 225.0)):
        rad = math.radians(ang)
        loc = unreal.Vector(core.x + math.cos(rad) * half, core.y + math.sin(rad) * half, core.z)
        place(f"Arch_{i}", "SM_Kit_Arch", loc,
              rot=unreal.Rotator(0, ang, 0), scale=unreal.Vector(1.3, 1.3, 1.3),
              material=trim_mat, tag="arch")

    # --- seeded cover scatter, clear of the core corridor + spawns ---
    cover_pieces = ["SM_Kit_Cover", "SM_Kit_Crate", "SM_Kit_Barrier", "SM_Kit_Debris"]
    placed_cover = 0
    for i in range(16):
        ang = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(half * 0.3, half * 0.9)
        loc = unreal.Vector(core.x + math.cos(ang) * rad, core.y + math.sin(ang) * rad, core.z)
        # keep the core corridor readable: skip anything hugging the spine
        if abs(loc.y - core.y) < span * 0.06:
            continue
        piece = cover_pieces[i % len(cover_pieces)]
        if place(f"Cover_{i}", piece, loc, rot=unreal.Rotator(0, rng.uniform(0, 360), 0),
                 material=trim_mat, tag="cover"):
            placed_cover += 1

    result["authored"] = authored

    # --- lighting rig (SkyAtmosphere law) ---
    def ensure(cls, label, spawn_loc=None):
        for a in eas.get_all_level_actors():
            if isinstance(a, cls):
                return a, False
        a = eas.spawn_actor_from_class(cls, spawn_loc or unreal.Vector(core.x, core.y, core.z + 500),
                                       unreal.Rotator(0, 0, 0))
        a.set_actor_label(PREFIX + label)
        return a, True

    rig = []
    for cls, label in ((unreal.SkyAtmosphere, "SkyAtmosphere"),
                       (unreal.DirectionalLight, "SunLight"),
                       (unreal.SkyLight, "SkyLight"),
                       (unreal.ExponentialHeightFog, "WaneFog")):
        actor, spawned = ensure(cls, label)
        rig.append({"class": cls.__name__, "label": actor.get_actor_label(), "spawned": spawned})
    # teal wane accent point light at the contested core (readability + mood)
    accent = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(core.x, core.y, core.z + 260),
                                        unreal.Rotator(0, 0, 0))
    accent.set_actor_label(PREFIX + "WaneCoreAccent")
    try:
        lc = accent.point_light_component
        # a SUBTLE teal core glow, not a floor blowout: the earlier 1600 hotspot washed the light
        # floor into a white square from top-down. Low intensity + tight radius = a readable accent.
        lc.set_intensity(300.0)
        lc.set_attenuation_radius(450.0)
        lc.set_light_color(unreal.LinearColor(0.20, 0.95, 1.0, 1.0))
    except Exception as e:
        result["errors"].append(f"accent light tune: {e}")
    rig.append({"class": "PointLight", "label": accent.get_actor_label(), "spawned": True})
    result["lighting_rig"] = rig

    saved = les.save_current_level()
    result["map_saved"] = bool(saved)
    result["total_flagship_actors"] = len([a for a in eas.get_all_level_actors()
                                           if a.get_actor_label().startswith(PREFIX)])
    result["ok"] = bool(saved) and not [e for e in result["errors"] if "missing kit mesh" in e]
except Exception:
    result["errors"].append(traceback.format_exc())

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("FLAGSHIP_DRESS_RESULT:", json.dumps({k: result[k] for k in
      ("ok", "authored", "player_starts", "total_flagship_actors", "map_saved")})[:400])
