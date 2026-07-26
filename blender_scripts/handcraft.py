"""Dimwit HANDCRAFT (Blender headless, ONE session) — the full elite-topology -> handcrafted-result translation
with guaranteed high/low alignment (no FBX round-trip): import dense gen/scan mesh (HIGH) -> duplicate -> Quadriflow
the duplicate to clean quads (LOW) -> Smart UV -> bake HIGH->LOW NORMAL + AO (+ diffuse) in the SAME space ->
export LOW as FBX + the baked maps. Output reads handcrafted: clean deformable topology carrying sculpt detail.

  blender --background --python handcraft.py -- in=<dense.glb> outdir=<dir> name=<n> target=14000 res=2048
"""
import bpy, bmesh, sys, json, math
from pathlib import Path

A = {}
for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []):
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
SRC = A["in"]
OUTDIR = Path(A.get("outdir", "artifacts/handcraft/out")).resolve()
NAME = A.get("name", Path(SRC).stem)
TARGET = int(A.get("target", 14000))
PRE = int(A.get("pre", 160000))
RES = int(A.get("res", 2048))
SAMPLES = int(A.get("samples", 12))
ALBEDO = A.get("albedo")     # optional base-color PNG (on the HIGH's UVs) -> baked to the LOW's new UVs
OUTDIR.mkdir(parents=True, exist_ok=True)
out = {"ok": False, "name": NAME, "src": SRC, "maps": {}}


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def topo(ob):
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    nf = len(bm.faces)
    q = sum(1 for f in bm.faces if len(f.verts) == 4)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return {"faces": nf, "quad_fraction": round(q / nf, 4) if nf else 0, "non_manifold": nm,
            "has_uv": len(me.uv_layers) > 0}


