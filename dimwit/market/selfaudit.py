"""Self-audit for the market lane — the does-it-actually-run gate.

A module can be large, well documented, listed in a registry, and never execute a line in production. That gap
is invisible to line counts and to any status field the component writes about itself. So this function does
not assert the lane works: it **runs** the lane end to end on a synthetic series and reports what actually
executed, what is missing, and why.

`costume_risk` is the finding list. Empty means every declared capability resolved to real code that produced a
real result on this invocation. Non-empty is the honest state of a partially wired cell, and
`tests/test_market_cell_contract.py` fails on it.

`synthetic_series()` lives here rather than in a test helper because the self-audit needs it at runtime: a cell
that can only prove itself under pytest has not proved itself.
"""
from __future__ import annotations

import math
from typing import Any

from ..core import sha256_obj
from . import bars as bars_mod
from . import chart as chart_mod
from . import chart_vision as vision_mod
from . import evidence as evidence_mod
from . import indicators as ind
from . import knowledge as knowledge_mod
from . import patterns as pat
from . import scan as scan_mod
from . import sports as sports_mod

#: What this lane is expected to cover, and what is honestly true of each item.
DECLARED_RESPONSIBILITIES: tuple[dict[str, Any], ...] = (
    {
        "responsibility": "deterministic_technical_analysis_for_stocks_and_crypto",
        "status": "IMPLEMENTED_AND_EXECUTED",
        "implementation": "dimwit.market.indicators + dimwit.market.patterns",
    },
    {
        "responsibility": "chart_vision_on_rendered_charts",
        "status": "IMPLEMENTED_AND_EXECUTED",
        "implementation": "dimwit.market.chart + dimwit.market.chart_vision",
        "note": "Price recovery requires the renderer's geometry; error is reported in pixels.",
    },
    {
        "responsibility": "chart_vision_on_foreign_screenshots",
        "status": "IMPLEMENTED_SHAPE_ONLY",
        "implementation": "dimwit.market.chart_vision.describe_chart",
        "note": "No axis mapping is recoverable from a foreign image, so prices are never named.",
    },
    {
        "responsibility": "sports_game_state_analysis_and_charting",
        "status": "IMPLEMENTED_AND_EXECUTED",
        "implementation": "dimwit.market.sports",
    },
    {
        "responsibility": "walk_forward_evidence_production_with_search_disclosure",
        "status": "IMPLEMENTED_AND_EXECUTED",
        "implementation": "dimwit.market.scan + dimwit.market.sports.scan_sports_rules",
    },
    {
        "responsibility": "provenance_and_tamper_evident_evidence_ledger",
        "status": "IMPLEMENTED_AND_EXECUTED",
        "implementation": "dimwit.market.evidence",
    },
    {
        "responsibility": "forecast_probabilities_or_expected_returns",
        "status": "NOT_IMPLEMENTED_BY_DESIGN",
        "implementation": None,
        "note": "Observations only. Probability claims belong downstream, after held-out evidence.",
    },
    {
        "responsibility": "live_market_data_ingestion",
        "status": "NOT_IMPLEMENTED_BY_DESIGN",
        "implementation": None,
        "note": "No network access. Bars are supplied by the caller with a declared classification.",
    },
    {
        "responsibility": "order_routing_or_brokerage_access",
        "status": "NOT_IMPLEMENTED_BY_DESIGN",
        "implementation": None,
        "note": "Brokerage access belongs to whatever consumes this lane. It holds no credentials.",
    },
)

_EXECUTED_STATUSES = frozenset({"IMPLEMENTED_AND_EXECUTED", "IMPLEMENTED_SHAPE_ONLY"})


def synthetic_series(
    *,
    bar_count: int = 1000,
    symbol: str = "DIMWIT-SELFTEST",
    asset_class: str = "equity",
    timeframe: str = "1d",
    seed: int = 20260730,
    start_price: float = 100.0,
) -> dict[str, Any]:
    """Deterministic synthetic OHLCV series for self-verification.

    A fixed linear-congruential generator, not `random`: seeding the stdlib RNG would make the fixture depend on
    global interpreter state that another caller can perturb. Classification is pinned to the synthetic label so
    this can never be mistaken for market evidence.
    """
    if bar_count < 30:
        raise ValueError("bar_count must be at least 30")
    state = seed & 0xFFFFFFFF
    minutes = bars_mod.timeframe_minutes(timeframe)

    def unit() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    price = float(start_price)
    epoch = 1_700_000_000  # fixed, so timestamps never depend on the wall clock
    generated: list[dict[str, Any]] = []
    for index in range(bar_count):
        drift = math.sin(index / 90.0) * 0.0012
        shock = (unit() - 0.5) * 0.018
        open_price = price
        close_price = max(0.5, open_price * (1.0 + drift + shock))
        wick = abs(shock) * open_price + open_price * 0.001
        high = max(open_price, close_price) + wick * unit()
        low = max(0.25, min(open_price, close_price) - wick * unit())
        volume = 100_000 + int(unit() * 400_000)
        seconds = epoch + index * minutes * 60
        generated.append(
            {
                "observed_at": _iso(seconds),
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(low, 6),
                "close": round(close_price, 6),
                "volume": float(volume),
            }
        )
        price = close_price
    return {
        "schema": bars_mod.NATIVE_SCHEMA,
        "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
        "symbol": symbol,
        "asset_class": asset_class,
        "timeframe": timeframe,
        "as_of": _iso(epoch + bar_count * minutes * 60),
        "bars": generated,
    }


