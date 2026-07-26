"""Fix PPV exposure bias back to 10.5 (was correct for the dim directional light level;
reduced too aggressively in prior script after the fill light was removed).
Also bumps the DirectionalLight intensity to 25 Lux to give more front key light.
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_fix_exposure_result.json")
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
            lbl = ""

        # Restore PPV exposure bias to a value that properly exposes the dim directional light
        if isinstance(a, unreal.PostProcessVolume) and lbl == "ExposureLock":
            try:
                s = a.get_editor_property("settings")
                s.set_editor_property("auto_exposure_bias", 10.5)
                a.set_editor_property("settings", s)
                log("PPV ExposureLock exposure_bias -> 10.5")
            except Exception as e:
                log(f"PPV error: {e}")
            continue

        # Boost the front-facing DirectionalLight to give the character key light
        if isinstance(a, unreal.DirectionalLight):
            try:
                a.light_component.set_intensity(25.0)
                log(f"DirectionalLight '{lbl}' intensity -> 25.0")
            except Exception as e:
                log(f"DirectionalLight '{lbl}' intensity error: {e}")
            continue

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_FIX_EXPOSURE_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_FIX_EXPOSURE_DONE ok={out['ok']}")
