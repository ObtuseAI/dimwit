"""EXPERIMENT C (Phase 3): is the white figure a MAP actor rather than the spawned rig?

Every render of Wanefall_ModeShell_Prototype_01 from the rig_ship camera shows the same white
character regardless of spawned-actor material state. Capture the scene WITHOUT spawning anything;
if the figure is still there, it is baked into the map (a display statue from an earlier dressing
pass) and every 'rig capture' has been photographing map furniture. Also dumps all actors with
mesh components near the PlayerStart. Read-only.
"""
import json
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/shader_wait_experiment")
OUT = OUT_DIR / "ghost_figure_probe_result.json"
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
result = {"nearby_actors": [], "all_mesh_actors": []}

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
    result["player_start"] = [base.x, base.y, base.z]

    for a in eas.get_all_level_actors():
        rec = None
        loc = a.get_actor_location()
        dist = ((loc.x - base.x) ** 2 + (loc.y - base.y) ** 2 + (loc.z - base.z) ** 2) ** 0.5
        meshes = []
        for comp in a.get_components_by_class(unreal.StaticMeshComponent):
            sm = comp.static_mesh
            if sm:
                mats = [comp.get_material(i).get_path_name() if comp.get_material(i) else None
                        for i in range(comp.get_num_materials())]
                meshes.append({"kind": "static", "mesh": sm.get_path_name(), "materials": mats})
        for comp in a.get_components_by_class(unreal.SkeletalMeshComponent):
            sk = comp.get_skeletal_mesh_asset() if hasattr(comp, "get_skeletal_mesh_asset") else comp.skeletal_mesh
            if sk:
                mats = [comp.get_material(i).get_path_name() if comp.get_material(i) else None
                        for i in range(comp.get_num_materials())]
                meshes.append({"kind": "skeletal", "mesh": sk.get_path_name(), "materials": mats})
        if meshes:
            rec = {"actor": a.get_actor_label(), "class": type(a).__name__,
                   "distance_from_playerstart": round(dist, 1), "meshes": meshes}
            result["all_mesh_actors"].append(rec)
            if dist < 900.0:
                result["nearby_actors"].append(rec)

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
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), "ghost_empty_scene.png")
    png = OUT_DIR / "ghost_empty_scene.png"
    result["empty_scene_png"] = str(png)
    result["empty_scene_bytes"] = png.stat().st_size if png.exists() else 0
    eas.destroy_actor(capactor)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()
    result["ok"] = False

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("GHOST_PROBE_DONE")
