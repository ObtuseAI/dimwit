"""Bar normalization is the market cell's only input gate, so it is tested as a gate: every way a series can
lie about itself must raise, and every accepted series must come out in exactly one canonical shape."""
from __future__ import annotations

import copy

import pytest

from dimwit.market import bars
from dimwit.market.selfaudit import synthetic_series


@pytest.fixture(scope="module")
def raw() -> dict:
    return synthetic_series(bar_count=120)


def test_normalize_produces_canonical_shape(raw):
    normalized = bars.normalize_series(raw)
    assert normalized["schema"] == bars.NATIVE_SCHEMA
    assert normalized["source_schema"] == raw["schema"]
    assert normalized["bar_count"] == 120
    assert normalized["timeframe_minutes"] == 1440
    assert normalized["spacing"]["uniform"] is True
    assert set(normalized["bars"][0]) == set(bars.BAR_KEYS)
    assert normalized["digest"] == bars.series_digest(normalized)


def test_digest_is_content_addressed_not_order_dependent(raw):
    normalized = bars.normalize_series(raw)
    reordered = {key: normalized[key] for key in reversed(list(normalized))}
    assert bars.series_digest(reordered) == normalized["digest"]


def test_digest_changes_when_a_single_price_changes(raw):
    normalized = bars.normalize_series(raw)
    mutated = copy.deepcopy(normalized)
    mutated["bars"][7]["close"] += 0.01
    assert bars.series_digest(mutated) != normalized["digest"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda s: s.update(schema="something.else.v1"), "unsupported series schema"),
        (lambda s: s.update(classification="TOTALLY_REAL_MARKET_TRUTH"), "known classification"),
        (lambda s: s.update(symbol="  "), "symbol is required"),
        (lambda s: s.update(asset_class="tulips"), "asset_class must be one of"),
        (lambda s: s.update(timeframe="3.5h"), "unsupported timeframe"),
        (lambda s: s.update(bars=s["bars"][:4]), "at least"),
        (lambda s: s.update(as_of="2000-01-01T00:00:00Z"), "later than as_of"),
    ],
)
def test_normalize_rejects_dishonest_series(raw, mutate, message):
    series = copy.deepcopy(raw)
    mutate(series)
    with pytest.raises(bars.BarSeriesError, match=message):
        bars.normalize_series(series)


def test_normalize_rejects_naive_timestamps(raw):
    series = copy.deepcopy(raw)
    series["bars"][3]["observed_at"] = "2023-11-17T00:00:00"
    with pytest.raises(bars.BarSeriesError, match="timezone"):
        bars.normalize_series(series)


def test_normalize_rejects_non_chronological_bars(raw):
    series = copy.deepcopy(raw)
    series["bars"][5], series["bars"][6] = series["bars"][6], series["bars"][5]
    with pytest.raises(bars.BarSeriesError, match="strictly after"):
        bars.normalize_series(series)


def test_normalize_rejects_impossible_high_low_envelope(raw):
    series = copy.deepcopy(raw)
    series["bars"][9]["high"] = series["bars"][9]["low"] - 1.0
    with pytest.raises(bars.BarSeriesError, match="envelope"):
        bars.normalize_series(series)


def test_normalize_rejects_non_positive_prices_and_negative_volume(raw):
    negative_price = copy.deepcopy(raw)
    negative_price["bars"][2]["low"] = -1.0
    with pytest.raises(bars.BarSeriesError, match="positive"):
        bars.normalize_series(negative_price)
    negative_volume = copy.deepcopy(raw)
    negative_volume["bars"][2]["volume"] = -5.0
    with pytest.raises(bars.BarSeriesError, match="non-negative"):
        bars.normalize_series(negative_volume)


def test_synthetic_classification_cannot_claim_point_in_time(raw):
    series = copy.deepcopy(raw)
    series["point_in_time_claim"] = True
    with pytest.raises(bars.BarSeriesError, match="point_in_time_claim"):
        bars.normalize_series(series)


