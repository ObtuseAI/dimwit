"""Post-import verification (task 13). After a mesh is imported to UE, assert the import is CORRECT before the
technical gate passes — slot count, real (non-default) materials, collision proxy, bounds within scale
tolerance, and the Nanite usage flag. Pure stdlib: takes the EXPECTED spec + an ACTUAL dict (gathered by the
live UE bridge via ue_exec, or by an import commandlet) and returns a structured verdict. No UE dependency, so
it is unit-testable headlessly and reusable by the technical gate."""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "config" / "unreal_import_contract.json"


def _contract() -> dict:
    try:
        return json.loads(CONTRACT.read_text(encoding="utf-8")).get("post_import_verify", {})
    except Exception:
        return {}


def verify_import(spec: dict, actual: dict) -> dict:
    """spec: the candidate spec (expected material_slots, scale_cm, collision_proxy, nanite).
    actual: measured from UE { material_slots:[...], materials:[...], has_collision:bool, bounds_cm:[x,y,z],
            nanite_enabled:bool, nanite_flag_set:bool }. Returns {ok, checks:[{name,pass,detail}]}."""
    tol = float(_contract().get("bounds_tolerance_pct", 25)) / 100.0
    checks = []

    exp_slots = len(spec.get("material_slots", []) or [])
    act_slots = len(actual.get("material_slots", actual.get("materials", [])) or [])
    checks.append({"name": "material_slot_count_matches_spec",
                   "pass": exp_slots == 0 or act_slots == exp_slots,
                   "detail": f"expected {exp_slots}, got {act_slots}"})

    mats = [str(m).lower() for m in (actual.get("materials", []) or [])]
    bad = [m for m in mats if "worldgridmaterial" in m or "defaultmaterial" in m or m in ("", "none")]
    checks.append({"name": "no_default_world_grid_material", "pass": not bad,
                   "detail": f"default materials present: {bad}" if bad else "none"})

    checks.append({"name": "collision_proxy_present",
                   "pass": bool(actual.get("has_collision", spec.get("collision_proxy"))),
                   "detail": f"collision={actual.get('has_collision')}"})

    bounds = actual.get("bounds_cm")
    scale = float(spec.get("scale_cm", 0) or 0)
    if bounds and scale:
        longest = max(float(x) for x in bounds)
        ok = (1 - tol) * scale <= longest <= (1 + tol) * scale
        checks.append({"name": "bounds_within_scale_tolerance", "pass": ok,
                       "detail": f"longest={longest:.1f}cm vs scale={scale}cm (+-{int(tol*100)}%)"})
    else:
        checks.append({"name": "bounds_within_scale_tolerance", "pass": True, "detail": "no bounds/scale to check"})

    if actual.get("nanite_enabled"):
        checks.append({"name": "nanite_usage_flag_set_if_nanite", "pass": bool(actual.get("nanite_flag_set")),
                       "detail": f"nanite_flag_set={actual.get('nanite_flag_set')}"})
    else:
        checks.append({"name": "nanite_usage_flag_set_if_nanite", "pass": True, "detail": "not nanite"})

    return {"ok": all(c["pass"] for c in checks), "checks": checks}
