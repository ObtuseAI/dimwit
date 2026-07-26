"""Bridge capture: spawn the roster rig + SM_Rifle attached to hand_r exactly as AttachVisibleWeapon does,
frame the SceneCapture on the right hand, render a PNG so we can SEE how the gun sits vs the hand."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ue_mcp.ue_client import call

OUT = r"C:/Users/developer/Documents/Dimwit/artifacts/weapon_capture.png"
code = r'''
import unreal, json
res = {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
les.load_level("/Game/Wanefall/Maps/Wanefall_CleanStage_01")

rig = unreal.load_asset("/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig")
rifle = unreal.load_asset("/Game/NiagaraExamples/Gallery/Weapons/Rifle/Mesh/SM_Rifle.SM_Rifle")
res["rig"] = bool(rig); res["rifle"] = bool(rifle)

base = unreal.Vector(0, 0, 0)
char = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, base, unreal.Rotator(0, 0, 0))
comp = char.skeletal_mesh_component
comp.set_skeletal_mesh_asset(rig) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(rig)
comp.set_editor_property("visibility_based_anim_tick_option", unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)

# WeaponNormScale in-game = 60cm / longest axis. SM_Rifle bbox longest ~ compute.
wb = rifle.get_bounds().box_extent
longest = max(wb.x, wb.y, wb.z) * 2.0
scale = (60.0 / longest) if longest > 1.0 else 1.0
res["rifle_longest_cm"] = round(longest, 1); res["norm_scale"] = round(scale, 4)

# Attach the rifle to hand_r exactly like AttachVisibleWeapon: SnapToTarget, relative (0,0,0), yaw -90.
gun = eas.spawn_actor_from_class(unreal.StaticMeshActor, base, unreal.Rotator(0, 0, 0))
gc = gun.static_mesh_component
gc.set_static_mesh(rifle)
gc.attach_to_component(comp, unreal.Name("hand_r"), unreal.AttachmentRule.SNAP_TO_TARGET, unreal.AttachmentRule.SNAP_TO_TARGET, unreal.AttachmentRule.SNAP_TO_TARGET, False)
gc.set_relative_location(unreal.Vector(0, 0, 0))
gc.set_relative_rotation(unreal.Rotator(0, -90, 0))
gc.set_relative_scale3d(unreal.Vector(scale, scale, scale))

hand = comp.get_socket_transform(unreal.Name("hand_r"), unreal.RelativeTransformSpace.RTS_WORLD).translation
gunw = gc.get_world_location()
res["hand_r_world"] = [round(hand.x,1), round(hand.y,1), round(hand.z,1)]
res["gun_world"] = [round(gunw.x,1), round(gunw.y,1), round(gunw.z,1)]
res["gun_offset_from_hand_cm"] = round(((gunw.x-hand.x)**2+(gunw.y-hand.y)**2+(gunw.z-hand.z)**2)**0.5, 1)

# key light + framing on the upper body / right hand
key = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0,-200,300), unreal.Rotator(-40,50,0))
sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0,0,150))
rt = unreal.RenderingLibrary.create_render_target2d(world, 1000, 1000, unreal.TextureRenderTargetFormat.RTF_RGBA8)
cam_loc = unreal.Vector(hand.x, hand.y - 180, hand.z + 10)
look = unreal.Vector(hand.x, hand.y, hand.z)
rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, look)
cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, rot)
cc = cap.capture_component2d
cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
cc.set_editor_property("texture_target", rt)
cc.set_editor_property("fov_angle", 55.0)
cc.capture_scene()
unreal.RenderingLibrary.export_render_target(world, rt, r"C:/Users/developer/Documents/Dimwit/artifacts", "weapon_capture.png")
for a in (cap, gun, char, key, sky):
    try: eas.destroy_actor(a)
    except Exception: pass
result = json.dumps(res)
'''
r = call("exec", {"code": code}, timeout=180.0)
raw = r.get("result") if isinstance(r, dict) else None
if isinstance(raw, str) and raw[:1] == raw[-1:] == "'":
    raw = raw[1:-1]
print(raw)
