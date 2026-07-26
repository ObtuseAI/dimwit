"""Tune the clean stage exposure after removing SkyAtmosphere:
- Without the warm sky, 25 Lux DirectionalLight + bias=10.5 overexposes to white.
- Reduce DirectionalLight to 8.0 Lux (softer key light).
- Reduce PPV exposure bias from 10.5 to 7.5 (appropriate for indoor dim studio).
- SkyLight already at 1.0 (fine for gentle ambient fill).

Target result: silver-grey character, properly exposed, against medium-grey backdrop.

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_tune_exposure_result.json")
out = {"ok": False, "log": []}

def log(msg):
    out["log"].append(msg)

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
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

        # Reduce DirectionalLight to soft key
        if isinstance(a, unreal.DirectionalLight):
            try:
                a.light_component.set_intensity(8.0)
                log(f"DirectionalLight '{lbl}' intensity -> 8.0 Lux")
            except Exception as e:
                log(f"DirectionalLight error: {e}")
            continue

        # Reduce PPV exposure bias to moderate indoor level
        if isinstance(a, unreal.PostProcessVolume) and lbl == "ExposureLock":
            try:
                s = a.get_editor_property("settings")
                s.set_editor_property("auto_exposure_bias", 7.5)
                a.set_editor_property("settings", s)
                log("PPV ExposureLock exposure_bias -> 7.5")
            except Exception as e:
                log(f"PPV error: {e}")
            continue

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_TUNE_EXP_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_TUNE_EXP_DONE ok={out['ok']}")
