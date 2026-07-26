"""Best-effort scriptable scaffold for GASP Stage 2: create a Blueprint player pawn that is a child of the
Wanefall C++ character AWanefallPrototypeCharacter (keeps all game logic), and set it up to drive GASP's
ABP: mesh = GASP UE5 SKM_Manny, AnimClass = SandboxCharacter_CMC_ABP, + CharacterTrajectory component for
motion matching. Reports per-step what stuck. The BP-interface impl graph is NOT scriptable and is left
for the editor. Run as a Wanefall-editor commandlet."""
import unreal, os, json

OUT = r"C:/Users/developer/AppData/Local/Temp/claude/C--Users-chris/0d90559f-b663-435d-afb6-586407116470/scratchpad/gasp_scaffold.json"
BP_PATH = "/Game/Wanefall/Player"
BP_NAME = "BP_WanefallGaspCharacter"
r = {"steps": {}}

def step(k, fn):
    try:
        r["steps"][k] = {"ok": True, "detail": fn()}
    except Exception as e:
        import traceback
        r["steps"][k] = {"ok": False, "error": str(e)[:300], "tb": traceback.format_exc()[-500:]}

# 1) resolve the Wanefall C++ pawn class
def _parent():
    cls = unreal.load_object(None, "/Script/WanefallGreybox.WanefallPrototypeCharacter")
    if not cls:
        raise Exception("WanefallPrototypeCharacter class not found")
    return cls.get_name()
step("resolve_parent_class", _parent)

# 2) create the BP child (or load if it exists)
def _create():
    full = BP_PATH + "/" + BP_NAME
    if unreal.EditorAssetLibrary.does_asset_exist(full):
        return "exists"
    parent = unreal.load_object(None, "/Script/WanefallGreybox.WanefallPrototypeCharacter")
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent)
    at = unreal.AssetToolsHelpers.get_asset_tools()
    bp = at.create_asset(BP_NAME, BP_PATH, unreal.Blueprint, factory)
    unreal.EditorAssetLibrary.save_asset(BP_PATH + "/" + BP_NAME)
    return "created" if bp else "create_returned_none"
step("create_bp_child", _create)

# 3) set the inherited Mesh component default: GASP SKM_Manny + GASP ABP
def _mesh_anim():
    bp = unreal.load_asset(BP_PATH + "/" + BP_NAME)
    gc = unreal.load_object(None, BP_PATH + "/" + BP_NAME + "." + BP_NAME + "_C")
    cdo = unreal.get_default_object(gc) if gc else None
    if not cdo:
        raise Exception("no CDO for generated class")
    mesh = cdo.get_editor_property("mesh")  # inherited ACharacter Mesh comp
    skm = unreal.load_asset("/Game/Characters/UE5_Mannequins/Meshes/SKM_Manny")
    abp_bp = unreal.load_asset("/Game/Blueprints/SandboxCharacter_CMC_ABP")
    abp_cls = unreal.load_object(None, "/Game/Blueprints/SandboxCharacter_CMC_ABP.SandboxCharacter_CMC_ABP_C")
    out = {}
    if skm:
        mesh.set_editor_property("skeletal_mesh_asset", skm); out["mesh"] = skm.get_name()
    if abp_cls:
        mesh.set_editor_property("anim_class", abp_cls); out["anim_class"] = abp_cls.get_name()
    unreal.EditorAssetLibrary.save_asset(BP_PATH + "/" + BP_NAME)
    return out
step("set_mesh_and_abp", _mesh_anim)

# 4) does the CharacterTrajectory component type exist (needed by motion matching)?
def _traj():
    t = None
    for n in ("CharacterTrajectoryComponent", "CharacterMovementTrajectoryComponent"):
        c = getattr(unreal, n, None)
        if c:
            t = n; break
    return t or "NOT-FOUND (add PoseSearch/AnimationLocomotionLibrary trajectory comp in editor)"
step("trajectory_component_type", _traj)

# 5) can we enumerate the interfaces the BP must implement (report only)
r["interfaces_to_implement_in_editor"] = [
    "/Game/Blueprints/BPI_SandboxCharacter_ABP",
    "/Game/Blueprints/BPI_SandboxCharacter_Pawn",
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(r, open(OUT, "w"), indent=2)
oks = sum(1 for v in r["steps"].values() if v.get("ok"))
print("GASP_SCAFFOLD_DONE ok=%d/%d -> %s" % (oks, len(r["steps"]), OUT))
