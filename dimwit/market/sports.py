"""Sports game-state analysis, charting, and a cross-game rule scanner.

Why sports gets its own scanner instead of reusing `scan.py`: **independence**. Overlapping fixed-horizon bar
windows share information, so 500 bar outcomes are worth far fewer than 500 independent draws. Distinct games
do not overlap — one game contributes exactly one settled outcome per rule. Sports is therefore the cheapest
source of genuinely independent settled observations in the whole system, and this module is built to harvest
them without the overlap deflation that bar-based evidence needs.

What this module refuses to do
------------------------------
* **No win-probability model.** If the caller supplies a `win_prob_home` timeline, it is analyzed. If not, the
  result says `NOT_PROVIDED`. Fitting an in-house WP curve here and reporting it as an observation would be
  exactly the unvalidated forecast the cell doctrine forbids.
* **No edge claims.** `scan_sports_rules` benchmarks a rule's hit rate against a fair coin, and stamps
  `benchmark: FAIR_COIN_NOT_MARKET_PRICE`. Beating 50% is not edge; beating the price is, and no prices are
  present here.
* **No unsettled outcomes.** A game without a `final` score is analyzable but contributes zero observations.
"""
from __future__ import annotations

import base64
import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image, ImageDraw

from ..core import sha256_obj, sha256_text
from . import chart as chart_mod
from . import indicators as ind

GAME_SERIES_SCHEMA = "dimwit.sports-game-series.v1"

#: classification -> may it back a point-in-time claim
CLASSIFICATIONS: dict[str, bool] = {
    "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE": False,
    "IMPORTED_PUBLIC_SPORTS_DATA_RETROSPECTIVE_RESEARCH": False,
    "POINT_IN_TIME_CAPTURED_SPORTS_TIMELINE": True,
}

#: league -> regulation seconds + the margin at which late-game play is conventionally decided.
LEAGUE_DEFAULTS: dict[str, dict[str, Any]] = {
    "NBA": {"regulation_seconds": 2880, "garbage_margin": 20, "periods": 4},
    "WNBA": {"regulation_seconds": 2400, "garbage_margin": 18, "periods": 4},
    "NCAAMB": {"regulation_seconds": 2400, "garbage_margin": 18, "periods": 2},
    "NFL": {"regulation_seconds": 3600, "garbage_margin": 17, "periods": 4},
    "NCAAF": {"regulation_seconds": 3600, "garbage_margin": 21, "periods": 4},
    "NHL": {"regulation_seconds": 3600, "garbage_margin": 3, "periods": 3},
    "MLB": {"regulation_seconds": 0, "garbage_margin": 6, "periods": 9},
}

GARBAGE_TIME_REMAINING_FRACTION = 0.125


class SportsSeriesError(ValueError):
    """Raised when a game timeline cannot be trusted without weakening its contract."""


def _league_defaults(league: str) -> dict[str, Any]:
    return LEAGUE_DEFAULTS.get(league.upper(), {"regulation_seconds": 0, "garbage_margin": 0, "periods": 0})


