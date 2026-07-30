"""Walk-forward scanner tests.

The scanner's job is to be *hard to fool*, so most of these tests try to fool it:

* the execution model must never fill at the signal bar (`entry_index == signal_index + 1`, always);
* no outcome may settle outside its own segment, which is what the embargo is for;
* survivors must be scored on excess over the unconditional same-side baseline, not on raw return — otherwise a
  long rule "wins" any rising segment;
* it must have power (an injected conditional edge is found) *and* discipline (pure noise yields nothing, and a
  placebo with displaced entries does not beat the real run).

The last pair is the important one. A scanner that finds nothing is useless; a scanner that finds something in
noise is worse than useless.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from dimwit.market import bars, scan
from dimwit.market.selfaudit import synthetic_series

CONFIG = scan.ScanConfig(warmup_bars=200, training_bars=300, embargo_bars=10, holdout_bars=400)


def _timestamp(index: int) -> str:
    return datetime.fromtimestamp(1_700_000_000 + index * 86_400, UTC).isoformat().replace("+00:00", "Z")


def _wrap(rows: list[dict], symbol: str) -> dict:
    return bars.normalize_series(
        {
            "schema": bars.NATIVE_SCHEMA,
            "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
            "symbol": symbol,
            "asset_class": "equity",
            "timeframe": "1d",
            "as_of": rows[-1]["observed_at"],
            "bars": rows,
        }
    )


@pytest.fixture(scope="module")
def noise() -> dict:
    """A driftless-ish random walk: nothing conditional to find."""
    return bars.normalize_series(synthetic_series(bar_count=1000))


@pytest.fixture(scope="module")
def injected() -> dict:
    """A random walk with a RARE conditional edge: after a 20-bar z-score of -2 or lower, the next five bars
    carry a real positive drift. Rare on purpose — a frequent trigger would move the unconditional baseline and
    stop being a *conditional* edge at all."""
    state = 11
    boost_bars, boost = 5, 0.008

    def unit() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    price = 100.0
    rows: list[dict] = []
    closes: list[float] = []
    countdown = 0
    for index in range(1500):
        drift = boost if countdown > 0 else 0.0
        if countdown:
            countdown -= 1
        open_price = price
        close = max(1.0, open_price * (1.0 + drift + (unit() - 0.5) * 0.014))
        rows.append(
            {
                "observed_at": _timestamp(index),
                "open": open_price,
                "high": max(open_price, close) * (1 + unit() * 0.002),
                "low": min(open_price, close) * (1 - unit() * 0.002),
                "close": close,
                "volume": 100_000.0 + unit() * 50_000,
            }
        )
        closes.append(close)
        if len(closes) >= 20 and countdown == 0:
            window = closes[-20:]
            mean = sum(window) / 20
            deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / 20)
            if deviation > 0 and (close - mean) / deviation <= -2.0:
                countdown = boost_bars
        price = close
    return _wrap(rows, "ZINJECT")


@pytest.fixture(scope="module")
def noise_scan(noise) -> dict:
    return scan.scan_rules(noise, config=CONFIG)


# --- configuration ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"warmup_bars": 10}, "warmup_bars"),
        ({"training_bars": 0}, "positive"),
        ({"horizon_bars": 0}, "horizon_bars must be positive"),
        ({"embargo_bars": 2, "horizon_bars": 5}, "embargo_bars must cover"),
        ({"holdout_bars": 3, "horizon_bars": 5}, "holdout_bars must exceed"),
        ({"alpha": 0.9}, "alpha"),
        ({"round_trip_cost_bps": 0.0}, "round_trip_cost_bps"),
    ],
)
def test_config_refuses_to_weaken_its_own_accounting(kwargs, message):
    with pytest.raises(scan.ScanError, match=message):
        scan.ScanConfig(**kwargs).validate()


def test_scan_refuses_a_series_that_cannot_afford_the_split():
    short = bars.normalize_series(synthetic_series(bar_count=300))
    with pytest.raises(scan.ScanError, match="scan needs"):
        scan.scan_rules(short, config=CONFIG)


def test_unknown_and_empty_rule_sets_raise(noise):
    with pytest.raises(scan.ScanError, match="unknown rules"):
        scan.scan_rules(noise, config=CONFIG, rules=["moon_phase"])
    with pytest.raises(scan.ScanError, match="at least one rule"):
        scan.scan_rules(noise, config=CONFIG, rules=[])


# --- split and execution model --------------------------------------------


def test_segments_are_disjoint_and_the_embargo_covers_the_horizon(noise_scan):
    split = noise_scan["split"]
    assert split["training"]["end"] < split["embargo"]["start"]
    assert split["embargo"]["end"] < split["holdout"]["start"]
    assert split["embargo"]["end"] - split["embargo"]["start"] + 1 >= CONFIG.horizon_bars
    assert split["disjoint"] is True
    assert split["embargo_covers_horizon"] is True
    assert split["holdout_used_for_selection"] is False
    assert split["selection_basis"] == "TRAINING_SEGMENT_ONLY"


def test_entry_is_the_next_bar_open_and_exit_is_horizon_bars_later(injected):
    result = scan.scan_rules(injected, config=CONFIG)
    checked = 0
    for rule in result["rules"].values():
        for segment in ("training_metrics", "held_out_metrics"):
            assert rule[segment]["n"] >= 0
    # re-derive outcomes directly to inspect the execution model
    features = scan.build_features(injected)
    segments = scan._segments(CONFIG, injected["bar_count"])
    for name in ("donchian_breakout_up", "rsi_oversold", "macd_cross_down"):
        outcomes = scan._outcomes(
            injected, features, scan.RULES[name]["fn"], segments["holdout"], CONFIG
        )
        for item in outcomes:
            assert item["entry_index"] == item["signal_index"] + 1, "filled on the signal bar"
            assert item["outcome_index"] == item["entry_index"] + CONFIG.horizon_bars
            assert segments["holdout"]["start"] <= item["signal_index"]
            assert item["outcome_index"] <= segments["holdout"]["end"], "outcome escaped the segment"
            checked += 1
    assert checked > 0


def test_net_return_is_gross_minus_the_full_round_trip_cost(injected):
    features = scan.build_features(injected)
    segments = scan._segments(CONFIG, injected["bar_count"])
    outcomes = scan._outcomes(
        injected, features, scan.RULES["trend_stack_long"]["fn"], segments["holdout"], CONFIG
    )
    assert outcomes
    for item in outcomes:
        assert item["net_return_bps"] == pytest.approx(
            item["gross_return_bps"] - CONFIG.round_trip_cost_bps, abs=1e-6
        )
        assert item["round_trip_cost_bps"] == CONFIG.round_trip_cost_bps
        assert item["positive_after_cost"] == (item["net_return_bps"] > 0)


def test_short_outcomes_invert_the_price_move(injected):
    features = scan.build_features(injected)
    segments = scan._segments(CONFIG, injected["bar_count"])
    outcomes = scan._outcomes(
        injected, features, scan.RULES["trend_stack_short"]["fn"], segments["holdout"], CONFIG
    )
    for item in outcomes:
        entry, exit_price = item["entry_price"], item["outcome_price"]
        expected = -1 * (exit_price / entry - 1.0) * 10_000.0
        assert item["gross_return_bps"] == pytest.approx(expected, abs=1e-4)


# --- statistics ------------------------------------------------------------


def test_overlap_deflation_divides_by_sqrt_horizon(noise_scan):
    for rule in noise_scan["rules"].values():
        metrics = rule["held_out_metrics"]
        if metrics["t_stat"] is None:
            continue
        assert metrics["t_stat_overlap_adjusted"] == pytest.approx(
            metrics["t_stat"] / math.sqrt(CONFIG.horizon_bars), abs=1e-6
        )
        assert metrics["independent_n_estimate"] == pytest.approx(
            metrics["n"] / CONFIG.horizon_bars, abs=1e-4
        )


def test_baseline_is_the_unconditional_same_side_return(noise_scan):
    baseline = noise_scan["baselines"]["holdout"]
    assert baseline["model"] == "TAKE_THE_SAME_SIDE_AT_EVERY_BAR_OF_THE_SEGMENT"
    assert baseline["n"] > 0
    # long and short are mirror images once the same cost is charged to both
    assert baseline["long_mean_net_bps"] + baseline["short_mean_net_bps"] == pytest.approx(
        -2 * CONFIG.round_trip_cost_bps, abs=1e-3
    )


def test_excess_is_measured_against_the_matching_side_baseline(noise_scan):
    baseline = noise_scan["baselines"]["holdout"]
    for rule in noise_scan["rules"].values():
        metrics = rule["held_out_metrics"]
        if not metrics["n"] or metrics["mean_excess_bps"] is None:
            continue
        assert metrics["mean_excess_bps"] == pytest.approx(
            metrics["mean_net_bps"] - metrics["baseline_mean_net_bps"], abs=1e-4
        )
        sides = set(metrics["direction_mix"])
        if sides == {"long"}:
            assert metrics["baseline_mean_net_bps"] == pytest.approx(baseline["long_mean_net_bps"])
        elif sides == {"short"}:
            assert metrics["baseline_mean_net_bps"] == pytest.approx(baseline["short_mean_net_bps"])


def test_survivor_accounting_uses_the_excess_p_value(noise_scan):
    disclosure = noise_scan["search_disclosure"]
    assert disclosure["tested_quantity"] == "EXCESS_OVER_UNCONDITIONAL_SAME_SIDE_BASELINE"
    threshold = disclosure["bonferroni"]["critical_value"]
    for name in disclosure["bonferroni"]["survivors"]:
        assert noise_scan["rules"][name]["held_out_metrics"]["p_value_excess_overlap_adjusted"] <= threshold


def test_search_space_is_fully_disclosed(noise_scan):
    disclosure = noise_scan["search_disclosure"]
    assert disclosure["family_size"] == len(scan.RULES)
    assert disclosure["rules_evaluated"] == sorted(scan.RULES)
    assert disclosure["bonferroni"]["critical_value"] == pytest.approx(CONFIG.alpha / len(scan.RULES))
    assert disclosure["bonferroni"]["survivor_count"] <= disclosure["benjamini_hochberg"]["survivor_count"]
    assert disclosure["p_value_method"] == scan.P_VALUE_METHOD
    assert disclosure["overlap_deflation"] == "T_DIVIDED_BY_SQRT_HORIZON_BARS"


def test_bonferroni_is_never_more_permissive_than_benjamini_hochberg():
    p_values = {"a": 0.001, "b": 0.02, "c": 0.30, "d": None}
    bonferroni = scan._bonferroni(p_values, 0.05, 4)
    bh = scan._benjamini_hochberg(p_values, 0.05)
    assert set(bonferroni["survivors"]) <= set(bh["survivors"])
    assert bonferroni["family_size"] == 4
    assert bh["tested"] == 3  # None is excluded, not counted as a pass


def test_observation_accounting_deflates_overlapping_windows(noise_scan):
    accounting = noise_scan["observation_accounting"]
    assert accounting["settled_holdout_outcomes"] > 0
    assert accounting["independent_holdout_estimate"] == pytest.approx(
        accounting["settled_holdout_outcomes"] / CONFIG.horizon_bars, abs=1e-3
    )
    assert "not independent" in accounting["note"]


# --- power and discipline --------------------------------------------------


def test_scanner_finds_an_injected_conditional_edge(injected):
    config = scan.ScanConfig(warmup_bars=200, training_bars=400, embargo_bars=10, holdout_bars=890)
    result = scan.scan_rules(injected, config=config)
    survivors = result["search_disclosure"]["benjamini_hochberg"]["survivors"]
    assert "zscore_stretch_long" in survivors, f"injected edge not detected; survivors={survivors}"
    metrics = result["rules"]["zscore_stretch_long"]["held_out_metrics"]
    assert metrics["mean_excess_bps"] > 100
    assert result["candidate_status"] == "HELD_OUT_SURVIVORS_PRESENT"


def test_injected_edge_beats_its_own_placebo(injected):
    config = scan.ScanConfig(warmup_bars=200, training_bars=400, embargo_bars=10, holdout_bars=890)
    control = scan.placebo_control(injected, config=config)
    assert control["null_model"] == "FIXED_BAR_LAG_DISPLACEMENT_OF_EVERY_ENTRY"
    assert control["max_bh_survivors"] == 0
    assert control["verdict"] == "REAL_EXCEEDS_PLACEBO"
    assert control["candidate_status"] == "DIAGNOSTIC_ONLY"


def test_noise_yields_no_survivors_and_is_not_distinguishable_from_placebo(noise, noise_scan):
    assert noise_scan["search_disclosure"]["benjamini_hochberg"]["survivor_count"] == 0
    assert noise_scan["candidate_status"] == "NO_HELD_OUT_SURVIVOR"
    control = scan.placebo_control(noise, config=CONFIG)
    assert control["verdict"] == "NOT_DISTINGUISHABLE_FROM_PLACEBO"


def test_placebo_rejects_non_positive_lags(noise):
    with pytest.raises(scan.ScanError, match="lags must be positive"):
        scan.placebo_control(noise, config=CONFIG, lags=(0,))


def test_placebo_displaces_entries_without_changing_direction(injected):
    features = scan.build_features(injected)
    segments = scan._segments(CONFIG, injected["bar_count"])
    rule = scan.RULES["trend_stack_long"]["fn"]
    real = scan._outcomes(injected, features, rule, segments["holdout"], CONFIG)
    placebo = scan._outcomes(
        injected, features, rule, segments["holdout"], CONFIG, placebo_lag_bars=37
    )
    assert placebo, "placebo produced no outcomes"
    assert {item["direction"] for item in placebo} == {item["direction"] for item in real}
    for item in placebo:
        assert item["entry_index"] == item["signal_index"] + 38


# --- shape -----------------------------------------------------------------


def test_scan_carries_no_forecast_and_no_authority(noise_scan):
    assert noise_scan["forecast_probability"] is None
    assert noise_scan["expected_return_bps"] is None
    assert noise_scan["promotions_applied"] == 0
    assert noise_scan["orders_created"] == 0
    assert noise_scan["broker_calls"] == 0
    assert noise_scan["live_activation"] is False
    assert noise_scan["execution_authority"] is False
    assert noise_scan["recommendation_only"] is True
    assert noise_scan["placebo_control"] is False


def test_scan_is_deterministic(noise):
    first = scan.scan_rules(noise, config=CONFIG)
    second = scan.scan_rules(noise, config=CONFIG)
    assert first["digest"] == second["digest"]


def test_summary_reports_the_search_and_the_baseline(noise_scan):
    summary = scan.scan_summary(noise_scan)
    assert summary["family_size"] == len(scan.RULES)
    assert summary["tested_quantity"] == "EXCESS_OVER_UNCONDITIONAL_SAME_SIDE_BASELINE"
    assert summary["holdout_baseline"]["model"]
    assert len(summary["top_by_holdout_excess_t"]) <= 5
    assert summary["forecast_probability"] is None


def test_every_rule_is_registered_with_a_family_and_description():
    assert len(scan.RULES) >= 30
    for name, spec in scan.RULES.items():
        assert callable(spec["fn"]), name
        assert spec["description"].strip(), name
        assert spec["family"] in scan.RULE_FAMILIES, name


def test_rules_return_only_minus_one_zero_or_one(injected):
    features = scan.build_features(injected)
    seen: set[int] = set()
    for spec in scan.RULES.values():
        for row in features[::37]:
            seen.add(spec["fn"](row))
    assert seen <= {-1, 0, 1}


def test_features_expose_one_bar_lags_for_crossing_rules(injected):
    features = scan.build_features(injected)
    assert features[0]["prev_macd_hist"] is None
    for index in (500, 900):
        assert features[index]["prev_rsi14"] == features[index - 1]["rsi14"]
        assert features[index]["prev_stoch_k14"] == features[index - 1]["stoch_k14"]
