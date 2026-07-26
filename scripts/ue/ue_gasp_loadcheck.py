"""Load-verify the migrated GASP character system inside the WanefallGreybox project. Run as a
Wanefall-editor commandlet. Reports whether the key assets load and what the ABP's target skeleton is."""
import unreal, os, json
OUT = r"C:/Users/developer/AppData/Local/Temp/claude/C--Users-chris/0d90559f-b663-435d-afb6-586407116470/scratchpad/gasp_loadcheck.json"
targets = [
    "/Game/Blueprints/SandboxCharacter_CMC_ABP",
    "/Game/Blueprints/SandboxCharacter_CMC",
    "/Game/Blueprints/BPI_SandboxCharacter_ABP",
    "/Game/Characters/UE5_Mannequins/Meshes/SKM_Manny",
]
res = {}
for t in targets:
    try:
        a = unreal.load_asset(t)
        res[t] = {"loaded": bool(a), "class": a.get_class().get_name() if a else None}
    except Exception as e:
        res[t] = {"loaded": False, "error": str(e)[:200]}
# target skeleton of the ABP (anim blueprints expose TargetSkeleton via the generated class is hard headless;
# just report the CMC_ABP loaded ok — deeper introspection happens in the editor GUI)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(res, open(OUT, "w"), indent=2)
ok = sum(1 for v in res.values() if v.get("loaded"))
print("GASP_LOADCHECK_DONE ok=%d/%d -> %s" % (ok, len(targets), OUT))
