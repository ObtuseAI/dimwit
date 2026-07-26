"""Check what material SM_Char_02_ekris_Rig actually has in its material slots."""
import unreal, json
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_mat_check.json")
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig"

mesh = unreal.load_asset(RIG)
out = {"rig_type": type(mesh).__name__}
if isinstance(mesh, unreal.SkeletalMesh):
    mats = mesh.materials
    out["slot_count"] = len(mats)
    out["slots"] = []
    for i, sm in enumerate(mats):
        mi = sm.get_editor_property("material_interface") if sm else None
        out["slots"].append({
            "index": i,
            "material": mi.get_path_name() if mi else None,
            "material_type": type(mi).__name__ if mi else None,
        })
else:
    out["error"] = "not a SkeletalMesh"

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("RM_RIG_MAT_CHECK_DONE " + str(OUT))
