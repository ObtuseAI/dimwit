"""Dimwit RE-BAKE onto EXISTING UVs (Blender headless) - high-quality texture refresh for an
already-rigged character WITHOUT touching its topology/UVs.

The 2026-06-30 roster relift baked albedo/normal/AO at res=2048 samples=8; the semantic optics
gate correctly rejects that bake as blurry noise vs the Hi3D reference. Re-running handcraft.py
would re-retopo and orphan the rig's UVs, so this script imports the EXISTING retopo FBX as LOW
(UVs untouched), the textured source GLB as HIGH (900k cap, emission driven by its embedded
base-color image - same EMIT-transfer technique as handcraft.py), aligns HIGH onto LOW's bounds,
and bakes NORMAL + AO + EMIT(albedo) at high res/samples.

  blender --background --python rebake_maps_onto_existing_uvs.py -- \
      high=<source.glb> low=<existing_retopo.fbx> out=<dir> name=<prefix> res=4096 samples=32
"""
import json
import math
import sys
import traceback
from pathlib import Path

import bpy

A = {}
for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []):
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
HIGH_PATH, LOW_PATH = A["high"], A["low"]
OUTDIR = Path(A.get("out", "artifacts/rig_rebake"))
NAME = A.get("name", "rebake")
RES = int(A.get("res", 4096))
SAMPLES = int(A.get("samples", 32))
HIGHCAP = int(A.get("highcap", 900000))
OUTDIR.mkdir(parents=True, exist_ok=True)
out = {"ok": False, "high": HIGH_PATH, "low": LOW_PATH, "res": RES, "samples": SAMPLES, "maps": {}}


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for d in (bpy.data.meshes, bpy.data.objects, bpy.data.images, bpy.data.materials):
        for b in list(d):
            try:
                d.remove(b)
            except Exception:
                pass


def import_joined(path):
    before = set(bpy.context.scene.objects)
    p = path.lower()
    if p.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in before]
    if not meshes:
        raise RuntimeError(f"no meshes imported from {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


try:
    clear()
    low = import_joined(LOW_PATH)
    low.name = "LOW"
    if not low.data.uv_layers:
        raise RuntimeError("LOW retopo mesh has no UVs - aborting (UVs are the whole point)")
    out["low_faces"] = len(low.data.polygons)

    high = import_joined(HIGH_PATH)
    high.name = "HIGH"
    out["high_faces"] = len(high.data.polygons)
    if len(high.data.polygons) > HIGHCAP:                      # RAM safeguard (handcraft.py precedent)
        md = high.modifiers.new("hcap", "DECIMATE")
        md.ratio = max(0.02, HIGHCAP / len(high.data.polygons))
        bpy.context.view_layer.objects.active = high
        bpy.ops.object.modifier_apply(modifier=md.name)
        out["high_faces_capped"] = len(high.data.polygons)

    # align HIGH onto LOW's bounds (retopo FBX and GLB should share space; guard against unit drift)
    def bounds(o):
        import mathutils
        pts = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        mins = [min(p[i] for p in pts) for i in range(3)]
        maxs = [max(p[i] for p in pts) for i in range(3)]
        return mins, maxs
    lmin, lmax = bounds(low)
    hmin, hmax = bounds(high)
    lsize = max(lmax[i] - lmin[i] for i in range(3)) or 1.0
    hsize = max(hmax[i] - hmin[i] for i in range(3)) or 1.0
    scale = lsize / hsize
    out["align_scale"] = round(scale, 6)
    if abs(scale - 1.0) > 0.02:
        high.scale = tuple(s * scale for s in high.scale)
        bpy.context.view_layer.objects.active = high
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        hmin, hmax = bounds(high)
    lcen = [(lmin[i] + lmax[i]) * 0.5 for i in range(3)]
    hcen = [(hmin[i] + hmax[i]) * 0.5 for i in range(3)]
    high.location = tuple(high.location[i] + (lcen[i] - hcen[i]) for i in range(3))
    out["align_offset"] = [round(lcen[i] - hcen[i], 4) for i in range(3)]

    # drive HIGH emission from its embedded base-color image (EMIT bake = reliable cross-UV transfer)
    albedo_img = None
    for m in high.data.materials:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    albedo_img = n.image
                    break
        if albedo_img:
            break
    if albedo_img is None:
        raise RuntimeError("no base-color image found in HIGH's GLB materials")
    out["albedo_image"] = albedo_img.name
    high.data.materials.clear()
    hm = bpy.data.materials.new("high_albedo")
    hm.use_nodes = True
    high.data.materials.append(hm)
    nt = hm.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    timg = nt.nodes.new("ShaderNodeTexImage")
    timg.image = albedo_img
    nt.links.new(timg.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], outn.inputs["Surface"])

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        sc.cycles.device = "CPU"
        sc.cycles.samples = SAMPLES
    except Exception:
        pass
    low.data.materials.clear()
    low.data.materials.append(bpy.data.materials.new("low_bake"))
    mat = low.data.materials[0]
    mat.use_nodes = True
    bake_diag = {}

    def bake_one(btype, fname, is_normal=False):
        img = bpy.data.images.new(fname, RES, RES, float_buffer=is_normal)
        img.file_format = "PNG"
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        mat.node_tree.nodes.active = node
        for n in mat.node_tree.nodes:
            n.select = (n == node)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        try:
            r = bpy.ops.object.bake(type=btype, use_selected_to_active=True, cage_extrusion=0.08,
                                    max_ray_distance=0.15, margin=16)
            bake_diag[btype] = str(r)
        except Exception as e:
            bake_diag[btype] = f"bake-exc: {e}"
            return None
        p = str(OUTDIR / fname)
        try:
            img.save(filepath=p)
        except Exception:
            try:
                img.filepath_raw = p
                img.save()
            except Exception as e2:
                bake_diag[btype + "_save"] = str(e2)
                return None
        return p if Path(p).exists() and Path(p).stat().st_size > 0 else None

    out["maps"]["albedo"] = bake_one("EMIT", f"{NAME}_albedo_4k.png")
    out["maps"]["normal"] = bake_one("NORMAL", f"{NAME}_normal_4k.png", is_normal=True)
    out["maps"]["ao"] = bake_one("AO", f"{NAME}_ao_4k.png")
    out["bake_diag"] = bake_diag
    out["ok"] = all(out["maps"].get(k) for k in ("albedo", "normal", "ao"))
except Exception:
    out["error"] = traceback.format_exc().splitlines()[-1]
    out["trace"] = traceback.format_exc()[-1200:]

Path(A.get("report", str(OUTDIR / f"{NAME}_rebake_report.json"))).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_REBAKE_DONE ok=" + str(out["ok"]))
