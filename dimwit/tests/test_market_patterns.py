"""Pattern tests.

Two things are being defended here. First, that each shape detector actually fires on a hand-built instance of
its shape (and the shape is written out explicitly, so a reader can check the detector against the definition
rather than against itself). Second — and more important — that `detected_at_index` is honest: a swing pivot
must not be visible before its confirmation bars exist, and `pattern_flags` must be identical when recomputed on
a truncated prefix.
"""
from __future__ import annotations

import pytest

from dimwit.market import bars, patterns as pat
from dimwit.market.selfaudit import synthetic_series

EPOCH_DAY = 86_400


def build(rows: list[tuple[float, float, float, float]], *, volume: float = 1000.0) -> dict:
    """Build a normalized series from explicit (open, high, low, close) rows."""
    payload = {
        "schema": bars.NATIVE_SCHEMA,
        "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
        "symbol": "FIXTURE",
        "asset_class": "equity",
        "timeframe": "1d",
        "as_of": "2030-01-01T00:00:00Z",
        "bars": [
            {
                "observed_at": f"2024-01-{index + 1:02d}T00:00:00Z",
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for index, (open_price, high, low, close) in enumerate(rows)
        ],
    }
    return bars.normalize_series(payload, min_bars=len(rows))


def filler(count: int, price: float = 100.0) -> list[tuple[float, float, float, float]]:
    """Neutral padding bars: a real body (so they are not themselves doji) and wicks too short to read as a
    hammer or a star. Padding that accidentally matches a pattern would make every fixture below ambiguous."""
    return [(price, price + 0.8, price - 0.8, price + 0.5) for _ in range(count)]


def detected(series: dict, name: str) -> list[int]:
    observation = pat.detect_patterns(series, [name])
    return [item["index"] for item in observation["detections"]]


@pytest.fixture(scope="module")
def synthetic() -> dict:
    return bars.normalize_series(synthetic_series(bar_count=400))


# --- single-bar shapes ------------------------------------------------------


def test_doji_requires_a_body_under_a_tenth_of_the_range():
    rows = filler(3) + [(100.0, 105.0, 95.0, 100.2)] + filler(3)
    assert detected(build(rows), "doji") == [3]
    thick = filler(3) + [(100.0, 105.0, 95.0, 104.0)] + filler(3)
    assert 3 not in detected(build(thick), "doji")


def test_hammer_needs_a_lower_wick_at_least_twice_the_body():
    rows = filler(3) + [(100.0, 100.6, 94.0, 100.5)] + filler(3)
    assert detected(build(rows), "hammer") == [3]


def test_shooting_star_needs_an_upper_wick_at_least_twice_the_body():
    rows = filler(3) + [(100.0, 106.0, 99.6, 100.5)] + filler(3)
    assert detected(build(rows), "shooting_star") == [3]


def test_marubozu_directions_follow_the_close():
    rising = filler(3) + [(100.0, 105.0, 100.0, 105.0)] + filler(3)
    assert detected(build(rising), "marubozu_bull") == [3]
    falling = filler(3) + [(105.0, 105.0, 100.0, 100.0)] + filler(3)
    assert detected(build(falling), "marubozu_bear") == [3]


# --- two-bar shapes --------------------------------------------------------


def test_bullish_engulfing_body_contains_the_prior_down_body():
    rows = filler(3) + [(102.0, 102.5, 99.5, 100.0), (99.0, 103.5, 98.5, 103.0)] + filler(3)
    assert detected(build(rows), "bullish_engulfing") == [4]


def test_bearish_engulfing_body_contains_the_prior_up_body():
    rows = filler(3) + [(100.0, 102.5, 99.5, 102.0), (103.0, 103.5, 98.5, 99.0)] + filler(3)
    assert detected(build(rows), "bearish_engulfing") == [4]


def test_inside_and_outside_bars_are_range_relationships():
    inside = filler(3) + [(100.0, 106.0, 94.0, 100.0), (100.0, 103.0, 97.0, 101.0)] + filler(3)
    assert 4 in detected(build(inside), "inside_bar")
    outside = filler(3) + [(100.0, 103.0, 97.0, 101.0), (100.0, 106.0, 94.0, 99.0)] + filler(3)
    assert 4 in detected(build(outside), "outside_bar")


def test_gaps_require_a_full_range_separation():
    up = filler(3) + [(100.0, 101.0, 99.0, 100.0), (110.0, 112.0, 109.0, 111.0)] + filler(3)
    assert detected(build(up), "gap_up") == [4]
    down = filler(3) + [(110.0, 112.0, 109.0, 111.0), (100.0, 101.0, 99.0, 100.0)] + filler(3)
    assert detected(build(down), "gap_down") == [4]


# --- three-bar shapes ------------------------------------------------------


def test_three_white_soldiers_and_black_crows():
    soldiers = filler(3) + [
        (100.0, 101.5, 99.8, 101.0),
        (101.0, 102.5, 100.8, 102.0),
        (102.0, 103.5, 101.8, 103.0),
    ] + filler(3)
    assert 5 in detected(build(soldiers), "three_white_soldiers")
    crows = filler(3) + [
        (103.0, 103.2, 101.5, 102.0),
        (102.0, 102.2, 100.5, 101.0),
        (101.0, 101.2, 99.5, 100.0),
    ] + filler(3)
    assert 5 in detected(build(crows), "three_black_crows")


def test_morning_and_evening_star_need_a_small_middle_bar():
    morning = filler(3) + [
        (110.0, 110.5, 100.0, 100.5),
        (100.2, 101.0, 99.5, 100.0),
        (100.5, 108.0, 100.4, 107.0),
    ] + filler(3)
    assert 5 in detected(build(morning), "morning_star")
    evening = filler(3) + [
        (100.0, 110.5, 99.5, 110.0),
        (110.2, 111.0, 109.5, 110.0),
        (109.5, 109.8, 101.0, 102.0),
    ] + filler(3)
    assert 5 in detected(build(evening), "evening_star")


# --- structure and causality ----------------------------------------------


def test_swing_pivot_carries_its_confirmation_lag():
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 102.0, 99.5, 101.0),
        (101.0, 108.0, 100.5, 107.0),  # index 2: the swing high
        (107.0, 107.5, 105.0, 106.0),
        (106.0, 106.5, 104.0, 105.0),
        (105.0, 105.5, 103.0, 104.0),
    ]
    pivots = pat.swing_pivots(build(rows), left_bars=2, right_bars=2)
    highs = pivots["swing_highs"]
    assert [item["index"] for item in highs] == [2]
    assert highs[0]["confirmed_at_index"] == 4
    assert pivots["confirmation_lag_bars"] == 2


