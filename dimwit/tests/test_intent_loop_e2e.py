"""End-to-end proof of the hardened intent-contract loop through the real driver + ledger + review packager.
Stdlib + numpy/Pillow. Run:  python -m dimwit.tests.test_intent_loop_e2e

Asserts the whole chain the user asked for:
  1. the intent contract (declared picture/goals/design) is AUTHORED and hash-ANCHORED in the proof ledger
     BEFORE any pixel — and the ledger chain proves it predates the run (anti-retrofit by construction);
  2. run_asset_task consumes the contract; a declared-only build (no real captures) CANNOT promote — the
     fused weakest-link gate is BLOCKED and the run is NEEDS_RECURSION, never PROMOTED_TO_REVIEW;
  3. the run's ledger entry BINDS the intent_hash + records fused_meets_gate=False (auditable);
  4. the human review package carries an intent-vs-actual diff that names the miss;
  5. once a capture exists on disk, re-authoring the intent is REFUSED (anti-retrofit, fail-closed).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit import spec_author
from dimwit.core import AssetTask, Lifecycle
from dimwit.engine import DimwitLedger, run_asset_task
from dimwit.ledger.hashchain import chain_verify
from dimwit.review import build_review_package

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_e2e_"))


def _ref(path):
    im = Image.new("RGB", (300, 420), (40, 44, 50)); d = ImageDraw.Draw(im)
    d.ellipse([130, 40, 175, 90], fill=(150, 160, 170)); d.rectangle([120, 90, 185, 230], fill=(150, 160, 170))
    d.rectangle([122, 230, 148, 360], fill=(150, 160, 170)); d.rectangle([158, 230, 184, 360], fill=(150, 160, 170))
    d.rectangle([135, 120, 170, 150], fill=(220, 120, 40)); im.save(path); return str(path)


def test_full_loop_declared_only_blocks_and_audits():
    root = _TMP / "ws"
    assets = root / "assets"
    ledger = DimwitLedger(root / "proofs" / "ledger.jsonl")
    ref = _ref(_TMP / "hero_ref.png")
    asset_id = "e2e_char_01"

    # (1) AUTHOR the intent contract first; anchor it in the ledger BEFORE any pixel exists
    authored = spec_author.author_intent_contract(
        asset_id, "character", ref, declared_intent="dark alien melee enemy, teal spinal vein, orange weak-point",
        provenance={"license_class": "owned_reference", "reference_license": "owned", "source_prompt": "concept"},
        ledger=ledger, run_id="e2e", out_root=assets)
    assert authored["ok"] and authored["anchored"], authored
    contract = authored["contract"]
    assert ledger.entries()[0]["state"] == Lifecycle.INTENT_DECLARED, "intent must be the FIRST ledger entry"
    assert ledger.entries()[0]["intent_hash"] == contract["intent_hash"]

    # (2)+(3) run the build with declared-only evidence (no real captures) -> must NOT promote; intent bound
    task = AssetTask(asset_id=asset_id, asset_type="character", source_kind="design_need")
    seed_spec = {"traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
                 "collision_proxy": "convex", "scale_cm": 270, "material_slots": ["m"], "mesh_ref": "SM_x",
                 "tri_estimate": 100000, "camera_readability": 0.95, "gameplay_readability": 0.95,
                 "hit_destroy_clarity": 0.95}
    seed_ev = {"provenance": {"license_class": "owned_reference", "reference_license": "owned",
                              "source_prompt": "concept"}}
    report = run_asset_task(task, seed_spec, seed_ev, ledger, run_id="e2e", contract=contract)
    assert report.final_state != Lifecycle.PROMOTED_TO_REVIEW, report.final_state
    assert report.final_state == Lifecycle.NEEDS_RECURSION, report.final_state
    assert report.fused.get("meets_gate") is False and report.fused.get("blocked") is True, report.fused

    run_entry = ledger.entries()[-1]
    assert run_entry["intent_hash"] == contract["intent_hash"], "run entry must bind the anchored intent_hash"
    assert run_entry["fused_meets_gate"] is False, run_entry
    assert Lifecycle.INTENT_DECLARED in [e["state"] for e in ledger.entries()]

    # ledger chain integrity + anti-retrofit ORDER (intent declared strictly before the run terminal)
    chk = chain_verify(ledger.entries())
    assert chk["ok"], chk
    states = [e["state"] for e in ledger.entries()]
    assert states.index(Lifecycle.INTENT_DECLARED) < len(states) - 1, "intent must precede the run entry"

    # (4) the human review package surfaces the declared-vs-actual diff and names the miss
    pkg = build_review_package(root, task.to_dict(), report.to_dict(), contract=contract, copy_evidence=False)
    import json
    man = json.loads(Path(pkg["manifest"]).read_text("utf-8"))
    diff = man["intent_vs_actual"]
    assert diff["applicable"] is True and diff["actual_meets_gate"] is False, diff
    assert diff["declared_summary"].startswith("dark alien"), diff
    assert diff["intent_hash"] == contract["intent_hash"], diff
    assert any("INTENT MISS" in w for w in man["known_weaknesses"]), man["known_weaknesses"]
    assert man["fused_meets_gate"] is False, man

    # (5) once a capture exists on disk, re-authoring intent is REFUSED (anti-retrofit, fail-closed)
    (assets / asset_id).mkdir(parents=True, exist_ok=True)
    (assets / asset_id / "player_camera_contact_sheet.png").write_bytes(b"rendered-after-the-fact")
    retro = spec_author.author_intent_contract(
        asset_id, "character", ref,
        provenance={"license_class": "owned_reference", "reference_license": "owned", "source_prompt": "p"},
        ledger=ledger, out_root=assets)
    assert retro["ok"] is False and retro["blocked"] is True, retro
    assert "already exist" in retro["reason"], retro


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
