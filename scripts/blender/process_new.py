"""One Blender session: process the 18 new assets for UE.
  mech_*.glb  -> symmetrize (bilateral) + decimate 45k -> SM_Char_Mech_<name>.glb  (Characters)
  gren_*.glb  -> decimate 15k                          -> SM_Wpn_Gren_<name>.glb   (Weapons)
Run:  blender --background --python scripts/blender/process_new.py -- <in_dir> <out_dir>
"""
import bpy, sys, os, glob
A = sys.argv[sys.argv.index("--")+1:]
SRC, DST = os.path.abspath(A[0]), os.path.abspath(A[1]); os.makedirs(DST, exist_ok=True)

def load(g):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=g)
    ms = [o for o in bpy.context.scene.objects if o.type=='MESH']
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    return bpy.context.view_layer.objects.active

def symmetrize(ob):
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    ob.location = (0,0,0); bpy.ops.object.transform_apply(location=True)
    bb = ob.bound_box
    ext = {ax: max(c[i] for c in bb)-min(c[i] for c in bb) for i,ax in enumerate("XYZ")}
    up = max(ext, key=ext.get); lr = max([a for a in "XYZ" if a!=up], key=lambda a: ext[a])
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.symmetrize(direction=f"POSITIVE_{lr}", threshold=8e-4)
    bpy.ops.object.mode_set(mode='OBJECT')

def decimate(ob, target):
    tris = sum(len(p.vertices)-2 for p in ob.data.polygons)
    if tris > target:
        m = ob.modifiers.new("d","DECIMATE"); m.decimate_type='COLLAPSE'; m.ratio = target/max(tris,1)
        bpy.ops.object.modifier_apply(modifier="d")

def cap(s): return "_".join(w.capitalize() for w in s.split("_"))

done = 0
for g in sorted(glob.glob(os.path.join(SRC, "*.glb"))):
    base = os.path.basename(g)
    if base.startswith("mech_"):
        name = base[len("mech_"):-4]; out = os.path.join(DST, f"SM_Char_Mech_{cap(name)}.glb"); tgt = 45000; sym = True
    elif base.startswith("gren_"):
        name = base[len("gren_"):-4]; out = os.path.join(DST, f"SM_Wpn_Gren_{cap(name)}.glb"); tgt = 15000; sym = False
    else:
        continue
    ob = load(g)
    if sym: symmetrize(ob)
    decimate(ob, tgt)
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
    done += 1; print(f"PROC {os.path.basename(out)} faces={len(ob.data.polygons)}")
print(f"PROCESS_NEW_DONE {done}")
