"""Decimate-only stage for mechs 05-08 (multi-view = already symmetric; symmetrize hangs on dense
non-manifold hard-surface geo, so we skip it). One Blender session, per-item try/except, skip-if-exists.
Run:  blender --background --python scripts/blender/process_mechs_fix.py -- <in_dir> <out_dir>
"""
import bpy, sys, os, glob, traceback
A = sys.argv[sys.argv.index("--")+1:]
SRC, DST = os.path.abspath(A[0]), os.path.abspath(A[1]); os.makedirs(DST, exist_ok=True)
ONLY = {"mech_05_pyroclast", "mech_06_jadewind", "mech_07_ironline", "mech_08_nightwire"}

def load(g):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=g)
    ms = [o for o in bpy.context.scene.objects if o.type=='MESH']
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    return bpy.context.view_layer.objects.active

def decimate(ob, target):
    tris = sum(len(p.vertices)-2 for p in ob.data.polygons)
    if tris > target:
        m = ob.modifiers.new("d","DECIMATE"); m.decimate_type='COLLAPSE'; m.ratio = target/max(tris,1)
        bpy.ops.object.modifier_apply(modifier="d")

def cap(s): return "_".join(w.capitalize() for w in s.split("_"))

done = 0
for g in sorted(glob.glob(os.path.join(SRC, "*.glb"))):
    base = os.path.basename(g)[:-4]
    if base not in ONLY: continue
    name = base[len("mech_"):]; out = os.path.join(DST, f"SM_Char_Mech_{cap(name)}.glb")
    if os.path.exists(out): print(f"SKIP {os.path.basename(out)} (exists)"); continue
    try:
        ob = load(g); decimate(ob, 45000)
        bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
        done += 1; print(f"PROC {os.path.basename(out)} faces={len(ob.data.polygons)}", flush=True)
    except Exception:
        print(f"FAIL {base}:\n{traceback.format_exc()}", flush=True)
print(f"MECHS_FIX_DONE {done}")
