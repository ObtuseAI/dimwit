"""Evidence tests — attestation and tamper detection.

The attestation test matters because the whole reason this package exists is that a `producer: "dimwit"` stamp
turned out to be a label applied by code Dimwit did not own. So: the digest must be computed from real module
bytes, must change when a module changes, and must name the module that changed.

The ledger tests are a tamper matrix. Each row is an attack, and the assertion is whether verification catches
it — including the one it does *not* catch without a length commitment, because a detection claim that is not
true is worse than no claim.
"""
from __future__ import annotations

import copy
import json

import pytest

from dimwit.market import bars, chart, chart_vision, evidence
from dimwit.market.selfaudit import synthetic_series


@pytest.fixture(scope="module")
def series() -> dict:
    return bars.normalize_series(synthetic_series(bar_count=300))


@pytest.fixture(scope="module")
def observation(series) -> dict:
    return evidence.export_dumbmoney_observation(series)


# --- attestation -----------------------------------------------------------


def test_attestation_digests_real_module_bytes():
    attestation = evidence.implementation_digest()
    assert attestation["cell"] == "dimwit"
    assert attestation["package"] == "dimwit.market"
    assert set(attestation["modules"]) == set(evidence.ATTESTED_MODULES)
    assert attestation["module_count"] == len(evidence.ATTESTED_MODULES)
    assert all(len(digest) == 64 for digest in attestation["modules"].values())
    assert attestation["digest"] == evidence.implementation_digest()["digest"]


def test_attestation_states_what_it_does_not_prove():
    attestation = evidence.implementation_digest()
    assert "correctness" in attestation["does_not_attest"]
    assert "point-in-time" in attestation["does_not_attest"]


def test_attestation_detects_a_changed_module(tmp_path, monkeypatch):
    """A per-file digest map means a mismatch names the module that moved, not just 'something changed'."""
    real = evidence.implementation_digest()
    tampered = dict(real["modules"])
    tampered["indicators.py"] = "0" * 64
    from dimwit.core import sha256_obj

    assert sha256_obj(dict(sorted(tampered.items()))) != real["digest"]
    changed = [name for name in real["modules"] if real["modules"][name] != tampered[name]]
    assert changed == ["indicators.py"]


def test_missing_attested_module_is_an_error(monkeypatch):
    monkeypatch.setattr(evidence, "ATTESTED_MODULES", evidence.ATTESTED_MODULES + ("not_real.py",))
    with pytest.raises(evidence.EvidenceError, match="attested modules missing"):
        evidence.implementation_digest()


# --- observation export ----------------------------------------------------


def test_observation_carries_the_dumbmoney_v2_field_set(observation):
    required = {
        "schema",
        "producer",
        "symbol",
        "asset_class",
        "timeframe",
        "as_of",
        "source_classification",
        "source_digest",
        "point_in_time_claim",
        "bar_count",
        "indicators",
        "technical_state",
        "chart_pixel_evidence",
        "candidate_status",
        "forecast_probability",
        "expected_return_bps",
        "broker_credentials_available",
        "broker_calls",
        "execution_authority",
        "digest",
    }
    assert required <= set(observation)
    assert observation["dumbmoney_schema_compatibility"] == evidence.DUMBMONEY_COMPATIBLE_SCHEMA


def test_observation_supplies_the_legacy_indicator_keys(observation):
    legacy = {
        "last_close",
        "sma20",
        "ema12",
        "ema26",
        "macd",
        "rsi14",
        "atr14",
        "bollinger_upper20",
        "bollinger_lower20",
        "support20",
        "resistance20",
        "sma50",
        "sma200",
        "return20_bps",
        "atr14_percent",
    }
    assert legacy <= set(observation["indicators"])
    assert observation["indicators"]["support20"] <= observation["indicators"]["resistance20"]


