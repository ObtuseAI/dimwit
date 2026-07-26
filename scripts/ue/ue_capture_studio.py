"""Dimwit in-engine STUDIO proof: render the RIGGED skeletal Ekris with its real material in a clean neutral
studio (grey enclosure + 3-point light + LOCKED exposure). Supports named camera angles so arm/profile defects
cannot hide behind a single front-ish screenshot.

Examples:
  angle=front out=runtime_rig_multiview/02_ekris_front.png
  angle=side out=runtime_rig_multiview/02_ekris_side.png
  angle=threequarter out=runtime_rig_multiview/02_ekris_threequarter.png
"""
import unreal, json, sys, traceback
from pathlib import Path

ARGS = {}
for arg in sys.argv:
    if "=" in arg and not arg.startswith("-"):
        k, v = arg.split("=", 1)
        ARGS[k.strip()] = v.strip()

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/hold_capture")
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/studio_result.json")
LOBBY = "/Game/Wanefall/Maps/Wanefall_Lobby"
RIG = ARGS.get("rig", "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig")
MAT = ARGS.get("mat", "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material.pbr_material")
IDLE = ARGS.get("anim", "/Game/Mannequins/Animations/Manny/MM_Idle")
POSE = ARGS.get("pose", "idle").lower()
ANGLE = ARGS.get("angle", "side").lower()
OUT_NAME = ARGS.get("out", "studio_ekris.png")
ROOM = ARGS.get("room", "1") != "0"
CUBE = "/Engine/BasicShapes/Cube"
out = {"ok": False, "pose": POSE, "angle": ANGLE, "rig": RIG, "mat": MAT}
spawned = []


