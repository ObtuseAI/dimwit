"""Local-only Studio IDE server with allowlisted, proof-visible actions.

The IDE is an operator surface, not a new authority tier. It binds only to 127.0.0.1, requires a random
per-process token for every non-health API, confines source reads to first-party roots, and exposes only fixed
commands. There is no arbitrary shell, provider call, download, install, promotion, or studio execution action.
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dimwit.evolution.diversity import build_diversity_plan
from dimwit.improvement_outcomes import summarize_outcomes
from dimwit.opensource_adoption import audit_ecosystem
from dimwit.toolchains.studio import StudioController
from dimwit.toolchains.engines.universal import audit_engines
from dimwit.toolchains.mobile import audit_mobile


ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"
SOURCE_ROOTS = (ROOT / "dimwit", ROOT / "config", ROOT / "docs")
SOURCE_SUFFIXES = frozenset({".py", ".json", ".md", ".txt", ".ini", ".toml", ".css", ".js", ".html"})
MAX_SOURCE_BYTES = 200_000
MAX_OUTPUT_CHARS = 80_000
REVIEW_CEILING = "PROMOTED_TO_REVIEW"
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|secret|password)(\s*[=:]\s*|\s+)([^\s,;\"']+)"
)


ACTION_COMMANDS = {
    "studio_plan": {
        "label": "Refresh studio plan", "argv": (sys.executable, "dimwit.py", "studio"),
        "description": "Plan the 22-node game-production DAG without mutation.",
    },
    "improvement_plan": {
        "label": "Plan recursive improvement", "argv": (sys.executable, "dimwit.py", "improve"),
        "description": "Rank review-bounded experiments from current validator evidence.",
    },
    "ecosystem_audit": {
        "label": "Audit open-source ecosystem", "argv": (sys.executable, "dimwit.py", "ecosystem"),
        "description": "Audit license, risk, fit, and local presence; no installs.",
    },
    "slice_tests": {
        "label": "Run IDE and evolution tests",
        "argv": (sys.executable, "-m", "pytest", "dimwit/tests/test_studio_ide.py",
                 "dimwit/tests/test_diversity_and_ecosystem.py", "-q"),
        "description": "Run the bounded IDE/evolution safety regression slice.",
    },
    "validate_full": {
        "label": "Run authoritative validation", "argv": (sys.executable, "scripts/pipeline/run_validation.py"),
        "description": "Run the full fail-closed validator suite; this may take several minutes.",
    },
    "engine_audit": {
        "label": "Audit universal engines", "argv": (sys.executable, "dimwit.py", "engines"),
        "description": "Inventory eight engine adapters and their exact local blockers.",
    },
    "mobile_audit": {
        "label": "Audit mobile factory", "argv": (sys.executable, "dimwit.py", "mobile"),
        "description": "Audit Android, iOS, device, quality, and store-readiness gates.",
    },
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _ledger_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except ValueError:
            continue
    return rows


def _validation_summary(report: dict) -> dict:
    rows = [row for row in report.get("results", []) if isinstance(row, dict)]
    non_pass = [
        {"domain": row.get("domain"), "validator": row.get("validator_id"), "state": row.get("state"),
         "reason": row.get("reason") or row.get("detail")}
        for row in rows if str(row.get("state") or "").upper() != "PASS"
    ]
    return {
        "verdict": report.get("suite_verdict", "NOT_RUN"), "counts": report.get("counts", {}),
        "total": sum(int(value or 0) for value in (report.get("counts") or {}).values()),
        "run_ts": report.get("run_ts"), "non_pass": non_pass[:20],
    }


def build_workspace_state() -> dict:
    report = _read_json(ROOT / "artifacts" / "validation" / "validation_report_full.json", {})
    studio = StudioController().plan()
    experiments = _ledger_entries(ROOT / "ledger" / "improvement_experiments.jsonl")
    diversity = build_diversity_plan(experiments)
    ecosystem = audit_ecosystem()
    engines = audit_engines()
    outcomes = summarize_outcomes(ROOT / "ledger" / "improvement_experiments.jsonl",
                                  ROOT / "ledger" / "improvement_outcomes.jsonl")
    cross_engine = _read_json(ROOT / "artifacts" / "toolchains" / "universal" / "cross_engine_proof.json",
                              {"state": "NOT_RUN", "engines": [], "comparable": False, "issues": ["proof not run"]})
    mobile = audit_mobile()
    registry = _read_json(ROOT / "config" / "capability_registry.json", {"capabilities": []})
    completed = studio.get("complete", 0)
    total = studio.get("total", 0)
    next_nodes = [row for row in studio.get("nodes", []) if row.get("deps_ready") and row.get("status") not in {"PASS", "REVIEW_READY"}]
    latest = experiments[-8:][::-1]
    review_ready = [
        {"task_key": (row.get("detail") or {}).get("task_key"), "ts": row.get("ts"),
         "status": "REVIEW_ELIGIBLE_ONLY"}
        for row in experiments if (row.get("detail") or {}).get("eligible_for_review")
    ][-8:][::-1]
    preflight = _read_json(
        ROOT / "artifacts" / "studio" / "wanefall_elite_full_game" / "state.json", {}
    ).get("nodes", {}).get("toolchain_preflight", {}).get("detail", {})
    return {
        "schema_version": 1, "product": "DIMWIT STUDIO", "local_only": True,
        "review_ceiling": REVIEW_CEILING, "generated_at": int(time.time()),
        "validation": _validation_summary(report),
        "studio": {**studio, "progress_percent": round(completed / total * 100, 2) if total else 0,
                   "next_nodes": next_nodes[:6]},
        "toolchains": {
            "blender": preflight.get("blender", {"ok": False, "version": "No preflight evidence"}),
            "unreal": preflight.get("unreal", {"ok": False, "version": "No preflight evidence"}),
        },
        "evolution": diversity,
        "improvement_outcomes": outcomes,
        "ecosystem": {
            "state": ecosystem["state"], "candidate_count": ecosystem["candidate_count"],
            "recommended_now": ecosystem["recommended_now"], "evaluation_queue": ecosystem["evaluation_queue"],
            "top": ecosystem["ranked_candidates"][:6],
        },
        "engines": engines,
        "cross_engine": cross_engine,
        "mobile": mobile,
        "capabilities": {"count": len(registry.get("capabilities", [])), "items": registry.get("capabilities", [])},
        "activity": {"recent_experiments": latest, "review_queue": review_ready},
        "boundaries": [
            "Localhost only", "No arbitrary shell", "No provider or paid calls", "No installs or downloads",
            "No automatic acceptance", f"Ceiling: {REVIEW_CEILING}",
        ],
    }


def _allowed_source(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.suffix.lower() in SOURCE_SUFFIXES and any(
        resolved == root.resolve() or root.resolve() in resolved.parents for root in SOURCE_ROOTS
    ) and not any(part.lower() in {".git", "__pycache__", "secrets", "private"} for part in resolved.parts)


def search_source(query: str, limit: int = 40) -> list[dict]:
    needle = str(query or "").strip().lower()
    if len(needle) < 2:
        return []
    matches = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not _allowed_source(path) or path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            relative = path.relative_to(ROOT).as_posix()
            if needle in relative.lower():
                matches.append({"path": relative, "name": path.name, "bytes": path.stat().st_size})
            if len(matches) >= limit:
                return sorted(matches, key=lambda row: (len(row["path"]), row["path"]))
    return sorted(matches, key=lambda row: (len(row["path"]), row["path"]))[:limit]


def read_source(relative: str) -> dict:
    raw = str(relative or "").replace("\\", "/")
    path = (ROOT / raw).resolve()
    if not _allowed_source(path) or not path.is_file():
        raise ValueError("source path is outside the first-party read boundary")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source file exceeds the IDE read limit")
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "content": path.read_text(encoding="utf-8", errors="replace")}


def redact_output(value: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", str(value))[-MAX_OUTPUT_CHARS:]


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._processes: dict[str, subprocess.Popen] = {}

    def list(self) -> list[dict]:
        with self._lock:
            return sorted((dict(job) for job in self._jobs.values()), key=lambda row: row["created_at"], reverse=True)[:20]

    def start(self, action: str) -> dict:
        spec = ACTION_COMMANDS.get(action)
        if spec is None:
            raise ValueError("action is not allowlisted")
        job_id = secrets.token_hex(8)
        job = {"id": job_id, "action": action, "label": spec["label"], "description": spec["description"],
               "status": "queued", "created_at": time.time(), "output": "", "return_code": None}
        with self._lock:
            self._jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id, spec), daemon=True).start()
        return dict(job)

    def _run(self, job_id: str, spec: dict) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = time.time()
        try:
            process = subprocess.Popen(
                list(spec["argv"]), cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", shell=False,
            )
            with self._lock:
                self._processes[job_id] = process
            output, _ = process.communicate(timeout=900)
            with self._lock:
                self._jobs[job_id].update({
                    "status": "completed" if process.returncode == 0 else "failed",
                    "return_code": process.returncode, "output": redact_output(output), "finished_at": time.time(),
                })
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            with self._lock:
                self._jobs[job_id].update({"status": "failed", "return_code": -1,
                                           "output": redact_output(output + "\nTIMEOUT"), "finished_at": time.time()})
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update({"status": "failed", "return_code": -1,
                                           "output": f"{type(exc).__name__}: {exc}", "finished_at": time.time()})
        finally:
            with self._lock:
                self._processes.pop(job_id, None)


class StudioIDERequestHandler(BaseHTTPRequestHandler):
    server_version = "DimwitStudioIDE/1"

    def log_message(self, fmt: str, *args) -> None:
        return

    @property
    def app(self):
        return self.server.app  # type: ignore[attr-defined]

    def _headers(self, status: int = 200, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._headers(status)
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Dimwit-Token", "")
        return bool(supplied) and hmac.compare_digest(supplied, self.app.token)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._json({"ok": True, "service": "dimwit-studio-ide", "local_only": True})
            return
        if parsed.path == "/favicon.ico":
            self._headers(HTTPStatus.NO_CONTENT, "image/x-icon")
            return
        if parsed.path.startswith("/api/") and not self._require_auth():
            return
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/state":
            self._json(build_workspace_state())
        elif parsed.path == "/api/jobs":
            self._json({"jobs": self.app.jobs.list()})
        elif parsed.path == "/api/source":
            self._json({"results": search_source((query.get("q") or [""])[0])})
        elif parsed.path == "/api/file":
            try:
                self._json(read_source((query.get("path") or [""])[0]))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        else:
            self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/actions":
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            size = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
            payload = json.loads(self.rfile.read(size) or b"{}")
            self._json(self.app.jobs.start(str(payload.get("action") or "")), HTTPStatus.ACCEPTED)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _static(self, request_path: str) -> None:
        name = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        path = (STATIC / name).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8"}.get(path.suffix, "application/octet-stream")
        self._headers(200, content_type)
        self.wfile.write(path.read_bytes())


class StudioIDEApp:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or secrets.token_urlsafe(24)
        self.jobs = JobStore()


def create_server(port: int = 8765, token: str | None = None) -> ThreadingHTTPServer:
    if not 0 <= int(port) <= 65535:
        raise ValueError("port is outside the valid range")
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), StudioIDERequestHandler)
    server.app = StudioIDEApp(token)  # type: ignore[attr-defined]
    return server


def serve(port: int = 8765, open_browser: bool = True) -> None:
    server = create_server(port)
    actual_port = server.server_address[1]
    token = server.app.token  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{actual_port}/?token={urllib.parse.quote(token)}"
    print(f"Dimwit Studio IDE: {url}")
    print("Local-only. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
