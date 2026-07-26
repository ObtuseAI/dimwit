"""ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1 - cleanup: remove experiment displays + variant assets.

Run after the winning variant's params are applied to the production M_ZythanRigShip
(scripts/ue/ue_zythan_rig_base_material_build.py). Experiment content must never ship in a package:
removes every RigMatExperiment_* actor from the ModeShell map, saves the level, then deletes
the M_ZythanRigShip_EXP_* material assets.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_zythan_mat_experiment_cleanup.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/zythan_mat_experiment/cleanup_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
DEST_DIR = "/Game/Wanefall/Dimwit/CharactersRigged"
VARIANT_NAMES = ["E0_CTRL", "E1_EM0", "E2_EMALB", "E3_SHEEN"]
result = {"ok": False, "removed_actors": [], "deleted_assets": []}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    eal = unreal.EditorAssetLibrary
    les.load_level(MAP)
    for a in list(eas.get_all_level_actors()):
        if a.get_actor_label().startswith("RigMatExperiment_"):
            label = a.get_actor_label()
            eas.destroy_actor(a)
            result["removed_actors"].append(label)
    saved = les.save_current_level()
    result["map_saved"] = bool(saved)
    # delete variant assets only AFTER the level no longer references them
    for name in VARIANT_NAMES:
        path = f"{DEST_DIR}/M_ZythanRigShip_EXP_{name}"
        if eal.does_asset_exist(path):
            if eal.delete_asset(path):
                result["deleted_assets"].append(path)
            else:
                result.setdefault("delete_failures", []).append(path)
    result["ok"] = bool(saved) and not result.get("delete_failures")
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("MAT_EXPERIMENT_CLEANUP:", json.dumps(result)[:400])
