"""ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1 - session 2: photograph the variant row.

MUST run with -NoTextureStreaming (capture law clause 2: tick-less sessions never stream mips).
Captures each RigMatExperiment_* display with the exact production probe framing so variants
compare 1:1 against cap_rig_ship history. Records the effective component material per capture
as honest evidence of what was photographed.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_mat_experiment_capture.py" -NoTextureStreaming
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_mat_experiment")
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
result = {"ok": False, "captures": {}}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

    try:
        result["texture_streaming_off"] = (
            unreal.SystemLibrary.get_console_variable_int_value("r.TextureStreaming") == 0)
    except Exception:
        result["texture_streaming_off"] = None

    displays = sorted(
        (a for a in eas.get_all_level_actors()
         if isinstance(a, unreal.SkeletalMeshActor) and a.get_actor_label().startswith("RigMatExperiment_")),
        key=lambda a: a.get_actor_label())
    if not displays:
        raise RuntimeError("no RigMatExperiment_* displays found (run scripts/ue/ue_zythan_mat_experiment_install.py)")

    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900,
                                                        unreal.TextureRenderTargetFormat.RTF_RGBA8)
    capactor = None
    for actor in displays:
        label = actor.get_actor_label()
        comp = actor.skeletal_mesh_component
        for tick_call in (lambda: comp.tick_pose(0.1, False),
                          lambda: comp.tick_animation(0.1, False),
                          lambda: comp.tick_component(0.1, unreal.LevelTick.LEVELTICK_ALL, None)):
            try:
                tick_call()
            except Exception:
                pass
        loc = actor.get_actor_location()
        cam_pos = unreal.Vector(loc.x + 430.0, loc.y, loc.z + 95.0)   # production probe framing
        rot = unreal.MathLibrary.find_look_at_rotation(cam_pos, unreal.Vector(loc.x, loc.y, loc.z + 90.0))
        if capactor is None:
            capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam_pos, rot)
            cc = capactor.capture_component2d
            cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
            cc.set_editor_property("texture_target", rt)
            cc.set_editor_property("fov_angle", 42.0)
            cc.set_editor_property("capture_every_frame", False)
        else:
            capactor.set_actor_location(cam_pos, False, False)
            capactor.set_actor_rotation(rot, False)
        cc.capture_scene()
        png_name = label + ".png"
        unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), png_name)
        mats = [m.get_path_name() if m else None for m in comp.get_materials()]
        result["captures"][label] = {
            "png": str(OUT_DIR / png_name),
            "exists": (OUT_DIR / png_name).exists(),
            "effective_materials": mats,
        }
    if capactor is not None:
        eas.destroy_actor(capactor)
    result["ok"] = all(c["exists"] for c in result["captures"].values())
except Exception:
    result["error"] = traceback.format_exc()

OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "capture_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("MAT_EXPERIMENT_CAPTURE:", json.dumps(result)[:500])
