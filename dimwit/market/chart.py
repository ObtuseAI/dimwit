"""Deterministic chart renderer — the "chart viewer" half of Dimwit's assigned DumbMoney role.

Design constraints, all of them driven by the fact that these pixels are *evidence*:

* **Deterministic.** Same series + same options => byte-identical PNG. No timestamps in the file, no
  antialiasing, no floating-point-dependent layout: every coordinate is an int.
* **Invertible.** `chart_geometry()` is computed first and returned with the image, so any consumer can map
  pixel <-> price/time exactly. `chart_vision.read_chart()` uses it to recover the OHLC series back out of the
  pixels, which is what makes "chart vision" a testable claim instead of a slogan.
* **Reserved colors.** Candle up/down bodies use exact RGB constants that nothing else in the frame may use.
  Overlays and markers are drawn from a disjoint palette so the reader can separate price geometry from
  decoration by color alone.
* **Honest windowing.** A chart that cannot fit every bar renders the most recent window and reports
  `bars_omitted` / `window_start_index`. Silent truncation reads as "you are looking at everything".

Themes: `dark` (default), `light`, `tote` (the pitch-green totalizator skin the DumbMoney dashboard uses).
"""
from __future__ import annotations

import base64
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..core import sha256_obj, sha256_text

ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = ROOT / "artifacts" / "market"

#: Reserved candle colors. Overlays/markers/grid MUST NOT reuse these — chart_vision keys off them.
CANDLE_UP = (38, 208, 124)
CANDLE_DOWN = (226, 66, 74)

THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "dark": {
        "background": (14, 17, 22),
        "panel": (20, 24, 31),
        "grid": (44, 51, 62),
        "axis": (120, 132, 148),
        "text": (198, 208, 222),
        "volume_up": (26, 96, 66),
        "volume_down": (108, 44, 48),
    },
    "light": {
        "background": (250, 250, 252),
        "panel": (240, 241, 245),
        "grid": (214, 218, 226),
        "axis": (110, 118, 132),
        "text": (36, 40, 48),
        "volume_up": (168, 214, 190),
        "volume_down": (226, 172, 176),
    },
    "tote": {
        "background": (9, 38, 26),
        "panel": (12, 48, 33),
        "grid": (24, 74, 52),
        "axis": (132, 176, 150),
        "text": (232, 226, 176),
        "volume_up": (26, 96, 66),
        "volume_down": (108, 44, 48),
    },
}

#: Overlay palette, disjoint from CANDLE_UP/CANDLE_DOWN and from every theme color.
OVERLAY_COLORS: tuple[tuple[int, int, int], ...] = (
    (240, 196, 64),
    (96, 168, 244),
    (196, 128, 236),
    (244, 148, 96),
    (128, 220, 232),
    (212, 212, 216),
)
MARKER_UP = (120, 236, 176)
MARKER_DOWN = (248, 140, 148)
MARKER_NEUTRAL = (196, 196, 204)

MIN_SLOT = 3
MARGIN_LEFT = 66
MARGIN_RIGHT = 10
MARGIN_TOP = 10
MARGIN_BOTTOM = 26
GRID_LINES = 5
PRICE_PAD_FRACTION = 0.02


class ChartError(ValueError):
    """Raised when a chart cannot be rendered without misrepresenting the series."""


def _theme(name: str) -> dict[str, tuple[int, int, int]]:
    if name not in THEMES:
        raise ChartError(f"unknown theme {name!r}; expected one of {sorted(THEMES)}")
    return THEMES[name]


