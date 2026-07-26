"""Export a decimated roster mesh (geometry only, no skeleton) to FBX for Mixamo/Accurig auto-rig upload.
Mixamo needs a clean single-mesh T/A-pose under its poly limit; the ~45k staging_sym mesh is ideal.
Run: blender --background --python export_for_mixamo.py -- in=<mesh.glb> out=<mesh.fbx>
"""
import bpy, sys, json
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
IN, OUT = A.get("in"), A.get("out")
res = {"ok": False, "in": IN, "out": OUT}
try:
    assert IN and OUT, "need in= out="
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.import_scene.gltf(filepath=IN)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert meshes, "no mesh"
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    # drop any armature/skeleton so Mixamo auto-rigs cleanly (geometry only)
    for m in list(mesh.modifiers):
        if m.type == "ARMATURE":
            mesh.modifiers.remove(m)
    mesh.vertex_groups.clear()
    res["tris"] = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, add_leaf_bones=False,
                             mesh_smooth_type="FACE", bake_anim=False, object_types={"MESH"})
    res["ok"] = Path(OUT).exists()
except Exception:
    import traceback
    res["error"] = traceback.format_exc()
print("MIXAMO_EXPORT_DONE " + json.dumps({k: res.get(k) for k in ("ok", "tris")}))
Path((OUT or "x") + ".export.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
