"""Indicator tests, in priority order of what actually goes wrong.

The first test is the one that matters: **prefix stability**. Every indicator is recomputed on truncated
prefixes and must agree with its full-series value bar for bar. That is the mechanical proof of no lookahead,
applied to all 46 indicators rather than asserted in a docstring.

The second is warmup exactness: the registry's `warmup_bars` must equal the first index where the indicator is
actually defined, so nothing quietly reports a 20-period average computed from 6 bars.
"""
from __future__ import annotations

import math

import pytest

from dimwit.market import bars, indicators as ind
from dimwit.market.selfaudit import synthetic_series

PREFIX_PROBES = (255, 279, 300, 319)


@pytest.fixture(scope="module")
def series() -> dict:
    return bars.normalize_series(synthetic_series(bar_count=320))


@pytest.fixture(scope="module")
def panel(series) -> dict:
    return ind.indicator_series(series)


def test_every_indicator_is_prefix_stable(series, panel):
    """indicator(bars)[i] == indicator(bars[:i+1])[-1] for every registered indicator."""
    violations: list[str] = []
    for probe in PREFIX_PROBES:
        prefix_panel = ind.indicator_series(bars.point_in_time_prefix(series, probe))
        for name, full in panel.items():
            expected, actual = full[probe], prefix_panel[name][-1]
            if (expected is None) != (actual is None):
                violations.append(f"{name}@{probe}: definedness differs")
            elif expected is not None and not math.isclose(expected, actual, rel_tol=0, abs_tol=1e-9):
                violations.append(f"{name}@{probe}: {expected} != {actual}")
    assert not violations, "prefix-unstable indicators (lookahead): " + "; ".join(violations)


def test_registry_warmup_matches_first_defined_index(panel):
    mismatches = {}
    for name, series_values in panel.items():
        first = next((index for index, value in enumerate(series_values) if value is not None), None)
        expected = ind.INDICATORS[name]["warmup_bars"] - 1
        if first != expected:
            mismatches[name] = {"first_defined_index": first, "registry_expects": expected}
    assert not mismatches, f"warmup registry drift: {mismatches}"


def test_panel_and_registry_do_not_drift(panel):
    assert set(panel) == set(ind.INDICATORS)
    assert len(ind.INDICATORS) >= 40
    for name, spec in ind.INDICATORS.items():
        assert spec["description"].strip(), f"{name} has no description"
        assert spec["family"] in ind.INDICATOR_FAMILIES


def test_warmup_bars_helper_reports_the_deepest_requirement():
    assert ind.warmup_bars(["sma20", "rsi14"]) == 20
    assert ind.warmup_bars(["sma200"]) == 200
    assert ind.warmup_bars() == max(spec["warmup_bars"] for spec in ind.INDICATORS.values())


def test_sma_and_ema_against_hand_computed_values():
    values = [float(x) for x in range(1, 11)]
    assert ind.sma(values, 3)[:3] == [None, None, 2.0]
    assert ind.sma(values, 3)[-1] == pytest.approx(9.0)
    # EMA is seeded with the SMA of the first `period` samples, then alpha = 2/(n+1)
    ema3 = ind.ema(values, 3)
    assert ema3[2] == pytest.approx(2.0)
    assert ema3[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)


def test_wilder_smoothing_matches_the_recursion():
    values = [2.0, 4.0, 6.0, 8.0]
    smoothed = ind.wilder(values, 2)
    assert smoothed[1] == pytest.approx(3.0)
    assert smoothed[2] == pytest.approx((3.0 * 1 + 6.0) / 2)


def test_rsi_saturates_on_a_monotonic_series():
    rising = [100.0 + index for index in range(30)]
    assert ind.rsi(rising)[-1] == pytest.approx(100.0)
    falling = [100.0 - index for index in range(30)]
    assert ind.rsi(falling)[-1] == pytest.approx(0.0)


def test_wilder_rsi_differs_from_the_legacy_flat_average(series):
    closes = bars.closes(series)
    wilder_value = ind.rsi(closes)[-1]
    legacy_value = ind.rsi_simple(closes)[-1]
    assert wilder_value is not None and legacy_value is not None
    # they must not be silently identical: the parity block downstream exists because they differ
    assert abs(wilder_value - legacy_value) > 1e-6


def test_macd_histogram_is_line_minus_signal(series):
    closes = bars.closes(series)
    line, signal, histogram = ind.macd(closes)
    for index in range(len(closes)):
        if histogram[index] is None:
            continue
        assert histogram[index] == pytest.approx(line[index] - signal[index])


def test_bollinger_bands_bracket_the_midline(panel):
    for index in range(len(panel["bb_mid20"])):
        if panel["bb_mid20"][index] is None:
            continue
        assert panel["bb_lower20"][index] <= panel["bb_mid20"][index] <= panel["bb_upper20"][index]


def test_percent_b_is_zero_at_the_lower_band_and_one_at_the_upper(panel):
    for index in range(len(panel["bb_percent_b20"])):
        value = panel["bb_percent_b20"][index]
        if value is None:
            continue
        close = panel["last_close"][index]
        if close <= panel["bb_lower20"][index]:
            assert value <= 0.0 + 1e-9
        if close >= panel["bb_upper20"][index]:
            assert value >= 1.0 - 1e-9


def test_donchian_channel_contains_price(series, panel):
    highs, lows = bars.highs(series), bars.lows(series)
    for index in range(19, len(highs)):
        assert panel["donchian_high20"][index] == max(highs[index - 19 : index + 1])
        assert panel["donchian_low20"][index] == min(lows[index - 19 : index + 1])


def test_bounded_oscillators_stay_in_range(panel):
    ranges = {
        "rsi14": (0.0, 100.0),
        "rsi14_simple": (0.0, 100.0),
        "stoch_k14": (0.0, 100.0),
        "stoch_d14": (0.0, 100.0),
        "mfi14": (0.0, 100.0),
        "willr14": (-100.0, 0.0),
        "adx14": (0.0, 100.0),
        "di_plus14": (0.0, 100.0),
        "di_minus14": (0.0, 100.0),
    }
    for name, (low, high) in ranges.items():
        for value in panel[name]:
            if value is not None:
                assert low - 1e-9 <= value <= high + 1e-9, f"{name} out of range: {value}"


def test_atr_and_true_range_are_non_negative(panel):
    for name in ("atr14", "true_range", "realized_vol20_bps"):
        for value in panel[name]:
            if value is not None:
                assert value >= 0.0


def test_supertrend_direction_is_only_plus_or_minus_one(panel):
    assert {value for value in panel["supertrend_dir"] if value is not None} <= {1.0, -1.0}


def test_snapshot_rounds_and_indexes(series):
    last = ind.snapshot(series)
    at_index = ind.snapshot(series, index=len(series["bars"]) - 1)
    assert last == at_index
    mid = ind.snapshot(series, ["sma20", "rsi14"], index=100)
    assert set(mid) == {"sma20", "rsi14"}
    with pytest.raises(IndexError):
        ind.snapshot(series, index=10_000)


def test_unknown_indicator_names_raise(series):
    with pytest.raises(KeyError, match="unknown indicators"):
        ind.indicator_series(series, ["not_an_indicator"])


def test_short_series_returns_all_none_rather_than_a_shorter_window():
    assert ind.sma([1.0, 2.0], 20) == [None, None]
    assert ind.ema([1.0, 2.0], 20) == [None, None]
    assert ind.wilder([1.0, 2.0], 20) == [None, None]
