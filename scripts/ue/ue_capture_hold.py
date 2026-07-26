"""Dimwit in-engine PROOF capture: load THE HOLD (lobby) map, spawn the RIGGED skeletal Ekris posed in MM_Idle
with the brightened silver PBR skin, and render it offscreen via a SceneCapture2D -> PNG (no screen-grab, no lock
screen). This is the honest 'did it actually change in-engine' check: it must read SILVER + be a posed humanoid
(not a grey static blob). Writes artifacts/hold_capture/hold_ekris.png + capture_result.json."""
import unreal, json, traceback
from pathlib import Path

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/hold_capture")
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/capture_result.json")
LOBBY = "/Game/Wanefall/Maps/Wanefall_Lobby"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig"
MAT = "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material.pbr_material"
IDLE = "/Game/Mannequins/Animations/Manny/MM_Idle"
RT_PKG = "/Game/Wanefall/Dimwit/_tmp_capture_rt"
out = {"ok": False}
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(LOBBY)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

    # pick a spawn spot: a PlayerStart if present, else origin
    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location()
            break

    char_loc = unreal.Vector(base.x, base.y, base.z)
    cam_loc = unreal.Vector(char_loc.x, char_loc.y - 320.0, char_loc.z + 110.0)
    sk = unreal.load_asset(RIG)
    mat = unreal.load_asset(MAT)
    idle = unreal.load_asset(IDLE)

    # face the character toward the camera (yaw only) so we see the FRONT, pose with MM_Idle
    face = unreal.MathLibrary.find_look_at_rotation(char_loc, cam_loc)
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, char_loc, unreal.Rotator(0.0, 0.0, face.yaw))
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
    if mat:
        for i in range(max(1, comp.get_num_materials())):
            comp.set_material(i, mat)
    if idle:
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        comp.set_animation(idle)
        comp.set_position(0.35)   # a frame into the idle so it's a natural pose, not bind pose
        comp.play(False)
    out["spawned"] = actor.get_name()
    out["pose"] = "MM_Idle@0.35" if idle else "ref"

    # TEMP grey backdrop behind the char (occludes the bright sky so auto-exposure settles mid and the silver
    # reads instead of crushing to a silhouette). Destroyed after the shot — game world untouched.
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    backdrop = eas.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(char_loc.x, char_loc.y + 320.0, char_loc.z + 180.0), unreal.Rotator(0, 0, 0))
    backdrop.static_mesh_component.set_static_mesh(cube)
    backdrop.set_actor_scale3d(unreal.Vector(24, 0.3, 24))

    # TEMP capture-only lighting (destroyed after the shot — NOT added to the game) so the skin tone is judgeable
    # rather than lost to the hold's dim cave ambient. Neutral white key + soft sky fill, no color/glow tricks.
    temp_lights = []
    key = eas.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(char_loc.x, char_loc.y - 200.0, char_loc.z + 400.0),
        unreal.Rotator(-35.0, 55.0, 0.0))
    try:
        key.directional_light_component.set_intensity(6.0)
        key.directional_light_component.set_light_color(unreal.LinearColor(1.0, 0.99, 0.97, 1.0))
    except Exception:
        pass
    temp_lights.append(key)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(char_loc.x, char_loc.y, char_loc.z + 150.0))
    try:
        sky.sky_light_component.set_intensity(1.2)
    except Exception:
        pass
    temp_lights.append(sky)

    # render target
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1600, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)

    # SceneCapture2D in front of the char, eye height, looking at the chest
    target = unreal.Vector(char_loc.x, char_loc.y, char_loc.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, target)
    cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, rot)
    cc = cap.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 50.0)
    cc.set_editor_property("capture_every_frame", False)
    # LOCK exposure (clamp histogram min==max) so the subject isn't crushed to a silhouette by the bright sky.
    # Override booleans MUST be enabled or the struct values are ignored.
    pp = cc.get_editor_property("post_process_settings")
    for ob in ("override_auto_exposure_min_brightness", "override_auto_exposure_max_brightness",
               "override_auto_exposure_bias"):
        try:
            pp.set_editor_property(ob, True)
        except Exception:
            pass
    pp.set_editor_property("auto_exposure_min_brightness", 1.0)
    pp.set_editor_property("auto_exposure_max_brightness", 1.0)
    pp.set_editor_property("auto_exposure_bias", 1.0)
    cc.set_editor_property("post_process_settings", pp)
    cc.capture_scene()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok_exp = unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), "hold_ekris.png")
    png = OUT_DIR / "hold_ekris.png"
    out["png"] = str(png)
    out["png_exists"] = png.exists()
    out["png_bytes"] = png.stat().st_size if png.exists() else 0

    # cleanup spawned helpers so the saved map isn't polluted (temp lights included — game lighting untouched)
    eas.destroy_actor(cap)
    eas.destroy_actor(actor)
    try:
        eas.destroy_actor(backdrop)
    except Exception:
        pass
    for L in temp_lights:
        try:
            eas.destroy_actor(L)
        except Exception:
            pass
    out["ok"] = out["png_exists"] and out["png_bytes"] > 2000
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_HOLD_CAPTURE_DONE ok=" + str(out.get("ok")))
