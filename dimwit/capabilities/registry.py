"""Capability registry + dispatch (task 9).

Loads `config/capability_registry.json` into lazily-resolved Capability handles, so any caller (the director,
the brain agent loop, the MCP server) can `dispatch("TEST/gate.run_all", cand)` by name. `verify_all()` is the
self-validation hook (task 16): every registered capability must resolve to a real importable callable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .base import Capability

ROOT = Path(__file__).resolve().parents[2]              # Dimwit/
REGISTRY_CONFIG = ROOT / "config" / "capability_registry.json"

# ensure the Dimwit root is importable (for the dimwit package and scripts.* modules like scripts.qa.dimwit_light_qa)
for p in (str(ROOT),):
    if p not in sys.path:
        sys.path.insert(0, p)

_REGISTRY: dict = {}


def load_registry(force: bool = False) -> dict:
    if _REGISTRY and not force:
        return _REGISTRY
    _REGISTRY.clear()
    data = json.loads(REGISTRY_CONFIG.read_text(encoding="utf-8"))
    for e in data.get("capabilities", []):
        cap = Capability(name=e["name"], target=e["target"], domain=e.get("domain", ""),
                         description=e.get("description", ""))
        _REGISTRY[cap.name] = cap
    return _REGISTRY


def get(name: str) -> Capability:
    return load_registry()[name]


def list_capabilities() -> list:
    return list(load_registry().values())


def dispatch(name: str, *args, **kwargs):
    """Resolve + call a capability by name."""
    return get(name).resolve()(*args, **kwargs)


def verify_all() -> dict:
    """Every registry entry must resolve to a real importable callable (task 16 self-validation hook)."""
    out = {"ok": True, "count": 0, "resolved": [], "broken": []}
    for cap in list_capabilities():
        out["count"] += 1
        try:
            cap.resolve()
            out["resolved"].append(cap.name)
        except Exception as e:
            out["ok"] = False
            out["broken"].append({"name": cap.name, "target": cap.target, "error": str(e)})
    return out


if __name__ == "__main__":
    print(json.dumps(verify_all(), indent=2))
