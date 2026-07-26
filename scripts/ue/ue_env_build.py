"""Dimwit UE driver — procedurally build a WANE-LINE arena (UE 5.8 headless commandlet).

Invoked by dimwit/pipelines/environment.py via:
    UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_env_build.py level=<path> seed=<int> ...

Creates a brand-new level under /Game/Wanefall/Maps/Wanefall_GenArena_<n> from scratch and places the modular
MapKit (SM_Kit_Floor/Wall/Cover/Pillar/Vein/Ramp/Arch/Spire) in a readable arena layout built around a
deterministic collapse axis (the WANE LINE = a glowing Wane-vein spine running down +X with spires marking the
contested core). Adds N PlayerStarts, a DirectionalLight + SkyLight + ExponentialHeightFog, and forces the kit
meshes to block (CTF_USE_COMPLEX_AS_SIMPLE) so floor/cover/walls are solid. Saves the level, then WRITES the
proof JSON to artifacts/env_build_result.json (the pipeline verifies via the FILE, not the exit code).

Determinism: all randomness is derived from a seeded random.Random(seed) so the same seed -> the same arena.
Everything is wrapped fail-soft: a missing kit piece is recorded (not crashed) so QA can judge honestly.

TODO(real): full UE5 PCG graph authoring (PCGComponent + procedural graph) instead of deterministic scatter;
Hi3D hero landmarks at the core; GLM readability/flow/silhouette QA on a top-down capture; World Partition.
"""
import json
import math
import os
import random
import sys

import unreal


# ---- argv parsing (key=val after the script path) ------------------------------------------------
def _args():
    out = {}
    for a in sys.argv:
        if "=" in a and not a.lower().endswith(".py"):
            k, _, v = a.partition("=")
            out[k.strip()] = v.strip()
    return out


ARGS = _args()
LEVEL = ARGS.get("level", "/Game/Wanefall/Maps/Wanefall_GenArena_1")
SEED = int(ARGS.get("seed", "1"))
KIT = ARGS.get("kit", "/Game/Wanefall/Dimwit/MapKit")
NUM_STARTS = max(2, int(ARGS.get("starts", "8")))
GRID = max(3, int(ARGS.get("grid", "4")))            # half-extent in tiles -> (2*GRID+1) square
RESULT_PATH = ARGS.get("result", "")                  # absolute path the pipeline passes; else derive

# Derive the result path next to this driver (Dimwit/artifacts/) if not given.
if not RESULT_PATH:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    RESULT_PATH = os.path.join(here, "artifacts", "env_build_result.json")

T = 400.0                                              # 4 m tile in unreal units
PIECES = ["SM_Kit_Floor", "SM_Kit_Wall", "SM_Kit_Cover", "SM_Kit_Pillar",
          "SM_Kit_Vein", "SM_Kit_Ramp", "SM_Kit_Arch", "SM_Kit_Spire"]

rng = random.Random(SEED)
rec = {
    "level": LEVEL, "seed": SEED, "kit": KIT,
    "placed": 0, "by_piece": {}, "missing_pieces": [], "starts": 0,
    "lighting": {"directional": False, "sky": False, "fog": False},
    "wane_line": {"axis": "+X", "vein_count": 0, "spire_count": 0},
    "saved": False, "error": None,
}