def chart_geometry(
    normalized: Mapping[str, Any],
    *,
    width: int = 1100,
    height: int = 620,
    volume_pane_fraction: float = 0.22,
    max_bars: int | None = None,
) -> dict[str, Any]:
    """Compute the exact pixel geometry of a chart before drawing it.

    Returned separately (and embedded in every render result) so pixel <-> price inversion is available to any
    consumer without re-deriving layout constants.
    """
    if width < MARGIN_LEFT + MARGIN_RIGHT + 60 or height < MARGIN_TOP + MARGIN_BOTTOM + 80:
        raise ChartError(f"canvas {width}x{height} is too small to render a readable chart")
    if not 0.0 <= volume_pane_fraction < 0.6:
        raise ChartError("volume_pane_fraction must be in [0, 0.6)")

    series_bars = list(normalized["bars"])
    if not series_bars:
        raise ChartError("cannot render an empty series")

    plot_x0 = MARGIN_LEFT
    plot_x1 = width - MARGIN_RIGHT
    plot_width = plot_x1 - plot_x0
    total_height = height - MARGIN_TOP - MARGIN_BOTTOM
    volume_height = int(total_height * volume_pane_fraction)
    price_height = total_height - volume_height - (4 if volume_height else 0)
    price_y0 = MARGIN_TOP
    price_y1 = price_y0 + price_height
    volume_y0 = price_y1 + (4 if volume_height else 0)
    volume_y1 = volume_y0 + volume_height

    capacity = plot_width // MIN_SLOT
    limit = capacity if max_bars is None else min(capacity, max_bars)
    if limit < 2:
        raise ChartError("plot area cannot fit two bars")
    window_start = max(0, len(series_bars) - limit)
    window = series_bars[window_start:]
    slot = max(MIN_SLOT, plot_width // len(window))
    if slot % 2 == 0:
        slot -= 1  # odd slot => an exact center column for the wick
    body_width = max(1, slot - 2)

    price_min = min(float(bar["low"]) for bar in window)
    price_max = max(float(bar["high"]) for bar in window)
    span = price_max - price_min
    pad = span * PRICE_PAD_FRACTION if span > 0 else max(price_max * 0.01, 1e-9)
    price_min -= pad
    price_max += pad

    volume_max = max((float(bar["volume"]) for bar in window), default=0.0)

    return {
        "schema": "dimwit.market-chart-geometry.v1",
        "width": width,
        "height": height,
        "plot": {"x0": plot_x0, "x1": plot_x1, "y0": price_y0, "y1": price_y1},
        "volume_pane": (
            None if not volume_height else {"x0": plot_x0, "x1": plot_x1, "y0": volume_y0, "y1": volume_y1}
        ),
        "slot_width": slot,
        "body_width": body_width,
        "window_start_index": window_start,
        "bars_rendered": len(window),
        "bars_omitted": window_start,
        "price_min": price_min,
        "price_max": price_max,
        "price_span": price_max - price_min,
        "volume_max": volume_max,
        "candle_up_rgb": list(CANDLE_UP),
        "candle_down_rgb": list(CANDLE_DOWN),
        "first_observed_at": window[0]["observed_at"],
        "last_observed_at": window[-1]["observed_at"],
    }


def x_center(geometry: Mapping[str, Any], window_position: int) -> int:
    """Pixel column of the wick for the `window_position`-th rendered bar."""
    return int(geometry["plot"]["x0"]) + window_position * int(geometry["slot_width"]) + int(
        geometry["slot_width"]
    ) // 2


def price_to_y(geometry: Mapping[str, Any], price: float) -> int:
    plot = geometry["plot"]
    span = float(geometry["price_span"])
    if span <= 0:
        return int((plot["y0"] + plot["y1"]) // 2)
    ratio = (float(geometry["price_max"]) - float(price)) / span
    return int(round(plot["y0"] + ratio * (plot["y1"] - plot["y0"])))


def y_to_price(geometry: Mapping[str, Any], y: float) -> float:
    plot = geometry["plot"]
    height = plot["y1"] - plot["y0"]
    if height <= 0:
        return float(geometry["price_max"])
    ratio = (float(y) - plot["y0"]) / height
    return float(geometry["price_max"]) - ratio * float(geometry["price_span"])


def price_per_pixel(geometry: Mapping[str, Any]) -> float:
    plot = geometry["plot"]
    height = plot["y1"] - plot["y0"]
    return float(geometry["price_span"]) / height if height else 0.0


def _format_price(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 10:
        return f"{value:,.2f}"
    if magnitude >= 1:
        return f"{value:.3f}"
    return f"{value:.5f}"


def _draw_grid(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    palette: Mapping[str, tuple[int, int, int]],
    labels: bool,
) -> list[dict[str, Any]]:
    plot = geometry["plot"]
    ticks: list[dict[str, Any]] = []
    for step in range(GRID_LINES + 1):
        ratio = step / GRID_LINES
        y = int(round(plot["y0"] + ratio * (plot["y1"] - plot["y0"])))
        price = y_to_price(geometry, y)
        draw.line([(plot["x0"], y), (plot["x1"], y)], fill=palette["grid"], width=1)
        ticks.append({"y": y, "price": round(price, 8)})
        if labels:
            draw.text((6, y - 5), _format_price(price), fill=palette["text"])
    return ticks


def _draw_candles(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    window: Sequence[Mapping[str, Any]],
) -> None:
    body_width = int(geometry["body_width"])
    half = body_width // 2
    for position, bar in enumerate(window):
        center = x_center(geometry, position)
        rising = float(bar["close"]) >= float(bar["open"])
        color = CANDLE_UP if rising else CANDLE_DOWN
        high_y = price_to_y(geometry, float(bar["high"]))
        low_y = price_to_y(geometry, float(bar["low"]))
        draw.line([(center, high_y), (center, low_y)], fill=color, width=1)
        open_y = price_to_y(geometry, float(bar["open"]))
        close_y = price_to_y(geometry, float(bar["close"]))
        top, bottom = min(open_y, close_y), max(open_y, close_y)
        if bottom == top:
            bottom = top  # doji: a single row is the honest depiction
        draw.rectangle(
            [(center - half, top), (center - half + body_width - 1, bottom)],
            fill=color,
        )


def _draw_volume(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    window: Sequence[Mapping[str, Any]],
    palette: Mapping[str, tuple[int, int, int]],
) -> None:
    pane = geometry.get("volume_pane")
    if not pane:
        return
    volume_max = float(geometry["volume_max"])
    if volume_max <= 0:
        return
    body_width = int(geometry["body_width"])
    half = body_width // 2
    pane_height = pane["y1"] - pane["y0"]
    for position, bar in enumerate(window):
        center = x_center(geometry, position)
        rising = float(bar["close"]) >= float(bar["open"])
        color = palette["volume_up"] if rising else palette["volume_down"]
        bar_height = int(round(float(bar["volume"]) / volume_max * pane_height))
        if bar_height <= 0:
            continue
        draw.rectangle(
            [(center - half, pane["y1"] - bar_height), (center - half + body_width - 1, pane["y1"] - 1)],
            fill=color,
        )


def _draw_overlays(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    overlays: Mapping[str, Sequence[float | None]],
) -> list[dict[str, Any]]:
    plot = geometry["plot"]
    start = int(geometry["window_start_index"])
    count = int(geometry["bars_rendered"])
    legend: list[dict[str, Any]] = []
    for order, (name, series) in enumerate(sorted(overlays.items())):
        color = OVERLAY_COLORS[order % len(OVERLAY_COLORS)]
        legend.append({"name": name, "rgb": list(color)})
        points: list[tuple[int, int]] = []
        for position in range(count):
            index = start + position
            if index >= len(series):
                break
            value = series[index]
            if value is None:
                if len(points) > 1:
                    draw.line(points, fill=color, width=1)
                points = []
                continue
            y = price_to_y(geometry, float(value))
            if plot["y0"] <= y <= plot["y1"]:
                points.append((x_center(geometry, position), y))
            elif len(points) > 1:
                draw.line(points, fill=color, width=1)
                points = []
        if len(points) > 1:
            draw.line(points, fill=color, width=1)
    return legend


def _draw_markers(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    markers: Sequence[Mapping[str, Any]],
) -> int:
    plot = geometry["plot"]
    start = int(geometry["window_start_index"])
    count = int(geometry["bars_rendered"])
    drawn = 0
    for marker in markers:
        index = int(marker.get("detected_at_index", marker.get("index", -1)))
        position = index - start
        if not 0 <= position < count:
            continue
        direction = int(marker.get("direction", 0))
        color = MARKER_UP if direction > 0 else MARKER_DOWN if direction < 0 else MARKER_NEUTRAL
        center = x_center(geometry, position)
        if direction >= 0:
            top = plot["y0"] + 2
            draw.polygon(
                [(center, top + 6), (center - 3, top), (center + 3, top)],
                fill=color,
            )
        else:
            bottom = plot["y1"] - 2
            draw.polygon(
                [(center, bottom - 6), (center - 3, bottom), (center + 3, bottom)],
                fill=color,
            )
        drawn += 1
    return drawn


def _draw_time_axis(
    draw: ImageDraw.ImageDraw,
    geometry: Mapping[str, Any],
    window: Sequence[Mapping[str, Any]],
    palette: Mapping[str, tuple[int, int, int]],
) -> None:
    plot = geometry["plot"]
    y = int(geometry["height"]) - MARGIN_BOTTOM + 6
    draw.line([(plot["x0"], plot["y1"] + 1), (plot["x1"], plot["y1"] + 1)], fill=palette["axis"], width=1)
    for position in (0, len(window) // 2, len(window) - 1):
        label = window[position]["observed_at"].replace("T", " ").replace("Z", "")
        anchor = max(plot["x0"], min(x_center(geometry, position) - 34, plot["x1"] - 70))
        draw.text((anchor, y), label[:16], fill=palette["text"])


def render_chart_png(
    normalized: Mapping[str, Any],
    *,
    overlays: Mapping[str, Sequence[float | None]] | None = None,
    markers: Sequence[Mapping[str, Any]] | None = None,
    theme: str = "dark",
    width: int = 1100,
    height: int = 620,
    volume_pane_fraction: float = 0.22,
    max_bars: int | None = None,
    labels: bool = True,
) -> dict[str, Any]:
    """Render candles (+ optional overlays/markers) to a deterministic PNG.

    Returns the image as base64 (so it survives JSON/MCP transport unchanged) plus the geometry needed to read
    it back. `plot_digest` covers only the price plot rectangle, i.e. the part whose pixels are price evidence
    and which does not move when a font renders differently.
    """
    palette = _theme(theme)
    geometry = chart_geometry(
        normalized,
        width=width,
        height=height,
        volume_pane_fraction=volume_pane_fraction,
        max_bars=max_bars,
    )
    window = list(normalized["bars"])[int(geometry["window_start_index"]) :]

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    plot = geometry["plot"]
    draw.rectangle([(plot["x0"], plot["y0"]), (plot["x1"], plot["y1"])], fill=palette["panel"])
    if geometry["volume_pane"]:
        pane = geometry["volume_pane"]
        draw.rectangle([(pane["x0"], pane["y0"]), (pane["x1"], pane["y1"])], fill=palette["panel"])

    ticks = _draw_grid(draw, geometry, palette, labels)
    _draw_volume(draw, geometry, window, palette)
    _draw_candles(draw, geometry, window)
    legend = _draw_overlays(draw, geometry, overlays or {})
    markers_drawn = _draw_markers(draw, geometry, markers or [])
    if labels:
        _draw_time_axis(draw, geometry, window, palette)
        header = (
            f"{normalized['symbol']}  {normalized['timeframe']}  "
            f"{normalized['classification']}  bars={geometry['bars_rendered']}"
        )
        draw.text((MARGIN_LEFT + 4, 0), header, fill=palette["text"])

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    png_bytes = buffer.getvalue()

    plot_crop = image.crop((plot["x0"], plot["y0"], plot["x1"] + 1, plot["y1"] + 1))
    return {
        "schema": "dimwit.market-chart-render.v1",
        "producer": "dimwit",
        "symbol": normalized["symbol"],
        "timeframe": normalized["timeframe"],
        "as_of": normalized["as_of"],
        "series_digest": normalized["digest"],
        "theme": theme,
        "labels": labels,
        "geometry": geometry,
        "price_ticks": ticks,
        "overlay_legend": legend,
        "markers_drawn": markers_drawn,
        "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        "png_bytes": len(png_bytes),
        "png_sha256": sha256_text(base64.b64encode(png_bytes).decode("ascii")),
        "plot_digest": sha256_text(base64.b64encode(plot_crop.tobytes()).decode("ascii")),
        "chart_pixel_evidence": "PROVIDED",
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


def render_chart_svg(
    normalized: Mapping[str, Any],
    *,
    overlays: Mapping[str, Sequence[float | None]] | None = None,
    markers: Sequence[Mapping[str, Any]] | None = None,
    theme: str = "dark",
    width: int = 1100,
    height: int = 620,
    volume_pane_fraction: float = 0.22,
    max_bars: int | None = None,
) -> dict[str, Any]:
    """Same chart as vector SVG, for dashboards that want crisp scaling and text selection.

    Shares `chart_geometry` with the PNG path, so both renderings place a given price at the same y.
    """
    palette = _theme(theme)
    geometry = chart_geometry(
        normalized,
        width=width,
        height=height,
        volume_pane_fraction=volume_pane_fraction,
        max_bars=max_bars,
    )
    window = list(normalized["bars"])[int(geometry["window_start_index"]) :]
    plot = geometry["plot"]

    def rgb(color: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % color

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{normalized["symbol"]} {normalized["timeframe"]} candlestick chart">',
        f'<rect width="{width}" height="{height}" fill="{rgb(palette["background"])}"/>',
        f'<rect x="{plot["x0"]}" y="{plot["y0"]}" width="{plot["x1"] - plot["x0"]}" '
        f'height="{plot["y1"] - plot["y0"]}" fill="{rgb(palette["panel"])}"/>',
    ]
    if geometry["volume_pane"]:
        pane = geometry["volume_pane"]
        parts.append(
            f'<rect x="{pane["x0"]}" y="{pane["y0"]}" width="{pane["x1"] - pane["x0"]}" '
            f'height="{pane["y1"] - pane["y0"]}" fill="{rgb(palette["panel"])}"/>'
        )
    for step in range(GRID_LINES + 1):
        y = int(round(plot["y0"] + step / GRID_LINES * (plot["y1"] - plot["y0"])))
        price = y_to_price(geometry, y)
        parts.append(
            f'<line x1="{plot["x0"]}" y1="{y}" x2="{plot["x1"]}" y2="{y}" '
            f'stroke="{rgb(palette["grid"])}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="6" y="{y + 4}" font-family="monospace" font-size="11" '
            f'fill="{rgb(palette["text"])}">{_format_price(price)}</text>'
        )

    pane = geometry.get("volume_pane")
    volume_max = float(geometry["volume_max"])
    body_width = int(geometry["body_width"])
    half = body_width // 2
    for position, bar in enumerate(window):
        center = x_center(geometry, position)
        rising = float(bar["close"]) >= float(bar["open"])
        color = rgb(CANDLE_UP if rising else CANDLE_DOWN)
        high_y = price_to_y(geometry, float(bar["high"]))
        low_y = price_to_y(geometry, float(bar["low"]))
        open_y = price_to_y(geometry, float(bar["open"]))
        close_y = price_to_y(geometry, float(bar["close"]))
        top, bottom = min(open_y, close_y), max(open_y, close_y)
        parts.append(
            f'<line x1="{center}" y1="{high_y}" x2="{center}" y2="{low_y}" stroke="{color}" stroke-width="1"/>'
        )
        parts.append(
            f'<rect x="{center - half}" y="{top}" width="{body_width}" '
            f'height="{max(1, bottom - top)}" fill="{color}"/>'
        )
        if pane and volume_max > 0:
            pane_height = pane["y1"] - pane["y0"]
            bar_height = int(round(float(bar["volume"]) / volume_max * pane_height))
            if bar_height > 0:
                volume_color = rgb(palette["volume_up"] if rising else palette["volume_down"])
                parts.append(
                    f'<rect x="{center - half}" y="{pane["y1"] - bar_height}" width="{body_width}" '
                    f'height="{bar_height}" fill="{volume_color}"/>'
                )

    legend: list[dict[str, Any]] = []
    start = int(geometry["window_start_index"])
    for order, (name, series) in enumerate(sorted((overlays or {}).items())):
        color = OVERLAY_COLORS[order % len(OVERLAY_COLORS)]
        legend.append({"name": name, "rgb": list(color)})
        run: list[str] = []
        for position in range(int(geometry["bars_rendered"])):
            index = start + position
            value = series[index] if index < len(series) else None
            if value is None:
                if len(run) > 1:
                    parts.append(
                        f'<polyline points="{" ".join(run)}" fill="none" stroke="{rgb(color)}" stroke-width="1"/>'
                    )
                run = []
                continue
            run.append(f"{x_center(geometry, position)},{price_to_y(geometry, float(value))}")
        if len(run) > 1:
            parts.append(
                f'<polyline points="{" ".join(run)}" fill="none" stroke="{rgb(color)}" stroke-width="1"/>'
            )

    markers_drawn = 0
    for marker in markers or []:
        index = int(marker.get("detected_at_index", marker.get("index", -1)))
        position = index - start
        if not 0 <= position < int(geometry["bars_rendered"]):
            continue
        direction = int(marker.get("direction", 0))
        color = rgb(MARKER_UP if direction > 0 else MARKER_DOWN if direction < 0 else MARKER_NEUTRAL)
        center = x_center(geometry, position)
        if direction >= 0:
            top = plot["y0"] + 2
            points = f"{center},{top + 6} {center - 3},{top} {center + 3},{top}"
        else:
            bottom = plot["y1"] - 2
            points = f"{center},{bottom - 6} {center - 3},{bottom} {center + 3},{bottom}"
        parts.append(f'<polygon points="{points}" fill="{color}"/>')
        markers_drawn += 1

    header = (
        f"{normalized['symbol']} {normalized['timeframe']} "
        f"{normalized['classification']} bars={geometry['bars_rendered']}"
    )
    parts.append(
        f'<text x="{MARGIN_LEFT + 4}" y="{MARGIN_TOP - 1}" font-family="monospace" font-size="11" '
        f'fill="{rgb(palette["text"])}">{header}</text>'
    )
    parts.append("</svg>")
    svg = "".join(parts)
    return {
        "schema": "dimwit.market-chart-render.v1",
        "producer": "dimwit",
        "format": "svg",
        "symbol": normalized["symbol"],
        "timeframe": normalized["timeframe"],
        "as_of": normalized["as_of"],
        "series_digest": normalized["digest"],
        "theme": theme,
        "geometry": geometry,
        "overlay_legend": legend,
        "markers_drawn": markers_drawn,
        "svg": svg,
        "svg_sha256": sha256_text(svg),
        "chart_pixel_evidence": "VECTOR_ONLY",
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


def export_chart(
    normalized: Mapping[str, Any],
    filename: str,
    *,
    fmt: str = "png",
    **render_kwargs: Any,
) -> dict[str, Any]:
    """Write a rendered chart under `artifacts/market/` and return the render result plus the path.

    The only write path in this package. `filename` must be a bare name — no separators, no traversal, no
    absolute paths — and the resolved target must stay inside `artifacts/market/`. This is a new gate, not a
    relaxation of an existing one: rendering itself never touches disk.
    """
    if fmt not in {"png", "svg"}:
        raise ChartError("fmt must be 'png' or 'svg'")
    if not isinstance(filename, str) or not filename.strip():
        raise ChartError("filename must be a non-empty string")
    if any(token in filename for token in ("/", "\\", "..", ":")) or Path(filename).is_absolute():
        raise ChartError(f"filename {filename!r} must be a bare name inside artifacts/market")
    expected_suffix = f".{fmt}"
    if not filename.endswith(expected_suffix):
        filename = f"{filename}{expected_suffix}"

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    target = (EXPORT_ROOT / filename).resolve()
    if not target.is_relative_to(EXPORT_ROOT.resolve()):
        raise ChartError("resolved export path escaped artifacts/market")

    if fmt == "png":
        result = render_chart_png(normalized, **render_kwargs)
        target.write_bytes(base64.b64decode(result["png_base64"]))
    else:
        result = render_chart_svg(normalized, **render_kwargs)
        target.write_text(result["svg"], encoding="utf-8")
    result = dict(result)
    result["export_path"] = str(target)
    result["export_relative_path"] = str(target.relative_to(ROOT))
    result["export_digest"] = sha256_obj(
        {"path": result["export_relative_path"], "series_digest": normalized["digest"], "format": fmt}
    )
    return result
