"""Determine GASP ABP's data contract: does SandboxCharacter_CMC_ABP depend on the BP interface
(BPI_SandboxCharacter_ABP) and/or hard-reference the SandboxCharacter pawn? List its anim-relevant
deps + the interface's functions + the anim-properties struct fields. Run as a Wanefall-editor commandlet."""
import unreal, os, json

OUT = r"C:/Users/developer/AppData/Local/Temp/claude/C--Users-chris/0d90559f-b663-435d-afb6-586407116470/scratchpad/gasp_contract.json"
ar = unreal.AssetRegistryHelpers.get_asset_registry()
opts = unreal.AssetRegistryDependencyOptions()
opts.include_hard_package_references = True
opts.include_soft_package_references = True

abp = "/Game/Blueprints/SandboxCharacter_CMC_ABP"
deps = [str(d) for d in (ar.get_dependencies(abp, opts) or [])]
rel = [d for d in deps if any(k in d for k in ("Sandbox", "BPI_", "Trajectory", "S_Character", "Chooser", "CT_", "Overlay"))]
res = {
    "abp_uses_interface_ABP": any("BPI_SandboxCharacter_ABP" in d for d in deps),
    "abp_refs_pawn": any("BPI_SandboxCharacter_Pawn" in d for d in deps) or any(d.endswith("SandboxCharacter_CMC") for d in deps),
    "abp_relevant_deps": sorted(rel),
    "abp_total_deps": len(deps),
}

# enumerate functions on the interface's generated class + fields of the anim struct
def class_functions(bp_path):
    try:
        bp = unreal.load_asset(bp_path)
        gc = bp.get_editor_property("generated_class") if bp else None
        if not gc:
            return None
        names = []
        # UFunction discovery via the struct's children isn't directly exposed; try get_function_names if present
        try:
            names = [str(n) for n in unreal.PythonBPLib.get_function_names(gc)]  # may not exist
        except Exception:
            names = None
        return {"generated_class": gc.get_name(), "functions": names}
    except Exception as e:
        return {"error": str(e)[:200]}

res["interface_ABP"] = class_functions("/Game/Blueprints/BPI_SandboxCharacter_ABP")

def struct_fields(struct_path):
    try:
        s = unreal.load_asset(struct_path)
        return s.get_name() if s else None
    except Exception as e:
        return {"error": str(e)[:120]}
res["anim_struct_loads"] = struct_fields("/Game/Blueprints/Data/S_CharacterPropertiesForAnimation")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(res, open(OUT, "w"), indent=2)
print("GASP_CONTRACT_DONE iface=%s pawnref=%s -> %s" % (res["abp_uses_interface_ABP"], res["abp_refs_pawn"], OUT))
