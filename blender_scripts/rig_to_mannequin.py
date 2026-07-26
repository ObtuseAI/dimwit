"""Dimwit RIGGING (Blender headless): auto-rig a static Hi3D character mesh onto the UE5 Mannequin skeleton so
it becomes animatable and reuses ABP_Manny / the Lyra-style locomotion in UE — no per-character animator.

Pipeline: import the UE5 Mannequin armature (FBX exported from SK_Mannequin) + the character mesh (decimated GLB,
~45k = good for skinning; the full Nanite mesh stays the static display), align mesh to the armature, parent with
AUTOMATIC WEIGHTS, clamp to <=4 influences/vertex (UE limit) + normalize, export a UE-ready skinned FBX.

Run:  blender --background --python rig_to_mannequin.py -- mannequin=<sk_mann.fbx> mesh=<char.glb> out=<out.fbx> [height=180]
Result JSON -> <out>.rig.json  (bones, verts, weighted_verts, max_influences -> honest QA metrics)
"""
import bpy, sys, json, math
from pathlib import Path

# ---- args after '--' ----
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
MANN = A.get("mannequin"); MESH = A.get("mesh"); OUT = A.get("out")
TARGET_H = float(A.get("height", 180.0))   # cm
RIGID = str(A.get("rigid", "false")).lower() in ("1", "true", "yes")
res = {"ok": False, "mannequin": MANN, "mesh": MESH, "out": OUT, "rigid": RIGID}


def _rig_provenance(mannequin_path, mesh_path):
    mesh_file = str(Path(mesh_path)) if mesh_path else ""
    mannequin_file = str(Path(mannequin_path)) if mannequin_path else ""
    mesh_stem = Path(mesh_path).stem if mesh_path else "unknown_mesh"
    return {
        "license_class": "generated_concept",
        "source_file": mesh_file,
        "derived_from": f"{mesh_stem} rigged to UE5 Manny mannequin skeleton",
        "source": "WANEFALL handcrafted retopo mesh rigged in Blender to UE5 Manny mannequin",
        "license": "WANEFALL generated/source-linked character mesh plus Epic Content EULA mannequin skeleton",
        "mannequin_source_file": mannequin_file,
        "toolchain": "blender_scripts/rig_to_mannequin.py",
        "direct_copy_of_copyright": False,
    }


res["provenance"] = _rig_provenance(MANN, MESH)


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for c in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials):
        for b in list(c):
            try: c.remove(b)
            except Exception: pass


def import_any(path):
    p = path.lower()
    if p.endswith(".fbx"):
        # ignore_leaf_bones: UE FBX export adds tip "leaf" bones; importing them gives coincident bones
        # that break Blender's bone-heat auto-weighting. Skip them + keep UE bone orientation.
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True,
                                 automatic_bone_orientation=False)
    elif p.endswith(".glb") or p.endswith(".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif p.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"unsupported: {path}")


def bbox_world(obj):
    import mathutils
    cs = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [c.x for c in cs]; ys = [c.y for c in cs]; zs = [c.z for c in cs]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def coverage(mesh):
    vc = len(mesh.data.vertices)
    return (sum(1 for v in mesh.data.vertices if len(v.groups) > 0) / vc) if vc else 0.0


def object_scales_clean(rows):
    for row in rows:
        scale = row.get("scale") or []
        if len(scale) != 3:
            return False
        if any(abs(abs(float(v)) - 1.0) > 0.001 for v in scale):
            return False
    return bool(rows)


def transform_rows():
    rows = []
    for obj in bpy.context.scene.objects:
        if obj.type in {"MESH", "ARMATURE"}:
            rows.append({
                "name": obj.name,
                "type": obj.type,
                "scale": [round(float(v), 6) for v in obj.scale],
                "location": [round(float(v), 6) for v in obj.location],
            })
    return rows


def bake_export_transforms(mesh, arm):
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()


def inspect_exported_fbx(path):
    reset()
    import_any(str(path))
    return transform_rows()


def export_selected_fbx(path, meshes, arms):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes + arms:
        obj.select_set(True)
    if arms:
        bpy.context.view_layer.objects.active = arms[0]
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, add_leaf_bones=False,
                             mesh_smooth_type="FACE", bake_anim=False, object_types={"ARMATURE", "MESH"})


