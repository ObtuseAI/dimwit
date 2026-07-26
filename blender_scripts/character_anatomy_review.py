"""Dimwit CHARACTER ANATOMY REVIEW (Blender headless).

Loads a GLB/FBX/OBJ in Blender, saves an inspection .blend, renders six orthographic
axis views plus two diagonals, and writes mesh-space symmetry/anatomy metrics.

This is intentionally upstream of Unreal import. UE screenshots are useful, but a
bad source/retopo/rig FBX must be catchable in Blender before it reaches the game.

Run:
  blender --background --python character_anatomy_review.py -- in=<mesh> out=<dir> label=<name>
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
import mathutils
from mathutils import Vector
from mathutils.kdtree import KDTree


def _args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {}
    for item in argv:
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


A = _args()
SRC = A.get("in")
OUT = Path(A.get("out", "artifacts/blender_anatomy_review")).resolve()
LABEL = A.get("label") or (Path(SRC).stem if SRC else "character")
RENDER = A.get("render", "1") != "0"
SAVE_BLEND = A.get("save_blend", "1") != "0"
MAX_SAMPLE = int(A.get("max_sample", "45000"))
RES = int(A.get("res", "900"))

result = {"ok": False, "label": LABEL, "src": SRC, "out": str(OUT)}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images):
        for datablock in list(coll):
            try:
                coll.remove(datablock)
            except Exception:
                pass


def import_any(path: str) -> None:
    p = path.lower()
    if p.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif p.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=False)
    elif p.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise RuntimeError(f"unsupported mesh format: {path}")


def mesh_objects() -> list:
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def world_bbox(meshes: list) -> tuple[Vector, Vector]:
    pts = []
    for obj in meshes:
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    if not pts:
        raise RuntimeError("no mesh bounds")
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def sample_vertices(meshes: list, max_sample: int) -> list[Vector]:
    total = sum(len(o.data.vertices) for o in meshes)
    step = max(1, math.ceil(total / max_sample)) if total else 1
    pts = []
    i = 0
    for obj in meshes:
        mw = obj.matrix_world
        for v in obj.data.vertices:
            if i % step == 0:
                pts.append(mw @ v.co)
            i += 1
    return pts


def axis_metrics(points: list[Vector], mn: Vector, mx: Vector) -> dict:
    dims = mx - mn
    height = max(dims.x, dims.y, dims.z, 1e-6)
    center = (mn + mx) * 0.5
    tuples = [(p.x, p.y, p.z) for p in points]
    kd = KDTree(len(tuples))
    for i, p in enumerate(tuples):
        kd.insert(Vector(p), i)
    kd.balance()

    def mismatch(axis_idx: int, subset: list[int] | None = None) -> float:
        ids = subset if subset is not None else range(len(tuples))
        acc = 0.0
        n = 0
        for i in ids:
            p = list(tuples[i])
            p[axis_idx] = 2.0 * center[axis_idx] - p[axis_idx]
            _, _, dist = kd.find(Vector(p))
            acc += dist / height
            n += 1
        return round((acc / max(1, n)) * 100.0, 3)

    raw = {"x": mismatch(0), "y": mismatch(1), "z": mismatch(2)}
    up_axis_idx = max(range(3), key=lambda idx: (dims.x, dims.y, dims.z)[idx])
    up_name = ("x", "y", "z")[up_axis_idx]
    body_axes = [idx for idx in range(3) if idx != up_axis_idx]
    symmetry_axis_idx = min(body_axes, key=mismatch)
    symmetry_axis = ("x", "y", "z")[symmetry_axis_idx]
    up_min = (mn.x, mn.y, mn.z)[up_axis_idx]
    up_extent = max((dims.x, dims.y, dims.z)[up_axis_idx], 1e-6)
    regions = {
        "legs": (0.00, 0.45),
        "torso_arms": (0.45, 0.82),
        "head_face": (0.82, 1.00),
    }
    region_out = {}
    for name, (lo, hi) in regions.items():
        ids = [
            i for i, p in enumerate(tuples)
            if lo <= ((p[up_axis_idx] - up_min) / up_extent) <= hi
        ]
        region_out[name] = {
            "samples": len(ids),
            "mirror_mismatch_pct": mismatch(symmetry_axis_idx, ids) if ids else None,
        }

    return {
        "sample_count": len(points),
        "bbox_min": [round(v, 4) for v in mn],
        "bbox_max": [round(v, 4) for v in mx],
        "dimensions": [round(v, 4) for v in dims],
        "up_axis": up_name,
        "best_body_symmetry_axis": symmetry_axis,
        "mirror_mismatch_pct_by_axis": raw,
        "mirror_mismatch_pct_by_region": region_out,
    }


def object_metrics(meshes: list) -> dict:
    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    mods = []
    for obj in meshes:
        for mod in obj.modifiers:
            if mod.type == "ARMATURE":
                mods.append({
                    "mesh": obj.name,
                    "armature": mod.object.name if mod.object else None,
                })
    return {
        "mesh_count": len(meshes),
        "armature_count": len(armatures),
        "vertex_count": sum(len(o.data.vertices) for o in meshes),
        "face_count": sum(len(o.data.polygons) for o in meshes),
        "objects": [
            {
                "name": o.name,
                "verts": len(o.data.vertices),
                "faces": len(o.data.polygons),
                "location": [round(v, 4) for v in o.location],
                "rotation_euler": [round(v, 4) for v in o.rotation_euler],
                "scale": [round(v, 4) for v in o.scale],
                "parent": o.parent.name if o.parent else None,
            }
            for o in meshes
        ],
        "armatures": [
            {
                "name": a.name,
                "bones": len(a.data.bones),
                "location": [round(v, 4) for v in a.location],
                "rotation_euler": [round(v, 4) for v in a.rotation_euler],
                "scale": [round(v, 4) for v in a.scale],
                "parent": a.parent.name if a.parent else None,
            }
            for a in armatures
        ],
        "armature_modifiers": mods,
    }


def component_metrics(meshes: list, max_faces: int = 220000) -> dict:
    total_faces = sum(len(o.data.polygons) for o in meshes)
    if total_faces > max_faces:
        return {
            "measured": False,
            "reason": f"face_count {total_faces} > component metric cap {max_faces}",
            "total_faces": total_faces,
        }
    total_components = 0
    largest_faces = 0
    small_components = 0
    per_mesh = []
    for obj in meshes:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        visited = set()
        sizes = []
        for face in bm.faces:
            if face.index in visited:
                continue
            stack = [face]
            visited.add(face.index)
            size = 0
            while stack:
                cur = stack.pop()
                size += 1
                for edge in cur.edges:
                    for linked in edge.link_faces:
                        if linked.index not in visited:
                            visited.add(linked.index)
                            stack.append(linked)
            sizes.append(size)
        bm.free()
        sizes.sort(reverse=True)
        total_components += len(sizes)
        if sizes:
            largest_faces = max(largest_faces, sizes[0])
            small_components += sum(1 for s in sizes[1:] if s < max(12, int(total_faces * 0.02)))
        per_mesh.append({
            "mesh": obj.name,
            "components": len(sizes),
            "largest_component_faces": sizes[0] if sizes else 0,
            "component_faces_top8": sizes[:8],
        })
    return {
        "measured": True,
        "total_faces": total_faces,
        "component_count": total_components,
        "largest_component_face_fraction": round(largest_faces / max(1, total_faces), 4),
        "small_component_count": small_components,
        "per_mesh": per_mesh,
    }


def ensure_review_material(meshes: list) -> None:
    mat = bpy.data.materials.new("Dimwit_Review_Matte")
    mat.diffuse_color = (0.74, 0.76, 0.78, 1.0)
    for obj in meshes:
        if not obj.data.materials:
            obj.data.materials.append(mat)


def setup_render_scene(mn: Vector, mx: Vector) -> tuple[Vector, float]:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_cavity = True
    except Exception:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except Exception:
            pass
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.world.color = (0.02, 0.022, 0.026)
    center = (mn + mx) * 0.5
    dims = mx - mn
    radius = max(dims.x, dims.y, dims.z, 1.0) * 0.72
    return center, radius


def add_camera(name: str, loc: Vector, target: Vector, ortho_scale: float):
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho_scale
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = loc
    direction = target - loc
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def render_views(mn: Vector, mx: Vector) -> dict:
    center, radius = setup_render_scene(mn, mx)
    scale = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1.0) * 1.18
    d = max(scale * 2.2, 1.0)
    views = {
        "x_plus": Vector((d, 0, 0)),
        "x_minus": Vector((-d, 0, 0)),
        "y_plus": Vector((0, d, 0)),
        "y_minus": Vector((0, -d, 0)),
        "z_plus": Vector((0, 0, d)),
        "z_minus": Vector((0, 0, -d)),
        "diag_a": Vector((d, -d, d * 0.55)),
        "diag_b": Vector((-d, d, d * 0.55)),
    }
    rendered = {}
    for name, off in views.items():
        cam = add_camera(f"review_{name}", center + off, center, scale)
        bpy.context.scene.camera = cam
        path = OUT / f"{LABEL}_{name}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered[name] = str(path)
    return rendered


try:
    if not SRC:
        raise RuntimeError("missing in=<mesh>")
    OUT.mkdir(parents=True, exist_ok=True)
    clear_scene()
    import_any(SRC)
    meshes = mesh_objects()
    if not meshes:
        raise RuntimeError("no mesh objects after import")
    ensure_review_material(meshes)
    mn, mx = world_bbox(meshes)
    pts = sample_vertices(meshes, MAX_SAMPLE)
    result["object_metrics"] = object_metrics(meshes)
    result["anatomy_metrics"] = axis_metrics(pts, mn, mx)
    result["component_metrics"] = component_metrics(meshes)
    if RENDER:
        result["renders"] = render_views(mn, mx)
    if SAVE_BLEND:
        blend = OUT / f"{LABEL}_review.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        result["blend"] = str(blend)
    result["ok"] = True
except Exception:
    result["error"] = traceback.format_exc()

OUT.mkdir(parents=True, exist_ok=True)
(OUT / f"{LABEL}_review.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("DIMWIT_CHARACTER_ANATOMY_REVIEW " + json.dumps({
    "ok": result.get("ok"),
    "label": LABEL,
    "error": (result.get("error") or "").splitlines()[-1:] or None,
}, default=str))
