"""Fix clean stage lighting v2 — corrected UE Python attribute names.

Changes:
- Remove CharFillLight PointLight (the 80,000 lm blowout)
- Rotate DirectionalLight Sun to Pitch=-30 Yaw=180 (front-top illumination)
- SkyLight intensity -> 2.0 (gentle ambient only)
- PPV exposure bias -> 6.0 (indoor-range, avoids blowout)

Run headless via UnrealEditor-Cmd.exe with -ExecutePythonScript
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_fix_lighting2_result.json")
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
            lbl = ""

        # 1) Remove the blown-out fill light
        if lbl == "CharFillLight" and isinstance(a, unreal.PointLight):
            eas.destroy_actor(a)
            log("removed CharFillLight")
            continue

        # 2) Fix DirectionalLight rotation to front-light the character
        #    Character faces +X (toward camera). Yaw=180 shines from +X toward -X → hits front.
        #    Pitch=-30 adds downward angle for portrait top-front lighting.
        if isinstance(a, unreal.DirectionalLight):
            try:
                a.set_actor_rotation(unreal.Rotator(-30.0, 180.0, 0.0), False)
                log(f"DirectionalLight '{lbl}' rotated Pitch=-30 Yaw=180")
                # Try to boost intensity via light_component (correct UE Python attr)
                try:
                    a.light_component.set_intensity(12.0)
                    log("  intensity -> 12.0 via light_component")
                except AttributeError:
                    log("  light_component not accessible (ok — rotation done)")
            except Exception as e:
                log(f"DirectionalLight '{lbl}' error: {e}")
            continue

        # 3) Dial SkyLight back to gentle ambient
        if isinstance(a, unreal.SkyLight):
            try:
                a.sky_light_component.set_intensity(2.0)
                log(f"SkyLight '{lbl}' intensity -> 2.0")
            except Exception as e:
                log(f"SkyLight '{lbl}' error: {e}")
            continue

        # 4) Fix PostProcessVolume exposure
        if isinstance(a, unreal.PostProcessVolume) and lbl == "ExposureLock":
            try:
                s = a.get_editor_property("settings")
                s.set_editor_property("auto_exposure_bias", 6.0)
                a.set_editor_property("settings", s)
                log("PPV ExposureLock exposure_bias -> 6.0")
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
print(f"DIMWIT_FIX2_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_FIX2_DONE ok={out['ok']}")
