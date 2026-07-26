"""Boost clean stage lights so the character's mean luminance clears the 0.18 too_dark floor.

Current: DirectionalLight=12 Lux, SkyLight=15.0, PPV ExposureBias=7.5
  → subject mean_luminance=0.1741 (just under 0.18 floor)

Fix: DirectionalLight→18 Lux, SkyLight→22.0 (proportional +50% on ambient fill),
     PPV ExposureBias→8.5 (+1 stop from 7.5).
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_boost_result.json")
out = {"ok": False, "log": []}

def log(msg):
    print(f"  [boost] {msg}")
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

        if isinstance(a, unreal.DirectionalLight):
            try:
                a.light_component.set_intensity(18.0)
                log(f"DirectionalLight '{lbl}' intensity -> 18.0 Lux")
            except Exception as e:
                log(f"DirectionalLight error: {e}")

        if isinstance(a, unreal.SkyLight):
            try:
                a.light_component.set_intensity(22.0)
                log(f"SkyLight '{lbl}' intensity -> 22.0 (ambient fill)")
            except Exception as e:
                log(f"SkyLight error: {e}")

        if isinstance(a, unreal.PostProcessVolume):
            try:
                s = a.settings
                s.set_editor_property("auto_exposure_bias", 8.5)
                s.set_editor_property("override_auto_exposure_bias", True)
                a.set_editor_property("settings", s)
                log(f"PPV '{lbl}' ExposureBias -> 8.5")
            except Exception as e:
                log(f"PPV error: {e}")

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_BOOST_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_BOOST_DONE ok={out['ok']}")
