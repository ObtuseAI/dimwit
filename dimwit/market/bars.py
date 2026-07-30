"""OHLCV bar normalization with point-in-time guarantees.

Every other module in `dimwit.market` consumes the output of `normalize_series` and nothing else, so the
validation here is the single choke point for "is this input honest data":

* strictly chronological, no duplicate timestamps, all timezone-aware, all <= `as_of` (no future bars);
* prices positive, volume non-negative, `high`/`low` a real envelope around `open`/`close`;
* the declared classification must say what the data *is* — synthetic fixture, imported retrospective public
  data, or point-in-time capture. Retrospective backfill can never claim `point_in_time_claim: True`, because
  a file downloaded today cannot prove what was visible last March.

`resample` drops the trailing partial bucket. A partially formed higher-timeframe bar is the classic lookahead
leak (its close is "the future" relative to every bar inside it), so it is discarded rather than emitted.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from ..core import sha256_obj

NATIVE_SCHEMA = "dimwit.market-ohlcv-series.v1"

ACCEPTED_SCHEMAS = frozenset(
    {
        NATIVE_SCHEMA,
        "dumbmoney.synthetic-ohlcv-series.v1",
        "dumbmoney.point-in-time-ohlcv-series.v1",
    }
)

#: classification -> whether a point-in-time claim is permissible for it
CLASSIFICATIONS: dict[str, bool] = {
    "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE": False,
    "IMPORTED_PUBLIC_MARKET_DATA_RETROSPECTIVE_RESEARCH": False,
    "POINT_IN_TIME_CAPTURED_STRUCTURED_OHLCV": True,
}

ASSET_CLASSES = frozenset({"equity", "crypto", "index", "future"})

#: canonical timeframe token -> minutes
TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "2m": 2,
    "3m": 3,
    "5m": 5,
    "10m": 10,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "1w": 10080,
}

BAR_KEYS = ("observed_at", "open", "high", "low", "close", "volume")


class BarSeriesError(ValueError):
    """Raised when an OHLCV series cannot be trusted without weakening its contract."""


def timeframe_minutes(timeframe: object) -> int:
    token = str(timeframe or "").strip().lower()
    if token not in TIMEFRAME_MINUTES:
        raise BarSeriesError(
            f"unsupported timeframe {timeframe!r}; expected one of {sorted(TIMEFRAME_MINUTES)}"
        )
    return TIMEFRAME_MINUTES[token]


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise BarSeriesError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BarSeriesError(f"{field} is not a valid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BarSeriesError(f"{field} must include a timezone offset")
    return parsed.astimezone(UTC)


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BarSeriesError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BarSeriesError(f"{field} must be a number") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise BarSeriesError(f"{field} must be finite")
    return number


def _normalize_bar(raw: object, index: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise BarSeriesError(f"bar[{index}] must be an object")
    observed_at = _timestamp(raw.get("observed_at"), f"bar[{index}].observed_at")
    open_price = _number(raw.get("open"), f"bar[{index}].open")
    high = _number(raw.get("high"), f"bar[{index}].high")
    low = _number(raw.get("low"), f"bar[{index}].low")
    close = _number(raw.get("close"), f"bar[{index}].close")
    volume = _number(raw.get("volume"), f"bar[{index}].volume")
    if min(open_price, high, low, close) <= 0:
        raise BarSeriesError(f"bar[{index}] prices must be positive")
    if volume < 0:
        raise BarSeriesError(f"bar[{index}] volume must be non-negative")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise BarSeriesError(f"bar[{index}] high/low envelope does not contain open/close")
    return {
        "observed_at": _utc(observed_at),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _spacing_report(bars: Sequence[Mapping[str, Any]], expected_minutes: int) -> dict[str, Any]:
    """Describe timestamp spacing. Gaps are *reported*, never silently repaired or rejected — real markets
    close, halt and skip. A caller that needs contiguity can gate on `uniform`."""
    if len(bars) < 2:
        return {"uniform": True, "expected_minutes": expected_minutes, "gap_count": 0, "max_gap_minutes": 0.0}
    gaps: list[float] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        delta = (
            datetime.fromisoformat(current["observed_at"].replace("Z", "+00:00"))
            - datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00"))
        ).total_seconds() / 60.0
        gaps.append(delta)
    off_grid = [gap for gap in gaps if abs(gap - expected_minutes) > 1e-6]
    return {
        "uniform": not off_grid,
        "expected_minutes": expected_minutes,
        "gap_count": len(off_grid),
        "max_gap_minutes": round(max(gaps), 6),
        "min_gap_minutes": round(min(gaps), 6),
    }


def normalize_series(series: Mapping[str, Any], *, min_bars: int = 26) -> dict[str, Any]:
    """Validate + canonicalize an OHLCV series into the one shape the market cell consumes.

    Raises `BarSeriesError` on anything that would let unverifiable data through. Returns a dict with the
    normalized bars plus `point_in_time_claim`, `spacing` and a content digest.
    """
    if not isinstance(series, Mapping):
        raise BarSeriesError("series must be an object")
    schema = series.get("schema")
    if schema not in ACCEPTED_SCHEMAS:
        raise BarSeriesError(f"unsupported series schema {schema!r}; accepted {sorted(ACCEPTED_SCHEMAS)}")
    classification = series.get("classification")
    if classification not in CLASSIFICATIONS:
        raise BarSeriesError(
            f"series must declare a known classification; got {classification!r}"
        )
    symbol = str(series.get("symbol", "")).strip()
    if not symbol:
        raise BarSeriesError("series symbol is required")
    asset_class = str(series.get("asset_class", "")).strip()
    if asset_class not in ASSET_CLASSES:
        raise BarSeriesError(f"asset_class must be one of {sorted(ASSET_CLASSES)}")
    expected_minutes = timeframe_minutes(series.get("timeframe"))
    as_of = _timestamp(series.get("as_of"), "as_of")

    raw_bars = series.get("bars")
    if not isinstance(raw_bars, list):
        raise BarSeriesError("bars must be a list")
    if len(raw_bars) < min_bars:
        raise BarSeriesError(f"series requires at least {min_bars} bars, got {len(raw_bars)}")

    bars: list[dict[str, Any]] = []
    previous: datetime | None = None
    for index, raw in enumerate(raw_bars):
        bar = _normalize_bar(raw, index)
        observed_at = datetime.fromisoformat(bar["observed_at"].replace("Z", "+00:00"))
        if previous is not None and observed_at <= previous:
            raise BarSeriesError(f"bar[{index}] is not strictly after bar[{index - 1}]")
        if observed_at > as_of:
            raise BarSeriesError(f"bar[{index}] is later than as_of; future bars are forbidden")
        previous = observed_at
        bars.append(bar)

    claim = bool(series.get("point_in_time_claim", False))
    if claim and not CLASSIFICATIONS[classification]:
        raise BarSeriesError(
            f"classification {classification} cannot support point_in_time_claim=True"
        )

    normalized = {
        "schema": NATIVE_SCHEMA,
        "source_schema": schema,
        "classification": classification,
        "symbol": symbol,
        "asset_class": asset_class,
        "timeframe": str(series.get("timeframe")).strip().lower(),
        "timeframe_minutes": expected_minutes,
        "as_of": _utc(as_of),
        "bar_count": len(bars),
        "first_observed_at": bars[0]["observed_at"],
        "last_observed_at": bars[-1]["observed_at"],
        "point_in_time_claim": claim,
        "spacing": _spacing_report(bars, expected_minutes),
        "bars": bars,
    }
    normalized["digest"] = series_digest(normalized)
    return normalized


def series_digest(normalized: Mapping[str, Any]) -> str:
    """Content digest over the identity + every bar. Independent of dict ordering."""
    return sha256_obj(
        {
            "schema": normalized.get("schema"),
            "classification": normalized.get("classification"),
            "symbol": normalized.get("symbol"),
            "asset_class": normalized.get("asset_class"),
            "timeframe": normalized.get("timeframe"),
            "as_of": normalized.get("as_of"),
            "bars": [
                [bar["observed_at"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]]
                for bar in normalized.get("bars", [])
            ],
        }
    )


#: fields only `normalize_series` produces; a payload lacking any of them has not been through the gate
_NORMALIZED_MARKERS = ("bar_count", "timeframe_minutes", "spacing", "digest", "point_in_time_claim")


def is_normalized(series: Mapping[str, Any]) -> bool:
    """True only for a payload that has been through `normalize_series` AND still matches its own digest.

    The schema field is not sufficient evidence: a caller can write `schema: dimwit.market-ohlcv-series.v1` on a
    raw dict, and treating that as normalized would skip the only input gate this package has. Requiring the
    content digest to match means a hand-built "normalized" dict cannot bluff its way past validation.
    """
    if not isinstance(series, Mapping) or series.get("schema") != NATIVE_SCHEMA:
        return False
    if any(marker not in series for marker in _NORMALIZED_MARKERS):
        return False
    try:
        return series_digest(series) == series["digest"]
    except Exception:  # noqa: BLE001 - a malformed payload is simply not normalized
        return False


def ensure_normalized(series: Mapping[str, Any], *, min_bars: int = 26) -> dict[str, Any]:
    """Return `series` if it is genuinely normalized, otherwise normalize it."""
    return dict(series) if is_normalized(series) else normalize_series(series, min_bars=min_bars)


def point_in_time_prefix(normalized: Mapping[str, Any], upto_index: int) -> dict[str, Any]:
    """Return the series as it existed through `upto_index` inclusive.

    This is the mechanical basis of every no-lookahead test: an indicator is prefix-stable iff its value at
    index *i* on the full series equals its value at the last index of `point_in_time_prefix(series, i)`.
    """
    bars = list(normalized.get("bars", []))
    if not isinstance(upto_index, int) or isinstance(upto_index, bool):
        raise BarSeriesError("upto_index must be an int")
    if not 0 <= upto_index < len(bars):
        raise BarSeriesError(f"upto_index {upto_index} outside 0..{len(bars) - 1}")
    prefix = bars[: upto_index + 1]
    sliced = dict(normalized)
    sliced["bars"] = prefix
    sliced["bar_count"] = len(prefix)
    sliced["as_of"] = prefix[-1]["observed_at"]
    sliced["last_observed_at"] = prefix[-1]["observed_at"]
    sliced["spacing"] = _spacing_report(prefix, int(normalized["timeframe_minutes"]))
    sliced["digest"] = series_digest(sliced)
    return sliced


def resample(normalized: Mapping[str, Any], target_timeframe: str) -> dict[str, Any]:
    """Aggregate to a higher timeframe. The trailing partial bucket is DROPPED (it would leak the future).

    Buckets are cut on wall-clock boundaries derived from the Unix epoch, so the same input always produces
    the same buckets regardless of where the series happens to start.
    """
    source_minutes = int(normalized["timeframe_minutes"])
    target_minutes = timeframe_minutes(target_timeframe)
    if target_minutes < source_minutes:
        raise BarSeriesError("resample only aggregates upward; target timeframe is shorter than source")
    if target_minutes % source_minutes != 0:
        raise BarSeriesError(
            f"target timeframe {target_timeframe} is not an integer multiple of {normalized['timeframe']}"
        )
    factor = target_minutes // source_minutes
    if factor == 1:
        return dict(normalized)

    bucket_seconds = target_minutes * 60
    buckets: list[list[dict[str, Any]]] = []
    current_key: int | None = None
    for bar in normalized["bars"]:
        epoch = int(
            datetime.fromisoformat(bar["observed_at"].replace("Z", "+00:00")).timestamp()
        )
        key = epoch - (epoch % bucket_seconds)
        if key != current_key:
            buckets.append([])
            current_key = key
        buckets[-1].append(bar)

    aggregated: list[dict[str, Any]] = []
    for bucket in buckets:
        if len(bucket) != factor:
            continue  # partial bucket: incomplete, therefore forward-looking. Drop it.
        aggregated.append(
            {
                "observed_at": bucket[-1]["observed_at"],
                "open": bucket[0]["open"],
                "high": max(bar["high"] for bar in bucket),
                "low": min(bar["low"] for bar in bucket),
                "close": bucket[-1]["close"],
                "volume": sum(bar["volume"] for bar in bucket),
            }
        )
    if not aggregated:
        raise BarSeriesError(
            f"resample to {target_timeframe} produced no complete buckets from {len(normalized['bars'])} bars"
        )

    out = dict(normalized)
    out["timeframe"] = str(target_timeframe).strip().lower()
    out["timeframe_minutes"] = target_minutes
    out["bars"] = aggregated
    out["bar_count"] = len(aggregated)
    out["first_observed_at"] = aggregated[0]["observed_at"]
    out["last_observed_at"] = aggregated[-1]["observed_at"]
    out["as_of"] = normalized["as_of"]
    out["resampled_from"] = normalized["timeframe"]
    out["partial_buckets_dropped"] = len(buckets) - len(aggregated)
    out["spacing"] = _spacing_report(aggregated, target_minutes)
    out["digest"] = series_digest(out)
    return out


def closes(normalized: Mapping[str, Any]) -> list[float]:
    return [float(bar["close"]) for bar in normalized["bars"]]


def highs(normalized: Mapping[str, Any]) -> list[float]:
    return [float(bar["high"]) for bar in normalized["bars"]]


def lows(normalized: Mapping[str, Any]) -> list[float]:
    return [float(bar["low"]) for bar in normalized["bars"]]


def opens(normalized: Mapping[str, Any]) -> list[float]:
    return [float(bar["open"]) for bar in normalized["bars"]]


def volumes(normalized: Mapping[str, Any]) -> list[float]:
    return [float(bar["volume"]) for bar in normalized["bars"]]
