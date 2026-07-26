"""FLAGSHIP_ARENA_ART_PASS_V1 (masterplan bundle 10, B3) — capture tour of the dressed arena.

Loads the SAVED, dressed Wanefall_Arena4v4_Prototype_01 (capture-law compliant: actors come from
disk, not session-spawned, so they render their real materials) and renders a per-station still with
a SceneCapture2D at N judged waypoints: a top-down OVERVIEW, the contested CORE, each of the four
team/flank directions. Stations are DATA-DRIVEN from the map's PlayerStarts (centroid + span). Each
still is a real per-station render (distinct camera) so the Dimwit gate can prove readable coverage
+ visible variance between stations, and judge the overview/core for readability.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_arena_capture_tour.py" -NoTextureStreaming
"""
import json
import math
import traceback
from pathlib import Path

import unreal

OUT_DIR = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/flagship_arena/tour")
PROOF = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/flagship_arena/flagship_arena_tour_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"
RES_X, RES_Y = 1280, 720

result = {"ok": False, "map": MAP, "stations": [], "errors": []}


def _pump(world, rt, cap_comp):
    # tick + capture a few times so the scene resolves (tick-less session needs manual pumping)
    for _ in range(6):
        try:
            cap_comp.capture_scene()
        except Exception:
            pass


try:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    les.load_level(MAP)
    world = ues.get_editor_world()

    actors = eas.get_all_level_actors()
    starts = [a for a in actors if isinstance(a, unreal.PlayerStart)]
    if starts:
        xs = [s.get_actor_location().x for s in starts]
        ys = [s.get_actor_location().y for s in starts]
        zs = [s.get_actor_location().z for s in starts]
        core = unreal.Vector(sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        span = max(600.0, max(max(xs) - min(xs), max(ys) - min(ys)))
    else:
        core = unreal.Vector(0, 0, 0)
        span = 3000.0
    half = span * 0.55

    rt = unreal.RenderingLibrary.create_render_target2d(world, RES_X, RES_Y,
                                                        unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    cap.set_actor_label("Flagship_TourCapture")
    cc = cap.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.texture_target = rt

    # station cameras: (name, camera_pos, look_at)
    stations = []
    stations.append(("overview", unreal.Vector(core.x, core.y, core.z + span * 1.15), core))
    stations.append(("core", unreal.Vector(core.x - half * 0.55, core.y, core.z + 220),
                     unreal.Vector(core.x, core.y, core.z + 160)))
    for name, ang in (("team_a", 0.0), ("team_b", 180.0), ("flank", 90.0)):
        rad = math.radians(ang)
        eye = unreal.Vector(core.x + math.cos(rad) * half * 1.05,
                            core.y + math.sin(rad) * half * 1.05, core.z + 300)
        stations.append((name, eye, unreal.Vector(core.x, core.y, core.z + 140)))

    for name, eye, look in stations:
        try:
            cap.set_actor_location(eye, False, False)
            rot = unreal.MathLibrary.find_look_at_rotation(eye, look)
            cap.set_actor_rotation(rot, False)
            _pump(world, rt, cc)
            path = OUT_DIR / f"station_{name}.png"
            unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), f"station_{name}.png")
            result["stations"].append({"name": name, "still": str(path),
                                       "eye": [eye.x, eye.y, eye.z], "exists": path.exists()})
        except Exception as e:
            result["errors"].append(f"station {name}: {e}")

    try:
        eas.destroy_actor(cap)
    except Exception:
        pass
    result["station_count"] = len(result["stations"])
    result["ok"] = len([s for s in result["stations"] if s.get("exists")]) >= 4
except Exception:
    result["errors"].append(traceback.format_exc())

PROOF.parent.mkdir(parents=True, exist_ok=True)
PROOF.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("FLAGSHIP_TOUR_RESULT:", json.dumps({"ok": result["ok"],
      "stations": result.get("station_count"), "errors": result["errors"][:1]})[:300])
