"""Build THE HOLD front-end room (UE headless commandlet) from the kit + character/weapon meshes.
/Game/Wanefall/Maps/Wanefall_TheHold_01 : an enclosed cargo hold. The Hold pawn spawns at center looking +X
(THE SQUAD = the 8 species lined up); -Y wall = THE RACK (crates + display guns); +Y wall = THE TABLE (console +
Wane spire). Lit + fogged. Run after the editor target compiles (references the new collision-baked kit).
"""
import unreal, math

LEVEL = "/Game/Wanefall/Maps/Wanefall_TheHold_01"

def kit(n):  return unreal.load_asset(f"/Game/Wanefall/Dimwit/MapKit/{n}/StaticMeshes/{n}")
def char(n): return unreal.load_asset(f"/Game/Wanefall/Dimwit/Characters/{n}/StaticMeshes/{n}")
def wpn(n):  return unreal.load_asset(f"/Game/Wanefall/Dimwit/Weapons/{n}/StaticMeshes/{n}")

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Robust rebuild-in-place: new_level() returns False when the asset already exists, so on a re-run we LOAD the
# level and clear its actors instead (deleting + recreating leaves the asset in a bad state). Either path leaves
# us with an empty Wanefall_TheHold_01 as the current level, ready to repopulate + save.
exists = unreal.EditorAssetLibrary.does_asset_exist(LEVEL)
print(f"HOLD: exists={exists}")
if exists:
    print(f"HOLD: load_level -> {les.load_level(LEVEL)}")
    cleared = 0
    for a in list(eas.get_all_level_actors()):
        try:
            eas.destroy_actor(a)
            cleared += 1
        except Exception:
            pass
    print(f"HOLD: cleared {cleared} actors")
else:
    print(f"HOLD: new_level -> {les.new_level(LEVEL)}")

n = [0]
def spawn(m, loc, yaw=0.0):
    if not m: return None
    n[0] += 1
    return eas.spawn_actor_from_object(m, unreal.Vector(loc[0], loc[1], loc[2]), unreal.Rotator(0, 0, yaw))

def spawn_h(m, loc, yaw, target_h):
    a = spawn(m, loc, yaw)
    if not a: return None
    try:
        bb = m.get_bounding_box()
        h = bb.max.z - bb.min.z
        s = (target_h / h) if h > 1.0 else 1.0
        a.set_actor_scale3d(unreal.Vector(s, s, s))
    except Exception as e:
        unreal.log_warning(f"scale {e}")
    return a

T = 400.0
# enclosed floor (6 x 5)
for ix in range(-2, 4):
    for iy in range(-2, 3):
        spawn(kit("SM_Kit_Floor"), (ix * T, iy * T, 0))
# perimeter walls
for ix in range(-2, 4):
    spawn(kit("SM_Kit_Wall"), (ix * T, 2 * T + T / 2, 0), 0.0)
    spawn(kit("SM_Kit_Wall"), (ix * T, -2 * T - T / 2, 0), 0.0)
for iy in range(-2, 3):
    spawn(kit("SM_Kit_Wall"), (3 * T + T / 2, iy * T, 0), 90.0)
    spawn(kit("SM_Kit_Wall"), (-2 * T - T / 2, iy * T, 0), 90.0)

# THE SQUAD: 8 species lined up on the +X wall, facing the pawn (-X = yaw 180)
soldiers = ["SM_Char_01_Vorlax", "SM_Char_02_ekris", "SM_Char_03_zythan", "SM_Char_04_qorin",
            "SM_Char_05_therak", "SM_Char_06_ullio", "SM_Char_07_kelous", "SM_Char_08_nexor"]
for i, s in enumerate(soldiers):
    spawn_h(char(s), (1050, (i - 3.5) * 210, 20), 180.0, 185.0)
# a pillar pair framing the squad
spawn(kit("SM_Kit_Pillar"), (1150, 850, 0))
spawn(kit("SM_Kit_Pillar"), (1150, -850, 0))

# THE RACK: crates + three display guns on the -Y wall
for x in (-450, 0, 450):
    spawn(kit("SM_Kit_Crate"), (x, -760, 0))
for i, g in enumerate(["SM_Wpn_Gun_03_pulse_carbine", "SM_Wpn_Gun_08_sentinel_sniper", "SM_Wpn_Gun_25_gravity_hammer"]):
    spawn_h(wpn(g), ((i - 1) * 450, -740, 135), 0.0, 95.0)
spawn(kit("SM_Kit_Vein"), (0, -880, 0), 0.0)

# THE TABLE: a console + a Wane spire beacon on the +Y wall
spawn(kit("SM_Kit_Cover"), (0, 770, 0), 0.0)
spawn(kit("SM_Kit_Spire"), (0, 980, 0))
spawn(kit("SM_Kit_Catwalk"), (700, 770, 0), 0.0)

# atmosphere: veins radiating + a Fallen rubble pile
for ang in range(0, 360, 72):
    spawn(kit("SM_Kit_Vein"), (math.cos(math.radians(ang)) * 480, math.sin(math.radians(ang)) * 480, 0), float(ang))
spawn(kit("SM_Kit_FallenWall"), (-1000, 700, 0), 30.0)
spawn(kit("SM_Kit_Debris"), (-900, -650, 0))

