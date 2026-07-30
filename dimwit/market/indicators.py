"""Deterministic, prefix-stable technical indicators.

Two rules govern everything in this module.

**1. Prefix stability (no lookahead).** Every series returned here satisfies

    indicator(bars)[i] == indicator(bars[:i+1])[-1]

for all *i* past the warmup. That is enforced mechanically by construction: every value is a function of
`values[:i+1]` only — recursive indicators (EMA, Wilder RSI/ATR/ADX, Supertrend) carry state forward and never
peek, and rolling windows always end at *i*. `tests/test_market_indicators.py` asserts it per indicator rather
than trusting the claim.

**2. Warmup is `None`, not a guess.** Before an indicator has enough bars it emits `None`. It never back-fills
with a shorter window, because a "20-period SMA" computed from 6 bars is a different statistic wearing the same
name, and downstream walk-forward accounting would silently mix the two.

Periods are fixed canonical values (the ones the rest of the industry quotes) instead of tunable knobs. Free
parameters are where overfitting enters, and the search-space disclosure in `scan.py` only means something if
the feature panel is not itself being tuned. The low-level primitives (`sma`, `ema`, `wilder`, ...) are public
for callers that genuinely need another period.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from . import bars as bars_mod

Series = list[float | None]

# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def sma(values: Sequence[float], period: int) -> Series:
    """Simple moving average. `None` until `period` samples exist."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            out[index] = running / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """Exponential moving average, seeded with the SMA of the first `period` samples (Wilder-style seeding,
    so the value is deterministic and independent of how much history precedes the window)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    state = sum(values[:period]) / period
    out[period - 1] = state
    for index in range(period, len(values)):
        state = alpha * values[index] + (1.0 - alpha) * state
        out[index] = state
    return out


