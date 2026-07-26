import unreal, statistics
DST = "/Game/Wanefall/Maps/Wanefall_Lobby"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
unreal.log("LOBBY_LOAD " + str(les.load_level(DST)))
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
acts = eas.get_all_level_actors()
starts = [a for a in acts if a.get_class().get_name() == "PlayerStart"]
unreal.log("LOBBY_PS_COUNT " + str(len(starts)))
for s in starts[:3]:
    unreal.log("LOBBY_PS_LOC " + str(s.get_actor_location()))
if not starts:
    locs = [a.get_actor_location() for a in acts if a.get_class().get_name() == "StaticMeshActor"]
    if locs:
        loc = unreal.Vector(statistics.median([l.x for l in locs]),
                            statistics.median([l.y for l in locs]),
                            min(l.z for l in locs) + 250)
    else:
        loc = unreal.Vector(0, 0, 300)
    eas.spawn_actor_from_class(unreal.PlayerStart, loc, unreal.Rotator(0, 0, 0))
    unreal.log("LOBBY_PS_ADDED " + str(loc))
    unreal.log("LOBBY_SAVE " + str(les.save_current_level()))
