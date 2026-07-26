"""Dimwit PRIMITIVE BLOCKOUT (Blender headless) — the guaranteed LOCAL geometry fallback so Dimwit never
hard-stops when the Hi3D cloud is unavailable (closes G3's single-point-of-failure). Generates a deterministic,
correctly-proportioned humanoid blockout (clean quad primitives, manifold, UV'd) at the SK_Mannequin scale. It is
an honest PLACEHOLDER (flagged not-promotable) but it keeps the pipeline running + riggable end-to-end offline.

  blender --background --python primitive_blockout.py -- out=<blockout.fbx> height=1.8 seed=2
"""
import bpy, bmesh, sys, json, math
from pathlib import Path

A = {}
for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []):
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
OUT = A.get("out", "artifacts/geo/blockout.fbx")
H = float(A.get("height", 1.8))
SEED = int(A.get("seed", 2))


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def box(name, loc, size):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    return o


out = {"ok": False, "out": OUT, "placeholder": True}
try:
    clear()
    # proportioned humanoid blockout (heights as fractions of H), deterministic from seed
    j = 0.02 * ((SEED % 5) - 2)                     # tiny deterministic variation
    parts = []
    parts.append(box("pelvis", (0, 0, H * 0.50), (H * 0.20, H * 0.13, H * 0.16)))
    parts.append(box("torso", (0, 0, H * 0.68 + j), (H * 0.26, H * 0.15, H * 0.26)))
    parts.append(box("head", (0, 0, H * 0.92), (H * 0.13, H * 0.13, H * 0.14)))
    for s in (-1, 1):
        parts.append(box(f"upperarm{s}", (s * H * 0.18, 0, H * 0.74), (H * 0.08, H * 0.08, H * 0.22)))
        parts.append(box(f"forearm{s}", (s * H * 0.18, 0, H * 0.55), (H * 0.07, H * 0.07, H * 0.20)))
        parts.append(box(f"thigh{s}", (s * H * 0.07, 0, H * 0.34), (H * 0.10, H * 0.10, H * 0.26)))
        parts.append(box(f"shin{s}", (s * H * 0.07, 0, H * 0.12), (H * 0.08, H * 0.08, H * 0.24)))
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = "blockout"
    # weld + manifold + UV
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(ob.data); bm.free()
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    try:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
    except Exception:
        bpy.ops.uv.unwrap(margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, add_leaf_bones=False)
    out["faces"] = len(ob.data.polygons)
    out["ok"] = Path(OUT).exists()
except Exception:
    import traceback
    out["error"] = traceback.format_exc().splitlines()[-1]
Path(A.get("report", OUT + ".blockout.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_BLOCKOUT_DONE ok=" + str(out["ok"]))
