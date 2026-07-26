"""Verify the rigged Ekris is bound to the SK_Mannequin skeleton so ABP_Manny will actually drive it
(otherwise the hold char stays frozen in ref pose). Writes artifacts/inspect_rig.json."""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/inspect_rig.json")
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig"
ABP = "/Game/Mannequins/Animations/ABP_Manny"
MANN_SKEL = "/Game/Mannequins/Meshes/SK_Mannequin"
out = {}
try:
    sk = unreal.load_asset(RIG)
    out["rig_class"] = type(sk).__name__
    rig_skel = None
    if isinstance(sk, unreal.SkeletalMesh):
        s = sk.get_editor_property("skeleton")
        rig_skel = s.get_path_name() if s else None
        out["rig_skeleton"] = rig_skel
        out["rig_num_materials"] = len(sk.materials)
        out["rig_bounds_z_cm"] = round(sk.get_bounds().box_extent.z * 2.0, 1)
    mann = unreal.load_asset(MANN_SKEL)
    out["mann_skeleton_path"] = mann.get_path_name() if mann else None
    abp = unreal.load_asset(ABP)
    out["abp_class"] = type(abp).__name__
    try:
        abp_skel = abp.get_editor_property("target_skeleton")
        out["abp_target_skeleton"] = abp_skel.get_path_name() if abp_skel else None
    except Exception as e:
        out["abp_target_skeleton_err"] = str(e)
    # match check: rig skeleton path (strip object suffix) vs SK_Mannequin
    norm = lambda p: (p or "").split(".")[0]
    out["rig_uses_mannequin_skeleton"] = norm(rig_skel) == norm(MANN_SKEL)
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_INSPECT_RIG_DONE match=" + str(out.get("rig_uses_mannequin_skeleton")))