def mesh(name):
    # Interchange/MapKit convention: <KIT>/<Name>/StaticMeshes/<Name>
    m = unreal.load_asset(f"{KIT}/{name}/StaticMeshes/{name}")
    if not m:
        m = unreal.load_asset(f"{KIT}/{name}")        # fallback flat layout
    return m


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    les.new_level(LEVEL)

    # ---- force kit collision so the arena is solid (complex-as-simple) ----
    avail = {}
    for n in PIECES:
        m = mesh(n)
        avail[n] = m
        if not m:
            rec["missing_pieces"].append(n)
            continue
        try:
            bs = m.get_editor_property("body_setup")
            if bs:
                bs.set_editor_property("collision_trace_flag",
                                       unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                unreal.EditorAssetLibrary.save_loaded_asset(m)
        except Exception as e:
            unreal.log_warning(f"collision set failed {n}: {e}")

    def place(name, loc, yaw=0.0):
        m = avail.get(name)
        if not m:
            return None
        a = eas.spawn_actor_from_object(m, unreal.Vector(loc[0], loc[1], loc[2]),
                                        unreal.Rotator(0.0, 0.0, float(yaw)))
        rec["placed"] += 1
        rec["by_piece"][name] = rec["by_piece"].get(name, 0) + 1
        return a

    edge = GRID * T + T / 2

    # ---- floor grid (square arena) ----
    for ix in range(-GRID, GRID + 1):
        for iy in range(-GRID, GRID + 1):
            place("SM_Kit_Floor", (ix * T, iy * T, 0))

    # ---- perimeter walls ----
    for ix in range(-GRID, GRID + 1):
        place("SM_Kit_Wall", (ix * T, edge, 0), 0.0)
        place("SM_Kit_Wall", (ix * T, -edge, 0), 0.0)
    for iy in range(-GRID, GRID + 1):
        place("SM_Kit_Wall", (edge, iy * T, 0), 90.0)
        place("SM_Kit_Wall", (-edge, iy * T, 0), 90.0)

    # ---- THE WANE LINE: a deterministic collapse axis down +X ----
    # A spine of glowing Wane-veins marks where the world is crystallizing/eroding; spires bracket the
    # contested core. This is the readable wayfinding + the arena's identity.
    vein_n = 0
    for ix in range(-GRID, GRID + 1):
        if place("SM_Kit_Vein", (ix * T, 0, 0), 0.0):
            vein_n += 1
    rec["wane_line"]["vein_count"] = vein_n

    spire_n = 0
    for sx in (-T, T):                                 # bracket the central core
        if place("SM_Kit_Spire", (sx, 0, 0), 0.0):
            spire_n += 1
    rec["wane_line"]["spire_count"] = spire_n

    # ---- ramps onto the spine flanks (verticality, deterministic offsets) ----
    for iy in (-2, 2):
        place("SM_Kit_Ramp", (0, iy * T, 0), 90.0 if iy > 0 else -90.0)

    # ---- pillars at the quarter points (stable landmarks) ----
    q = (GRID - 1) * T
    for (x, y) in [(-q, -q), (q, -q), (-q, q), (q, q)]:
        place("SM_Kit_Pillar", (x, y, 0))

    # ---- deterministic asymmetric cover scatter (seeded; avoids the spine corridor) ----
    cover_target = 8
    placed_cover = 0
    guard = 0
    while placed_cover < cover_target and guard < 400:
        guard += 1
        ix = rng.randint(-GRID + 1, GRID - 1)
        iy = rng.randint(-GRID + 1, GRID - 1)
        if abs(iy) <= 0:                               # keep the Wane-line corridor clear
            continue
        yaw = rng.choice([0, 25, 45, 70, -30, -55])
        if place("SM_Kit_Cover", (ix * T + rng.uniform(-60, 60),
                                  iy * T + rng.uniform(-60, 60), 0), yaw):
            placed_cover += 1

    # ---- flank-portal arches on the two ends of the Wane line ----
    place("SM_Kit_Arch", (edge - 30, 0, 0), 90.0)
    place("SM_Kit_Arch", (-edge + 30, 0, 0), 90.0)

    # ---- lighting + atmosphere (moody; emissive Wane accents glow against the dark) ----
    try:
        dl = eas.spawn_actor_from_class(unreal.DirectionalLight,
                                        unreal.Vector(0, 0, 1600), unreal.Rotator(-42, 35, 0))
        c = dl.get_component_by_class(unreal.DirectionalLightComponent)
        if c:
            c.set_intensity(3.2)
        rec["lighting"]["directional"] = True
    except Exception as e:
        unreal.log_warning(f"dir light: {e}")
    try:
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1300))
        sc = sky.get_component_by_class(unreal.SkyLightComponent)
        if sc:
            sc.set_intensity(1.1)
            try:
                sc.recapture_sky()
            except Exception:
                pass
        rec["lighting"]["sky"] = True
    except Exception as e:
        unreal.log_warning(f"sky light: {e}")
    try:
        eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 80))
        rec["lighting"]["fog"] = True
    except Exception as e:
        unreal.log_warning(f"fog: {e}")

    # ---- PlayerStarts: deterministic ring around the arena; [0] reserved near a Wane-line end ----
    starts = [(-(GRID - 0.5) * T, 0, 60)]              # player faces down the Wane line
    ring = NUM_STARTS - 1
    for i in range(ring):
        ang = (2 * math.pi * i) / max(1, ring)
        r = (GRID - 0.5) * T
        starts.append((math.cos(ang) * r, math.sin(ang) * r, 60))
    for (x, y, z) in starts:
        eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(x, y, z),
                                   unreal.Rotator(0, 0, 0))
    rec["starts"] = len(starts)

    # ---- save ----
    try:
        les.save_current_level()
        rec["saved"] = unreal.EditorAssetLibrary.does_asset_exist(LEVEL)
    except Exception as e:
        rec["error"] = f"save failed: {e}"

    unreal.log(f"WANEFALL_GEN_ARENA_DONE placed={rec['placed']} starts={rec['starts']} "
               f"veins={vein_n} saved={rec['saved']}")


try:
    main()
except Exception as e:
    rec["error"] = f"{type(e).__name__}: {e}"
    try:
        unreal.log_error(f"WANEFALL_GEN_ARENA_FAIL {rec['error']}")
    except Exception:
        pass
finally:
    try:
        os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
    except Exception:
        pass
