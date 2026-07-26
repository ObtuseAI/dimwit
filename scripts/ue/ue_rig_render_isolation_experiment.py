"""EXPERIMENT B (Phase 3): isolate WHERE the white comes from - component resolution, the
Interchange MIC chain, or the capture pipeline. One session, four captures, no asset mutations.

  cap A: spawn rig exactly like the probe -> what does comp.get_material(0) resolve? render.
  cap B: override slot 0 with a plain project Material (M_WaneEnemyDarkBody4, skeletal-ready,
         hardcoded dark) -> if this renders dark, rendering+capture are fine and the fault is
         in the material chain the slot resolves.
  cap C: force-set the saved zythan_mat directly on the component -> if still white while B is
         dark, the Interchange-parented MIC provably renders white on skeletal components.
  cap D: dynamic instance created FROM zythan_mat -> checks MID resolution of the same chain.
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "rig_render_isolation_result.json"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
ZY_MAT = "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat"
DARK_MAT = "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4"
result = {"captures": {}, "component": {}}

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
    darkmat = unreal.load_asset(DARK_MAT)
    anim = unreal.load_asset("/Game/Mannequins/Animations/Manny/MM_Idle")

    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 180))
    comp = actor.skeletal_mesh_component
    (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
    if anim:
        comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        comp.set_animation(anim)
        comp.set_position(0.3)
        comp.play(False)

    result["component"]["num_materials"] = comp.get_num_materials()
    m0 = comp.get_material(0)
    result["component"]["resolved_slot0"] = m0.get_path_name() if m0 else None

    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cam = unreal.Vector(base.x + 430.0, base.y, base.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 90.0))
    capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
    cc = capactor.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)

    def snap(name):
        cc.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), name)
        p = OUT_DIR / name
        return {"png": str(p), "bytes": p.stat().st_size if p.exists() else 0}

    result["captures"]["A_as_spawned"] = snap("iso_A_as_spawned.png")

    if isinstance(darkmat, unreal.MaterialInterface):
        comp.set_material(0, darkmat)
        result["captures"]["B_project_dark_override"] = snap("iso_B_dark_override.png")

    if isinstance(zymat, unreal.MaterialInterface):
        comp.set_material(0, zymat)
        result["captures"]["C_zythan_mat_forced"] = snap("iso_C_zythan_forced.png")
        mid = comp.create_dynamic_material_instance(0, zymat)
        result["captures"]["D_zythan_mid"] = snap("iso_D_zythan_mid.png")
        result["component"]["mid_parent"] = mid.get_editor_property("parent").get_path_name() if mid else None

    eas.destroy_actor(actor)
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("ISOLATION_RESULT:", json.dumps(result)[:500])
