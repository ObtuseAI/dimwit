"""Dimwit ASSET FINISH (UE headless) — generate REAL UCX convex collision (+ LODs for non-Nanite meshes) on
produced static meshes, closing G9 (collision was faked complex-as-simple; props were single-LOD). Shippable
assets need proper collision so physics/queries don't use the render mesh. Writes artifacts/lod_collision.json.

  UnrealEditor-Cmd <uproj> -ExecutePythonScript="scripts/ue/ue_lod_collision.py assets=/Game/a,/Game/b hulls=16 lods=3 out=..."
"""
import unreal, json, sys, traceback
from pathlib import Path

A = {}
for a in sys.argv:
    if "=" in a and not a.startswith("-"):
        k, v = a.split("=", 1)
        A[k] = v
ASSETS = [s for s in A.get("assets", "").split(",") if s]
HULLS = int(A.get("hulls", 16))
MAXV = int(A.get("max_hull_verts", 32))
LODS = int(A.get("lods", 3))
OUT = Path(A.get("out", "C:/Users/developer/Documents/Dimwit/artifacts/lod_collision.json"))

sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
eal = unreal.EditorAssetLibrary
out = {"ok": False, "records": []}
try:
    for ap in ASSETS:
        rec = {"asset": ap}
        try:
            sm = unreal.load_asset(ap)
            if not isinstance(sm, unreal.StaticMesh):
                rec["error"] = f"not a StaticMesh: {type(sm).__name__ if sm else None}"
                out["records"].append(rec); continue
            is_nanite = False
            try:
                is_nanite = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
            except Exception:
                pass
            rec["nanite"] = is_nanite
            # UCX convex collision (real, not render-mesh) — works for Nanite + non-Nanite
            try:
                sub.set_convex_decomposition_collisions(sm, HULLS, MAXV, 100000)
                rec["convex_collision"] = True
            except Exception as e:
                try:    # older API fallback
                    unreal.EditorStaticMeshLibrary.set_convex_decomposition_collisions(sm, HULLS, MAXV, 100000)
                    rec["convex_collision"] = True
                except Exception:
                    rec["convex_collision"] = False
                    rec["collision_err"] = str(e)
            try:
                rec["collision_prims"] = sm.get_editor_property("body_setup").get_editor_property("agg_geom").get_editor_property("convex_elems").__len__() if sm.get_editor_property("body_setup") else None
            except Exception:
                rec["collision_prims"] = None
            # LODs only matter for non-Nanite meshes (Nanite does its own continuous LOD)
            if not is_nanite and LODS > 1:
                try:
                    opt = unreal.EditorScriptingMeshReductionOptions()
                    opt.reduction_settings = [unreal.EditorScriptingMeshReductionSettings(1.0 / (i + 1), 0)
                                              for i in range(LODS)]
                    sub.set_lods(sm, opt)
                    rec["lods_set"] = LODS
                except Exception as e:
                    rec["lods_set"] = 0
                    rec["lod_err"] = str(e)
            else:
                rec["lods_set"] = "nanite_continuous" if is_nanite else 0
            eal.save_asset(ap)
            rec["ok"] = bool(rec.get("convex_collision"))
        except Exception:
            rec["error"] = traceback.format_exc().splitlines()[-1]
        out["records"].append(rec)
    out["ok"] = bool(out["records"]) and all(r.get("ok") for r in out["records"])
except Exception:
    out["error"] = traceback.format_exc()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_LOD_COLLISION_DONE ok=" + str(out.get("ok")))
