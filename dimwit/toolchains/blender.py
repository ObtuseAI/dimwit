"""Elite Blender adapter: deterministic headless jobs with manifests, budgets, logs, and output hashes."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

from .common import atomic_json, output_proofs, require_job_id, require_within, run_process, sha256_file


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
SCRIPT_ROOT = ROOT / "blender_scripts"
JOB_ROOT = ROOT / "artifacts" / "toolchains" / "blender" / "jobs"
OUTPUT_ARG_KEYS = frozenset({"out", "outdir", "output", "report", "result"})


def discover() -> Path | None:
    override = os.environ.get("DIMWIT_BLENDER_EXE")
    candidates = [Path(override)] if override else []
    candidates.extend([DEFAULT_EXE, Path(r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe")])
    return next((path.resolve() for path in candidates if path and path.is_file()), None)


def health(run_version: bool = False) -> dict:
    executable = discover()
    scripts = sorted(SCRIPT_ROOT.glob("*.py")) if SCRIPT_ROOT.exists() else []
    result = {"ok": bool(executable and scripts), "executable": str(executable) if executable else None,
              "script_root": str(SCRIPT_ROOT), "script_count": len(scripts),
              "capabilities": ["procedural_modeling", "retopology", "uv", "baking", "rigging",
                               "animation_export", "material_authoring", "rendering", "geometry_analysis"]}
    if executable and run_version:
        try:
            completed = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                       timeout=30, shell=False)
            result["version"] = (completed.stdout or "").splitlines()[0] if completed.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["version_error"] = f"{type(exc).__name__}: {exc}"
    return result


def plan_script(script: str, args: list[str] | None = None, outputs: list[str] | None = None,
                job_id: str = "blender_job", timeout: float = 1800, root: Path = ROOT,
                allowed_output_roots: list[Path] | None = None) -> dict:
    executable = discover()
    if not executable:
        raise FileNotFoundError("Blender executable not found")
    root = Path(root).resolve()
    script_path = require_within(Path(script), [root / "blender_scripts"], "Blender script")
    if not script_path.is_file():
        raise FileNotFoundError(f"Blender script not found: {script_path}")
    job_id = require_job_id(job_id)
    output_roots = allowed_output_roots or [root / "artifacts", root / "assets", root / "unreal_imports"]
    output_paths = [require_within(Path(path), output_roots, "Blender output") for path in (outputs or [])]
    user_args = [str(value) for value in (args or [])]
    for value in user_args:
        if "=" not in value:
            continue
        key, candidate = value.split("=", 1)
        if key.casefold() in OUTPUT_ARG_KEYS:
            require_within(Path(candidate), output_roots, f"Blender {key} argument")
    command = [str(executable), "--background", "--factory-startup", "--disable-autoexec",
               "--python", str(script_path), "--", *user_args]
    return {"schema_version": 1, "toolchain": "blender", "job_id": job_id, "command": command,
            "script": str(script_path), "script_sha256": sha256_file(script_path),
            "outputs": [str(path) for path in output_paths], "timeout_seconds": float(timeout),
            "review_ceiling": "PROMOTED_TO_REVIEW", "shell": False}


def run_script(script: str, args: list[str] | None = None, outputs: list[str] | None = None,
               job_id: str = "blender_job", timeout: float = 1800, allow_mutation: bool = False,
               root: Path = ROOT, allowed_output_roots: list[Path] | None = None,
               runner: Callable | None = None) -> dict:
    plan = plan_script(script, args, outputs, job_id, timeout, root, allowed_output_roots)
    if not allow_mutation:
        return {"ok": True, "state": "PLAN_ONLY", "plan": plan, "mutation_performed": False}
    job_dir = Path(root) / "artifacts" / "toolchains" / "blender" / "jobs" / plan["job_id"]
    atomic_json(job_dir / "manifest.json", plan)
    process = run_process(plan["command"], job_dir, cwd=Path(root), timeout=timeout, runner=runner)
    proofs = output_proofs([Path(path) for path in plan["outputs"]])
    ok = process["returncode"] == 0 and all(proof["exists"] and proof["bytes"] > 0 for proof in proofs)
    result = {"ok": ok, "state": "PASS" if ok else "FAIL", "plan": plan, "process": process,
              "output_proofs": proofs, "mutation_performed": True,
              "review_ceiling": "PROMOTED_TO_REVIEW"}
    atomic_json(job_dir / "result.json", result)
    return result
