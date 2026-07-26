import unreal
SRC = "/Game/SoulCave/Maps/LV_Soul_Cave"
DST = "/Game/Wanefall/Maps/Wanefall_Lobby"
eal = unreal.EditorAssetLibrary
if eal.does_asset_exist(DST):
    eal.delete_asset(DST)
dup = eal.duplicate_asset(SRC, DST)          # duplicate only — NO load_level in the same process
print("LOBBY_DUP", dup is not None)
print("LOBBY_SAVE", eal.save_asset(DST))
print("LOBBY_EXISTS", eal.does_asset_exist(DST))
