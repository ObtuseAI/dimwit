"""Probe Blender FBX scale encoding for rigged WANEFALL exports.

This diagnostic imports a rig FBX, bakes object transforms, exports several FBX
scale-option variants, re-imports each, and records object scales. It is not a
production pipeline; it exists to pin down the exporter setting before changing
rig_to_mannequin.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in argv if "=" in kv}
SRC = Path(A.get("in", "")).resolve()
OUT = Path(A.get("out", "artifacts/fbx_scale_probe")).resolve()


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials):
        for datablock in list(coll):
            try:
                coll.remove(datablock)
            except Exception:
                pass


def import_fbx(path: Path) -> None:
    bpy.ops.import_scene.fbx(
        filepath=str(path),
        ignore_leaf_bones=True,
        automatic_bone_orientation=False,
    )


def scene_objects() -> tuple[list, list]:
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    return meshes, arms


def apply_transforms() -> None:
    meshes, arms = scene_objects()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in arms + meshes:
        obj.select_set(True)
    if arms:
        bpy.context.view_layer.objects.active = arms[0]
    elif meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()


def object_scale_report() -> list[dict]:
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


def export_variant(path: Path, **opts) -> None:
    meshes, arms = scene_objects()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes + arms:
        obj.select_set(True)
    if arms:
        bpy.context.view_layer.objects.active = arms[0]
    bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        add_leaf_bones=False,
        mesh_smooth_type="FACE",
        bake_anim=False,
        object_types={"ARMATURE", "MESH"},
        **opts,
    )


def inspect_import(path: Path) -> list[dict]:
    clear_scene()
    import_fbx(path)
    return object_scale_report()


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    variants = [
        ("default", {}),
        ("no_unit", {"apply_unit_scale": False}),
        ("scale_units", {"apply_scale_options": "FBX_SCALE_UNITS"}),
        ("scale_all", {"apply_scale_options": "FBX_SCALE_ALL"}),
        ("custom_no_unit", {"apply_unit_scale": False, "apply_scale_options": "FBX_SCALE_CUSTOM"}),
        ("all_no_unit", {"apply_unit_scale": False, "apply_scale_options": "FBX_SCALE_ALL"}),
    ]
    report = {"src": str(SRC), "out": str(OUT), "variants": []}
    for name, opts in variants:
        clear_scene()
        import_fbx(SRC)
        before = object_scale_report()
        apply_transforms()
        baked = object_scale_report()
        out_fbx = OUT / f"{SRC.stem}_{name}.fbx"
        export_variant(out_fbx, **opts)
        imported = inspect_import(out_fbx)
        report["variants"].append({
            "name": name,
            "opts": opts,
            "path": str(out_fbx),
            "before": before,
            "baked": baked,
            "reimported": imported,
        })
    report_path = OUT / f"{SRC.stem}_scale_probe.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("DIMWIT_FBX_SCALE_PROBE " + json.dumps({"report": str(report_path), "variants": len(variants)}))
    return report


if __name__ == "__main__":
    main()
