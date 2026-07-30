"""Candlestick, structure and divergence detectors.

The one thing that matters here is the difference between **where a pattern is** and **when you could have
known about it**. A fractal swing high at bar 40 needs `right_bars` of confirmation, so the earliest an
operator could act on it is bar `40 + right_bars`. Every detection therefore carries both:

* `index` — the bar the pattern is *located* at;
* `detected_at_index` — the first bar at which the pattern was knowable.

Rules in `scan.py` are only ever allowed to read `detected_at_index`. Mixing the two is the single most common
way a backtest invents edge that never existed, so the split is structural rather than a convention.

Nothing here emits a probability. A detector says "this shape is present and it is *this* big relative to ATR";
whether that shape pays is an empirical question for `scan.py` and, past that, for doofus.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import bars as bars_mod
from . import indicators as ind

#: pattern name -> metadata. `bars_required` counts the bars the shape itself spans (not indicator warmup).
PATTERNS: dict[str, dict[str, Any]] = {
    "doji": {
        "family": "candlestick",
        "bars_required": 1,
        "direction": 0,
        "description": "Body <= 10% of the bar range: open and close effectively equal.",
        "invalidation": "Meaningless in a low-range bar; measure body vs ATR before reading anything into it.",
    },
    "hammer": {
        "family": "candlestick",
        "bars_required": 1,
        "direction": 1,
        "description": "Small upper body with a lower wick >= 2x the body: rejection of lower prices.",
        "invalidation": "Close below the hammer low.",
    },
    "shooting_star": {
        "family": "candlestick",
        "bars_required": 1,
        "direction": -1,
        "description": "Small lower body with an upper wick >= 2x the body: rejection of higher prices.",
        "invalidation": "Close above the star high.",
    },
    "marubozu_bull": {
        "family": "candlestick",
        "bars_required": 1,
        "direction": 1,
        "description": "Up bar whose body covers >= 90% of its range: no rejection at either end.",
        "invalidation": "Close back inside the body.",
    },
    "marubozu_bear": {
        "family": "candlestick",
        "bars_required": 1,
        "direction": -1,
        "description": "Down bar whose body covers >= 90% of its range.",
        "invalidation": "Close back inside the body.",
    },
    "bullish_engulfing": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": 1,
        "description": "Up bar whose body fully contains the prior down bar's body.",
        "invalidation": "Close below the engulfing bar's low.",
    },
    "bearish_engulfing": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": -1,
        "description": "Down bar whose body fully contains the prior up bar's body.",
        "invalidation": "Close above the engulfing bar's high.",
    },
    "inside_bar": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": 0,
        "description": "Bar range fully inside the prior bar's range: contraction, direction unresolved.",
        "invalidation": "Break of either side of the mother bar.",
    },
    "outside_bar": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": 0,
        "description": "Bar range fully contains the prior bar's range: expansion, direction from the close.",
        "invalidation": "None; it is a completed expansion event.",
    },
    "gap_up": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": 1,
        "description": "Bar low above the prior bar high.",
        "invalidation": "Gap fill (trade back through the prior high).",
    },
    "gap_down": {
        "family": "candlestick",
        "bars_required": 2,
        "direction": -1,
        "description": "Bar high below the prior bar low.",
        "invalidation": "Gap fill (trade back through the prior low).",
    },
    "three_white_soldiers": {
        "family": "candlestick",
        "bars_required": 3,
        "direction": 1,
        "description": "Three consecutive up bars, each closing above the prior close.",
        "invalidation": "Close below the first soldier's open.",
    },
    "three_black_crows": {
        "family": "candlestick",
        "bars_required": 3,
        "direction": -1,
        "description": "Three consecutive down bars, each closing below the prior close.",
        "invalidation": "Close above the first crow's open.",
    },
    "morning_star": {
        "family": "candlestick",
        "bars_required": 3,
        "direction": 1,
        "description": "Down bar, small-bodied middle bar, then an up bar closing above the first midpoint.",
        "invalidation": "Close below the star low.",
    },
    "evening_star": {
        "family": "candlestick",
        "bars_required": 3,
        "direction": -1,
        "description": "Up bar, small-bodied middle bar, then a down bar closing below the first midpoint.",
        "invalidation": "Close above the star high.",
    },
    "swing_high": {
        "family": "structure",
        "bars_required": 5,
        "direction": 0,
        "description": "Fractal high: highest high of the surrounding window. Confirmed `right_bars` later.",
        "invalidation": "A higher high.",
    },
    "swing_low": {
        "family": "structure",
        "bars_required": 5,
        "direction": 0,
        "description": "Fractal low: lowest low of the surrounding window. Confirmed `right_bars` later.",
        "invalidation": "A lower low.",
    },
    "break_of_structure_up": {
        "family": "structure",
        "bars_required": 5,
        "direction": 1,
        "description": "Close above the most recent CONFIRMED swing high.",
        "invalidation": "Close back below that swing high.",
    },
    "break_of_structure_down": {
        "family": "structure",
        "bars_required": 5,
        "direction": -1,
        "description": "Close below the most recent CONFIRMED swing low.",
        "invalidation": "Close back above that swing low.",
    },
    "donchian_breakout_up": {
        "family": "structure",
        "bars_required": 20,
        "direction": 1,
        "description": "Close above the prior 20-bar highest high.",
        "invalidation": "Close back inside the channel.",
    },
    "donchian_breakout_down": {
        "family": "structure",
        "bars_required": 20,
        "direction": -1,
        "description": "Close below the prior 20-bar lowest low.",
        "invalidation": "Close back inside the channel.",
    },
    "squeeze_release": {
        "family": "volatility",
        "bars_required": 20,
        "direction": 0,
        "description": "Bollinger width leaves the bottom decile of its own 100-bar history.",
        "invalidation": "Width returns to the low decile without a range expansion.",
    },
    "rsi_bullish_divergence": {
        "family": "divergence",
        "bars_required": 5,
        "direction": 1,
        "description": "Lower confirmed swing low in price with a higher RSI at that low.",
        "invalidation": "New low with a new RSI low.",
    },
    "rsi_bearish_divergence": {
        "family": "divergence",
        "bars_required": 5,
        "direction": -1,
        "description": "Higher confirmed swing high in price with a lower RSI at that high.",
        "invalidation": "New high with a new RSI high.",
    },
}

DOJI_BODY_FRACTION = 0.10
WICK_BODY_MULTIPLE = 2.0
MARUBOZU_BODY_FRACTION = 0.90
STAR_BODY_FRACTION = 0.35
SQUEEZE_LOOKBACK = 100
SQUEEZE_DECILE = 0.10


def _body(bar: Mapping[str, Any]) -> float:
    return abs(float(bar["close"]) - float(bar["open"]))


def _range(bar: Mapping[str, Any]) -> float:
    return float(bar["high"]) - float(bar["low"])


def _atr_norm(value: float, atr_value: float | None) -> float | None:
    if atr_value is None or atr_value <= 0:
        return None
    return round(value / atr_value, 6)


def swing_pivots(
    normalized: Mapping[str, Any],
    left_bars: int = 2,
    right_bars: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    """Fractal swing highs/lows with explicit confirmation lag.

    A pivot at `index` is only knowable at `index + right_bars`; that value is returned as
    `confirmed_at_index` and is the ONLY index a causal rule may use.
    """
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be >= 1")
    series_bars = normalized["bars"]
    highs = bars_mod.highs(normalized)
    lows = bars_mod.lows(normalized)
    length = len(series_bars)
    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []
    for index in range(left_bars, length - right_bars):
        window = range(index - left_bars, index + right_bars + 1)
        if all(highs[index] >= highs[other] for other in window) and any(
            highs[index] > highs[other] for other in window if other != index
        ):
            swing_highs.append(
                {
                    "index": index,
                    "observed_at": series_bars[index]["observed_at"],
                    "price": highs[index],
                    "confirmed_at_index": index + right_bars,
                    "confirmed_at": series_bars[index + right_bars]["observed_at"],
                }
            )
        if all(lows[index] <= lows[other] for other in window) and any(
            lows[index] < lows[other] for other in window if other != index
        ):
            swing_lows.append(
                {
                    "index": index,
                    "observed_at": series_bars[index]["observed_at"],
                    "price": lows[index],
                    "confirmed_at_index": index + right_bars,
                    "confirmed_at": series_bars[index + right_bars]["observed_at"],
                }
            )
    return {
        "left_bars": left_bars,
        "right_bars": right_bars,
        "confirmation_lag_bars": right_bars,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


def market_structure(
    normalized: Mapping[str, Any],
    left_bars: int = 2,
    right_bars: int = 2,
) -> dict[str, Any]:
    """Trend label from CONFIRMED swings only.

    `trend` is a description of realized structure ("the last two confirmed highs were higher"), not a
    prediction. `as_of_index` is the last bar; every swing referenced was confirmed at or before it.
    """
    pivots = swing_pivots(normalized, left_bars, right_bars)
    last_index = int(normalized["bar_count"]) - 1
    highs = [item for item in pivots["swing_highs"] if item["confirmed_at_index"] <= last_index]
    lows = [item for item in pivots["swing_lows"] if item["confirmed_at_index"] <= last_index]

    def _label(points: Sequence[Mapping[str, Any]]) -> str:
        if len(points) < 2:
            return "INSUFFICIENT_SWINGS"
        return "RISING" if points[-1]["price"] > points[-2]["price"] else "FALLING"

    high_label = _label(highs)
    low_label = _label(lows)
    if high_label == "RISING" and low_label == "RISING":
        trend = "UPTREND_STRUCTURE"
    elif high_label == "FALLING" and low_label == "FALLING":
        trend = "DOWNTREND_STRUCTURE"
    elif "INSUFFICIENT_SWINGS" in (high_label, low_label):
        trend = "INSUFFICIENT_SWINGS"
    else:
        trend = "RANGE_OR_TRANSITION"

    return {
        "as_of_index": last_index,
        "as_of": normalized["bars"][last_index]["observed_at"],
        "confirmation_lag_bars": right_bars,
        "confirmed_swing_high_count": len(highs),
        "confirmed_swing_low_count": len(lows),
        "swing_high_sequence": high_label,
        "swing_low_sequence": low_label,
        "trend": trend,
        "last_confirmed_swing_high": highs[-1] if highs else None,
        "last_confirmed_swing_low": lows[-1] if lows else None,
        "forecast_probability": None,
    }


def support_resistance(
    normalized: Mapping[str, Any],
    left_bars: int = 2,
    right_bars: int = 2,
    tolerance_atr: float = 0.5,
) -> dict[str, Any]:
    """Cluster confirmed pivots into levels, tolerance scaled by ATR so it travels across symbols.

    `touch_count` is a *count of realized touches*, nothing more. It is reported because it is measurable, and
    deliberately not converted into a strength score, which would smuggle a forecast in as a number.
    """
    pivots = swing_pivots(normalized, left_bars, right_bars)
    last_index = int(normalized["bar_count"]) - 1
    atr_series = ind.atr(
        bars_mod.highs(normalized), bars_mod.lows(normalized), bars_mod.closes(normalized)
    )
    atr_value = atr_series[last_index]
    if atr_value is None or atr_value <= 0:
        return {
            "status": "BLOCKED",
            "reason": "ATR undefined; cannot scale a level tolerance without it",
            "levels": [],
        }
    tolerance = tolerance_atr * atr_value

    points = [
        {"price": item["price"], "kind": kind, "index": item["index"]}
        for kind, group in (("resistance", pivots["swing_highs"]), ("support", pivots["swing_lows"]))
        for item in group
        if item["confirmed_at_index"] <= last_index
    ]
    points.sort(key=lambda item: item["price"])

    levels: list[dict[str, Any]] = []
    for point in points:
        if levels and abs(point["price"] - levels[-1]["_sum"] / levels[-1]["touch_count"]) <= tolerance:
            levels[-1]["_sum"] += point["price"]
            levels[-1]["touch_count"] += 1
            levels[-1]["kinds"].add(point["kind"])
            levels[-1]["last_touch_index"] = max(levels[-1]["last_touch_index"], point["index"])
        else:
            levels.append(
                {
                    "_sum": point["price"],
                    "touch_count": 1,
                    "kinds": {point["kind"]},
                    "last_touch_index": point["index"],
                }
            )

    last_close = bars_mod.closes(normalized)[last_index]
    out: list[dict[str, Any]] = []
    for level in levels:
        price = level["_sum"] / level["touch_count"]
        out.append(
            {
                "price": round(price, 8),
                "touch_count": level["touch_count"],
                "kinds": sorted(level["kinds"]),
                "last_touch_index": level["last_touch_index"],
                "distance_bps": round((price / last_close - 1.0) * 10_000.0, 4),
                "side": "above" if price > last_close else "below",
            }
        )
    return {
        "status": "OK",
        "tolerance_atr": tolerance_atr,
        "tolerance_price": round(tolerance, 8),
        "atr14": round(atr_value, 8),
        "level_count": len(out),
        "levels": out,
        "forecast_probability": None,
    }


def _candlestick_detections(
    normalized: Mapping[str, Any],
    atr_series: ind.Series,
) -> list[dict[str, Any]]:
    series_bars = normalized["bars"]
    found: list[dict[str, Any]] = []

    def add(index: int, name: str, measures: dict[str, Any]) -> None:
        found.append(
            {
                "index": index,
                "observed_at": series_bars[index]["observed_at"],
                "pattern": name,
                "direction": PATTERNS[name]["direction"],
                "detected_at_index": index,
                "detected_at": series_bars[index]["observed_at"],
                "measures": measures,
            }
        )

    for index, bar in enumerate(series_bars):
        body = _body(bar)
        span = _range(bar)
        atr_value = atr_series[index]
        upper_wick = float(bar["high"]) - max(float(bar["open"]), float(bar["close"]))
        lower_wick = min(float(bar["open"]), float(bar["close"])) - float(bar["low"])
        base = {"body_atr": _atr_norm(body, atr_value), "range_atr": _atr_norm(span, atr_value)}
        if span > 0 and body <= DOJI_BODY_FRACTION * span:
            add(index, "doji", base | {"body_fraction": round(body / span, 6)})
        if body > 0 and lower_wick >= WICK_BODY_MULTIPLE * body and upper_wick <= body:
            add(index, "hammer", base | {"lower_wick_body_ratio": round(lower_wick / body, 6)})
        if body > 0 and upper_wick >= WICK_BODY_MULTIPLE * body and lower_wick <= body:
            add(index, "shooting_star", base | {"upper_wick_body_ratio": round(upper_wick / body, 6)})
        if span > 0 and body >= MARUBOZU_BODY_FRACTION * span:
            name = "marubozu_bull" if float(bar["close"]) > float(bar["open"]) else "marubozu_bear"
            add(index, name, base | {"body_fraction": round(body / span, 6)})

        if index >= 1:
            previous = series_bars[index - 1]
            previous_body_low = min(float(previous["open"]), float(previous["close"]))
            previous_body_high = max(float(previous["open"]), float(previous["close"]))
            body_low = min(float(bar["open"]), float(bar["close"]))
            body_high = max(float(bar["open"]), float(bar["close"]))
            rising = float(bar["close"]) > float(bar["open"])
            previous_rising = float(previous["close"]) > float(previous["open"])
            engulfs = body_low <= previous_body_low and body_high >= previous_body_high and body > 0
            if engulfs and rising and not previous_rising:
                add(index, "bullish_engulfing", base)
            if engulfs and not rising and previous_rising:
                add(index, "bearish_engulfing", base)
            if float(bar["high"]) <= float(previous["high"]) and float(bar["low"]) >= float(previous["low"]):
                add(index, "inside_bar", base | {"contraction": round(span / max(_range(previous), 1e-12), 6)})
            if float(bar["high"]) >= float(previous["high"]) and float(bar["low"]) <= float(previous["low"]):
                add(index, "outside_bar", base | {"expansion": round(span / max(_range(previous), 1e-12), 6)})
            if float(bar["low"]) > float(previous["high"]):
                gap = float(bar["low"]) - float(previous["high"])
                add(index, "gap_up", base | {"gap_atr": _atr_norm(gap, atr_value)})
            if float(bar["high"]) < float(previous["low"]):
                gap = float(previous["low"]) - float(bar["high"])
                add(index, "gap_down", base | {"gap_atr": _atr_norm(gap, atr_value)})

        if index >= 2:
            first, middle, last = series_bars[index - 2], series_bars[index - 1], bar
            ups = [float(item["close"]) > float(item["open"]) for item in (first, middle, last)]
            closes_rising = float(middle["close"]) > float(first["close"]) and float(last["close"]) > float(
                middle["close"]
            )
            closes_falling = float(middle["close"]) < float(first["close"]) and float(last["close"]) < float(
                middle["close"]
            )
            if all(ups) and closes_rising:
                add(index, "three_white_soldiers", base)
            if not any(ups) and closes_falling:
                add(index, "three_black_crows", base)
            first_span = _range(first)
            middle_small = first_span > 0 and _body(middle) <= STAR_BODY_FRACTION * first_span
            first_midpoint = (float(first["open"]) + float(first["close"])) / 2.0
            if (
                middle_small
                and not ups[0]
                and ups[2]
                and float(last["close"]) > first_midpoint
            ):
                add(index, "morning_star", base)
            if (
                middle_small
                and ups[0]
                and not ups[2]
                and float(last["close"]) < first_midpoint
            ):
                add(index, "evening_star", base)
    return found


def _structure_detections(
    normalized: Mapping[str, Any],
    atr_series: ind.Series,
    left_bars: int,
    right_bars: int,
) -> list[dict[str, Any]]:
    series_bars = normalized["bars"]
    closes = bars_mod.closes(normalized)
    highs = bars_mod.highs(normalized)
    lows = bars_mod.lows(normalized)
    pivots = swing_pivots(normalized, left_bars, right_bars)
    found: list[dict[str, Any]] = []

    for kind, group in (("swing_high", pivots["swing_highs"]), ("swing_low", pivots["swing_lows"])):
        for item in group:
            found.append(
                {
                    "index": item["index"],
                    "observed_at": item["observed_at"],
                    "pattern": kind,
                    "direction": 0,
                    "detected_at_index": item["confirmed_at_index"],
                    "detected_at": item["confirmed_at"],
                    "measures": {"price": item["price"]},
                }
            )

    # break of structure: walk forward carrying only pivots already confirmed at the current bar
    confirmed_highs: list[dict[str, Any]] = []
    confirmed_lows: list[dict[str, Any]] = []
    high_queue = sorted(pivots["swing_highs"], key=lambda item: item["confirmed_at_index"])
    low_queue = sorted(pivots["swing_lows"], key=lambda item: item["confirmed_at_index"])
    high_cursor = low_cursor = 0
    broken_high: float | None = None
    broken_low: float | None = None
    for index in range(len(series_bars)):
        while high_cursor < len(high_queue) and high_queue[high_cursor]["confirmed_at_index"] <= index:
            confirmed_highs.append(high_queue[high_cursor])
            broken_high = None
            high_cursor += 1
        while low_cursor < len(low_queue) and low_queue[low_cursor]["confirmed_at_index"] <= index:
            confirmed_lows.append(low_queue[low_cursor])
            broken_low = None
            low_cursor += 1
        if confirmed_highs:
            level = confirmed_highs[-1]["price"]
            if closes[index] > level and broken_high != level:
                broken_high = level
                found.append(
                    {
                        "index": index,
                        "observed_at": series_bars[index]["observed_at"],
                        "pattern": "break_of_structure_up",
                        "direction": 1,
                        "detected_at_index": index,
                        "detected_at": series_bars[index]["observed_at"],
                        "measures": {
                            "level": level,
                            "excess_atr": _atr_norm(closes[index] - level, atr_series[index]),
                            "swing_index": confirmed_highs[-1]["index"],
                        },
                    }
                )
        if confirmed_lows:
            level = confirmed_lows[-1]["price"]
            if closes[index] < level and broken_low != level:
                broken_low = level
                found.append(
                    {
                        "index": index,
                        "observed_at": series_bars[index]["observed_at"],
                        "pattern": "break_of_structure_down",
                        "direction": -1,
                        "detected_at_index": index,
                        "detected_at": series_bars[index]["observed_at"],
                        "measures": {
                            "level": level,
                            "excess_atr": _atr_norm(level - closes[index], atr_series[index]),
                            "swing_index": confirmed_lows[-1]["index"],
                        },
                    }
                )

    # donchian breakouts compare against the PRIOR window, excluding the breaking bar itself
    prior_high = ind.rolling_max(highs, 20)
    prior_low = ind.rolling_min(lows, 20)
    for index in range(1, len(series_bars)):
        reference_high = prior_high[index - 1]
        reference_low = prior_low[index - 1]
        if reference_high is not None and closes[index] > reference_high:
            found.append(
                {
                    "index": index,
                    "observed_at": series_bars[index]["observed_at"],
                    "pattern": "donchian_breakout_up",
                    "direction": 1,
                    "detected_at_index": index,
                    "detected_at": series_bars[index]["observed_at"],
                    "measures": {
                        "level": reference_high,
                        "excess_atr": _atr_norm(closes[index] - reference_high, atr_series[index]),
                    },
                }
            )
        if reference_low is not None and closes[index] < reference_low:
            found.append(
                {
                    "index": index,
                    "observed_at": series_bars[index]["observed_at"],
                    "pattern": "donchian_breakout_down",
                    "direction": -1,
                    "detected_at_index": index,
                    "detected_at": series_bars[index]["observed_at"],
                    "measures": {
                        "level": reference_low,
                        "excess_atr": _atr_norm(reference_low - closes[index], atr_series[index]),
                    },
                }
            )
    return found


def _squeeze_detections(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    series_bars = normalized["bars"]
    closes = bars_mod.closes(normalized)
    upper, mid, lower = ind.bollinger(closes)
    width: list[float | None] = [
        None
        if (upper[i] is None or lower[i] is None or not mid[i])
        else (upper[i] - lower[i]) / mid[i]
        for i in range(len(closes))
    ]
    found: list[dict[str, Any]] = []
    for index in range(1, len(closes)):
        window = [value for value in width[max(0, index - SQUEEZE_LOOKBACK) : index] if value is not None]
        if len(window) < SQUEEZE_LOOKBACK or width[index] is None or width[index - 1] is None:
            continue
        ordered = sorted(window)
        threshold = ordered[max(0, int(SQUEEZE_DECILE * len(ordered)) - 1)]
        if width[index - 1] <= threshold < width[index]:
            found.append(
                {
                    "index": index,
                    "observed_at": series_bars[index]["observed_at"],
                    "pattern": "squeeze_release",
                    "direction": 0,
                    "detected_at_index": index,
                    "detected_at": series_bars[index]["observed_at"],
                    "measures": {
                        "width": round(width[index], 8),
                        "prior_width": round(width[index - 1], 8),
                        "decile_threshold": round(threshold, 8),
                    },
                }
            )
    return found


def _divergence_detections(
    normalized: Mapping[str, Any],
    left_bars: int,
    right_bars: int,
) -> list[dict[str, Any]]:
    rsi_series = ind.rsi(bars_mod.closes(normalized))
    pivots = swing_pivots(normalized, left_bars, right_bars)
    found: list[dict[str, Any]] = []

    def scan(group: Sequence[Mapping[str, Any]], name: str, lower_price: bool) -> None:
        usable = [item for item in group if rsi_series[item["index"]] is not None]
        for previous, current in zip(usable, usable[1:], strict=False):
            price_moved = (
                current["price"] < previous["price"] if lower_price else current["price"] > previous["price"]
            )
            rsi_moved = (
                rsi_series[current["index"]] > rsi_series[previous["index"]]
                if lower_price
                else rsi_series[current["index"]] < rsi_series[previous["index"]]
            )
            if price_moved and rsi_moved:
                found.append(
                    {
                        "index": current["index"],
                        "observed_at": current["observed_at"],
                        "pattern": name,
                        "direction": PATTERNS[name]["direction"],
                        "detected_at_index": current["confirmed_at_index"],
                        "detected_at": current["confirmed_at"],
                        "measures": {
                            "prior_price": previous["price"],
                            "price": current["price"],
                            "prior_rsi": round(rsi_series[previous["index"]], 6),
                            "rsi": round(rsi_series[current["index"]], 6),
                        },
                    }
                )

    scan(pivots["swing_lows"], "rsi_bullish_divergence", lower_price=True)
    scan(pivots["swing_highs"], "rsi_bearish_divergence", lower_price=False)
    return found


def detect_patterns(
    normalized: Mapping[str, Any],
    names: Sequence[str] | None = None,
    *,
    left_bars: int = 2,
    right_bars: int = 2,
) -> dict[str, Any]:
    """Detect every registered pattern (or the requested subset).

    Detections are sorted by `detected_at_index` then `index`, i.e. in the order an operator could have learned
    them, which is the order `scan.py` consumes.
    """
    if names is not None:
        unknown = [name for name in names if name not in PATTERNS]
        if unknown:
            raise KeyError(f"unknown patterns: {unknown}")
    atr_series = ind.atr(
        bars_mod.highs(normalized), bars_mod.lows(normalized), bars_mod.closes(normalized)
    )
    detections = (
        _candlestick_detections(normalized, atr_series)
        + _structure_detections(normalized, atr_series, left_bars, right_bars)
        + _squeeze_detections(normalized)
        + _divergence_detections(normalized, left_bars, right_bars)
    )
    if names is not None:
        wanted = set(names)
        detections = [item for item in detections if item["pattern"] in wanted]
    detections.sort(key=lambda item: (item["detected_at_index"], item["index"], item["pattern"]))
    counts: dict[str, int] = {}
    for item in detections:
        counts[item["pattern"]] = counts.get(item["pattern"], 0) + 1
    return {
        "schema": "dimwit.market-pattern-observation.v1",
        "producer": "dimwit",
        "symbol": normalized["symbol"],
        "timeframe": normalized["timeframe"],
        "as_of": normalized["as_of"],
        "series_digest": normalized["digest"],
        "confirmation_lag_bars": right_bars,
        "pattern_family_size": len(PATTERNS if names is None else names),
        "detection_count": len(detections),
        "counts_by_pattern": dict(sorted(counts.items())),
        "detections": detections,
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


def pattern_flags(
    normalized: Mapping[str, Any],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
) -> list[dict[str, bool]]:
    """Per-bar boolean pattern flags keyed on `detected_at_index`.

    This is the causal view `scan.py` needs: `flags[i][name]` is True only if the pattern was knowable at bar
    *i*, so a rule reading it cannot accidentally consume an unconfirmed pivot.
    """
    observation = detect_patterns(normalized, left_bars=left_bars, right_bars=right_bars)
    flags = [dict.fromkeys(PATTERNS, False) for _ in range(int(normalized["bar_count"]))]
    for item in observation["detections"]:
        flags[item["detected_at_index"]][item["pattern"]] = True
    return flags
