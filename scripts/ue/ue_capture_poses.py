"""Dimwit DEFORMATION capture (the #32 layer): load the RIGGED skeletal mesh, pose it across a locomotion
STRESS SET (bind + idle/walk/run/jump/turn frames), and render each pose offscreen via SceneCapture2D -> PNG.
This is the evidence the deformation QA needs — structural rig QA (weights/influences/bones) cannot see a
candy-wrapper twist collapse or a skinning blowup, but these posed silhouettes do.

Follows the proven scripts/ue/ue_capture_hold.py pattern (temp backdrop + neutral key/sky + LOCKED exposure + cleanup of
every spawned helper so the saved map is untouched). Fail-closed: writes which poses captured + which anims
were missing so the QA can refuse to certify deformation it could not measure.

Run (headless):  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_capture_poses.py rig_path=/Game/... asset=SM_Char_02_ekris out_dir=<dir> mat=/Game/...pbr_material"
"""
import unreal, json, sys, traceback
from pathlib import Path

# -------- args (key=value, like scripts/ue/ue_rig_io.py) --------
ARGS = {}
for a in sys.argv:
    if "=" in a:
        k, v = a.split("=", 1)
        ARGS[k.strip()] = v.strip()

RIG = ARGS.get("rig_path", "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig")
ASSET = ARGS.get("asset", "SM_Char_02_ekris")
MAT = ARGS.get("mat", "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material.pbr_material")
OUT_DIR = Path(ARGS.get("out_dir", r"C:/Users/developer/Documents/Dimwit/artifacts/pose_capture") + f"/{ASSET}")
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/pose_capture_result.json")
MAP = ARGS.get("map", "/Game/Wanefall/Maps/Wanefall_Lobby")

# The stress set: bind (reference pose) + frames of real locomotion that exercise shoulders/hips/spine. A rig
# that looks bad in NORMAL motion fails here — which is exactly how the player will see it. Missing anims are
# skipped and reported (never silently dropped). (name, anim_path|None, position_seconds)
POSES = [
    ("bind",  None, 0.0),
    ("idle",  "/Game/Mannequins/Animations/Manny/MM_Idle", 0.35),
    ("walk",  "/Game/Mannequins/Animations/Manny/MM_Walk_Fwd", 0.40),
    ("run",   "/Game/Mannequins/Animations/Manny/MM_Run_Fwd", 0.20),
    ("jump",  "/Game/Mannequins/Animations/Manny/MM_Jump", 0.50),
    ("fall",  "/Game/Mannequins/Animations/Manny/MM_Fall_Loop", 0.30),   # spread limbs — shoulder/hip stress
    ("land",  "/Game/Mannequins/Animations/Manny/MM_Land", 0.20),        # compression — spine/knee stress
]

def _evaluate_pose(comp):
    """Force the skeletal component to actually evaluate + push the current single-node pose to the render
    state in a headless editor (no PIE world tick does it for us). Without this the capture is the frozen
    bind pose every time.

    Order matters: tick_animation/tick_pose EVALUATE the single-node anim instance; refresh_bone_transforms
    PUSHES the evaluated pose to the render bone buffer that SceneCapture reads. We repeat a few times because
    the first tick after set_position can land on the prior frame. Requires ALWAYS_TICK_POSE_AND_REFRESH_BONES
    (set at setup) or these no-op on an unrendered headless component."""
    # Proven params (scripts/ue/ue_probe_pose_eval.py: hand bone moved 20cm): a small NON-zero dt tick_animation actually
    # evaluates the single-node pose; dt=0 with a frozen play rate evaluates NOTHING (bone stays at bind). Each
    # pose re-calls play_animation fresh + set_position, so the tiny 0.1 advance stays on that pose. refresh/
    # finalize push the evaluated pose to the render bone buffer that SceneCapture reads.
    for _ in range(2):
        for call in (lambda: comp.tick_animation(0.1, False),
                     lambda: comp.tick_pose(0.1, False),
                     lambda: comp.refresh_bone_transforms(),
                     lambda: comp.finalize_bone_transform()):
            try:
                call()
            except Exception:
                pass


