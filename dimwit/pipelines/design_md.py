"""Dimwit DESIGN.md gate — the declared WANEFALL visual law as a fail-closed validator domain.

Incorporates Google Labs' DESIGN.md format (https://github.com/google-labs-code/design.md): a persistent,
agent-readable visual-identity spec (YAML tokens + normative prose) that BOTH Claude (validator rubric) and
Dimwit (this gate) read. The canonical law lives at <WanefallGreybox>/DESIGN.md.

Three gates, all fail-closed (missing CLI / missing file / unreadable output -> BlockedError -> BLOCKED, never PASS):

  1. design_md_lint_no_errors        — `design.md lint` must report 0 errors (warnings are advisory; the doc
                                        documents its own intentional warning set). Errors == structural breakage
                                        of the law (bad token ref, malformed color, invalid component sub-token).
  2. design_md_no_baseline_regression — `design.md diff baseline current` must NOT report a regression. Catches a
                                        silent erosion of the identity (a token deleted, a contrast dropped). The
                                        baseline is an explicit, operator-established snapshot (snapshot_baseline()).
  3. design_md_synced_to_code         — the DESIGN.md camera-grading law must still mirror the SHIPPING C++ values
                                        (FP/TP WhiteTemp + exposure). Anti-drift: code and law cannot diverge
                                        silently. This is the gate that makes the law REAL rather than decorative.

The CLI is the design.md clone at C:/Users/developer/design.md run through bun (no build needed; bun runs the TS).
Override either via env: DESIGN_MD_CLI (path to packages/cli/src/index.ts) and DESIGN_MD_BUN (path to bun.exe).

DOCTRINE PRESERVED: warnings never block (only errors + diff-regressions + code-drift do); the gate never weakens
a validator to silence a warning; a missing toolchain BLOCKS (honest) rather than passing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from dimwit.pipelines.validation import (
    Validator, Severity as S, ProbeType as P, ROOT, PROJECT, ok, fail,
)
from dimwit.pipelines.base import Verdict, BlockedError

DESIGN_MD = PROJECT / "DESIGN.md"
BASELINE = ROOT / "config" / "design_md" / "baseline.DESIGN.md"
CPP = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"

# The camera-grading invariants that MUST appear identically in both the C++ and the DESIGN.md `cameras` group.
# (label, regex over the .cpp) -> the captured number is required, verbatim, somewhere in DESIGN.md.
_CODE_ANCHORS = [
    ("FP.WhiteTemp",         r"FP\.WhiteTemp\s*=\s*([\d.]+?)f?\s*;"),
    ("FP.AutoExposureBias",  r"FP\.AutoExposureBias\s*=\s*([\d.]+?)f?\s*;"),
    ("FP.ExposureMin",       r"FP\.AutoExposureMinBrightness\s*=\s*([\d.]+?)f?\s*;"),
    ("FP.ExposureMax",       r"FP\.AutoExposureMaxBrightness\s*=\s*([\d.]+?)f?\s*;"),
    ("TP.WhiteTemp",         r"TP\.WhiteTemp\s*=\s*([\d.]+?)f?\s*;"),
    ("TP.AutoExposureBias",  r"TP\.AutoExposureBias\s*=\s*([\d.]+?)f?\s*;"),
    ("TP.ExposureMin",       r"TP\.AutoExposureMinBrightness\s*=\s*([\d.]+?)f?\s*;"),
    ("TP.ExposureMax",       r"TP\.AutoExposureMaxBrightness\s*=\s*([\d.]+?)f?\s*;"),
]


# ------------------------------------------------------------------ CLI resolution (fail-closed)
def _resolve_bun() -> str:
    cand = []
    env = os.environ.get("DESIGN_MD_BUN")
    if env:
        cand.append(Path(env))
    which = shutil.which("bun.exe") or shutil.which("bun")
    if which:
        w = Path(which)
        # a .CMD/.cmd shim cannot be CreateProcess'd directly — resolve the real exe next to the npm global.
        cand.append(w.parent / "node_modules" / "bun" / "bin" / "bun.exe")
        if w.suffix.lower() == ".exe":
            cand.append(w)
    cand += [
        Path.home() / ".bun" / "bin" / "bun.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "bun" / "bin" / "bun.exe",
    ]
    for c in cand:
        if c and c.exists():
            return str(c)
    raise BlockedError("bun executable not found (design.md CLI needs bun; set DESIGN_MD_BUN)")


def _resolve_cli() -> str:
    env = os.environ.get("DESIGN_MD_CLI")
    cands = [Path(env)] if env else []
    cands += [
        Path("C:/Users/developer/design.md/packages/cli/src/index.ts"),
        Path.home() / "design.md" / "packages" / "cli" / "src" / "index.ts",
    ]
    for c in cands:
        if c and c.exists():
            return str(c)
    raise BlockedError("design.md CLI clone not found (set DESIGN_MD_CLI to packages/cli/src/index.ts)")


def _run_cli(args: list, timeout: int = 120) -> dict:
    """Run `bun run <cli> <args...> --format=json` and return parsed JSON. Fail-closed on every failure mode."""
    bun, cli = _resolve_bun(), _resolve_cli()
    cmd = [bun, "run", cli] + args + ["--format=json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(Path(cli).parents[3]))   # repo root (…/design.md)
    except subprocess.TimeoutExpired:
        raise BlockedError(f"design.md CLI timed out: {' '.join(args)}")
    except OSError as e:
        raise BlockedError(f"design.md CLI could not launch: {e}")
    out = (r.stdout or "").strip()
    if not out:
        raise BlockedError(f"design.md CLI emitted no JSON (stderr: {(r.stderr or '')[:200]})")
    # the CLI may print a banner line before the JSON object; slice from the first brace.
    brace = out.find("{")
    if brace < 0:
        raise BlockedError(f"design.md CLI emitted no JSON object: {out[:200]}")
    try:
        return json.loads(out[brace:])
    except Exception as e:
        raise BlockedError(f"design.md CLI JSON unreadable: {e}")


# ------------------------------------------------------------------ validators
def v_design_md_lint(ctx) -> Verdict:
    if not DESIGN_MD.exists():
        raise BlockedError(f"DESIGN.md missing at {DESIGN_MD} (the visual law is not committed)")
    data = _run_cli(["lint", str(DESIGN_MD)])
    summ = data.get("summary") or {}
    errors = summ.get("errors")
    if errors is None:
        raise BlockedError("design.md lint produced no summary.errors")
    if errors > 0:
        errs = [f.get("message") for f in data.get("findings", []) if f.get("severity") == "error"][:8]
        return fail(issues=[f"DESIGN.md has {errors} lint error(s)"] + errs, hard=True,
                    errors=errors, warnings=summ.get("warnings"))
    return ok(errors=0, warnings=summ.get("warnings"), infos=summ.get("infos"))


def v_design_md_no_regression(ctx) -> Verdict:
    if not DESIGN_MD.exists():
        raise BlockedError(f"DESIGN.md missing at {DESIGN_MD}")
    if not BASELINE.exists():
        raise BlockedError(
            f"no DESIGN.md baseline at {BASELINE} — establish one with "
            f"`python -c \"from dimwit.pipelines.design_md import snapshot_baseline; snapshot_baseline()\"` "
            f"(operator-gated: only snapshot a baseline you've reviewed)")
    data = _run_cli(["diff", str(BASELINE), str(DESIGN_MD)])
    if data.get("regression") is True:
        offenders = [f.get("message") for f in data.get("findings", [])
                     if f.get("severity") in ("error", "warning")][:8]
        return fail(issues=["DESIGN.md regressed vs baseline"] + offenders, hard=True,
                    regression=True, token_changes=len(data.get("tokens", []) or []))
    return ok(regression=False, token_changes=len(data.get("tokens", []) or []))


def v_design_md_synced_to_code(ctx) -> Verdict:
    """Anti-drift: every camera-grading constant in the shipping C++ must be present, verbatim, in the DESIGN.md
    `cameras` law. If a value changes in code but not in the law (or vice-versa), the law is lying -> fail."""
    if not CPP.exists():
        raise BlockedError(f"camera source missing: {CPP}")
    if not DESIGN_MD.exists():
        raise BlockedError(f"DESIGN.md missing at {DESIGN_MD}")
    cpp = CPP.read_text(encoding="utf-8", errors="replace")
    law = DESIGN_MD.read_text(encoding="utf-8", errors="replace")
    drift, checked = [], 0
    for label, pat in _CODE_ANCHORS:
        m = re.search(pat, cpp)
        if not m:
            raise BlockedError(f"could not read {label} from {CPP.name} (regex drift)")
        val = m.group(1).rstrip(".")            # 1.5 / 0.10 / 5600  (cpp writes 5600.0 -> normalize below)
        checked += 1
        # accept both the cpp literal and its trimmed form (5600.0 -> 5600, 1.50 -> 1.5)
        forms = {val, val.rstrip("0").rstrip(".") if "." in val else val,
                 val[:-2] if val.endswith(".0") else val}
        if not any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", law) for f in forms if f):
            drift.append(f"{label}={val} present in C++ but not in DESIGN.md cameras law")
    if drift:
        return fail(issues=drift, hard=True, drift=drift, anchors_checked=checked)
    return ok(anchors_checked=checked)


# ------------------------------------------------------------------ operator-gated baseline snapshot
def snapshot_baseline() -> dict:
    """Establish/refresh the diff baseline from the CURRENT DESIGN.md. OPERATOR-ONLY — promotes the present law
    to "the bar". Autonomy must never call this; it would let a regression define its own baseline. Returns a
    small record for the operator to confirm."""
    if not DESIGN_MD.exists():
        raise BlockedError(f"DESIGN.md missing at {DESIGN_MD}")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DESIGN_MD, BASELINE)
    return {"baseline": str(BASELINE), "from": str(DESIGN_MD), "bytes": BASELINE.stat().st_size}


# ------------------------------------------------------------------ registry contribution
def design_md_validators() -> list:
    D = "design_system"
    return [
        Validator("design_md_lint_no_errors", D, P.STATIC, S.BLOCKER, "DESIGN.md",
                  "broken token ref / malformed color / invalid component sub-token in the visual law",
                  v_design_md_lint),
        Validator("design_md_no_baseline_regression", D, P.STATIC, S.BLOCKER, "DESIGN.md vs baseline",
                  "silent erosion of the visual identity (deleted token / dropped contrast) vs committed baseline",
                  v_design_md_no_regression),
        Validator("design_md_synced_to_code", D, P.STATIC, S.BLOCKER, "DESIGN.md cameras vs C++",
                  "art law drifting away from the shipping FP/TP camera-grading code (decorative, lying spec)",
                  v_design_md_synced_to_code),
    ]
