"""Dimwit pipelines self-validation (the 'fully-proofed' self-check).

Every registered pipeline must: resolve to a class, be a ProductionPipeline subclass, instantiate, declare
name/kind, and expose the four hooks (plan/execute/qa/repair). Mirrors capabilities.registry.verify_all().

  python -m dimwit.pipelines.validate
"""
from __future__ import annotations

import json

from . import list_pipelines, get_pipeline
from .base import ProductionPipeline


def validate_all() -> dict:
    out = {"ok": True, "count": 0, "valid": [], "broken": []}
    for name in list_pipelines():
        out["count"] += 1
        try:
            pipe = get_pipeline(name)
            assert isinstance(pipe, ProductionPipeline), "not a ProductionPipeline subclass"
            assert getattr(pipe, "name", None) and getattr(pipe, "kind", None), "missing name/kind"
            for hook in ("plan", "execute", "qa", "repair"):
                assert callable(getattr(pipe, hook, None)), f"missing hook {hook}"
            # ledger must be hash-chain consistent
            chain_ok = pipe.ledger.consistency_check().get("chain_ok", True)
            assert chain_ok, "ledger chain broken"
            out["valid"].append(name)
        except Exception as e:
            out["ok"] = False
            out["broken"].append({"name": name, "error": str(e)})
    return out


if __name__ == "__main__":
    print(json.dumps(validate_all(), indent=2))
