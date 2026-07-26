"""Dimwit mesh refine — turn a raw neural mesh into a cleaner, smoother, game-budget asset.

polish_mesh: import -> weld/fill/recalc -> volume-preserving Laplacian de-lump -> decimate to a tri budget
-> shade-smooth -> export OBJ (keeps the baked UV texture) + copy the atlas. This removes the "melted lump"
look while keeping the silhouette + the texture, and brings the poly count into a usable range.

Heavier true-retopo (voxel remesh + selected-to-active texture re-bake) is a separate, optional stage.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .meshgen import blender_exe

_POLISH = r'''
import bpy, sys, math, mathutils
A=sys.argv[sys.argv.index("--")+1:]
mesh=A[0]; out=A[1]; target=int(A[2]) if len(A)>2 else 30000; delump=float(A[3]) if len(A)>3 else 1.0
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
tris0=len(ob.data.polygons)
# cleanup: weld, fill holes, recalc normals outward
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0008)
bpy.ops.mesh.fill_holes(sides=12)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
# de-lump: volume-preserving Laplacian smooth (kills the melted noise, keeps the silhouette)
ls=ob.modifiers.new("laplace","LAPLACIANSMOOTH")
ls.iterations=max(1,int(8*delump)); ls.lambda_factor=12.0*delump; ls.use_volume_preserve=True
bpy.ops.object.modifier_apply(modifier=ls.name)
# decimate to budget
if tris0>target:
    dc=ob.modifiers.new("dec","DECIMATE"); dc.decimate_type='COLLAPSE'; dc.ratio=max(0.02,target/tris0)
    bpy.ops.object.modifier_apply(modifier=dc.name)
for p in ob.data.polygons: p.use_smooth=True
tris1=len(ob.data.polygons)
# export cleaned OBJ (keeps UVs -> the baked atlas still maps)
try: bpy.ops.wm.obj_export(filepath=out+"/clean.obj", export_materials=True, export_uv=True, export_normals=True)
except Exception: bpy.ops.export_scene.obj(filepath=out+"/clean.obj")
open(out+"/polish_done.json","w").write(json.dumps({"ok":True,"tris_in":tris0,"tris_out":tris1}) if False else __import__("json").dumps({"ok":True,"tris_in":tris0,"tris_out":tris1}))
print("POLISH_OK tris_in",tris0,"tris_out",tris1)
'''


def polish_mesh(mesh_path: str, out_dir: Path, target_tris: int = 30000, delump: float = 1.0, timeout: int = 300) -> dict:
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    exe = blender_exe()
    if not exe:
        return {"ok": False, "error": "Blender not found"}
    scr = out / "_polish.py"; scr.write_text(_POLISH, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(scr), "--", str(Path(mesh_path).resolve()), str(out), str(target_tris), str(delump)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    ok = "POLISH_OK" in r.stdout
    # carry the baked texture next to the cleaned mesh so 'atlas' rendering still works
    src_tex = Path(mesh_path).resolve().parent / "texture.png"
    if src_tex.exists():
        shutil.copyfile(src_tex, out / "texture.png")
    info = {"ok": ok, "clean_obj": str(out / "clean.obj") if (out / "clean.obj").exists() else None,
            "stdout_tail": r.stdout.strip().splitlines()[-2:] if r.stdout else [],
            "stderr_tail": r.stderr.strip().splitlines()[-3:] if r.stderr else []}
    return info


_FINALIZE = r'''
import bpy, sys, math, mathutils, json, os
A=sys.argv[sys.argv.index("--")+1:]
mesh=A[0]; out=A[1]; target=int(A[2]) if len(A)>2 else 30000; texres=int(A[3]) if len(A)>3 else 2048
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
# import high-poly recon (vertex colors)
try: bpy.ops.wm.obj_import(filepath=mesh)
except Exception: bpy.ops.import_scene.obj(filepath=mesh)
ms=[o for o in bpy.context.scene.objects if o.type=='MESH']
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active=ms[0]
if len(ms)>1: bpy.ops.object.join()
src=bpy.context.view_layer.objects.active; src.name="HI"
# orient head-up: rot_x=0 keeps Y-up import; flip 180 about X (InstantMesh comes upside down)
src.rotation_euler=(math.radians(180),0,0); bpy.ops.object.transform_apply(rotation=True)
bb=[src.matrix_world@mathutils.Vector(c) for c in src.bound_box]; zmn=min(v.z for v in bb)
src.location.z-=zmn; bpy.ops.object.transform_apply(location=True)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False); bpy.ops.object.mode_set(mode='OBJECT')
hi_tris=len(src.data.polygons)
# --- RETOPO: duplicate -> voxel remesh (clean watertight) -> decimate to budget ---
bpy.ops.object.select_all(action='DESELECT'); src.select_set(True); bpy.context.view_layer.objects.active=src
bpy.ops.object.duplicate(); tgt=bpy.context.view_layer.objects.active; tgt.name="LO"
dim=max(tgt.dimensions); tgt.data.remesh_voxel_size=dim/220.0; tgt.data.remesh_voxel_adaptivity=0.0
bpy.ops.object.voxel_remesh()
if len(tgt.data.polygons)>target:
    dc=tgt.modifiers.new("dec","DECIMATE"); dc.ratio=max(0.03,target/len(tgt.data.polygons)); bpy.ops.object.modifier_apply(modifier=dc.name)
# light de-lump
ls=tgt.modifiers.new("ls","LAPLACIANSMOOTH"); ls.iterations=3; ls.lambda_factor=2.0; ls.use_volume_preserve=True
bpy.ops.object.modifier_apply(modifier=ls.name)
for p in tgt.data.polygons: p.use_smooth=True
lo_tris=len(tgt.data.polygons)
# --- color transfer HI -> LO (nearest), so the clean retopo keeps the concept colors ---
dt=tgt.modifiers.new("dt","DATA_TRANSFER"); dt.object=src; dt.use_loop_data=True
dt.data_types_loops={'COLOR_CORNER'}; dt.loop_mapping='POLYINTERP_NEAREST'
try: bpy.ops.object.datalayout_transfer(modifier=dt.name)
except Exception: pass
bpy.ops.object.modifier_apply(modifier=dt.name)
# --- UV unwrap LO ---
bpy.ops.object.select_all(action='DESELECT'); tgt.select_set(True); bpy.context.view_layer.objects.active=tgt
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.003); bpy.ops.object.mode_set(mode='OBJECT')
# --- BAKE vertex colors -> texture atlas (EMIT, flat) ---
img=bpy.data.images.new("WaneTex", texres, texres)
mat=bpy.data.materials.new("M_Wane"); mat.use_nodes=True; nt=mat.node_tree; bsdf=nt.nodes.get("Principled BSDF")
vcol=nt.nodes.new("ShaderNodeVertexColor")
ca=tgt.data.color_attributes
if ca: vcol.layer_name=ca[0].name
nt.links.new(vcol.outputs["Color"], bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value=1.0
texnode=nt.nodes.new("ShaderNodeTexImage"); texnode.image=img; nt.nodes.active=texnode
tgt.data.materials.clear(); tgt.data.materials.append(mat)
scene=bpy.context.scene; scene.render.engine='CYCLES'
try: scene.cycles.device='CPU'; scene.cycles.samples=4
except Exception: pass
scene.render.bake.use_pass_direct=False; scene.render.bake.use_pass_indirect=False
try:
    bpy.ops.object.bake(type='EMIT'); img.filepath_raw=out+"/wane_basecolor.png"; img.file_format='PNG'; img.save()
    baked=True
except Exception as e:
    print("BAKE_ERR",e); baked=False
# now wire the baked texture as Base Color + a clean WANEFALL material (darker armor look)
for l in list(bsdf.inputs["Emission Color"].links): nt.links.remove(l)
bsdf.inputs["Emission Strength"].default_value=0.0
nt.links.new(texnode.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Metallic"].default_value=0.3; bsdf.inputs["Roughness"].default_value=0.5
# export game-ready FBX + OBJ
bpy.ops.object.select_all(action='DESELECT'); tgt.select_set(True); bpy.context.view_layer.objects.active=tgt
bpy.ops.export_scene.fbx(filepath=out+"/vorlax_gameready.fbx", use_selection=True, path_mode='COPY', embed_textures=False)
try: bpy.ops.wm.obj_export(filepath=out+"/vorlax_gameready.obj", export_materials=True, export_uv=True, export_selected_objects=True)
except Exception: pass
# --- HERO RENDER (same session: textured retopo mesh, dark studio, key+rim+fill, 4 angles) ---
for o in list(bpy.context.scene.objects):
    if o.type in ('LIGHT','CAMERA') or o.name in ('HI',): bpy.data.objects.remove(o, do_unlink=True)
src=None
def M2(n,base,metal,rough,emis=None,estr=0.0):
    m=bpy.data.materials.new(n); m.use_nodes=True; b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(base[0],base[1],base[2],1); b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    if emis: b.inputs["Emission Color"].default_value=(emis[0],emis[1],emis[2],1); b.inputs["Emission Strength"].default_value=estr
    return m
scene.cycles.samples=64
scene.render.resolution_x=560; scene.render.resolution_y=820
w=bpy.data.worlds['World']; scene.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.008,0.009,0.012,1)
bpy.ops.mesh.primitive_plane_add(size=16, location=(-2.0,0,1.4)); bd=bpy.context.active_object
bd.rotation_euler=(0,math.radians(90),0); bd.data.materials.append(M2("M_BD",(0.012,0.014,0.02),0,0.85))
bpy.ops.mesh.primitive_plane_add(size=16, location=(0,0,0)); fl=bpy.context.active_object; fl.data.materials.append(M2("M_FL",(0.014,0.016,0.022),0,0.7))
def light(n,loc,e,c,sz=2.0):
    ld=bpy.data.lights.new(n,'AREA'); ld.energy=e; ld.color=c; ld.size=sz
    lo=bpy.data.objects.new(n,ld); lo.location=loc; scene.collection.objects.link(lo)
    d=mathutils.Vector((0,0,1.0))-mathutils.Vector(loc); lo.rotation_euler=d.to_track_quat('-Z','Y').to_euler(); return lo
light("key",(2.6,-2.2,3.2),1200,(1.0,0.97,0.92),2.5); light("rim",(-1.8,2.0,2.4),1000,(0.35,0.8,1.0),1.6)
light("rim2",(-1.6,-2.2,2.2),600,(0.45,0.85,1.0),1.6); light("fill",(2.4,2.4,1.0),80,(0.8,0.88,1.0),3.0)
cam_d=bpy.data.cameras.new("cam"); cam=bpy.data.objects.new("cam",cam_d); scene.collection.objects.link(cam); scene.camera=cam; cam_d.lens=58
look=mathutils.Vector((0,0,1.0))
for vn,loc in {"front":(4.6,0,1.05),"threequarter":(3.9,-2.8,1.15),"side":(0.2,-4.8,1.05),"back":(-4.6,0.2,1.05)}.items():
    cam.location=loc; d=look-mathutils.Vector(loc); cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=out+f"/hero_{vn}.png"; bpy.ops.render.render(write_still=True)
open(out+"/finalize_done.json","w").write(json.dumps({"ok":True,"hi_tris":hi_tris,"lo_tris":lo_tris,"baked":baked}))
print("FINALIZE_OK hi",hi_tris,"lo",lo_tris,"baked",baked)
'''


def finalize_character(mesh_path: str, out_dir: Path, target_tris: int = 30000, tex_res: int = 2048, timeout: int = 420) -> dict:
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    exe = blender_exe()
    if not exe:
        return {"ok": False, "error": "Blender not found"}
    scr = out / "_finalize.py"; scr.write_text(_FINALIZE, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(scr), "--", str(Path(mesh_path).resolve()), str(out), str(target_tris), str(tex_res)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    ok = "FINALIZE_OK" in r.stdout
    return {"ok": ok, "fbx": str(out / "vorlax_gameready.fbx") if (out / "vorlax_gameready.fbx").exists() else None,
            "basecolor": str(out / "wane_basecolor.png") if (out / "wane_basecolor.png").exists() else None,
            "stdout_tail": r.stdout.strip().splitlines()[-3:] if r.stdout else [],
            "stderr_tail": r.stderr.strip().splitlines()[-4:] if r.stderr else []}


if __name__ == "__main__":
    import sys
    print(json.dumps(polish_mesh(sys.argv[1], Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/polish")), indent=2))
