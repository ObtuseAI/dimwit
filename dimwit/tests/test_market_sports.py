"""Sports tests.

The distinctive claim on this side is **independence**: one settled game contributes one observation per rule,
so no overlap deflation is needed. That claim is only worth anything if the boundaries hold, so the tests check
that unsettled games contribute nothing, draws are excluded rather than scored as a loss, and the split is
chronological by game.

The other thing under guard is the refusal to model win probability. If a caller supplies a curve it is analyzed
and attributed to them; if not, the result says `NOT_PROVIDED` and no substitute appears anywhere.
"""
from __future__ import annotations


import pytest

from dimwit.market import sports
from dimwit.market.selfaudit import synthetic_games


def game(
    events: list[tuple[float, int, int]],
    *,
    final: tuple[int, int] | None = None,
    league: str = "NBA",
    game_id: str = "T-1",
    win_probs: list[float] | None = None,
) -> dict:
    payload = {
        "schema": sports.GAME_SERIES_SCHEMA,
        "classification": "SYNTHETIC_TEST_FIXTURE_NOT_MARKET_EVIDENCE",
        "league": league,
        "game_id": game_id,
        "home": "HOME",
        "away": "AWAY",
        "as_of": "2026-01-01T00:00:00Z",
        "events": [
            {
                "elapsed_seconds": elapsed,
                "home_score": home,
                "away_score": away,
                **({"win_prob_home": win_probs[index]} if win_probs else {}),
            }
            for index, (elapsed, home, away) in enumerate(events)
        ],
    }
    if final is not None:
        payload["final"] = {"home_score": final[0], "away_score": final[1]}
    return payload


BASIC = [(600.0, 10, 8), (1200.0, 24, 20), (1800.0, 35, 40), (2400.0, 52, 50), (2880.0, 70, 66)]


# --- normalization ---------------------------------------------------------


def test_normalization_produces_a_canonical_timeline():
    normalized = sports.normalize_game_series(game(BASIC, final=(70, 66)))
    assert normalized["league"] == "NBA"
    assert normalized["regulation_seconds"] == 2880
    assert normalized["event_count"] == 5
    assert normalized["settled"] is True
    assert normalized["events"][2]["margin"] == -5
    assert normalized["win_probability_supplied"] is False
    assert normalized["digest"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update(schema="other.v1"), "schema must be"),
        (lambda p: p.update(classification="REAL_TRUTH"), "unknown classification"),
        (lambda p: p.update(league=""), "league is required"),
        (lambda p: p.update(game_id=""), "game_id is required"),
        (lambda p: p.update(events=p["events"][:1]), "at least 2"),
        (lambda p: p.update(league="CRICKET"), "regulation_seconds is required"),
    ],
)
def test_normalization_rejects_dishonest_timelines(mutate, message):
    payload = game(BASIC, final=(70, 66))
    mutate(payload)
    with pytest.raises(sports.SportsSeriesError, match=message):
        sports.normalize_game_series(payload)


def test_clock_must_strictly_increase():
    payload = game([(600.0, 5, 5), (600.0, 8, 5), (1200.0, 12, 9)], final=(12, 9))
    with pytest.raises(sports.SportsSeriesError, match="strictly increasing"):
        sports.normalize_game_series(payload)


def test_scores_cannot_decrease():
    payload = game([(600.0, 10, 8), (1200.0, 7, 9), (1800.0, 20, 18)], final=(20, 18))
    with pytest.raises(sports.SportsSeriesError, match="score decreased"):
        sports.normalize_game_series(payload)


def test_final_cannot_be_below_the_timeline():
    with pytest.raises(sports.SportsSeriesError, match="below the last timeline score"):
        sports.normalize_game_series(game(BASIC, final=(10, 10)))


def test_win_probability_must_be_a_probability():
    payload = game(BASIC, final=(70, 66), win_probs=[0.4, 0.5, 0.6, 0.7, 1.4])
    with pytest.raises(sports.SportsSeriesError, match=r"win_prob_home must be in \[0, 1\]"):
        sports.normalize_game_series(payload)


def test_synthetic_classification_cannot_claim_point_in_time():
    payload = game(BASIC, final=(70, 66))
    payload["point_in_time_claim"] = True
    with pytest.raises(sports.SportsSeriesError, match="point_in_time_claim"):
        sports.normalize_game_series(payload)


# --- analysis --------------------------------------------------------------


def test_analysis_counts_lead_changes_and_largest_leads():
    observation = sports.analyze_game_series(game(BASIC, final=(70, 66)))
    state = observation["state"]
    assert state["largest_home_lead"] == 4
    assert state["largest_away_lead"] == 5
    assert state["lead_changes"] == 2  # home -> away -> home
    assert state["total_points"] == 136
    assert observation["settled_outcome"]["home_won"] is True
    assert observation["settled_outcome"]["margin"] == 4


