"""Fix ekris_backdrop_grey_mat: set BaseColorTexture=WhiteSquare so BaseColorFactor [0.30]
actually produces grey, not black (same UV issue as the character material).
Also increase DirectionalLight to 12 Lux (8 was slightly dim for a nice silver highlight).

Run headless via UnrealEditor-Cmd.exe -ExecutePythonScript=...
"""
import unreal, json, traceback
from pathlib import Path

MAP   = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
GREY  = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_backdrop_grey_mat"
WHITE = "/Engine/EngineResources/WhiteSquareTexture"
OUT   = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_fix_backdrop_mat_result.json")
out   = {"ok": False, "log": []}

def log(msg):
    out["log"].append(msg)

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    les.load_level(MAP)
    log("map loaded")

    # Fix the backdrop material ------------------------------------------------
    grey_mic = unreal.load_asset(GREY)
    assert isinstance(grey_mic, unreal.MaterialInstanceConstant), f"not MIC: {type(grey_mic)}"

    # Wire 1×1 white texture so BaseColorFactor drives final color (no UV dependency)
    white_tex = unreal.load_asset(WHITE)
    if isinstance(white_tex, unreal.Texture):
        mel.set_material_instance_texture_parameter_value(grey_mic, "BaseColorTexture", white_tex)
        log("BaseColorTexture -> WhiteSquare")
    else:
        log(f"WARNING: WhiteSquare not found: {type(white_tex)}")

    # Medium grey backdrop (not too bright to avoid white_debug, not too dark)
    mel.set_material_instance_vector_parameter_value(
        grey_mic, "BaseColorFactor", unreal.LinearColor(0.28, 0.28, 0.32, 1.0))
    mel.set_material_instance_scalar_parameter_value(grey_mic, "MetallicFactor",  0.0)
    mel.set_material_instance_scalar_parameter_value(grey_mic, "RoughnessFactor", 0.9)
    mel.update_material_instance(grey_mic)
    eal.save_asset(GREY)
    log("backdrop material: BaseColorFactor=[0.28,0.28,0.32] + WhiteSquare")

    # Re-apply to the GrayBackdrop actor in the level --------------------------
    world = ues.get_editor_world()
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.Actor.static_class()))
    for a in actors:
        try:
            lbl = a.get_actor_label()
        except Exception:
            lbl = "?"

        if lbl == "GrayBackdrop" and isinstance(a, unreal.StaticMeshActor):
            smc = a.static_mesh_component
            if smc:
                smc.set_material(0, grey_mic)
                log("re-applied grey mat to GrayBackdrop")
            continue

        # Also bump DirectionalLight to 12 Lux (slightly brighter key for silver highlight)
        if isinstance(a, unreal.DirectionalLight):
            try:
                a.light_component.set_intensity(12.0)
                log(f"DirectionalLight '{lbl}' intensity -> 12.0")
            except Exception as e:
                log(f"DirectionalLight error: {e}")
            continue

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_FIX_BACKDROP_MAT_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_FIX_BACKDROP_MAT_DONE ok={out['ok']}")
