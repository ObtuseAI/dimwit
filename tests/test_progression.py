import json
from pathlib import Path

from dimwit.pipelines import progression

GOLDENS = Path(__file__).resolve().parents[1] / "dimwit" / "goldens" / "progression"


def test_schema_versioned_passes_on_v1():
    payload = json.loads((GOLDENS / "profile_v1_current.json").read_text())
    ok, detail = progression.check_schema_versioned(payload)
    assert ok, detail


def test_schema_versioned_fails_on_missing_version():
    payload = json.loads((GOLDENS / "profile_v0_legacy.json").read_text())
    ok, _ = progression.check_schema_versioned(payload)
    assert not ok  # a live v1 save must carry schema_version


def test_v0_migration_roundtrips():
    v0 = json.loads((GOLDENS / "profile_v0_legacy.json").read_text())
    ok, detail = progression.migrate_and_validate(v0)
    assert ok, detail


def test_earned_from_telemetry_passes_on_consistent_proof():
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    ok, detail = progression.check_earned_from_telemetry(proof)
    assert ok, detail


def test_earned_from_telemetry_fails_on_fabricated_xp():
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    proof["account_xp_after"] = proof["account_xp_after"] + 999999
    ok, _ = progression.check_earned_from_telemetry(proof)
    assert not ok


def test_earned_from_telemetry_fails_on_fabricated_kills():
    # inflate kills without touching xp_granted -> recompute disagrees with the stored grant.
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    proof["kills"] = proof["kills"] + 50
    ok, _ = progression.check_earned_from_telemetry(proof)
    assert not ok


def test_anti_farm_cap_enforced():
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    proof["kills"] = 100000  # would blow the cap
    ok, detail = progression.check_anti_farm(proof)
    assert ok, detail  # recomputed grant must equal the cap, not 100000*weight


def test_challenges_advance_from_events():
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    ok, detail = progression.check_challenges(proof)
    assert ok, detail


def test_challenges_fail_on_fabricated_progress():
    proof = json.loads((GOLDENS / "apply_proof_sample.json").read_text())
    proof["challenge_daily_kills_progress"] = 9999
    ok, _ = progression.check_challenges(proof)
    assert not ok


def test_cumulative_challenges_tracks_and_clamps():
    # cumulative kills 4, 4, 4 -> progress 4, 8, 10 (clamped at target 10), monotonic
    proofs = [
        {"match_id": "botmatch_0", "kills": 4, "challenge_daily_kills_progress": 4},
        {"match_id": "botmatch_1", "kills": 4, "challenge_daily_kills_progress": 8},
        {"match_id": "botmatch_2", "kills": 4, "challenge_daily_kills_progress": 10},
    ]
    ok, detail = progression.compute_cumulative_challenges(proofs)
    assert ok, detail


def test_cumulative_challenges_fails_on_wrong_progress():
    proofs = [
        {"match_id": "botmatch_0", "kills": 4, "challenge_daily_kills_progress": 4},
        {"match_id": "botmatch_1", "kills": 4, "challenge_daily_kills_progress": 4},  # should be 8
    ]
    ok, _ = progression.compute_cumulative_challenges(proofs)
    assert not ok


def test_level_for_xp_curve():
    # thresholds mirror LevelForXp: L2=1000, L3=3000, L4=6000, L5=10000
    assert progression.level_for_xp(0) == 1
    assert progression.level_for_xp(999) == 1
    assert progression.level_for_xp(1000) == 2
    assert progression.level_for_xp(2999) == 2
    assert progression.level_for_xp(3000) == 3
    assert progression.level_for_xp(6000) == 4
    assert progression.level_for_xp(10000) == 5