def test_time_leading_fractions_sum_to_at_most_one():
    observation = sports.analyze_game_series(game(BASIC, final=(70, 66)))
    state = observation["state"]
    assert 0.0 <= state["time_leading_home_fraction"] <= 1.0
    assert state["time_leading_home_fraction"] + state["time_leading_away_fraction"] <= 1.0 + 1e-9


def test_runs_are_maximal_single_sided_stretches():
    events = [(600.0, 10, 10), (1200.0, 22, 10), (1800.0, 30, 10), (2400.0, 30, 24), (2880.0, 32, 30)]
    observation = sports.analyze_game_series(game(events, final=(32, 30)))
    longest = observation["runs"]["longest_run"]
    assert longest["side"] == "home"
    assert longest["points"] == 20  # 12 + 8 across two consecutive home-only stretches
    assert observation["runs"]["home_runs"] >= 1
    assert observation["runs"]["away_runs"] >= 1


def test_garbage_time_needs_both_a_late_clock_and_a_big_margin():
    blowout = [(600.0, 20, 5), (1500.0, 45, 15), (2600.0, 90, 50), (2880.0, 100, 60)]
    detected = sports.analyze_game_series(game(blowout, final=(100, 60)))["garbage_time"]
    assert detected["detected"] is True
    assert detected["from_elapsed_seconds"] >= 2880 * (1 - sports.GARBAGE_TIME_REMAINING_FRACTION)
    close = sports.analyze_game_series(game(BASIC, final=(70, 66)))["garbage_time"]
    assert close["detected"] is False


def test_win_probability_is_never_invented():
    observation = sports.analyze_game_series(game(BASIC, final=(70, 66)))
    assert observation["win_probability"] == {"status": "NOT_PROVIDED"}
    assert observation["forecast_probability"] is None
    assert observation["expected_return_bps"] is None


def test_supplied_win_probability_is_analyzed_and_attributed():
    probabilities = [0.55, 0.62, 0.38, 0.58, 0.91]
    observation = sports.analyze_game_series(
        game(BASIC, final=(70, 66), win_probs=probabilities)
    )
    block = observation["win_probability"]
    assert block["status"] == "SUPPLIED_BY_CALLER"
    assert "does not model" in block["source_disclosure"]
    assert block["first"] == pytest.approx(0.55)
    assert block["last"] == pytest.approx(0.91)
    assert block["crossings_of_50"] == 2
    assert block["max_single_event_swing"] == pytest.approx(0.33, abs=1e-9)
    assert block["top_leverage_events"]
    for item in block["top_leverage_events"]:
        assert item["leverage_per_point"] >= 0


def test_unsettled_games_are_analyzable_but_settle_nothing():
    observation = sports.analyze_game_series(game(BASIC))
    assert observation["settled"] is False
    assert observation["settled_outcome"] is None


# --- chart -----------------------------------------------------------------


def test_game_chart_is_deterministic_and_reports_its_geometry():
    payload = game(BASIC, final=(70, 66))
    first = sports.render_game_chart(payload)
    second = sports.render_game_chart(payload)
    assert first["png_sha256"] == second["png_sha256"]
    assert first["png_bytes"] > 500
    assert first["geometry"]["schema"] == "dimwit.sports-chart-geometry.v1"
    assert first["geometry"]["win_probability_overlay"] is False
    assert first["forecast_probability"] is None


def test_game_chart_overlays_a_supplied_win_probability_curve():
    payload = game(BASIC, final=(70, 66), win_probs=[0.5, 0.6, 0.4, 0.55, 0.9])
    result = sports.render_game_chart(payload)
    assert result["geometry"]["win_probability_overlay"] is True


def test_game_chart_rejects_an_unknown_theme_and_a_tiny_canvas():
    payload = game(BASIC, final=(70, 66))
    with pytest.raises(sports.SportsSeriesError, match="unknown theme"):
        sports.render_game_chart(payload, theme="vaporwave")
    with pytest.raises(sports.SportsSeriesError, match="too small"):
        sports.render_game_chart(payload, width=80, height=80)


# --- cross-game scan -------------------------------------------------------


@pytest.fixture(scope="module")
def games() -> list[dict]:
    return synthetic_games(60)


@pytest.fixture(scope="module")
def game_scan(games) -> dict:
    return sports.scan_sports_rules(games)


def test_scan_requires_enough_settled_games(games):
    with pytest.raises(sports.SportsSeriesError, match="at least 4 games"):
        sports.scan_sports_rules(games[:2])
    unsettled = [{key: value for key, value in item.items() if key != "final"} for item in games[:10]]
    with pytest.raises(sports.SportsSeriesError, match="are settled"):
        sports.scan_sports_rules(unsettled)


def test_scan_discloses_its_full_search_space(game_scan):
    disclosure = game_scan["search_disclosure"]
    assert disclosure["family_size"] == len(sports.SPORTS_CONDITIONS) * len(sports.CHECKPOINTS)
    assert disclosure["conditions"] == sorted(sports.SPORTS_CONDITIONS)
    assert disclosure["checkpoints"] == list(sports.CHECKPOINTS)
    assert disclosure["benchmark"] == "FAIR_COIN_NOT_MARKET_PRICE"
    assert len(game_scan["rules"]) == disclosure["family_size"]


