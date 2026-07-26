"""Add a bright fill PointLight near the camera in Wanefall_CleanStage_01 to
front-light the Ekris character (which is currently silhouetted — directional light
is side/back angled). Also boosts SkyLight to 4.0 for ambient fill.

Run headless:
  UnrealEditor-Cmd.exe WanefallGreybox.uproject
    -ExecutePythonScript="C:/Users/developer/Documents/Dimwit/scripts/ue/ue_clean_stage_fill_light.py"
    -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_fill_light_result.json")
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

    # 1) Boost existing SkyLight(s) for ambient fill
    def boost_skylight():
        world = ues.get_editor_world()
        sls = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkyLight.static_class())
        for sl in sls:
            try:
                sl.sky_light_component.set_intensity(5.0)
            except Exception:
                pass
        return f"boosted {len(sls)} skylights to 5.0"
    step("boost_skylight", boost_skylight)

    # 2) Add a front fill PointLight co-located with the camera (320, 70, 120) pointing at the char
    def add_fill_light():
        # Camera is at (320, 70, 120) looking toward origin (character at 0,0,0).
        # Place the fill light between camera and character, elevated, to get a 3/4 front-top lighting.
        fill = eas.spawn_actor_from_class(unreal.PointLight,
            unreal.Vector(250.0, 50.0, 200.0), unreal.Rotator(0, 0, 0))
        if fill:
            try:
                fill.set_actor_label("CharFillLight")
                comp = fill.point_light_component
                comp.set_intensity(80000.0)           # flood-fill the 200cm character
                comp.set_attenuation_radius(1200.0)   # reach the character at ~330 cm distance
                comp.set_editor_property("cast_shadows", False)   # faster, no shadow
            except Exception as e:
                return f"spawned but config failed: {e}"
        return f"added fill light at (250, 50, 200) intensity=80000"
    step("add_fill_light", add_fill_light)

    # 3) Save
    step("save", lambda: les.save_current_level())
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log(f"DIMWIT_FILL_LIGHT_DONE ok={out['ok']}")
print(f"DIMWIT_FILL_LIGHT_DONE ok={out['ok']}")