# PlayerStart at center (the Hold pawn spawns here, camera looks +X at the squad)
eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 60), unreal.Rotator(0, 0, 0))

# ---------------------------------------------------------------------------
# LIGHTING — all MOVABLE (a commandlet level has no baked lighting, so Stationary/Static lights render
# the room pitch-black in -game; only Movable lights work without a build). A real interior fill rig so the
# metal surfaces, the squad, and the props all read, with the Wane accents as glowing highlights on top.
# ---------------------------------------------------------------------------
def movable(comp):
    try: comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    except Exception as e: unreal.log_warning(f"mobility {e}")

def point(loc, intensity, radius, color=(255, 246, 230)):
    try:
        pl = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(*loc))
        c = pl.get_component_by_class(unreal.PointLightComponent)
        movable(c)
        try: c.set_editor_property('intensity_units', unreal.LightUnits.LUMENS)
        except Exception: pass
        c.set_intensity(intensity)
        c.set_attenuation_radius(radius)
        try: c.set_light_color(unreal.Color(color[0], color[1], color[2], 255))
        except Exception: pass
        try: c.set_cast_shadows(False)
        except Exception: pass
        return pl
    except Exception as e:
        unreal.log_warning(f"point {e}")

def spot(loc, rot, intensity, radius, color=(220, 246, 255)):
    try:
        sp = eas.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(*loc), unreal.Rotator(rot[0], rot[1], rot[2]))
        c = sp.get_component_by_class(unreal.SpotLightComponent)
        movable(c)
        try: c.set_editor_property('intensity_units', unreal.LightUnits.LUMENS)
        except Exception: pass
        c.set_intensity(intensity)
        c.set_attenuation_radius(radius)
        try:
            c.set_editor_property('outer_cone_angle', 55.0)
            c.set_editor_property('inner_cone_angle', 30.0)
        except Exception: pass
        try: c.set_light_color(unreal.Color(color[0], color[1], color[2], 255))
        except Exception: pass
        return sp
    except Exception as e:
        unreal.log_warning(f"spot {e}")

# key directional (Movable) — warm, raking
try:
    dl = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1500), unreal.Rotator(-42, 25, 0))
    dc = dl.get_component_by_class(unreal.DirectionalLightComponent)
    movable(dc)
    dc.set_intensity(6.0)
    try: dc.set_light_color(unreal.Color(255, 244, 224, 255))
    except Exception: pass
except Exception as e:
    unreal.log_warning(f"dl {e}")

# overhead ambient fill grid — guarantees the floor + walls read
for gx in (-700, 0, 700):
    for gy in (-500, 500):
        point((gx, gy, 560), 8000.0, 3500, (210, 224, 240))
# brighter center key
point((0, 0, 620), 16000.0, 3500, (255, 248, 235))
# station spotlights aimed down at the three stations (lumens, validated live in-editor)
spot((1050, 0, 760), (-58, 0, 0), 25000.0, 3500, (225, 248, 255))   # SQUAD (+X)
spot((0, -760, 760), (-58, -90, 0), 18000.0, 3500, (255, 232, 210)) # RACK (-Y)
spot((0, 760, 760), (-58, 90, 0), 18000.0, 3500, (210, 248, 255))   # TABLE (+Y)

# SkyAtmosphere — gives the SkyLight a real sky to capture (without it real-time capture is black + metals
# have nothing to reflect). The hull is enclosed so you don't see the sky directly, only its ambient/reflection.
try:
    eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
except Exception as e:
    print(f"skyatmo {e}")

# SkyLight (Movable, real-time) — soft ambient + reflections off the atmosphere
try:
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1100))
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    movable(sc)
    try: sc.set_editor_property('real_time_capture', True)
    except Exception: pass
    sc.set_intensity(2.0)
    try: sc.recapture_sky()
    except Exception: pass
except Exception as e:
    print(f"sky {e}")

# thin fog only (the old default density swallowed the room)
try:
    fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 60))
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    if fc:
        try: fc.set_editor_property('fog_density', 0.008)
        except Exception: pass
except Exception as e:
    unreal.log_warning(f"fog {e}")

# unbound PostProcessVolume — auto-exposure with a sane band (now that surfaces actually reflect light) + bloom
try:
    ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 300))
    ppv.set_editor_property('unbound', True)
    s = ppv.get_editor_property('settings')
    s.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_HISTOGRAM)
    s.set_editor_property('override_auto_exposure_method', True)
    s.set_editor_property('auto_exposure_min_brightness', 0.3)
    s.set_editor_property('override_auto_exposure_min_brightness', True)
    s.set_editor_property('auto_exposure_max_brightness', 2.0)
    s.set_editor_property('override_auto_exposure_max_brightness', True)
    s.set_editor_property('auto_exposure_bias', 1.0)
    s.set_editor_property('override_auto_exposure_bias', True)
    s.set_editor_property('bloom_intensity', 0.5)
    s.set_editor_property('override_bloom_intensity', True)
    ppv.set_editor_property('settings', s)
except Exception as e:
    print(f"ppv {e}")

saved = les.save_current_level()
print(f"WANEFALL_HOLD_ROOM_DONE actors={n[0]} saved={saved}")
