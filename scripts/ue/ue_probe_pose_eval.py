"""One-shot diagnostic: does a headless single-node anim actually move BONES?
Poses a rigged skeletal mesh at bind vs a run frame, reads a hand-bone world transform each, prints both.
If they differ -> anim eval works, the frozen-capture is a RENDER/capture problem.
If identical    -> anim eval itself is broken (set_position/tick not evaluating).
Run: UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_probe_pose_eval.py rig_path=/Game/... bone=hand_r"
"""
import unreal, sys, json, traceback
from pathlib import Path

ARGS = {}
for a in sys.argv:
    if "=" in a:
        k, v = a.split("=", 1)
        ARGS[k.strip()] = v.strip()
RIG = ARGS.get("rig_path", "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig")
BONE = ARGS.get("bone", "hand_r")
ANIM = ARGS.get("anim", "/Game/Mannequins/Animations/Manny/MM_Run_Fwd")
MAP = ARGS.get("map", "/Game/Wanefall/Maps/Wanefall_Lobby")
RES = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/pose_eval_probe.json")
out = {"ok": False, "rig": RIG, "bone": BONE}


def _eval(comp):
    for _ in range(3):
        for call in (lambda: comp.tick_animation(0.1, False),
                     lambda: comp.tick_pose(0.1, False),
                     lambda: comp.refresh_bone_transforms(),
                     lambda: comp.finalize_bone_transform()):
            try:
                call()
            except Exception:
                pass


def _bone_loc(comp):
    t = comp.get_socket_transform(BONE, unreal.RelativeTransformSpace.RTS_WORLD)
    l = t.translation
    return [round(l.x, 3), round(l.y, 3), round(l.z, 3)]


try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(MAP)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    sk = unreal.load_asset(RIG)
    anim = unreal.load_asset(ANIM)
    out["anim_loaded"] = bool(anim)
    actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(sk) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    try:
        comp.set_editor_property("visibility_based_anim_tick_option",
                                 unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    except Exception as e:
        out["vis_warn"] = str(e)
    try:
        comp.set_update_animation_in_editor(True)
    except Exception:
        pass

    # bind pose
    comp.set_animation(None)
    _eval(comp)
    out["bind_bone"] = _bone_loc(comp)

    # M1: set_animation + set_position + play + tick
    comp.set_animation(anim)
    comp.set_position(0.5)
    comp.play(False)
    _eval(comp)
    out["run_bone_setpos"] = _bone_loc(comp)

    # M2: FSingleAnimationPlayData struct (animation_data) + init_anim(True) then tick
    try:
        pd = unreal.SingleAnimationPlayData()
        pd.set_editor_property("anim_to_play", anim)
        try:
            pd.set_editor_property("saved_position", 0.5)
        except Exception:
            pass
        comp.set_editor_property("animation_data", pd)
        try:
            comp.init_anim(True)
        except Exception as e:
            out["init_anim_warn"] = str(e)
        _eval(comp)
        out["run_bone_animdata"] = _bone_loc(comp)
    except Exception as e:
        out["animdata_warn"] = str(e)

    # M3: play_animation(anim, looping) then set_position then tick
    try:
        comp.play_animation(anim, False)
        comp.set_position(0.5)
        _eval(comp)
        out["run_bone_playanim"] = _bone_loc(comp)
    except Exception as e:
        out["playanim_warn"] = str(e)

    b = out.get("bind_bone")
    out["moved_setpos"] = b != out.get("run_bone_setpos")
    out["moved_animdata"] = b != out.get("run_bone_animdata")
    out["moved_playanim"] = b != out.get("run_bone_playanim")
    out["ok"] = True
    eas.destroy_actor(actor)
except Exception:
    out["error"] = traceback.format_exc()

RES.parent.mkdir(parents=True, exist_ok=True)
RES.write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("DIMWIT_POSE_EVAL_PROBE " + json.dumps({k: out.get(k) for k in
           ("bind_bone", "run_bone_setpos", "run_bone_sni", "bind_vs_setpos_moved", "bind_vs_sni_moved")}))
