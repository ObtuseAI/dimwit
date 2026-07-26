"""Dimwit Blender builder interface (contract + reference adapter).

This is the GENERALIZED entry point Dimwit calls to turn an asset_spec.json into mesh art. It defines a
single contract used by every asset class (enemy, helmet, weapon, vehicle shell, prop, cover, ...), and a
reference adapter that, for V1, can delegate to the existing WANEFALL hostile-construct Blender script.

Run inside Blender:  blender --background --python dimwit_blender_asset_builder_interface.py -- <asset_spec.json> <out_dir>
Stub mode (no Blender): importing this module and calling plan_build(spec) returns the build plan + the
mesh_metadata.json contract WITHOUT requiring bpy, so the engine can validate the contract headlessly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---- the contract every asset class must satisfy ----
BUILD_CONTRACT = {
    "input": "asset_spec.json",
    "outputs": [".blend", ".fbx_or_glb", "mesh_metadata.json"],
    "origin_convention": "feet at z=0, single welded mesh, front faces -X (toward player)",
    "scale_units": "centimeters",
    "material_slots": "ordered; index matches asset_spec.material_slots",
    "collision_proxy_suggestion": "convex_decomp | capsule+box | box (by asset class)",
}

# per-asset-class default build recipe (generalization point — extend as new classes are added)
CLASS_RECIPES = {
    "hostile_construct_enemy": {"base": "humanoid_construct", "weak_point": "central_red_core", "delegate": "SourceAssets/Blender/scripts/gen_hostile_construct.py"},
    "helmet": {"base": "head_shell", "weak_point": None},
    "weapon": {"base": "rifle_blockout", "weak_point": None},
    "vehicle_shell": {"base": "hull_blockout", "weak_point": None},
    "waneboard_shell": {"base": "board_blockout", "weak_point": None},
    "cover_piece": {"base": "panel_blockout", "weak_point": None},
    "arena_prop": {"base": "prop_blockout", "weak_point": None},
    "target_dummy": {"base": "humanoid_construct", "weak_point": "central_red_core"},
}


def plan_build(spec: dict) -> dict:
    """Pure: return the build plan + the mesh_metadata contract for this spec (no Blender needed)."""
    atype = spec.get("asset_type", "arena_prop")
    recipe = CLASS_RECIPES.get(atype, {"base": "prop_blockout", "weak_point": None})
    slots = spec.get("material_slots", ["M_Default"])
    return {
        "asset_type": atype,
        "recipe": recipe,
        "contract": BUILD_CONTRACT,
        "mesh_metadata": {
            "scale_cm": spec.get("scale_cm", 200),
            "material_slots": slots,
            "slot_count": len(slots),
            "origin": "feet_z0_front_minus_x",
            "collision_proxy": spec.get("collision_proxy", "box"),
            "weak_point": recipe.get("weak_point"),
        },
        "delegate_script": recipe.get("delegate"),
    }


def build(spec_path: str, out_dir: str) -> dict:
    """Build entry point. With bpy available, delegate/recipe builds the mesh; without bpy, write the
    plan + mesh_metadata so the engine can validate the contract headlessly (V1 foundation mode)."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = plan_build(spec)
    (out / "mesh_metadata.json").write_text(json.dumps(plan["mesh_metadata"], indent=2), encoding="utf-8")
    (out / "build_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    try:
        import bpy  # noqa: F401  (only present inside Blender)
        plan["blender_available"] = True
        # Real mesh build / delegate would run here in a Blender session.
        plan["mode"] = "blender_session"
    except Exception:
        plan["blender_available"] = False
        # task 11: headless still produces REAL per-class geometry via the in-Dimwit trimesh backend
        # (per-class recipes in meshgen._class_parts) — no longer a contract-only no-op.
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from dimwit.meshgen import generate_trimesh
            meta = generate_trimesh(spec, out)
            plan["geometry"] = {"backend": "trimesh", "exports": meta.get("exports"),
                                "measured": meta.get("measured"), "material_slots": meta.get("material_slots")}
            plan["mode"] = "headless_trimesh_build"
        except Exception as e:
            plan["mode"] = f"headless_contract_only ({e})"
    return plan


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    spec_path = args[0] if args else "asset_spec.json"
    out_dir = args[1] if len(args) > 1 else "."
    print(json.dumps(build(spec_path, out_dir), indent=2))
