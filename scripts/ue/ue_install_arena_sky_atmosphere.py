"""Install a SkyAtmosphere into the arena map (packaged-gameplay polish, 2026-07-02).

The first machine-played packaged matches render the engine's on-screen red warning: the map's
SkyLight uses real-time capture but the scene has no SkyAtmosphere / VolumetricCloud / IsSky
material, so the capture would be black. Adds a SkyAtmosphere actor (idempotent by label) and
saves the map - kills the on-screen warning and gives the arena a real sky contribution.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_install_arena_sky_atmosphere.py"
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/arena_sky_atmosphere_install_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01"
LABEL = "ArenaSkyAtmosphere"
result = {"ok": False, "map": MAP}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)
    existing = [a for a in eas.get_all_level_actors() if isinstance(a, unreal.SkyAtmosphere)]
    if existing:
        result["already_present"] = [a.get_actor_label() for a in existing]
    else:
        actor = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        actor.set_actor_label(LABEL)
        result["spawned"] = LABEL
    result["skylights"] = [a.get_actor_label() for a in eas.get_all_level_actors()
                           if isinstance(a, unreal.SkyLight)]
    saved = les.save_current_level()
    result["map_saved"] = bool(saved)
    result["ok"] = bool(saved)
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("SKY_ATMO_RESULT:", json.dumps(result)[:300])
