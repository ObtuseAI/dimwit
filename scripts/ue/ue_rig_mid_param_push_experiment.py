"""EXPERIMENT D (Phase 3): does an explicit MID parameter push render correctly where the saved
MIC renders as parent defaults?

All evidence says the spawned skeletal component renders zythan_mat with PARENT DEFAULT (white)
values: instance uniform-expression caches never refresh in this tick-less headless path, and
post-registration set_material calls never land either. MaterialInstanceDynamic parameter setters
enqueue render commands directly on the game thread - no tick required. If pushing the texture +
dark factors through a MID renders the dark textured character, the root cause and the fix are
both proven: the probe capture must drive the rig material through an explicitly-parameterized MID
(exactly what the in-game path effectively does every frame).
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "mid_param_push_result.json"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
ZY_MAT = "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat"
BASECOLOR_TEX = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_0"
METALROUGH_TEX = "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_1"
result = {"steps": []}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location()
            break
    sk = unreal.load_asset(RIG)
    zymat = unreal.load_asset(ZY_MAT)
    alb = unreal.load_asset(BASECOLOR_TEX)
    mr = unreal.load_asset(METALROUGH_TEX)
    anim = unreal.load_asset("/Game/Mannequins/Animations/Manny/MM_Idle")

    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 180))
    comp = actor.skeletal_mesh_component
    (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
    if anim:
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        comp.set_animation(anim)
        comp.set_position(0.3)
        comp.play(False)

    mid = comp.create_dynamic_material_instance(0, zymat)
    result["mid_created"] = bool(mid)
    if mid:
        if isinstance(alb, unreal.Texture):
            mid.set_texture_parameter_value("BaseColorTexture", alb)
        if isinstance(mr, unreal.Texture):
            mid.set_texture_parameter_value("MetallicRoughnessTexture", mr)
        mid.set_vector_parameter_value("BaseColorFactor", unreal.LinearColor(0.10, 0.11, 0.14, 1.0))
        mid.set_vector_parameter_value("EmissiveFactor", unreal.LinearColor(0.21, 0.15, 0.52, 1.0))
        mid.set_scalar_parameter_value("EmissiveStrength", 1.8)
        mid.set_scalar_parameter_value("MetallicFactor", 0.1)
        result["steps"].append("mid params pushed (texture + dark factor + violet emissive)")

    # pump the component like ue_capture_studio does
    for call in (lambda: comp.tick_pose(0.1, False),
                 lambda: comp.tick_animation(0.1, False),
                 lambda: comp.tick_component(0.1, unreal.LevelTick.LEVELTICK_ALL, None)):
        try:
            call()
        except Exception:
            pass

    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cam = unreal.Vector(base.x + 430.0, base.y, base.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 90.0))
    capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
    cc = capactor.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)
    cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), "mid_push.png")
    png = OUT_DIR / "mid_push.png"
    result["png"] = str(png)
    eas.destroy_actor(actor)
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("MID_PUSH_RESULT:", json.dumps(result)[:300])