def evaluate_pose(comp):
    for call in (lambda: comp.tick_pose(0.1, False),
                 lambda: comp.tick_animation(0.1, False),
                 lambda: comp.refresh_bone_transforms(),
                 lambda: comp.tick_component(0.1, unreal.LevelTick.LEVELTICK_ALL, None)):
        try:
            call()
        except Exception:
            pass


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(LOBBY)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

    C = unreal.Vector(0.0, 0.0, 300.0)              # isolated above the loaded map; char faces +X (UE forward)
    camera_offsets = {"side": None, "front": None, "threequarter": None, "back": None}
    if ANGLE not in camera_offsets:
        raise RuntimeError(f"unknown studio angle '{ANGLE}', expected one of {sorted(camera_offsets)}")

    sk = unreal.load_asset(RIG); mat = unreal.load_asset(MAT); idle = unreal.load_asset(IDLE); cube = unreal.load_asset(CUBE)
    out["rig_loaded_type"] = type(sk).__name__ if sk else None
    if not isinstance(sk, unreal.SkeletalMesh):
        raise RuntimeError(f"rig asset did not load as SkeletalMesh: {RIG} -> {type(sk).__name__ if sk else None}")

    # the rigged alien faces the +X camera (this mesh's forward is -X, so yaw 180); posed in idle
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, C, unreal.Rotator(0.0, 0.0, 180.0))
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
    for m in ("set_update_animation_in_editor", "set_update_cloth_in_editor"):
        try:
            getattr(comp, m)(True)
        except Exception:
            pass
    if mat:
        for i in range(max(1, comp.get_num_materials())):
            comp.set_material(i, mat)
    if idle and POSE != "bind":
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        comp.set_animation(idle); comp.set_position(0.35); comp.play(False)
    else:
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        try:
            comp.set_animation(None)
        except Exception:
            pass
    evaluate_pose(comp)
    spawned.append(actor)
    unreal.EditorLevelLibrary.editor_invalidate_viewports()
    try:
        origin, extent = actor.get_actor_bounds(False)
    except Exception:
        origin = C
        extent = unreal.Vector(80.0, 80.0, 90.0)
    out["actor_bounds_origin"] = [round(origin.x, 3), round(origin.y, 3), round(origin.z, 3)]
    out["actor_bounds_extent"] = [round(extent.x, 3), round(extent.y, 3), round(extent.z, 3)]
    out["component_material_slots"] = comp.get_num_materials()
    bounds_max = max(abs(extent.x), abs(extent.y), abs(extent.z))
    if bounds_max < 10.0:
        raise RuntimeError(f"skeletal actor bounds too small to capture: extent={out['actor_bounds_extent']}")

    floor_z = origin.z - abs(extent.z)
    studio_center = unreal.Vector(origin.x, origin.y, floor_z)

    # neutral grey enclosure (cubes always occlude regardless of facing) -> kills bright sky that fools exposure
    def box(loc, scale):
        a = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, unreal.Rotator(0, 0, 0))
        a.static_mesh_component.set_static_mesh(cube)
        a.set_actor_scale3d(scale)
        spawned.append(a); return a
    if ROOM:
        box(unreal.Vector(studio_center.x, studio_center.y, floor_z - 10.0), unreal.Vector(30, 30, 0.2))
        box(unreal.Vector(studio_center.x - 350.0, studio_center.y, floor_z + 250.0), unreal.Vector(0.2, 30, 30))
        box(unreal.Vector(studio_center.x, studio_center.y - 500.0, floor_z + 250.0), unreal.Vector(30, 0.2, 30))
        box(unreal.Vector(studio_center.x, studio_center.y + 500.0, floor_z + 250.0), unreal.Vector(30, 0.2, 30))

    # 3-point lighting (neutral, moderate -- a studio rig, NOT a glow hack on the character)
    def dlight(rot, inten, col):
        a = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(C.x, C.y, C.z + 300), rot)
        try:
            a.directional_light_component.set_intensity(inten)
            a.directional_light_component.set_light_color(col)
        except Exception:
            pass
        spawned.append(a); return a
    dlight(unreal.Rotator(-40.0, 180.0, 0.0), 3.0, unreal.LinearColor(1.0, 0.99, 0.97, 1.0))   # key from +X (front), down
    dlight(unreal.Rotator(-15.0, 70.0, 0.0), 1.6, unreal.LinearColor(0.7, 0.8, 1.0, 1.0))       # cool side fill
    dlight(unreal.Rotator(-55.0, 0.0, 0.0), 3.0, unreal.LinearColor(0.8, 0.88, 1.0, 1.0))       # rim from behind (-X)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(origin.x, origin.y, origin.z + 150))
    try:
        sky.sky_light_component.set_intensity(1.0)
    except Exception:
        pass
    spawned.append(sky)

    # render target + scene capture with LOCKED manual exposure (silver isn't crushed by auto-exposure)
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 1200, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    distance = max(430.0, bounds_max * 4.0)
    camera_offsets = {
        "side": unreal.Vector(distance, 0.0, extent.z * 0.1),
        "front": unreal.Vector(0.0, -distance, extent.z * 0.1),
        "threequarter": unreal.Vector(distance * 0.72, -distance * 0.72, extent.z * 0.16),
        "back": unreal.Vector(0.0, distance, extent.z * 0.1),
    }
    off = camera_offsets[ANGLE]
    cam_loc = unreal.Vector(origin.x + off.x, origin.y + off.y, origin.z + off.z)
    target = unreal.Vector(origin.x, origin.y, origin.z + extent.z * 0.05)
    out["camera_loc"] = [round(cam_loc.x, 3), round(cam_loc.y, 3), round(cam_loc.z, 3)]
    out["camera_target"] = [round(target.x, 3), round(target.y, 3), round(target.z, 3)]
    rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, target)
    cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, rot)
    cc = cap.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)
    pp = cc.get_editor_property("post_process_settings")
    pp.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    pp.set_editor_property("auto_exposure_bias", 9.5)     # neutral-ish: don't clip a DARK albedo up to grey
    cc.set_editor_property("post_process_settings", pp)
    spawned.append(cap)
    cc.capture_scene()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), OUT_NAME)
    png = OUT_DIR / OUT_NAME
    out["png"] = str(png); out["png_exists"] = png.exists()
    out["png_bytes"] = png.stat().st_size if png.exists() else 0
    out["ok"] = out["png_exists"] and out["png_bytes"] > 2000
finally:
    for a in spawned:
        try:
            eas.destroy_actor(a)
        except Exception:
            pass
RES.parent.mkdir(parents=True, exist_ok=True)
try:
    RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
except Exception:
    pass
unreal.log("DIMWIT_STUDIO_CAPTURE_DONE ok=" + str(out.get("ok")))
