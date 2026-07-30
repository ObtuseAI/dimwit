"""Chart vision — reading price structure back out of pixels.

DumbMoney's runtime binding for Dimwit lists `chart_pixels_and_visual_perception_not_implemented` as a
limitation. This module implements it, in the only form that is falsifiable:

* `read_chart` inverts a Dimwit-rendered chart back into OHLC values using the geometry the renderer emitted.
* `verify_chart_roundtrip` renders a known series, reads it back, and reports the recovery error in *pixels*.
  Because the ground truth is known, the claim "Dimwit can see a chart" becomes a measurable number that a test
  can fail — not a self-attestation.
* `describe_chart` handles the harder case: a *foreign* chart screenshot with no geometry. It reports shape only
  (bar count, up/down mass, pixel-space slope, congestion) and pins `price_scale: "UNKNOWN"`, because without
  an axis mapping there is no honest way to name a price. It never guesses one.

The HSV machinery is `dimwit.perception`'s — the same vectorized pixel-truth stack the studio validators use to
refuse renders that merely *claim* to look right.
"""
from __future__ import annotations

import base64
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..core import sha256_obj
from ..perception import _rgb_to_hsv
from . import chart as chart_mod

#: A body narrower than this cannot be separated from the 1px wick that shares its center column.
MIN_READABLE_BODY_WIDTH = 3
DEFAULT_TOLERANCE_PX = 1.0


class ChartVisionError(ValueError):
    """Raised when pixels cannot be read into prices without guessing."""


def _load_rgb(png_base64: str | None = None, path: str | Path | None = None) -> np.ndarray:
    if (png_base64 is None) == (path is None):
        raise ChartVisionError("supply exactly one of png_base64 or path")
    if png_base64 is not None:
        try:
            raw = base64.b64decode(png_base64, validate=True)
        except Exception as exc:  # noqa: BLE001 - surface as a domain error
            raise ChartVisionError(f"png_base64 is not valid base64: {exc}") from exc
        image = Image.open(io.BytesIO(raw))
    else:
        target = Path(path)  # type: ignore[arg-type]
        if not target.is_file():
            raise ChartVisionError(f"chart image not found: {target}")
        image = Image.open(target)
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _exact_color_mask(pixels: np.ndarray, color: Sequence[int]) -> np.ndarray:
    return (
        (pixels[..., 0] == color[0]) & (pixels[..., 1] == color[1]) & (pixels[..., 2] == color[2])
    )


