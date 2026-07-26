"""Install SAVED rig display actors into the ModeShell map (ACTIVE_RIG_MATERIAL_TRUTH_REPAIR_V1).

PROBE-PROVEN ROOT CAUSE: in the tick-less headless sessions the validation probe uses, SESSION-
SPAWNED actors always render the engine default material (even map-proven materials assigned to a
spawned cube render as the default checker). Only SAVED MAP CONTENT renders real materials. Every
rig_ship capture ever taken photographed the default material; vorlax merely sat under the 0.06
white threshold. Fix: the capture subject becomes saved map content - two SkeletalMeshActors
labeled RigShipValidationDisplay_A/_B placed in a far validation corner (following the existing
ModeShellValidation_NeutralBackdrop staging precedent), saved with the active rig and two saved
single-node poses. The probe then captures them without spawning or mutating anything.

Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_install_rig_ship_display.py"
Re-run whenever the active rig changes (roster swap) - idempotent.
"""
import json
import traceback
from pathlib import Path

import unreal

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/rig_ship_display_install_result.json")
MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
# EXPOSURE-BALANCED ZONE (ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1, 2026-07-02): the menu area's
# lighting falls off along -Y — the 4-variant experiment row photographed it directly
# (artifacts/zythan_mat_experiment/): y-400 washes the dark-violet carapace to silver under the
# PlayerStart brightness, y<=-1200 goes black. Exposure is NOT tunable in tick-less captures
# (sweeps proved PP overrides inert + cvars saturating), so staging position IS the exposure knob.
# H1B2 REFINEMENT (same day): the calibrated cross-vendor judge quorum stably failed the y-800
# capture as underexposed (figure mean_v 0.286 vs reference 0.489; a +12% synthetic lift passed
# stably) — y-700 buys roughly that lift while staying clear of the y-400 wash zone.
DISPLAY_OFFSET = unreal.Vector(0.0, -700.0, 0.0)
ACTORS = [
    ("RigShipValidationDisplay_A", "/Game/Mannequins/Animations/Manny/MM_Idle", 0.3),
    ("RigShipValidationDisplay_B", "/Game/Mannequins/Animations/Manny/MM_Run_Fwd", 0.5),
]
result = {"ok": False, "map": MAP, "rig": RIG, "actors": []}

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(MAP)
    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location()
            break
    anchor = base + DISPLAY_OFFSET
    sk = unreal.load_asset(RIG)
    if not isinstance(sk, unreal.SkeletalMesh):
        raise RuntimeError(f"active rig not a SkeletalMesh: {type(sk).__name__ if sk else None}")

    existing = {a.get_actor_label(): a for a in eas.get_all_level_actors()
                if isinstance(a, unreal.SkeletalMeshActor)}
    for i, (label, anim_path, t) in enumerate(ACTORS):
        loc = anchor + unreal.Vector(0.0, i * 300.0, 0.0)
        actor = existing.get(label)
        if actor is None:
            actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, loc, unreal.Rotator(0, 0, 180))
            actor.set_actor_label(label)
        else:
            actor.set_actor_location(loc, False, False)
        comp = actor.skeletal_mesh_component
        (comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk))
        anim = unreal.load_asset(anim_path)
        if anim:
            comp.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            try:
                data = comp.get_editor_property("animation_data")
                data.set_editor_property("anim_to_play", anim)
                data.set_editor_property("saved_position", t)
                data.set_editor_property("saved_play_rate", 0.0)
                comp.set_editor_property("animation_data", data)
            except Exception as exc:
                result.setdefault("warnings", []).append(f"{label} animation_data: {exc!r}")
        result["actors"].append({"label": label, "location": [loc.x, loc.y, loc.z],
                                 "mesh": sk.get_path_name(), "anim": anim_path, "position": t})

    # The menu area's own lighting/exposure is authoritative (old spawn captures were correctly
    # exposed there). Remove the earlier corner-staging attempt - custom enclosed studio + auto
    # exposure blew the frame to white regardless of light intensity.
    removed = []
    for a in list(eas.get_all_level_actors()):
        label = a.get_actor_label()
        if label in ("RigShipValidationFloor", "RigShipValidationBackdrop",
                     "RigShipValidationKeyLight", "RigShipValidationFillLight"):
            eas.destroy_actor(a)
            removed.append(label)
    result["staging_removed"] = removed

    saved = les.save_current_level()
    result["map_saved"] = bool(saved)
    result["ok"] = bool(saved)
except Exception:
    result["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("DISPLAY_INSTALL_RESULT:", json.dumps(result)[:400])
