"""Codex partner — a PEER DRIVER of the WANEFALL build loop, bound by the SAME fail-closed gates and the SAME
PROMOTED_TO_REVIEW ceiling as Claude. Three modes (all identically gated):
  - partner : Claude dispatches a sub-task to Codex; Codex executes; this harness VALIDATES the result.
  - sub     : delegated execution of a scoped task.
  - failover: Codex drives the loop when Claude is unavailable ("ran out of data").

INVARIANT: Codex is never a new authority. Every Codex action is followed by the fail-closed validation suite
(`scripts/pipeline/run_validation.py`) PLUS a ceiling guard (no operator-only self-promotion). When Codex drives without Claude's
live eyes, the eyes-required validators STAY BLOCKED (fail-closed) — nothing eyes-gated can pass on Codex's watch.
Codex may NEVER write HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE, weaken a validator, or lower a floor.

  python scripts/pipeline/codex_partner.py --check               # is Codex installed/authed + ceiling-guard + baton state
  python scripts/pipeline/codex_partner.py --dry-run [--task T]  # structural cycle (no model call)
  python scripts/pipeline/codex_partner.py --smoke               # LIVE read-only proof Codex is callable as the failover
  python scripts/pipeline/codex_partner.py --task "..." [--no-ue]# dispatch a task to Codex, then VALIDATE + ceiling-guard
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODEX_HOME = Path(os.path.expanduser("~")) / ".codex"
HANDOFF = ROOT / "codex_handoff.json"
LOG = ROOT / "artifacts" / "codex_partner_log.jsonl"

# The doctrine preamble injected into EVERY dispatch (belt-and-suspenders with AGENTS.md, so the guardrails
# travel with the prompt even if Codex is run from a directory where AGENTS.md is not auto-discovered).
DOCTRINE = """You are CODEX, the PARTNER/FAILOVER to Claude on the WANEFALL game build. You drive the SAME gated
machinery and are NOT a new authority. NON-NEGOTIABLE, FAIL-CLOSED:
1. Ceiling = PROMOTED_TO_REVIEW. NEVER write HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE (operator-only).
2. NEVER weaken/delete/stub a validator or lower a threshold/floor. Gates may only be ADDED or hardened.
3. Fail-closed: missing evidence = BLOCKED, never a fake PASS. Never fabricate captures/result-JSON/provenance.
4. You have NO live "own eyes" (Claude's role): leave perception/optics/live-capture validators BLOCKED.
5. Operator-only (never do): sign in, pay, download-from-untrusted, design.md snapshot_baseline, Hi3D regen, GitHub push.
6. After ANY change, run `python scripts/pipeline/run_validation.py` (exit 0 only on PASS). Your change is a CANDIDATE until it passes. Stop at review.
Full doctrine in AGENTS.md. Work the task, run the gate, STOP at the review ceiling, report what you did + the verdict.
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log(entry: dict) -> dict:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now(), **entry}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry


def codex_available() -> dict:
    exe = shutil.which("codex") or shutil.which("codex.cmd")
    authed = (CODEX_HOME / "auth.json").exists()
    return {"installed": bool(exe), "exe": exe, "authenticated": authed, "ready": bool(exe) and authed}


def _codex_exe() -> str:
    return shutil.which("codex") or shutil.which("codex.cmd") or "codex"


def _codex_argv(sandbox: str, prompt_inline: str | None = None, reasoning: str = "medium") -> list[str]:
    """The codex sub-args for the LEAN FAILOVER profile. Config values are passed UNQUOTED: they fail TOML parse
    and codex falls back to the raw string literal (per `codex exec --help`), avoiding shell quote-mangling
    through the .CMD shim.

    SPEED: the operator's global ~/.codex/config.toml loads a `node_repl` MCP server with a 120s startup timeout
    plus a heavy plugin set (browser/chrome/presentations/...). NONE of that is needed to drive the loop (run
    python gates + edit code), and it dominates wall-clock. So the failover DISABLES MCP per-call
    (`mcp_servers={}`) to kill the startup tax, runs medium reasoning (operator's pick), and uses the flex tier.
    Escalate `reasoning` to 'xhigh' only for genuinely hard code tasks."""
    argv = ["exec",
            "-c", f"sandbox_mode={sandbox}",
            "-c", "approval_policy=never",
            # --- The four overrides that make headless exec actually WORK on this machine (each was a real bug): ---
            # 1. notify hook: ~/.codex/config.toml runs a computer-use exe on "turn-ended" that BLOCKS headless
            #    exec forever (every smoke hung 13-45 min). Clearing it is the critical un-hang.
            "-c", "notify=[]",
            # 2. service_tier: config carries "default" (CLI rejects: expects fast|flex) and the API REJECTS "flex"
            #    for this gpt-5.5 account ("Unsupported service_tier: flex"). "fast" is the one value that passes both.
            "-c", "service_tier=fast",
            # 3. MCP: the global node_repl MCP server has a 120s startup timeout the failover never needs.
            "-c", "mcp_servers={}",
            # 4. memories: headless runs hit "no such table: jobs" from the memories writer; disable to silence it.
            "-c", "features.memories=false",
            "-c", f"model_reasoning_effort={reasoning}",
            "--skip-git-repo-check"]
    argv.append(prompt_inline if prompt_inline is not None else "-")  # '-' => read prompt from stdin
    return argv


