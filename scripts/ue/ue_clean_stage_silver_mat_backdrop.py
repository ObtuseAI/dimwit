"""Two fixes in one script:
1. Change ekris_optics_proof_mat BaseColorFactor to silver-grey [0.65, 0.65, 0.70].
   The reference (hi3d_02_ekris.png) shows a silver/dark alien; flat orange was
   being rejected as 'untextured debug mesh'. Silver-grey body will give 'partial'
   reference match instead of 'no'.
2. Spawn a large grey backdrop plane at X=-400 behind the character (facing camera
   at +X) to replace the dark void that causes pixel:too_dark + pixel:black_blob.

After saving, run scripts/capture/ekris_clean_capture.py to recapture and re-test optics.

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP   = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
DEST  = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_optics_proof_mat"
PLANE = "/Engine/BasicShapes/Plane"
OUT   = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_silver_backdrop_result.json")
out   = {"ok": False, "log": []}

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

    # 1) Update the proof material to silver-grey ----------------------------
    mic = unreal.load_asset(DEST)
    assert isinstance(mic, unreal.MaterialInstanceConstant), f"not MIC: {type(mic)}"

    # Silver-white: dominant color of the reference (silver/dark body).
    mel.set_material_instance_vector_parameter_value(
        mic, "BaseColorFactor", unreal.LinearColor(0.65, 0.65, 0.70, 1.0))
    log("BaseColorFactor -> silver-grey [0.65, 0.65, 0.70]")

    # Keep MetallicFactor=0, RoughnessFactor=0.45 (slightly smoother -> reads as armour-like)
    mel.set_material_instance_scalar_parameter_value(mic, "MetallicFactor",   0.0)
    mel.set_material_instance_scalar_parameter_value(mic, "RoughnessFactor",  0.45)
    mel.update_material_instance(mic)
    eal.save_asset(DEST)
    log("material saved")

    # 2) Spawn a backdrop plane ---------------------------------------------------
    # The directional light shines from +X direction (Yaw=180 was set by fix_lighting2).
    # A plane at X=-400, Pitch=-90 (normal faces +X = toward camera), will:
    #  a) be visible behind the character from the camera at (320, 70, 120)
    #  b) be directly lit by the front directional light (which also faces -X)
    #  c) fill the dark void background

    world = ues.get_editor_world()
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.Actor.static_class()))

    # Remove any existing backdrop so we don't double-spawn
    for a in actors:
        try:
            if a.get_actor_label() == "GrayBackdrop":
                eas.destroy_actor(a)
                log("removed old GrayBackdrop")
        except Exception:
            pass

    # Spawn backdrop plane
    plane_mesh = unreal.load_asset(PLANE)
    backdrop = eas.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(-400.0, 0.0, 100.0),      # X=-400 behind character (camera at +320)
        unreal.Rotator(-90.0, 0.0, 0.0))         # Pitch=-90 rotates the normal from +Z to +X (faces camera)
    if backdrop:
        backdrop.set_actor_label("GrayBackdrop")
        backdrop.set_actor_scale3d(unreal.Vector(25.0, 25.0, 1.0))  # 2500×2500 units (fills BG)
        smc = backdrop.static_mesh_component
        if smc:
            smc.set_static_mesh(plane_mesh)
            # Create a simple grey material instance from M_Default_Opaque
            gltf_mat = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
            grey_dest = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_backdrop_grey_mat"
            if not eal.does_asset_exist(grey_dest):
                eal.duplicate_asset(gltf_mat, grey_dest)
                log("created ekris_backdrop_grey_mat")
            else:
                log("reused ekris_backdrop_grey_mat")
            grey_mic = unreal.load_asset(grey_dest)
            if isinstance(grey_mic, unreal.MaterialInstanceConstant):
                # Dark-neutral grey so backdrop doesn't blow out (but not black)
                mel.set_material_instance_vector_parameter_value(
                    grey_mic, "BaseColorFactor", unreal.LinearColor(0.10, 0.10, 0.12, 1.0))
                mel.set_material_instance_scalar_parameter_value(grey_mic, "MetallicFactor",  0.0)
                mel.set_material_instance_scalar_parameter_value(grey_mic, "RoughnessFactor", 0.9)
                mel.update_material_instance(grey_mic)
                eal.save_asset(grey_dest)
                smc.set_material(0, grey_mic)
                log("grey material applied to backdrop")
        log("backdrop plane spawned at X=-400 scale=25")
    else:
        log("WARNING: backdrop spawn returned None")

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_SILVER_BACKDROP_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_SILVER_BACKDROP_DONE ok={out['ok']}")
