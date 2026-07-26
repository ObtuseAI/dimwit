"""Proof tests for the weakest-link fusion primitive (dimwit/confidence.py).

Stdlib-only, no pytest dependency. Run:  python -m dimwit.tests.test_confidence
Each test asserts one un-gameable property of fuse(); the module exits non-zero on any failure so it
can be wired into a proof gate. The headline test is `test_mean_would_pass_but_min_fails` — the exact
defect the hardened loop exists to close (a flat mean averaging one weak load-bearing dim away).
"""
from __future__ import annotations

import sys

from dimwit.confidence import fuse, signal, HARD_FAIL_FLOOR
from dimwit.pipelines.validation import resolve_asset_type_floors

CHAR = resolve_asset_type_floors("character")
# character floors: domains {perception,optics,design_md,intent_conformance};
# load-bearing dims {silhouette_readability, third_person_camera_readability, hit_destroy_state_clarity};
# capture stages {plan,execute,hero,player_camera,motion}; confidence_floor 0.95; target_match_floor 0.85.

_STAGES = ["plan", "execute", "hero", "player_camera", "motion"]


def _full_strong(value=0.99, target=0.99):
    """A complete, fully-covered, all-strong record set for a character build — the only shape that
    should ever be allowed to meet the gate. Tests perturb ONE thing away from this."""
    recs = []
    # required domains, each with a load-bearing dim where applicable
    recs.append(signal("perception", value, dimension="silhouette_readability", stage="hero", id="percep_sil"))
    recs.append(signal("perception", value, dimension="hit_destroy_state_clarity", stage="hero", id="percep_hit"))
    recs.append(signal("optics", value, dimension="third_person_camera_readability", stage="player_camera", id="optics_tpc"))
    recs.append(signal("design_md", value, stage="plan", id="design_lint"))
    recs.append(signal("intent_conformance", value, stage="execute", id="intent"))
    # the declared-target identity match
    recs.append(signal("perception", target, stage="hero", is_target_similarity=True, id="target_sim"))
    # cover every required capture stage with at least one live signal
    present = {r.get("stage") for r in recs}
    for st in _STAGES:
        if st not in present:
            recs.append(signal("perception", value, stage=st, id=f"stage_{st}"))
    return recs


def _contract(**over):
    c = {"target_reference": "ref/ekris_hero.png", "declares_target": True}
    c.update(over)
    return c


# --------------------------------------------------------------------------- the tests
def test_all_strong_meets_gate():
    r = fuse(_full_strong(0.99, 0.99), _contract(), CHAR)
    assert r["confidence"] is not None, r
    assert r["meets_gate"] is True, r
    assert r["confidence"] >= 0.95, r


def test_mean_would_pass_but_min_fails():
    """THE regression. 15 dims at 1.0 and one load-bearing dim at 0.30 -> arithmetic mean ~0.956 (would
    sail past 0.95) but the weakest-link MIN is 0.30 -> NOT promotable. This is what the old
    sum(scores)/len(scores) could not catch and what disfigured assets exploited."""
    recs = _full_strong(1.0, 1.0)
    # tank exactly one load-bearing dim
    recs.append(signal("perception", 0.30, dimension="silhouette_readability", stage="hero", id="weak_sil"))
    r = fuse(recs, _contract(), CHAR)
    # mean sanity: had we averaged, it would have passed
    flat = [1.0] * 15 + [0.30]
    assert sum(flat) / len(flat) > 0.95, "test premise wrong: mean should exceed gate"
    # weakest-link truth:
    assert r["confidence"] == 0.30, r
    assert r["meets_gate"] is False, r
    assert "silhouette_readability" in r["binding_constraint"], r


def test_single_weak_dim_cannot_reach_099():
    recs = _full_strong(0.99, 0.99)
    recs.append(signal("optics", 0.94, dimension="third_person_camera_readability", stage="player_camera", id="weak_tpc"))
    r = fuse(recs, _contract(confidence_floor=0.99), CHAR)
    assert r["confidence"] == 0.94, r
    assert r["meets_gate"] is False, r   # 0.94 < 0.99 gate