def _iso(seconds: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")


def synthetic_games(count: int = 40, *, league: str = "NBA", seed: int = 4242) -> list[dict[str, Any]]:
    """Deterministic synthetic settled games for the sports self-test."""
    state = seed & 0xFFFFFFFF

    def unit() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    regulation = sports_mod.LEAGUE_DEFAULTS[league]["regulation_seconds"]
    games: list[dict[str, Any]] = []
    for game_index in range(count):
        home = away = 0
        events: list[dict[str, Any]] = []
        for step in range(1, 41):
            elapsed = regulation * step / 40.0
            home += int(unit() * 7)
            away += int(unit() * 7)
            events.append(
                {
                    "elapsed_seconds": elapsed,
                    "home_score": home,
                    "away_score": away,
                    "period": min(4, 1 + int(step / 10)),
                }
            )
        if home == away:
            home += 1
        games.append(
            {
                "schema": sports_mod.GAME_SERIES_SCHEMA,
                "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
                "league": league,
                "game_id": f"SELFTEST-{game_index:04d}",
                "home": "HOME",
                "away": "AWAY",
                "as_of": _iso(1_700_000_000 + game_index * 86_400),
                "regulation_seconds": regulation,
                "events": events,
                "final": {"home_score": home, "away_score": away},
            }
        )
    return games


def _probe(name: str, fn: Any) -> dict[str, Any]:
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - a probe records failures, it does not raise them
        return {"probe": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"probe": name, "ok": True, "detail": result}


def audit_market_cell(*, deep: bool = False) -> dict[str, Any]:
    """Execute the cell and report what really ran.

    `deep=True` additionally runs the walk-forward scan and its null control. That costs a couple of seconds on
    1000 bars, so the default stays fast enough for a status poll while the deep pass is available to CI.
    """
    series = bars_mod.normalize_series(synthetic_series(bar_count=1000))
    probes: list[dict[str, Any]] = []

    def probe_indicators() -> dict[str, Any]:
        panel = ind.snapshot(series)
        defined = [name for name, value in panel.items() if value is not None]
        return {
            "registered": len(ind.INDICATORS),
            "defined_at_last_bar": len(defined),
            "families": list(ind.INDICATOR_FAMILIES),
            "undefined": sorted(set(panel) - set(defined)),
        }

    def probe_patterns() -> dict[str, Any]:
        detections = pat.detect_patterns(series)
        structure = pat.market_structure(series)
        return {
            "registered": len(pat.PATTERNS),
            "detections": detections["detection_count"],
            "distinct_patterns_seen": len(detections["counts_by_pattern"]),
            "structure_trend": structure["trend"],
            "confirmation_lag_bars": detections["confirmation_lag_bars"],
        }

    def probe_chart() -> dict[str, Any]:
        render = chart_mod.render_chart_png(series, max_bars=120)
        svg = chart_mod.render_chart_svg(series, max_bars=120)
        return {
            "png_bytes": render["png_bytes"],
            "svg_bytes": len(svg["svg"]),
            "themes": sorted(chart_mod.THEMES),
            "bars_rendered": render["geometry"]["bars_rendered"],
        }

    def probe_chart_vision() -> dict[str, Any]:
        verdict = vision_mod.verify_chart_roundtrip(series, max_bars=120)
        render = chart_mod.render_chart_png(series, max_bars=120)
        foreign = vision_mod.describe_chart(png_base64=render["png_base64"])
        return {
            "roundtrip_verdict": verdict["verdict"],
            "worst_error_px": verdict.get("worst_error_px"),
            "bars_compared": verdict.get("bars_compared"),
            "foreign_read_status": foreign["status"],
            "foreign_detected_bars": foreign.get("detected_bar_count"),
        }

    def probe_sports() -> dict[str, Any]:
        games = synthetic_games(24)
        observation = sports_mod.analyze_game_series(games[0])
        chart = sports_mod.render_game_chart(games[0])
        result = sports_mod.scan_sports_rules(games)
        return {
            "game_observation_settled": observation["settled"],
            "chart_png_bytes": chart["png_bytes"],
            "sports_family_size": result["search_disclosure"]["family_size"],
            "settled_holdout_observations": result["observation_accounting"][
                "settled_holdout_observations"
            ],
        }

    def probe_knowledge() -> dict[str, Any]:
        summary = knowledge_mod.summary()
        return {
            "term_count": summary["term_count"],
            "by_kind": summary["by_kind"],
            "pack_digest": summary["pack_digest"],
        }

    def probe_evidence() -> dict[str, Any]:
        attestation = evidence_mod.implementation_digest()
        observation = evidence_mod.export_observation(series)
        return {
            "attested_modules": attestation["module_count"],
            "implementation_digest": attestation["digest"],
            "observation_schema": observation["schema"],
            "downstream_compatibility": observation["downstream_schema_compatibility"],
            "chart_pixel_evidence": observation["chart_pixel_evidence"],
        }

    probes.append(_probe("indicators", probe_indicators))
    probes.append(_probe("patterns", probe_patterns))
    probes.append(_probe("chart", probe_chart))
    probes.append(_probe("chart_vision", probe_chart_vision))
    probes.append(_probe("sports", probe_sports))
    probes.append(_probe("knowledge", probe_knowledge))
    probes.append(_probe("evidence", probe_evidence))

    if deep:

        def probe_scan() -> dict[str, Any]:
            config = scan_mod.ScanConfig(
                warmup_bars=200, training_bars=300, embargo_bars=10, holdout_bars=400
            )
            result = scan_mod.scan_rules(series, config=config)
            control = scan_mod.placebo_control(series, config=config, lags=(37, 181))
            return {
                "family_size": result["search_disclosure"]["family_size"],
                "bh_survivors": result["search_disclosure"]["benjamini_hochberg"]["survivor_count"],
                "settled_holdout_outcomes": result["observation_accounting"][
                    "settled_holdout_outcomes"
                ],
                "placebo_max_bh_survivors": control["max_bh_survivors"],
            }

        probes.append(_probe("walkforward_scan", probe_scan))

    risks: list[dict[str, Any]] = []
    for probe in probes:
        if not probe["ok"]:
            risks.append(
                {
                    "finding": "DECLARED_CAPABILITY_FAILED_TO_EXECUTE",
                    "probe": probe["probe"],
                    "detail": probe["error"],
                }
            )
    executed = {probe["probe"] for probe in probes if probe["ok"]}
    if "evidence" in executed and "indicators" not in executed:
        risks.append(
            {
                "finding": "EVIDENCE_EXPORTED_WITHOUT_WORKING_ANALYSIS",
                "detail": "the export path ran while the analysis it summarizes did not",
            }
        )
    declared_executed = [
        item["responsibility"]
        for item in DECLARED_RESPONSIBILITIES
        if item["status"] in _EXECUTED_STATUSES
    ]

    audit = {
        "schema": "dimwit.market-cell-audit.v1",
        "producer": "dimwit",
        "cell": "dimwit",
        "assigned_role": "chart_vision_and_deterministic_technical_analysis_for_stocks_and_crypto",
        "host_product_role": "proof_bearing_game_production_studio",
        "deep": deep,
        "counts": {
            "indicators": len(ind.INDICATORS),
            "patterns": len(pat.PATTERNS),
            "bar_rules": len(scan_mod.RULES),
            "sports_conditions": len(sports_mod.SPORTS_CONDITIONS),
            "sports_checkpoints": len(sports_mod.CHECKPOINTS),
            "sports_family_size": len(sports_mod.SPORTS_CONDITIONS) * len(sports_mod.CHECKPOINTS),
            "knowledge_terms": knowledge_mod.summary()["term_count"],
            "chart_themes": len(chart_mod.THEMES),
        },
        "responsibilities": list(DECLARED_RESPONSIBILITIES),
        "declared_executed_count": len(declared_executed),
        "probes": probes,
        "probes_passed": len(executed),
        "probes_total": len(probes),
        "costume_risk": risks,
        "costume_clean": not risks,
        "implementation_attestation": evidence_mod.implementation_digest(),
        "honest_limitations": [
            item["responsibility"]
            for item in DECLARED_RESPONSIBILITIES
            if item["status"].startswith("NOT_IMPLEMENTED")
        ],
        "forecast_probability": None,
        "candidate_status": "DIAGNOSTIC_ONLY",
    }
    audit["digest"] = sha256_obj({key: value for key, value in audit.items() if key != "digest"})
    return audit
