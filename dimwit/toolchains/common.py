"""Shared proof-bearing process helpers. Commands are always argv lists and never use a shell."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Callable


SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def atomic_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_file(path: Path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str | None:
    path = Path(path)
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update((sha256_file(child) or "").encode("ascii"))
    return digest.hexdigest()


def require_job_id(job_id: str) -> str:
    job_id = str(job_id)
    if not SAFE_ID.fullmatch(job_id):
        raise ValueError("job_id must contain only letters, numbers, dot, underscore, or hyphen")
    return job_id


def require_within(path: Path, roots: list[Path], label: str) -> Path:
    resolved = Path(path).resolve()
    allowed = [Path(root).resolve() for root in roots]
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed):
        raise ValueError(f"{label} escapes allowed roots: {resolved}")
    return resolved


def output_proofs(paths: list[Path]) -> list[dict]:
    proofs = []
    for path in paths:
        path = Path(path)
        exists = path.exists()
        if path.is_file():
            size = path.stat().st_size
            kind = "file"
        elif path.is_dir():
            size = sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
            kind = "directory"
        else:
            size, kind = 0, "missing"
        proofs.append({"path": str(path), "exists": exists,
                       "kind": kind, "bytes": size,
                       "sha256": sha256_tree(path) if exists else None})
    return proofs


def run_process(command: list[str], job_dir: Path, *, cwd: Path | None = None, timeout: float = 900,
                runner: Callable | None = None) -> dict:
    """Run an argv-only process and persist complete stdout/stderr receipts."""
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must be a non-empty argv string list")
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    runner = runner or subprocess.run
    started = time.time()
    try:
        completed = runner(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           timeout=float(timeout), shell=False)
        returncode = int(completed.returncode)
        stdout, stderr = completed.stdout or "", completed.stderr or ""
        timed_out, error = False, None
    except subprocess.TimeoutExpired as exc:
        returncode = -1
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        timed_out, error = True, f"timeout after {timeout}s"
    except OSError as exc:
        returncode, stdout, stderr = -1, "", ""
        timed_out, error = False, f"{type(exc).__name__}: {exc}"
    (job_dir / "stdout.log").write_text(stdout, encoding="utf-8", errors="replace")
    (job_dir / "stderr.log").write_text(stderr, encoding="utf-8", errors="replace")
    return {"returncode": returncode, "timed_out": timed_out, "error": error,
            "elapsed_seconds": round(time.time() - started, 3),
            "stdout_path": str(job_dir / "stdout.log"), "stderr_path": str(job_dir / "stderr.log"),
            "stdout_tail": stdout.splitlines()[-20:], "stderr_tail": stderr.splitlines()[-20:]}
