"""Regression tests for proof-ledger append concurrency (bundle: PROOF_LEDGER_CONCURRENCY_SEAL_V1).

The 2026-06-29..07-01 chain breaks were caused by concurrent/overlapping validation runs: each
DimwitLedger cached the chain head at construction, so two writers chained from the same stale
head and forked the chain. These tests pin the required behavior: every append must chain from
the CURRENT on-disk head under a cross-process lock, so interleaved writers can never fork it.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dimwit.engine import DimwitLedger
from dimwit.ledger.hashchain import chain_verify

TMP = Path(tempfile.mkdtemp(prefix="dimwit_ledger_concurrency_"))
DIMWIT_ROOT = Path(__file__).resolve().parents[2]


def _entry(actor: str, i: int) -> dict:
    return {"ts": 1782900000 + i, "actor": actor, "asset_id": f"asset_{actor}_{i}",
            "state": "PASS", "candidate_hash": f"cand_{actor}_{i}", "detail": {"i": i}}


def _read_entries(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_append_rechains_from_current_disk_head_across_instances():
    """Two live ledger instances (as in two overlapping validation runs) must never fork the chain.

    Instance B is constructed BEFORE instance A appends, so B's constructor-cached head is stale by
    the time B appends. A correct writer re-reads the head from disk at append time.
    """
    path = TMP / "two_instances" / "validation.jsonl"
    a = DimwitLedger(path)
    b = DimwitLedger(path)          # both now believe head == GENESIS

    a.append(_entry("run_a", 0))     # head moves on disk
    b.append(_entry("run_b", 0))     # must chain from run_a's entry, not stale GENESIS
    a.append(_entry("run_a", 1))     # must chain from run_b's entry
    b.append(_entry("run_b", 1))

    ents = _read_entries(path)
    verdict = chain_verify(ents)
    assert len(ents) == 4
    assert verdict["ok"] is True, f"chain forked by stale cached head: {verdict}"
    assert verdict["chained"] == 4


_WORKER_CODE = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[4])
from dimwit.engine import DimwitLedger

ledger_path, go_file, tag = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
count = int(sys.argv[5])
led = DimwitLedger(ledger_path)              # construct (and cache head) BEFORE the go signal
deadline = time.monotonic() + 30.0
while not go_file.exists():
    if time.monotonic() > deadline:
        raise SystemExit("go file never appeared")
    time.sleep(0.005)
for i in range(count):
    led.append({"ts": 1782900000 + i, "actor": f"proc_{tag}", "asset_id": f"asset_{tag}_{i}",
                "state": "PASS", "candidate_hash": f"cand_{tag}_{i}", "detail": {"i": i}})
"""


def test_concurrent_process_appends_keep_chain_intact():
    """Four processes appending simultaneously (like overlapping suite runs) must keep chain_ok True."""
    workdir = TMP / "multi_process"
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "validation.jsonl"
    go_file = workdir / "go"
    n_procs, n_each = 4, 25

    procs = [subprocess.Popen(
        [sys.executable, "-c", _WORKER_CODE, str(path), str(go_file), str(t), str(DIMWIT_ROOT), str(n_each)],
        cwd=str(DIMWIT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE) for t in range(n_procs)]
    time.sleep(1.0)                   # let every worker construct its ledger (and cache a common head)
    go_file.write_text("go", encoding="utf-8")

    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f"worker failed: {err.decode(errors='replace')[:2000]}"

    ents = _read_entries(path)
    verdict = chain_verify(ents)
    assert len(ents) == n_procs * n_each, f"lost/duplicated entries: {len(ents)}"
    assert verdict["ok"] is True, f"concurrent appends forked the chain: {verdict}"
    assert verdict["chained"] == n_procs * n_each


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
