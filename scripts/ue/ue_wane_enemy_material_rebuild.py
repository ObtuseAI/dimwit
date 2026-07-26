"""Rebuild WANE enemy material graphs so active character proof cannot fall back to white/checker."""
import json
import traceback
from pathlib import Path

import unreal


OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/wane_enemy_material_rebuild_result.json")
MATERIAL_SPECS = [
    {
        "path": "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4",
        "base": (0.035, 0.042, 0.050),
        "emissive": (0.0, 0.012, 0.018),
        "metallic": 0.0,
        "roughness": 0.62,
        "skeletal": True,
        "nanite": True,
    },
    {
        "path": "/Game/Wanefall/Materials/M_WaneEnemyCoreRed",
        "base": (0.55, 0.035, 0.015),
        "emissive": (0.95, 0.08, 0.02),
        "metallic": 0.0,
        "roughness": 0.45,
        "skeletal": True,
        "nanite": True,
    },
    {
        "path": "/Game/Wanefall/Materials/M_WaneEnemyTealAccent",
        "base": (0.0, 0.45, 0.52),
        "emissive": (0.0, 0.85, 1.0),
        "metallic": 0.0,
        "roughness": 0.38,
        "skeletal": True,
        "nanite": True,
    },
]

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def set_usage(mat, rec, skeletal, nanite):
    for name, enabled in (("used_with_skeletal_mesh", skeletal), ("used_with_nanite", nanite)):
        if not enabled:
            continue
        try:
            rec.setdefault("usage_before", {})[name] = bool(mat.get_editor_property(name))
            mat.set_editor_property(name, True)
            rec.setdefault("usage_after", {})[name] = bool(mat.get_editor_property(name))
        except Exception as exc:
            rec.setdefault("usage_errors", []).append(f"{name}: {exc}")


def const3(mat, rgb, x, y):
    expr = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, x, y)
    expr.set_editor_property("constant", unreal.LinearColor(float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0))
    return expr


def const1(mat, value, x, y):
    expr = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, x, y)
    expr.set_editor_property("r", float(value))
    return expr


def connect(rec, expr, output, prop, label):
    try:
        ok = bool(mel.connect_material_property(expr, output, prop))
        rec.setdefault("connected", {})[label] = ok
    except Exception as exc:
        rec.setdefault("connect_errors", {})[label] = str(exc)


def rebuild(spec):
    mat = unreal.load_asset(spec["path"])
    rec = {"path": spec["path"], "loaded": bool(mat), "class": type(mat).__name__ if mat else None}
    if not isinstance(mat, unreal.Material):
        rec["ok"] = False
        rec["error"] = "not a Material asset"
        return rec

    set_usage(mat, rec, skeletal=spec["skeletal"], nanite=spec["nanite"])
    base = const3(mat, spec["base"], -500, -200)
    metal = const1(mat, spec["metallic"], -500, -20)
    rough = const1(mat, spec["roughness"], -500, 120)
    emissive = const3(mat, spec["emissive"], -500, 300)

    connect(rec, base, "", unreal.MaterialProperty.MP_BASE_COLOR, "BaseColor")
    connect(rec, metal, "", unreal.MaterialProperty.MP_METALLIC, "Metallic")
    connect(rec, rough, "", unreal.MaterialProperty.MP_ROUGHNESS, "Roughness")
    connect(rec, emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR, "EmissiveColor")
    rec["params"] = {
        "base": spec["base"],
        "emissive": spec["emissive"],
        "metallic": spec["metallic"],
        "roughness": spec["roughness"],
    }
    try:
        mel.recompile_material(mat)
        rec["compiled"] = True
    except Exception as exc:
        rec["compiled"] = False
        rec["compile_error"] = str(exc)
    try:
        rec["saved"] = bool(eal.save_asset(spec["path"], False))
    except Exception as exc:
        rec["saved"] = False
        rec["save_error"] = str(exc)
    rec["ok"] = (
        rec.get("compiled") is True
        and rec.get("saved") is True
        and all(rec.get("connected", {}).values())
        and (not spec["skeletal"] or rec.get("usage_after", {}).get("used_with_skeletal_mesh") is True)
        and (not spec["nanite"] or rec.get("usage_after", {}).get("used_with_nanite") is True)
    )
    return rec


def main():
    result = {"ok": False, "materials": []}
    try:
        result["materials"] = [rebuild(spec) for spec in MATERIAL_SPECS]
        result["ok"] = all(rec.get("ok") for rec in result["materials"])
    except Exception:
        result["error"] = traceback.format_exc()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"DIMWIT_WANE_ENEMY_MATERIAL_REBUILD ok={result['ok']} out={OUT}")


main()
