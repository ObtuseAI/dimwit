"""Dimwit TOPOLOGY ANALYZE (Blender headless) — measure mesh topology quality so Dimwit can judge it like a
character artist: quad/tri/ngon ratio, non-manifold edges, pole/valence distribution, loose geometry, UV
presence, watertightness, tri count. This is the data source for topology QA + the before/after proof of retopo.

  blender --background --python topology_analyze.py -- in=<mesh.glb|.fbx> out=<metrics.json>
"""
import bpy, bmesh, sys, json
from pathlib import Path

A = {}
for a in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []:
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
SRC, OUT = A.get("in"), A.get("out", "topo.json")


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
    elif p.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise RuntimeError("unsupported mesh format: " + path)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("no mesh in " + path)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def analyze(ob) -> dict:
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    nf = len(bm.faces)
    tris = quads = ngons = 0
    for f in bm.faces:
        n = len(f.verts)
        if n == 3:
            tris += 1
        elif n == 4:
            quads += 1
        else:
            ngons += 1
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    # valence: a clean quad/subdiv mesh is mostly valence-4; poles = verts not valence 4
    val = {}
    poles = 0
    for v in bm.verts:
        d = len(v.link_edges)
        val[d] = val.get(d, 0) + 1
        if d != 4:
            poles += 1
    loose_verts = sum(1 for v in bm.verts if not v.link_faces)
    nv = len(bm.verts)
    bm.free()
    return {
        "verts": nv, "edges": len(me.edges), "faces": nf,
        "tris": tris, "quads": quads, "ngons": ngons,
        "tri_fraction": round(tris / nf, 4) if nf else 0,
        "quad_fraction": round(quads / nf, 4) if nf else 0,
        "ngon_fraction": round(ngons / nf, 4) if nf else 0,
        "non_manifold_edges": non_manifold,
        "boundary_edges": boundary,
        "watertight": non_manifold == 0 and boundary == 0,
        "poles": poles, "pole_fraction": round(poles / nv, 4) if nv else 0,
        "valence_hist": {str(k): v for k, v in sorted(val.items())},
        "loose_verts": loose_verts,
        "uv_layers": len(me.uv_layers), "has_uv": len(me.uv_layers) > 0,
        "materials": len(me.materials),
        "tri_count_render": tris + quads * 2 + max(0, ngons) * 3,   # approx renderable tri budget
    }


out = {"ok": False, "src": SRC}
try:
    clear()
    ob = import_any(SRC)
    out["metrics"] = analyze(ob)
    out["ok"] = True
except Exception:
    import traceback
    out["error"] = traceback.format_exc().splitlines()[-1]
Path(OUT).parent.mkdir(parents=True, exist_ok=True)
Path(OUT).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_TOPOLOGY_ANALYZE_DONE ok=" + str(out["ok"]))
