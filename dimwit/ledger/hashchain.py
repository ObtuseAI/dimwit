"""Tamper-evident hash chaining for Dimwit's append-only proof ledger.

Each entry carries `prev_hash` (the previous entry's `entry_hash`) + `entry_hash` = sha256 over
{prev_hash, payload}, where payload is the entry minus the two hash fields. Any edit to a past entry
breaks every link after it. Pure stdlib; reuses `core.sha256_obj`.

Legacy-tolerant: entries written before chaining (no hash fields) are skipped as `legacy` and reset the
running prev to GENESIS, so a ledger that starts unchained and becomes chained still verifies cleanly.
"""
from __future__ import annotations

from ..core import sha256_obj

GENESIS = "0" * 64


def _payload(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}


def compute_entry_hash(entry: dict, prev_hash: str) -> str:
    return sha256_obj({"prev_hash": prev_hash, "payload": _payload(entry)})


def chain_entry(entry: dict, prev_hash: str) -> dict:
    """Return a copy of `entry` stamped with prev_hash + entry_hash."""
    e = dict(entry)
    e["prev_hash"] = prev_hash
    e["entry_hash"] = compute_entry_hash(e, prev_hash)
    return e


def chain_verify(entries: list) -> dict:
    """Recompute the whole chain. Returns {ok, length, chained, legacy, mid_ledger_legacy, head} or
    {ok:False, broken_at, reason}.

    A *leading* run of legacy (pre-chaining) entries is tolerated (a ledger that started unchained and later
    became chained still verifies). But a legacy entry that appears AFTER any chained entry is treated as
    tamper evidence (`mid_ledger_legacy`) — the classic "strip the hash fields off a middle entry and let the
    chain restart from GENESIS" forgery — and fails the chain. (validation §Phase 0)"""
    prev = GENESIS
    legacy = 0
    chained = 0
    mid_ledger_legacy = False
    for i, e in enumerate(entries):
        if "entry_hash" not in e and "prev_hash" not in e:
            legacy += 1
            if chained > 0:
                mid_ledger_legacy = True         # legacy AFTER a chained entry -> re-chain forgery / corruption
            prev = GENESIS                        # unchained legacy entry — chain (re)starts after it
            continue
        if e.get("prev_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "prev_hash mismatch", "legacy": legacy,
                    "chained": chained, "mid_ledger_legacy": mid_ledger_legacy}
        if e.get("entry_hash") != compute_entry_hash(e, prev):
            return {"ok": False, "broken_at": i, "reason": "entry_hash mismatch", "legacy": legacy,
                    "chained": chained, "mid_ledger_legacy": mid_ledger_legacy}
        prev = e["entry_hash"]
        chained += 1
    return {"ok": not mid_ledger_legacy, "length": len(entries), "chained": chained, "legacy": legacy,
            "mid_ledger_legacy": mid_ledger_legacy, "head": prev}