def test_hard_fail_clamps_to_floor():
    recs = _full_strong(0.99, 0.99)
    recs.append(signal("optics", 0.0, dimension="third_person_camera_readability", stage="player_camera",
                       hard_fail=True, id="magenta_blocker"))
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] <= HARD_FAIL_FLOOR, r
    assert r["meets_gate"] is False, r
    assert any("hard_fail" in c for c in r["clamps"]), r


def test_zero_validator_required_domain_is_none():
    recs = [r for r in _full_strong(0.99, 0.99) if r["domain"] != "optics"]
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None, r
    assert r["blocked"] is True, r
    assert any("optics" in br for br in r["blocked_reasons"]), r


def test_missing_perception_blocks():
    recs = [r for r in _full_strong(0.99, 0.99) if r["domain"] != "perception"]
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None and r["blocked"], r
    assert any("perception" in br for br in r["blocked_reasons"]), r


def test_blocked_signal_in_required_domain_blocks():
    """A perception lib that is present but could not measure (numpy/Pillow missing at runtime) reports a
    BLOCKED signal -> the whole result blocks; it is never scored as free confidence."""
    recs = _full_strong(0.99, 0.99)
    recs.append(signal("optics", None, stage="player_camera", blocked=True, id="glm_unavailable"))
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None and r["blocked"], r


def test_unmeasured_load_bearing_dim_is_none():
    """Drop the hit_destroy_state_clarity measurement entirely. The dim is load-bearing, so an unmeasured
    one cannot be silently treated as fine -> None (cannot certify)."""
    recs = [r for r in _full_strong(0.99, 0.99) if r.get("dimension") != "hit_destroy_state_clarity"]
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None and r["blocked"], r
    assert any("hit_destroy_state_clarity" in br for br in r["blocked_reasons"]), r


def test_missing_required_capture_stage_blocks():
    recs = [r for r in _full_strong(0.99, 0.99) if r.get("stage") != "motion"]
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None and r["blocked"], r
    assert any("motion" in br for br in r["blocked_reasons"]), r


def test_target_similarity_below_floor_blocks_gate():
    """A build can be visually strong on every dim yet be the WRONG character. target_similarity below the
    identity floor (0.85) must stop promotion even when every other member is high."""
    recs = _full_strong(0.99, 0.80)   # target sim only 0.80, below 0.85 floor
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] == 0.80, r        # it is the binding member
    assert r["meets_gate"] is False, r
    assert r["binding_constraint"] == "target_similarity", r


def test_declared_target_but_unmeasured_blocks():
    recs = [r for r in _full_strong(0.99, 0.99) if not r.get("is_target_similarity")]
    r = fuse(recs, _contract(), CHAR)
    assert r["confidence"] is None and r["blocked"], r


def test_author_can_only_raise_floor():
    # author tries to LOWER the gate to 0.80 -> ignored, frozen 0.95 wins
    recs = _full_strong(0.96, 0.96)
    r_low = fuse(recs, _contract(confidence_floor=0.80), CHAR)
    assert r_low["gate"] == 0.95, r_low
    assert r_low["meets_gate"] is True, r_low      # 0.96 >= 0.95
    # author RAISES the gate to 0.99 -> honored, now 0.96 fails
    r_high = fuse(recs, _contract(confidence_floor=0.99), CHAR)
    assert r_high["gate"] == 0.99, r_high
    assert r_high["meets_gate"] is False, r_high


def test_ratchet_to_099_is_strict():
    strong = fuse(_full_strong(0.99, 0.99), _contract(confidence_floor=0.99), CHAR)
    assert strong["meets_gate"] is True, strong
    near = fuse(_full_strong(0.985, 0.99), _contract(confidence_floor=0.99), CHAR)
    assert near["meets_gate"] is False, near       # 0.985 < 0.99


def test_unknown_asset_type_is_strict_fail_closed():
    floors = resolve_asset_type_floors("a_brand_new_type_we_never_defined")
    # an under-covered build for an unknown type must block (strictest row demands optics + perception etc.)
    recs = [signal("perception", 0.99, dimension="silhouette_readability", stage="hero", id="x")]
    r = fuse(recs, _contract(), floors)
    assert r["confidence"] is None and r["blocked"], r


# --------------------------------------------------------------------------- runner
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, e))
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, e))
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