def normalize_game_series(series: Mapping[str, Any]) -> dict[str, Any]:
    """Validate + canonicalize a game timeline.

    Rejects non-monotonic clocks, decreasing scores (scores only go up), and any point-in-time claim a
    retrospective classification cannot support.
    """
    if not isinstance(series, Mapping):
        raise SportsSeriesError("series must be an object")
    if series.get("schema") != GAME_SERIES_SCHEMA:
        raise SportsSeriesError(f"series schema must be {GAME_SERIES_SCHEMA}")
    classification = series.get("classification")
    if classification not in CLASSIFICATIONS:
        raise SportsSeriesError(f"unknown classification {classification!r}")
    league = str(series.get("league", "")).strip().upper()
    if not league:
        raise SportsSeriesError("league is required")
    game_id = str(series.get("game_id", "")).strip()
    if not game_id:
        raise SportsSeriesError("game_id is required")
    events = series.get("events")
    if not isinstance(events, list) or len(events) < 2:
        raise SportsSeriesError("events must be a list of at least 2 entries")

    defaults = _league_defaults(league)
    regulation = int(series.get("regulation_seconds") or defaults["regulation_seconds"] or 0)
    if regulation <= 0:
        raise SportsSeriesError(
            f"regulation_seconds is required for league {league} (no default is known)"
        )

    normalized_events: list[dict[str, Any]] = []
    previous_elapsed = -1.0
    previous_home = previous_away = -1
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise SportsSeriesError(f"event[{index}] must be an object")
        elapsed = float(raw.get("elapsed_seconds", -1))
        if elapsed < 0:
            raise SportsSeriesError(f"event[{index}].elapsed_seconds must be >= 0")
        if elapsed <= previous_elapsed:
            raise SportsSeriesError(f"event[{index}] clock is not strictly increasing")
        home_score = int(raw.get("home_score", -1))
        away_score = int(raw.get("away_score", -1))
        if home_score < 0 or away_score < 0:
            raise SportsSeriesError(f"event[{index}] scores must be >= 0")
        if home_score < previous_home or away_score < previous_away:
            raise SportsSeriesError(f"event[{index}] score decreased; scores are monotonic")
        win_prob = raw.get("win_prob_home")
        if win_prob is not None:
            win_prob = float(win_prob)
            if not 0.0 <= win_prob <= 1.0:
                raise SportsSeriesError(f"event[{index}].win_prob_home must be in [0, 1]")
        normalized_events.append(
            {
                "elapsed_seconds": elapsed,
                "home_score": home_score,
                "away_score": away_score,
                "margin": home_score - away_score,
                "period": raw.get("period"),
                "win_prob_home": win_prob,
                "observed_at": raw.get("observed_at"),
            }
        )
        previous_elapsed, previous_home, previous_away = elapsed, home_score, away_score

    final = series.get("final")
    settled = False
    if final is not None:
        if not isinstance(final, Mapping):
            raise SportsSeriesError("final must be an object")
        final_home = int(final.get("home_score", -1))
        final_away = int(final.get("away_score", -1))
        if final_home < 0 or final_away < 0:
            raise SportsSeriesError("final scores must be >= 0")
        last = normalized_events[-1]
        if final_home < last["home_score"] or final_away < last["away_score"]:
            raise SportsSeriesError("final score is below the last timeline score")
        final = {"home_score": final_home, "away_score": final_away}
        settled = True

    claim = bool(series.get("point_in_time_claim", False))
    if claim and not CLASSIFICATIONS[classification]:
        raise SportsSeriesError(
            f"classification {classification} cannot support point_in_time_claim=True"
        )

    normalized = {
        "schema": GAME_SERIES_SCHEMA,
        "classification": classification,
        "league": league,
        "game_id": game_id,
        "home": str(series.get("home", "")).strip() or "HOME",
        "away": str(series.get("away", "")).strip() or "AWAY",
        "as_of": series.get("as_of"),
        "regulation_seconds": regulation,
        "garbage_margin": int(series.get("garbage_margin") or defaults["garbage_margin"] or 0),
        "point_in_time_claim": claim,
        "event_count": len(normalized_events),
        "events": normalized_events,
        "final": final,
        "settled": settled,
        "win_probability_supplied": all(
            event["win_prob_home"] is not None for event in normalized_events
        ),
    }
    normalized["digest"] = sha256_obj(
        {
            "game_id": game_id,
            "league": league,
            "classification": classification,
            "events": [
                [event["elapsed_seconds"], event["home_score"], event["away_score"], event["win_prob_home"]]
                for event in normalized_events
            ],
            "final": final,
        }
    )
    return normalized


