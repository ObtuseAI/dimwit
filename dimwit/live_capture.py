"""Calibrated LIVE hero capture for the powerloop (Unlock #1). Drives the live editor via the Dimwit bridge
(ue_mcp tcp:8222) to produce a FAIR, subject-isolated hero shot of a rigged character — the thing the loop
judges. Solves the three capture artifacts found the hard way:

  * MISFRAMING  -> auto-frame the camera from the actor's REAL bounds (get_actor_bounds), not guessed offsets.
  * DARK FRONT  -> a front-fill light from the camera direction (+ side key + sky), so the camera-facing body
                   is lit, not just rim-lit (a mid-albedo body otherwise renders near-black from the front).
  * BG POLLUTION-> capture an empty-scene BG shot with the SAME camera+lights, then isolate the character by
                   BACKGROUND SUBTRACTION (perception.analyze_image(char, bg_path=bg)). Measures the CHARACTER,
                   never the void/backdrop/environment — which otherwise false-fail too_dark + dilute palette.

Requires the editor open with the Dimwit bridge running (init_unreal.py auto-starts it; see ue_mcp/). Returns
{ok, bg, char, origin, extent} ; feed `char` + bg_path=`bg` to perception for the isolated read. Pure driver
(no asset writes); spawns + destroys its own capture rig, game world untouched.
"""
from __future__ import annotations

from pathlib import Path
import sys as _sys
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
from ue_mcp.ue_client import call as _bridge_call   # noqa: E402

_CAPTURE_TEMPLATE = r'''
import unreal, math
from pathlib import Path
OUT=Path(r"{out_dir}"); OUT.mkdir(parents=True, exist_ok=True)
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem); world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
sk=unreal.load_asset("{rig}"); mat=unreal.load_asset("{mat}")
if not sk: raise RuntimeError("rig not found: {rig}")
spawn=unreal.Vector(0,0,300)
probe=eas.spawn_actor_from_class(unreal.SkeletalMeshActor, spawn, unreal.Rotator(0,0,0))
pc=probe.skeletal_mesh_component; pc.set_skeletal_mesh_asset(sk) if hasattr(pc,"set_skeletal_mesh_asset") else pc.set_skeletal_mesh(sk)
origin, extent = probe.get_actor_bounds(False); eas.destroy_actor(probe)
half_h=max(extent.z,40.0); fov={fov}; dist=(half_h/math.tan(math.radians(fov*0.5)))*1.2
cam=unreal.Vector(origin.x, origin.y-dist, origin.z)
temp=[]
keyl=eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(origin.x-150,origin.y-150,origin.z+250), unreal.Rotator(-30,45,0))
try: keyl.directional_light_component.set_intensity(12.0)
except Exception: pass
temp.append(keyl)
fill=eas.spawn_actor_from_class(unreal.DirectionalLight, cam, unreal.Rotator(-8,90,0))   # FRONT FILL (camera dir)
try: fill.directional_light_component.set_intensity(16.0)
except Exception: pass
temp.append(fill)
sky=eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(origin.x,origin.y,origin.z+150))
try: sky.sky_light_component.set_intensity(2.5)
except Exception: pass
temp.append(sky)
rt=unreal.RenderingLibrary.create_render_target2d(world,{res},{res},unreal.TextureRenderTargetFormat.RTF_RGBA8)
cap=eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, unreal.MathLibrary.find_look_at_rotation(cam, origin))
cc=cap.capture_component2d; cc.set_editor_property("capture_source",unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
cc.set_editor_property("texture_target",rt); cc.set_editor_property("fov_angle",fov); cc.set_editor_property("capture_every_frame",False)
cc.capture_scene(); unreal.RenderingLibrary.export_render_target(world,rt,str(OUT),"{asset}_bg.png")   # empty BG
actor=eas.spawn_actor_from_class(unreal.SkeletalMeshActor, spawn, unreal.Rotator(0,0,0))
comp=actor.skeletal_mesh_component; comp.set_skeletal_mesh_asset(sk) if hasattr(comp,"set_skeletal_mesh_asset") else comp.set_skeletal_mesh(sk)
if mat:
    for i in range(max(1,comp.get_num_materials())): comp.set_material(i,mat)
face=unreal.MathLibrary.find_look_at_rotation(origin, cam); actor.set_actor_rotation(unreal.Rotator(0,0,face.yaw-90.0), False)
cc.capture_scene(); unreal.RenderingLibrary.export_render_target(world,rt,str(OUT),"{asset}.png")        # CHAR
for a in [cap,actor]+temp:
    try: eas.destroy_actor(a)
    except Exception: pass
result=str({{"origin":[round(origin.x,1),round(origin.y,1),round(origin.z,1)],"extent":[round(extent.x,1),round(extent.y,1),round(extent.z,1)]}})
'''


def hero_capture(rig_path: str, asset: str, out_dir: str, mat_path: str = "",
                 fov: float = 35.0, res: int = 900, timeout: float = 200.0) -> dict:
    """Capture a calibrated, subject-isolatable hero shot of `rig_path` via the live bridge. Returns
    {ok, bg, char, detail|error}. Use perception.analyze_image(char, bg_path=bg, ...) for the isolated read."""
    out = Path(out_dir).resolve()      # absolute: the exec runs in the EDITOR's cwd, not Dimwit's
    code = _CAPTURE_TEMPLATE.format(out_dir=str(out).replace("\\", "/"), rig=rig_path,
                                    mat=mat_path or "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material.pbr_material",
                                    asset=asset, fov=fov, res=res)
    r = _bridge_call("exec", {"code": code}, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error"), "trace": (r.get("trace") or "")[-500:]}
    return {"ok": True, "bg": str(out / f"{asset}_bg.png"), "char": str(out / f"{asset}.png"),
            "detail": r.get("result")}