def read_chart(
    geometry: Mapping[str, Any],
    *,
    png_base64: str | None = None,
    path: str | Path | None = None,
    timestamps: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Recover OHLC values from a Dimwit-rendered chart.

    `geometry` is the dict `render_chart_png` returned. It is required: it carries the price<->pixel mapping,
    and without it the y axis is unlabelled pixel rows. Returns a `status` of `OK` or `BLOCKED` — never a
    partially-invented series.
    """
    if geometry.get("schema") != "dimwit.market-chart-geometry.v1":
        raise ChartVisionError("geometry must be a dimwit.market-chart-geometry.v1 payload")
    body_width = int(geometry["body_width"])
    if body_width < MIN_READABLE_BODY_WIDTH:
        return {
            "schema": "dimwit.market-chart-read.v1",
            "producer": "dimwit",
            "status": "BLOCKED",
            "reason": (
                f"body_width {body_width}px < {MIN_READABLE_BODY_WIDTH}px: the wick and body share a column, "
                "so open/close cannot be separated. Render fewer bars or a wider canvas."
            ),
            "bars": [],
        }

    pixels = _load_rgb(png_base64=png_base64, path=path)
    height, width = pixels.shape[:2]
    if (width, height) != (int(geometry["width"]), int(geometry["height"])):
        return {
            "schema": "dimwit.market-chart-read.v1",
            "producer": "dimwit",
            "status": "BLOCKED",
            "reason": f"image {width}x{height} does not match geometry {geometry['width']}x{geometry['height']}",
            "bars": [],
        }

    plot = geometry["plot"]
    up_mask = _exact_color_mask(pixels, geometry["candle_up_rgb"])
    down_mask = _exact_color_mask(pixels, geometry["candle_down_rgb"])
    candle_mask = up_mask | down_mask
    band = slice(int(plot["y0"]), int(plot["y1"]) + 1)

    half = body_width // 2
    recovered: list[dict[str, Any]] = []
    unread: list[int] = []
    for position in range(int(geometry["bars_rendered"])):
        center = chart_mod.x_center(geometry, position)
        body_column = center - half  # left edge of the body: body pixels only, no wick
        if not 0 <= body_column < width:
            unread.append(position)
            continue
        wick_rows = np.flatnonzero(candle_mask[band, center])
        body_rows = np.flatnonzero(candle_mask[band, body_column])
        if wick_rows.size == 0 or body_rows.size == 0:
            unread.append(position)
            continue
        offset = int(plot["y0"])
        high_y = int(wick_rows.min()) + offset
        low_y = int(wick_rows.max()) + offset
        body_top = int(body_rows.min()) + offset
        body_bottom = int(body_rows.max()) + offset
        rising = bool(up_mask[body_top, body_column])
        top_price = chart_mod.y_to_price(geometry, body_top)
        bottom_price = chart_mod.y_to_price(geometry, body_bottom)
        recovered.append(
            {
                "window_position": position,
                "index": int(geometry["window_start_index"]) + position,
                "observed_at": (
                    timestamps[position] if timestamps and position < len(timestamps) else None
                ),
                "open": round(bottom_price if rising else top_price, 8),
                "high": round(chart_mod.y_to_price(geometry, high_y), 8),
                "low": round(chart_mod.y_to_price(geometry, low_y), 8),
                "close": round(top_price if rising else bottom_price, 8),
                "direction": 1 if rising else -1,
                "pixels": {
                    "center_x": center,
                    "high_y": high_y,
                    "low_y": low_y,
                    "body_top_y": body_top,
                    "body_bottom_y": body_bottom,
                },
            }
        )

    return {
        "schema": "dimwit.market-chart-read.v1",
        "producer": "dimwit",
        "status": "OK" if recovered else "BLOCKED",
        "reason": None if recovered else "no candle pixels found in the plot band",
        "source": "DIMWIT_RENDERED_CHART_WITH_GEOMETRY",
        "price_scale": "KNOWN_FROM_GEOMETRY",
        "price_per_pixel": round(chart_mod.price_per_pixel(geometry), 10),
        "bars_expected": int(geometry["bars_rendered"]),
        "bars_read": len(recovered),
        "unread_positions": unread,
        "bars": recovered,
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


def verify_chart_roundtrip(
    normalized: Mapping[str, Any],
    *,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
    **render_kwargs: Any,
) -> dict[str, Any]:
    """Render `normalized`, read it back, and report the recovery error in pixels.

    Errors are reported in pixels rather than price because a pixel is the actual resolution limit of the
    medium: a 1-pixel error is the renderer being exact, and no amount of price precision can beat it. Overlays
    and markers are disabled for the verification render (they overwrite candle pixels by design), and the
    result discloses that.
    """
    for reserved in ("overlays", "markers"):
        render_kwargs.pop(reserved, None)
    render = chart_mod.render_chart_png(normalized, labels=True, **render_kwargs)
    geometry = render["geometry"]
    window_start = int(geometry["window_start_index"])
    window = list(normalized["bars"])[window_start:]
    read = read_chart(
        geometry,
        png_base64=render["png_base64"],
        timestamps=[bar["observed_at"] for bar in window],
    )
    if read["status"] != "OK":
        return {
            "schema": "dimwit.market-chart-roundtrip.v1",
            "producer": "dimwit",
            "verdict": "BLOCKED",
            "reason": read["reason"],
            "render_digest": render["plot_digest"],
        }

    scale = chart_mod.price_per_pixel(geometry) or 1.0
    errors: dict[str, list[float]] = {"open": [], "high": [], "low": [], "close": []}
    direction_mismatches = 0
    for bar, recovered in zip(window, read["bars"], strict=False):
        for field in errors:
            errors[field].append(abs(float(bar[field]) - float(recovered[field])) / scale)
        rising_source = float(bar["close"]) >= float(bar["open"])
        if rising_source != (recovered["direction"] > 0):
            direction_mismatches += 1

    per_field = {
        field: {
            "max_px": round(max(values), 6) if values else None,
            "mean_px": round(sum(values) / len(values), 6) if values else None,
        }
        for field, values in errors.items()
    }
    worst = max((stats["max_px"] or 0.0) for stats in per_field.values())
    coverage = read["bars_read"] / max(1, int(geometry["bars_rendered"]))
    verdict = (
        "PASS"
        if worst <= tolerance_px and coverage == 1.0 and direction_mismatches == 0
        else "BLOCKED"
    )
    return {
        "schema": "dimwit.market-chart-roundtrip.v1",
        "producer": "dimwit",
        "verdict": verdict,
        "reason": (
            None
            if verdict == "PASS"
            else (
                f"worst_error_px={worst} tolerance_px={tolerance_px} coverage={coverage} "
                f"direction_mismatches={direction_mismatches}"
            )
        ),
        "symbol": normalized["symbol"],
        "timeframe": normalized["timeframe"],
        "series_digest": normalized["digest"],
        "overlays_disabled_for_verification": True,
        "tolerance_px": tolerance_px,
        "worst_error_px": round(worst, 6),
        "price_per_pixel": round(scale, 10),
        "coverage": round(coverage, 6),
        "direction_mismatches": direction_mismatches,
        "bars_compared": len(read["bars"]),
        "per_field_error": per_field,
        "render_digest": render["plot_digest"],
        "chart_pixel_evidence": "PROVIDED_AND_VERIFIED",
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


def _dominant_colors(pixels: np.ndarray, min_share: float = 0.10, limit: int = 3) -> list[list[int]]:
    """Exact RGB values covering at least `min_share` of the frame — the background and panel fills.

    Needed because a themed chart can have a *saturated* background. Dimwit's own `tote` theme is pitch green,
    which a naive hue test reads as one enormous up candle. Excluding the large flat fills first makes the hue
    test mean what it claims to mean.
    """
    packed = (
        pixels[..., 0].astype(np.int32) << 16
        | pixels[..., 1].astype(np.int32) << 8
        | pixels[..., 2].astype(np.int32)
    ).ravel()
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(counts)[::-1][:limit]
    threshold = min_share * packed.size
    return [
        [int((values[i] >> 16) & 0xFF), int((values[i] >> 8) & 0xFF), int(values[i] & 0xFF)]
        for i in order
        if counts[i] >= threshold
    ]


def _max_horizontal_run(mask: np.ndarray) -> int:
    """Longest run of consecutive True pixels within any single row."""
    if not mask.any():
        return 0
    longest = 0
    for row in mask:
        if not row.any():
            continue
        padded = np.concatenate(([False], row, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        longest = max(longest, int((edges[1::2] - edges[0::2]).max()))
    return longest


def _rule_line_colors(
    pixels: np.ndarray,
    mask: np.ndarray,
    *,
    min_run_fraction: float = 0.5,
    min_pixel_fraction: float = 0.0005,
) -> list[list[int]]:
    """Exact colors that draw long horizontal rules — gridlines, axes, separators.

    A candle body is at most a few pixels wide, so no candle color can produce a single-color horizontal run
    spanning half the frame. A gridline always does. This catches themed gridlines that are too *small* to be
    caught as background but hue-wise indistinguishable from a candle: Dimwit's own `tote` theme draws green
    gridlines that would otherwise merge every bar into one blob.
    """
    packed = (
        pixels[..., 0].astype(np.int32) << 16
        | pixels[..., 1].astype(np.int32) << 8
        | pixels[..., 2].astype(np.int32)
    )
    values, counts = np.unique(packed[mask], return_counts=True)
    width = pixels.shape[1]
    found: list[list[int]] = []
    for value, count in zip(values, counts, strict=False):
        if count < min_pixel_fraction * packed.size:
            continue
        color = [int((value >> 16) & 0xFF), int((value >> 8) & 0xFF), int(value & 0xFF)]
        if _max_horizontal_run(_exact_color_mask(pixels, color)) >= min_run_fraction * width:
            found.append(color)
    return found


def _row_bands(mask: np.ndarray, min_gap: int = 4) -> list[tuple[int, int]]:
    """Contiguous horizontal bands of mask coverage, split on runs of >= `min_gap` empty rows.

    A candlestick chart with a volume pane produces two bands. Without this split, volume bars — which are
    conventionally green/red too — get counted as price candles.
    """
    occupied = mask.any(axis=1)
    bands: list[tuple[int, int]] = []
    start: int | None = None
    empty_run = 0
    for y, flag in enumerate(occupied):
        if flag:
            if start is None:
                start = y
            empty_run = 0
        elif start is not None:
            empty_run += 1
            if empty_run >= min_gap:
                bands.append((start, y - empty_run))
                start = None
                empty_run = 0
    if start is not None:
        bands.append((start, len(occupied) - 1))
    return bands


def describe_chart(
    *,
    png_base64: str | None = None,
    path: str | Path | None = None,
    saturation_floor: float = 0.25,
    value_floor: float = 0.18,
) -> dict[str, Any]:
    """Shape-only reading of a FOREIGN chart image (a screenshot from someone else's charting tool).

    Green-ish and red-ish saturated pixel masses stand in for up/down candles, after two corrections that stop
    the heuristic from lying: large flat fills (background/panel) are excluded by exact color, and the mask is
    split into horizontal bands so a volume pane is analyzed separately from the price pane.

    Everything reported is in pixel space and `price_scale` is pinned to `UNKNOWN`: with no axis mapping, any
    price number would be invented. Use this to compare *shape* — how many bars, which way the mass leans, where
    the congestion is — never to extract levels.
    """
    pixels = _load_rgb(png_base64=png_base64, path=path)
    normalized = pixels.astype(np.float32) / 255.0
    hsv = _rgb_to_hsv(normalized)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    background = _dominant_colors(pixels)
    fill_mask = np.zeros(pixels.shape[:2], dtype=bool)
    for color in background:
        fill_mask |= _exact_color_mask(pixels, color)
    lively = (saturation > saturation_floor) & (value > value_floor) & ~fill_mask
    rule_colors = _rule_line_colors(pixels, lively)
    for color in rule_colors:
        lively = lively & ~_exact_color_mask(pixels, color)
    up_mask = lively & (hue >= 90) & (hue <= 170)
    down_mask = lively & ((hue <= 20) | (hue >= 335))
    candle_mask = up_mask | down_mask

    if not int(candle_mask.sum()):
        return {
            "schema": "dimwit.market-foreign-chart-read.v1",
            "producer": "dimwit",
            "status": "BLOCKED",
            "reason": "no saturated green/red candle mass found; this may not be a candlestick chart",
            "price_scale": "UNKNOWN",
            "excluded_background_colors": background,
            "excluded_rule_line_colors": rule_colors,
        }

    bands = _row_bands(candle_mask)
    price_band = max(bands, key=lambda item: item[1] - item[0]) if bands else None
    if price_band is not None:
        pane = np.zeros_like(candle_mask)
        pane[price_band[0] : price_band[1] + 1, :] = True
        up_mask = up_mask & pane
        down_mask = down_mask & pane
        candle_mask = candle_mask & pane

    total = int(candle_mask.sum())
    if total == 0:  # pragma: no cover - band selection always keeps the largest band
        return {
            "schema": "dimwit.market-foreign-chart-read.v1",
            "producer": "dimwit",
            "status": "BLOCKED",
            "reason": "candle mass vanished after pane selection",
            "price_scale": "UNKNOWN",
        }

    column_counts = candle_mask.sum(axis=0)
    occupied = column_counts > 0
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, flag in enumerate(occupied):
        if flag and start is None:
            start = x
        elif not flag and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, len(occupied) - 1))

    widths = sorted(end - begin + 1 for begin, end in runs)
    gaps = [
        runs[i + 1][0] - runs[i][1] - 1 for i in range(len(runs) - 1)
    ]
    rows = np.flatnonzero(candle_mask.any(axis=1))
    midpoints: list[tuple[int, float]] = []
    for begin, end in runs:
        column_slice = candle_mask[:, begin : end + 1]
        row_indices = np.flatnonzero(column_slice.any(axis=1))
        if row_indices.size:
            midpoints.append(((begin + end) / 2.0, float(row_indices.mean())))

    slope_per_px = None
    if len(midpoints) >= 2:
        xs = np.array([item[0] for item in midpoints], dtype=np.float64)
        ys = np.array([item[1] for item in midpoints], dtype=np.float64)
        spread = float(((xs - xs.mean()) ** 2).sum())
        if spread > 0:
            slope_per_px = float(((xs - xs.mean()) * (ys - ys.mean())).sum() / spread)

    up_pixels = int(up_mask.sum())
    return {
        "schema": "dimwit.market-foreign-chart-read.v1",
        "producer": "dimwit",
        "status": "OK",
        "source": "FOREIGN_CHART_PIXELS",
        "price_scale": "UNKNOWN",
        "image": {"width": int(pixels.shape[1]), "height": int(pixels.shape[0])},
        "excluded_background_colors": background,
        "excluded_rule_line_colors": rule_colors,
        "row_bands_detected": len(bands),
        "price_pane_rows": None if price_band is None else list(price_band),
        "candle_mass_pixels": total,
        "up_mass_fraction": round(up_pixels / total, 6),
        "down_mass_fraction": round(1.0 - up_pixels / total, 6),
        "detected_bar_count": len(runs),
        "median_bar_width_px": widths[len(widths) // 2] if widths else None,
        "max_column_gap_px": max(gaps) if gaps else 0,
        "vertical_extent_px": int(rows.max() - rows.min() + 1) if rows.size else 0,
        # y grows downward in image space, so a NEGATIVE slope means the mass rises left-to-right
        "pixel_slope_per_column": None if slope_per_px is None else round(slope_per_px, 8),
        "pixel_space_drift": (
            "UNDETERMINED"
            if slope_per_px is None
            else "RISING"
            if slope_per_px < -0.02
            else "FALLING"
            if slope_per_px > 0.02
            else "FLAT"
        ),
        "read_digest": sha256_obj(
            {
                "width": int(pixels.shape[1]),
                "height": int(pixels.shape[0]),
                "mass": total,
                "bars": len(runs),
            }
        ),
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
        "limitations": [
            "no axis mapping: prices, levels and dates cannot be recovered from a foreign image",
            "hue heuristics assume a conventional green-up / red-down palette",
            "only the tallest horizontal band is analyzed; a second price pane would be ignored",
            "flat fills covering <10% of the frame are not treated as background and may join the mass",
        ],
    }
