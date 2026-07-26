"""Cross-process lock for proof-ledger writes (PROOF_LEDGER_CONCURRENCY_SEAL_V1).

Overlapping validation/director runs previously appended to the same JSONL with each writer
chaining from a construction-time cached head — forking the hash chain and, under true
simultaneity, interleaving partial lines. Every ledger write must hold this lock and re-read
the on-disk head inside it.

Windows byte-range lock via msvcrt (this repo's platform), fcntl fallback elsewhere. The lock
lives in a `<ledger>.lock` sidecar so the ledger file itself stays append-only.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path

try:  # Windows
    import msvcrt

    def _try_lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

except ImportError:  # POSIX
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def ledger_lock(target_path: Path, timeout_s: float = 30.0, poll_s: float = 0.02):
    """Exclusive cross-process lock guarding writes to `target_path`. Fail-closed: raises
    TimeoutError rather than proceeding unlocked."""
    lock_path = Path(str(target_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Initialize the byte on a separate handle before any process can lock it.  Initializing and
    # locking through the same handle races on Windows: process A may acquire the byte-range lock
    # after process B's size check but before B flushes its first byte, producing PermissionError.
    # Multiple pre-lock writers of the same sentinel byte are harmless; a locked-file conflict is
    # retried until the regular acquisition deadline.
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with open(lock_path, "a+b") as initializer:
                if initializer.seek(0, 2) == 0:
                    initializer.write(b"\0")
                    initializer.flush()
            break
        except (OSError, PermissionError):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"ledger lock byte not initialized within {timeout_s}s: {lock_path}")
            time.sleep(poll_s)
    handle = open(lock_path, "r+b")
    try:
        while True:
            try:
                _try_lock(handle)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"ledger lock not acquired within {timeout_s}s: {lock_path}")
                time.sleep(poll_s)
        try:
            yield
        finally:
            try:
                _unlock(handle)
            except OSError:
                pass
    finally:
        handle.close()
