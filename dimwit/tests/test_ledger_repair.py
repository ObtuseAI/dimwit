from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.ledger.hashchain import chain_entry, chain_verify
from dimwit.ledger.repair import repair_ledger_chain


TMP = Path(tempfile.mkdtemp(prefix="dimwit_ledger_repair_"))


def _payload(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_repair_rechains_branched_ledger_without_changing_payloads():
    ledger_path = TMP / "ledger" / "validation.jsonl"
    backup_dir = TMP / "artifacts" / "proof_integrity"

    entries: list[dict] = []
    head = "0" * 64
    for index in range(5):
        entry = {
            "ts": 1782710000 + index,
            "actor": "validation_suite",
            "asset_id": f"validator_{index}",
            "state": "PASS",
            "candidate_hash": f"candidate_{index}",
            "payload": {"index": index},
        }
        chained = chain_entry(entry, head)
        entries.append(chained)
        head = chained["entry_hash"]

    branched = dict(entries[4])
    branched["prev_hash"] = entries[1]["entry_hash"]
    entries[4] = chain_entry(_payload(branched), branched["prev_hash"])
    assert chain_verify(entries)["ok"] is False

    original_payloads = [_payload(entry) for entry in entries]
    _write_jsonl(ledger_path, entries)

    report = repair_ledger_chain(ledger_path, backup_dir=backup_dir, reason="unit-test-branched-head")

    repaired = _read_jsonl(ledger_path)
    assert chain_verify(repaired)["ok"] is True
    assert [_payload(entry) for entry in repaired] == original_payloads
    assert Path(report["backup_path"]).exists()
    assert Path(report["report_path"]).exists()
    assert report["payloads_preserved"] is True
    assert report["original"]["chain_ok"] is False
    assert report["repaired"]["chain_ok"] is True
    assert report["repaired"]["entry_count"] == len(entries)


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
