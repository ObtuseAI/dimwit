"""Make the kit metal READABLE. The glTF-imported M_KitMetal is Metallic 0.85 + near-black base, so every surface
renders black with no sky to reflect. We author a fresh mostly-diffuse dark-grey UE material (M_KitLit) and
reassign it to every 'Metal' slot on the kit meshes. The emissive Wane-accent slot is left untouched.
Run headless; affects THE HOLD and the kit arena (shared mesh assets)."""
import unreal

MAP_KIT = "/Game/Wanefall/Dimwit/MapKit"
LIT_PATH = "/Game/Wanefall/Dimwit/MapKit"
LIT_NAME = "M_KitLit"

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

# --- author M_KitLit (constant dark blue-grey, low metallic, medium roughness) ---
full = f"{LIT_PATH}/{LIT_NAME}"
if eal.does_asset_exist(full):
    eal.delete_asset(full)
mat = tools.create_asset(LIT_NAME, LIT_PATH, unreal.Material, unreal.MaterialFactoryNew())

bc = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
bc.set_editor_property("constant", unreal.LinearColor(0.14, 0.15, 0.18, 1.0))
mel.connect_material_property(bc, "", unreal.MaterialProperty.MP_BASE_COLOR)

mm = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
mm.set_editor_property("r", 0.10)
mel.connect_material_property(mm, "", unreal.MaterialProperty.MP_METALLIC)

rr = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 320)
rr.set_editor_property("r", 0.58)
mel.connect_material_property(rr, "", unreal.MaterialProperty.MP_ROUGHNESS)

mel.recompile_material(mat)
eal.save_asset(full)
print(f"FIXKIT: authored {full}")

# --- reassign every 'Metal' slot on the kit meshes to M_KitLit ---
assets = eal.list_assets(MAP_KIT, recursive=True, include_folder=False)
changed = 0
for a in assets:
    sm = unreal.load_asset(a)
    if not isinstance(sm, unreal.StaticMesh):
        continue
    n = sm.get_num_sections(0) if hasattr(sm, "get_num_sections") else 0
    # iterate material slots
    slots = sm.get_editor_property("static_materials")
    touched = False
    for i in range(len(slots)):
        cur = sm.get_material(i)
        cur_name = cur.get_name() if cur else ""
        if "Metal" in cur_name and "Lit" not in cur_name:
            sm.set_material(i, mat)
            touched = True
    if touched:
        eal.save_asset(a)
        changed += 1

print(f"FIXKIT_DONE meshes_changed={changed}")
