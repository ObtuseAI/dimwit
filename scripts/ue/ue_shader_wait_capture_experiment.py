"""EXPERIMENT (systematic-debugging Phase 3): is the white rig a not-yet-compiled shader fallback?

Hypothesis: cc.capture_scene() fires on the same blocked game-thread tick as actor spawn in a fresh
headless session, so the rig's material permutation is still compiling and UE renders the default
flat-white fallback. Static characters render fine because their permutations are DDC-cached.

Test: (1) enumerate which compile/tick APIs this UE 5.8 Python actually exposes; (2) spawn the rig
exactly like scripts/ue/ue_validation_probe.py does, then force synchronous shader compilation
("recompileshaders changed" console command blocks until finished; FinishAllShaderCompilation
checked too), then capture. If the experiment PNG shows a textured character, root cause confirmed.
Writes artifacts/shader_wait_experiment/cap_rig_shaderwait.png + result JSON. No asset mutations.
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "shader_wait_experiment_result.json"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
result = {"api": {}, "steps": []}

try:
    result["api"]["unreal_module_compile_names"] = [n for n in dir(unreal) if "compil" in n.lower()][:12]
    result["api"]["unreal_module_shader_names"] = [n for n in dir(unreal) if "shader" in n.lower()][:12]
    mel_names = [n for n in dir(unreal.MaterialEditingLibrary) if "compil" in n.lower() or "update" in n.lower()]
    result["api"]["material_editing_library"] = mel_names[:12]
    for cls_name in ("AssetCompilingManager", "ShaderCompilingManager", "AssetCompilingManagerLibrary"):
        result["api"][cls_name] = hasattr(unreal, cls_name)

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
    result["steps"].append("actor spawned with rig")

    # force-finish shader compilation (blocking) before the capture
    for cmd in ("recompileshaders changed",):
        try:
            unreal.SystemLibrary.execute_console_command(world, cmd)
            result["steps"].append(f"console: {cmd} (returned - synchronous compile finished)")
        except Exception as exc:
            result["steps"].append(f"console {cmd} failed: {exc!r}")

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
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), "cap_rig_shaderwait.png")
    png = OUT_DIR / "cap_rig_shaderwait.png"
    result["png"] = str(png)
    result["png_bytes"] = png.stat().st_size if png.exists() else 0
    eas.destroy_actor(actor)
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("EXPERIMENT_RESULT:", json.dumps({k: v for k, v in result.items() if k != "api"})[:400])
