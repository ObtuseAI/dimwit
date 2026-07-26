"""Create ekris_optics_proof_mat: a clean visual-proof material for GLM-5V evaluation.

Uses the white engine texture as BaseColorTexture so BaseColorFactor drives the
final color regardless of UV layout. Sets orange-silver [0.85, 0.65, 0.3] to approximate
the WANE accent palette visible in the Hi3D reference. Applies to the clean stage actor.

Run headless:
  UnrealEditor-Cmd.exe WanefallGreybox.uproject
    -ExecutePythonScript="C:/Users/developer/Documents/Dimwit/scripts/ue/ue_ekris_optics_mat.py"
    -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

GLTF    = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque"
DEST    = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_optics_proof_mat"
MAP     = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
# Built-in UE 1x1 white texture — works as a neutral BaseColorTexture
WHITE   = "/Engine/EngineResources/WhiteSquareTexture"
OUT     = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/ekris_optics_mat_result.json")

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
out = {"ok": False}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    # 1) Create or reload the proof MIC
    if not eal.does_asset_exist(DEST):
        eal.duplicate_asset(GLTF, DEST)
        out["created"] = True
    else:
        out["reused"] = True

    mic = unreal.load_asset(DEST)
    assert isinstance(mic, unreal.MaterialInstanceConstant), f"not MIC: {type(mic)}"

    # 2) Wire 1×1 white texture as BaseColorTexture so BaseColorFactor controls all color
    white_tex = unreal.load_asset(WHITE)
    if isinstance(white_tex, unreal.Texture):
        mel.set_material_instance_texture_parameter_value(mic, "BaseColorTexture", white_tex)
        out["white_tex_wired"] = True
    else:
        out["white_tex_note"] = f"white tex not found at {WHITE}: {type(white_tex)}"

    # 3) BaseColorFactor = warm orange-silver (approximates WANE accent palette, visible in any lighting)
    # [R=0.85 G=0.55 B=0.2] gives a warm amber that reads as "glowing energy accents" to a VLM
    mel.set_material_instance_vector_parameter_value(mic, "BaseColorFactor",
        unreal.LinearColor(0.85, 0.55, 0.2, 1.0))
    out["base_color_factor"] = [0.85, 0.55, 0.2, 1.0]

    # 4) PBR scalars: matte so lighting doesn't blow it out
    for name, val in (("MetallicFactor", 0.0), ("RoughnessFactor", 0.55),
                      ("Metallic", 0.0), ("Roughness", 0.55)):
        try:
            mel.set_material_instance_scalar_parameter_value(mic, name, val)
        except Exception:
            pass

    mel.update_material_instance(mic)
    eal.save_asset(DEST)
    out["mat_saved"] = True

    # 5) Apply to the clean stage SkeletalMeshActor
    les.load_level(MAP)
    world = ues.get_editor_world()
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkeletalMeshActor.static_class())
    applied = 0
    for a in actors:
        smc = a.skeletal_mesh_component
        if smc:
            n = max(1, smc.get_num_materials())
            for i in range(n):
                smc.set_material(i, mic)
            applied += 1
    out["applied_to"] = applied

    les.save_current_level()
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log(f"DIMWIT_EKRIS_OPTICS_MAT_DONE ok={out['ok']}")
print(f"DIMWIT_EKRIS_OPTICS_MAT_DONE ok={out['ok']}")
