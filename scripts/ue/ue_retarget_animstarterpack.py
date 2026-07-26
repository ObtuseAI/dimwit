"""Dimwit ANIMATION backend (animstarterpack_retarget): IK-retarget the in-project AnimStarterPack (UE4 mocap)
onto SK_Mannequin so the rigged aliens play REAL locomotion. Best-effort headless: uses an existing UE4->UE5 IK
Retargeter if one is present; otherwise records an honest blocker (the IK Retargeter asset is a one-time in-editor
setup, after which this script batch-runs). Writes artifacts/retarget_result.json. NEVER fakes anims.
"""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/retarget_result.json")
SRC_ROOT = "/Game/AnimStarterPack"
DEST = "/Game/Wanefall/Dimwit/Anims"
TARGET_SKEL = "/Game/Mannequins/Meshes/SK_Mannequin"   # the modern skeleton the aliens are rigged to
RETARGETER_CANDIDATES = [
    "/Game/Characters/Mannequins/Rigs/RTG_UE4_to_UE5",
    "/Game/Mannequins/Rigs/RTG_UE4_Manny_to_UE5",
    "/Game/Characters/Mannequins/RTG_Manny",
]
out = {"ok": False, "retargeted": 0, "records": []}
eal = unreal.EditorAssetLibrary
ar = unreal.AssetRegistryHelpers.get_asset_registry()
try:
    # find a usable IK Retargeter asset (best authored once in-editor; headless authoring of IK rigs is fragile)
    rtg = None
    for c in RETARGETER_CANDIDATES:
        o = unreal.load_asset(c)
        if o and o.__class__.__name__ == "IKRetargeter":
            rtg = c
            break
    if rtg is None:
        for ad in ar.get_assets_by_class(unreal.TopLevelAssetPath("/Script/IKRig", "IKRetargeter"), True):
            rtg = str(ad.package_name)
            break
    out["retargeter"] = rtg

    # gather AnimStarterPack sequences
    anims = [a for a in eal.list_assets(SRC_ROOT, recursive=True, include_folder=False)
             if isinstance(unreal.load_asset(a), unreal.AnimSequence)]
    out["source_anim_count"] = len(anims)

    if rtg is None:
        out["blocker"] = ("no IK Retargeter asset found. One-time in-editor: create an IK Rig for "
                          "UE4_Mannequin_Skeleton + one for SK_Mannequin, then an IK Retargeter linking them, save "
                          "as /Game/Characters/Mannequins/Rigs/RTG_UE4_to_UE5. Then re-run this script to batch.")
    elif anims:
        if not eal.does_directory_exist(DEST):
            eal.make_directory(DEST)
        batch = unreal.IKRetargetBatchOperation()
        settings = unreal.IKRetargetBatchOperationContext()
        settings.set_editor_property("source_mesh", None)
        settings.set_editor_property("ik_retargeter", unreal.load_asset(rtg))
        settings.set_editor_property("assets_to_retarget", [unreal.load_asset(a) for a in anims])
        settings.set_editor_property("name_rule", unreal.IKRetargetBatchOperationNameRule())
        settings.set_editor_property("destination_folder", DEST)
        batch.run_retarget(settings)
        made = eal.list_assets(DEST, recursive=True, include_folder=False)
        out["retargeted"] = len(made)
        out["ok"] = out["retargeted"] > 0
except Exception:
    out["error"] = traceback.format_exc()
RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_RETARGET_DONE ok=" + str(out.get("ok")))
