"""Dimwit MARKET lane — the executed technical-analysis / chart-vision surface.

Why this package exists
-----------------------
Dimwit's premise is that a claim is worth exactly its evidence, and that premise is not specific to art. A
backtest is the purest counter-example: it produces a number that looks like proof, is trivial to generate, and
is wrong in ways no exit code reveals — an indicator computed over the whole series then indexed historically, a
pattern dated to where it *is* rather than to when it was *knowable*, a rule credited for a market it merely sat
in, or a t-statistic quoted without the search space behind it.

This package applies the studio's law to that domain. `selfaudit.audit_market_cell()` runs the lane and reports
an honest executed/not-executed manifest, so the surface cannot quietly become an impressive-looking module that
never actually runs.

Doctrine (inherited from the studio side, unchanged)
---------------------------------------------------
* **Observations, never forecasts.** Nothing here emits a probability or an expected return. Every result
  carries `candidate_status` and `forecast_probability: None`. Edge claims belong to a downstream evidence
  court, after held-out evidence.
* **Fail-closed.** Missing/ambiguous evidence returns a BLOCKED verdict, never a fabricated PASS.
* **No lookahead, ever.** Indicators are prefix-stable: the value at bar *i* is identical whether computed on
  `bars[:i+1]` or on the whole series. `tests/test_market_indicators.py` proves this per indicator.
* **No network, no credentials, no broker.** Pure functions over caller-supplied bars.
* **Disclose the search.** `scan` reports the rule-family size it searched and applies Bonferroni +
  Benjamini-Hochberg, because a statistic that does not survive its own search space is not evidence.

Deps: stdlib + numpy + Pillow (already vendored for the perception stack).
"""
from __future__ import annotations

from .bars import (
    BarSeriesError,
    normalize_series,
    point_in_time_prefix,
    resample,
    series_digest,
)
from .chart import chart_geometry, render_chart_png, render_chart_svg
from .chart_vision import describe_chart, read_chart, verify_chart_roundtrip
from .evidence import (
    MarketEvidenceLedger,
    export_observation,
    implementation_digest,
)
from .indicators import INDICATORS, indicator_series, snapshot
from .knowledge import describe as knowledge_describe
from .knowledge import search as knowledge_search
from .knowledge import terms as knowledge_terms
from .patterns import PATTERNS, detect_patterns, market_structure, swing_pivots
from .scan import RULES, ScanConfig, placebo_control, scan_rules
from .selfaudit import audit_market_cell
from .sports import analyze_game_series, render_game_chart, scan_sports_rules

__all__ = [
    "INDICATORS",
    "PATTERNS",
    "RULES",
    "BarSeriesError",
    "MarketEvidenceLedger",
    "ScanConfig",
    "analyze_game_series",
    "audit_market_cell",
    "chart_geometry",
    "describe_chart",
    "detect_patterns",
    "export_observation",
    "implementation_digest",
    "indicator_series",
    "knowledge_describe",
    "knowledge_search",
    "knowledge_terms",
    "market_structure",
    "normalize_series",
    "point_in_time_prefix",
    "read_chart",
    "render_chart_png",
    "render_chart_svg",
    "render_game_chart",
    "resample",
    "placebo_control",
    "scan_rules",
    "scan_sports_rules",
    "series_digest",
    "snapshot",
    "swing_pivots",
    "verify_chart_roundtrip",
]
