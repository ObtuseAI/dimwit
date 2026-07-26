import unreal
eal = unreal.EditorAssetLibrary
n = 0
for a in eal.list_assets("/Game/Wanefall/Dimwit/Characters", recursive=True, include_folder=False):
    obj = unreal.load_asset(a)
    if isinstance(obj, unreal.MaterialInterface):
        eal.save_asset(a); n += 1
print("CHMAT_RESAVED " + str(n))
