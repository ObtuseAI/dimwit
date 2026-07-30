"""Chart vision tests — the falsification of "Dimwit can see a chart".

`verify_chart_roundtrip` is the load-bearing test: render a series whose values are known, read the pixels back,
and require sub-pixel agreement on all four OHLC fields plus exact direction agreement. If the reader were
guessing, this fails immediately.

The rest of the file is about refusing to guess: no geometry, a mismatched image, or candles too narrow to
separate body from wick must all return BLOCKED, and a foreign screenshot must never produce a price.
"""
from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image

from dimwit.market import bars, chart, chart_vision as vision
from dimwit.market.selfaudit import synthetic_series


@pytest.fixture(scope="module")
def series() -> dict:
    return bars.normalize_series(synthetic_series(bar_count=400))


def test_roundtrip_recovers_every_bar_within_a_pixel(series):
    verdict = vision.verify_chart_roundtrip(series, max_bars=120)
    assert verdict["verdict"] == "PASS"
    assert verdict["coverage"] == 1.0
    assert verdict["direction_mismatches"] == 0
    assert verdict["worst_error_px"] <= 1.0
    for field, stats in verdict["per_field_error"].items():
        assert stats["max_px"] <= 1.0, f"{field} recovery worse than a pixel"


def test_roundtrip_passes_at_several_window_sizes_and_themes(series):
    for max_bars in (40, 80, 150):
        for theme in chart.THEMES:
            verdict = vision.verify_chart_roundtrip(series, max_bars=max_bars, theme=theme)
            assert verdict["verdict"] == "PASS", f"{theme}@{max_bars}: {verdict.get('reason')}"


def test_roundtrip_disables_overlays_and_says_so(series):
    verdict = vision.verify_chart_roundtrip(
        series, max_bars=80, overlays={"sma20": [1.0] * 400}, markers=[{"index": 5, "direction": 1}]
    )
    assert verdict["overlays_disabled_for_verification"] is True
    assert verdict["verdict"] == "PASS"


def test_read_recovers_high_low_ordering_and_direction(series):
    render = chart.render_chart_png(series, max_bars=60)
    read = vision.read_chart(render["geometry"], png_base64=render["png_base64"])
    assert read["status"] == "OK"
    assert read["bars_read"] == render["geometry"]["bars_rendered"]
    assert read["price_scale"] == "KNOWN_FROM_GEOMETRY"
    window = series["bars"][render["geometry"]["window_start_index"] :]
    for source, recovered in zip(window, read["bars"], strict=True):
        assert recovered["high"] >= max(recovered["open"], recovered["close"]) - 1e-6
        assert recovered["low"] <= min(recovered["open"], recovered["close"]) + 1e-6
        assert (recovered["direction"] > 0) == (source["close"] >= source["open"])


def test_read_blocks_when_bodies_are_too_narrow_to_separate(series):
    # a tiny canvas forces slot_width == 3, i.e. body_width == 1: wick and body share one column
    geometry = chart.chart_geometry(series, width=420, height=300, max_bars=110)
    assert geometry["body_width"] < vision.MIN_READABLE_BODY_WIDTH
    render = chart.render_chart_png(series, width=420, height=300, max_bars=110)
    read = vision.read_chart(geometry, png_base64=render["png_base64"])
    assert read["status"] == "BLOCKED"
    assert "body_width" in read["reason"]
    assert read["bars"] == []


def test_read_blocks_on_an_image_that_does_not_match_the_geometry(series):
    render = chart.render_chart_png(series, max_bars=60)
    other = chart.render_chart_png(series, width=900, height=500, max_bars=60)
    read = vision.read_chart(render["geometry"], png_base64=other["png_base64"])
    assert read["status"] == "BLOCKED"
    assert "does not match geometry" in read["reason"]


def test_read_requires_real_geometry(series):
    render = chart.render_chart_png(series, max_bars=60)
    with pytest.raises(vision.ChartVisionError, match="market-chart-geometry"):
        vision.read_chart({"schema": "made.up.v1"}, png_base64=render["png_base64"])


def test_read_requires_exactly_one_image_source(series):
    geometry = chart.chart_geometry(series, max_bars=60)
    with pytest.raises(vision.ChartVisionError, match="exactly one"):
        vision.read_chart(geometry)


