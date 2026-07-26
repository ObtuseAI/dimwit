"""Fix the clean stage lighting so the Ekris character is properly front-lit:
1. Remove the blown-out CharFillLight (80,000 lm was too much)
2. Rotate the DirectionalLight to Pitch=-30, Yaw=180 (front-top illumination)
3. SkyLight back to 2.0 (gentle ambient fill)
4. PPV exposure bias reduced to 6.0 (avoids floor/sky blowout)

Run headless:
  UnrealEditor-Cmd.exe WanefallGreybox.uproject
    -ExecutePythonScript="C:/Users/developer/Documents/Dimwit/scripts/ue/ue_clean_stage_fix_lighting.py"
    -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_fix_lighting_result.json")
out = {"ok": False, "steps": {}}


def step(name, fn):
    try:
        v = fn()
        out["steps"][name] = {"ok": True, "info": str(v)[:200] if v is not None else "ok"}
        return v
    except Exception as e:
        out["steps"][name] = {"ok": False, "error": repr(e)}
        return None


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    step("load_map", lambda: les.load_level(MAP))

    def fix_lights():
        world = ues.get_editor_world()
        actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor.static_class())
        removed = []
        dir_fixed = []
        sky_fixed = []
        ppv_fixed = []

        for a in actors:
            lbl = a.get_actor_label() if hasattr(a, 'get_actor_label') else ""

            # Remove the blown-out fill light
            if lbl == "CharFillLight" and isinstance(a, unreal.PointLight):
                eas.destroy_actor(a)
                removed.append("CharFillLight")
                continue

            # Fix DirectionalLight "Sun" — rotate to front-light the character
            if lbl == "Sun" and isinstance(a, unreal.DirectionalLight):
                # Character faces +X (toward camera). Directional light at Yaw=180 shines from +X toward origin.
                # Pitch=-30 adds a downward angle for top-front portrait lighting.
                a.set_actor_rotation(unreal.Rotator(-30.0, 180.0, 0.0), False)
                a.directional_light_component.set_intensity(10.0)  # slightly brighter for the tighter angle
                dir_fixed.append("Sun rotated to Pitch=-30 Yaw=180")
                continue

            # Dial SkyLight back to gentle ambient
            if isinstance(a, unreal.SkyLight):
                try:
                    a.sky_light_component.set_intensity(2.0)
                    sky_fixed.append(a.get_name())
                except Exception:
                    pass
                continue

            # Fix PostProcessVolume exposure — reduce to moderate value to avoid blowout
            if isinstance(a, unreal.PostProcessVolume) and lbl == "ExposureLock":
                try:
                    s = a.get_editor_property("settings")
                    s.set_editor_property("auto_exposure_bias", 7.5)
                    a.set_editor_property("settings", s)
                    ppv_fixed.append("exposure bias -> 7.5")
                except Exception as e:
                    ppv_fixed.append(f"failed: {e}")
                continue

        return {"removed": removed, "dir_fixed": dir_fixed, "sky_fixed": sky_fixed, "ppv_fixed": ppv_fixed}

    step("fix_lights", fix_lights)
    step("save", lambda: les.save_current_level())
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log(f"DIMWIT_FIX_LIGHTING_DONE ok={out['ok']}")
print(f"DIMWIT_FIX_LIGHTING_DONE ok={out['ok']}")