def wilder(values: Sequence[float], period: int) -> Series:
    """Wilder's smoothing (a.k.a. RMA): the recursion behind RSI, ATR and ADX."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    state = sum(values[:period]) / period
    out[period - 1] = state
    for index in range(period, len(values)):
        state = (state * (period - 1) + values[index]) / period
        out[index] = state
    return out


def rolling_max(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    for index in range(period - 1, len(values)):
        out[index] = max(values[index - period + 1 : index + 1])
    return out


def rolling_min(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    for index in range(period - 1, len(values)):
        out[index] = min(values[index - period + 1 : index + 1])
    return out


def rolling_stdev(values: Sequence[float], period: int) -> Series:
    """Population standard deviation over the trailing window (population, not sample: the window IS the
    population being described, and the choice must be pinned so digests are reproducible)."""
    out: Series = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        mean = sum(window) / period
        out[index] = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
    return out


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> Series:
    out: Series = [None] * len(closes)
    for index in range(1, len(closes)):
        previous_close = closes[index - 1]
        out[index] = max(
            highs[index] - lows[index],
            abs(highs[index] - previous_close),
            abs(lows[index] - previous_close),
        )
    return out


def _compact(values: Series, start: int) -> list[float]:
    """The non-None tail of a warmup-padded series, from `start` onward."""
    return [value for value in values[start:] if value is not None]


def rsi(closes: Sequence[float], period: int = 14) -> Series:
    """Wilder RSI. Note this is *not* the flat-average RSI in DumbMoney's legacy
    `technical_analysis._rsi`; `rsi_simple` reproduces that one so the bridge can report both and the
    difference stays visible instead of being quietly reconciled."""
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains[index] = max(change, 0.0)
        losses[index] = max(-change, 0.0)
    average_gain = sum(gains[1 : period + 1]) / period
    average_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_from(average_gain, average_loss)
    for index in range(period + 1, len(closes)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
        out[index] = _rsi_from(average_gain, average_loss)
    return out


def _rsi_from(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 100.0 if average_gain > 0.0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def rsi_simple(closes: Sequence[float], period: int = 14) -> Series:
    """Flat-average RSI over the trailing `period` changes — DumbMoney's legacy formulation, kept for
    parity/diff reporting only."""
    out: Series = [None] * len(closes)
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    for index in range(period, len(closes)):
        window = changes[index - period : index]
        gains = sum(max(change, 0.0) for change in window) / period
        losses = sum(max(-change, 0.0) for change in window) / period
        out[index] = _rsi_from(gains, losses)
    return out


def macd(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[Series, Series, Series]:
    """MACD line, signal line, histogram. The signal EMA is seeded from the first `signal` *defined* MACD
    values, so it too is prefix-stable."""
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: Series = [
        None if (fast_ema[i] is None or slow_ema[i] is None) else fast_ema[i] - slow_ema[i]
        for i in range(len(closes))
    ]
    first_defined = next((i for i, value in enumerate(line) if value is not None), None)
    signal_series: Series = [None] * len(closes)
    histogram: Series = [None] * len(closes)
    if first_defined is not None:
        defined = [value for value in line[first_defined:] if value is not None]
        smoothed = ema(defined, signal)
        for offset, value in enumerate(smoothed):
            signal_series[first_defined + offset] = value
    for index in range(len(closes)):
        if line[index] is not None and signal_series[index] is not None:
            histogram[index] = line[index] - signal_series[index]
    return line, signal_series, histogram


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Series:
    ranges = true_range(highs, lows, closes)
    defined = [value for value in ranges if value is not None]
    smoothed = wilder(defined, period)
    out: Series = [None] * len(closes)
    for offset, value in enumerate(smoothed):
        out[offset + 1] = value
    return out


def bollinger(
    closes: Sequence[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[Series, Series, Series]:
    mid = sma(closes, period)
    deviation = rolling_stdev(closes, period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for index in range(len(closes)):
        if mid[index] is None or deviation[index] is None:
            continue
        upper[index] = mid[index] + deviations * deviation[index]
        lower[index] = mid[index] - deviations * deviation[index]
    return upper, mid, lower


def keltner(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> tuple[Series, Series, Series]:
    mid = ema(closes, period)
    band = atr(highs, lows, closes, atr_period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for index in range(len(closes)):
        if mid[index] is None or band[index] is None:
            continue
        upper[index] = mid[index] + multiplier * band[index]
        lower[index] = mid[index] - multiplier * band[index]
    return upper, mid, lower


def donchian(
    highs: Sequence[float],
    lows: Sequence[float],
    period: int = 20,
) -> tuple[Series, Series, Series]:
    upper = rolling_max(highs, period)
    lower = rolling_min(lows, period)
    mid: Series = [
        None if (upper[i] is None or lower[i] is None) else (upper[i] + lower[i]) / 2.0
        for i in range(len(highs))
    ]
    return upper, mid, lower


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
    smooth: int = 3,
) -> tuple[Series, Series]:
    highest = rolling_max(highs, period)
    lowest = rolling_min(lows, period)
    percent_k: Series = [None] * len(closes)
    for index in range(len(closes)):
        if highest[index] is None or lowest[index] is None:
            continue
        span = highest[index] - lowest[index]
        percent_k[index] = 50.0 if span <= 0 else 100.0 * (closes[index] - lowest[index]) / span
    first_defined = next((i for i, value in enumerate(percent_k) if value is not None), None)
    percent_d: Series = [None] * len(closes)
    if first_defined is not None:
        defined = [value for value in percent_k[first_defined:] if value is not None]
        smoothed = sma(defined, smooth)
        for offset, value in enumerate(smoothed):
            percent_d[first_defined + offset] = value
    return percent_k, percent_d


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> tuple[Series, Series, Series]:
    """Wilder ADX with +DI / -DI. Returns (adx, di_plus, di_minus)."""
    length = len(closes)
    plus_dm = [0.0] * length
    minus_dm = [0.0] * length
    for index in range(1, length):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm[index] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[index] = down_move if (down_move > up_move and down_move > 0) else 0.0
    ranges = true_range(highs, lows, closes)
    tr_defined = [value for value in ranges if value is not None]
    smoothed_tr = wilder(tr_defined, period)
    smoothed_plus = wilder(plus_dm[1:], period)
    smoothed_minus = wilder(minus_dm[1:], period)

    di_plus: Series = [None] * length
    di_minus: Series = [None] * length
    dx_defined: list[float] = []
    dx_index: list[int] = []
    for offset in range(len(smoothed_tr)):
        index = offset + 1
        tr_value = smoothed_tr[offset]
        if tr_value is None or smoothed_plus[offset] is None or smoothed_minus[offset] is None:
            continue
        if tr_value <= 0:
            di_plus[index] = 0.0
            di_minus[index] = 0.0
        else:
            di_plus[index] = 100.0 * smoothed_plus[offset] / tr_value
            di_minus[index] = 100.0 * smoothed_minus[offset] / tr_value
        total = di_plus[index] + di_minus[index]
        dx_defined.append(0.0 if total <= 0 else 100.0 * abs(di_plus[index] - di_minus[index]) / total)
        dx_index.append(index)

    adx_series: Series = [None] * length
    smoothed_dx = wilder(dx_defined, period)
    for offset, value in enumerate(smoothed_dx):
        if value is not None:
            adx_series[dx_index[offset]] = value
    return adx_series, di_plus, di_minus


def obv(closes: Sequence[float], volumes: Sequence[float]) -> Series:
    out: Series = [0.0] * len(closes)
    running = 0.0
    for index in range(1, len(closes)):
        if closes[index] > closes[index - 1]:
            running += volumes[index]
        elif closes[index] < closes[index - 1]:
            running -= volumes[index]
        out[index] = running
    return out


def vwap_cumulative(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> Series:
    """Volume-weighted average price accumulated from the first bar of the supplied series.

    Deliberately NOT session-anchored: the bar series carries no session metadata, and inventing a session
    boundary would make the value depend on an assumption the data does not support. Callers that need a
    session VWAP should slice the series to the session first.
    """
    out: Series = [None] * len(closes)
    price_volume = 0.0
    total_volume = 0.0
    for index in range(len(closes)):
        typical = (highs[index] + lows[index] + closes[index]) / 3.0
        price_volume += typical * volumes[index]
        total_volume += volumes[index]
        out[index] = typical if total_volume <= 0 else price_volume / total_volume
    return out


def cci(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
) -> Series:
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    mean_series = sma(typical, period)
    out: Series = [None] * len(closes)
    for index in range(len(closes)):
        if mean_series[index] is None:
            continue
        window = typical[index - period + 1 : index + 1]
        mean_deviation = sum(abs(value - mean_series[index]) for value in window) / period
        out[index] = 0.0 if mean_deviation == 0 else (typical[index] - mean_series[index]) / (
            0.015 * mean_deviation
        )
    return out


def williams_r(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Series:
    highest = rolling_max(highs, period)
    lowest = rolling_min(lows, period)
    out: Series = [None] * len(closes)
    for index in range(len(closes)):
        if highest[index] is None or lowest[index] is None:
            continue
        span = highest[index] - lowest[index]
        out[index] = -50.0 if span <= 0 else -100.0 * (highest[index] - closes[index]) / span
    return out


def roc_bps(values: Sequence[float], period: int = 10) -> Series:
    out: Series = [None] * len(values)
    for index in range(period, len(values)):
        previous = values[index - period]
        if previous <= 0:
            continue
        out[index] = (values[index] / previous - 1.0) * 10_000.0
    return out


def mfi(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 14,
) -> Series:
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    positive = [0.0] * len(closes)
    negative = [0.0] * len(closes)
    for index in range(1, len(closes)):
        flow = typical[index] * volumes[index]
        if typical[index] > typical[index - 1]:
            positive[index] = flow
        elif typical[index] < typical[index - 1]:
            negative[index] = flow
    out: Series = [None] * len(closes)
    for index in range(period, len(closes)):
        positive_flow = sum(positive[index - period + 1 : index + 1])
        negative_flow = sum(negative[index - period + 1 : index + 1])
        if negative_flow == 0:
            out[index] = 100.0 if positive_flow > 0 else 50.0
        else:
            out[index] = 100.0 - (100.0 / (1.0 + positive_flow / negative_flow))
    return out


def supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[Series, Series]:
    """ATR-banded trend follower. Returns (line, direction) where direction is +1 / -1 / None."""
    band = atr(highs, lows, closes, period)
    line: Series = [None] * len(closes)
    direction: Series = [None] * len(closes)
    final_upper: float | None = None
    final_lower: float | None = None
    trend = 1
    for index in range(len(closes)):
        if band[index] is None:
            continue
        midpoint = (highs[index] + lows[index]) / 2.0
        basic_upper = midpoint + multiplier * band[index]
        basic_lower = midpoint - multiplier * band[index]
        previous_close = closes[index - 1] if index > 0 else closes[index]
        if final_upper is None:
            final_upper, final_lower = basic_upper, basic_lower
            trend = 1 if closes[index] >= midpoint else -1
        else:
            final_upper = (
                min(basic_upper, final_upper) if previous_close <= final_upper else basic_upper
            )
            final_lower = (
                max(basic_lower, final_lower) if previous_close >= final_lower else basic_lower
            )
            if closes[index] > final_upper:
                trend = 1
            elif closes[index] < final_lower:
                trend = -1
        line[index] = final_lower if trend > 0 else final_upper
        direction[index] = float(trend)
    return line, direction


def zscore(values: Sequence[float], period: int = 20) -> Series:
    mean_series = sma(values, period)
    deviation = rolling_stdev(values, period)
    out: Series = [None] * len(values)
    for index in range(len(values)):
        if mean_series[index] is None or deviation[index] is None:
            continue
        out[index] = 0.0 if deviation[index] == 0 else (values[index] - mean_series[index]) / deviation[index]
    return out


def realized_vol_bps(closes: Sequence[float], period: int = 20) -> Series:
    """Standard deviation of per-bar log returns, expressed in basis points. Unannualized on purpose: an
    annualization factor would encode a bars-per-year assumption the series cannot justify."""
    log_returns: list[float | None] = [None] * len(closes)
    for index in range(1, len(closes)):
        if closes[index - 1] > 0:
            log_returns[index] = math.log(closes[index] / closes[index - 1])
    out: Series = [None] * len(closes)
    for index in range(period, len(closes)):
        window = [value for value in log_returns[index - period + 1 : index + 1] if value is not None]
        if len(window) < period:
            continue
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        out[index] = math.sqrt(variance) * 10_000.0
    return out


# ---------------------------------------------------------------------------
# canonical panel
# ---------------------------------------------------------------------------

#: name -> {description, warmup_bars, family}. The knowledge pack cites this and `selfaudit` counts it, so a
#: new indicator is not "shipped" until it appears here.
INDICATORS: dict[str, dict[str, Any]] = {
    "last_close": {"family": "price", "warmup_bars": 1, "description": "Most recent close."},
    "true_range": {"family": "volatility", "warmup_bars": 2, "description": "Wilder true range of the bar."},
    "sma20": {"family": "trend", "warmup_bars": 20, "description": "20-bar simple moving average."},
    "sma50": {"family": "trend", "warmup_bars": 50, "description": "50-bar simple moving average."},
    "sma200": {"family": "trend", "warmup_bars": 200, "description": "200-bar simple moving average."},
    "ema12": {"family": "trend", "warmup_bars": 12, "description": "12-bar EMA (MACD fast leg)."},
    "ema26": {"family": "trend", "warmup_bars": 26, "description": "26-bar EMA (MACD slow leg)."},
    "macd": {"family": "momentum", "warmup_bars": 26, "description": "EMA12 - EMA26."},
    "macd_signal": {"family": "momentum", "warmup_bars": 34, "description": "9-bar EMA of the MACD line."},
    "macd_hist": {"family": "momentum", "warmup_bars": 34, "description": "MACD line minus signal line."},
    "rsi14": {"family": "momentum", "warmup_bars": 15, "description": "Wilder 14-bar RSI."},
    "rsi14_simple": {
        "family": "momentum",
        "warmup_bars": 15,
        "description": "Flat-average 14-bar RSI (DumbMoney legacy formulation, parity only).",
    },
    "atr14": {"family": "volatility", "warmup_bars": 15, "description": "Wilder 14-bar average true range."},
    "atr14_percent": {
        "family": "volatility",
        "warmup_bars": 15,
        "description": "ATR14 as a percentage of the last close.",
    },
    "bb_upper20": {"family": "volatility", "warmup_bars": 20, "description": "Bollinger upper band (20, 2s)."},
    "bb_mid20": {"family": "volatility", "warmup_bars": 20, "description": "Bollinger midline (SMA20)."},
    "bb_lower20": {"family": "volatility", "warmup_bars": 20, "description": "Bollinger lower band (20, 2s)."},
    "bb_width20": {
        "family": "volatility",
        "warmup_bars": 20,
        "description": "Bollinger band width as a fraction of the midline (squeeze detector).",
    },
    "bb_percent_b20": {
        "family": "volatility",
        "warmup_bars": 20,
        "description": "Close position inside the Bollinger envelope (0 = lower band, 1 = upper).",
    },
    "keltner_upper20": {"family": "volatility", "warmup_bars": 20, "description": "Keltner upper (EMA20 + 2*ATR10)."},
    "keltner_lower20": {"family": "volatility", "warmup_bars": 20, "description": "Keltner lower (EMA20 - 2*ATR10)."},
    "donchian_high20": {"family": "structure", "warmup_bars": 20, "description": "Highest high of 20 bars."},
    "donchian_low20": {"family": "structure", "warmup_bars": 20, "description": "Lowest low of 20 bars."},
    "donchian_mid20": {"family": "structure", "warmup_bars": 20, "description": "Donchian channel midline."},
    "stoch_k14": {"family": "momentum", "warmup_bars": 14, "description": "Stochastic %K (14)."},
    "stoch_d14": {"family": "momentum", "warmup_bars": 16, "description": "Stochastic %D (SMA3 of %K)."},
    "adx14": {"family": "trend", "warmup_bars": 28, "description": "Wilder ADX (14) trend strength."},
    "di_plus14": {"family": "trend", "warmup_bars": 15, "description": "Wilder +DI (14)."},
    "di_minus14": {"family": "trend", "warmup_bars": 15, "description": "Wilder -DI (14)."},
    "obv": {"family": "volume", "warmup_bars": 1, "description": "On-balance volume, cumulative from bar 0."},
    "vwap_cum": {
        "family": "volume",
        "warmup_bars": 1,
        "description": "Cumulative VWAP from the first supplied bar (not session-anchored).",
    },
    "cci20": {"family": "momentum", "warmup_bars": 20, "description": "Commodity channel index (20)."},
    "willr14": {"family": "momentum", "warmup_bars": 14, "description": "Williams %R (14)."},
    "roc10_bps": {"family": "momentum", "warmup_bars": 11, "description": "10-bar rate of change in bps."},
    "mfi14": {"family": "volume", "warmup_bars": 15, "description": "Money flow index (14)."},
    "supertrend": {"family": "trend", "warmup_bars": 11, "description": "Supertrend line (ATR10, 3x)."},
    "supertrend_dir": {"family": "trend", "warmup_bars": 11, "description": "Supertrend direction, +1 or -1."},
    "zscore20": {"family": "meanrev", "warmup_bars": 20, "description": "Close z-score over 20 bars."},
    "realized_vol20_bps": {
        "family": "volatility",
        "warmup_bars": 21,
        "description": "Stdev of 20 per-bar log returns, in bps (unannualized).",
    },
    "return1_bps": {"family": "momentum", "warmup_bars": 2, "description": "1-bar return in bps."},
    "return5_bps": {"family": "momentum", "warmup_bars": 6, "description": "5-bar return in bps."},
    "return20_bps": {"family": "momentum", "warmup_bars": 21, "description": "20-bar return in bps."},
    "volume_sma20": {"family": "volume", "warmup_bars": 20, "description": "20-bar average volume."},
    "volume_ratio20": {
        "family": "volume",
        "warmup_bars": 20,
        "description": "Current volume divided by the 20-bar average volume.",
    },
    "dist_sma20_bps": {
        "family": "meanrev",
        "warmup_bars": 20,
        "description": "Close distance from SMA20 in bps.",
    },
    "dist_sma200_bps": {
        "family": "meanrev",
        "warmup_bars": 200,
        "description": "Close distance from SMA200 in bps.",
    },
}

INDICATOR_FAMILIES = tuple(sorted({spec["family"] for spec in INDICATORS.values()}))


def _ratio_bps(value: float, reference: float | None) -> float | None:
    if reference is None or reference == 0:
        return None
    return (value / reference - 1.0) * 10_000.0


def compute_all(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> dict[str, Series]:
    """Compute the whole canonical panel as full-length series."""
    length = len(closes)
    macd_line, macd_sig, macd_hist = macd(closes)
    bb_upper, bb_mid, bb_lower = bollinger(closes)
    kc_upper, _kc_mid, kc_lower = keltner(highs, lows, closes)
    dc_high, dc_mid, dc_low = donchian(highs, lows)
    stoch_k, stoch_d = stochastic(highs, lows, closes)
    adx_series, di_plus, di_minus = adx(highs, lows, closes)
    st_line, st_dir = supertrend(highs, lows, closes)
    atr_series = atr(highs, lows, closes)
    sma20_series = sma(closes, 20)
    sma200_series = sma(closes, 200)
    volume_sma = sma(volumes, 20)

    panel: dict[str, Series] = {
        "last_close": list(closes),
        "true_range": true_range(highs, lows, closes),
        "sma20": sma20_series,
        "sma50": sma(closes, 50),
        "sma200": sma200_series,
        "ema12": ema(closes, 12),
        "ema26": ema(closes, 26),
        "macd": macd_line,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "rsi14": rsi(closes),
        "rsi14_simple": rsi_simple(closes),
        "atr14": atr_series,
        "bb_upper20": bb_upper,
        "bb_mid20": bb_mid,
        "bb_lower20": bb_lower,
        "keltner_upper20": kc_upper,
        "keltner_lower20": kc_lower,
        "donchian_high20": dc_high,
        "donchian_mid20": dc_mid,
        "donchian_low20": dc_low,
        "stoch_k14": stoch_k,
        "stoch_d14": stoch_d,
        "adx14": adx_series,
        "di_plus14": di_plus,
        "di_minus14": di_minus,
        "obv": obv(closes, volumes),
        "vwap_cum": vwap_cumulative(highs, lows, closes, volumes),
        "cci20": cci(highs, lows, closes),
        "willr14": williams_r(highs, lows, closes),
        "roc10_bps": roc_bps(closes, 10),
        "mfi14": mfi(highs, lows, closes, volumes),
        "supertrend": st_line,
        "supertrend_dir": st_dir,
        "zscore20": zscore(closes),
        "realized_vol20_bps": realized_vol_bps(closes),
        "return1_bps": roc_bps(closes, 1),
        "return5_bps": roc_bps(closes, 5),
        "return20_bps": roc_bps(closes, 20),
        "volume_sma20": volume_sma,
        "volume_ratio20": [None] * length,
        "atr14_percent": [None] * length,
        "bb_width20": [None] * length,
        "bb_percent_b20": [None] * length,
        "dist_sma20_bps": [None] * length,
        "dist_sma200_bps": [None] * length,
    }

    for index in range(length):
        if volume_sma[index] not in (None, 0):
            panel["volume_ratio20"][index] = volumes[index] / volume_sma[index]
        if atr_series[index] is not None and closes[index] > 0:
            panel["atr14_percent"][index] = atr_series[index] / closes[index] * 100.0
        if bb_mid[index] not in (None, 0) and bb_upper[index] is not None and bb_lower[index] is not None:
            panel["bb_width20"][index] = (bb_upper[index] - bb_lower[index]) / bb_mid[index]
            span = bb_upper[index] - bb_lower[index]
            panel["bb_percent_b20"][index] = (
                0.5 if span == 0 else (closes[index] - bb_lower[index]) / span
            )
        panel["dist_sma20_bps"][index] = _ratio_bps(closes[index], sma20_series[index])
        panel["dist_sma200_bps"][index] = _ratio_bps(closes[index], sma200_series[index])

    missing = set(INDICATORS) - set(panel)
    extra = set(panel) - set(INDICATORS)
    if missing or extra:  # pragma: no cover - guarded by test_market_indicators
        raise AssertionError(f"panel/registry drift: missing={sorted(missing)} extra={sorted(extra)}")
    return panel


def indicator_series(
    normalized: Mapping[str, Any],
    names: Sequence[str] | None = None,
) -> dict[str, Series]:
    """Full-length indicator series for a normalized bar series."""
    panel = compute_all(
        bars_mod.opens(normalized),
        bars_mod.highs(normalized),
        bars_mod.lows(normalized),
        bars_mod.closes(normalized),
        bars_mod.volumes(normalized),
    )
    if names is None:
        return panel
    unknown = [name for name in names if name not in panel]
    if unknown:
        raise KeyError(f"unknown indicators: {unknown}")
    return {name: panel[name] for name in names}


def snapshot(
    normalized: Mapping[str, Any],
    names: Sequence[str] | None = None,
    *,
    index: int | None = None,
    digits: int = 8,
) -> dict[str, float | None]:
    """Indicator values at a single bar (default: the last one). Values are rounded so that digests over the
    snapshot are stable across platforms."""
    panel = indicator_series(normalized, names)
    length = int(normalized["bar_count"])
    position = length - 1 if index is None else index
    if not 0 <= position < length:
        raise IndexError(f"index {position} outside 0..{length - 1}")
    out: dict[str, float | None] = {}
    for name, series in panel.items():
        value = series[position]
        out[name] = None if value is None else round(float(value), digits)
    return out


def warmup_bars(names: Sequence[str] | None = None) -> int:
    """Bars needed before every requested indicator is defined."""
    selected = INDICATORS if names is None else {name: INDICATORS[name] for name in names}
    return max(int(spec["warmup_bars"]) for spec in selected.values())