def _runs(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Maximal stretches in which only one side scored."""
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for previous, event in zip(events, events[1:], strict=False):
        home_delta = event["home_score"] - previous["home_score"]
        away_delta = event["away_score"] - previous["away_score"]
        if home_delta == away_delta == 0:
            continue
        side = "home" if home_delta > away_delta else "away" if away_delta > home_delta else None
        points = max(home_delta, away_delta)
        if side is None:
            current = None
            continue
        if current and current["side"] == side:
            current["points"] += points
            current["end_elapsed"] = event["elapsed_seconds"]
        else:
            current = {
                "side": side,
                "points": points,
                "start_elapsed": previous["elapsed_seconds"],
                "end_elapsed": event["elapsed_seconds"],
            }
            runs.append(current)
    for run in runs:
        run["duration_seconds"] = run["end_elapsed"] - run["start_elapsed"]
    return runs


def analyze_game_series(series: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic description of realized game state. No forecast, ever."""
    normalized = normalize_game_series(series)
    events = normalized["events"]
    margins = [float(event["margin"]) for event in events]
    regulation = int(normalized["regulation_seconds"])

    lead_changes = 0
    ties = 0
    previous_sign = 0
    for margin in margins:
        sign = 1 if margin > 0 else -1 if margin < 0 else 0
        if sign == 0:
            ties += 1
        elif previous_sign and sign != previous_sign:
            lead_changes += 1
        if sign:
            previous_sign = sign

    time_leading_home = 0.0
    time_leading_away = 0.0
    for previous, event in zip(events, events[1:], strict=False):
        span = event["elapsed_seconds"] - previous["elapsed_seconds"]
        if previous["margin"] > 0:
            time_leading_home += span
        elif previous["margin"] < 0:
            time_leading_away += span
    total_span = max(1e-9, events[-1]["elapsed_seconds"] - events[0]["elapsed_seconds"])

    deltas = [margins[i] - margins[i - 1] for i in range(1, len(margins))]
    momentum = ind.ema(deltas, min(10, max(2, len(deltas) // 4))) if len(deltas) >= 2 else []
    runs = _runs(events)
    longest_run = max(runs, key=lambda run: run["points"], default=None)

    garbage_from: float | None = None
    if normalized["garbage_margin"] > 0:
        threshold_elapsed = regulation * (1.0 - GARBAGE_TIME_REMAINING_FRACTION)
        for event in events:
            if (
                event["elapsed_seconds"] >= threshold_elapsed
                and abs(event["margin"]) >= normalized["garbage_margin"]
            ):
                garbage_from = event["elapsed_seconds"]
                break

    win_prob_block: dict[str, Any] = {"status": "NOT_PROVIDED"}
    if normalized["win_probability_supplied"]:
        probabilities = [float(event["win_prob_home"]) for event in events]
        swings = [abs(probabilities[i] - probabilities[i - 1]) for i in range(1, len(probabilities))]
        leverage: list[dict[str, Any]] = []
        for index in range(1, len(events)):
            points = abs(
                (events[index]["home_score"] - events[index - 1]["home_score"])
                - (events[index]["away_score"] - events[index - 1]["away_score"])
            )
            leverage.append(
                {
                    "elapsed_seconds": events[index]["elapsed_seconds"],
                    "win_prob_delta": round(swings[index - 1], 6),
                    "margin_delta": points,
                    "leverage_per_point": round(swings[index - 1] / max(1, points), 6),
                }
            )
        top_leverage = sorted(leverage, key=lambda item: -item["leverage_per_point"])[:5]
        win_prob_block = {
            "status": "SUPPLIED_BY_CALLER",
            "source_disclosure": "Dimwit does not model win probability; these are the caller's numbers.",
            "first": round(probabilities[0], 6),
            "last": round(probabilities[-1], 6),
            "min": round(min(probabilities), 6),
            "max": round(max(probabilities), 6),
            "max_single_event_swing": round(max(swings), 6) if swings else 0.0,
            "mean_abs_swing": round(sum(swings) / len(swings), 6) if swings else 0.0,
            "crossings_of_50": sum(
                1
                for i in range(1, len(probabilities))
                if (probabilities[i - 1] - 0.5) * (probabilities[i] - 0.5) < 0
            ),
            "top_leverage_events": top_leverage,
        }

    observation = {
        "schema": "dimwit.sports-game-observation.v1",
        "producer": "dimwit",
        "league": normalized["league"],
        "game_id": normalized["game_id"],
        "home": normalized["home"],
        "away": normalized["away"],
        "as_of": normalized["as_of"],
        "classification": normalized["classification"],
        "point_in_time_claim": normalized["point_in_time_claim"],
        "series_digest": normalized["digest"],
        "event_count": normalized["event_count"],
        "elapsed_covered_seconds": round(events[-1]["elapsed_seconds"], 3),
        "regulation_seconds": regulation,
        "state": {
            "final_margin_in_timeline": margins[-1],
            "largest_home_lead": max(margins),
            "largest_away_lead": -min(margins),
            "lead_changes": lead_changes,
            "tied_events": ties,
            "time_leading_home_fraction": round(time_leading_home / total_span, 6),
            "time_leading_away_fraction": round(time_leading_away / total_span, 6),
            "margin_volatility": round(
                (ind.rolling_stdev(margins, min(10, len(margins)))[-1] or 0.0), 6
            ),
            "momentum_ema_last": None if not momentum else round(momentum[-1] or 0.0, 6),
            "total_points": events[-1]["home_score"] + events[-1]["away_score"],
            "points_per_minute": round(
                (events[-1]["home_score"] + events[-1]["away_score"])
                / max(1e-9, events[-1]["elapsed_seconds"] / 60.0),
                6,
            ),
        },
        "runs": {
            "run_count": len(runs),
            "longest_run": longest_run,
            "home_runs": sum(1 for run in runs if run["side"] == "home"),
            "away_runs": sum(1 for run in runs if run["side"] == "away"),
        },
        "garbage_time": {
            "rule": (
                f"|margin| >= {normalized['garbage_margin']} with <= "
                f"{int(GARBAGE_TIME_REMAINING_FRACTION * 100)}% of regulation remaining"
            ),
            "detected": garbage_from is not None,
            "from_elapsed_seconds": garbage_from,
        },
        "win_probability": win_prob_block,
        "settled": normalized["settled"],
        "settled_outcome": (
            None
            if not normalized["settled"]
            else {
                "home_score": normalized["final"]["home_score"],
                "away_score": normalized["final"]["away_score"],
                "home_won": normalized["final"]["home_score"] > normalized["final"]["away_score"],
                "margin": normalized["final"]["home_score"] - normalized["final"]["away_score"],
            }
        ),
        "forecast_probability": None,
        "expected_return_bps": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }
    observation["digest"] = sha256_obj(
        {key: value for key, value in observation.items() if key != "digest"}
    )
    return observation


# ---------------------------------------------------------------------------
# chart
# ---------------------------------------------------------------------------


def render_game_chart(
    series: Mapping[str, Any],
    *,
    theme: str = "dark",
    width: int = 1000,
    height: int = 420,
) -> dict[str, Any]:
    """Deterministic margin timeline (with the caller's win-probability curve overlaid when supplied).

    Shares the palette and int-only-coordinate discipline of `chart.render_chart_png`, so a sports panel and a
    price panel look like the same instrument.
    """
    normalized = normalize_game_series(series)
    palette = chart_mod.THEMES.get(theme)
    if palette is None:
        raise SportsSeriesError(f"unknown theme {theme!r}")
    events = normalized["events"]

    margin_left, margin_right, margin_top, margin_bottom = 56, 12, 22, 26
    x0, x1 = margin_left, width - margin_right
    y0, y1 = margin_top, height - margin_bottom
    if x1 - x0 < 40 or y1 - y0 < 40:
        raise SportsSeriesError("canvas too small for a game chart")

    margins = [float(event["margin"]) for event in events]
    bound = max(4.0, max(abs(value) for value in margins) * 1.15)
    max_elapsed = max(float(normalized["regulation_seconds"]), events[-1]["elapsed_seconds"])

    def to_x(elapsed: float) -> int:
        return int(round(x0 + (elapsed / max_elapsed) * (x1 - x0)))

    def to_y(margin: float) -> int:
        return int(round(y0 + ((bound - margin) / (2 * bound)) * (y1 - y0)))

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    draw.rectangle([(x0, y0), (x1, y1)], fill=palette["panel"])

    periods = _league_defaults(normalized["league"]).get("periods") or 0
    if periods:
        for period in range(1, periods):
            x = to_x(max_elapsed * period / periods)
            draw.line([(x, y0), (x, y1)], fill=palette["grid"], width=1)
    for level in (-bound, -bound / 2, 0.0, bound / 2, bound):
        y = to_y(level)
        colour = palette["axis"] if level == 0.0 else palette["grid"]
        draw.line([(x0, y), (x1, y)], fill=colour, width=1)
        draw.text((6, y - 5), f"{level:+.0f}", fill=palette["text"])

    points = [(to_x(event["elapsed_seconds"]), to_y(event["margin"])) for event in events]
    for index in range(1, len(points)):
        rising = margins[index] >= margins[index - 1]
        draw.line(
            [points[index - 1], points[index]],
            fill=chart_mod.CANDLE_UP if rising else chart_mod.CANDLE_DOWN,
            width=2,
        )

    win_prob_drawn = False
    if normalized["win_probability_supplied"]:
        overlay = chart_mod.OVERLAY_COLORS[0]
        curve = [
            (to_x(event["elapsed_seconds"]), int(round(y1 - float(event["win_prob_home"]) * (y1 - y0))))
            for event in events
        ]
        if len(curve) > 1:
            draw.line(curve, fill=overlay, width=1)
            win_prob_drawn = True

    header = (
        f"{normalized['league']} {normalized['away']} @ {normalized['home']}  "
        f"margin(home-away)  {normalized['classification']}"
    )
    draw.text((margin_left + 2, 4), header, fill=palette["text"])
    draw.text((x1 - 96, height - margin_bottom + 6), "elapsed ->", fill=palette["text"])

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    png_bytes = buffer.getvalue()
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return {
        "schema": "dimwit.sports-chart-render.v1",
        "producer": "dimwit",
        "league": normalized["league"],
        "game_id": normalized["game_id"],
        "series_digest": normalized["digest"],
        "theme": theme,
        "geometry": {
            "schema": "dimwit.sports-chart-geometry.v1",
            "width": width,
            "height": height,
            "plot": {"x0": x0, "x1": x1, "y0": y0, "y1": y1},
            "margin_bound": bound,
            "max_elapsed_seconds": max_elapsed,
            "win_probability_overlay": win_prob_drawn,
        },
        "png_base64": encoded,
        "png_bytes": len(png_bytes),
        "png_sha256": sha256_text(encoded),
        "forecast_probability": None,
        "candidate_status": "RESEARCH_INPUT_ONLY",
    }


# ---------------------------------------------------------------------------
# cross-game rule scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SportsScanConfig:
    """Chronological split across GAMES. `gap_games` is belt-and-braces: games are already disjoint, so no
    embargo is strictly required, but a gap keeps a same-day slate from straddling the boundary."""

    training_fraction: float = 0.6
    gap_games: int = 0
    alpha: float = 0.05
    min_observations: int = 20

    def validate(self) -> None:
        if not 0.2 <= self.training_fraction <= 0.8:
            raise SportsSeriesError("training_fraction must be in [0.2, 0.8]")
        if self.gap_games < 0:
            raise SportsSeriesError("gap_games must be >= 0")
        if not 0.0 < self.alpha < 0.5:
            raise SportsSeriesError("alpha must be in (0, 0.5)")
        if self.min_observations < 2:
            raise SportsSeriesError("min_observations must be >= 2")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "training_fraction": self.training_fraction,
            "gap_games": self.gap_games,
            "alpha": self.alpha,
            "min_observations": self.min_observations,
            "split_basis": "CHRONOLOGICAL_BY_GAME",
        }


#: checkpoints expressed as a fraction of regulation elapsed
CHECKPOINTS: tuple[float, ...] = (0.25, 0.5, 0.75)

Checkpoint = Mapping[str, Any]
SportsRuleFn = Callable[[Checkpoint], int]


def _snapshot_at(normalized: Mapping[str, Any], fraction: float) -> dict[str, Any] | None:
    """Game state at the last event at or before `fraction` of regulation, or `None`.

    `None` is returned unless the timeline actually *reaches* the checkpoint. Falling back to the last available
    event would silently evaluate a "75% elapsed" rule on a game whose feed stopped at 4% — the checkpoint would
    be a label, not a state. Partial feeds are common enough that this has to be structural.
    """
    events = normalized["events"]
    target = float(normalized["regulation_seconds"]) * fraction
    if float(events[-1]["elapsed_seconds"]) < target:
        return None
    seen = [event for event in events if event["elapsed_seconds"] <= target]
    if not seen:
        return None
    last = seen[-1]
    margins = [event["margin"] for event in seen]
    lead_changes = 0
    previous_sign = 0
    for margin in margins:
        sign = 1 if margin > 0 else -1 if margin < 0 else 0
        if sign and previous_sign and sign != previous_sign:
            lead_changes += 1
        if sign:
            previous_sign = sign
    runs = _runs(seen)
    longest = max((run["points"] for run in runs), default=0)
    return {
        "fraction": fraction,
        "elapsed_seconds": last["elapsed_seconds"],
        "margin": last["margin"],
        "total_points": last["home_score"] + last["away_score"],
        "largest_home_lead": max(margins),
        "largest_away_lead": -min(margins),
        "lead_changes": lead_changes,
        "longest_run_points": longest,
        "win_prob_home": last["win_prob_home"],
    }


def _rule_home_leading(threshold: int) -> SportsRuleFn:
    def rule(state: Checkpoint) -> int:
        return 1 if state["margin"] >= threshold else 0

    return rule


def _rule_away_leading(threshold: int) -> SportsRuleFn:
    def rule(state: Checkpoint) -> int:
        return -1 if state["margin"] <= -threshold else 0

    return rule


def _rule_tight(state: Checkpoint) -> int:
    return 1 if abs(state["margin"]) <= 2 else 0


def _rule_home_comeback_setup(state: Checkpoint) -> int:
    return 1 if -8 <= state["margin"] <= -3 and state["lead_changes"] >= 2 else 0


def _rule_run_against_home(state: Checkpoint) -> int:
    return -1 if state["longest_run_points"] >= 10 and state["margin"] < 0 else 0


#: condition name -> {fn, side, description}. The disclosed family size is
#: len(SPORTS_CONDITIONS) * len(CHECKPOINTS).
SPORTS_CONDITIONS: dict[str, dict[str, Any]] = {
    "home_lead_ge_3": {"fn": _rule_home_leading(3), "side": 1, "description": "Home leads by 3+."},
    "home_lead_ge_8": {"fn": _rule_home_leading(8), "side": 1, "description": "Home leads by 8+."},
    "away_lead_ge_3": {"fn": _rule_away_leading(3), "side": -1, "description": "Away leads by 3+."},
    "away_lead_ge_8": {"fn": _rule_away_leading(8), "side": -1, "description": "Away leads by 8+."},
    "within_2": {"fn": _rule_tight, "side": 1, "description": "Margin within 2 (home side taken)."},
    "home_comeback_setup": {
        "fn": _rule_home_comeback_setup,
        "side": 1,
        "description": "Home trails 3-8 in a game that has already changed hands twice.",
    },
    "run_against_home": {
        "fn": _rule_run_against_home,
        "side": -1,
        "description": "Home trails after conceding a 10+ point run.",
    },
}


def _binomial_two_sided_p(successes: int, trials: int) -> tuple[float, str]:
    """Two-sided p against a fair coin. Exact for small samples, normal approximation past 2000 trials (the
    method used is returned so the number is never quoted without it)."""
    if trials == 0:
        return 1.0, "NONE"
    if trials <= 2000:
        cumulative_low = sum(math.comb(trials, k) for k in range(0, successes + 1)) / 2**trials
        cumulative_high = sum(math.comb(trials, k) for k in range(successes, trials + 1)) / 2**trials
        return min(1.0, 2.0 * min(cumulative_low, cumulative_high)), "EXACT_BINOMIAL"
    mean = trials / 2.0
    deviation = math.sqrt(trials) / 2.0
    z = (abs(successes - mean) - 0.5) / deviation
    return min(1.0, math.erfc(z / math.sqrt(2.0))), "NORMAL_APPROXIMATION_WITH_CONTINUITY_CORRECTION"


def _wilson_interval(successes: int, trials: int, z: float = 1.959964) -> dict[str, float] | None:
    if trials == 0:
        return None
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    centre = (proportion + z**2 / (2 * trials)) / denominator
    spread = (
        z * math.sqrt(proportion * (1 - proportion) / trials + z**2 / (4 * trials**2)) / denominator
    )
    return {"lower": round(centre - spread, 6), "upper": round(centre + spread, 6)}


def scan_sports_rules(
    games: Sequence[Mapping[str, Any]],
    *,
    config: SportsScanConfig | None = None,
) -> dict[str, Any]:
    """Score in-game state rules across many settled games with full search disclosure.

    One game contributes at most one observation per (condition, checkpoint) pair, so the counts here are
    independent draws — no overlap deflation is applied or needed, and the result says so explicitly.
    """
    config = config or SportsScanConfig()
    config.validate()
    if not isinstance(games, Sequence) or len(games) < 4:
        raise SportsSeriesError("at least 4 games are required to split training/holdout")

    prepared: list[dict[str, Any]] = []
    for raw in games:
        normalized = normalize_game_series(raw)
        if not normalized["settled"]:
            continue
        prepared.append(normalized)
    if len(prepared) < 4:
        raise SportsSeriesError(
            f"only {len(prepared)} of {len(games)} games are settled; unsettled games contribute no evidence"
        )
    prepared.sort(key=lambda item: (str(item.get("as_of") or ""), item["game_id"]))

    split_at = int(len(prepared) * config.training_fraction)
    training_games = prepared[:split_at]
    holdout_games = prepared[split_at + config.gap_games :]
    if not training_games or not holdout_games:
        raise SportsSeriesError("chronological split left an empty segment")

    def evaluate(segment: Sequence[Mapping[str, Any]], name: str, fraction: float) -> dict[str, Any]:
        condition = SPORTS_CONDITIONS[name]
        wins = 0
        trials = 0
        for game in segment:
            state = _snapshot_at(game, fraction)
            if state is None:
                continue
            side = condition["fn"](state)
            if not side:
                continue
            trials += 1
            home_won = game["final"]["home_score"] > game["final"]["away_score"]
            tied = game["final"]["home_score"] == game["final"]["away_score"]
            if tied:
                trials -= 1  # a draw cannot settle a two-sided side bet
                continue
            if (side > 0 and home_won) or (side < 0 and not home_won):
                wins += 1
        p_value, method = _binomial_two_sided_p(wins, trials)
        return {
            "n": trials,
            "wins": wins,
            "win_rate": None if trials == 0 else round(wins / trials, 6),
            "wilson_95": _wilson_interval(wins, trials),
            "p_value_vs_fair_coin": round(p_value, 8),
            "p_value_method": method,
            "independent_observations": trials,
        }

    family: list[tuple[str, float]] = [
        (name, fraction) for name in SPORTS_CONDITIONS for fraction in CHECKPOINTS
    ]
    per_rule: dict[str, dict[str, Any]] = {}
    holdout_p: dict[str, float | None] = {}
    settled_total = 0
    for name, fraction in family:
        key = f"{name}@{fraction:g}"
        training = evaluate(training_games, name, fraction)
        holdout = evaluate(holdout_games, name, fraction)
        settled_total += holdout["n"]
        holdout_p[key] = holdout["p_value_vs_fair_coin"] if holdout["n"] >= config.min_observations else None
        per_rule[key] = {
            "rule": key,
            "condition": name,
            "checkpoint_fraction": fraction,
            "side": SPORTS_CONDITIONS[name]["side"],
            "description": SPORTS_CONDITIONS[name]["description"],
            "training_metrics": training,
            "held_out_metrics": holdout,
            "underpowered": holdout["n"] < config.min_observations,
        }

    from .scan import _benjamini_hochberg, _bonferroni  # local import: shared statistics, no cycle at runtime

    bonferroni = _bonferroni(holdout_p, config.alpha, len(family))
    bh = _benjamini_hochberg(holdout_p, config.alpha)

    observation = {
        "schema": "dimwit.sports-walkforward-scan.v1",
        "producer": "dimwit",
        "leagues": sorted({game["league"] for game in prepared}),
        "games_supplied": len(games),
        "games_settled": len(prepared),
        "classifications": sorted({game["classification"] for game in prepared}),
        "point_in_time_claim": all(game["point_in_time_claim"] for game in prepared),
        "configuration": config.to_dict(),
        "split": {
            "training_games": len(training_games),
            "gap_games": config.gap_games,
            "holdout_games": len(holdout_games),
            "disjoint": True,
            "holdout_used_for_selection": False,
            "selection_basis": "TRAINING_SEGMENT_ONLY",
        },
        "search_disclosure": {
            "family_size": len(family),
            "conditions": sorted(SPORTS_CONDITIONS),
            "checkpoints": list(CHECKPOINTS),
            "benchmark": "FAIR_COIN_NOT_MARKET_PRICE",
            "underpowered_excluded_from_correction": sorted(
                key for key, value in holdout_p.items() if value is None
            ),
            "bonferroni": bonferroni,
            "benjamini_hochberg": bh,
        },
        "observation_accounting": {
            "settled_holdout_observations": settled_total,
            "independent_holdout_observations": settled_total,
            "overlap_deflation_applied": False,
            "note": (
                "Distinct games do not share outcome windows, so each observation is an independent draw. "
                "This is why sports evidence is cheaper per independent observation than bar-window evidence."
            ),
        },
        "rules": per_rule,
        "promotions_applied": 0,
        "orders_created": 0,
        "broker_calls": 0,
        "live_activation": False,
        "execution_authority": False,
        "forecast_probability": None,
        "expected_return_bps": None,
        "recommendation_only": True,
        "candidate_status": (
            "HELD_OUT_SURVIVORS_PRESENT" if bh["survivor_count"] else "NO_HELD_OUT_SURVIVOR"
        ),
        "limitations": [
            "hit rate is measured against a fair coin, not against a traded price; this is not an edge claim",
            "no win-probability model is fitted; supplied curves are attributed to the caller",
        ],
    }
    observation["digest"] = sha256_obj(
        {key: value for key, value in observation.items() if key != "digest"}
    )
    return observation
