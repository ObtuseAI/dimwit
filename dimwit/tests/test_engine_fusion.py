"""Proof that the engine promotion gate is now the WEAKEST-LINK fused confidence, not the arithmetic mean.
Stdlib + numpy/Pillow (only the wrong-identity case renders real PNGs). Run:
    python -m dimwit.tests.test_engine_fusion

These lock the three audit defects shut at the engine-checkpoint level:
  1. a high MEAN with one weak load-bearing dim must NOT promote (the headline averaging gap);
  2. a flawless render of the WRONG asset (good palette, wrong shape) must NOT promote (identity gap);
  3. declared-only data with NO measured pixels must NOT promote a strict type (fail-open gap).
And the converse: a candidate whose load-bearing dims are all genuinely measured-high DOES reach the gate.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from dimwit import engine
from dimwit.core import AssetCandidate, AssetTask, Lifecycle

_TMP = Path(tempfile.mkdtemp(prefix="dimwit_engfuse_"))


def _cand(asset_type="character", *, hero=None, lane=None, hard=None, spec=None, evidence=None):
    """Build a candidate with perception pre-populated (bypassing perceive_evidence) for precise control."""
    c = AssetCandidate(candidate_id="c0", asset_id="a0", asset_type=asset_type, iteration=0,
                       spec=spec or {"traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point",
                                                "clean_silhouette"], "hit_destroy_clarity": 0.97,
                                     "collision_proxy": "convex", "scale_cm": 270, "material_slots": ["m"],
                                     "mesh_ref": "SM_x", "tri_estimate": 100000},
                       evidence=evidence or {})
    engine.score_candidate(c)            # fills cand.scores from spec/style-law first
    perc = {}
    if hero is not None:
        perc["hero_contact_sheet"] = {"style": {"scores": hero, "hard_fails": []}}
    if lane is not None:
        perc["player_camera_contact_sheet"] = {"style": {"scores": lane, "hard_fails": hard or []}}
    perc["hard_fails"] = hard or []
    c.perception = perc
    return c


STRONG_HERO = {"silhouette_readability": 0.97, "hero_readability": 0.97}
STRONG_LANE = {"third_person_camera_readability": 0.97, "gameplay_readability": 0.97,
               "not_black_blob": 0.99, "palette_discipline": 0.98}


def test_strong_measured_reaches_gate():
    c = _cand(hero=STRONG_HERO, lane=STRONG_LANE)
    f = engine.fuse_candidate(c, None, "character")
    assert f["meets_gate"] is True, f
    assert f["confidence"] >= 0.95, f


def test_high_mean_one_weak_loadbearing_blocks():
    # silhouette_readability is load-bearing for a character; tank ONLY it. Everything else is 0.97-0.99,
    # so the arithmetic mean stays high — but the weakest-link gate must catch the one weak dim.
    weak_hero = {"silhouette_readability": 0.30, "hero_readability": 0.97}
    c = _cand(hero=weak_hero, lane=STRONG_LANE)
    mean = c.overall
    f = engine.fuse_candidate(c, None, "character")
    assert f["meets_gate"] is False, (f, "one weak load-bearing dim must cap the fused gate")
    assert f["confidence"] == 0.30, f
    assert f["binding_constraint"] == "dim:silhouette_readability", f
    # prove the mean WOULD have masked it
    assert mean > 0.70, (mean, "the mean is high precisely because 15 dims average the one weak dim away")


def test_no_pixels_strict_blocks():
    c = _cand(hero=None, lane=None)        # declared-only: no measured perception
    f = engine.fuse_candidate(c, None, "character")
    assert f["meets_gate"] is False and f["blocked"] is True, f
    assert any("perception" in r for r in f["blocked_reasons"]), f


def test_loose_type_also_fail_closed_without_pixels():
    # even a loose prop (no optics required) cannot certify without a measured silhouette
    c = _cand(asset_type="prop", hero=None, lane=None)
    f = engine.fuse_candidate(c, None, "prop")
    assert f["meets_gate"] is False and f["blocked"] is True, f


def test_wrong_identity_capture_blocks():
    # render a faithful target + a WRONG-shape capture; with a contract declaring the target, the engine
    # checkpoint must reject the wrong identity even though its palette/quality is fine.
    from PIL import Image, ImageDraw
    ref = _TMP / "ref.png"; cap = _TMP / "cap_wrong.png"
    im = Image.new("RGB", (300, 420), (40, 44, 50)); d = ImageDraw.Draw(im)
    d.ellipse([130, 40, 175, 90], fill=(150, 160, 170)); d.rectangle([120, 90, 185, 230], fill=(150, 160, 170))
    d.rectangle([122, 230, 148, 360], fill=(150, 160, 170)); d.rectangle([158, 230, 184, 360], fill=(150, 160, 170))
    im.save(ref)
    im2 = Image.new("RGB", (300, 420), (40, 44, 50)); d2 = ImageDraw.Draw(im2)
    d2.ellipse([90, 120, 210, 300], fill=(150, 160, 170)); im2.save(cap)      # wrong: one round blob

    contract = {"declares_target": True, "expected_appearance": {"reference_images": [str(ref)]}}
    c = _cand(hero=STRONG_HERO, lane=STRONG_LANE,
              evidence={"player_camera_contact_sheet": str(cap), "hero_contact_sheet": str(cap)})
    f = engine.fuse_candidate(c, contract, "character")
    assert f["meets_gate"] is False, (f, "wrong-identity capture must not reach the gate")
    assert f["target_similarity"] is not None and f["target_similarity"] < 0.85, f


def test_run_asset_task_declared_only_does_not_promote():
    # end-to-end through the driver: a strict character with declared-only seed evidence must land in
    # NEEDS_RECURSION (cannot certify), never PROMOTED_TO_REVIEW.
    led = engine.DimwitLedger(_TMP / "ledger.jsonl")
    task = AssetTask(asset_id="char_declonly", asset_type="character", source_kind="design_need")
    seed_spec = {"traits": ["dark_alien", "teal_wane_energy", "red_or_orange_weak_point", "clean_silhouette"],
                 "collision_proxy": "convex", "scale_cm": 270, "material_slots": ["m"], "mesh_ref": "SM_x",
                 "tri_estimate": 100000, "camera_readability": 0.9, "gameplay_readability": 0.9,
                 "hit_destroy_clarity": 0.9}
    seed_ev = {"hero_contact_sheet": "", "player_camera_contact_sheet": "",
               "provenance": {"license_class": "generated_concept", "source_prompt": "p"}}
    rep = engine.run_asset_task(task, seed_spec, seed_ev, led, run_id="r1")
    assert rep.final_state != Lifecycle.PROMOTED_TO_REVIEW, rep.final_state
    assert rep.fused.get("meets_gate") is False, rep.fused
    promo = next(g for g in rep.gates if g["gate"] == "promotion")
    assert promo["gate_kind"] == "fused_weakest_link", promo
    assert promo["verdict"] == "FAIL", promo


def test_loop_stops_when_fused_gate_met_not_mean():
    # a candidate that already meets the fused gate should make the loop stop at iteration 1 (no needless churn)
    c = _cand(hero=STRONG_HERO, lane=STRONG_LANE)
    loop = engine.recursive_mutation_loop(c, contract=None, asset_type="character")
    assert loop["reached_fused_gate"] is True, loop
    assert loop["best_fused"]["meets_gate"] is True, loop["best_fused"]
    assert loop["iterations"] == 1, ("already-passing seed must not be mutated further", loop["iterations"])


def test_loop_keeps_best_by_weakest_link_via_render_fn():
    # seed measures a weak load-bearing dim; a render_fn that "re-renders" stronger pixels each iteration lets
    # the loop recover and reach the fused gate — proving keep-best follows the weakest-link, not the mean.
    seed = _cand(hero={"silhouette_readability": 0.30, "hero_readability": 0.9}, lane=STRONG_LANE)

    def render_fn(cand):
        # simulate a real re-render that fixes the binding constraint (silhouette) on later iterations
        cand.perception = {"hero_contact_sheet": {"style": {"scores": STRONG_HERO, "hard_fails": []}},
                           "player_camera_contact_sheet": {"style": {"scores": STRONG_LANE, "hard_fails": []}},
                           "hard_fails": []}

    loop = engine.recursive_mutation_loop(seed, render_fn=render_fn, contract=None, asset_type="character")
    assert loop["reached_fused_gate"] is True, loop
    assert loop["best_fused"]["meets_gate"] is True, loop["best_fused"]


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e)); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e)); print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
