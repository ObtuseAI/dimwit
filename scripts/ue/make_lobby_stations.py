"""Place the 5 lobby stations in Wanefall_Lobby (SoulCave), fanned in front of the PlayerStart. Run AFTER the
editor target compiles (needs the WanefallLobbyStation class). Separate process from any duplicate (avoids the
GC-leak fatal)."""
import unreal

LEVEL = "/Game/Wanefall/Maps/Wanefall_Lobby"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
print("LOBSTA load", les.load_level(LEVEL))
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

ps = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "PlayerStart"]
base = ps[0].get_actor_location() if ps else unreal.Vector(-20170, -12910, -1978)
print("LOBSTA base", base)

StationCls = unreal.load_class(None, "/Script/WanefallGreybox.WanefallLobbyStation")
console = (unreal.load_asset("/Game/Wanefall/Dimwit/MapKit/SM_Kit_Spire/StaticMeshes/SM_Kit_Spire")
           or unreal.load_asset("/Game/Wanefall/Dimwit/MapKit/SM_Kit_Cover/StaticMeshes/SM_Kit_Cover"))

# clear any prior lobby stations
for a in list(eas.get_all_level_actors()):
    if a.get_class().get_name() == "WanefallLobbyStation":
        eas.destroy_actor(a)

types = [unreal.WanefallStation.CHARACTER, unreal.WanefallStation.LOADOUT,
         unreal.WanefallStation.LEADERBOARDS, unreal.WanefallStation.RANK,
         unreal.WanefallStation.MODE_SELECT]
n = 0
for i, t in enumerate(types):
    loc = unreal.Vector(base.x + 700, base.y + (i - 2) * 360, base.z + 60)
    act = eas.spawn_actor_from_class(StationCls, loc, unreal.Rotator(0, 180, 0))
    if not act:
        continue
    act.set_editor_property("station_type", t)
    smc = act.get_component_by_class(unreal.StaticMeshComponent)
    if smc and console:
        smc.set_static_mesh(console)
    act.set_actor_scale3d(unreal.Vector(2.2, 2.2, 2.2))
    n += 1

print("LOBSTA placed", n)
print("LOBSTA save", les.save_current_level())