try:
    clear()
    bpy.ops.import_scene.gltf(filepath=SRC)
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    high = bpy.context.view_layer.objects.active
    high.name = "HIGH"
    out["high_faces"] = len(high.data.polygons)

    # RAM safeguard (machine is tight): cap the HIGH before duplicating so peak memory stays bounded. 900k tris
    # still carries far more detail than the bake target needs, and avoids OOM on the 215MB source meshes.
    HIGHCAP = int(A.get("highcap", 900000))
    if len(high.data.polygons) > HIGHCAP:
        md = high.modifiers.new("hcap", "DECIMATE")
        md.ratio = max(0.02, HIGHCAP / len(high.data.polygons))
        bpy.context.view_layer.objects.active = high
        bpy.ops.object.modifier_apply(modifier=md.name)
        out["high_faces_capped"] = len(high.data.polygons)

    # optionally drive the HIGH's base color from a provided albedo PNG (same UVs as the source) so the DIFFUSE
    # bake transfers the intended silver+seams onto the LOW's new UVs (not the GLB's dark embedded albedo).
    if ALBEDO:
        try:
            # resolve the albedo image: ALBEDO=='auto' -> the GLB's own embedded base-color image (per-char,
            # roster batch); else a provided PNG. Then drive EMISSION from it (EMIT bake = reliable cross-UV
            # color transfer). Non-fatal: a failure just skips the albedo map.
            albedo_img = None
            if ALBEDO == "auto":
                for m in high.data.materials:
                    if m and m.use_nodes:
                        for n in m.node_tree.nodes:
                            if n.type == "TEX_IMAGE" and n.image:
                                albedo_img = n.image; break
                    if albedo_img:
                        break
                if not albedo_img:
                    out["albedo_err"] = "no base-color image in GLB material"
            elif Path(ALBEDO).exists():
                albedo_img = bpy.data.images.load(str(Path(ALBEDO).resolve()))
            if albedo_img is not None:
                high.data.materials.clear()
                hm = bpy.data.materials.new("high_albedo"); hm.use_nodes = True
                high.data.materials.append(hm)
                nt = hm.node_tree
                for n in list(nt.nodes):
                    if n.type != "OUTPUT_MATERIAL":
                        nt.nodes.remove(n)
                outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
                emit = nt.nodes.new("ShaderNodeEmission")
                timg = nt.nodes.new("ShaderNodeTexImage"); timg.image = albedo_img
                nt.links.new(timg.outputs["Color"], emit.inputs["Color"])
                nt.links.new(emit.outputs["Emission"], outn.inputs["Surface"])
                out["albedo_source"] = ALBEDO
        except Exception as e:
            out["albedo_err"] = repr(e)

    # duplicate -> LOW
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    bpy.context.view_layer.objects.active = high
    bpy.ops.object.duplicate()
    low = bpy.context.view_layer.objects.active
    low.name = "LOW"

    # weld, then VOXEL-REMESH the LOW to make it MANIFOLD. Quadriflow REQUIRES a manifold mesh with consistent
    # normals; the raw gen meshes are heavily non-manifold (~1.9M bad edges) so quadriflow silently no-ops on
    # them, leaving triangle soup. Voxel remesh produces a watertight manifold base at a bbox-relative density.
    bm = bmesh.new(); bm.from_mesh(low.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(low.data); bm.free()
    dims = low.dimensions
    maxd = max(dims.x, dims.y, dims.z) or 1.0
    mv = low.modifiers.new("vox", "REMESH"); mv.mode = "VOXEL"
    mv.voxel_size = maxd / float(A.get("voxel_div", 160))   # ~25k clean quads = good hero-char budget
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.modifier_apply(modifier=mv.name)
    out["voxel_faces"] = len(low.data.polygons)
    # voxel remesh gives a reliably CLEAN, manifold, all-quad, deformation-ready mesh. (Quadriflow field-alignment
    # is attempted next but is unreliable headless on these gen meshes; the voxel quads are the robust baseline.
    # Field-aligned-on-all = the instant_meshes backend, see config/rig_anim_backends.json.)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # QUADRIFLOW on the now-manifold mesh -> clean field-aligned quads (low pole count). Symmetry detection is
    # the usual reason it silently no-ops post-voxel, so symmetry OFF. Detect a no-op (face count ~ unchanged)
    # and record honestly so the topology gate can tell field-aligned from voxel-quad output.
    voxel_faces = len(low.data.polygons)
    method = "quadriflow"
    try:
        bpy.ops.object.quadriflow_remesh(target_faces=TARGET, use_mesh_symmetry=False,
                                         use_preserve_boundary=False, smooth_normals=True, mode="FACES")
    except Exception as e:
        out["quadriflow_error"] = str(e)
    if abs(len(low.data.polygons) - voxel_faces) <= max(50, voxel_faces * 0.02):
        method = "voxel_quads"        # quadriflow no-op'd; we kept the voxel quad mesh (clean but more poles)
    out["method"] = method
    out["post_quadriflow_faces"] = len(low.data.polygons)
    out["low_topology"] = topo(low)

    # Smart UV on LOW
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
    except Exception:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    out["low_topology"] = topo(low)

    # bake HIGH->LOW (same session => aligned)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES
    except Exception:
        pass
    if not low.data.materials:
        low.data.materials.append(bpy.data.materials.new("low_mat"))
    mat = low.data.materials[0]; mat.use_nodes = True

    bake_diag = {}

    def bake_one(btype, fname, is_normal=False):
        img = bpy.data.images.new(fname, RES, RES, float_buffer=is_normal)
        img.file_format = "PNG"
        node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = img
        mat.node_tree.nodes.active = node
        for n in mat.node_tree.nodes:
            n.select = (n == node)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True); low.select_set(True)
        bpy.context.view_layer.objects.active = low
        try:
            r = bpy.ops.object.bake(type=btype, use_selected_to_active=True, cage_extrusion=0.08,
                                    max_ray_distance=0.15, margin=8)
            bake_diag[btype] = str(r)
        except Exception as e:
            bake_diag[btype] = f"bake-exc: {e}"
            return None
        p = str(OUTDIR / fname)
        try:
            img.save(filepath=p)                       # explicit filepath (headless-reliable)
        except Exception as e:
            bake_diag[btype + "_save"] = f"save-exc: {e}"
            try:
                img.filepath_raw = p; img.save()
            except Exception as e2:
                bake_diag[btype + "_save2"] = str(e2); return None
        return p if Path(p).exists() and Path(p).stat().st_size > 0 else None

    out["maps"]["normal"] = bake_one("NORMAL", f"{NAME}_normal.png", is_normal=True)
    out["maps"]["ao"] = bake_one("AO", f"{NAME}_ao.png")
    if out.get("albedo_source") and "albedo_err" not in out:
        # EMIT bake -> transfer the raw albedo (silver/dark armor + orange seams) onto the LOW's UVs
        try:
            out["maps"]["albedo"] = bake_one("EMIT", f"{NAME}_albedo.png")
        except Exception as e:
            out["albedo_bake_err"] = repr(e)
    out["bake_diag"] = bake_diag

    # export LOW fbx
    low_fbx = OUTDIR / f"{NAME}_retopo.fbx"
    bpy.ops.object.select_all(action="DESELECT"); low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.export_scene.fbx(filepath=str(low_fbx), use_selection=True, mesh_smooth_type="FACE",
                             add_leaf_bones=False)
    out["low_fbx"] = str(low_fbx)
    out["ok"] = bool(out["maps"]["normal"]) and bool(out["maps"]["ao"]) and low_fbx.exists()
except Exception:
    import traceback
    out["error"] = traceback.format_exc().splitlines()[-1]
Path(A.get("report", str(OUTDIR / f"{NAME}_handcraft.json"))).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_HANDCRAFT_DONE ok=" + str(out["ok"]) + " method=" + str(out.get("method")))