out = {"ok": False, "asset": ASSET, "rig": RIG, "poses": {}, "missing_anims": [], "captured": []}
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(MAP)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location(); break
    char_loc = unreal.Vector(base.x, base.y, base.z)
    # Frame TIGHT: the deformation metric downsamples to 160px and averages over the whole frame, so a small
    # character (far camera) drowns real limb motion in static background -> deltas hover at the 0.004 frozen
    # floor and even good rigs fail as noise. Pull the camera in (tunable) so the body fills the frame and
    # genuine articulation clears the floor with margin. This calibrates the instrument; the floor is unchanged.
    CAM_DIST = float(ARGS.get("cam_dist", 320.0))
    cam_loc = unreal.Vector(char_loc.x, char_loc.y - CAM_DIST, char_loc.z + 110.0)

    sk = unreal.load_asset(RIG)
    if not sk:
        raise RuntimeError(f"rigged skeletal mesh not found: {RIG}")
    mat = unreal.load_asset(MAT)

    face = unreal.MathLibrary.find_look_at_rotation(char_loc, cam_loc)
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, char_loc, unreal.Rotator(0.0, 0.0, face.yaw))
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
    if mat:
        for i in range(max(1, comp.get_num_materials())):
            comp.set_material(i, mat)
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    # CRITICAL (headless-anim-needs-PIE trap): without this, set_animation/set_position do NOT evaluate in a
    # non-PIE editor and every capture renders the FROZEN bind pose. This makes the component tick + evaluate
    # animation in the editor world so the posed deformation actually reaches the render.
    for m in ("set_update_animation_in_editor", "set_update_cloth_in_editor"):
        try:
            getattr(comp, m)(True)
        except Exception:
            pass
    # ROOT-CAUSE FIX (frozen-capture regression): a headless component with no active view defaults to
    # VisibilityBasedAnimTickOption.ONLY_TICK_POSE_WHEN_RENDERED -> tick_pose no-ops (thinks it's unrendered)
    # and every stress pose renders identical to bind. Force ALWAYS_TICK_POSE_AND_REFRESH_BONES so the pose
    # evaluates + reaches the bone buffer regardless of visibility. Also disable URO frame-skipping.
    try:
        comp.set_editor_property("visibility_based_anim_tick_option",
                                 unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    except Exception as e:
        out["vis_tick_warn"] = str(e)
    for prop, val in (("enable_update_rate_optimizations", False), ("component_use_fixed_skel_bounds", True)):
        try:
            comp.set_editor_property(prop, val)
        except Exception:
            pass

    # temp backdrop + neutral capture lighting (destroyed after — game world untouched), as in hold capture
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    backdrop = eas.spawn_actor_from_class(unreal.StaticMeshActor,
        unreal.Vector(char_loc.x, char_loc.y + 320.0, char_loc.z + 180.0), unreal.Rotator(0, 0, 0))
    backdrop.static_mesh_component.set_static_mesh(cube)
    backdrop.set_actor_scale3d(unreal.Vector(24, 0.3, 24))
    temp = [backdrop]
    key = eas.spawn_actor_from_class(unreal.DirectionalLight,
        unreal.Vector(char_loc.x, char_loc.y - 200.0, char_loc.z + 400.0), unreal.Rotator(-35.0, 55.0, 0.0))
    try:
        key.directional_light_component.set_intensity(6.0)
        key.directional_light_component.set_light_color(unreal.LinearColor(1.0, 0.99, 0.97, 1.0))
    except Exception:
        pass
    temp.append(key)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(char_loc.x, char_loc.y, char_loc.z + 150.0))
    try:
        sky.sky_light_component.set_intensity(1.2)
    except Exception:
        pass
    temp.append(sky)

    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 1200, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    target = unreal.Vector(char_loc.x, char_loc.y, char_loc.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, target)
    cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, rot)
    cc = cap.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 50.0)
    cc.set_editor_property("capture_every_frame", False)
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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, anim_path, pos in POSES:
        if anim_path is None:
            comp.set_animation(None)        # bind / reference pose
            comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        else:
            anim = unreal.load_asset(anim_path)
            if not anim:
                out["missing_anims"].append(anim_path)
                continue
            # UE 5.8 fix (proven via scripts/ue/ue_probe_pose_eval.py -> only the SingleAnimationPlayData struct moved the
            # bone; set_animation()+set_position() and play_animation() left it at bind headless). Assign the
            # FSingleAnimationPlayData (anim_to_play + saved_position) directly, then tick to evaluate.
            pd = unreal.SingleAnimationPlayData()
            pd.set_editor_property("anim_to_play", anim)
            try:
                pd.set_editor_property("saved_position", float(pos))
            except Exception:
                pass
            comp.set_editor_property("animation_data", pd)
            try:
                comp.set_position(float(pos))
            except Exception:
                pass
        _evaluate_pose(comp)        # force headless anim eval so the pose actually reaches the render
        try:
            _bt = comp.get_socket_transform("hand_r", unreal.RelativeTransformSpace.RTS_WORLD).translation
            out.setdefault("bone_trace", {})[name] = [round(_bt.x, 2), round(_bt.y, 2), round(_bt.z, 2)]
        except Exception:
            pass
        cc.capture_scene()
        fname = f"pose_{name}.png"
        unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), fname)
        png = OUT_DIR / fname
        if png.exists() and png.stat().st_size > 2000:
            out["poses"][name] = str(png)
            out["captured"].append(name)

    # cleanup every spawned helper
    for actr in [cap, actor] + temp:
        try:
            eas.destroy_actor(actr)
        except Exception:
            pass

    out["bind"] = out["poses"].get("bind")
    # honest gate: need the bind + >=3 stress poses to certify deformation
    out["ok"] = bool(out["bind"]) and len([n for n in out["captured"] if n != "bind"]) >= 3
except Exception:
    out["error"] = traceback.format_exc()

RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_POSE_CAPTURE_DONE ok=" + str(out.get("ok")) + " captured=" + ",".join(out.get("captured", [])))
