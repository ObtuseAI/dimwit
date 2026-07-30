"""Knowledge pack tests.

The pack's value is that it cannot drift from the code: indicator and pattern definitions come from the code
registries, and a JSON concept that duplicates one of those names is a hard error rather than a second source of
truth. The rest checks that lookups fail loudly (an unknown term raises instead of returning a plausible
sentence) and that citations carry a digest a reader can check.
"""
from __future__ import annotations

import json

import pytest

from dimwit.market import indicators as ind
from dimwit.market import knowledge
from dimwit.market import patterns as pat


@pytest.fixture(autouse=True)
def _fresh_cache():
    knowledge.load(force=True)
    yield
    knowledge.load(force=True)


def test_every_indicator_and_pattern_is_citable():
    terms = set(knowledge.terms())
    assert set(ind.INDICATORS) <= terms
    assert set(pat.PATTERNS) <= terms
    assert len(terms) == len(ind.INDICATORS) + len(pat.PATTERNS) + len(knowledge.terms("concept"))


def test_code_registries_are_the_source_of_truth_for_their_own_definitions():
    entry = knowledge.describe("rsi14")
    assert entry["source"] == "code:dimwit.market.indicators.INDICATORS"
    assert entry["definition"] == ind.INDICATORS["rsi14"]["description"]
    assert entry["warmup_bars"] == ind.INDICATORS["rsi14"]["warmup_bars"]
    pattern = knowledge.describe("bullish_engulfing")
    assert pattern["source"] == "code:dimwit.market.patterns.PATTERNS"
    assert pattern["invalidation"] == pat.PATTERNS["bullish_engulfing"]["invalidation"]


def test_a_json_concept_may_not_shadow_a_code_definition(tmp_path, monkeypatch):
    payload = {
        "schema": "dimwit.market-knowledge-pack.v1",
        "version": "test",
        "concepts": [{"term": "rsi14", "family": "momentum", "definition": "a competing definition"}],
    }
    path = tmp_path / "market_knowledge.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(knowledge, "KNOWLEDGE_PATH", path)
    with pytest.raises(knowledge.KnowledgeError, match="duplicates a code-derived definition"):
        knowledge.load(force=True)


def test_pack_must_declare_its_schema(tmp_path, monkeypatch):
    path = tmp_path / "market_knowledge.json"
    path.write_text(json.dumps({"concepts": []}), encoding="utf-8")
    monkeypatch.setattr(knowledge, "KNOWLEDGE_PATH", path)
    with pytest.raises(knowledge.KnowledgeError, match="knowledge-pack.v1"):
        knowledge.load(force=True)


def test_unknown_terms_raise_instead_of_being_improvised():
    with pytest.raises(knowledge.KnowledgeError, match="unknown market term"):
        knowledge.describe("quantum_fibonacci_retracement")


def test_lookup_resolves_aliases_and_is_case_insensitive():
    by_alias = knowledge.describe("clv")
    assert by_alias["term"] == "closing_line_value"
    assert by_alias["resolved_from_alias"] == "clv"
    assert knowledge.describe("ADVERSE_SELECTION")["term"] == "adverse_selection"


def test_search_ranks_term_hits_above_body_hits():
    hits = knowledge.search("calibration")
    assert hits[0]["term"] == "calibration"
    assert all(hit["match_rank"] >= hits[0]["match_rank"] for hit in hits)
    assert knowledge.search("") == []
    assert len(knowledge.search("bias", limit=3)) <= 3


def test_search_finds_concepts_by_their_failure_modes():
    hits = {hit["term"] for hit in knowledge.search("per-order", limit=20)}
    assert "fee_ceiling_per_contract" in hits


def test_citation_is_quotable_and_digest_stamped():
    citation = knowledge.citation("adverse_selection")
    assert citation["schema"] == "dimwit.market-knowledge-citation.v1"
    assert citation["term"] == "adverse_selection"
    assert "Why it matters:" in citation["text"]
    assert "Failure modes:" in citation["text"]
    assert citation["citation_digest"]
    assert knowledge.citation("adverse_selection")["citation_digest"] == citation["citation_digest"]


def test_pattern_citations_include_the_invalidation_condition():
    citation = knowledge.citation("hammer")
    assert "Invalidation:" in citation["text"]


def test_every_concept_carries_a_rationale_and_failure_modes():
    thin: list[str] = []
    for term in knowledge.terms("concept"):
        entry = knowledge.describe(term)
        if not entry.get("why_it_matters") or not entry.get("failure_modes"):
            thin.append(term)
    assert not thin, f"concepts missing why_it_matters/failure_modes: {thin}"


def test_concept_cross_references_resolve():
    dangling: dict[str, list[str]] = {}
    known = set(knowledge.terms())
    for term in knowledge.terms("concept"):
        missing = [ref for ref in knowledge.describe(term).get("see_also", []) if ref not in known]
        if missing:
            dangling[term] = missing
    assert not dangling, f"see_also points at unknown terms: {dangling}"


def test_the_pack_records_the_lessons_this_system_has_already_paid_for():
    """These specific concepts exist because the surrounding system got each of them wrong once. Losing them
    would mean re-deriving them from a live loss."""
    required = {
        "adverse_selection",
        "favorite_longshot_bias",
        "fee_ceiling_per_contract",
        "unconditional_baseline",
        "overlapping_windows",
        "settled_observation",
        "self_attestation",
        "selection_leakage",
        "multiple_testing",
        "null_control",
        "closing_line_value",
        "fail_closed",
        "chart_pixel_evidence",
        "win_probability_model",
    }
    assert required <= set(knowledge.terms("concept"))


def test_summary_counts_by_kind_and_family():
    summary = knowledge.summary()
    assert summary["term_count"] == len(knowledge.terms())
    assert summary["by_kind"]["indicator"] == len(ind.INDICATORS)
    assert summary["by_kind"]["pattern"] == len(pat.PATTERNS)
    assert summary["by_kind"]["concept"] >= 35
    assert summary["pack_digest"] and summary["merged_digest"]
