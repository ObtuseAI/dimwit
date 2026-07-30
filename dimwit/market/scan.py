"""Walk-forward rule scanner — Dimwit's settled-observation factory.

The scarce resource in this whole system is not signals, it is **settled independent observations**. Anyone can
generate another rule; almost nothing generates trustworthy outcomes to judge rules against. So this module is
built to manufacture settled observations honestly and to refuse to overstate how many it has:

* **Walk-forward, embargoed.** `warmup -> training -> embargo -> holdout`. Rules are ranked on training only;
  the holdout is scored for every rule and never consulted for selection (`holdout_used_for_selection: False`).
  The embargo must be at least `horizon_bars` long, so no training outcome can settle inside the holdout.
* **Explicit execution model.** Signal at bar *i* (from `detected_at_index`, never from an unconfirmed pivot)
  -> entry at bar *i+1* open -> exit at bar *i+1+horizon* close, minus a round-trip cost. No fills at the
  signal bar's close, which is the most common way a backtest quietly front-runs itself.
* **Tested against a baseline, not against zero.** Every segment's unconditional outcome — take the same side at
  *every* bar — is computed, and each rule is scored on its **excess** over that baseline. Without this, a long
  rule evaluated over a rising segment looks profitable because the segment rose, and no amount of statistical
  correction notices. Survivor accounting uses the excess t-statistic.
* **Search disclosure.** `family_size` is the number of rules actually evaluated, and survivors are reported
  under both Bonferroni and Benjamini-Hochberg. A t-statistic that does not survive its own search space is a
  coincidence with a name.
* **Overlap deflation.** Fixed-horizon windows overlap, so `n` outcomes are worth roughly `n / horizon`
  independent draws. Every t-statistic is reported twice: raw, and deflated by `sqrt(horizon)`. Survivor
  accounting uses the deflated one, because the raw number is the flattering one.
* **A placebo that must come back empty.** `placebo_control` re-runs the whole scan with every entry displaced
  by a fixed number of bars: the same count of same-sided positions, opened at bars the condition says nothing
  about. If rules "survive" that, the accounting manufactures edge, and a test asserts it does not.

Nothing here promotes anything or emits a probability. The output is evidence for doofus to judge.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from ..core import sha256_obj
from . import indicators as ind
from . import patterns as pat

ENTRY_MODEL = "NEXT_BAR_OPEN"
OUTCOME_MODEL = "FIXED_HORIZON_CLOSE"
P_VALUE_METHOD = "TWO_SIDED_NORMAL_APPROXIMATION_OF_T"


class ScanError(ValueError):
    """Raised when a scan cannot be run without weakening its own accounting."""


@dataclass(frozen=True)
class ScanConfig:
    """Segment sizes in bars. Defaults are deliberately demanding: a scan that cannot afford them should say so
    rather than shrink its holdout."""

    warmup_bars: int = 200
    training_bars: int = 300
    embargo_bars: int = 10
    holdout_bars: int = 400
    horizon_bars: int = 5
    round_trip_cost_bps: float = 10.0
    alpha: float = 0.05

    def validate(self) -> None:
        if self.warmup_bars < 26:
            raise ScanError("warmup_bars must be at least 26 (the deepest short-window indicator)")
        if self.training_bars <= 0 or self.holdout_bars <= 0:
            raise ScanError("training_bars and holdout_bars must be positive")
        if self.horizon_bars <= 0:
            raise ScanError("horizon_bars must be positive")
        if self.embargo_bars < self.horizon_bars:
            raise ScanError("embargo_bars must cover the full outcome horizon")
        if self.holdout_bars <= self.horizon_bars:
            raise ScanError("holdout_bars must exceed the outcome horizon")
        if not 0.0 < self.alpha < 0.5:
            raise ScanError("alpha must be in (0, 0.5)")
        if not math.isfinite(self.round_trip_cost_bps) or self.round_trip_cost_bps <= 0:
            raise ScanError("round_trip_cost_bps must be finite and positive")

    @property
    def required_bars(self) -> int:
        return self.warmup_bars + self.training_bars + self.embargo_bars + self.holdout_bars

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "warmup_bars": self.warmup_bars,
            "training_bars": self.training_bars,
            "embargo_bars": self.embargo_bars,
            "holdout_bars": self.holdout_bars,
            "horizon_bars": self.horizon_bars,
            "round_trip_cost_bps": round(self.round_trip_cost_bps, 8),
            "alpha": self.alpha,
            "entry_model": ENTRY_MODEL,
            "outcome_model": OUTCOME_MODEL,
        }


# ---------------------------------------------------------------------------
# rule family
# ---------------------------------------------------------------------------

Features = Mapping[str, Any]
RuleFn = Callable[[Features], int]


def _defined(features: Features, *names: str) -> bool:
    return all(features.get(name) is not None for name in names)


def _trend_up(features: Features) -> int:
    if not _defined(features, "last_close", "sma50", "sma200"):
        return 0
    return 1 if features["last_close"] > features["sma50"] > features["sma200"] else 0


def _trend_down(features: Features) -> int:
    if not _defined(features, "last_close", "sma50", "sma200"):
        return 0
    return -1 if features["last_close"] < features["sma50"] < features["sma200"] else 0


def _macd_cross_up(features: Features) -> int:
    if not _defined(features, "macd_hist", "prev_macd_hist"):
        return 0
    return 1 if features["prev_macd_hist"] <= 0 < features["macd_hist"] else 0


def _macd_cross_down(features: Features) -> int:
    if not _defined(features, "macd_hist", "prev_macd_hist"):
        return 0
    return -1 if features["prev_macd_hist"] >= 0 > features["macd_hist"] else 0


def _rsi_oversold(features: Features) -> int:
    if not _defined(features, "rsi14"):
        return 0
    return 1 if features["rsi14"] < 30 else 0


def _rsi_overbought(features: Features) -> int:
    if not _defined(features, "rsi14"):
        return 0
    return -1 if features["rsi14"] > 70 else 0


def _rsi_exit_oversold(features: Features) -> int:
    if not _defined(features, "rsi14", "prev_rsi14"):
        return 0
    return 1 if features["prev_rsi14"] < 30 <= features["rsi14"] else 0


def _bollinger_lower_tag(features: Features) -> int:
    if not _defined(features, "bb_percent_b20"):
        return 0
    return 1 if features["bb_percent_b20"] <= 0.0 else 0


def _bollinger_upper_tag(features: Features) -> int:
    if not _defined(features, "bb_percent_b20"):
        return 0
    return -1 if features["bb_percent_b20"] >= 1.0 else 0


def _zscore_stretch_long(features: Features) -> int:
    if not _defined(features, "zscore20"):
        return 0
    return 1 if features["zscore20"] <= -2.0 else 0


def _zscore_stretch_short(features: Features) -> int:
    if not _defined(features, "zscore20"):
        return 0
    return -1 if features["zscore20"] >= 2.0 else 0


def _adx_trend_long(features: Features) -> int:
    if not _defined(features, "adx14", "di_plus14", "di_minus14"):
        return 0
    return 1 if features["adx14"] > 25 and features["di_plus14"] > features["di_minus14"] else 0


def _adx_trend_short(features: Features) -> int:
    if not _defined(features, "adx14", "di_plus14", "di_minus14"):
        return 0
    return -1 if features["adx14"] > 25 and features["di_minus14"] > features["di_plus14"] else 0


def _supertrend_flip_up(features: Features) -> int:
    if not _defined(features, "supertrend_dir", "prev_supertrend_dir"):
        return 0
    return 1 if features["prev_supertrend_dir"] < 0 < features["supertrend_dir"] else 0


def _supertrend_flip_down(features: Features) -> int:
    if not _defined(features, "supertrend_dir", "prev_supertrend_dir"):
        return 0
    return -1 if features["prev_supertrend_dir"] > 0 > features["supertrend_dir"] else 0


def _volume_thrust_long(features: Features) -> int:
    if not _defined(features, "volume_ratio20", "return1_bps"):
        return 0
    return 1 if features["volume_ratio20"] >= 2.0 and features["return1_bps"] > 0 else 0


def _volume_thrust_short(features: Features) -> int:
    if not _defined(features, "volume_ratio20", "return1_bps"):
        return 0
    return -1 if features["volume_ratio20"] >= 2.0 and features["return1_bps"] < 0 else 0


def _mfi_oversold(features: Features) -> int:
    if not _defined(features, "mfi14"):
        return 0
    return 1 if features["mfi14"] < 20 else 0


def _mfi_overbought(features: Features) -> int:
    if not _defined(features, "mfi14"):
        return 0
    return -1 if features["mfi14"] > 80 else 0


def _stochastic_cross_up(features: Features) -> int:
    if not _defined(features, "stoch_k14", "stoch_d14", "prev_stoch_k14", "prev_stoch_d14"):
        return 0
    crossed = features["prev_stoch_k14"] <= features["prev_stoch_d14"] and (
        features["stoch_k14"] > features["stoch_d14"]
    )
    return 1 if crossed and features["stoch_k14"] < 40 else 0


def _stochastic_cross_down(features: Features) -> int:
    if not _defined(features, "stoch_k14", "stoch_d14", "prev_stoch_k14", "prev_stoch_d14"):
        return 0
    crossed = features["prev_stoch_k14"] >= features["prev_stoch_d14"] and (
        features["stoch_k14"] < features["stoch_d14"]
    )
    return -1 if crossed and features["stoch_k14"] > 60 else 0


def _squeeze_expansion(features: Features) -> int:
    if not features.get("squeeze_release") or not _defined(features, "return1_bps"):
        return 0
    return 1 if features["return1_bps"] > 0 else -1


def _vol_contraction_long(features: Features) -> int:
    if not _defined(features, "atr14_percent", "prev_atr14_percent", "dist_sma20_bps"):
        return 0
    contracting = features["atr14_percent"] < features["prev_atr14_percent"]
    return 1 if contracting and features["dist_sma20_bps"] > 0 else 0


def _pattern_rule(name: str, direction: int) -> RuleFn:
    def rule(features: Features) -> int:
        return direction if features.get(name) else 0

    rule.__name__ = f"_pattern_{name}"
    return rule


#: rule name -> {family, description, fn}. `len(RULES)` IS the disclosed search-space size.
RULES: dict[str, dict[str, Any]] = {
    "trend_stack_long": {"family": "trend", "fn": _trend_up, "description": "Close > SMA50 > SMA200."},
    "trend_stack_short": {"family": "trend", "fn": _trend_down, "description": "Close < SMA50 < SMA200."},
    "macd_cross_up": {"family": "momentum", "fn": _macd_cross_up, "description": "MACD histogram crosses up through zero."},
    "macd_cross_down": {"family": "momentum", "fn": _macd_cross_down, "description": "MACD histogram crosses down through zero."},
    "rsi_oversold": {"family": "meanrev", "fn": _rsi_oversold, "description": "Wilder RSI14 below 30."},
    "rsi_overbought": {"family": "meanrev", "fn": _rsi_overbought, "description": "Wilder RSI14 above 70."},
    "rsi_exit_oversold": {"family": "meanrev", "fn": _rsi_exit_oversold, "description": "RSI14 crosses back up through 30."},
    "bollinger_lower_tag": {"family": "meanrev", "fn": _bollinger_lower_tag, "description": "Close at/below the lower Bollinger band."},
    "bollinger_upper_tag": {"family": "meanrev", "fn": _bollinger_upper_tag, "description": "Close at/above the upper Bollinger band."},
    "zscore_stretch_long": {"family": "meanrev", "fn": _zscore_stretch_long, "description": "Close z-score <= -2 over 20 bars."},
    "zscore_stretch_short": {"family": "meanrev", "fn": _zscore_stretch_short, "description": "Close z-score >= +2 over 20 bars."},
    "adx_trend_long": {"family": "trend", "fn": _adx_trend_long, "description": "ADX > 25 with +DI above -DI."},
    "adx_trend_short": {"family": "trend", "fn": _adx_trend_short, "description": "ADX > 25 with -DI above +DI."},
    "supertrend_flip_up": {"family": "trend", "fn": _supertrend_flip_up, "description": "Supertrend direction flips to +1."},
    "supertrend_flip_down": {"family": "trend", "fn": _supertrend_flip_down, "description": "Supertrend direction flips to -1."},
    "volume_thrust_long": {"family": "volume", "fn": _volume_thrust_long, "description": "Volume >= 2x average on an up bar."},
    "volume_thrust_short": {"family": "volume", "fn": _volume_thrust_short, "description": "Volume >= 2x average on a down bar."},
    "mfi_oversold": {"family": "volume", "fn": _mfi_oversold, "description": "Money flow index below 20."},
    "mfi_overbought": {"family": "volume", "fn": _mfi_overbought, "description": "Money flow index above 80."},
    "stochastic_cross_up": {"family": "momentum", "fn": _stochastic_cross_up, "description": "%K crosses above %D below 40."},
    "stochastic_cross_down": {"family": "momentum", "fn": _stochastic_cross_down, "description": "%K crosses below %D above 60."},
    "squeeze_expansion": {"family": "volatility", "fn": _squeeze_expansion, "description": "Bollinger squeeze releases; direction from the bar."},
    "vol_contraction_long": {"family": "volatility", "fn": _vol_contraction_long, "description": "ATR% contracting while price holds above SMA20."},
    "pattern_bullish_engulfing": {"family": "pattern", "fn": _pattern_rule("bullish_engulfing", 1), "description": "Bullish engulfing bar."},
    "pattern_bearish_engulfing": {"family": "pattern", "fn": _pattern_rule("bearish_engulfing", -1), "description": "Bearish engulfing bar."},
    "pattern_hammer": {"family": "pattern", "fn": _pattern_rule("hammer", 1), "description": "Hammer bar."},
    "pattern_shooting_star": {"family": "pattern", "fn": _pattern_rule("shooting_star", -1), "description": "Shooting star bar."},
    "pattern_morning_star": {"family": "pattern", "fn": _pattern_rule("morning_star", 1), "description": "Morning star triple."},
    "pattern_evening_star": {"family": "pattern", "fn": _pattern_rule("evening_star", -1), "description": "Evening star triple."},
    "structure_break_up": {"family": "structure", "fn": _pattern_rule("break_of_structure_up", 1), "description": "Close above the last confirmed swing high."},
    "structure_break_down": {"family": "structure", "fn": _pattern_rule("break_of_structure_down", -1), "description": "Close below the last confirmed swing low."},
    "donchian_breakout_up": {"family": "structure", "fn": _pattern_rule("donchian_breakout_up", 1), "description": "Close above the prior 20-bar high."},
    "donchian_breakout_down": {"family": "structure", "fn": _pattern_rule("donchian_breakout_down", -1), "description": "Close below the prior 20-bar low."},
    "divergence_bullish": {"family": "divergence", "fn": _pattern_rule("rsi_bullish_divergence", 1), "description": "Confirmed bullish RSI divergence."},
    "divergence_bearish": {"family": "divergence", "fn": _pattern_rule("rsi_bearish_divergence", -1), "description": "Confirmed bearish RSI divergence."},
}

RULE_FAMILIES = tuple(sorted({spec["family"] for spec in RULES.values()}))

_LAGGED_FEATURES = (
    "macd_hist",
    "rsi14",
    "supertrend_dir",
    "stoch_k14",
    "stoch_d14",
    "atr14_percent",
)


def build_features(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Per-bar causal feature rows: indicator values at *i*, one-bar lags, and pattern flags keyed on the bar
    the pattern became knowable."""
    panel = ind.indicator_series(normalized)
    flags = pat.pattern_flags(normalized)
    length = int(normalized["bar_count"])
    rows: list[dict[str, Any]] = []
    for index in range(length):
        row: dict[str, Any] = {name: series[index] for name, series in panel.items()}
        for name in _LAGGED_FEATURES:
            row[f"prev_{name}"] = panel[name][index - 1] if index >= 1 else None
        row.update(flags[index])
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def _normal_sf(value: float) -> float:
    """Upper-tail probability of the standard normal."""
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def _two_sided_p(t_stat: float | None) -> float | None:
    if t_stat is None or not math.isfinite(t_stat):
        return None
    return min(1.0, 2.0 * _normal_sf(abs(t_stat)))


