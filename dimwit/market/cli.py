"""`python -m dimwit market <cmd>` — operator surface for the market cell.

Every command prints one JSON document to stdout and returns 0 on an OK/PASS verdict, non-zero on BLOCKED.
That makes each of these usable directly as a shell gate.

  audit                                   run the cell and print the anti-costume manifest (add --deep for the scan)
  indicators   <series.json>              canonical indicator panel at the last bar
  patterns     <series.json>              pattern detections + confirmed market structure
  analyze      <series.json>              full DumbMoney-compatible TA observation
  chart        <series.json> [--svg] [--theme t] [--bars n] [--out name]
                                          render a chart; --out writes under artifacts/market/
  vision       <series.json> [--bars n]   render -> read back -> report recovery error in pixels
  describe     <image.png>                shape-only read of a FOREIGN chart screenshot
  scan         <series.json> [--null]     walk-forward scan with search disclosure (--null adds the control)
  game         <game.json>                realized game-state observation
  gamescan     <games.json>               cross-game rule scan (games.json is a JSON list)
  know         <term|--search q>          knowledge pack lookup
  ledger       [path]                     verify the market evidence ledger

A `series.json` is a `dimwit.market-ohlcv-series.v1` (or DumbMoney synthetic/point-in-time) payload. Pass
`--self` instead of a path to run against the deterministic synthetic fixture.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import bars as bars_mod
from . import chart as chart_mod
from . import chart_vision as vision_mod
from . import evidence as evidence_mod
from . import indicators as ind
from . import knowledge as knowledge_mod
from . import patterns as pat
from . import scan as scan_mod
from . import selfaudit
from . import sports as sports_mod

BLOCKED_VERDICTS = {"BLOCKED", "FAIL"}


def _flag(rest: list[str], name: str, default: Any = None, cast: Any = str) -> Any:
    if name not in rest:
        return default
    index = rest.index(name)
    if index + 1 >= len(rest):
        raise SystemExit(f"{name} requires a value")
    return cast(rest[index + 1])


def _load_series(rest: list[str]) -> dict[str, Any]:
    if "--self" in rest:
        return bars_mod.normalize_series(selfaudit.synthetic_series(bar_count=1000))
    positional = [item for item in rest if not item.startswith("--")]
    if not positional:
        raise SystemExit("a series.json path (or --self) is required")
    payload = json.loads(Path(positional[0]).read_text(encoding="utf-8"))
    return bars_mod.normalize_series(payload)


def _load_json(rest: list[str]) -> Any:
    positional = [item for item in rest if not item.startswith("--")]
    if not positional:
        raise SystemExit("a JSON path is required")
    return json.loads(Path(positional[0]).read_text(encoding="utf-8"))


def _emit(payload: Any, *, blocked: bool = False) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 1 if blocked else 0


def _render_kwargs(rest: list[str], *, default_max_bars: int | None = None) -> dict[str, Any]:
    """Render options from argv.

    `default_max_bars` exists because the vision path needs candles wide enough to separate body from wick:
    rendering every bar of a long series shrinks the body to one pixel and the read correctly BLOCKS. Defaulting
    here (rather than at the call site) keeps `--theme` from silently dropping the bar limit.
    """
    kwargs: dict[str, Any] = {}
    theme = _flag(rest, "--theme")
    if theme:
        kwargs["theme"] = theme
    max_bars = _flag(rest, "--bars", cast=int)
    if max_bars:
        kwargs["max_bars"] = max_bars
    elif default_max_bars is not None:
        kwargs["max_bars"] = default_max_bars
    return kwargs


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, rest = argv[0], list(argv[1:])

    if cmd == "audit":
        audit = selfaudit.audit_market_cell(deep="--deep" in rest)
        return _emit(audit, blocked=not audit["costume_clean"])

    if cmd == "indicators":
        series = _load_series(rest)
        return _emit(
            {
                "symbol": series["symbol"],
                "timeframe": series["timeframe"],
                "as_of": series["as_of"],
                "bar_count": series["bar_count"],
                "indicators": ind.snapshot(series),
            }
        )

    if cmd == "patterns":
        series = _load_series(rest)
        detections = pat.detect_patterns(series)
        return _emit(
            {
                "counts_by_pattern": detections["counts_by_pattern"],
                "detection_count": detections["detection_count"],
                "pattern_family_size": detections["pattern_family_size"],
                "confirmation_lag_bars": detections["confirmation_lag_bars"],
                "market_structure": pat.market_structure(series),
                "support_resistance": pat.support_resistance(series),
            }
        )

    if cmd == "analyze":
        series = _load_series(rest)
        kwargs = _render_kwargs(rest, default_max_bars=120)
        render = chart_mod.render_chart_png(series, **kwargs)
        roundtrip = vision_mod.verify_chart_roundtrip(series, **kwargs)
        observation = evidence_mod.export_dumbmoney_observation(
            series, chart_render=render, roundtrip=roundtrip
        )
        observation.pop("indicators_full", None)
        return _emit(observation, blocked=roundtrip["verdict"] in BLOCKED_VERDICTS)

    if cmd == "chart":
        series = _load_series(rest)
        kwargs = _render_kwargs(rest)
        out = _flag(rest, "--out")
        fmt = "svg" if "--svg" in rest else "png"
        if out:
            result = chart_mod.export_chart(series, out, fmt=fmt, **kwargs)
        else:
            result = (
                chart_mod.render_chart_svg(series, **kwargs)
                if fmt == "svg"
                else chart_mod.render_chart_png(series, **kwargs)
            )
        result.pop("png_base64", None)
        result.pop("svg", None)
        return _emit(result)

    if cmd == "vision":
        series = _load_series(rest)
        verdict = vision_mod.verify_chart_roundtrip(
            series, **_render_kwargs(rest, default_max_bars=120)
        )
        return _emit(verdict, blocked=verdict["verdict"] in BLOCKED_VERDICTS)

    if cmd == "describe":
        positional = [item for item in rest if not item.startswith("--")]
        if not positional:
            raise SystemExit("an image path is required")
        read = vision_mod.describe_chart(path=positional[0])
        return _emit(read, blocked=read["status"] in BLOCKED_VERDICTS)

    if cmd == "scan":
        series = _load_series(rest)
        config = scan_mod.ScanConfig(
            warmup_bars=_flag(rest, "--warmup", 200, int),
            training_bars=_flag(rest, "--training", 300, int),
            embargo_bars=_flag(rest, "--embargo", 10, int),
            holdout_bars=_flag(rest, "--holdout", 400, int),
            horizon_bars=_flag(rest, "--horizon", 5, int),
            round_trip_cost_bps=_flag(rest, "--cost", 10.0, float),
        )
        result = scan_mod.scan_rules(series, config=config)
        payload: dict[str, Any] = {
            "summary": scan_mod.scan_summary(result),
            "split": result["split"],
            "search_disclosure": result["search_disclosure"],
            "observation_accounting": result["observation_accounting"],
            "digest": result["digest"],
        }
        if "--null" in rest:
            payload["placebo_control"] = scan_mod.placebo_control(series, config=config)
        return _emit(payload)

    if cmd == "game":
        return _emit(sports_mod.analyze_game_series(_load_json(rest)))

    if cmd == "gamescan":
        games = _load_json(rest)
        if not isinstance(games, list):
            raise SystemExit("gamescan expects a JSON list of game series")
        result = sports_mod.scan_sports_rules(games)
        result.pop("rules", None)
        return _emit(result)

    if cmd == "know":
        query = _flag(rest, "--search")
        if query:
            return _emit({"query": query, "hits": knowledge_mod.search(query)})
        positional = [item for item in rest if not item.startswith("--")]
        if not positional:
            return _emit(knowledge_mod.summary())
        return _emit(knowledge_mod.citation(positional[0]))

    if cmd == "ledger":
        positional = [item for item in rest if not item.startswith("--")]
        ledger = evidence_mod.MarketEvidenceLedger(positional[0] if positional else None)
        verification = ledger.verify()
        return _emit(
            {"summary": ledger.summary(), "verification": verification},
            blocked=not verification["ok"],
        )

    print(__doc__)
    return 2
