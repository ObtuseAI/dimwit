"""The anti-costume contract.

Background: DumbMoney's runtime bindings assign Dimwit the role
`chart_vision_and_deterministic_technical_analysis_for_stocks_and_crypto`, and its audit found the cell was a
costume — the TA lived in DumbMoney, was stamped `producer: "dimwit"`, and the verifier checked its own stamp.
The audit also found the wider pattern: a component whose embedded line count looked large while almost none of
it executed.

This file is the standing guard against that recurring. It asserts the cell *executes*, that every declared
capability resolves to real code in `dimwit.market`, that the writing verbs stay behind the mutation gate, that
no module in the package escapes attestation, and that nothing anywhere emits a forecast.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from dimwit.capabilities import agent_loop, base, registry
from dimwit.market import (
    bars,
    chart,
    chart_vision,
    evidence,
    indicators,
    knowledge,
    patterns,
    scan,
    selfaudit,
    sports,
)

PACKAGE_ROOT = Path(evidence.__file__).resolve().parent
MARKET_MODULES = (
    bars,
    chart,
    chart_vision,
    evidence,
    indicators,
    knowledge,
    patterns,
    scan,
    selfaudit,
    sports,
)


@pytest.fixture(scope="module")
def audit() -> dict:
    return selfaudit.audit_market_cell(deep=True)


# --- the cell really runs ---------------------------------------------------


def test_audit_is_costume_clean(audit):
    assert audit["costume_risk"] == [], f"costume findings: {audit['costume_risk']}"
    assert audit["costume_clean"] is True
    assert audit["probes_passed"] == audit["probes_total"]
    assert audit["probes_total"] >= 8  # 7 core probes + the deep walk-forward pass


def test_every_probe_produced_a_real_result(audit):
    for probe in audit["probes"]:
        assert probe["ok"] is True, f"{probe['probe']}: {probe.get('error')}"
        assert probe["detail"], f"{probe['probe']} returned an empty detail"


def test_audit_reports_substantive_counts(audit):
    counts = audit["counts"]
    assert counts["indicators"] >= 40
    assert counts["patterns"] >= 20
    assert counts["bar_rules"] >= 30
    assert counts["sports_family_size"] == counts["sports_conditions"] * counts["sports_checkpoints"]
    assert counts["knowledge_terms"] >= 100
    assert counts["chart_themes"] >= 2


def test_chart_vision_actually_recovered_prices(audit):
    probe = next(item for item in audit["probes"] if item["probe"] == "chart_vision")
    assert probe["detail"]["roundtrip_verdict"] == "PASS"
    assert probe["detail"]["worst_error_px"] <= 1.0
    assert probe["detail"]["bars_compared"] >= 100
    assert probe["detail"]["foreign_read_status"] == "OK"


def test_deep_audit_ran_the_scan_and_its_placebo(audit):
    probe = next(item for item in audit["probes"] if item["probe"] == "walkforward_scan")
    assert probe["detail"]["family_size"] == len(scan.RULES)
    assert probe["detail"]["settled_holdout_outcomes"] > 0
    assert probe["detail"]["placebo_max_bh_survivors"] >= 0


def test_audit_states_what_is_deliberately_absent(audit):
    absent = set(audit["honest_limitations"])
    assert "forecast_probabilities_or_expected_returns" in absent
    assert "live_market_data_ingestion" in absent
    assert "order_routing_or_brokerage_access" in absent
    for item in audit["responsibilities"]:
        assert item["status"].startswith(("IMPLEMENTED", "NOT_IMPLEMENTED"))
        if item["status"].startswith("IMPLEMENTED"):
            assert item["implementation"], item["responsibility"]


def test_audit_names_the_role_and_the_upstream_product_honestly(audit):
    assert audit["assigned_role"] == (
        "chart_vision_and_deterministic_technical_analysis_for_stocks_and_crypto"
    )
    # the frozen snapshot really is a game studio; pretending otherwise is how the costume started
    assert audit["upstream_product_role"] == "proof_bearing_game_production_studio"


def test_audit_is_reproducible():
    first = selfaudit.audit_market_cell()
    second = selfaudit.audit_market_cell()
    assert first["digest"] == second["digest"]


# --- capability registry ---------------------------------------------------


def test_every_registered_capability_resolves():
    result = registry.verify_all()
    assert result["ok"] is True, f"broken capabilities: {result['broken']}"


def test_market_domain_is_declared():
    assert "MARKET" in base.DOMAINS


def test_market_capabilities_point_into_this_package():
    market = [cap for cap in registry.list_capabilities() if cap.domain == "MARKET"]
    assert len(market) >= 20
    for cap in market:
        module, _, function = cap.target.partition(":")
        assert module.startswith("dimwit.market"), f"{cap.name} -> {cap.target}"
        assert function
        assert cap.description.strip(), f"{cap.name} has no description"
        assert callable(cap.resolve())


def test_the_two_writing_verbs_are_behind_the_mutation_gate():
    """Nothing in MARKET may write to disk. `export_chart` and `record_observations` do, so they are registered
    under EXECUTE, which the MCP server gates on DIMWIT_MCP_ALLOW_MUTATION."""
    by_target = {cap.target: cap for cap in registry.list_capabilities()}
    for target in ("dimwit.market.chart:export_chart", "dimwit.market.evidence:record_observations"):
        assert target in by_target, f"{target} is not registered"
        assert by_target[target].domain == "EXECUTE", f"{target} must not be a MARKET capability"
    market_targets = {
        cap.target for cap in registry.list_capabilities() if cap.domain == "MARKET"
    }
    assert "dimwit.market.chart:export_chart" not in market_targets
    assert "dimwit.market.evidence:record_observations" not in market_targets


def test_market_is_reachable_by_the_safe_agent_loop():
    assert "MARKET" in agent_loop._SAFE_DOMAINS
    assert not {"EXECUTE", "DEVELOP"} & agent_loop._SAFE_DOMAINS


def test_mcp_confines_image_paths_for_chart_vision_verbs():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dimwit_mcp_server", PACKAGE_ROOT.parents[1] / "mcp" / "dimwit_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MARKET_IMAGE_CAPABILITIES == {"MARKET/chart.read", "MARKET/chart.describe_foreign"}
    assert "MARKET" not in module.MUTATING_DOMAINS
    with pytest.raises(ValueError, match="outside Dimwit's approved capture roots"):
        module._confined_provider_image(__file__)


# --- attestation completeness ----------------------------------------------


def test_no_module_in_the_package_escapes_the_attestation_decision():
    on_disk = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    declared = set(evidence.ATTESTED_MODULES) | set(evidence.NON_ATTESTED_MODULES)
    assert on_disk == declared, (
        "a new market module must be added to ATTESTED_MODULES (or explicitly to "
        f"NON_ATTESTED_MODULES): on_disk-declared={on_disk - declared}, declared-on_disk={declared - on_disk}"
    )


def test_only_the_cli_is_exempt_from_attestation():
    assert evidence.NON_ATTESTED_MODULES == ("cli.py",)


# --- doctrine --------------------------------------------------------------


def test_no_market_module_reaches_the_network():
    banned = ("requests", "urllib.request", "httpx", "socket", "aiohttp", "http.client")
    offenders: dict[str, list[str]] = {}
    for module in MARKET_MODULES:
        source = Path(module.__file__).read_text(encoding="utf-8")
        hits = [name for name in banned if f"import {name}" in source]
        if hits:
            offenders[module.__name__] = hits
    assert not offenders, f"market modules must not reach the network: {offenders}"


def test_every_public_observation_reports_forecast_probability_none():
    series = bars.normalize_series(selfaudit.synthetic_series(bar_count=1000))
    games = selfaudit.synthetic_games(24)
    render = chart.render_chart_png(series, max_bars=100)
    produced = {
        "ta_observation": evidence.export_dumbmoney_observation(series),
        "patterns": patterns.detect_patterns(series),
        "structure": patterns.market_structure(series),
        "levels": patterns.support_resistance(series),
        "chart_png": render,
        "chart_svg": chart.render_chart_svg(series, max_bars=100),
        "chart_read": chart_vision.read_chart(render["geometry"], png_base64=render["png_base64"]),
        "roundtrip": chart_vision.verify_chart_roundtrip(series, max_bars=100),
        "foreign_read": chart_vision.describe_chart(png_base64=render["png_base64"]),
        "scan": scan.scan_rules(series),
        "placebo": scan.placebo_control(series, lags=(37,)),
        "game": sports.analyze_game_series(games[0]),
        "game_chart": sports.render_game_chart(games[0]),
        "game_scan": sports.scan_sports_rules(games),
        "audit": selfaudit.audit_market_cell(),
    }
    for name, payload in produced.items():
        assert "forecast_probability" in payload, f"{name} does not declare forecast_probability"
        assert payload["forecast_probability"] is None, f"{name} emitted a forecast"
        assert payload.get("expected_return_bps") is None, f"{name} emitted an expected return"


def test_nothing_claims_execution_authority_or_broker_access():
    series = bars.normalize_series(selfaudit.synthetic_series(bar_count=1000))
    for payload in (
        evidence.export_dumbmoney_observation(series),
        scan.scan_rules(series),
        sports.scan_sports_rules(selfaudit.synthetic_games(24)),
    ):
        assert payload["execution_authority"] is False
        assert payload["live_activation"] is False
        assert payload["broker_calls"] == 0
        assert payload["orders_created"] == 0


def test_every_market_module_documents_itself():
    for module in MARKET_MODULES:
        doc = inspect.getdoc(module)
        assert doc and len(doc) > 200, f"{module.__name__} needs a real module docstring"


def test_error_types_are_domain_specific_not_bare():
    for error in (
        bars.BarSeriesError,
        chart.ChartError,
        chart_vision.ChartVisionError,
        evidence.EvidenceError,
        scan.ScanError,
        sports.SportsSeriesError,
    ):
        assert issubclass(error, (ValueError, KeyError))
    assert issubclass(knowledge.KnowledgeError, KeyError)


# --- CLI ------------------------------------------------------------------


def test_cli_exits_zero_on_a_clean_audit(capsys):
    from dimwit.market.cli import main

    assert main(["audit"]) == 0
    payload = capsys.readouterr().out
    assert '"costume_clean": true' in payload


def test_cli_exits_zero_on_a_passing_vision_check(capsys):
    from dimwit.market.cli import main

    assert main(["vision", "--self", "--bars", "120"]) == 0
    assert '"verdict": "PASS"' in capsys.readouterr().out


def test_cli_theme_flag_does_not_drop_the_bar_limit(capsys):
    """Regression: `--theme` used to make the render-kwargs dict truthy, which silently discarded the 120-bar
    default and rendered every bar — shrinking bodies to one pixel and BLOCKING the read."""
    from dimwit.market.cli import main

    assert main(["vision", "--self", "--theme", "tote"]) == 0
    output = capsys.readouterr().out
    assert '"verdict": "PASS"' in output
    assert '"theme": "tote"' in output or '"bars_compared": 120' in output


def test_cli_help_and_unknown_command(capsys):
    from dimwit.market.cli import main

    assert main([]) == 0
    assert main(["--help"]) == 0
    assert main(["definitely-not-a-command"]) == 2


def test_cli_requires_a_series_argument():
    from dimwit.market.cli import main

    with pytest.raises(SystemExit, match="series.json"):
        main(["indicators"])


def test_dimwit_cli_routes_market(capsys):
    from dimwit.cli import main

    assert main(["market", "know", "adverse_selection"]) == 0
    assert "adverse_selection" in capsys.readouterr().out