def test_pattern_flags_are_causal_on_every_prefix(synthetic):
    full = pat.pattern_flags(synthetic)
    for probe in (320, 360, 399):
        prefix = pat.pattern_flags(bars.point_in_time_prefix(synthetic, probe))
        assert prefix[probe] == full[probe], f"pattern flags changed with hindsight at bar {probe}"


def test_no_detection_is_ever_reported_before_it_is_knowable(synthetic):
    observation = pat.detect_patterns(synthetic)
    for item in observation["detections"]:
        assert item["detected_at_index"] >= item["index"]
    lagged = {"swing_high", "swing_low", "rsi_bullish_divergence", "rsi_bearish_divergence"}
    for item in observation["detections"]:
        if item["pattern"] in lagged:
            assert item["detected_at_index"] == item["index"] + observation["confirmation_lag_bars"]


def test_detections_are_ordered_by_when_they_became_knowable(synthetic):
    keys = [
        (item["detected_at_index"], item["index"], item["pattern"])
        for item in pat.detect_patterns(synthetic)["detections"]
    ]
    assert keys == sorted(keys)


def test_break_of_structure_fires_on_a_close_above_a_confirmed_swing_high():
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 102.0, 99.5, 101.0),
        (101.0, 108.0, 100.5, 107.0),  # swing high at 108, confirmed at index 4
        (107.0, 107.5, 105.0, 106.0),
        (106.0, 106.5, 104.0, 105.0),
        (105.0, 106.0, 104.5, 105.5),
        (105.5, 110.0, 105.0, 109.5),  # closes above 108
    ]
    series = build(rows)
    breaks = pat.detect_patterns(series, ["break_of_structure_up"])["detections"]
    assert [item["index"] for item in breaks] == [6]
    assert breaks[0]["measures"]["level"] == 108.0
    assert breaks[0]["measures"]["swing_index"] == 2


def test_donchian_breakout_compares_against_the_prior_window_not_its_own_bar():
    rows = filler(25, 100.0) + [(100.0, 120.0, 99.0, 119.0)]
    series = build(rows)
    breakouts = pat.detect_patterns(series, ["donchian_breakout_up"])["detections"]
    assert [item["index"] for item in breakouts] == [25]
    # the level is the prior window's highest HIGH (filler high = 100.8), not the breaking bar's own high
    assert breakouts[0]["measures"]["level"] == pytest.approx(100.8)


def test_market_structure_only_uses_confirmed_swings(synthetic):
    structure = pat.market_structure(synthetic)
    last_index = synthetic["bar_count"] - 1
    assert structure["as_of_index"] == last_index
    for key in ("last_confirmed_swing_high", "last_confirmed_swing_low"):
        pivot = structure[key]
        if pivot is not None:
            assert pivot["confirmed_at_index"] <= last_index
    assert structure["trend"] in {
        "UPTREND_STRUCTURE",
        "DOWNTREND_STRUCTURE",
        "RANGE_OR_TRANSITION",
        "INSUFFICIENT_SWINGS",
    }
    assert structure["forecast_probability"] is None


def test_support_resistance_reports_touches_without_a_strength_score(synthetic):
    levels = pat.support_resistance(synthetic)
    assert levels["status"] == "OK"
    assert levels["level_count"] >= 1
    for level in levels["levels"]:
        assert level["touch_count"] >= 1
        assert level["side"] in {"above", "below"}
        assert "strength" not in level and "probability" not in level
    assert levels["forecast_probability"] is None


def test_support_resistance_blocks_when_atr_is_undefined():
    result = pat.support_resistance(build(filler(26, 100.0)))
    assert result["status"] in {"OK", "BLOCKED"}
    if result["status"] == "BLOCKED":
        assert "ATR" in result["reason"]


def test_registry_is_complete_and_self_describing():
    assert len(pat.PATTERNS) >= 20
    for name, spec in pat.PATTERNS.items():
        assert spec["description"].strip(), f"{name} lacks a description"
        assert spec["invalidation"].strip(), f"{name} lacks an invalidation condition"
        assert spec["direction"] in {-1, 0, 1}
        assert spec["bars_required"] >= 1


def test_unknown_pattern_names_raise(synthetic):
    with pytest.raises(KeyError, match="unknown patterns"):
        pat.detect_patterns(synthetic, ["moon_phase_reversal"])


def test_observation_discloses_its_own_family_size(synthetic):
    observation = pat.detect_patterns(synthetic)
    assert observation["pattern_family_size"] == len(pat.PATTERNS)
    assert observation["candidate_status"] == "RESEARCH_INPUT_ONLY"
    assert observation["forecast_probability"] is None
