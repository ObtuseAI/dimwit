"""Auditable repair utilities for Rainman JSONL hash-chain ledgers.

The repair path is intentionally narrow: it never edits the semantic payload of
an entry. It backs up the original ledger, strips only hash fields, rebuilds a
canonical chain, and writes a report proving payload preservation.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Iterable

from ..core import sha256_obj
from .hashchain import GENESIS, chain_entry, chain_verify
from .locking import ledger_lock


HASH_FIELDS = ("prev_hash", "entry_hash")


def payload(entry: dict) -> dict:
    """Return the hash-chain payload, excluding hash metadata."""
    return {key: value for key, value in entry.items() if key not in HASH_FIELDS}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    entries: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL entry: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_number}: ledger entry is not an object")
        entries.append(item)
    return entries


def write_jsonl(path: Path, entries: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def _chain_summary(entries: list[dict]) -> dict:
    chain = chain_verify(entries)
    return {
        "entry_count": len(entries),
        "chain_ok": bool(chain.get("ok")),
        "head": chain.get("head") or (entries[-1].get("entry_hash") if entries else GENESIS),
        "chain": chain,
    }


def rechain_entries(entries: list[dict]) -> list[dict]:
    """Return entries rebuilt into one canonical hash chain with payloads intact."""
    repaired: list[dict] = []
    head = GENESIS
    for entry in entries:
        chained = chain_entry(payload(entry), head)
        repaired.append(chained)
        head = chained["entry_hash"]
    return repaired


def repair_ledger_chain(path: Path | str, *, backup_dir: Path | str, reason: str = "manual-rechain") -> dict:
    """Repair a broken JSONL hash-chain ledger while preserving every payload.

    Returns the audit report that is also written to `backup_dir`.
    """
    ledger_path = Path(path)
    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Hold the same cross-process lock the appender uses: an append landing between our read and the
    # atomic replace would otherwise be silently discarded (or re-fork the chain we just repaired).
    with ledger_lock(ledger_path):
        original_entries = read_jsonl(ledger_path)
        original_payloads = [payload(entry) for entry in original_entries]
        original_payload_digest = sha256_obj(original_payloads)
        original_summary = _chain_summary(original_entries)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = out_dir / f"{ledger_path.stem}_pre_repair_{stamp}.jsonl"
        report_path = out_dir / f"{ledger_path.stem}_repair_report_{stamp}.json"
        shutil.copy2(ledger_path, backup_path)

        repaired_entries = rechain_entries(original_entries)
        repaired_payloads = [payload(entry) for entry in repaired_entries]
        repaired_payload_digest = sha256_obj(repaired_payloads)
        payloads_preserved = repaired_payload_digest == original_payload_digest and repaired_payloads == original_payloads
        if not payloads_preserved:
            raise RuntimeError("ledger repair refused: payload digest changed during rechain")

        write_jsonl(ledger_path, repaired_entries)
        repaired_summary = _chain_summary(repaired_entries)
        if not repaired_summary["chain_ok"]:
            raise RuntimeError(f"ledger repair wrote a non-verifying chain: {repaired_summary['chain']}")

    report = {
        "operation": "RECHAIN_PRESERVE_PAYLOADS",
        "reason": reason,
        "ledger_path": str(ledger_path),
        "backup_path": str(backup_path),
        "report_path": str(report_path),
        "payloads_preserved": payloads_preserved,
        "payload_digest_before": original_payload_digest,
        "payload_digest_after": repaired_payload_digest,
        "original": original_summary,
        "repaired": repaired_summary,
        "hash_fields_rebuilt": list(HASH_FIELDS),
        "generated_at": time.time(),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _main() -> int:
    parser = argparse.ArgumentParser(description="Repair a Rainman JSONL hash-chain ledger without changing payloads.")
    parser.add_argument("ledger", type=Path)
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--reason", default="manual-rechain")
    args = parser.parse_args()
    report = repair_ledger_chain(args.ledger, backup_dir=args.backup_dir, reason=args.reason)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