def test_observations_are_independent_with_no_overlap_deflation(game_scan):
    accounting = game_scan["observation_accounting"]
    assert accounting["overlap_deflation_applied"] is False
    assert accounting["settled_holdout_observations"] == accounting["independent_holdout_observations"]
    assert "do not share outcome windows" in accounting["note"]


def test_split_is_chronological_and_disjoint(game_scan, games):
    split = game_scan["split"]
    assert split["training_games"] + split["holdout_games"] <= len(games)
    assert split["holdout_used_for_selection"] is False
    assert split["disjoint"] is True
    assert game_scan["configuration"]["split_basis"] == "CHRONOLOGICAL_BY_GAME"


def test_underpowered_rules_are_excluded_from_the_correction_not_silently_passed(game_scan):
    excluded = set(game_scan["search_disclosure"]["underpowered_excluded_from_correction"])
    for key, rule in game_scan["rules"].items():
        assert rule["underpowered"] == (key in excluded)
    survivors = set(game_scan["search_disclosure"]["benjamini_hochberg"]["survivors"])
    assert not survivors & excluded


def test_win_rate_and_wilson_interval_agree_with_the_counts(game_scan):
    for rule in game_scan["rules"].values():
        metrics = rule["held_out_metrics"]
        if not metrics["n"]:
            assert metrics["win_rate"] is None
            continue
        assert metrics["win_rate"] == pytest.approx(metrics["wins"] / metrics["n"])
        interval = metrics["wilson_95"]
        assert interval["lower"] <= metrics["win_rate"] <= interval["upper"]


def test_exact_binomial_is_used_for_small_samples(game_scan):
    methods = {rule["held_out_metrics"]["p_value_method"] for rule in game_scan["rules"].values()}
    assert methods <= {"EXACT_BINOMIAL", "NONE"}


def test_binomial_helper_matches_known_values():
    p_value, method = sports._binomial_two_sided_p(10, 10)
    assert method == "EXACT_BINOMIAL"
    assert p_value == pytest.approx(2 / 1024)
    assert sports._binomial_two_sided_p(5, 10)[0] == pytest.approx(1.0)
    assert sports._binomial_two_sided_p(0, 0) == (1.0, "NONE")


def test_draws_are_excluded_rather_than_counted_as_losses():
    drawn = synthetic_games(8)
    for item in drawn:
        item["final"] = {"home_score": 100, "away_score": 100}
        item["events"] = [
            {**event, "home_score": min(event["home_score"], 100), "away_score": min(event["away_score"], 100)}
            for event in item["events"]
        ]
    result = sports.scan_sports_rules(drawn)
    assert result["observation_accounting"]["settled_holdout_observations"] == 0


def test_scan_carries_no_forecast_and_states_its_limits(game_scan):
    assert game_scan["forecast_probability"] is None
    assert game_scan["expected_return_bps"] is None
    assert game_scan["orders_created"] == 0
    assert game_scan["execution_authority"] is False
    assert game_scan["recommendation_only"] is True
    assert any("not an edge claim" in item for item in game_scan["limitations"])
    assert any("no win-probability model" in item for item in game_scan["limitations"])


def test_scan_is_deterministic(games):
    assert sports.scan_sports_rules(games)["digest"] == sports.scan_sports_rules(games)["digest"]


def test_config_validation():
    with pytest.raises(sports.SportsSeriesError, match="training_fraction"):
        sports.SportsScanConfig(training_fraction=0.95).validate()
    with pytest.raises(sports.SportsSeriesError, match="gap_games"):
        sports.SportsScanConfig(gap_games=-1).validate()
    with pytest.raises(sports.SportsSeriesError, match="alpha"):
        sports.SportsScanConfig(alpha=0.7).validate()
    with pytest.raises(sports.SportsSeriesError, match="min_observations"):
        sports.SportsScanConfig(min_observations=1).validate()


def test_snapshot_returns_none_when_the_checkpoint_never_happened():
    # the feed stops at 120s of a 2880s game: only checkpoints inside those 120s are real states
    truncated = sports.normalize_game_series(game([(60.0, 2, 0), (120.0, 4, 2)], final=(4, 2)))
    assert sports._snapshot_at(truncated, 0.75) is None
    assert sports._snapshot_at(truncated, 0.5) is None
    assert sports._snapshot_at(truncated, 60.0 / 2880.0) is not None


def test_snapshot_only_sees_events_up_to_the_checkpoint():
    normalized = sports.normalize_game_series(game(BASIC, final=(70, 66)))
    half = sports._snapshot_at(normalized, 0.5)
    assert half["elapsed_seconds"] <= 2880 * 0.5
    assert half["total_points"] == 44  # the 1200s event, not the final score
