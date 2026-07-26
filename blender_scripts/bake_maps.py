"""Dimwit BAKE MAPS (Blender headless) — translate dense HIGH-poly detail onto the clean retopo'd LOW-poly via
selected-to-active Cycles baking: NORMAL (tangent) + AO. This is the "handcrafted result" step — the low-poly
keeps clean deformable quad topology while the baked maps carry the full sculpt-grade surface detail (the
classic AAA high->low pipeline), so the in-engine asset reads handcrafted, not auto-genned.

  blender --background --python bake_maps.py -- high=<dense.glb> low=<retopo.fbx> out=<dir> res=2048
"""
import bpy, sys, json
from pathlib import Path

A = {}
for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []):
    if "=" in a:
        k, v = a.split("=", 1)
        A[k] = v
HIGH, LOW = A["high"], A["low"]
OUTDIR = Path(A.get("out", "artifacts/bake"))
RES = int(A.get("res", 2048))
SAMPLES = int(A.get("samples", 16))
OUTDIR.mkdir(parents=True, exist_ok=True)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for d in (bpy.data.meshes, bpy.data.objects, bpy.data.images, bpy.data.materials):
        for b in list(d):
            try:
                d.remove(b)
            except Exception:
                pass


def imp(path):
    p = path.lower()
    if p.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True)
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in BEFORE]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def bake_one(low, btype, fname):
    img = bpy.data.images.new(fname, RES, RES, alpha=False,
                              float_buffer=(btype == "NORMAL"))
    mat = low.data.materials[0] if low.data.materials else bpy.data.materials.new("bake_mat")
    if not low.data.materials:
        low.data.materials.append(mat)
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    mat.node_tree.nodes.active = node
    for n in mat.node_tree.nodes:
        n.select = (n == node)
    bpy.ops.object.bake(type=btype, use_selected_to_active=True, cage_extrusion=0.05,
                        max_ray_distance=0.10, margin=8)
    p = str(OUTDIR / fname)
    img.filepath_raw = p
    img.file_format = "PNG"
    img.save()
    return p


out = {"ok": False, "high": HIGH, "low": LOW, "maps": {}}
BEFORE = []
try:
    clear()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        scene.cycles.device = "CPU"
        scene.cycles.samples = SAMPLES
    except Exception:
        pass
    BEFORE = list(bpy.context.scene.objects)
    low = imp(LOW)
    low.name = "LOWPOLY"
    BEFORE = list(bpy.context.scene.objects)
    high = imp(HIGH)
    high.name = "HIGHPOLY"
    # selected-to-active: high selected, low active+selected
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    out["maps"]["normal"] = bake_one(low, "NORMAL", "T_normal.png")
    out["maps"]["ao"] = bake_one(low, "AO", "T_ao.png")
    out["ok"] = all(Path(p).exists() for p in out["maps"].values())
except Exception:
    import traceback
    out["error"] = traceback.format_exc().splitlines()[-1]
Path(A.get("report", str(OUTDIR / "bake_report.json"))).write_text(json.dumps(out, indent=2), encoding="utf-8")
print("DIMWIT_BAKE_DONE ok=" + str(out["ok"]))