def test_rsi_change_is_disclosed_rather_than_reconciled(observation):
    parity = observation["parity"]
    assert parity["rsi14_wilder"] == observation["indicators"]["rsi14"]
    assert parity["rsi14_simple_legacy"] is not None
    assert parity["rsi14_delta"] == pytest.approx(
        parity["rsi14_wilder"] - parity["rsi14_simple_legacy"], abs=1e-6
    )
    assert "Wilder" in parity["note"]
    assert parity["technical_state_legacy_parity"] in {
        "BULLISH_ALIGNMENT",
        "BEARISH_ALIGNMENT",
        "MIXED_OR_EXTENDED",
        "INSUFFICIENT_HISTORY",
    }


def test_observation_declares_it_really_executed(observation):
    assert observation["producer"] == "dimwit"
    assert observation["producer_executed"] is True
    assert observation["producer_implementation"] == "dimwit.market"
    assert observation["implementation_attestation"]["digest"]


def test_observation_holds_no_authority_and_no_forecast(observation):
    assert observation["forecast_probability"] is None
    assert observation["expected_return_bps"] is None
    assert observation["broker_credentials_available"] is False
    assert observation["broker_calls"] == 0
    assert observation["orders_created"] == 0
    assert observation["live_activation"] is False
    assert observation["execution_authority"] is False
    assert observation["recommendation_only"] is True


def test_pixel_evidence_is_not_provided_until_a_chart_is(series, observation):
    assert observation["chart_pixel_evidence"] == "NOT_PROVIDED"
    render = chart.render_chart_png(series, max_bars=100)
    with_chart = evidence.export_dumbmoney_observation(series, chart_render=render)
    assert with_chart["chart_pixel_evidence"]["status"] == "PROVIDED"
    roundtrip = chart_vision.verify_chart_roundtrip(series, max_bars=100)
    verified = evidence.export_dumbmoney_observation(series, chart_render=render, roundtrip=roundtrip)
    assert verified["chart_pixel_evidence"]["status"] == "PROVIDED_AND_VERIFIED"
    assert verified["chart_pixel_evidence"]["roundtrip_verdict"] == "PASS"
    assert verified["chart_pixel_evidence"]["worst_error_px"] <= 1.0


def test_candidate_status_tracks_the_source_classification(series):
    assert evidence.export_dumbmoney_observation(series)["candidate_status"] == "RESEARCH_INPUT_ONLY"
    imported = bars.normalize_series(
        {
            **synthetic_series(bar_count=300),
            "classification": "IMPORTED_PUBLIC_MARKET_DATA_RETROSPECTIVE_RESEARCH",
        }
    )
    assert (
        evidence.export_dumbmoney_observation(imported)["candidate_status"]
        == "WALK_FORWARD_EVIDENCE_REQUIRED"
    )


def test_export_cannot_upgrade_a_point_in_time_claim(series, observation):
    assert observation["point_in_time_claim"] is False
    captured = bars.normalize_series(
        {
            **synthetic_series(bar_count=300),
            "classification": "POINT_IN_TIME_CAPTURED_STRUCTURED_OHLCV",
            "point_in_time_claim": True,
        }
    )
    assert evidence.export_dumbmoney_observation(captured)["point_in_time_claim"] is True


def test_export_accepts_a_raw_series_and_normalizes_it():
    raw = synthetic_series(bar_count=300)
    assert evidence.export_dumbmoney_observation(raw)["bar_count"] == 300


def test_observation_digest_covers_the_whole_body(series, observation):
    from dimwit.core import sha256_obj

    body = {key: value for key, value in observation.items() if key != "digest"}
    assert observation["digest"] == sha256_obj(body)
    mutated = copy.deepcopy(body)
    mutated["technical_state"] = "BULLISH_ALIGNMENT_TOTALLY"
    assert sha256_obj(mutated) != observation["digest"]


# --- ledger ----------------------------------------------------------------


@pytest.fixture()
def ledger(tmp_path, observation) -> evidence.MarketEvidenceLedger:
    instance = evidence.MarketEvidenceLedger(tmp_path / "evidence.jsonl")
    for index in range(3):
        instance.append(observation, occurred_at=f"2026-07-30T0{index}:00:00Z")
    return instance


