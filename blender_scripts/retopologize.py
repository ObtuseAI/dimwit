"""Dimwit RETOPOLOGIZE (Blender headless) — translate a dense triangle-soup scan/gen mesh into CLEAN,
animation-ready QUAD topology (field-aligned, watertight, UV-unwrapped) so it DEFORMS like a handcrafted asset
instead of morphing/disfiguring. Pipeline: import -> weld+clean -> (decimate to a tractable density) ->
QUADRIFLOW remesh to target quads (voxel-remesh fallback) -> Smart UV -> export low-poly FBX. Keeps the original
high-poly available for the high->low detail bake (bake_maps.py) = the handcrafted result.

  blender --background --python retopologize.py -- in=<dense.glb> out=<retopo.fbx> target=14000 pre=160000
"""
import bpy, bmesh, sys, json, math
from pathlib import Path

A = {}
for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []):
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
SRC = A["in"]
OUT = A.get("out", "retopo.fbx")
TARGET = int(A.get("target", 14000))      # target quad count for a game character
PRE = int(A.get("pre", 160000))            # pre-decimate density before quadriflow (RAM-tight machine)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for d in (bpy.data.meshes, bpy.data.objects):
        for b in list(d):
            try:
                d.remove(b)
            except Exception:
                pass


def import_any(path):
    p = path.lower()
    if p.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif p.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True)
    else:
        raise RuntimeError("unsupported: " + path)
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def facecount(ob):
    return len(ob.data.polygons)


def weld_clean(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def decimate_to(ob, target_faces):
    cur = facecount(ob)
    if cur <= target_faces:
        return
    m = ob.modifiers.new("dec", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = max(0.01, min(1.0, target_faces / cur))
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=m.name)


def smart_uv(ob):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
    except Exception:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")


out = {"ok": False, "src": SRC, "target": TARGET}
try:
    clear()
    ob = import_any(SRC)
    out["raw_faces"] = facecount(ob)
    weld_clean(ob)
    decimate_to(ob, PRE)
    out["pre_quad_faces"] = facecount(ob)
    # QUADRIFLOW: field-aligned quad remesh (the elite step). Falls back to voxel remesh if it fails.
    method = "quadriflow"
    try:
        bpy.ops.object.quadriflow_remesh(target_faces=TARGET, use_mesh_symmetry=True,
                                         use_preserve_sharp=False, use_preserve_boundary=True,
                                         smooth_normals=True, mode="FACES")
    except Exception as e:
        method = "voxel_fallback"
        out["quadriflow_error"] = str(e)
        mv = ob.modifiers.new("rm", "REMESH")
        mv.mode = "VOXEL"
        mv.voxel_size = 0.03
        bpy.ops.object.modifier_apply(modifier=mv.name)
        decimate_to(ob, TARGET * 2)
    out["method"] = method
    out["retopo_faces"] = facecount(ob)
    smart_uv(ob)
    # metrics after
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    q = sum(1 for f in bm.faces if len(f.verts) == 4)
    nf = len(bm.faces)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    out["retopo_quad_fraction"] = round(q / nf, 4) if nf else 0
    out["retopo_non_manifold"] = nm
    out["retopo_has_uv"] = len(me.uv_layers) > 0
    # export low-poly FBX
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, mesh_smooth_type="FACE",
                             add_leaf_bones=False, bake_space_transform=True)
    out["out"] = OUT
    out["ok"] = Path(OUT).exists() and nf > 0
except Exception:
    import traceback
    out["error"] = traceback.format_exc().splitlines()[-1]
Path(A.get("report", OUT + ".retopo.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_RETOPO_DONE ok=" + str(out["ok"]) + " method=" + str(out.get("method")))
