"""Market knowledge pack — the cell's citable memory.

Three sources, merged at read time so they cannot drift apart:

1. `indicators.INDICATORS` — indicator definitions, straight from the code that computes them.
2. `patterns.PATTERNS` — pattern definitions and, importantly, each pattern's invalidation condition.
3. `config/market_knowledge.json` — the methodology, statistics, microstructure, sports and assurance concepts
   that are not derivable from code: what adverse selection is, why a per-contract fee ceiling does not
   amortize, why overlapping windows inflate a t-statistic, why a producer stamp is not provenance.

The point of (3) is institutional memory. Every concept in there is one this system has already paid for, and
an agent that can look it up does not have to rediscover it. `describe()` is the lookup an LLM voice should cite
from instead of improvising a definition.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core import sha256_obj
from .indicators import INDICATORS
from .patterns import PATTERNS

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_PATH = ROOT / "config" / "market_knowledge.json"

_CACHE: dict[str, Any] = {}


class KnowledgeError(KeyError):
    """Raised when a term is not in the pack. Better than inventing a definition."""


def load(force: bool = False) -> dict[str, Any]:
    """Load and index the pack. Raises if a JSON concept collides with a code-derived term, because a
    duplicated definition is exactly the drift this merge exists to prevent."""
    if _CACHE and not force:
        return _CACHE
    data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "dimwit.market-knowledge-pack.v1":
        raise KnowledgeError("market_knowledge.json is not a dimwit.market-knowledge-pack.v1 payload")

    entries: dict[str, dict[str, Any]] = {}
    for name, spec in INDICATORS.items():
        entries[name] = {
            "term": name,
            "source": "code:dimwit.market.indicators.INDICATORS",
            "family": spec["family"],
            "kind": "indicator",
            "definition": spec["description"],
            "warmup_bars": spec["warmup_bars"],
            "aliases": [],
            "see_also": ["prefix_stability", "look_ahead_bias"],
        }
    for name, spec in PATTERNS.items():
        entries[name] = {
            "term": name,
            "source": "code:dimwit.market.patterns.PATTERNS",
            "family": spec["family"],
            "kind": "pattern",
            "definition": spec["description"],
            "invalidation": spec["invalidation"],
            "bars_required": spec["bars_required"],
            "direction": spec["direction"],
            "aliases": [],
            "see_also": ["confirmation_lag", "multiple_testing"],
        }

    aliases: dict[str, str] = {}
    for concept in data.get("concepts", []):
        term = concept["term"]
        if term in entries:
            raise KnowledgeError(
                f"concept {term!r} duplicates a code-derived definition; remove it from market_knowledge.json"
            )
        entries[term] = concept | {"source": "pack:config/market_knowledge.json", "kind": "concept"}
        for alias in concept.get("aliases", []):
            aliases[str(alias).lower()] = term

    _CACHE.clear()
    _CACHE.update(
        {
            "schema": data["schema"],
            "version": data.get("version", "0"),
            "entries": entries,
            "aliases": aliases,
            "pack_digest": sha256_obj(data),
            "merged_digest": sha256_obj(sorted(entries)),
        }
    )
    return _CACHE


def terms(kind: str | None = None) -> list[str]:
    """All known terms, optionally filtered to `indicator`, `pattern` or `concept`."""
    entries = load()["entries"]
    if kind is None:
        return sorted(entries)
    return sorted(name for name, entry in entries.items() if entry.get("kind") == kind)


def describe(term: str) -> dict[str, Any]:
    """Look up one term by name or alias. Raises `KnowledgeError` rather than guessing."""
    pack = load()
    key = str(term).strip()
    entries = pack["entries"]
    if key in entries:
        return dict(entries[key])
    resolved = pack["aliases"].get(key.lower())
    if resolved:
        return dict(entries[resolved]) | {"resolved_from_alias": key}
    lowered = {name.lower(): name for name in entries}
    if key.lower() in lowered:
        return dict(entries[lowered[key.lower()]])
    raise KnowledgeError(
        f"unknown market term {term!r}; {len(entries)} terms are available via knowledge.terms()"
    )


def search(query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Substring search over term, aliases, definition and rationale. Ranked: term hits before body hits."""
    needle = str(query).strip().lower()
    if not needle:
        return []
    hits: list[tuple[int, str]] = []
    for name, entry in load()["entries"].items():
        haystacks = [
            (0, name.lower()),
            (1, " ".join(str(alias).lower() for alias in entry.get("aliases", []))),
            (2, str(entry.get("definition", "")).lower()),
            (3, str(entry.get("why_it_matters", "")).lower()),
            (4, " ".join(str(mode).lower() for mode in entry.get("failure_modes", []))),
        ]
        rank = next((weight for weight, text in haystacks if needle in text), None)
        if rank is not None:
            hits.append((rank, name))
    hits.sort()
    entries = load()["entries"]
    return [
        {
            "term": name,
            "kind": entries[name].get("kind"),
            "family": entries[name].get("family"),
            "definition": entries[name].get("definition"),
            "match_rank": rank,
        }
        for rank, name in hits[:limit]
    ]


def citation(term: str) -> dict[str, Any]:
    """A quotable, digest-stamped citation for one term.

    Use this when a report or an LLM voice needs to state a definition: the digest lets a reader confirm the
    text came from the pack at a known version instead of from a model's recollection.
    """
    entry = describe(term)
    pack = load()
    lines = [f"{entry['term']} ({entry.get('kind')}/{entry.get('family')}): {entry.get('definition')}"]
    if entry.get("why_it_matters"):
        lines.append(f"Why it matters: {entry['why_it_matters']}")
    if entry.get("invalidation"):
        lines.append(f"Invalidation: {entry['invalidation']}")
    if entry.get("failure_modes"):
        lines.append("Failure modes: " + "; ".join(entry["failure_modes"]))
    text = "\n".join(lines)
    return {
        "schema": "dimwit.market-knowledge-citation.v1",
        "producer": "dimwit",
        "term": entry["term"],
        "kind": entry.get("kind"),
        "source": entry.get("source"),
        "pack_version": pack["version"],
        "pack_digest": pack["pack_digest"],
        "text": text,
        "citation_digest": sha256_obj({"term": entry["term"], "text": text, "pack": pack["pack_digest"]}),
    }


def summary() -> dict[str, Any]:
    """Coverage report: what the cell can cite, by kind and family."""
    entries = load()["entries"]
    by_kind: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for entry in entries.values():
        by_kind[str(entry.get("kind"))] = by_kind.get(str(entry.get("kind")), 0) + 1
        by_family[str(entry.get("family"))] = by_family.get(str(entry.get("family")), 0) + 1
    pack = load()
    return {
        "schema": "dimwit.market-knowledge-summary.v1",
        "producer": "dimwit",
        "pack_version": pack["version"],
        "pack_digest": pack["pack_digest"],
        "merged_digest": pack["merged_digest"],
        "term_count": len(entries),
        "by_kind": dict(sorted(by_kind.items())),
        "by_family": dict(sorted(by_family.items())),
    }
