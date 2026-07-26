"""Read-only live-Unreal capability exposed through the generic registry.

Mutating Unreal work belongs to the dedicated UE MCP tools and repository-owned
toolchain jobs, where mutation and bridge authentication are explicit. Keeping
the generic registry handle read-only prevents one broad opt-in from becoming
active-slice authority.
"""

from __future__ import annotations

from ue_mcp import ue_client

READ_ONLY_COMMANDS = frozenset({"ping", "list_actors"})


def call(cmd: str, params: dict | None = None) -> dict:
    if cmd not in READ_ONLY_COMMANDS:
        return {
            "ok": False,
            "blocked": True,
            "error": f"generic live-Unreal capability does not authorize {cmd!r}",
            "review_ceiling": "PROMOTED_TO_REVIEW",
        }
    return ue_client.call(cmd, params or {})
