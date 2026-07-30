"""Chart renderer tests.

The renderer is treated as an evidence producer, not decoration, so the properties under test are:
determinism (same input, same bytes), invertibility (the returned geometry really maps price to pixel),
disclosure (a windowed chart says how many bars it dropped), and confinement (the only write path cannot escape
`artifacts/market/`).
"""
from __future__ import annotations

import base64

import pytest

from dimwit.market import bars, chart, indicators as ind, patterns as pat
from dimwit.market.selfaudit import synthetic_series


@pytest.fixture(scope="module")
def series() -> dict:
    return bars.normalize_series(synthetic_series(bar_count=400))


def test_render_is_byte_deterministic(series):
    first = chart.render_chart_png(series, max_bars=100)
    second = chart.render_chart_png(series, max_bars=100)
    assert first["png_base64"] == second["png_base64"]
    assert first["png_sha256"] == second["png_sha256"]
    assert first["plot_digest"] == second["plot_digest"]


def test_render_changes_when_the_data_changes(series):
    baseline = chart.render_chart_png(series, max_bars=100)
    last = series["bars"][-1]
    lifted = {**last, "close": last["close"] * 1.05, "high": max(last["high"], last["close"] * 1.05)}
    mutated = bars.normalize_series({**series, "bars": series["bars"][:-1] + [lifted]})
    assert chart.render_chart_png(mutated, max_bars=100)["plot_digest"] != baseline["plot_digest"]


def test_geometry_round_trips_price_to_pixel_and_back(series):
    geometry = chart.chart_geometry(series, max_bars=100)
    scale = chart.price_per_pixel(geometry)
    for price in (
        geometry["price_min"] + geometry["price_span"] * fraction for fraction in (0.05, 0.3, 0.5, 0.8, 0.95)
    ):
        recovered = chart.y_to_price(geometry, chart.price_to_y(geometry, price))
        assert abs(recovered - price) <= scale  # at most one pixel of quantization


def test_geometry_price_band_contains_every_rendered_bar(series):
    geometry = chart.chart_geometry(series, max_bars=100)
    window = series["bars"][geometry["window_start_index"] :]
    assert min(bar["low"] for bar in window) > geometry["price_min"]
    assert max(bar["high"] for bar in window) < geometry["price_max"]


def test_windowing_is_disclosed_never_silent(series):
    geometry = chart.chart_geometry(series, max_bars=60)
    assert geometry["bars_rendered"] == 60
    assert geometry["bars_omitted"] == 400 - 60
    assert geometry["window_start_index"] == 340
    assert geometry["last_observed_at"] == series["bars"][-1]["observed_at"]


def test_bar_slot_is_odd_so_the_wick_has_a_center_column(series):
    for max_bars in (30, 60, 100, 200):
        geometry = chart.chart_geometry(series, max_bars=max_bars)
        assert geometry["slot_width"] % 2 == 1
        assert geometry["body_width"] == geometry["slot_width"] - 2


def test_x_centers_are_strictly_increasing_and_inside_the_plot(series):
    geometry = chart.chart_geometry(series, max_bars=100)
    centers = [chart.x_center(geometry, position) for position in range(geometry["bars_rendered"])]
    assert centers == sorted(set(centers))
    assert geometry["plot"]["x0"] <= centers[0]
    assert centers[-1] <= geometry["plot"]["x1"]


def test_candle_colors_are_reserved_and_disjoint_from_every_theme():
    reserved = {chart.CANDLE_UP, chart.CANDLE_DOWN}
    for name, palette in chart.THEMES.items():
        overlap = reserved & set(palette.values())
        assert not overlap, f"theme {name} reuses a reserved candle color: {overlap}"
    assert not reserved & set(chart.OVERLAY_COLORS)
    assert not reserved & {chart.MARKER_UP, chart.MARKER_DOWN, chart.MARKER_NEUTRAL}


