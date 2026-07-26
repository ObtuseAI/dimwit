"""Headless decimate a full character glb to a skinning-grade mesh (~45k tris) for rig_to_mannequin.py.
The full Nanite mesh stays the static display; only this decimated copy gets skinned.
Run: blender --background --python decimate_for_skinning.py -- in=<full.glb> out=<skin.glb> [target_tris=45000]
"""
import bpy, sys, json
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
IN, OUT = A.get("in"), A.get("out")
TARGET = int(A.get("target_tris", 45000))
res = {"ok": False, "in": IN, "out": OUT, "target_tris": TARGET}

try:
    assert IN and OUT, "need in= and out="
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.import_scene.gltf(filepath=IN)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert meshes, "no mesh imported"
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    tris_before = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    res["tris_before"] = tris_before
    if tris_before > TARGET:
        mod = mesh.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = max(0.01, min(1.0, TARGET / max(1, tris_before)))
        bpy.ops.object.modifier_apply(modifier=mod.name)
    res["tris_after"] = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format="GLB")
    res["ok"] = Path(OUT).exists()
except Exception:
    import traceback
    res["error"] = traceback.format_exc()

Path((OUT or "decim") + ".decim.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("DIMWIT_DECIM_DONE " + json.dumps({k: res.get(k) for k in ("ok", "tris_before", "tris_after")}))
