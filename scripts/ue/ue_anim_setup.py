"""Dimwit ANIMATION UE driver — wires a rigged Hi3D character (a SkeletalMesh on the UE5 Mannequin skeleton) up
to reuse the in-project ABP_Manny / AnimStarterPack so it animates with no per-character animator.

Args (key=val, parsed from argv):
  rig_path=/Game/Wanefall/Dimwit/CharactersRigged/<Asset>_Rig   (required; the rigged SkeletalMesh)
  anim_bp=ABP_Manny                                              (optional; AnimBP name or full /Game path)

What it does (all real, verified by the WRITTEN result file, not exit code):
  1) load the rigged SkeletalMesh + read its Skeleton.
  2) load SK_Mannequin + read its Skeleton; assert the two skeletons are the SAME asset (compatibility gate).
  3) resolve ABP_Manny (by name search if only a name was given) and assign it as the SkeletalMesh's
     post-process AnimBP (so the mesh animates wherever it is placed/spawned), then SAVE the asset.
  4) enumerate compatible AnimSequences (same skeleton) under /Game/Mannequins + /Game/AnimStarterPack.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_anim_setup.py rig_path=... anim_bp=..."
Result -> artifacts/anim_setup_result.json
"""
import unreal, json, sys, traceback
from pathlib import Path

RESULT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/anim_setup_result.json")
SK_MANN = "/Game/Mannequins/Meshes/SKM_Manny"   # the UE5 SkeletalMesh (SK_Mannequin is the USkeleton)
# Where to look for AnimBPs and compatible AnimSequences.
ANIM_SEARCH_ROOTS = ["/Game/Mannequins", "/Game/AnimStarterPack", "/Game/Characters/Mannequins"]
ABP_FALLBACKS = [
    "/Game/Mannequins/Animations/ABP_Manny",
    "/Game/Characters/Mannequins/Animations/ABP_Manny",
    "/Game/AnimStarterPack/UE4_Mannequin/Mannequin/Animations/ThirdPerson_AnimBP",
]

A = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv if "=" in a}
res = {"args": A, "ok": False}
eal = unreal.EditorAssetLibrary
ar = unreal.AssetRegistryHelpers.get_asset_registry()


def _skeleton_of(obj):
    try:
        return obj.get_editor_property("skeleton")
    except Exception:
        return None


def _find_asset_by_name(name, class_names):
    """Search the AssetRegistry under ANIM_SEARCH_ROOTS for an asset whose name matches `name`."""
    for root in ANIM_SEARCH_ROOTS:
        try:
            assets = ar.get_assets_by_path(unreal.Name(root), recursive=True)
        except Exception:
            assets = []
        for ad in assets:
            try:
                an = str(ad.asset_name)
                cn = str(ad.asset_class_path.asset_name) if hasattr(ad, "asset_class_path") else str(ad.asset_class)
            except Exception:
                continue
            if an == name and (not class_names or cn in class_names):
                return str(ad.package_name) + "." + an
    return None


def resolve_abp(spec):
    """spec may be a full /Game path or just a name like 'ABP_Manny'. Return a loaded AnimBlueprint-ish asset."""
    cands = []
    if spec.startswith("/Game"):
        cands.append(spec)
    else:
        found = _find_asset_by_name(spec, {"AnimBlueprint"})
        if found:
            cands.append(found)
    cands += ABP_FALLBACKS
    for c in cands:
        o = unreal.load_asset(c)
        if o is not None:
            res["anim_bp_resolved_path"] = c
            return o
    return None


def list_compatible_anims(skeleton):
    """All AnimSequences under the search roots whose Skeleton == the rigged mesh's skeleton."""
    out = []
    sk_path = skeleton.get_path_name() if skeleton else None
    for root in ANIM_SEARCH_ROOTS:
        try:
            assets = ar.get_assets_by_path(unreal.Name(root), recursive=True)
        except Exception:
            assets = []
        for ad in assets:
            try:
                cn = str(ad.asset_class_path.asset_name) if hasattr(ad, "asset_class_path") else str(ad.asset_class)
                if cn != "AnimSequence":
                    continue
                seq = unreal.load_asset(str(ad.package_name) + "." + str(ad.asset_name))
                if seq is None:
                    continue
                seq_skel = _skeleton_of(seq)
                if seq_skel and seq_skel.get_path_name() == sk_path:
                    out.append(seq.get_path_name())
            except Exception:
                continue
    return out


def assign_anim_bp(sk_mesh, abp):
    """Assign the AnimBP as the SkeletalMesh post-process anim instance so it animates on placement/spawn."""
    try:
        # AnimBlueprint -> its generated AnimInstance class.
        anim_class = abp.get_editor_property("generated_class") if hasattr(abp, "get_editor_property") else None
    except Exception:
        anim_class = None
    if anim_class is None:
        try:
            anim_class = unreal.load_class(None, abp.get_path_name() + "_C")
        except Exception:
            anim_class = None
    if anim_class is None:
        return False
    try:
        sk_mesh.set_editor_property("post_process_anim_blueprint", anim_class)
        eal.save_loaded_asset(sk_mesh)
        return True
    except Exception as e:
        res["assign_warn"] = str(e)
        return False


try:
    rig_path = A.get("rig_path")
    if not rig_path:
        raise ValueError("rig_path is required")

    sk_mesh = unreal.load_asset(rig_path)
    res["rig_exists"] = isinstance(sk_mesh, unreal.SkeletalMesh)
    if not res["rig_exists"]:
        # Fail-closed: the rigging pipeline must run first.
        res["error"] = f"rigged SkeletalMesh not found at {rig_path}; run the rigging pipeline first"
    else:
        rig_skel = _skeleton_of(sk_mesh)
        mann = unreal.load_asset(SK_MANN)
        mann_skel = _skeleton_of(mann) if mann else None
        res["rig_skeleton"] = rig_skel.get_path_name() if rig_skel else None
        res["mannequin_skeleton"] = mann_skel.get_path_name() if mann_skel else None
        res["skeleton_compatible"] = bool(
            rig_skel and mann_skel and rig_skel.get_path_name() == mann_skel.get_path_name())

        # Resolve + assign the AnimBP (only meaningful if compatible, but resolve regardless for diagnostics).
        abp = resolve_abp(A.get("anim_bp", "ABP_Manny"))
        res["anim_bp_found"] = abp is not None
        res["anim_bp_assigned"] = bool(res["skeleton_compatible"] and abp and assign_anim_bp(sk_mesh, abp))

        anims = list_compatible_anims(rig_skel) if res["skeleton_compatible"] else []
        res["compatible_anims"] = anims
        res["compatible_anim_count"] = len(anims)

        res["ok"] = bool(res["skeleton_compatible"] and res["anim_bp_assigned"] and res["compatible_anim_count"] >= 1)
except Exception:
    res["error"] = traceback.format_exc()

RESULT.parent.mkdir(parents=True, exist_ok=True)
RESULT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_ANIM_SETUP_DONE ok=" + str(res.get("ok")))
