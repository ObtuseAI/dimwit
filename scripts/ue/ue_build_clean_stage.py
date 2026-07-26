"""Dimwit CLEAN-ROOM STAGE builder (UE headless) — prove the renderer works with KNOWN-GOOD engine/Mannequin
assets only, bypassing the project's damaged ThirdPerson BP / missing /Game/Input IMC assets.

Builds /Game/Wanefall/Maps/Wanefall_CleanStage_01:
  - Floor: /Engine/BasicShapes/Plane scaled flat (neutral world-grid look = toned-down realism)
  - DirectionalLight + SkyLight + SkyAtmosphere (clean daylight, NOT photoreal cave)
  - Manny: SkeletalMeshActor SKM_Manny + ABP_Manny anim instance (idle animation)
  - CameraActor framing Manny, Auto Activate For Player 0 (deterministic shot, no input needed)
  - PlayerStart co-located with the camera so the GameModeBase DefaultPawn sphere hides behind the view
  - Unbound PostProcessVolume with MANUAL exposure (locks brightness — no white blow-out)
  - World GameMode override = GameModeBase (clean; never the damaged project gamemode)

Each cosmetic step is wrapped so the CORE (floor+Manny+camera) always lands. Writes artifacts/clean_stage.json.

  UnrealEditor-Cmd <uproj> -ExecutePythonScript="scripts/ue/ue_build_clean_stage.py" -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage.json")
out = {"ok": False, "map": MAP, "steps": {}, "actors": []}


def step(name, fn):
    try:
        v = fn()
        out["steps"][name] = {"ok": True, "info": str(v)[:120] if v is not None else "ok"}
        return v
    except Exception as e:
        out["steps"][name] = {"ok": False, "error": repr(e)}
        return None


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    def load(p):
        return unreal.load_asset(p)

    def spawn(cls, loc=(0, 0, 0), rot=(0, 0, 0), label=None):
        a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(*rot))
        if a and label:
            try:
                a.set_actor_label(label)
            except Exception:
                pass
        if a:
            out["actors"].append(label or a.get_name())
        return a

    # 0) brand-new empty level
    step("new_level", lambda: les.new_level(MAP))

    # 1) floor
    def mk_floor():
        plane = load("/Engine/BasicShapes/Plane")
        f = spawn(unreal.StaticMeshActor, (0, 0, 0), label="Floor")
        f.static_mesh_component.set_static_mesh(plane)
        f.set_actor_scale3d(unreal.Vector(40.0, 40.0, 1.0))
        return "floor 40x40"
    step("floor", mk_floor)

    # 2) sun (directional light)
    def mk_sun():
        s = spawn(unreal.DirectionalLight, (0, 0, 600), (0.0, -48.0, 35.0), label="Sun")
        try:
            s.directional_light_component.set_intensity(6.0)
        except Exception:
            pass
        return "sun"
    step("sun", mk_sun)

    # 3) sky atmosphere + sky light (clean daylight)
    step("sky_atmosphere", lambda: spawn(unreal.SkyAtmosphere, (0, 0, 0), label="SkyAtmosphere"))
    def mk_skylight():
        sl = spawn(unreal.SkyLight, (0, 0, 400), label="SkyLight")
        try:
            sl.sky_light_component.set_editor_property("real_time_capture", True)
            sl.sky_light_component.set_intensity(1.0)
        except Exception:
            pass
        return "skylight"
    step("skylight", mk_skylight)

    # 4) Manny — placed skeletal mesh actor with the stock anim BP (animates, no input/gamemode needed)
    def mk_manny():
        mesh = load("/Game/Mannequins/Meshes/SKM_Manny")
        ch = spawn(unreal.SkeletalMeshActor, (0, 0, 0), (0.0, 0.0, -90.0), label="Manny")
        smc = ch.skeletal_mesh_component
        smc.set_skeletal_mesh_asset(mesh)
        abp = unreal.load_class(None, "/Game/Mannequins/Animations/ABP_Manny.ABP_Manny_C")
        if abp:
            smc.set_anim_instance_class(abp)
        try:
            smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        except Exception:
            pass
        return f"manny mesh={'ok' if mesh else 'MISSING'} abp={'ok' if abp else 'MISSING'}"
    step("manny", mk_manny)

    # 5) framing camera (auto-activate for player 0) + co-located PlayerStart to hide the DefaultPawn
    def mk_camera():
        cam = spawn(unreal.CameraActor, (320.0, 70.0, 120.0), (0.0, -7.0, -168.0), label="ShotCam")
        cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
        try:
            cam.camera_component.set_editor_property("field_of_view", 50.0)
        except Exception:
            pass
        spawn(unreal.PlayerStart, (320.0, 70.0, 120.0), (0.0, 0.0, -168.0), label="PlayerStart")
        return "camera+playerstart"
    step("camera", mk_camera)

    # 6) lock exposure (no white blow-out) via unbound PostProcessVolume
    def mk_ppv():
        ppv = spawn(unreal.PostProcessVolume, (0, 0, 200), label="ExposureLock")
        ppv.set_editor_property("unbound", True)
        s = ppv.get_editor_property("settings")
        s.set_editor_property("override_auto_exposure_method", True)
        s.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
        s.set_editor_property("override_auto_exposure_bias", True)
        s.set_editor_property("auto_exposure_bias", 11.0)
        ppv.set_editor_property("settings", s)
        return "manual exposure locked"
    step("ppv", mk_ppv)

    # 7) clean gamemode override so the damaged project gamemode never runs
    def mk_gm():
        world = ues.get_editor_world()
        ws = world.get_world_settings()
        ws.set_editor_property("default_game_mode", unreal.GameModeBase)
        return "GameModeBase"
    step("gamemode", mk_gm)

    # 8) save
    step("save", lambda: les.save_current_level())
    out["ok"] = True
except Exception:
    out["error"] = traceback.format_exc()

RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_CLEAN_STAGE_DONE ok=" + str(out.get("ok")) + " actors=" + str(out.get("actors")))
print("DIMWIT_CLEAN_STAGE_DONE ok=" + str(out.get("ok")))
