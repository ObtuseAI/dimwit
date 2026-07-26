"""Dump graph-level data for WANE materials that are rendering white in SceneCapture."""
import json
import traceback
from pathlib import Path

import unreal


OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/material_swatch_diagnostics/graphs.json")
MATERIALS = [
    "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4",
    "/Game/Wanefall/Materials/M_WaneEnemyDarkBody",
    "/Game/Wanefall/Materials/M_WaneEnemyCoreRed",
    "/Game/Wanefall/Materials/M_WaneEnemyTealAccent",
    "/Game/Wanefall/Dimwit/Materials/M_WaneSurface",
]


def path_name(obj):
    try:
        return obj.get_path_name() if obj else None
    except Exception:
        return None


def simple_value(value):
    if hasattr(value, "get_path_name"):
        return value.get_path_name()
    if hasattr(value, "r") and hasattr(value, "g") and hasattr(value, "b"):
        return {
            "r": float(value.r),
            "g": float(value.g),
            "b": float(value.b),
            "a": float(getattr(value, "a", 1.0)),
        }
    return str(value)


def expression_info(expr):
    info = {
        "class": type(expr).__name__,
        "path": path_name(expr),
    }
    for prop in (
        "desc",
        "r",
        "g",
        "b",
        "a",
        "constant",
        "emissive_color",
        "material_function",
    ):
        try:
            value = expr.get_editor_property(prop)
        except Exception:
            continue
        info[prop] = simple_value(value)
    return info


def main():
    result = {"ok": False, "materials": []}
    try:
        for path in MATERIALS:
            mat = unreal.load_asset(path)
            rec = {"path": path, "loaded": bool(mat), "class": type(mat).__name__ if mat else None}
            if mat:
                for prop in ("used_with_skeletal_mesh", "used_with_nanite", "blend_mode", "shading_model"):
                    try:
                        rec[prop] = simple_value(mat.get_editor_property(prop))
                    except Exception:
                        pass
                try:
                    exprs = list(mat.get_editor_property("expressions"))
                except Exception as exc:
                    rec["expressions_error"] = str(exc)
                    exprs = []
                rec["expression_count"] = len(exprs)
                rec["expressions"] = [expression_info(expr) for expr in exprs]
            result["materials"].append(rec)
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"DIMWIT_MATERIAL_GRAPH_DIAGNOSTICS ok={result['ok']} out={OUT}")


main()
