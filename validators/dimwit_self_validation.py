"""Dimwit self-validation regression: imports, ledger/queue schema, PATH ISOLATION from Blunder,
config JSON validity, required-tree presence, review-package presence. Stdlib-only. Exit 0 = all pass.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "pass": bool(ok), "detail": detail})


# imports
try:
    from dimwit import core, engine, review  # noqa
    from dimwit.engine import assert_dimwit_path, DimwitLedger, DimwitQueue
    check("imports", True)
except Exception as e:
    check("imports", False, str(e)); print(json.dumps(checks, indent=2)); raise SystemExit(1)

# path isolation: a Dimwit path passes, a Blunder path is refused
try:
    assert_dimwit_path(ROOT / "proofs/x.jsonl")
    refused = False
    try:
        assert_dimwit_path(r"C:\Users\developer\Desktop\Shared Folder\Obtuse\30-proof-bundles\x.jsonl")
    except RuntimeError:
        refused = True
    check("path_isolation_from_blunder", refused, "Blunder path correctly refused" if refused else "GUARD FAILED")
except Exception as e:
    check("path_isolation_from_blunder", False, str(e))

# ledger schema + append-only consistency
led = DimwitLedger(ROOT / "proofs/dimwit_asset_proof_ledger.jsonl")
cc = led.consistency_check()
check("ledger_schema", cc["schema_ok"] and cc["entry_count"] >= 1, json.dumps(cc))

# queue schema
q = DimwitQueue(ROOT / "queues/dimwit_asset_queue.jsonl").items()
check("queue_schema", all("asset_task_id" in i and "status" in i for i in q), f"{len(q)} items")

# config JSON validity
bad = []
for p in (ROOT / "config").glob("*.json"):
    try:
        json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        bad.append(f"{p.name}: {e}")
check("config_json_valid", not bad, "; ".join(bad) or f"{len(list((ROOT/'config').glob('*.json')))} configs valid")

# required subdir tree
req = ["config", "state", "memory", "queues", "proofs", "artifacts", "assets", "source_art",
       "unreal_imports", "blender_scripts", "captures", "review_packages", "reports", "bundles", "lessons", "validators"]
missing = [d for d in req if not (ROOT / d).is_dir()]
check("required_tree", not missing, "missing: " + ", ".join(missing) if missing else "all present")

# review package present for the promoted asset
rp = ROOT / "review_packages/hostile_construct_enemy_variant_001/review_manifest.json"
check("review_package_present", rp.exists(), str(rp))

# blender builder interface is headless-safe (plan_build works without bpy)
try:
    sys.path.insert(0, str(ROOT / "blender_scripts"))
    import dimwit_blender_asset_builder_interface as bb
    plan = bb.plan_build({"asset_type": "helmet", "material_slots": ["M_A", "M_B"], "scale_cm": 60})
    check("blender_interface_headless_safe", plan["mesh_metadata"]["slot_count"] == 2)
except Exception as e:
    check("blender_interface_headless_safe", False, str(e))

# ---- V2 checks: pixel-truth perception, real mesh generation, open-source registry, CLI ----
try:
    from dimwit import perception
    lane = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\Saved\ShowMeAI\WanefallGameplayLaneEnemyRead\Captures\20260625T012606Z_baseline_gameplay_lane_contact_sheet.png"
    m = perception.analyze_image(lane)
    st = perception.measure_style_compliance(m)
    blob_caught = any(h["trait"] == "black_blob" for h in st.get("hard_fails", []))
    check("perception_pixel_truth", m.get("ok") and blob_caught,
          f"lane near_black={m.get('near_black_fraction')} contrast={m.get('silhouette_contrast')} black_blob_caught={blob_caught}")
except Exception as e:
    check("perception_pixel_truth", False, str(e))

try:
    from dimwit.meshgen import generate
    meta = generate({"asset_type": "hostile_construct_enemy", "scale_cm": 270}, ROOT / "artifacts" / "selftest_mesh", "trimesh")
    tris = meta.get("measured", {}).get("triangles", 0)
    check("meshgen_real_mesh", tris > 0 and meta.get("slot_count", 0) >= 1, f"trimesh tris={tris} slots={meta.get('slot_count')}")
except Exception as e:
    check("meshgen_real_mesh", False, str(e))

try:
    reg = json.loads((ROOT / "config" / "opensource_registry.json").read_text(encoding="utf-8"))
    all_ok = all(it.get("commercial_ok") for it in reg["imported"])
    check("opensource_registry", all_ok and len(reg["imported"]) >= 4, f"{len(reg['imported'])} tools, all commercial_ok={all_ok}")
except Exception as e:
    check("opensource_registry", False, str(e))

try:
    from dimwit import cli, adapters  # noqa
    check("cli_and_adapters_import", True)
except Exception as e:
    check("cli_and_adapters_import", False, str(e))

# ---- elite-build checks (tasks 9, 2, 7, 11) ----
try:
    from dimwit.capabilities import registry as _reg
    v = _reg.verify_all()
    check("capability_registry_resolves", v["ok"] and v["count"] >= 5,
          f"{len(v['resolved'])}/{v['count']} resolve; broken={v['broken']}")
except Exception as e:
    check("capability_registry_resolves", False, str(e))

try:
    chain = led.consistency_check().get("chain", {})
    check("proof_ledger_hash_chain", chain.get("ok", False), json.dumps(chain))
except Exception as e:
    check("proof_ledger_hash_chain", False, str(e))

uem = ROOT / "ue_mcp"
check("ue_mcp_live_bridge_present",
      (uem / "server.py").exists() and (uem / "ue_bridge.py").exists() and (uem / "README.md").exists(),
      "ue_mcp server/bridge/readme present")

try:
    import tempfile as _tf
    _sp = Path(_tf.gettempdir()) / "dimwit_selftest_weapon_spec.json"
    _sp.write_text(json.dumps({"asset_type": "weapon", "scale_cm": 120, "material_slots": ["a", "b", "c"]}), encoding="utf-8")
    _res = bb.build(str(_sp), str(ROOT / "artifacts" / "selftest_weapon"))
    _built = bool((_res.get("geometry") or {}).get("exports"))
    check("per_class_builder_executable", _built, f"weapon builder mode={_res.get('mode')}")
except Exception as e:
    check("per_class_builder_executable", False, str(e))

passed = sum(1 for c in checks if c["pass"])
result = {"phase": "DIMWIT_SELF_VALIDATION", "passed": passed, "total": len(checks),
          "all_pass": passed == len(checks), "checks": checks}
print(json.dumps(result, indent=2))
sys.exit(0 if result["all_pass"] else 1)