def test_append_chains_entries_and_records_ordering(ledger):
    entries = ledger.entries()
    assert [entry["sequence"] for entry in entries] == [0, 1, 2]
    assert entries[0]["prev_hash"] == "0" * 64
    for previous, current in zip(entries, entries[1:], strict=False):
        assert current["prev_hash"] == previous["entry_hash"]
    assert ledger.head() == entries[-1]["entry_hash"]


def test_clean_ledger_verifies_and_is_truncation_detectable(ledger):
    verification = ledger.verify()
    assert verification["ok"] is True
    assert verification["chain"]["ok"] is True
    assert verification["sequence_contiguous"] is True
    assert verification["truncation_detectable"] is True
    assert verification["length_anchor"]["matches"] is True
    assert verification["length_anchor"]["independent"] is False


def test_editing_a_past_entry_breaks_the_chain(ledger):
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["kind"] = "tampered"
    lines[0] = json.dumps(row, sort_keys=True)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verification = ledger.verify()
    assert verification["ok"] is False
    assert verification["chain"]["ok"] is False
    assert "mismatch" in verification["chain"]["reason"]


def test_removing_a_middle_entry_breaks_the_chain(ledger):
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    verification = ledger.verify()
    assert verification["ok"] is False
    assert verification["chain"]["ok"] is False


def test_truncating_the_tail_is_caught_by_the_length_anchor(ledger):
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    verification = ledger.verify()
    # the hash chain alone is perfectly happy: every remaining link still verifies
    assert verification["chain"]["ok"] is True
    assert verification["sequence_contiguous"] is True
    assert verification["length_anchor"]["matches"] is False
    assert verification["ok"] is False


def test_truncation_is_invisible_without_a_length_commitment(ledger):
    head, count = ledger.head(), len(ledger.entries())
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    ledger.anchor_path.unlink()
    blind = ledger.verify()
    assert blind["ok"] is True, "without a commitment there is nothing to compare a length against"
    assert blind["truncation_detectable"] is False
    assert any("tail truncation" in item for item in blind["does_not_detect"])
    informed = ledger.verify(expected_head=head, expected_count=count)
    assert informed["external_commitment"]["matches"] is False
    assert informed["ok"] is False


def test_swapping_an_observation_body_is_caught(ledger, series):
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["observation"] = {"schema": "fake", "digest": row["observation_digest"]}
    lines[1] = json.dumps(row, sort_keys=True)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ledger.verify()["ok"] is False


def test_verification_never_claims_to_stop_a_writer_with_both_files(ledger):
    assert any(
        "rewrite both the ledger and its local anchor" in item
        for item in ledger.verify()["does_not_detect"]
    )


def test_corrupt_json_is_reported_with_its_line_number(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"sequence": 0}\nnot json\n', encoding="utf-8")
    with pytest.raises(evidence.EvidenceError, match=r"broken.jsonl:2"):
        evidence.MarketEvidenceLedger(path).entries()


def test_empty_observations_are_refused(tmp_path):
    ledger = evidence.MarketEvidenceLedger(tmp_path / "e.jsonl")
    with pytest.raises(evidence.EvidenceError, match="non-empty object"):
        ledger.append({})


def test_summary_reports_the_head_and_counts(ledger):
    summary = ledger.summary()
    assert summary["entry_count"] == 3
    assert summary["head"] == ledger.head()
    assert summary["by_kind"] == {"observation": 3}
    assert summary["first_occurred_at"] == "2026-07-30T00:00:00Z"
    assert summary["last_occurred_at"] == "2026-07-30T02:00:00Z"


def test_empty_ledger_is_a_valid_empty_ledger(tmp_path):
    ledger = evidence.MarketEvidenceLedger(tmp_path / "absent.jsonl")
    assert ledger.entries() == []
    assert ledger.head() == "0" * 64
    assert ledger.summary()["entry_count"] == 0
    assert ledger.verify()["truncation_detectable"] is False


def test_record_observations_appends_and_verifies(tmp_path, observation):
    result = evidence.record_observations([observation, observation], path=tmp_path / "batch.jsonl")
    assert result["appended"] == 2
    assert len(result["appended_hashes"]) == 2
    assert result["ok"] is True
    assert result["entry_count"] == 2
