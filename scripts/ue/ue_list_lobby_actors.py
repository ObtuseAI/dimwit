"""List all actors in Wanefall_Lobby to identify placeholder cube geometry."""
import unreal, json
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/lobby_actors.json")

# Load the lobby map if not already open
lobby_pkg = "/Game/Wanefall/Maps/Wanefall_Lobby"
actor_list = []

world = unreal.EditorLevelLibrary.get_editor_world()
all_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor.static_class())

for a in all_actors:
    loc = a.get_actor_location()
    rec = {
        "name": a.get_name(),
        "class": type(a).__name__,
        "label": a.get_actor_label() if hasattr(a, 'get_actor_label') else "",
        "x": round(loc.x, 1),
        "y": round(loc.y, 1),
        "z": round(loc.z, 1),
    }
    # Check for static mesh components
    if isinstance(a, unreal.StaticMeshActor):
        smc = a.get_editor_property("static_mesh_component")
        if smc and smc.static_mesh:
            rec["mesh"] = smc.static_mesh.get_name()
    actor_list.append(rec)

# Sort by class then name
actor_list.sort(key=lambda r: (r["class"], r["name"]))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(actor_list, indent=2), encoding="utf-8")
unreal.log(f"RM_LIST_LOBBY_ACTORS_DONE total={len(actor_list)} -> {OUT}")
print(f"DIMWIT_LIST_LOBBY_ACTORS_DONE ok=True total={len(actor_list)}")