def test_read_blocks_on_a_blank_image_of_the_right_size(series):
    geometry = chart.chart_geometry(series, max_bars=60)
    blank = Image.new("RGB", (geometry["width"], geometry["height"]), (0, 0, 0))
    buffer = io.BytesIO()
    blank.save(buffer, format="PNG")
    read = vision.read_chart(
        geometry, png_base64=base64.b64encode(buffer.getvalue()).decode("ascii")
    )
    assert read["status"] == "BLOCKED"
    assert read["bars_read"] == 0


def test_invalid_base64_is_a_domain_error(series):
    geometry = chart.chart_geometry(series, max_bars=60)
    with pytest.raises(vision.ChartVisionError, match="not valid base64"):
        vision.read_chart(geometry, png_base64="not-an-image!!")


def test_missing_file_is_a_domain_error(series, tmp_path):
    geometry = chart.chart_geometry(series, max_bars=60)
    with pytest.raises(vision.ChartVisionError, match="not found"):
        vision.read_chart(geometry, path=tmp_path / "absent.png")


# --- foreign screenshots ---------------------------------------------------


def test_foreign_read_never_names_a_price(series):
    render = chart.render_chart_png(series, max_bars=120)
    read = vision.describe_chart(png_base64=render["png_base64"])
    assert read["status"] == "OK"
    assert read["price_scale"] == "UNKNOWN"
    forbidden = {"price", "prices", "levels", "support", "resistance", "price_min", "price_max"}
    assert not forbidden & set(read)
    assert read["candidate_status"] == "RESEARCH_INPUT_ONLY"
    assert read["limitations"]


def test_foreign_read_counts_bars_on_every_theme(series):
    """A saturated background (the `tote` theme is pitch green) and hue-matching gridlines must not be read as
    candle mass. This regressed once: the whole panel counted as one enormous up candle."""
    for theme in chart.THEMES:
        render = chart.render_chart_png(series, max_bars=120, theme=theme)
        read = vision.describe_chart(png_base64=render["png_base64"])
        assert read["status"] == "OK", theme
        assert 100 <= read["detected_bar_count"] <= 140, f"{theme}: {read['detected_bar_count']} bars"
        assert 0.1 < read["up_mass_fraction"] < 0.9, f"{theme}: mass {read['up_mass_fraction']}"


def test_foreign_read_separates_the_volume_pane(series):
    render = chart.render_chart_png(series, max_bars=120, theme="dark")
    read = vision.describe_chart(png_base64=render["png_base64"])
    assert read["row_bands_detected"] >= 2
    price_rows = read["price_pane_rows"]
    volume_pane = render["geometry"]["volume_pane"]
    assert price_rows[1] < volume_pane["y0"], "price pane leaked into the volume pane"


def test_foreign_read_blocks_on_an_image_with_no_candle_mass():
    grey = Image.new("RGB", (300, 200), (128, 128, 128))
    buffer = io.BytesIO()
    grey.save(buffer, format="PNG")
    read = vision.describe_chart(png_base64=base64.b64encode(buffer.getvalue()).decode("ascii"))
    assert read["status"] == "BLOCKED"
    assert read["price_scale"] == "UNKNOWN"


def test_pixel_slope_sign_follows_the_rendered_direction():
    """y grows downward in image space, so a rising market must report a NEGATIVE pixel slope."""
    rising = bars.normalize_series(
        {
            "schema": bars.NATIVE_SCHEMA,
            "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
            "symbol": "RISING",
            "asset_class": "equity",
            "timeframe": "1d",
            "as_of": "2030-01-01T00:00:00Z",
            "bars": [
                {
                    "observed_at": f"2024-{1 + index // 28:02d}-{1 + index % 28:02d}T00:00:00Z",
                    "open": 100.0 + index,
                    "high": 101.0 + index,
                    "low": 99.5 + index,
                    "close": 100.8 + index,
                    "volume": 1000.0,
                }
                for index in range(56)
            ],
        }
    )
    render = chart.render_chart_png(rising, max_bars=56)
    read = vision.describe_chart(png_base64=render["png_base64"])
    assert read["pixel_slope_per_column"] < 0
    assert read["pixel_space_drift"] == "RISING"


def test_rule_line_detector_finds_a_full_width_line():
    pixels = np.zeros((40, 200, 3), dtype=np.uint8)
    pixels[20, :, :] = (24, 74, 52)  # a full-width green rule
    pixels[5, 10:14, :] = (38, 208, 124)  # a candle-width green blob
    mask = np.ones(pixels.shape[:2], dtype=bool)
    found = vision._rule_line_colors(pixels, mask)
    assert [24, 74, 52] in found
    assert [38, 208, 124] not in found
