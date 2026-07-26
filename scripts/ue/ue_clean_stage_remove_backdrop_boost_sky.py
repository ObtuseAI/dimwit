"""Fix clean stage for optics pass:
1. Destroy GrayBackdrop — the plane edge was being flagged as stray_placeholder_geometry by GLM-5V.
2. Boost SkyLight to 3.0 (neutral ambient fill, no SkyAtmosphere = no orange tint).
   This fills the character's shadow side, eliminating the "sliced in half" reading.

No material changes needed — silver-grey ekris_optics_proof_mat is correctly saved.
No exposure changes — 7.5 is correct for this light level.

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_remove_backdrop_result.json")
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

        # 1) Remove the backdrop — it was causing stray_placeholder_geometry reads in GLM-5V
        if lbl == "GrayBackdrop":
            eas.destroy_actor(a)
            log("destroyed GrayBackdrop")
            continue

        # 2) Boost SkyLight to 3.0 for soft omnidirectional ambient fill
        #    No SkyAtmosphere = neutral grey ambient (no orange tint).
        #    3.0 provides enough fill to soften the character's shadow side.
        if isinstance(a, unreal.SkyLight):
            try:
                a.light_component.set_intensity(3.0)
                log(f"SkyLight '{lbl}' intensity -> 3.0 (neutral ambient fill)")
            except Exception as e:
                log(f"SkyLight error: {e}")
            continue

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_REMOVE_BACKDROP_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_REMOVE_BACKDROP_DONE ok={out['ok']}")
