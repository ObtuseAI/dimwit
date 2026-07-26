"""Read-only: enumerate the dependency tree of GASP's Sandbox character + ABP, and flag any /Game
package paths that already exist in WanefallGreybox (collision risk for a migrate). Run as a GASP-editor
commandlet:  UnrealEditor-Cmd <GASP.uproject> -run=pythonscript -script=scripts/ue/ue_gasp_depcheck.py
Writes the report to the scratchpad."""
import unreal, os, json

ROOTS = [
    "/Game/Blueprints/SandboxCharacter_CMC",
    "/Game/Blueprints/SandboxCharacter_CMC_ABP",
    "/Game/Blueprints/BPI_SandboxCharacter_ABP",
    "/Game/Blueprints/BPI_SandboxCharacter_Pawn",
]
WG_CONTENT = r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/Content"
OUT = r"C:/Users/developer/AppData/Local/Temp/claude/C--Users-chris/0d90559f-b663-435d-afb6-586407116470/scratchpad/gasp_depcheck.json"

ar = unreal.AssetRegistryHelpers.get_asset_registry()
seen = set()
stack = list(ROOTS)
opts = unreal.AssetRegistryDependencyOptions()
opts.include_hard_package_references = True
opts.include_soft_package_references = True

while stack:
    pkg = stack.pop()
    if pkg in seen or not pkg.startswith("/Game"):
        continue
    seen.add(pkg)
    try:
        deps = ar.get_dependencies(pkg, opts) or []
    except Exception:
        deps = []
    for d in deps:
        d = str(d)
        if d.startswith("/Game") and d not in seen:
            stack.append(d)

# collision = same /Game relative path already has a .uasset in Wanefall Content
collisions, migrate_list = [], sorted(seen)
for pkg in migrate_list:
    rel = pkg[len("/Game/"):]  # e.g. Blueprints/SandboxCharacter_CMC
    wg_path = os.path.join(WG_CONTENT, rel + ".uasset")
    if os.path.exists(wg_path):
        collisions.append(pkg)

colset = set(collisions)
missing = [p for p in migrate_list if p not in colset]
report = {
    "total_game_deps": len(migrate_list),
    "collision_count": len(collisions),
    "missing_count": len(missing),
    "missing": missing,
    "all_deps": migrate_list,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("GASP_DEPCHECK_DONE total=%d collisions=%d -> %s" % (len(migrate_list), len(collisions), OUT))
