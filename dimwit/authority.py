"""Central fail-closed predicates for Dimwit's human-review ceiling."""

from __future__ import annotations

from dimwit.pipelines.base import OPERATOR_ONLY

APPROVED_OPERATOR_ACTORS = frozenset({"human_operator"})


def is_ceiling_violation(entry: dict) -> bool:
    state = str(entry.get("state", "")).split(".")[-1]
    if state not in OPERATOR_ONLY:
        return False
    actor = entry.get("actor")
    return not (isinstance(actor, str) and actor.casefold() in APPROVED_OPERATOR_ACTORS)