def _run_codex(argv: list[str], *, input_text: str | None, cwd: str, timeout: int) -> subprocess.CompletedProcess:
    """Windows npm ships `codex` as a .CMD shim; CreateProcess can't launch it directly, so route through cmd /c.
    Force UTF-8 on stdin/stdout: the prompt may carry non-ASCII (e.g. U+2212 minus); the Windows cp1252 default
    crashes the stdin writer thread mid-prompt and leaves Codex hung waiting for EOF."""
    exe = _codex_exe()
    full = (["cmd", "/c", exe] + argv) if os.name == "nt" else ([exe] + argv)
    return subprocess.run(full, input=input_text, cwd=cwd, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def dispatch(task: str, *, sandbox: str = "workspace-write", cwd: Path | None = None,
             reasoning: str = "medium", dry_run: bool = False, timeout: int = 1800) -> dict:
    av = codex_available()
    if not av["ready"]:
        return _log({"action": "dispatch", "ok": False, "blocked": True, "reason": "codex not ready", "av": av})
    prompt = DOCTRINE + "\n\n## TASK\n" + task
    if dry_run:
        return _log({"action": "dispatch", "dry_run": True, "sandbox": sandbox, "reasoning": reasoning,
                     "cmd": "codex " + " ".join(_codex_argv(sandbox, reasoning=reasoning)), "prompt_chars": len(prompt)})
    try:
        r = _run_codex(_codex_argv(sandbox, reasoning=reasoning), input_text=prompt, cwd=str(cwd or ROOT), timeout=timeout)
    except subprocess.TimeoutExpired:
        return _log({"action": "dispatch", "ok": False, "blocked": True, "reason": "codex timed out"})
    return _log({"action": "dispatch", "ok": r.returncode == 0, "exit": r.returncode,
                 "stdout_tail": (r.stdout or "")[-3000:], "stderr_tail": (r.stderr or "")[-800:]})


def ceiling_guard() -> dict:
    """HARD STOP: scan the Dimwit ledgers for an operator-only state written by a non-operator actor — Codex
    must never self-promote past the review ceiling. Mirrors the suite's v_no_autonomous_operator_states."""
    try:
        from dimwit.authority import is_ceiling_violation
    except Exception as e:
        return {"ok": False, "blocked": True, "reason": f"cannot import OPERATOR_ONLY: {e}"}
    led = ROOT / "ledger"
    bad = []
    files = list((led / "pipelines").glob("*.jsonl")) if (led / "pipelines").exists() else []
    files += [led / n for n in ("director.jsonl", "validation.jsonl") if (led / n).exists()]
    for lf in files:
        try:
            lines = lf.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for ln in lines:
            if not ln.strip():
                continue
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if is_ceiling_violation(e):
                bad.append({"ledger": lf.name,
                            "state": str(e.get("state", "")).split(".")[-1],
                            "actor": str(e.get("actor", ""))})
    return {"ok": not bad, "violations": bad}


def validate_after(*, no_ue: bool = False, timeout: int = 2400) -> dict:
    """Run the canonical fail-closed gate exactly as Claude/CI does. Exit 0 only on suite PASS."""
    rv = ROOT / "scripts/pipeline/run_validation.py"
    if not rv.exists():
        return {"ok": False, "blocked": True, "reason": "scripts/pipeline/run_validation.py missing"}
    cmd = [sys.executable, str(rv)] + (["--no-ue"] if no_ue else [])
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "blocked": True, "reason": "validation timed out"}
    return {"ok": r.returncode == 0, "suite_verdict": "PASS" if r.returncode == 0 else "NOT_PASS",
            "exit": r.returncode, "tail": (r.stdout or "")[-1500:]}


