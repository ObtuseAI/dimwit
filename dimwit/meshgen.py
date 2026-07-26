"""Dimwit mesh generation — REAL asset geometry from a spec.

Two backends:
  * 'blender'  : writes a WANEFALL-native blockout build script and runs Blender 5.x HEADLESS, exporting
                 FBX (the WANEFALL import format) + GLB. This is the production DCC path.
  * 'trimesh'  : pure-Python procedural blockout exported to GLB/OBJ (fast, deterministic, no Blender).

Either way the result is a REAL mesh file whose tri count / bounds / watertightness are MEASURED from the
exported geometry (trimesh) — not declared. Generated assets land under Dimwit/artifacts and (optionally)
the UE staging source path; nothing is auto-promoted into the active game.

Deps: trimesh + numpy (permissive). Blender located via DIMWIT_BLENDER env or the default install path.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import trimesh

DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"


def blender_exe() -> str | None:
    cand = os.environ.get("DIMWIT_BLENDER", DEFAULT_BLENDER)
    return cand if Path(cand).exists() else None


# ----------------------------------------------------------------- WANEFALL hostile-construct blockout recipe
# Boxes in centimetres, feet at z=0, front faces -X. (cx,cy,cz, sx,sy,sz, slot)
# slots: 0=dark body, 1=red core/eye, 2=teal accent
def _construct_parts(scale: float) -> list:
    P = [
        ("LegL", -8, -24, 46, 30, 34, 92, 0), ("LegR", -8, 24, 46, 30, 34, 92, 0),
        ("Hips", -4, 0, 98, 52, 68, 30, 0), ("Torso", 4, 0, 142, 66, 86, 78, 0),
        ("ShoulderL", 2, -48, 178, 36, 36, 26, 0), ("ShoulderR", 2, 48, 178, 36, 36, 26, 0),
        ("ArmL", 8, -54, 138, 22, 22, 70, 0), ("ArmR", 8, 54, 138, 22, 22, 70, 0),
        ("Neck", 4, 0, 190, 22, 28, 20, 0), ("Head", 8, 0, 206, 36, 44, 36, 0),
        ("CoreChest", 26, 0, 146, 20, 26, 26, 1), ("Eye", 30, 0, 206, 12, 14, 10, 1),
        ("VentL", 22, -22, 150, 6, 8, 36, 2), ("VentR", 22, 22, 150, 6, 8, 36, 2),
    ]
    return [(n, np.array([cx, cy, cz]) * scale, np.array([sx, sy, sz]) * scale, slot) for (n, cx, cy, cz, sx, sy, sz, slot) in P]


def _class_parts(asset_type: str, scale: float) -> list:
    """Per-class blockout recipes (task 11). Slot 0=dark body, 1=red core/weak-point, 2=teal Wane accent.
    Enemy/construct/dummy/unknown fall back to the humanoid construct (byte-identical to the prior default)."""
    a = (asset_type or "").lower()
    if any(k in a for k in ("weapon", "rifle", "gun")):
        P = [("Body", 0, 0, 0, 140, 18, 26, 0), ("Grip", -30, 0, -22, 18, 16, 40, 0),
             ("Stock", -60, 0, 2, 40, 14, 22, 0), ("Barrel", 70, 0, 4, 40, 10, 10, 0),
             ("Sight", 10, 0, 20, 30, 6, 8, 0), ("WaneStrip", 20, 0, -8, 80, 4, 6, 2)]
    elif any(k in a for k in ("vehicle", "hull", "skimmer")):
        P = [("Hull", 0, 0, 20, 220, 120, 40, 0), ("Nose", 110, 0, 18, 40, 70, 30, 0),
             ("Canopy", 20, 0, 46, 60, 60, 28, 0), ("ThrusterL", -90, -50, 16, 40, 24, 24, 0),
             ("ThrusterR", -90, 50, 16, 40, 24, 24, 0), ("WaneVentL", -70, -50, 16, 30, 8, 8, 2),
             ("WaneVentR", -70, 50, 16, 30, 8, 8, 2)]
    elif any(k in a for k in ("helmet", "head")):
        P = [("Dome", 0, 0, 0, 46, 52, 44, 0), ("Jaw", 6, 0, -26, 40, 44, 20, 0),
             ("Visor", 24, 0, 4, 10, 40, 16, 2), ("EyeCore", 30, 0, 6, 8, 10, 8, 1)]
    elif "board" in a:
        P = [("Deck", 0, 0, 0, 200, 46, 10, 0), ("RailL", 0, -22, 0, 200, 4, 6, 2),
             ("RailR", 0, 22, 0, 200, 4, 6, 2), ("Core", 0, 0, -4, 40, 20, 4, 1)]
    elif any(k in a for k in ("cover", "prop", "panel", "kit")):
        P = [("Slab", 0, 0, 40, 80, 80, 80, 0), ("Trim", 0, 0, 82, 84, 84, 6, 2)]
    else:
        return _construct_parts(scale)        # enemy/construct/dummy/unknown -> humanoid (unchanged)
    return [(n, np.array([cx, cy, cz]) * scale, np.array([sx, sy, sz]) * scale, slot)
            for (n, cx, cy, cz, sx, sy, sz, slot) in P]


def _measure(mesh: trimesh.Trimesh) -> dict:
    b = mesh.bounds
    ext = (b[1] - b[0])
    # height = longest axis (robust to Blender Z-up vs glTF/FBX Y-up export conversion) for an upright asset
    return {
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "bounds_cm": [round(float(x), 2) for x in ext.tolist()],
        "height_cm": round(float(max(ext)), 2),
        "watertight": bool(mesh.is_watertight),
        "volume_cm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
    }


def generate_trimesh(spec: dict, out_dir: Path) -> dict:
    """Pure-Python WANEFALL blockout -> GLB + OBJ, with MEASURED geometry metrics."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    scale = float(spec.get("scale_cm", 270)) / 270.0
    parts, slot_meshes = _class_parts(spec.get("asset_type"), scale), {0: [], 1: [], 2: []}
    for _, c, s, slot in parts:
        box = trimesh.creation.box(extents=s)
        box.apply_translation(c)
        slot_meshes[slot].append(box)
    scene = trimesh.Scene()
    slot_names = {0: "dark_body", 1: "red_core", 2: "teal_accent"}
    merged_all = []
    for slot, meshes in slot_meshes.items():
        if not meshes:
            continue
        g = trimesh.util.concatenate(meshes)
        scene.add_geometry(g, geom_name=slot_names[slot])
        merged_all.append(g)
    merged = trimesh.util.concatenate(merged_all)
    glb = out / "mesh.glb"; obj = out / "mesh.obj"
    scene.export(glb)
    merged.export(obj)
    metrics = _measure(merged)
    meta = {"backend": "trimesh", "asset_type": spec.get("asset_type"), "scale_cm": spec.get("scale_cm", 270),
            "material_slots": ["dark_body", "red_core", "teal_accent"], "slot_count": 3,
            "exports": {"glb": str(glb), "obj": str(obj)}, "measured": metrics}
    (out / "mesh_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


_BLENDER_SCRIPT = r'''
import bpy, json, sys, math
argv = sys.argv[sys.argv.index("--")+1:]
spec = json.loads(open(argv[0], encoding="utf-8").read())
out_dir = argv[1]
scale = float(spec.get("scale_cm", 270))/270.0
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
def mat(name, rgba):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf: bsdf.inputs["Base Color"].default_value = rgba
    return m
DARK = mat("M_WaneEnemyDarkBody", (0.05,0.06,0.07,1)); RED = mat("M_WaneEnemyCoreRed", (0.55,0.0,0.0,1)); TEAL = mat("M_WaneEnemyTealAccent", (0.0,0.55,0.6,1))
parts = [
 ("LegL",-8,-24,46,30,34,92,0),("LegR",-8,24,46,30,34,92,0),("Hips",-4,0,98,52,68,30,0),
 ("Torso",4,0,142,66,86,78,0),("ShoulderL",2,-48,178,36,36,26,0),("ShoulderR",2,48,178,36,36,26,0),
 ("ArmL",8,-54,138,22,22,70,0),("ArmR",8,54,138,22,22,70,0),("Neck",4,0,190,22,28,20,0),
 ("Head",8,0,206,36,44,36,0),("CoreChest",26,0,146,20,26,26,1),("Eye",30,0,206,12,14,10,1),
 ("VentL",22,-22,150,6,8,36,2),("VentR",22,22,150,6,8,36,2)]
objs=[]
for n,cx,cy,cz,sx,sy,sz,slot in parts:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx*scale*0.01, cy*scale*0.01, cz*scale*0.01))
    o=bpy.context.active_object; o.name=n; o.scale=(sx*scale*0.01, sy*scale*0.01, sz*scale*0.01)
    o.data.materials.append([DARK,RED,TEAL][slot]); objs.append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.join()
joined = bpy.context.active_object; joined.name = "SM_WaneConstruct_Dimwit"
fbx = out_dir + "/mesh.fbx"; glb = out_dir + "/mesh.glb"
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True)
try: bpy.ops.export_scene.gltf(filepath=glb, use_selection=True, export_format='GLB')
except Exception as e: print("glb export skipped", e)
tris=sum(len(p.data.polygons) for p in [joined])
open(out_dir+"/blender_done.json","w").write(json.dumps({"fbx":fbx,"object":joined.name,"materials":3}))
print("BLENDER_OK")
'''


def generate_blender(spec: dict, out_dir: Path, timeout: int = 180) -> dict:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    exe = blender_exe()
    if not exe:
        return {"backend": "blender", "ok": False, "error": "Blender not found", "fallback": "trimesh"}
    spec_path = out / "_spec.json"; spec_path.write_text(json.dumps(spec), encoding="utf-8")
    script = out / "_build.py"; script.write_text(_BLENDER_SCRIPT, encoding="utf-8")
    cmd = [exe, "--background", "--python", str(script), "--", str(spec_path), str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"backend": "blender", "ok": False, "error": "timeout"}
    ok = "BLENDER_OK" in r.stdout
    meta = {"backend": "blender", "ok": ok, "exe": exe, "stdout_tail": r.stdout.strip().splitlines()[-3:] if r.stdout else []}
    glb = out / "mesh.glb"
    if glb.exists():
        try:
            m = trimesh.load(glb, force="mesh")
            meta["measured"] = _measure(m)
        except Exception as e:
            meta["measure_error"] = str(e)
    meta["exports"] = {k: str(out / f"mesh.{k}") for k in ("fbx", "glb") if (out / f"mesh.{k}").exists()}
    (out / "mesh_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def generate(spec: dict, out_dir: Path, backend: str = "blender") -> dict:
    if backend == "blender":
        meta = generate_blender(spec, out_dir)
        if meta.get("ok"):
            return meta
        # graceful fallback so generation never hard-blocks the loop
        tri = generate_trimesh(spec, out_dir)
        tri["blender_fallback_reason"] = meta.get("error", "blender failed")
        return tri
    return generate_trimesh(spec, out_dir)


if __name__ == "__main__":
    import sys
    bk = sys.argv[2] if len(sys.argv) > 2 else "blender"
    print(json.dumps(generate({"asset_type": "hostile_construct_enemy", "scale_cm": 270}, Path(sys.argv[1]), bk), indent=2))
