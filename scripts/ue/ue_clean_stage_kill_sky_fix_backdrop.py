"""Fix clean stage so silver material renders neutral (not orange):
1. Hide SkyAtmosphere — removes the warm orange atmospheric tint that was making
   everything appear orange regardless of BaseColorFactor.
2. Fix GrayBackdrop plane rotation from Pitch=-90 to Pitch=+90 so it faces the
   camera (Pitch=-90 was pointing the wrong way — invisible back face).
3. Brighten the backdrop material to medium grey.
4. Also verify ekris_optics_proof_mat has silver BaseColorFactor saved.

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP  = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
DEST = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_optics_proof_mat"
GREY = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_backdrop_grey_mat"
OUT  = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_kill_sky_result.json")
out  = {"ok": False, "log": []}

def log(msg):
    out["log"].append(msg)

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

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

        # 1) Hide SkyAtmosphere — removes the warm orange sky tint
        if isinstance(a, unreal.SkyAtmosphere):
            try:
                a.set_actor_hidden_in_game(True)
                eas.set_actor_selection_state(a, True)
                # Also try editor visibility
                a.set_is_temporarily_hidden_in_editor(True)
                log(f"SkyAtmosphere '{lbl}' hidden")
            except Exception as e:
                log(f"SkyAtmosphere hide error: {e}")
            continue

        # 2) Fix GrayBackdrop: wrong rotation (Pitch=-90 → back-face). Must be Pitch=+90.
        if lbl == "GrayBackdrop":
            try:
                # Pitch=+90 rotates the Plane's +Z normal to +X (faces camera at X=+320)
                a.set_actor_rotation(unreal.Rotator(90.0, 0.0, 0.0), False)
                a.set_actor_scale3d(unreal.Vector(25.0, 25.0, 1.0))  # keep 2500x2500
                log("GrayBackdrop rotation fixed to Pitch=+90 (faces camera)")
                # Update material to medium grey
                smc = a.static_mesh_component
                if smc:
                    grey_mic = unreal.load_asset(GREY)
                    if isinstance(grey_mic, unreal.MaterialInstanceConstant):
                        mel.set_material_instance_vector_parameter_value(
                            grey_mic, "BaseColorFactor", unreal.LinearColor(0.30, 0.30, 0.35, 1.0))
                        mel.set_material_instance_scalar_parameter_value(grey_mic, "MetallicFactor",  0.0)
                        mel.set_material_instance_scalar_parameter_value(grey_mic, "RoughnessFactor", 0.9)
                        mel.update_material_instance(grey_mic)
                        eal.save_asset(GREY)
                        smc.set_material(0, grey_mic)
                        log("backdrop material -> medium grey [0.30, 0.30, 0.35]")
            except Exception as e:
                log(f"GrayBackdrop fix error: {e}")
            continue

    # 3) Confirm proof material is still silver
    try:
        mic = unreal.load_asset(DEST)
        if isinstance(mic, unreal.MaterialInstanceConstant):
            params = mel.get_vector_parameter_values(mic)
            found = [(p.parameter_info.name, [p.parameter_value.r, p.parameter_value.g,
                                              p.parameter_value.b]) for p in params
                     if "BaseColor" in str(p.parameter_info.name)]
            log(f"ekris_optics_proof_mat BaseColor params: {found}")
            # If not silver, re-apply
            if not found or abs(found[0][1][0] - 0.65) > 0.05:
                mel.set_material_instance_vector_parameter_value(
                    mic, "BaseColorFactor", unreal.LinearColor(0.65, 0.65, 0.70, 1.0))
                mel.update_material_instance(mic)
                eal.save_asset(DEST)
                log("re-applied silver BaseColorFactor [0.65, 0.65, 0.70]")
    except Exception as e:
        log(f"material verify error: {e}")

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_KILL_SKY_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_KILL_SKY_DONE ok={out['ok']}")