def _max_drawdown_bps(returns: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return abs(worst)


def _metrics(
    outcomes: Sequence[Mapping[str, Any]],
    horizon_bars: int,
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Metrics for one rule on one segment.

    Two means are reported and they answer different questions. `mean_net_bps` asks "did this rule make money",
    which a long rule can answer yes to purely by being long during a rally. `mean_excess_bps` asks "did this
    rule beat taking the same side at every bar of the same segment" — the unconditional baseline — which is the
    question a signal has to answer to be worth anything. Survivor accounting uses the excess.
    """
    count = len(outcomes)
    empty = {
        "n": 0,
        "independent_n_estimate": 0.0,
        "hit_rate": None,
        "mean_net_bps": None,
        "stdev_net_bps": None,
        "t_stat": None,
        "t_stat_overlap_adjusted": None,
        "baseline_mean_net_bps": None,
        "mean_excess_bps": None,
        "t_stat_excess": None,
        "t_stat_excess_overlap_adjusted": None,
        "p_value_excess_overlap_adjusted": None,
        "total_net_bps": 0.0,
        "max_drawdown_bps": 0.0,
        "direction_mix": {},
    }
    if count == 0:
        return empty

    nets = [float(item["net_return_bps"]) for item in outcomes]
    mean = sum(nets) / count
    if count > 1:
        variance = sum((value - mean) ** 2 for value in nets) / (count - 1)
        deviation = math.sqrt(variance)
    else:
        deviation = 0.0
    t_stat = None if deviation == 0 else mean / (deviation / math.sqrt(count))

    baseline_per_outcome: list[float] = []
    if baseline is not None:
        for item in outcomes:
            key = "long_mean_net_bps" if int(item["direction"]) > 0 else "short_mean_net_bps"
            value = baseline.get(key)
            baseline_per_outcome.append(0.0 if value is None else float(value))
    excess = (
        [net - reference for net, reference in zip(nets, baseline_per_outcome, strict=True)]
        if baseline_per_outcome
        else None
    )
    excess_mean = None if excess is None else sum(excess) / count
    if excess is not None and count > 1:
        excess_variance = sum((value - excess_mean) ** 2 for value in excess) / (count - 1)
        excess_deviation = math.sqrt(excess_variance)
    else:
        excess_deviation = 0.0
    t_excess = (
        None
        if excess_mean is None or excess_deviation == 0
        else excess_mean / (excess_deviation / math.sqrt(count))
    )
    directions: dict[str, int] = {}
    for item in outcomes:
        key = "long" if int(item["direction"]) > 0 else "short"
        directions[key] = directions.get(key, 0) + 1

    def deflate(value: float | None) -> float | None:
        return None if value is None else value / math.sqrt(horizon_bars)

    adjusted = deflate(t_stat)
    adjusted_excess = deflate(t_excess)
    return {
        "n": count,
        # overlapping fixed-horizon windows share bars; n/horizon is the conservative independent count
        "independent_n_estimate": round(count / horizon_bars, 4),
        "hit_rate": round(sum(1 for value in nets if value > 0) / count, 6),
        "mean_net_bps": round(mean, 6),
        "stdev_net_bps": round(deviation, 6),
        "t_stat": None if t_stat is None else round(t_stat, 6),
        "t_stat_overlap_adjusted": None if adjusted is None else round(adjusted, 6),
        "baseline_mean_net_bps": (
            None
            if not baseline_per_outcome
            else round(sum(baseline_per_outcome) / count, 6)
        ),
        "mean_excess_bps": None if excess_mean is None else round(excess_mean, 6),
        "t_stat_excess": None if t_excess is None else round(t_excess, 6),
        "t_stat_excess_overlap_adjusted": (
            None if adjusted_excess is None else round(adjusted_excess, 6)
        ),
        "p_value_excess_overlap_adjusted": (
            None if adjusted_excess is None else round(_two_sided_p(adjusted_excess), 8)
        ),
        "total_net_bps": round(sum(nets), 6),
        "max_drawdown_bps": round(_max_drawdown_bps(nets), 6),
        "direction_mix": dict(sorted(directions.items())),
    }


def _benjamini_hochberg(p_values: Mapping[str, float | None], alpha: float) -> dict[str, Any]:
    usable = sorted(
        ((name, value) for name, value in p_values.items() if value is not None),
        key=lambda item: item[1],
    )
    total = len(usable)
    survivors: list[str] = []
    threshold = 0.0
    for rank, (name, value) in enumerate(usable, start=1):
        if value <= alpha * rank / total:
            survivors = [item[0] for item in usable[:rank]]
            threshold = alpha * rank / total
    return {
        "method": "BENJAMINI_HOCHBERG",
        "alpha": alpha,
        "tested": total,
        "critical_value": round(threshold, 10),
        "survivors": sorted(survivors),
        "survivor_count": len(survivors),
    }


def _bonferroni(p_values: Mapping[str, float | None], alpha: float, family_size: int) -> dict[str, Any]:
    threshold = alpha / max(1, family_size)
    survivors = sorted(
        name for name, value in p_values.items() if value is not None and value <= threshold
    )
    return {
        "method": "BONFERRONI",
        "alpha": alpha,
        "family_size": family_size,
        "critical_value": round(threshold, 10),
        "survivors": survivors,
        "survivor_count": len(survivors),
    }


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def _segments(config: ScanConfig, length: int) -> dict[str, dict[str, int]]:
    training_start = config.warmup_bars
    training_end = training_start + config.training_bars - 1
    embargo_end = training_end + config.embargo_bars
    holdout_start = embargo_end + 1
    holdout_end = length - 1
    return {
        "training": {"start": training_start, "end": training_end},
        "embargo": {"start": training_end + 1, "end": embargo_end},
        "holdout": {"start": holdout_start, "end": holdout_end},
    }


def _baseline(
    normalized: Mapping[str, Any],
    segment: Mapping[str, int],
    config: ScanConfig,
) -> dict[str, Any]:
    """Unconditional outcome of taking each side at EVERY bar of the segment.

    This is the thing a signal has to beat. Without it, a long rule evaluated over a rising segment looks
    profitable purely because the segment rose, and a circular-shift null control cannot tell the difference —
    which is exactly how a scan manufactures edge from drift.
    """
    series_bars = normalized["bars"]
    last_signal = segment["end"] - config.horizon_bars - 1
    longs: list[float] = []
    shorts: list[float] = []
    for index in range(segment["start"], last_signal + 1):
        entry_index = index + 1
        exit_index = entry_index + config.horizon_bars
        if exit_index > segment["end"]:
            continue
        entry_price = float(series_bars[entry_index]["open"])
        if entry_price <= 0:
            continue
        gross = (float(series_bars[exit_index]["close"]) / entry_price - 1.0) * 10_000.0
        longs.append(gross - config.round_trip_cost_bps)
        shorts.append(-gross - config.round_trip_cost_bps)
    return {
        "model": "TAKE_THE_SAME_SIDE_AT_EVERY_BAR_OF_THE_SEGMENT",
        "n": len(longs),
        "long_mean_net_bps": round(sum(longs) / len(longs), 6) if longs else None,
        "short_mean_net_bps": round(sum(shorts) / len(shorts), 6) if shorts else None,
    }


def _outcomes(
    normalized: Mapping[str, Any],
    features: Sequence[Mapping[str, Any]],
    rule: RuleFn,
    segment: Mapping[str, int],
    config: ScanConfig,
    *,
    placebo_lag_bars: int = 0,
) -> list[dict[str, Any]]:
    """Outcomes for one rule on one segment.

    `placebo_lag_bars` displaces every entry by a fixed number of bars while keeping the rule's direction and
    signal count. That is the placebo: the same number of same-sided positions taken at bars the condition says
    nothing about. Zero means a real evaluation.
    """
    series_bars = normalized["bars"]
    last_signal = segment["end"] - config.horizon_bars - 1
    candidates: list[tuple[int, int]] = []
    for index in range(segment["start"], last_signal + 1):
        direction = rule(features[index])
        if direction:
            candidates.append((index, direction))
    if not candidates:
        return []

    outcomes: list[dict[str, Any]] = []
    for index, direction in candidates:
        anchor = index + placebo_lag_bars
        if not segment["start"] <= anchor <= last_signal:
            continue
        entry_index = anchor + 1
        exit_index = entry_index + config.horizon_bars
        if exit_index > segment["end"]:
            continue
        entry_price = float(series_bars[entry_index]["open"])
        exit_price = float(series_bars[exit_index]["close"])
        if entry_price <= 0:
            continue
        gross = direction * (exit_price / entry_price - 1.0) * 10_000.0
        net = gross - config.round_trip_cost_bps
        outcomes.append(
            {
                "signal_index": index,
                "signal_available_at": series_bars[index]["observed_at"],
                "direction": direction,
                "entry_index": entry_index,
                "entry_at": series_bars[entry_index]["observed_at"],
                "entry_price": round(entry_price, 8),
                "outcome_index": exit_index,
                "outcome_at": series_bars[exit_index]["observed_at"],
                "outcome_price": round(exit_price, 8),
                "gross_return_bps": round(gross, 6),
                "round_trip_cost_bps": round(config.round_trip_cost_bps, 6),
                "net_return_bps": round(net, 6),
                "positive_after_cost": net > 0,
            }
        )
    return outcomes


def scan_rules(
    normalized: Mapping[str, Any],
    *,
    config: ScanConfig | None = None,
    rules: Sequence[str] | None = None,
    placebo_lag_bars: int = 0,
) -> dict[str, Any]:
    """Score every rule on training and holdout segments with full search disclosure.

    Returns a `dimwit.market-walkforward-scan.v1` observation. `placebo_lag_bars` is for the placebo control
    only; leave it at 0 for real scans (a non-zero value is stamped into the result as `placebo_control: True`).
    """
    config = config or ScanConfig()
    config.validate()
    selected = list(RULES) if rules is None else list(rules)
    unknown = [name for name in selected if name not in RULES]
    if unknown:
        raise ScanError(f"unknown rules: {unknown}")
    if not selected:
        raise ScanError("at least one rule is required")

    length = int(normalized["bar_count"])
    if length < config.required_bars:
        raise ScanError(
            f"scan needs {config.required_bars} bars "
            f"(warmup {config.warmup_bars} + training {config.training_bars} + embargo "
            f"{config.embargo_bars} + holdout {config.holdout_bars}); series has {length}"
        )
    segments = _segments(config, length)
    features = build_features(normalized)
    baselines = {
        "training": _baseline(normalized, segments["training"], config),
        "holdout": _baseline(normalized, segments["holdout"], config),
    }

    per_rule: dict[str, dict[str, Any]] = {}
    holdout_p: dict[str, float | None] = {}
    settled_holdout = 0
    for name in selected:
        rule = RULES[name]["fn"]
        training = _outcomes(normalized, features, rule, segments["training"], config)
        holdout = _outcomes(
            normalized,
            features,
            rule,
            segments["holdout"],
            config,
            placebo_lag_bars=placebo_lag_bars,
        )
        settled_holdout += len(holdout)
        training_metrics = _metrics(training, config.horizon_bars, baselines["training"])
        holdout_metrics = _metrics(holdout, config.horizon_bars, baselines["holdout"])
        holdout_p[name] = holdout_metrics["p_value_excess_overlap_adjusted"]
        per_rule[name] = {
            "rule": name,
            "family": RULES[name]["family"],
            "description": RULES[name]["description"],
            "training_metrics": training_metrics,
            "held_out_metrics": holdout_metrics,
            "holdout_outcome_digest": sha256_obj(
                [
                    [item["signal_index"], item["direction"], item["net_return_bps"]]
                    for item in holdout
                ]
            ),
        }

    ranked_on_training = sorted(
        per_rule.values(),
        key=lambda item: (
            -(item["training_metrics"]["t_stat_excess_overlap_adjusted"] or float("-inf")),
            item["rule"],
        ),
    )
    bonferroni = _bonferroni(holdout_p, config.alpha, len(selected))
    bh = _benjamini_hochberg(holdout_p, config.alpha)

    observation = {
        "schema": "dimwit.market-walkforward-scan.v1",
        "producer": "dimwit",
        "symbol": normalized["symbol"],
        "asset_class": normalized["asset_class"],
        "timeframe": normalized["timeframe"],
        "as_of": normalized["as_of"],
        "classification": normalized["classification"],
        "point_in_time_claim": bool(normalized.get("point_in_time_claim", False)),
        "series_digest": normalized["digest"],
        "configuration": config.to_dict(),
        "split": {
            "training": segments["training"],
            "embargo": segments["embargo"],
            "holdout": segments["holdout"],
            "disjoint": True,
            "embargo_covers_horizon": config.embargo_bars >= config.horizon_bars,
            "holdout_used_for_selection": False,
            "selection_basis": "TRAINING_SEGMENT_ONLY",
        },
        "baselines": baselines,
        "search_disclosure": {
            "family_size": len(selected),
            "rules_evaluated": sorted(selected),
            "rule_families": sorted({RULES[name]["family"] for name in selected}),
            "p_value_method": P_VALUE_METHOD,
            "tested_quantity": "EXCESS_OVER_UNCONDITIONAL_SAME_SIDE_BASELINE",
            "overlap_deflation": "T_DIVIDED_BY_SQRT_HORIZON_BARS",
            "bonferroni": bonferroni,
            "benjamini_hochberg": bh,
        },
        "observation_accounting": {
            "settled_holdout_outcomes": settled_holdout,
            "independent_holdout_estimate": round(settled_holdout / config.horizon_bars, 4),
            "note": (
                "Overlapping fixed-horizon windows are not independent draws; the estimate divides by the "
                "horizon. Treat it as an upper bound on usable evidence, not a count of trades."
            ),
        },
        "training_ranking": [
            {
                "rule": item["rule"],
                "t_stat_overlap_adjusted": item["training_metrics"]["t_stat_overlap_adjusted"],
                "n": item["training_metrics"]["n"],
            }
            for item in ranked_on_training
        ],
        "rules": per_rule,
        "placebo_control": bool(placebo_lag_bars),
        "placebo_lag_bars": placebo_lag_bars,
        "transaction_costs_included": True,
        "promotions_applied": 0,
        "orders_created": 0,
        "broker_calls": 0,
        "live_activation": False,
        "execution_authority": False,
        "forecast_probability": None,
        "expected_return_bps": None,
        "candidate_status": (
            "HELD_OUT_SURVIVORS_PRESENT" if bh["survivor_count"] else "NO_HELD_OUT_SURVIVOR"
        ),
        "recommendation_only": True,
    }
    observation["digest"] = sha256_obj(
        {key: value for key, value in observation.items() if key != "digest"}
    )
    return observation


def placebo_control(
    normalized: Mapping[str, Any],
    *,
    config: ScanConfig | None = None,
    rules: Sequence[str] | None = None,
    lags: Sequence[int] = (37, 89, 181, 349),
) -> dict[str, Any]:
    """Re-run the scan with every entry displaced by a fixed number of bars, and report survivors.

    Each rule keeps its direction and (very nearly) its signal count, but the positions are opened at bars the
    condition says nothing about. So the placebo asks the right question — "would the same number of same-sided
    positions, taken at arbitrary bars, have looked this good?" — and a healthy scan answers no.

    This replaced an earlier control that rotated the signal-to-outcome pairing within each rule's own signal
    list. That version was too weak in exactly the case that matters: when a rule's signals are homogeneous (all
    fired at similar states), permuting among them changes almost nothing, so a genuinely-detected regularity
    still "survived" its own null. Displacing in *time* leaves the rule's signal set behind entirely.

    One residual blind spot, stated rather than hidden: a lag that happens to be a multiple of a strong cycle in
    the data lands back on the same phase. Several coprime-ish lags are used and the worst case across them is
    reported, but on strongly periodic data this control should be read as inapplicable rather than as a pass.
    """
    config = config or ScanConfig()
    real = scan_rules(normalized, config=config, rules=rules)
    real_survivors = real["search_disclosure"]["benjamini_hochberg"]["survivors"]
    runs: list[dict[str, Any]] = []
    for lag in lags:
        if lag <= 0:
            raise ScanError("lags must be positive")
        scan = scan_rules(normalized, config=config, rules=rules, placebo_lag_bars=lag)
        runs.append(
            {
                "lag_bars": lag,
                "bh_survivors": scan["search_disclosure"]["benjamini_hochberg"]["survivors"],
                "bh_survivor_count": scan["search_disclosure"]["benjamini_hochberg"]["survivor_count"],
                "bonferroni_survivor_count": scan["search_disclosure"]["bonferroni"]["survivor_count"],
                "settled_holdout_outcomes": scan["observation_accounting"]["settled_holdout_outcomes"],
            }
        )
    placebo_max = max(run["bh_survivor_count"] for run in runs)
    return {
        "schema": "dimwit.market-placebo-control.v1",
        "producer": "dimwit",
        "symbol": normalized["symbol"],
        "series_digest": normalized["digest"],
        "configuration": config.to_dict(),
        "lags": list(lags),
        "null_model": "FIXED_BAR_LAG_DISPLACEMENT_OF_EVERY_ENTRY",
        "tested_quantity": "EXCESS_OVER_UNCONDITIONAL_SAME_SIDE_BASELINE",
        "runs": runs,
        "real_bh_survivors": real_survivors,
        "real_bh_survivor_count": len(real_survivors),
        "max_bh_survivors": placebo_max,
        "max_bonferroni_survivors": max(run["bonferroni_survivor_count"] for run in runs),
        # A placebo run is itself a draw from the null, so it will occasionally reject something. The number that
        # matters is the COMPARISON: a real result no better than its own placebo is not a result.
        "verdict": (
            "REAL_EXCEEDS_PLACEBO"
            if len(real_survivors) > placebo_max
            else "NOT_DISTINGUISHABLE_FROM_PLACEBO"
        ),
        "interpretation": (
            "Compare real survivors against the worst placebo run. Expect a small non-zero placebo count: "
            "Benjamini-Hochberg at this alpha rejects sometimes even under a true null. A real count at or "
            "below the placebo maximum means the scan found nothing it can distinguish from noise."
        ),
        "forecast_probability": None,
        "candidate_status": "DIAGNOSTIC_ONLY",
    }


def scan_summary(scan: Mapping[str, Any], top_k: int = 5) -> dict[str, Any]:
    """Compact operator view of a scan: what survived, what the search cost, how much evidence backs it."""
    disclosure = scan["search_disclosure"]
    survivors = disclosure["benjamini_hochberg"]["survivors"]
    rules = scan["rules"]
    ranked = sorted(
        rules.values(),
        key=lambda item: -(item["held_out_metrics"]["t_stat_excess_overlap_adjusted"] or float("-inf")),
    )
    return {
        "symbol": scan["symbol"],
        "timeframe": scan["timeframe"],
        "family_size": disclosure["family_size"],
        "tested_quantity": disclosure["tested_quantity"],
        "holdout_baseline": scan["baselines"]["holdout"],
        "bh_survivors": survivors,
        "bonferroni_survivors": disclosure["bonferroni"]["survivors"],
        "settled_holdout_outcomes": scan["observation_accounting"]["settled_holdout_outcomes"],
        "independent_holdout_estimate": scan["observation_accounting"]["independent_holdout_estimate"],
        "top_by_holdout_excess_t": [
            {
                "rule": item["rule"],
                "family": item["family"],
                "n": item["held_out_metrics"]["n"],
                "mean_net_bps": item["held_out_metrics"]["mean_net_bps"],
                "baseline_mean_net_bps": item["held_out_metrics"]["baseline_mean_net_bps"],
                "mean_excess_bps": item["held_out_metrics"]["mean_excess_bps"],
                "t_stat_excess_overlap_adjusted": item["held_out_metrics"][
                    "t_stat_excess_overlap_adjusted"
                ],
                "p_value_excess_overlap_adjusted": item["held_out_metrics"][
                    "p_value_excess_overlap_adjusted"
                ],
                "survived_bh": item["rule"] in survivors,
            }
            for item in ranked[:top_k]
        ],
        "candidate_status": scan["candidate_status"],
        "forecast_probability": None,
    }
