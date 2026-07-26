"""Dimwit MESH REPAIR (Blender headless) — fix common single-image-to-3D defects the human-override QA flags:
  mode=keep_main   : drop stray separate objects (e.g. a base/stand the item was generated sitting on) by
                     keeping only the largest loose part. Fixes "grenade fused to a base below it".
  mode=symmetrize  : mirror the GOOD half over the defective half (auto-picks the heavier side) to rebuild a
                     missing/incomplete limb. Fixes "missing leg / truncated forearm" on single-image gens.
  mode=trim_base   : crop everything below zcut (0..1 fraction of height). Fallback when a base is CONNECTED.

Run: blender --background --python mesh_repair.py -- in=<mesh.glb> out=<fixed.glb> mode=<...> [zcut=0.18]
Result JSON -> <out>.repair.json
"""
import bpy, sys, json
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
MESH_IN, OUT, MODE = A.get("in"), A.get("out"), A.get("mode", "keep_main")
ZCUT = float(A.get("zcut", "0.18"))
res = {"in": MESH_IN, "out": OUT, "mode": MODE, "ok": False}


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def imp(p):
    pl = p.lower()
    if pl.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=p)
    elif pl.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=p, ignore_leaf_bones=True)
    elif pl.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=p)


def join_meshes():
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


try:
    reset()
    imp(MESH_IN)
    obj = join_meshes()
    res["verts_before"] = len(obj.data.vertices)

    if MODE == "keep_main":
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        # WELD first: recon meshes are unwelded (every tri is its own loose part), so without this
        # "separate by loose" yields thousands of fragments. Merge coincident verts to form real components.
        ext0 = max((v.co.length for v in obj.data.vertices), default=1.0) or 1.0
        try:
            bpy.ops.mesh.remove_doubles(threshold=ext0 * 1e-4)
        except Exception:
            try:
                bpy.ops.mesh.merge(type="BY_DISTANCE")
            except Exception:
                pass
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
        parts = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        res["loose_parts"] = len(parts)
        parts.sort(key=lambda o: len(o.data.vertices), reverse=True)
        for o in parts[1:]:
            bpy.data.objects.remove(o, do_unlink=True)
        obj = parts[0]
        res["kept_verts"] = len(obj.data.vertices)

    elif MODE == "symmetrize":
        import mathutils
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        xs = [v.co.x for v in obj.data.vertices]
        cx = (min(xs) + max(xs)) / 2.0
        for v in obj.data.vertices:
            v.co.x -= cx                                   # center the symmetry plane on X=0
        vs = obj.data.vertices
        pos = sum(1 for v in vs if v.co.x > 0)
        neg = sum(1 for v in vs if v.co.x < 0)
        direction = "POSITIVE_X" if pos >= neg else "NEGATIVE_X"   # keep the heavier (complete) half
        res.update({"pos_verts": pos, "neg_verts": neg, "direction": direction})

        # --- per-body-part asymmetry ANALYSIS (mean mirror-mismatch as % of height, by Z region) ---
        zs = [v.co.z for v in vs]; zmin = min(zs); zmax = max(zs); H = (zmax - zmin) or 1.0
        kd = mathutils.kdtree.KDTree(len(vs))
        for i, v in enumerate(vs):
            kd.insert(v.co, i)
        kd.balance()
        regions = {"legs": (0.0, 0.45), "torso_arms": (0.45, 0.82), "head_face": (0.82, 1.0)}
        racc = {k: [0.0, 0] for k in regions}
        step = max(1, len(vs) // 15000)
        for i in range(0, len(vs), step):
            v = vs[i].co
            _, _, d = kd.find(mathutils.Vector((-v.x, v.y, v.z)))   # distance to nearest mirrored neighbor
            f = (v.z - zmin) / H
            for k, (a, b) in regions.items():
                if a <= f <= b:
                    racc[k][0] += d; racc[k][1] += 1
                    break
        res["asymmetry_pct_before"] = {k: (round(racc[k][0] / racc[k][1] / H * 100, 2) if racc[k][1] else None)
                                       for k in regions}

        ext = max(v.co.length for v in vs) or 1.0
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.symmetrize(direction=direction, threshold=ext * 5e-4)
        bpy.ops.object.mode_set(mode="OBJECT")
        res["verts_after"] = len(obj.data.vertices)

    elif MODE == "trim_base":
        import math, bmesh
        # bake the glTF Y-up->Z-up rotation so co.z is true world up
        bpy.context.view_layer.objects.active = obj; obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        vs = obj.data.vertices
        zs = [v.co.z for v in vs]
        zmin, zmax = min(zs), max(zs)
        H = (zmax - zmin) or 1.0
        xs = [v.co.x for v in vs]; ys = [v.co.y for v in vs]
        cx = (min(xs) + max(xs)) / 2.0; cy = (min(ys) + max(ys)) / 2.0
        if "zcut" in A:
            cut = zmin + H * ZCUT                          # explicit override
            res["mode_detail"] = "explicit_zcut"
        else:
            # auto neck-find: narrowest horizontal cross-section in the lower `search` fraction = the
            # body/base junction. Cut below it to drop the base the item was generated sitting on.
            search = float(A.get("search", "0.4"))
            nb = 48
            band = [0.0] * nb
            for v in vs:
                f = (v.co.z - zmin) / H
                if f <= search:
                    bi = min(nb - 1, int(f / search * (nb - 1)))
                    r = math.hypot(v.co.x - cx, v.co.y - cy)
                    if r > band[bi]:
                        band[bi] = r
            lo = max(1, int(0.06 * (nb - 1)))
            neck = min(range(lo, nb), key=lambda i: band[i] if band[i] > 0 else 1e18)
            cut = zmin + (neck / (nb - 1)) * search * H
            res["mode_detail"] = "auto_neck"; res["neck_band"] = neck
        res["z_cut_at"] = cut
        res["z_min"] = zmin; res["z_max"] = zmax
        bm = bmesh.new(); bm.from_mesh(obj.data)
        kill = [v for v in bm.verts if v.co.z < cut]
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
        bm.to_mesh(obj.data); bm.free()
        res["verts_after"] = len(obj.data.vertices)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True)
    res["ok"] = Path(OUT).exists()
except Exception:
    import traceback
    res["error"] = traceback.format_exc()

Path((OUT or "repair") + ".repair.json").write_text(json.dumps(res, indent=2))
print("DIMWIT_MESH_REPAIR_DONE " + json.dumps({k: res.get(k) for k in
      ("ok", "mode", "verts_before", "verts_after", "kept_verts", "loose_parts", "direction")}))
