"""Dimwit WANEFALL PAWN PROBE (UE headless) — GROUND TRUTH for the 'junk geometry on the lobby character' bug.
Spawn the real lobby pawn class, enumerate EVERY primitive component it carries (the inherited prototype meshes +
the lobby's own), and report each one's mesh asset, default (constructor) visibility, hidden-in-game flag, relative
location and world-bounds size. This tells us EXACTLY which meshes are the black cube + grey blob, instead of
guessing. Writes artifacts/pawn_probe.json.

  UnrealEditor-Cmd <uproj> -ExecutePythonScript="scripts/ue/wanefall_pawn_probe.py"
"""
import unreal, json, traceback
from pathlib import Path

RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/pawn_probe.json")
out = {"ok": False, "components": []}


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


try:
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # Spawn the real lobby pawn class in the current editor world (constructor runs -> all subobjects exist with
    # their DEFAULT visibility; BeginPlay's hide does NOT run on an editor spawn, so we see the raw carried set).
    cls = unreal.WanefallLobbyCharacter
    loc = unreal.Vector(0.0, 0.0, 0.0)
    pawn = eas.spawn_actor_from_class(cls, loc, unreal.Rotator(0, 0, 0))
    out["pawn_spawned"] = pawn is not None
    out["pawn_class"] = "WanefallLobbyCharacter"

    # every primitive (static + skeletal) component on the pawn
    prims = pawn.get_components_by_class(unreal.PrimitiveComponent)
    for c in prims:
        rec = {
            "name": safe(lambda: c.get_name()),
            "class": safe(lambda: c.get_class().get_name()),
            "visible": safe(lambda: c.get_editor_property("visible")),
            "hidden_in_game": safe(lambda: c.get_editor_property("hidden_in_game")),
            "rel_loc": safe(lambda: [round(c.get_relative_location().x, 1),
                                     round(c.get_relative_location().y, 1),
                                     round(c.get_relative_location().z, 1)]),
        }
        # mesh asset (static or skeletal)
        sm = safe(lambda: c.get_editor_property("static_mesh"))
        if sm:
            rec["mesh"] = safe(lambda: sm.get_path_name())
            rec["kind"] = "static"
        sk = safe(lambda: c.get_editor_property("skeletal_mesh_asset")) or safe(lambda: c.get_editor_property("skeletal_mesh"))
        if sk:
            rec["mesh"] = safe(lambda: sk.get_path_name())
            rec["kind"] = "skeletal"
        # world-space size so we can tell a big blob from a tiny marker
        b = safe(lambda: c.get_editor_property("bounds"))
        if b:
            rec["bounds_extent"] = safe(lambda: [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)])
        # "would render at rest" = visible AND not hidden-in-game AND has a mesh
        rec["renders_at_rest"] = bool(rec.get("visible")) and not bool(rec.get("hidden_in_game")) and bool(rec.get("mesh"))
        out["components"].append(rec)

    out["renders_at_rest"] = [r["name"] for r in out["components"] if r.get("renders_at_rest")]
    out["ok"] = True
    eas.destroy_actor(pawn)
except Exception:
    out["error"] = traceback.format_exc()

RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_PAWN_PROBE_DONE ok=" + str(out.get("ok")) + " renders_at_rest=" + str(out.get("renders_at_rest")))
print("DIMWIT_PAWN_PROBE_DONE ok=" + str(out.get("ok")))