def test_point_in_time_capture_may_claim_point_in_time(raw):
    series = copy.deepcopy(raw)
    series["classification"] = "POINT_IN_TIME_CAPTURED_STRUCTURED_OHLCV"
    series["point_in_time_claim"] = True
    assert bars.normalize_series(series)["point_in_time_claim"] is True


def test_prefix_is_a_true_prefix(raw):
    normalized = bars.normalize_series(raw)
    prefix = bars.point_in_time_prefix(normalized, 40)
    assert prefix["bar_count"] == 41
    assert prefix["bars"] == normalized["bars"][:41]
    assert prefix["as_of"] == normalized["bars"][40]["observed_at"]
    assert prefix["digest"] != normalized["digest"]


def test_prefix_rejects_out_of_range_index(raw):
    normalized = bars.normalize_series(raw)
    with pytest.raises(bars.BarSeriesError, match="outside"):
        bars.point_in_time_prefix(normalized, 120)


def test_resample_drops_the_partial_trailing_bucket():
    normalized = bars.normalize_series(synthetic_series(bar_count=103, timeframe="1h"))
    weekly = bars.resample(normalized, "4h")
    assert weekly["timeframe_minutes"] == 240
    assert weekly["bar_count"] * 4 <= 103
    assert weekly["partial_buckets_dropped"] >= 1
    assert weekly["resampled_from"] == "1h"


def test_resample_aggregates_ohlcv_correctly():
    normalized = bars.normalize_series(synthetic_series(bar_count=64, timeframe="1h"))
    aggregated = bars.resample(normalized, "4h")
    source = normalized["bars"]
    first = aggregated["bars"][0]
    # bucket boundaries come from the epoch, so locate the source bars by timestamp rather than by assuming 0..3
    members = [bar for bar in source if bar["observed_at"] <= first["observed_at"]][-4:]
    assert first["open"] == members[0]["open"]
    assert first["close"] == members[-1]["close"]
    assert first["high"] == max(bar["high"] for bar in members)
    assert first["low"] == min(bar["low"] for bar in members)
    assert first["volume"] == pytest.approx(sum(bar["volume"] for bar in members))


def test_resample_refuses_downsampling():
    normalized = bars.normalize_series(synthetic_series(bar_count=64, timeframe="1h"))
    with pytest.raises(bars.BarSeriesError, match="aggregates upward"):
        bars.resample(normalized, "15m")


def test_resample_refuses_non_multiple_timeframes():
    normalized = bars.normalize_series(synthetic_series(bar_count=64, timeframe="10m"))
    with pytest.raises(bars.BarSeriesError, match="integer multiple"):
        bars.resample(normalized, "15m")


def test_is_normalized_requires_a_matching_digest_not_just_a_schema_field(raw):
    """A raw payload can carry the native schema string. If that counted as normalized, `ensure_normalized`
    would wave unvalidated data straight past the only input gate this package has."""
    assert bars.is_normalized(raw) is False
    normalized = bars.normalize_series(raw)
    assert bars.is_normalized(normalized) is True
    forged = copy.deepcopy(normalized)
    forged["bars"][0]["close"] += 1.0
    assert bars.is_normalized(forged) is False
    stripped = {key: value for key, value in normalized.items() if key != "spacing"}
    assert bars.is_normalized(stripped) is False


def test_ensure_normalized_validates_raw_input(raw):
    dishonest = copy.deepcopy(raw)
    dishonest["asset_class"] = "tulips"
    with pytest.raises(bars.BarSeriesError, match="asset_class"):
        bars.ensure_normalized(dishonest)
    assert bars.ensure_normalized(raw)["bar_count"] == 120


def test_gaps_are_reported_not_rejected(raw):
    series = copy.deepcopy(raw)
    del series["bars"][50]
    normalized = bars.normalize_series(series)
    assert normalized["spacing"]["uniform"] is False
    assert normalized["spacing"]["gap_count"] == 1
    assert normalized["spacing"]["max_gap_minutes"] == pytest.approx(2880.0)
