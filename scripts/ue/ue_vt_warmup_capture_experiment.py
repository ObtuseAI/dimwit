"""EXPERIMENT F (Phase 3): virtual-texture warm-up. Are the character textures VT, and do
repeated scene captures stream the pages in (VT feedback is processed by the renderer per frame,
not by game-thread ticks)?

Captures the zythan rig 6 times with short waits; exports first and last. If the last frame is
textured while the first is white, the fix is a warm-up loop in the probe capture - small, clean,
no gate changes. Also records virtual_texture_streaming on the character textures. Read-only.
"""
import json
import time
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "vt_warmup_result.json"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
TEXTURES = [
    "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_0",
    "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/Textures/Image_1",
]
result = {"textures": {}, "captures": []}

try:
    for tp in TEXTURES:
        tex = unreal.load_asset(tp)
        if isinstance(tex, unreal.Texture2D):
            rec = {}
            for prop in ("virtual_texture_streaming", "never_stream"):
                try:
                    rec[prop] = bool(tex.get_editor_property(prop))
                except Exception as exc:
                    rec[prop] = f"unreadable:{exc}"
            try:
                rec["size"] = [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]
            except Exception:
                pass
            result["textures"][tp] = rec

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
    anim = unreal.load_asset("/Game/Mannequins/Animations/Manny/MM_Idle")
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 180))
    comp = actor.skeletal_mesh_component
    (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
    if anim:
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        comp.set_animation(anim)
        comp.set_position(0.3)
        comp.play(False)

    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cam = unreal.Vector(base.x + 430.0, base.y, base.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 90.0))
    capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
    cc = capactor.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)

    for i in range(6):
        cc.capture_scene()
        if i in (0, 5):
            name = f"vt_warm_{i}.png"
            unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), name)
            result["captures"].append(str(OUT_DIR / name))
        time.sleep(2.0)

    eas.destroy_actor(actor)
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("VT_WARMUP_RESULT:", json.dumps(result)[:400])
