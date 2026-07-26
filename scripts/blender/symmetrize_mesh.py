"""Enforce bilateral symmetry on a character GLB (fixes single-image-to-3D lopsidedness).
Auto-detects up=tallest axis and left-right=wider horizontal axis, centers the mesh on that plane,
and mirrors one half to the other (preserves UVs+material -> symmetric texture, correct for symmetric designs).
  blender --background --python scripts/blender/symmetrize_mesh.py -- <in.glb> <out.glb> [POSITIVE|NEGATIVE]
"""
import bpy, sys, os
A = sys.argv[sys.argv.index("--")+1:]
src, out = os.path.abspath(A[0]), os.path.abspath(A[1])
side = A[2] if len(A) > 2 else "POSITIVE"
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1: bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(rotation=True, scale=True)
# center geometry on origin so the symmetry plane passes through the middle
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
ob.location = (0, 0, 0); bpy.ops.object.transform_apply(location=True)
# axis detection from local bbox extents
bb = ob.bound_box
ext = {ax: max(c[i] for c in bb) - min(c[i] for c in bb) for i, ax in enumerate("XYZ")}
up = max(ext, key=ext.get)                                   # tallest = up (standing figure)
horiz = [a for a in "XYZ" if a != up]
lr = max(horiz, key=lambda a: ext[a])                        # wider horizontal = left-right (shoulders)
direction = f"{side}_{lr}"
print(f"SYM extents={ {k:round(v,3) for k,v in ext.items()} } up={up} mirror_axis={lr} dir={direction}")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.symmetrize(direction=direction, threshold=0.0008)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
print(f"SYMMETRIZE_OK -> {out} faces={len(ob.data.polygons)}")
