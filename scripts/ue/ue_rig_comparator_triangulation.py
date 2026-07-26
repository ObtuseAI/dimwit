"""EXPERIMENT E (Phase 2/3): triangulate with the historically-PASSING comparator.

The rig_ship gate passed on 2026-06-29 when the active rig was VORLAX; zythan's rig was created
2026-06-30 and became the active rig only at today's quarantine swap. So 'white zythan' may be a
never-worked asset, not a regressed pipeline. One session, same camera, three captures:
  A: vorlax rig (the 06-29 passing subject, still on disk though quarantined - read-only render)
  B: zythan rig (current active subject, renders white)
  C: static zythan mesh + its pbr_material (import-created instance)
Textured A + white B  -> zythan rig asset/material defect (rebuild zythan's rig lane like vorlax's).
White A + white B     -> the capture path lost skeletal-material rendering since 06-29.
Textured C + white B  -> rig-specific (e.g. UVs lost in the rigging export).
Read-only: no saves, spawned actors destroyed.
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "rig_comparator_result.json"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
SUBJECTS = [
    ("A_vorlax_rig", "skeletal", "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_01_vorlax_Rig"),
    ("B_zythan_rig", "skeletal", "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"),
    ("C_zythan_static", "static", "/Game/Wanefall/Dimwit/Characters/SM_Char_03_zythan/StaticMeshes/SM_Char_03_zythan"),
]
result = {"subjects": {}}

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
    anim = unreal.load_asset("/Game/Mannequins/Animations/Manny/MM_Idle")
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cam = unreal.Vector(base.x + 430.0, base.y, base.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 90.0))
    capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
    cc = capactor.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)

    for name, kind, path in SUBJECTS:
        rec = {"path": path}
        try:
            asset = unreal.load_asset(path)
            rec["loaded"] = bool(asset)
            if kind == "skeletal" and isinstance(asset, unreal.SkeletalMesh):
                actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 180))
                comp = actor.skeletal_mesh_component
                (comp.set_skeletal_mesh_asset(asset) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(asset))
                if anim:
                    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                    comp.set_animation(anim)
                    comp.set_position(0.3)
                    comp.play(False)
                m0 = comp.get_material(0)
                rec["slot0"] = m0.get_path_name() if m0 else None
            elif kind == "static" and isinstance(asset, unreal.StaticMesh):
                actor = eas.spawn_actor_from_class(unreal.StaticMeshActor, base, unreal.Rotator(0, 0, 180))
                comp = actor.static_mesh_component
                comp.set_editor_property("static_mesh", asset)
                m0 = comp.get_material(0)
                rec["slot0"] = m0.get_path_name() if m0 else None
            else:
                rec["error"] = f"unexpected class {type(asset).__name__ if asset else None}"
                result["subjects"][name] = rec
                continue
            cc.capture_scene()
            unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), f"tri_{name}.png")
            rec["png"] = str(OUT_DIR / f"tri_{name}.png")
            eas.destroy_actor(actor)
        except Exception:
            rec["error"] = traceback.format_exc().splitlines()[-1]
        result["subjects"][name] = rec

    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("TRIANGULATION_RESULT:", json.dumps(result)[:500])
