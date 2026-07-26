"""The single hardened-loop entry point: author the per-build INTENT CONTRACT, run the asset through the
fused weakest-link gate, and package the intent-vs-actual review. This is what the operator / Claude calls to
build ONE WANEFALL asset through the hardened loop, and what scripts/pipeline/run_dimwit.py's queue driver delegates to — so
there is exactly one wired path, not a hand-assembled one per caller.

Fail-closed throughout:
  * a strict asset_type with no real reference is BLOCKED at authoring (vacuous-target);
  * authoring is anti-retrofit — it REFUSES once capture pixels exist (declare intent BEFORE pixels);
  * the loop cannot reach PROMOTED_TO_REVIEW without real, measured captures that match the declared target;
  * the autonomy ceiling stays PROMOTED_TO_REVIEW — nothing here ever sets an OPERATOR_ONLY state.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import Lifecycle
from . import spec_author
from .engine import run_asset_task, DimwitLedger
from .review import build_review_package

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
_IMG_EXT = (".png", ".jpg", ".jpeg")


def _first_reference(task, explicit=None):
    """The declared reference image: an explicit arg wins, else the first image in task.source_paths."""
    if explicit:
        return explicit
    for p in (getattr(task, "source_paths", None) or []):
        if str(p).lower().endswith(_IMG_EXT) and Path(p).exists():
            return str(p)
    return None


def ensure_intent_contract(asset_id, asset_type, *, reference=None, declared_intent="",
                           assets_root=None, ledger=None, run_id="build", **author_kwargs):
    """Idempotently obtain the per-build intent contract.

    Returns (contract|None, path|None, status). status is 'loaded' if one was already anchored on disk,
    'authored' if freshly authored+anchored, or a BLOCK dict (ok=False) if authoring was refused (vacuous
    target / anti-retrofit / missing license). Loading an existing contract avoids the anti-retrofit refusal
    on recursion (author once before pixels; reuse thereafter)."""
    assets_root = Path(assets_root) if assets_root else ASSETS
    existing = assets_root / asset_id / "intent_contract.json"
    if existing.exists():
        try:
            return json.loads(existing.read_text(encoding="utf-8")), existing, "loaded"
        except Exception as e:
            return None, None, {"ok": False, "blocked": True, "reason": f"existing contract unreadable: {e}"}
    res = spec_author.author_intent_contract(
        asset_id, asset_type, reference, declared_intent=declared_intent,
        ledger=ledger, run_id=run_id, out_root=assets_root, **author_kwargs)
    if not res.get("ok"):
        return None, None, res
    return res["contract"], Path(res["contract_path"]), "authored"


def build_one(task, seed_spec, seed_evidence, ledger, run_id="build", *, reference=None,
              declared_intent="", render_fn=None, assets_root=None, review_root=None, author_kwargs=None):
    """Author-if-missing the intent contract, run the hardened fused-gate loop, package the review.

    Returns {asset_id, state, authoring, promoted, fused, contract, report, review_package}. When authoring is
    blocked (no usable reference for a strict type, or pixels already exist), returns state=BLOCKED and does
    NOT run the loop — you cannot certify a build against an intent you were not allowed to declare."""
    assets_root = Path(assets_root) if assets_root else ASSETS
    review_root = Path(review_root) if review_root else ROOT
    ref = _first_reference(task, reference)
    contract, cpath, status = ensure_intent_contract(
        task.asset_id, task.asset_type, reference=ref,
        declared_intent=declared_intent or getattr(task, "intended_gameplay_role", "") or "",
        assets_root=assets_root, ledger=ledger, run_id=run_id, **(author_kwargs or {}))
    if contract is None:
        return {"asset_id": task.asset_id, "state": Lifecycle.BLOCKED, "authoring": status,
                "promoted": False, "fused": None, "contract": None, "report": None,
                "review_package": None}

    report = run_asset_task(task, seed_spec, seed_evidence, ledger, run_id=run_id,
                            contract=contract, render_fn=render_fn)
    pkg = build_review_package(review_root, task.to_dict(), report.to_dict(), contract=contract)
    return {"asset_id": task.asset_id, "state": report.final_state, "authoring": status,
            "promoted": report.final_state == Lifecycle.PROMOTED_TO_REVIEW,
            "fused": report.fused, "contract": contract, "report": report, "review_package": pkg,
            "contract_path": str(cpath) if cpath else None}