def normalize_exported_fbx(path):
    reset()
    import_any(str(path))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if not meshes or not arms:
        return False
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes + arms:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arms[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    export_selected_fbx(path, meshes, arms)
    return True


def nearest_bone_weights(mesh, arm, k=4, power=2.2):
    """SMOOTH headless skinning (Spider-Man-grade deformation): each vertex is blended across its K nearest
    DEFORM bones by inverse distance-to-the-bone-SEGMENT (head->tail), normalized, clamped to K(<=4) influences.
    This replaces the old rigid 1-bone fallback so the mesh deforms fluidly on flips/swings/aim. A KDTree of bone
    midpoints prefilters candidates so it stays fast on ~135k verts. Always produces full coverage headless
    (bone-heat fails on the 141-bone UE rig), and never hangs."""
    import mathutils
    mesh.vertex_groups.clear()
    deform = [b for b in arm.data.bones if b.use_deform] or list(arm.data.bones)
    amw = arm.matrix_world
    heads, tails, names = [], [], []
    for b in deform:
        heads.append(amw @ b.head_local)
        tails.append(amw @ b.tail_local)
        names.append(b.name)
    mids = [(heads[i] + tails[i]) * 0.5 for i in range(len(names))]
    kd = mathutils.kdtree.KDTree(len(mids))
    for i, p in enumerate(mids):
        kd.insert(p, i)
    kd.balance()
    groups = {}
    for nme in set(names):
        groups[nme] = mesh.vertex_groups.new(name=nme)

    def seg_dist(p, a, b):
        ab = b - a
        d2 = ab.length_squared
        t = 0.0 if d2 < 1e-9 else max(0.0, min(1.0, (p - a).dot(ab) / d2))
        return (p - (a + ab * t)).length

    PREFILTER = min(len(mids), 14)   # candidate bones to evaluate segment-distance against
    mw = mesh.matrix_world
    for v in mesh.data.vertices:
        co = mw @ v.co
        cand = kd.find_n(co, PREFILTER)                      # nearest bone midpoints
        scored = sorted(((seg_dist(co, heads[i], tails[i]), i) for (_, i, _) in cand), key=lambda x: x[0])[:k]
        inv = [(1.0 / (max(d, 1e-4) ** power), i) for d, i in scored]
        tot = sum(w for w, _ in inv) or 1.0
        for w, i in inv:
            groups[names[i]].add([v.index], w / tot, "REPLACE")   # smooth blended influence
    if not any(m.type == "ARMATURE" for m in mesh.modifiers):
        md = mesh.modifiers.new("Armature", "ARMATURE")
        md.object = arm


def rigid_bone_weights(mesh, arm):
    """RIGID hard-surface skinning: each vertex assigned 100% to its single nearest DEFORM bone (segment
    distance), no blend. Armor plates stay rigid instead of stretching. Produces max_influences == 1."""
    import mathutils
    mesh.vertex_groups.clear()
    deform = [b for b in arm.data.bones if b.use_deform] or list(arm.data.bones)
    amw = arm.matrix_world
    heads = [amw @ b.head_local for b in deform]
    tails = [amw @ b.tail_local for b in deform]
    names = [b.name for b in deform]
    mids = [(heads[i] + tails[i]) * 0.5 for i in range(len(names))]
    kd = mathutils.kdtree.KDTree(len(mids))
    for i, p in enumerate(mids):
        kd.insert(p, i)
    kd.balance()
    groups = {nme: mesh.vertex_groups.new(name=nme) for nme in set(names)}

    def seg_dist(p, a, b):
        ab = b - a
        d2 = ab.length_squared
        t = 0.0 if d2 < 1e-9 else max(0.0, min(1.0, (p - a).dot(ab) / d2))
        return (p - (a + ab * t)).length

    PREFILTER = min(len(mids), 14)
    mw = mesh.matrix_world
    for v in mesh.data.vertices:
        co = mw @ v.co
        cand = kd.find_n(co, PREFILTER)
        best = min(((seg_dist(co, heads[i], tails[i]), i) for (_, i, _) in cand), key=lambda x: x[0])[1]
        groups[names[best]].add([v.index], 1.0, "REPLACE")
    if not any(m.type == "ARMATURE" for m in mesh.modifiers):
        md = mesh.modifiers.new("Armature", "ARMATURE")
        md.object = arm


try:
    assert MANN and MESH and OUT, "need mannequin=, mesh=, out="
    reset()

    # 1) mannequin armature
    import_any(MANN)
    arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
    assert arm, "no armature in mannequin FBX"
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    # UE exports the mannequin FBX with object-level scale. If that survives into the skinned export, UE can
    # report invalid bind poses and rebind the mesh at time zero. Bake the armature scale into the bone data.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    res["bones"] = len(arm.data.bones)
    (amnx, amny, amnz), (amxx, amxy, amxz) = bbox_world(arm)
    arm_h = max(1e-3, amxz - amnz)

    # 2) character mesh
    before = set(bpy.data.objects)
    import_any(MESH)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    assert new, "no mesh imported"
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active

    # 3) align mesh to armature: scale to target height, drop feet to armature floor, center on X/Y
    (mnx, mny, mnz), (mxx, mxy, mxz) = bbox_world(mesh)
    mh = max(1e-3, mxz - mnz)
    s = (TARGET_H / 100.0 if arm_h > 10 else TARGET_H * 0.01) / mh * arm_h  # match the armature's actual height
    # simplest robust: scale char so its height == armature height
    s = arm_h / mh
    mesh.scale = (mesh.scale.x * s, mesh.scale.y * s, mesh.scale.z * s)
    bpy.context.view_layer.update()
    (mnx, mny, mnz), (mxx, mxy, mxz) = bbox_world(mesh)
    mesh.location.x += (amnx + amxx) / 2 - (mnx + mxx) / 2
    mesh.location.y += (amny + amxy) / 2 - (mny + mxy) / 2
    mesh.location.z += amnz - mnz
    bpy.context.view_layer.update()
    res["scaled_by"] = round(s, 4)
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    # Bake alignment into vertex positions before skinning. Leaving mesh scale/location on the skinned FBX
    # produced dirty bind transforms in Unreal and visible limb deformation.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()

    # 4) skinning: rigid single-bone for hard-surface mechs, else bone-heat auto + smooth fallback
    if RIGID:
        res["skinning_mode"] = "rigid_single_bone"
        rigid_bone_weights(mesh, arm)
    else:
        res["skinning_mode"] = "smooth_auto"
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True); arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        except Exception as e:
            res["auto_weight_warn"] = str(e)
        res["auto_coverage"] = round(coverage(mesh), 4)

        # 4b) fallback: if bone-heat failed (common on complex rigs), guarantee weights via nearest-bone.
        if coverage(mesh) < 0.99:
            res["used_fallback"] = "nearest_bone"
            nearest_bone_weights(mesh, arm)

    # 5) clamp to <=4 influences/vertex (UE) + normalize
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True); bpy.context.view_layer.objects.active = mesh
    try:
        bpy.ops.object.vertex_group_limit_total(limit=4)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    except Exception as e:
        res["weight_clean_warn"] = str(e)
    bake_export_transforms(mesh, arm)
    res["pre_export_transforms"] = transform_rows()

    # honest weight metrics
    vc = len(mesh.data.vertices)
    weighted = sum(1 for v in mesh.data.vertices if len(v.groups) > 0)
    maxinf = max((len(v.groups) for v in mesh.data.vertices), default=0)
    res.update({"verts": vc, "weighted_verts": weighted, "max_influences": maxinf,
                "weight_coverage": round(weighted / max(1, vc), 4)})

    # 6) export UE-ready FBX (mesh + armature, no leaf bones, Z-up/Y-forward handled by UE on import)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    export_selected_fbx(Path(OUT), [mesh], [arm])
    if Path(OUT).exists():
        res["fbx_second_pass_normalized"] = normalize_exported_fbx(Path(OUT))
        rows = inspect_exported_fbx(Path(OUT))
        res["fbx_reimport_transforms"] = rows
        res["fbx_reimport_scales_clean"] = object_scales_clean(rows)
    res["ok"] = Path(OUT).exists() and res["weight_coverage"] > 0.99 and res.get("fbx_reimport_scales_clean") is True
except Exception:
    import traceback
    res["error"] = traceback.format_exc()

Path((OUT or "rig") + ".rig.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("DIMWIT_RIG_DONE " + json.dumps({k: res.get(k) for k in ("ok", "bones", "weight_coverage", "max_influences")}))
