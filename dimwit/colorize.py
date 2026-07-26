"""Dimwit autonomous WANE-energy colorize — turns flat projected vertex color into a full PBR + EMISSIVE
material, in-shader, with zero hand-painting:

  * Base color  = the concept color, darkened toward WANEFALL armor.
  * Metallic    = auto-high where the surface is DARK + DESATURATED (armor plate) -> real metal response.
  * Roughness   = derived from value.
  * EMISSION    = auto-detected Wane energy: teal/cyan accents glow their own colour; red/orange weak-points
                  glow hot. Driven entirely by the vertex colour via math nodes -> no masks to author.
  * Bloom       = compositor Glare (fog glow) so the emission is awe-striking.
  * DYNAMIC     = an optional turntable with the Wane energy PULSING (animated emission strength).

Renders hero stills (front/3q/side/back) + a turntable GIF. Cycles for reliable headless bloom.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .meshgen import blender_exe

_SHOWCASE = r'''
import bpy, sys, math, mathutils, json
A=sys.argv[sys.argv.index("--")+1:]
mesh=A[0]; out=A[1]; flip=int(A[2]) if len(A)>2 else 1; tframes=int(A[3]) if len(A)>3 else 32
glow=float(A[4]) if len(A)>4 else 7.0; edge=float(A[5]) if len(A)>5 else 6.0
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
ext=mesh.lower().rsplit(".",1)[-1]
if ext=="obj":
    try: bpy.ops.wm.obj_import(filepath=mesh)
    except Exception: bpy.ops.import_scene.obj(filepath=mesh)
elif ext in ("glb","gltf"): bpy.ops.import_scene.gltf(filepath=mesh)
else: bpy.ops.import_scene.fbx(filepath=mesh)
ms=[o for o in bpy.context.scene.objects if o.type=='MESH']
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active=ms[0]
if len(ms)>1: bpy.ops.object.join()
ob=bpy.context.view_layer.objects.active
if flip:
    ob.rotation_euler=(math.radians(180),0,0); bpy.ops.object.transform_apply(rotation=True)
# center on floor, scale to ~2m
bb=[ob.matrix_world@mathutils.Vector(c) for c in ob.bound_box]
mn=mathutils.Vector((min(v.x for v in bb),min(v.y for v in bb),min(v.z for v in bb)))
mx=mathutils.Vector((max(v.x for v in bb),max(v.y for v in bb),max(v.z for v in bb)))
h=max(mx.z-mn.z,1e-4); s=2.0/h; ob.scale=(s,s,s); bpy.ops.object.transform_apply(scale=True)
bb=[ob.matrix_world@mathutils.Vector(c) for c in ob.bound_box]
cx=(min(v.x for v in bb)+max(v.x for v in bb))/2; cy=(min(v.y for v in bb)+max(v.y for v in bb))/2; zmn=min(v.z for v in bb)
ob.location=(ob.location.x-cx,ob.location.y-cy,ob.location.z-zmn); bpy.ops.object.transform_apply(location=True)
for p in ob.data.polygons: p.use_smooth=True

# ---------------- AUTONOMOUS WANE PBR + EMISSIVE MATERIAL (in-shader, from vertex colour) ----------------
ob.data.materials.clear()
mat=bpy.data.materials.new("M_WaneAuto"); mat.use_nodes=True; nt=mat.node_tree; n=nt.nodes; lk=nt.links
bsdf=n.get("Principled BSDF")
vc=n.new("ShaderNodeVertexColor")
if ob.data.color_attributes: vc.layer_name=ob.data.color_attributes[0].name
sepr=n.new("ShaderNodeSeparateColor"); sepr.mode='RGB'; lk.new(vc.outputs["Color"], sepr.inputs["Color"])
seph=n.new("ShaderNodeSeparateColor"); seph.mode='HSV'; lk.new(vc.outputs["Color"], seph.inputs["Color"])
R=sepr.outputs["Red"]; G=sepr.outputs["Green"]; B=sepr.outputs["Blue"]
S=seph.outputs["Green"]; V=seph.outputs["Blue"]
def MA(op,a,b=0.5,clamp=False):
    m=n.new("ShaderNodeMath"); m.operation=op; m.use_clamp=clamp
    if hasattr(a,'default_value') or not isinstance(a,(int,float)): lk.new(a,m.inputs[0])
    else: m.inputs[0].default_value=a
    if isinstance(b,(int,float)): m.inputs[1].default_value=b
    else: lk.new(b,m.inputs[1])
    return m.outputs[0]
# teal/cyan Wane energy = (G+B)/2 - 0.85*R  (positive => glowing teal accent)
gb=MA('ADD',G,B); gbh=MA('MULTIPLY',gb,0.5); teal=MA('SUBTRACT',gbh,MA('MULTIPLY',R,0.85)); teal=MA('MULTIPLY',teal,glow,clamp=True)
# red/orange weak-point = R - (G+B)/2
red=MA('SUBTRACT',R,gbh); red=MA('MULTIPLY',red,glow*1.4,clamp=True)
emit_strength=MA('ADD',teal,red)
# PROCEDURAL WANE ENERGY-LINES: ambient-occlusion crevice mask -> the recessed armour SEAMS glow (Tron look)
ao=n.new("ShaderNodeAmbientOcclusion"); ao.samples=16; ao.only_local=True
try: ao.inputs["Distance"].default_value=0.05
except Exception: pass
crev=MA('SUBTRACT',1.0,ao.outputs["AO"]); crev=MA('POWER',crev,3.0); crev=MA('MULTIPLY',crev,edge,clamp=True)
# also faint CONVEX-EDGE rim from pointiness (plate edges catch energy)
geo=n.new("ShaderNodeNewGeometry"); pt=MA('SUBTRACT',geo.outputs["Pointiness"],0.52); pt=MA('MULTIPLY',MA('MAXIMUM',pt,0.0),edge*2.0,clamp=True)
emit_strength=MA('ADD',MA('ADD',emit_strength,crev),pt)
pulse=n.new("ShaderNodeValue"); pulse.outputs[0].default_value=1.0; pulse.label="PULSE"
emit_strength=MA('MULTIPLY',emit_strength,pulse.outputs[0])
# emission COLOUR: vivid WANE teal vs hot red, picked by which accent dominates -> energy glows pure, not muddy
tcol=n.new("ShaderNodeRGB"); tcol.outputs[0].default_value=(0.0,0.85,1.05,1)
rcol=n.new("ShaderNodeRGB"); rcol.outputs[0].default_value=(1.3,0.12,0.0,1)
denom=MA('ADD',MA('ADD',teal,red),0.0015); fac=MA('DIVIDE',red,denom,clamp=True)
emix=n.new("ShaderNodeMixRGB"); lk.new(tcol.outputs[0],emix.inputs["Color1"]); lk.new(rcol.outputs[0],emix.inputs["Color2"]); lk.new(fac,emix.inputs["Fac"])
lk.new(emix.outputs["Color"], bsdf.inputs["Emission Color"]); lk.new(emit_strength, bsdf.inputs["Emission Strength"])
# metallic = dark + desaturated -> armour plate, CAPPED (so it isn't a black mirror)
invS=MA('SUBTRACT',1.0,S); invV=MA('SUBTRACT',1.0,MA('MULTIPLY',V,0.55)); metal=MA('MULTIPLY',invS,invV)
metal=MA('MINIMUM',MA('MULTIPLY',metal,1.1,clamp=True),0.55)
lk.new(metal, bsdf.inputs["Metallic"])
# base colour: keep the concept colour, gently brighten (recon colours are dark) + slight teal cast
bright=n.new("ShaderNodeGamma"); bright.inputs["Gamma"].default_value=0.8; lk.new(vc.outputs["Color"], bright.inputs["Color"])
lk.new(bright.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value=0.4
ob.data.materials.append(mat)

# ---------------- studio + bloom + dramatic lighting ----------------
scene=bpy.context.scene; scene.render.engine='CYCLES'
try: scene.cycles.device='CPU'; scene.cycles.use_denoising=True
except Exception: pass
w=bpy.data.worlds['World']; scene.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.006,0.007,0.01,1)
def M2(nm,base,metal,rough):
    m=bpy.data.materials.new(nm); m.use_nodes=True; b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(base[0],base[1],base[2],1); b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    return m
bpy.ops.mesh.primitive_plane_add(size=22, location=(-6.0,0,1.5)); bd=bpy.context.active_object
bd.rotation_euler=(0,math.radians(90),0); bd.data.materials.append(M2("BD",(0.01,0.012,0.018),0,0.9))
bpy.ops.mesh.primitive_plane_add(size=18, location=(0,0,0)); fl=bpy.context.active_object; fl.data.materials.append(M2("FL",(0.012,0.014,0.02),0.1,0.6))
def light(nm,loc,e,c,sz=2.0):
    ld=bpy.data.lights.new(nm,'AREA'); ld.energy=e; ld.color=c; ld.size=sz
    lo=bpy.data.objects.new(nm,ld); lo.location=loc; scene.collection.objects.link(lo)
    d=mathutils.Vector((0,0,1.0))-mathutils.Vector(loc); lo.rotation_euler=d.to_track_quat('-Z','Y').to_euler(); return lo
light("key",(2.8,-2.4,3.4),1900,(1.0,0.97,0.92),2.2)
light("rimT",(-2.0,2.2,2.6),1500,(0.2,0.8,1.0),1.4)   # strong teal rim = Wane energy edge
light("rimB",(-1.8,-2.4,2.0),900,(0.3,0.85,1.0),1.4)
light("fill",(2.6,2.6,1.2),140,(0.8,0.88,1.0),3.2)
light("back",(-3.2,0,2.6),700,(0.85,0.92,1.0),2.0)
# (bloom/glow halo is applied in post via PIL on the rendered frames — reliable across Blender versions)
cam_d=bpy.data.cameras.new("cam"); cam=bpy.data.objects.new("cam",cam_d); scene.collection.objects.link(cam); scene.camera=cam; cam_d.lens=60
look=mathutils.Vector((0,0,1.0))
def aim(loc): cam.location=loc; d=look-mathutils.Vector(loc); cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()

# ---- hero stills (high quality) ----
scene.render.resolution_x=620; scene.render.resolution_y=900
try: scene.cycles.samples=110
except Exception: pass
for vn,loc in {"front":(4.7,0,1.05),"threequarter":(4.0,-2.9,1.18),"side":(0.2,-4.9,1.05),"back":(-4.7,0.3,1.05)}.items():
    aim(loc); scene.render.filepath=out+f"/hero_{vn}.png"; bpy.ops.render.render(write_still=True)

# ---- DYNAMIC turntable (object rotates, Wane energy pulses) ----
scene.render.resolution_x=420; scene.render.resolution_y=600
try: scene.cycles.samples=42
except Exception: pass
aim((4.6,0,1.05))
import os; os.makedirs(out+"/tt", exist_ok=True)
for i in range(tframes):
    ang=2*math.pi*i/tframes
    ob.rotation_euler=(0,0,ang)
    pulse.outputs[0].default_value=0.6+0.55*(0.5+0.5*math.sin(ang*2.0))   # pulse the glow
    scene.render.filepath=out+f"/tt/f{i:03d}.png"; bpy.ops.render.render(write_still=True)
open(out+"/showcase_done.json","w").write(json.dumps({"ok":True,"turntable_frames":tframes}))
print("SHOWCASE_OK frames",tframes)
'''


def wane_showcase(mesh_path: str, out_dir: Path, flip: bool = True, turntable_frames: int = 32,
                  glow: float = 7.0, edge: float = 6.0, timeout: int = 900) -> dict:
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    exe = blender_exe()
    if not exe:
        return {"ok": False, "error": "Blender not found"}
    scr = out / "_showcase.py"; scr.write_text(_SHOWCASE, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(scr), "--", str(Path(mesh_path).resolve()), str(out),
           str(int(flip)), str(turntable_frames), str(glow), str(edge)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    ok = "SHOWCASE_OK" in r.stdout
    return {"ok": ok, "hero": [str(out / f"hero_{v}.png") for v in ("front", "threequarter", "side", "back") if (out / f"hero_{v}.png").exists()],
            "turntable_dir": str(out / "tt"),
            "stderr_tail": r.stderr.strip().splitlines()[-4:] if r.stderr else []}


if __name__ == "__main__":
    import sys
    print(json.dumps(wane_showcase(sys.argv[1], Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/showcase")), indent=2))
