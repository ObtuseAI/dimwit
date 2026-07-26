"""Swap the SKM_Manny SkeletalMeshActor in Wanefall_CleanStage_01 for the Ekris rig + ekris_mat,
and export the Ekris albedo texture to PNG for visual inspection.

Run headless:
  UnrealEditor-Cmd.exe WanefallGreybox.uproject
    -ExecutePythonScript="C:/Users/developer/Documents/Dimwit/scripts/ue/ue_ekris_clean_stage.py"
    -unattended -nosplash -nopause -stdout
"""
import unreal, json, traceback
from pathlib import Path

MAP     = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
RIG     = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig"
MAT     = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_mat"
ALB     = "/Game/Wanefall/Dimwit/CharactersRigged/Textures/SM_Char_02_ekris_Rig_albedo"
ABP_PATH = "/Game/Mannequins/Animations/ABP_Manny"
OUT_ALB = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/ekris_albedo_export.png")
OUT_RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/ekris_clean_stage_result.json")

out = {"ok": False, "steps": {}}

def step(name, fn):
    try:
        v = fn()
        out["steps"][name] = {"ok": True, "info": str(v)[:200] if v is not None else "ok"}
        return v
    except Exception as e:
        out["steps"][name] = {"ok": False, "error": repr(e)}
        unreal.log_warning(f"[ekris_stage] STEP FAILED {name}: {e}")
        return None

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    eal = unreal.EditorAssetLibrary

    # 1) Load the clean stage
    def load_map():
        result = les.load_level(MAP)
        return f"loaded={result}"
    step("load_map", load_map)

    # 2) Export the Ekris albedo texture to PNG for inspection
    def export_albedo():
        tex = unreal.load_asset(ALB)
        if not isinstance(tex, unreal.Texture2D):
            return f"NOT FOUND or not Texture2D: {type(tex)}"
        OUT_ALB.parent.mkdir(parents=True, exist_ok=True)
        task = unreal.AssetExportTask()
        task.set_editor_property("object", tex)
        task.set_editor_property("filename", str(OUT_ALB))
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_identical", True)
        unreal.Exporter.run_asset_export_task(task)
        exists = OUT_ALB.exists()
        return f"exported={exists} size={OUT_ALB.stat().st_size if exists else 0}"
    step("export_albedo", export_albedo)

    # 3) Find the SkeletalMeshActor in the clean stage (currently SKM_Manny)
    def swap_mesh():
        world = ues.get_editor_world()
        actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkeletalMeshActor.static_class())
        ekris_mesh = unreal.load_asset(RIG)
        ekris_mat  = unreal.load_asset(MAT)
        abp_class  = unreal.load_class(None, ABP_PATH + "." + ABP_PATH.split("/")[-1] + "_C")

        swapped = 0
        for a in actors:
            smc = a.skeletal_mesh_component
            if not smc:
                continue
            if isinstance(ekris_mesh, unreal.SkeletalMesh):
                smc.set_skeletal_mesh_asset(ekris_mesh)
            if abp_class:
                smc.set_anim_instance_class(abp_class)
            if isinstance(ekris_mat, unreal.MaterialInstanceConstant):
                n = smc.get_num_materials()
                for i in range(max(1, n)):
                    smc.set_material(i, ekris_mat)
            a.set_actor_label("Ekris")
            swapped += 1

        return f"swapped {swapped} SkeletalMeshActors to Ekris rig + ekris_mat"
    step("swap_mesh", swap_mesh)

    # 4) Save the level
    step("save_level", lambda: les.save_current_level())

    out["ok"] = out["steps"].get("swap_mesh", {}).get("ok", False)

except Exception:
    out["error"] = traceback.format_exc()

OUT_RES.parent.mkdir(parents=True, exist_ok=True)
OUT_RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log(f"DIMWIT_EKRIS_CLEAN_STAGE_DONE ok={out['ok']}")
print(f"DIMWIT_EKRIS_CLEAN_STAGE_DONE ok={out['ok']}")
