import json, os, copy
import pytest
from dimwit.pipelines import mode_contract as mc

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mode_contract")

def _green():
    with open(os.path.join(FIX, "green_proof.json")) as f:
        return json.load(f)

def test_load_green_proof_ok():
    p = mc.load_proof(os.path.join(FIX, "green_proof.json"))
    assert p["complete"] is True
    # 13 arena + 4 large + 3 arcade + 1 UI + 2 demo (wanetrial, practice) = 23
    assert p["mode_count"] == len(p["modes"]) == 23

def test_missing_file_raises():
    with pytest.raises(mc.ModeProofError):
        mc.load_proof(os.path.join(FIX, "does_not_exist.json"))

def test_all_suites_green_on_fixture():
    p = _green()
    for check in (mc.check_arena_suite, mc.check_large_suite, mc.check_arcade_suite,
                  mc.check_ui_foundation, mc.check_wanetrial, mc.check_practice,
                  mc.check_demo_covered, mc.check_recompute_all):
        ok, detail = check(p)
        assert ok, f"{check.__name__} failed: {detail}"

def test_recompute_catches_fabricated_pass():
    p = copy.deepcopy(_green())
    # a mode claims pass:true but its raw fields say it never went live
    dm = next(m for m in p["modes"] if m["name"] == "arena.dm_1v1")
    dm["pass"] = True
    dm["fields"]["went_live"] = "false"
    ok, detail = mc.check_recompute_all(p)
    assert not ok and "arena.dm_1v1" in detail

def test_wanetrial_second_chance_violation_fails():
    p = copy.deepcopy(_green())
    wt = next(m for m in p["modes"] if m["name"] == "trial.wanetrial")
    wt["fields"]["second_chance_before_finish"] = "false"
    ok, detail = mc.check_wanetrial(p)
    assert not ok

def test_practice_resolving_a_winner_fails():
    p = copy.deepcopy(_green())
    pr = next(m for m in p["modes"] if m["name"] == "practice.range")
    pr["fields"]["winner"] = "0"
    pr["fields"]["is_over"] = "true"
    ok, detail = mc.check_practice(p)
    assert not ok

def test_missing_demo_mode_fails_coverage():
    p = copy.deepcopy(_green())
    p["modes"] = [m for m in p["modes"] if m["name"] != "practice.range"]
    ok, detail = mc.check_demo_covered(p)
    assert not ok and "practice.range" in detail


def test_extraction_kia_bad_reset_fails_large_suite():
    p = copy.deepcopy(_green())
    kia = next(m for m in p["modes"] if m["name"] == "extraction.kia")
    kia["reset_ok"] = False
    ok, detail = mc.check_large_suite(p)
    assert not ok and "extraction.kia" in detail
    ok2, detail2 = mc.check_recompute_all(p)
    assert not ok2 and "extraction.kia" in detail2


def test_ui_foundation_flipped_bool_field_fails():
    p = copy.deepcopy(_green())
    ui = next(m for m in p["modes"] if m["name"] == "ui.foundation")
    ui["fields"]["nav_ok"] = "false"
    ok, detail = mc.check_ui_foundation(p)
    assert not ok and "ui.foundation" in detail


def test_arcade_mangled_result_no_winner_fails():
    p = copy.deepcopy(_green())
    ac = next(m for m in p["modes"] if m["name"] == "arcade.waneclash")
    ac["result"] = "IN_PROGRESS"
    ac["fields"]["winner"] = "-1"
    ok, detail = mc.check_arcade_suite(p)
    assert not ok and "arcade.waneclash" in detail


