"""Does the runtime character rig expose the sockets the weapon/grapple attach code needs?
Mirrors WanefallPrototypeCharacter's DoesSocketExist checks: hand_r/GripPoint (weapon), lowerarm_l (grapple)."""
import unreal, json
from pathlib import Path

RIG = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig"
out = {"rig": RIG}
try:
    sk = unreal.load_asset(RIG)
    out["loaded"] = bool(sk)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
    out["skeleton"] = comp.get_skeletal_mesh_asset().skeleton.get_path_name() if hasattr(comp, "get_skeletal_mesh_asset") else None
    for name in ("hand_r", "hand_l", "lowerarm_l", "lowerarm_r", "GripPoint", "weapon_r", "root", "pelvis"):
        out[f"has_{name}"] = bool(comp.does_socket_exist(name))
    # sample a couple bone world transforms to confirm the skeleton is real
    for b in ("hand_r", "lowerarm_l"):
        try:
            t = comp.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_ACTOR).translation
            out[f"{b}_loc"] = [round(t.x, 1), round(t.y, 1), round(t.z, 1)]
        except Exception:
            pass
    eas.destroy_actor(actor)
except Exception as e:
    import traceback
    out["error"] = traceback.format_exc()

Path(r"C:/Users/developer/Documents/Dimwit/artifacts/socket_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("PROBE_SOCKETS " + json.dumps({k: out.get(k) for k in out if k.startswith("has_") or k in ("loaded", "error")}))
