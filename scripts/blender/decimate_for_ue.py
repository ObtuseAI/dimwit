"""Decimate a textured GLB to a game tri-budget (collapse preserves UVs+materials) -> export GLB.
  blender --background --python scripts/blender/decimate_for_ue.py -- <in.glb> <out.glb> <target_tris>"""
import bpy, sys, math
A = sys.argv[sys.argv.index("--")+1:]
src, out, target = A[0], A[1], int(A[2])
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.context.scene.objects if o.type=='MESH']
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1: bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
tris = sum(len(p.vertices)-2 for p in ob.data.polygons)
if tris > target:
    m = ob.modifiers.new("dec","DECIMATE"); m.decimate_type='COLLAPSE'; m.ratio = target/max(tris,1)
    bpy.ops.object.modifier_apply(modifier="dec")
final = len(ob.data.polygons)
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
print(f"DECIMATE_OK in_tris={tris} out_faces={final} -> {out}")