def test_arena_negative_winner_string_still_fails_despite_win_token():
    """Adversarial: the C++ emits result = f"SIDE_{WinnerSide()}_WIN" even when
    WinnerSide() == -1, so a naive "WIN" in result substring check is vacuously
    true. Field-driven resolution must key off fields.winner, not the result
    string, so this non-resolving mode still fails the contract."""
    p = copy.deepcopy(_green())
    dm = next(m for m in p["modes"] if m["name"] == "arena.dm_1v1")
    dm["result"] = "SIDE_-1_WIN"
    dm["fields"]["winner"] = "-1"
    dm["pass"] = True  # reported pass is fabricated/stale -- must not be trusted
    ok, detail = mc.check_arena_suite(p)
    assert not ok and "arena.dm_1v1" in detail
    ok2, detail2 = mc.check_recompute_all(p)
    assert not ok2 and "arena.dm_1v1" in detail2


def test_battle_royale_not_last_standing_fails():
    p = copy.deepcopy(_green())
    br = next(m for m in p["modes"] if m["name"] == "br.waneroyale")
    br["fields"]["alive"] = "2"
    ok, detail = mc.check_large_suite(p)
    assert not ok and "br.waneroyale" in detail


def test_extraction_success_all_terminal_flags_false_fails():
    p = copy.deepcopy(_green())
    ex = next(m for m in p["modes"] if m["name"] == "extraction.success")
    ex["fields"]["success"] = "false"
    ex["fields"]["dead"] = "false"
    ex["fields"]["timed_out"] = "false"
    ok, detail = mc.check_large_suite(p)
    assert not ok and "extraction.success" in detail


def test_arcade_wanerush_not_finished_fails():
    p = copy.deepcopy(_green())
    wr = next(m for m in p["modes"] if m["name"] == "arcade.wanerush")
    wr["fields"]["finished"] = "false"
    ok, detail = mc.check_arcade_suite(p)
    assert not ok and "arcade.wanerush" in detail


def test_load_proof_rejects_non_dict_root(tmp_path):
    bad_file = tmp_path / "list_root.json"
    bad_file.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(mc.ModeProofError):
        mc.load_proof(str(bad_file))


def test_harvest_failure_blocks_all_nine_mode_contract_validators(monkeypatch):
    """MODE_CONTRACT_V1's core guarantee: harvest failure -> every one of the 9 v_mode_contract_*
    validators reports BLOCKED, never PASS. This was previously only verified manually.

    Monkeypatches mode_contract.run_commandlet_and_harvest to raise ModeContractBlocked (simulating
    a commandlet/UE failure) and clears the process-wide _HARVEST_CACHE so the failure is forced
    fresh. Each of the 9 v_mode_contract_* validators (imported directly from validation_registry,
    the same functions the live registry wires into Validator objects) is invoked with a plain
    ValidationContext -- the lightest-weight invocation that still exercises the real
    harvest -> BlockedError path, mirroring how ValidationSuite._run_one catches BlockedError and
    records state="BLOCKED" (never PASS, never a silently-passed check)."""
    from dimwit.pipelines import validation_registry as reg
    from dimwit.pipelines.validation import ValidationContext
    from dimwit.pipelines.base import BlockedError

    def _boom():
        raise mc.ModeContractBlocked("simulated harvest failure (commandlet/UE unavailable)")

    monkeypatch.setattr(mc, "run_commandlet_and_harvest", _boom)
    mc._HARVEST_CACHE.clear()

    validators = [
        reg.v_mode_contract_proof_present,
        reg.v_mode_contract_arena_suite,
        reg.v_mode_contract_large_suite,
        reg.v_mode_contract_arcade_suite,
        reg.v_mode_contract_ui_foundation,
        reg.v_mode_contract_wanetrial_second_chance,
        reg.v_mode_contract_practice_range,
        reg.v_mode_contract_demo_modes_covered,
        reg.v_mode_contract_recompute,
    ]
    assert len(validators) == 9, "MODE_CONTRACT_V1 registers exactly 9 validators"

    ctx = ValidationContext()
    try:
        for v in validators:
            with pytest.raises(BlockedError, match="simulated harvest failure"):
                v(ctx)
    finally:
        mc._HARVEST_CACHE.clear()