def partner_cycle(task: str, *, sandbox: str = "workspace-write", no_ue: bool = False, dry_run: bool = False) -> dict:
    """The safe peer-driver cycle: Codex executes -> harness VALIDATES -> ceiling guard. NEVER promotes."""
    d = dispatch(task, sandbox=sandbox, dry_run=dry_run)
    if dry_run:
        return {"phase": "dry_run", "dispatch": d, "note": "no model call; wiring only"}
    guard = ceiling_guard()
    val = validate_after(no_ue=no_ue)
    if not guard["ok"]:
        verdict = "BLOCKED_CEILING_VIOLATION"      # Codex tried to self-promote -> hard stop
    elif val.get("ok"):
        verdict = "VALIDATED_PROMOTED_TO_REVIEW"    # the ceiling — NOT acceptance; operator owns that
    elif d.get("ok"):
        verdict = "EXECUTED_VALIDATION_NOT_PASS"    # ran, but the gate is not green -> BLOCKED
    else:
        verdict = "DISPATCH_FAILED"
    out = {"task": task[:160], "dispatch_ok": d.get("ok"), "ceiling_guard": guard, "validation": val,
           "verdict": verdict, "ceiling": "PROMOTED_TO_REVIEW (operator owns acceptance)"}
    _log({"action": "partner_cycle", **{k: out[k] for k in ("task", "verdict", "dispatch_ok")}})
    return out


# ---------------------------------------------------------------- handoff baton
def handoff_write(driver: str, work_queue: list, note: str = "") -> dict:
    baton = {"updated": _now(), "driver": driver, "ceiling": "PROMOTED_TO_REVIEW",
             "operating_model": "work-queue -> orchestrate -> execute (Dimwit) -> validate (fail-closed) -> PROMOTED_TO_REVIEW -> human gate -> lessons",
             "gate_cmd": "python scripts/pipeline/run_validation.py", "loop_cmd": "python scripts/pipeline/run_director.py", "doctrine": "AGENTS.md",
             "work_queue": work_queue, "note": note}
    HANDOFF.write_text(json.dumps(baton, indent=2), encoding="utf-8")
    return baton


def handoff_read() -> dict:
    if not HANDOFF.exists():
        return {"error": "no handoff baton yet"}
    return json.loads(HANDOFF.read_text(encoding="utf-8"))


def smoke() -> dict:
    """LIVE read-only proof that Codex is callable as the failover (cannot touch the repo: read-only sandbox)."""
    av = codex_available()
    if not av["ready"]:
        return {"ok": False, "blocked": True, "reason": "codex not ready", "av": av}
    scratch = os.environ.get("TEMP") or str(ROOT)
    argv = _codex_argv("read-only",
                       "Reply with exactly the token DIMWIT_CODEX_OK and nothing else. Do not read or write any files.")
    try:
        r = _run_codex(argv, input_text=None, cwd=scratch, timeout=300)
    except subprocess.TimeoutExpired:
        return {"ok": False, "blocked": True, "reason": "smoke timed out (>300s)"}
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    return _log({"action": "smoke", "ok": "DIMWIT_CODEX_OK" in out, "exit": r.returncode,
                 "saw_token": "DIMWIT_CODEX_OK" in out, "tail": out[-900:]})


def _arg(argv, k):
    return argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None


def main(argv) -> int:
    if "--check" in argv:
        print(json.dumps({"codex": codex_available(), "ceiling_guard": ceiling_guard(),
                          "handoff_present": HANDOFF.exists(), "agents_md": (ROOT / "AGENTS.md").exists()},
                         indent=2))
        return 0
    if "--smoke" in argv:
        print(json.dumps(smoke(), indent=2))
        return 0
    if "--dry-run" in argv:
        print(json.dumps(partner_cycle(_arg(argv, "--task") or "DRY RUN: confirm wiring only.", dry_run=True),
                         indent=2, default=str))
        return 0
    if "--task" in argv:
        print(json.dumps(partner_cycle(_arg(argv, "--task"), no_ue="--no-ue" in argv), indent=2, default=str))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
