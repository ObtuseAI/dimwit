"""Hide the Floor StaticMeshActor so its edge doesn't appear as stray geometry to GLM-5V.
The character will float against a pure black void — a common hero-render convention.

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_hide_floor_result.json")
out = {"ok": False, "log": []}

def log(msg):
    out["log"].append(msg)

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    les.load_level(MAP)
    log("map loaded")

    world = ues.get_editor_world()
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.Actor.static_class()))

    for a in actors:
        try:
            lbl = a.get_actor_label()
        except Exception:
            lbl = "?"

        # Hide the Floor — its edge against the black void reads as stray geometry
        if lbl == "Floor" and isinstance(a, unreal.StaticMeshActor):
            a.set_actor_hidden_in_game(True)
            log("Floor hidden_in_game=True")
            continue

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_HIDE_FLOOR_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_HIDE_FLOOR_DONE ok={out['ok']}")