def test_all_themes_render(series):
    for theme in chart.THEMES:
        result = chart.render_chart_png(series, max_bars=80, theme=theme)
        assert result["png_bytes"] > 1000
        assert result["theme"] == theme
    with pytest.raises(chart.ChartError, match="unknown theme"):
        chart.render_chart_png(series, theme="neon-hologram")


def test_overlays_and_markers_are_reported(series):
    panel = ind.indicator_series(series, ["sma20", "sma50", "bb_upper20"])
    markers = pat.detect_patterns(series, ["bullish_engulfing", "bearish_engulfing"])["detections"]
    result = chart.render_chart_png(series, max_bars=120, overlays=panel, markers=markers)
    assert [item["name"] for item in result["overlay_legend"]] == sorted(panel)
    assert result["markers_drawn"] >= 0
    assert result["markers_drawn"] <= len(markers)


def test_render_refuses_a_canvas_too_small_to_read(series):
    with pytest.raises(chart.ChartError, match="too small"):
        chart.render_chart_png(series, width=100, height=60)


def test_svg_shares_geometry_with_the_png(series):
    png = chart.render_chart_png(series, max_bars=90)
    svg = chart.render_chart_svg(series, max_bars=90)
    assert svg["geometry"]["plot"] == png["geometry"]["plot"]
    assert svg["geometry"]["price_min"] == png["geometry"]["price_min"]
    assert svg["svg"].startswith("<svg") and svg["svg"].endswith("</svg>")
    assert svg["chart_pixel_evidence"] == "VECTOR_ONLY"
    assert chart.render_chart_svg(series, max_bars=90)["svg_sha256"] == svg["svg_sha256"]


def test_render_results_carry_no_forecast(series):
    for result in (chart.render_chart_png(series, max_bars=50), chart.render_chart_svg(series, max_bars=50)):
        assert result["forecast_probability"] is None
        assert result["candidate_status"] == "RESEARCH_INPUT_ONLY"
        assert result["producer"] == "dimwit"
        assert result["series_digest"] == series["digest"]


@pytest.mark.parametrize(
    "filename",
    ["../escape.png", "sub/dir.png", "C:\\windows\\evil.png", "/etc/passwd", "..\\..\\x.png"],
)
def test_export_refuses_paths_outside_artifacts_market(series, filename):
    with pytest.raises(chart.ChartError, match="bare name|escaped"):
        chart.export_chart(series, filename, max_bars=40)


def test_export_writes_inside_artifacts_market(series, tmp_path, monkeypatch):
    monkeypatch.setattr(chart, "EXPORT_ROOT", tmp_path / "artifacts" / "market")
    monkeypatch.setattr(chart, "ROOT", tmp_path)
    result = chart.export_chart(series, "unit-test", max_bars=40)
    written = tmp_path / "artifacts" / "market" / "unit-test.png"
    assert written.is_file()
    assert result["export_path"] == str(written.resolve())
    assert written.read_bytes() == base64.b64decode(result["png_base64"])


def test_export_svg_appends_the_right_suffix(series, tmp_path, monkeypatch):
    monkeypatch.setattr(chart, "EXPORT_ROOT", tmp_path / "artifacts" / "market")
    monkeypatch.setattr(chart, "ROOT", tmp_path)
    result = chart.export_chart(series, "vector", fmt="svg", max_bars=40)
    assert result["export_path"].endswith("vector.svg")
    with pytest.raises(chart.ChartError, match="png' or 'svg"):
        chart.export_chart(series, "x", fmt="bmp")


def test_volume_pane_can_be_disabled(series):
    geometry = chart.chart_geometry(series, max_bars=60, volume_pane_fraction=0.0)
    assert geometry["volume_pane"] is None
    with pytest.raises(chart.ChartError, match="volume_pane_fraction"):
        chart.chart_geometry(series, volume_pane_fraction=0.9)


def test_empty_series_cannot_be_rendered():
    with pytest.raises(chart.ChartError, match="empty series"):
        chart.chart_geometry({"bars": []})
