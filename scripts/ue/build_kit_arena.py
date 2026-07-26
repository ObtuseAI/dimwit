"""Build a playable WANEFALL arena entirely from the modular kit (UE headless commandlet).
Creates /Game/Wanefall/Maps/Wanefall_KitArena_01 from scratch: kit-tile floor + perimeter walls + authored
cover/pillars/Wane-veins/arches/debris, lighting + fog, and PlayerStarts (player + bot spawns). Kit meshes are
set to block (complex-as-simple) so the floor/cover are solid. Run via UnrealEditor-Cmd -ExecutePythonScript.
"""
import unreal, math

LEVEL = "/Game/Wanefall/Maps/Wanefall_KitArena_01"
KIT = "/Game/Wanefall/Dimwit/MapKit"
PIECES = ["SM_Kit_Floor", "SM_Kit_Wall", "SM_Kit_Cover", "SM_Kit_Ramp", "SM_Kit_Pillar",
          "SM_Kit_Vein", "SM_Kit_Arch", "SM_Kit_Crate", "SM_Kit_Debris"]

def mesh(name):
    return unreal.load_asset(f"{KIT}/{name}/StaticMeshes/{name}")

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

les.new_level(LEVEL)

# Make the kit block (use render geometry as collision so floor/cover/walls are solid).
for n in PIECES:
    m = mesh(n)
    if not m:
        continue
    try:
        bs = m.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            unreal.EditorAssetLibrary.save_loaded_asset(m)
    except Exception as e:
        unreal.log_warning(f"collision set failed {n}: {e}")

placed = [0]
def place(name, loc, yaw=0.0):
    m = mesh(name)
    if not m:
        return None
    a = eas.spawn_actor_from_object(m, unreal.Vector(loc[0], loc[1], loc[2]), unreal.Rotator(0.0, 0.0, yaw))
    placed[0] += 1
    return a

T = 400.0   # 4 m tile in unreal units
EDGE = 3 * T + T / 2

# floor grid (7x7 = ~28 m arena)
for ix in range(-3, 4):
    for iy in range(-3, 4):
        place("SM_Kit_Floor", (ix * T, iy * T, 0))

# perimeter walls
for ix in range(-3, 4):
    place("SM_Kit_Wall", (ix * T, EDGE, 0), 0.0)
    place("SM_Kit_Wall", (ix * T, -EDGE, 0), 0.0)
for iy in range(-3, 4):
    place("SM_Kit_Wall", (EDGE, iy * T, 0), 90.0)
    place("SM_Kit_Wall", (-EDGE, iy * T, 0), 90.0)

# authored cover scatter (hand-placed, asymmetric)
for (x, y, yaw) in [(-600, 200, 20), (700, -300, -35), (0, 760, 0), (-340, -680, 55),
                    (880, 560, 15), (-880, -180, -20), (420, 360, 70), (-520, 480, 40)]:
    place("SM_Kit_Cover", (x, y, 0), yaw)

# pillars at the quarter points
for (x, y) in [(-T * 1.5, -T * 1.5), (T * 1.5, -T * 1.5), (-T * 1.5, T * 1.5), (T * 1.5, T * 1.5)]:
    place("SM_Kit_Pillar", (x, y, 0))

# Wane-veins radiating outward from the contested core (the bible's flow-to-core wayfinding)
for ang in range(0, 360, 45):
    r = math.radians(ang)
    place("SM_Kit_Vein", (math.cos(r) * 760, math.sin(r) * 760, 0), float(ang))

# flank-portal arches on the two long walls
place("SM_Kit_Arch", (0, EDGE - 30, 0), 0.0)
place("SM_Kit_Arch", (0, -EDGE + 30, 0), 0.0)

# Fallen-ground debris in two corners + a couple of crates near cover
for (x, y) in [(-T * 2.4, T * 2.4), (T * 2.4, -T * 2.4)]:
    place("SM_Kit_Debris", (x, y, 0))
for (x, y) in [(520, -120), (-220, 320)]:
    place("SM_Kit_Crate", (x, y, 0))

# --- lighting + atmosphere (moody dark; the emissive Wane accents glow against it) ---
try:
    dl = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1600), unreal.Rotator(-42, 35, 0))
    c = dl.get_component_by_class(unreal.DirectionalLightComponent)
    if c: c.set_intensity(3.2)
except Exception as e:
    unreal.log_warning(f"dir light: {e}")
try:
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1300))
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    if sc:
        sc.set_intensity(1.1)
        try: sc.recapture_sky()
        except Exception: pass
except Exception as e:
    unreal.log_warning(f"sky light: {e}")
try:
    eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 80))
except Exception as e:
    unreal.log_warning(f"fog: {e}")

# --- player + bot spawn points (director reserves [0] for the player) ---
starts = [(0, -T * 2.5, 60)] + [(x, y, 60) for (x, y) in
          [(T * 2, T * 2), (-T * 2, T * 2), (T * 2, -T * 2), (-T * 2, -T * 2),
           (0, T * 2.5), (T * 2.5, 0), (-T * 2.5, 0)]]
for (x, y, z) in starts:
    eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(x, y, z), unreal.Rotator(0, 0, 0))

les.save_current_level()
unreal.log(f"WANEFALL_KIT_ARENA_DONE placed={placed[0]} starts={len(starts)}")
