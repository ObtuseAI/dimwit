"""EXPERIMENT G (Phase 3): do SESSION-SPAWNED actors render their materials at all in this lane?

The map's own actors (floor/pads/backdrop, base materials) render correctly in every capture while
the spawned character never does, across four different material states. Three captures, one session:
  1_static_kitlit   - spawned StaticMeshActor cube using M_KitLit (renders correctly ON MAP ACTORS)
  2_static_rigship  - spawned StaticMeshActor cube using the new M_ZythanRigShip base material
  3_skeletal_rigship- the rig itself (known-white case, control)
1 OK + 2 OK + 3 white -> skeletal-specific (GPUSkin permutation) problem.
1 OK + 2 white        -> M_ZythanRigShip shader map not ready anywhere.
1 white               -> session-spawned actors never render current materials in this lane at all;
                         the gate subject must become SAVED MAP CONTENT.
Read-only (spawned actors destroyed, nothing saved).
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "spawned_actor_render_result.json"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
CUBE = "/Engine/BasicShapes/Cube"
KITLIT = "/Game/Wanefall/Dimwit/MapKit/M_KitLit"
RIGSHIP = "/Game/Wanefall/Dimwit/CharactersRigged/M_ZythanRigShip"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
result = {"captures": {}}

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
    cube = unreal.load_asset(CUBE)
    kitlit = unreal.load_asset(KITLIT)
    rigship = unreal.load_asset(RIGSHIP)
    sk = unreal.load_asset(RIG)

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
        return str(OUT_DIR / name)

    for label, mat in (("1_static_kitlit", kitlit), ("2_static_rigship", rigship)):
        actor = eas.spawn_actor_from_class(unreal.StaticMeshActor, base + unreal.Vector(0, 0, 60), unreal.Rotator(0, 0, 30))
        comp = actor.static_mesh_component
        comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        comp.set_editor_property("static_mesh", cube)
        if isinstance(mat, unreal.MaterialInterface):
            comp.set_material(0, mat)
        result["captures"][label] = snap(f"spawn_{label}.png")
        eas.destroy_actor(actor)

    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 180))
    comp = actor.skeletal_mesh_component
    (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
    result["captures"]["3_skeletal_rigship"] = snap("spawn_3_skeletal_rigship.png")
    m0 = comp.get_material(0)
    result["skeletal_slot0"] = m0.get_path_name() if m0 else None
    eas.destroy_actor(actor)
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("SPAWN_RENDER_RESULT:", json.dumps(result)[:400])
