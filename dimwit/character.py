"""Dimwit character generation — a procedural WANEFALL armored-humanoid GREYBOX PROXY + headless render.

This is an HONEST proxy: it builds a recognizable armored-humanoid silhouette (legs/torso/pauldrons/arms/
helmet/chest-core/rifle/optional cape) at correct proportions in the WANEFALL palette, exports FBX/GLB,
and renders a 3-view turnaround to PNG via Blender headless (EEVEE). It is NOT a concept-art sculpt — it is
a blockout to validate silhouette + palette + readability and to build from in-engine.

Deps: Blender (external process) for build+render; trimesh/numpy for measurement; Pillow for the sheet.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .meshgen import blender_exe, _measure
import trimesh

# A character spec is a small dict: name, palette accent (teal|purple), bulk (0.8..1.3), cape (bool),
# helmet style, height_cm, accent emissive RGB.
_CHAR_SCRIPT = r'''
import bpy, json, sys, math, mathutils
A = sys.argv[sys.argv.index("--")+1:]
spec = json.loads(open(A[0], encoding="utf-8").read()); out = A[1]
H = float(spec.get("height_cm",205))/100.0
bulk = float(spec.get("bulk",1.0)); cape = bool(spec.get("cape",False))
accent = spec.get("accent_rgb",[0.0,0.7,0.85])
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)

def M(name, base, metal, rough, emis=None, estr=0.0):
    m = bpy.data.materials.new(name); m.use_nodes=True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(base[0],base[1],base[2],1)
    b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    if emis:
        b.inputs["Emission Color"].default_value=(emis[0],emis[1],emis[2],1)
        b.inputs["Emission Strength"].default_value=estr
    return m
ARMOR = M("M_WaneArmor",(0.045,0.05,0.062),0.78,0.42)
ARMOR2= M("M_WaneArmorLt",(0.10,0.11,0.13),0.65,0.5)
CORE  = M("M_WaneCore",(0.02,0.05,0.06),0.1,0.3, accent, 6.0)
ACC   = M("M_WaneAccent",(0.02,0.04,0.05),0.2,0.4, accent, 2.2)

def box(name, loc, size, mat, rot=(0,0,0), bevel=0.012):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o=bpy.context.active_object; o.name=name; o.scale=(size[0]/2,size[1]/2,size[2]/2)
    o.rotation_euler=(math.radians(rot[0]),math.radians(rot[1]),math.radians(rot[2]))
    mod=o.modifiers.new("bev","BEVEL"); mod.width=bevel; mod.segments=2
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth=True
    return o
def cyl(name, loc, r, depth, mat, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, vertices=12)
    o=bpy.context.active_object; o.name=name
    o.rotation_euler=(math.radians(rot[0]),math.radians(rot[1]),math.radians(rot[2]))
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth=True
    return o

yo = 0.26*bulk   # shoulder y-offset
parts=[]
# legs — segments OVERLAP at joints so nothing floats; armored plates on knees/shins/thighs
for s in (-1,1):
    yL = s*0.12
    parts += [
      box(f"boot{s}",(0.06, yL, 0.06),(0.24,0.16*bulk,0.12),ARMOR2),
      cyl(f"shin{s}",(0.0, yL, 0.30),0.085*bulk,0.50,ARMOR),
      box(f"shinplt{s}",(0.06, yL, 0.30),(0.10,0.15*bulk,0.34),ARMOR2),
      box(f"knee{s}",(0.05, yL, 0.52),(0.15,0.17*bulk,0.16),ARMOR2),
      cyl(f"thigh{s}",(0.0, yL, 0.74),0.11*bulk,0.50,ARMOR),
      box(f"thighplt{s}",(0.07, yL, 0.78),(0.10,0.18*bulk,0.30),ARMOR2),
    ]
# pelvis / torso — a continuous tapered core, wide armoured chest
parts += [
  box("pelvis",(0.0,0.0,0.96),(0.40*bulk,0.30*bulk,0.26),ARMOR),
  box("belt",(0.0,0.0,1.04),(0.42*bulk,0.32*bulk,0.07),ACC),
  box("abdomen",(0.0,0.0,1.20),(0.34*bulk,0.26*bulk,0.26),ARMOR),
  box("chest",(0.04,0.0,1.42),(0.54*bulk,0.34*bulk,0.34),ARMOR2),
  box("chestplt",(0.16,0.0,1.40),(0.20,0.30*bulk,0.40),ARMOR),
  box("back",(-0.10,0.0,1.40),(0.30*bulk,0.30*bulk,0.40),ARMOR),
]
# chest core (the glowing identity/weak point)
parts.append(box("core",(0.27,0.0,1.40),(0.07,0.13,0.18),CORE))
# shoulder yoke + big pauldrons + connected arms (hands meet the rifle line)
parts += [ box("yoke",(0.0,0.0,1.60),(0.40*bulk,0.62*bulk,0.16),ARMOR) ]
for s in (-1,1):
    yA = s*yo
    parts += [
      box(f"pauldron{s}",(0.0, s*(0.34*bulk), 1.58),(0.30,0.30*bulk,0.28),ARMOR2),
      cyl(f"uarm{s}",(0.02, yA, 1.34),0.085*bulk,0.42,ARMOR),
      box(f"elbow{s}",(0.06, yA, 1.14),(0.13,0.15,0.15),ARMOR2),
      cyl(f"farm{s}",(0.14, yA, 0.98),0.07*bulk,0.40,ARMOR,(28,0,0)),
    ]
# hands placed ON the rifle (both forward, near body centre)
parts += [ box("handR",(0.22,-0.06,0.96),(0.11,0.10,0.16),ARMOR2),
           box("handL",(0.40,-0.02,1.18),(0.11,0.10,0.15),ARMOR2) ]
# short neck + BIG angular alien helmet sitting on the yoke + swept crest + glowing visor
parts += [
  cyl("neck",(0.0,0.0,1.66),0.07,0.10,ARMOR),
  box("head",(0.02,0.0,1.80),(0.24,0.26,0.34),ARMOR2),
  box("jaw",(0.10,0.0,1.70),(0.16,0.20,0.14),ARMOR),
  box("crest",(-0.10,0.0,1.96),(0.30,0.07,0.22),ARMOR,(34,0,0)),
  box("visor",(0.16,0.0,1.82),(0.05,0.20,0.09),CORE),
]
# rifle held diagonally across the chest (both hands on it)
rifle=[
  box("r_body",(0.30,-0.04,1.06),(0.62,0.07,0.12),ARMOR,(0,30,0)),
  box("r_barrel",(0.54,-0.04,1.22),(0.46,0.04,0.04),ARMOR2,(0,30,0)),
  box("r_mag",(0.24,-0.04,0.94),(0.07,0.06,0.20),ACC,(0,30,0)),
  box("r_stock",(0.08,-0.04,0.92),(0.22,0.06,0.11),ARMOR,(0,30,0)),
  box("r_scope",(0.36,-0.04,1.16),(0.14,0.05,0.06),ARMOR2,(0,30,0)),
]
parts += rifle
# optional flowing back cape
if cape:
    parts.append(box("cape",(-0.20,0.0,1.05),(0.06,0.54*bulk,1.05),ARMOR,(0,-6,0),bevel=0.03))

# join all into one mesh for export
bpy.ops.object.select_all(action='DESELECT')
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active=parts[0]
bpy.ops.object.join()
char=bpy.context.active_object; char.name="SM_WaneChar_"+spec.get("name","Char")

# export
bpy.ops.export_scene.fbx(filepath=out+"/char.fbx", use_selection=True)
try: bpy.ops.export_scene.gltf(filepath=out+"/char.glb", use_selection=True, export_format='GLB')
except Exception as e: print("glb skip",e)

# ---- render a 3-view turnaround (EEVEE) on a dark backdrop with a key+rim+fill rig ----
scene=bpy.context.scene
# Cycles CPU renders reliably in --background headless (EEVEE needs a GL context and silently writes nothing).
scene.render.engine='CYCLES'
try:
    scene.cycles.device='CPU'; scene.cycles.samples=48; scene.cycles.use_denoising=True
except Exception as e: print("cycles cfg",e)
scene.render.resolution_x=560; scene.render.resolution_y=820; scene.render.film_transparent=False
world=bpy.data.worlds['World'] if 'World' in bpy.data.worlds else bpy.data.worlds.new('World')
scene.world=world; world.use_nodes=True
world.node_tree.nodes["Background"].inputs[0].default_value=(0.008,0.009,0.012,1)
world.node_tree.nodes["Background"].inputs[1].default_value=1.0
# dark backdrop wall + floor (moody WANEFALL studio)
bpy.ops.mesh.primitive_plane_add(size=16, location=(-2.0,0,1.4)); bd=bpy.context.active_object
bd.rotation_euler=(0,math.radians(90),0); bd.data.materials.append(M("M_BD",(0.012,0.014,0.02),0,0.85))
bpy.ops.mesh.primitive_plane_add(size=16, location=(0,0,0)); fl=bpy.context.active_object
fl.data.materials.append(M("M_FL",(0.014,0.016,0.022),0,0.7))
# lights: bright cool KEY, strong teal RIM for edge separation (un-blob the dark armor), dim fill
def light(name,loc,energy,color,size=2.0):
    ld=bpy.data.lights.new(name,'AREA'); ld.energy=energy; ld.color=color; ld.size=size
    lo=bpy.data.objects.new(name,ld); lo.location=loc; scene.collection.objects.link(lo)
    d=mathutils.Vector((0,0,1.1))-mathutils.Vector(loc); lo.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    return lo
light("key",(2.6,-2.2,3.2),1100,(1.0,0.97,0.92),2.5)
light("rim",(-1.8,2.0,2.4),900,(0.35,0.8,1.0),1.6)
light("rim2",(-1.6,-2.2,2.2),520,(0.45,0.85,1.0),1.6)
light("fill",(2.4,2.4,1.0),70,(0.8,0.88,1.0),3.0)
# camera — full body, slight low angle for a heroic read
cam_d=bpy.data.cameras.new("cam"); cam=bpy.data.objects.new("cam",cam_d); scene.collection.objects.link(cam)
scene.camera=cam; cam_d.lens=58
views={"front":(4.6,0.0,1.05),"threequarter":(3.9,-2.8,1.15),"side":(0.2,-4.8,1.05)}
look=mathutils.Vector((0,0,1.0))
for vn,loc in views.items():
    cam.location=loc
    d=look-mathutils.Vector(loc); cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=out+f"/render_{vn}.png"; bpy.ops.render.render(write_still=True)
open(out+"/char_done.json","w").write(json.dumps({"ok":True,"name":spec.get("name"),"views":list(views)}))
print("CHAR_OK")
'''


_RENDER_MESH_SCRIPT = r'''
import bpy, json, sys, math, mathutils
A = sys.argv[sys.argv.index("--")+1:]
mesh_path=A[0]; out=A[1]; mode=A[2] if len(A)>2 else "wanefall"; rotx=float(A[3]) if len(A)>3 else 90.0
unmirror=int(A[4]) if len(A)>4 else 0
flip=int(A[5]) if len(A)>5 else 0
proj_image=A[6] if len(A)>6 else ""
mesh_dir=mesh_path.rsplit("/",1)[0].rsplit("\\",1)[0] if ("/" in mesh_path or "\\" in mesh_path) else "."
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
ext=mesh_path.lower().rsplit(".",1)[-1]
if ext=="obj":
    try: bpy.ops.wm.obj_import(filepath=mesh_path)
    except Exception: bpy.ops.import_scene.obj(filepath=mesh_path)
elif ext=="glb" or ext=="gltf": bpy.ops.import_scene.gltf(filepath=mesh_path)
elif ext=="fbx": bpy.ops.import_scene.fbx(filepath=mesh_path)
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active=objs[0]
if len(objs)>1: bpy.ops.object.join()
ob=bpy.context.view_layer.objects.active
# AUTO-ORIENT: longest bbox axis -> vertical (a standing humanoid is tallest along its height), then use
# centre-of-mass to fix upside-down (a humanoid's mass sits LOW: legs+torso heavier than the head).
if rotx < 0:
    d=ob.dimensions; axis=max(range(3), key=lambda i:d[i])
    if axis==0: ob.rotation_euler=(0, math.radians(90), 0)
    elif axis==1: ob.rotation_euler=(math.radians(-90), 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    zs=[(ob.matrix_world @ v.co).z for v in ob.data.vertices]
    zc=(min(zs)+max(zs))/2.0; zmean=sum(zs)/len(zs)
    if zmean > zc:  # top-heavy => upside down => flip 180 about X
        ob.rotation_euler=(math.radians(180),0,0); bpy.ops.object.transform_apply(rotation=True)
else:
    ob.rotation_euler=(math.radians(rotx),0,0); bpy.ops.object.transform_apply(rotation=True)
if flip:  # explicit 180 flip about X (head-up) — reliable operator control vs the centroid heuristic
    ob.rotation_euler=(math.radians(180),0,0); bpy.ops.object.transform_apply(rotation=True)
    # re-center on floor after flip
    bb=[ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
    zmn=min(v.z for v in bb); ob.location.z-=zmn; bpy.ops.object.transform_apply(location=True)
if unmirror:  # negate left-right axis + flip normals so handedness matches the concept (not inside-out)
    ob.scale.x=-1.0; bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.flip_normals(); bpy.ops.object.mode_set(mode='OBJECT')
for p in ob.data.polygons: p.use_smooth=True
bb=[ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
mn=mathutils.Vector((min(v.x for v in bb),min(v.y for v in bb),min(v.z for v in bb)))
mx=mathutils.Vector((max(v.x for v in bb),max(v.y for v in bb),max(v.z for v in bb)))
size=mx-mn; h=max(size.z,1e-4); s=2.0/h
ob.scale=(s,s,s); bpy.ops.object.transform_apply(scale=True)
bb=[ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
mn=mathutils.Vector((min(v.x for v in bb),min(v.y for v in bb),min(v.z for v in bb)))
cx=(min(v.x for v in bb)+max(v.x for v in bb))/2; cy=(min(v.y for v in bb)+max(v.y for v in bb))/2
ob.location=(ob.location.x-cx, ob.location.y-cy, ob.location.z-mn.z)
bpy.ops.object.transform_apply(location=True)
def M(name,base,metal,rough,emis=None,estr=0.0):
    m=bpy.data.materials.new(name); m.use_nodes=True; b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(base[0],base[1],base[2],1); b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    if emis: b.inputs["Emission Color"].default_value=(emis[0],emis[1],emis[2],1); b.inputs["Emission Strength"].default_value=estr
    return m
if mode=="wanefall":
    ob.data.materials.clear(); ob.data.materials.append(M("M_WaneArmor",(0.05,0.055,0.07),0.7,0.45))
elif mode=="clay":
    ob.data.materials.clear(); ob.data.materials.append(M("M_Clay",(0.55,0.56,0.585),0.0,0.62))  # neutral matte -> shows pure geometry detail
elif mode=="atlas":
    # load the baked UV texture atlas (texture.png next to the mesh) onto the imported UVs
    import os
    texp=None
    for cand in ("texture.png","mesh_texture.png"):
        p=os.path.join(mesh_dir,cand)
        if os.path.exists(p): texp=p; break
    ob.data.materials.clear()
    mt=bpy.data.materials.new("M_Atlas"); mt.use_nodes=True; nt=mt.node_tree; bsdf=nt.nodes.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value=0.25; bsdf.inputs["Roughness"].default_value=0.5
    if texp:
        tx=nt.nodes.new("ShaderNodeTexImage"); tx.image=bpy.data.images.load(texp)
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(mt)
elif mode in ("textured","wanefall_tint"):
    # AUTO-COLOR: use the per-vertex RGB TripoSR projected from the concept image.
    ob.data.materials.clear()
    mt=bpy.data.materials.new("M_AutoColor"); mt.use_nodes=True; nt=mt.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    vc=nt.nodes.new("ShaderNodeVertexColor")
    if ob.data.color_attributes: vc.layer_name=ob.data.color_attributes[0].name
    bsdf.inputs["Metallic"].default_value=0.25; bsdf.inputs["Roughness"].default_value=0.5
    if mode=="textured":
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    else:  # wanefall_tint: darken the armor + push teal/cyan accents brighter (emissive), per the WANEFALL style law
        # darken base toward WANEFALL armor
        gamma=nt.nodes.new("ShaderNodeGamma"); gamma.inputs["Gamma"].default_value=1.9
        nt.links.new(vc.outputs["Color"], gamma.inputs["Color"])
        mul=nt.nodes.new("ShaderNodeMixRGB"); mul.blend_type='MULTIPLY'; mul.inputs["Fac"].default_value=1.0
        mul.inputs["Color2"].default_value=(0.55,0.62,0.72,1)
        nt.links.new(gamma.outputs["Color"], mul.inputs["Color1"])
        nt.links.new(mul.outputs["Color"], bsdf.inputs["Base Color"])
        # detect teal/cyan accent pixels (high B+G, low R) -> drive emission so the Wane energy glows
        sep=nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(vc.outputs["Color"], sep.inputs["Color"])
        bg=nt.nodes.new("ShaderNodeMath"); bg.operation='ADD'
        nt.links.new(sep.outputs["Green"], bg.inputs[0]); nt.links.new(sep.outputs["Blue"], bg.inputs[1])
        sub=nt.nodes.new("ShaderNodeMath"); sub.operation='SUBTRACT'
        nt.links.new(bg.outputs[0], sub.inputs[0]); nt.links.new(sep.outputs["Red"], sub.inputs[1])
        sub2=nt.nodes.new("ShaderNodeMath"); sub2.operation='MULTIPLY'; sub2.inputs[1].default_value=2.2
        nt.links.new(sub.outputs[0], sub2.inputs[0])
        teal=nt.nodes.new("ShaderNodeRGB"); teal.outputs[0].default_value=(0.0,0.75,0.95,1)
        nt.links.new(teal.outputs[0], bsdf.inputs["Emission Color"])
        nt.links.new(sub2.outputs[0], bsdf.inputs["Emission Strength"])
    ob.data.materials.append(mt)
elif mode=="projected":
    # ACCURACY BOOST: planar-project the CRISP concept cutout onto the FRONT-facing surface (Generated
    # bbox coords -> world Y/Z), so seams/face/colour read razor-sharp on the soft mesh. Sides/back keep
    # the recon vertex colours. Front of the figure faces +X (the 'front' camera sits on +X).
    import os
    ob.data.materials.clear()
    mt=bpy.data.materials.new("M_Proj"); mt.use_nodes=True; nt=mt.node_tree; bsdf=nt.nodes.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value=0.3; bsdf.inputs["Roughness"].default_value=0.5
    vc=nt.nodes.new("ShaderNodeVertexColor")
    if ob.data.color_attributes: vc.layer_name=ob.data.color_attributes[0].name
    if proj_image and os.path.exists(proj_image):
        tc=nt.nodes.new("ShaderNodeTexCoord")
        sep=nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        comb=nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(sep.outputs["Y"], comb.inputs["X"]); nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
        img=nt.nodes.new("ShaderNodeTexImage"); img.image=bpy.data.images.load(proj_image); img.extension='CLIP'
        nt.links.new(comb.outputs[0], img.inputs["Vector"])
        geo=nt.nodes.new("ShaderNodeNewGeometry"); nsep=nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], nsep.inputs[0])
        face=nt.nodes.new("ShaderNodeMath"); face.operation='MULTIPLY'; face.inputs[1].default_value=3.0
        nt.links.new(nsep.outputs["X"], face.inputs[0])
        fc=nt.nodes.new("ShaderNodeClamp"); nt.links.new(face.outputs[0], fc.inputs["Value"])
        fac=nt.nodes.new("ShaderNodeMath"); fac.operation='MULTIPLY'
        nt.links.new(fc.outputs[0], fac.inputs[0]); nt.links.new(img.outputs["Alpha"], fac.inputs[1])
        mix=nt.nodes.new("ShaderNodeMixRGB")
        nt.links.new(fac.outputs[0], mix.inputs["Fac"])
        nt.links.new(vc.outputs["Color"], mix.inputs["Color1"]); nt.links.new(img.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(mt)
if mode!="raw":
    for p in ob.data.polygons: p.use_smooth=True
# render rig (same studio as generate_character)
scene=bpy.context.scene; scene.render.engine='CYCLES'
try: scene.cycles.device='CPU'; scene.cycles.samples=40; scene.cycles.use_denoising=True
except Exception: pass
scene.render.resolution_x=560; scene.render.resolution_y=820
w=bpy.data.worlds['World']; scene.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.008,0.009,0.012,1)
bpy.ops.mesh.primitive_plane_add(size=16, location=(-2.0,0,1.4)); bd=bpy.context.active_object
bd.rotation_euler=(0,math.radians(90),0); bd.data.materials.append(M("M_BD",(0.012,0.014,0.02),0,0.85))
bpy.ops.mesh.primitive_plane_add(size=16, location=(0,0,0)); fl=bpy.context.active_object; fl.data.materials.append(M("M_FL",(0.014,0.016,0.022),0,0.7))
def light(n,loc,e,c,sz=2.0):
    ld=bpy.data.lights.new(n,'AREA'); ld.energy=e; ld.color=c; ld.size=sz
    lo=bpy.data.objects.new(n,ld); lo.location=loc; scene.collection.objects.link(lo)
    d=mathutils.Vector((0,0,1.0))-mathutils.Vector(loc); lo.rotation_euler=d.to_track_quat('-Z','Y').to_euler(); return lo
light("key",(2.6,-2.2,3.2),1300,(1.0,0.98,0.95),2.5); light("rim",(-1.8,2.0,2.4),800,(0.4,0.82,1.0),1.6)
light("rim2",(-1.6,-2.2,2.2),480,(0.5,0.86,1.0),1.6); light("fill",(2.4,2.4,1.2),260,(0.9,0.93,1.0),3.4)
light("upfill",(0.5,-1.5,0.2),120,(0.85,0.9,1.0),3.0)   # soft up-fill so lower-body seams read
cam_d=bpy.data.cameras.new("cam"); cam=bpy.data.objects.new("cam",cam_d); scene.collection.objects.link(cam); scene.camera=cam; cam_d.lens=58
look=mathutils.Vector((0,0,1.0))
for vn,loc in {"front":(4.6,0,1.05),"threequarter":(3.9,-2.8,1.15),"side":(0.2,-4.8,1.05)}.items():
    cam.location=loc; d=look-mathutils.Vector(loc); cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=out+f"/mview_{vn}.png"; bpy.ops.render.render(write_still=True)
open(out+"/render_done.json","w").write(json.dumps({"ok":True,"mode":mode}))
print("RENDER_OK")
'''


def render_mesh(mesh_path: str, out_dir: Path, mode: str = "wanefall", rot_x: float = -1.0,
                unmirror: bool = False, flip: bool = False, timeout: int = 240, proj_image: str = "") -> dict:
    """Render any imported mesh (neural OBJ/GLB) into a WANEFALL 3-view turnaround.
    mode: 'raw' | 'wanefall' (flat dark armor) | 'textured' (concept vertex colors) | 'wanefall_tint'
          (concept colors pushed to the WANEFALL palette: darker armor + glowing teal accents).
    rot_x < 0 => auto-orient (longest axis up + centroid-flip); unmirror => negate handedness."""
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    exe = blender_exe()
    if not exe:
        return {"ok": False, "error": "Blender not found"}
    scr = out / "_rendermesh.py"; scr.write_text(_RENDER_MESH_SCRIPT, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(scr), "--", str(Path(mesh_path).resolve()), str(out), mode, str(rot_x), str(int(unmirror)), str(int(flip)), (str(Path(proj_image).resolve()) if proj_image else "")]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    ok = "RENDER_OK" in r.stdout
    return {"ok": ok, "mode": mode, "renders": [str(out / f"mview_{v}.png") for v in ("front", "threequarter", "side") if (out / f"mview_{v}.png").exists()],
            "stderr_tail": r.stderr.strip().splitlines()[-4:] if r.stderr else []}


def generate_character(spec: dict, out_dir: Path, timeout: int = 300) -> dict:
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)   # absolute so Blender writes here, not its CWD
    exe = blender_exe()
    if not exe:
        return {"ok": False, "error": "Blender not found"}
    sp = out / "_charspec.json"; sp.write_text(json.dumps(spec), encoding="utf-8")
    scr = out / "_charbuild.py"; scr.write_text(_CHAR_SCRIPT, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(scr), "--", str(sp), str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    ok = "CHAR_OK" in r.stdout
    meta = {"ok": ok, "name": spec.get("name"), "backend": "blender_eevee", "exe": exe,
            "renders": [str(out / f"render_{v}.png") for v in ("front", "threequarter", "side") if (out / f"render_{v}.png").exists()],
            "fbx": str(out / "char.fbx") if (out / "char.fbx").exists() else None,
            "glb": str(out / "char.glb") if (out / "char.glb").exists() else None,
            "stdout_tail": r.stdout.strip().splitlines()[-3:] if r.stdout else [],
            "stderr_tail": r.stderr.strip().splitlines()[-3:] if r.stderr else []}
    if meta["glb"]:
        try:
            meta["measured"] = _measure(trimesh.load(meta["glb"], force="mesh"))
        except Exception as e:
            meta["measure_error"] = str(e)
    (out / "char_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    import sys
    spec = {"name": "Vorlax", "accent_rgb": [0.0, 0.7, 0.9], "bulk": 1.0, "cape": False, "height_cm": 205}
    print(json.dumps(generate_character(spec, Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/char_vorlax")), indent=2))
