"""Elite Unreal adapter: audited commandlet, Python, build, and package job plans with full receipts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable

from .common import atomic_json, output_proofs, require_job_id, require_within, run_process, sha256_file


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject")
DEFAULT_ENGINE = Path(r"C:\UE_5.8")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:+/=-]+$")
ALLOWED_TARGETS = {"WanefallGreybox", "WanefallGreyboxEditor"}
ALLOWED_PLATFORMS = {"Win64", "Android"}
ALLOWED_CONFIGS = {"Development", "DebugGame", "Shipping"}


def discover(project: str | Path = DEFAULT_PROJECT) -> dict:
    project = Path(project).resolve()
    engine_root = Path(os.environ.get("DIMWIT_UNREAL_ROOT", str(DEFAULT_ENGINE))).resolve()
    editor = engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
    ubt = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    build_bat = engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    run_uat = engine_root / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
    build_version = engine_root / "Engine" / "Build" / "Build.version"
    version = None
    if build_version.is_file():
        try:
            data = json.loads(build_version.read_text(encoding="utf-8"))
            version = f"{data.get('MajorVersion')}.{data.get('MinorVersion')}.{data.get('PatchVersion')}"
        except (OSError, ValueError):
            version = None
    return {"project": str(project), "engine_root": str(engine_root), "editor_cmd": str(editor),
            "unreal_build_tool": str(ubt), "build_bat": str(build_bat), "run_uat": str(run_uat), "version": version,
            "exists": {"project": project.is_file(), "editor_cmd": editor.is_file(),
                       "unreal_build_tool": ubt.is_file(), "build_bat": build_bat.is_file(),
                       "run_uat": run_uat.is_file()}}


def health(project: str | Path = DEFAULT_PROJECT) -> dict:
    found = discover(project)
    return {"ok": all(found["exists"].values()), **found,
            "capabilities": ["cpp_build", "editor_commandlets", "python_automation", "asset_import",
                             "world_authoring", "gameplay_compile", "automation_tests", "cook", "package",
                             "runtime_smoke", "performance_capture", "movie_render_queue"]}


def _safe_args(args: list[str] | None) -> list[str]:
    values = [str(value) for value in (args or [])]
    if any(not SAFE_TOKEN.fullmatch(value) for value in values):
        raise ValueError("Unreal arguments contain unsafe characters")
    return values


def _batch_command(batch_file: str, args: list[str]) -> list[str]:
    # Epic's batch entrypoints establish the bundled .NET SDK/runtime before invoking UBT/UAT.  Use cmd.exe
    # explicitly while subprocess itself remains shell=False, keeping argument construction inspectable.
    command_processor = os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")
    return [command_processor, "/d", "/s", "/c", batch_file, *args]


def plan_job(operation: str, *, project: str | Path = DEFAULT_PROJECT, job_id: str = "unreal_job",
             script: str | None = None, commandlet: str | None = None, args: list[str] | None = None,
             target: str = "WanefallGreyboxEditor", platform: str = "Win64",
             configuration: str = "Development", archive_directory: str | None = None,
             timeout: float = 3600, root: Path = ROOT) -> dict:
    found = discover(project)
    if not all(found["exists"].values()):
        raise FileNotFoundError(f"Unreal toolchain incomplete: {found['exists']}")
    project_path = Path(found["project"])
    job_id = require_job_id(job_id)
    extra = _safe_args(args)
    outputs: list[Path] = []
    if operation == "python_script":
        if not script:
            raise ValueError("python_script operation requires script")
        script_path = require_within(Path(script), [Path(root)], "Unreal Python script")
        if not script_path.is_file():
            raise FileNotFoundError(script_path)
        command = [found["editor_cmd"], str(project_path), f"-ExecutePythonScript={script_path}",
                   "-unattended", "-nop4", "-nosplash", *extra]
    elif operation == "commandlet":
        if not commandlet or not re.fullmatch(r"[A-Za-z0-9_]+", commandlet):
            raise ValueError("invalid commandlet name")
        command = [found["editor_cmd"], str(project_path), f"-run={commandlet}",
                   "-unattended", "-nop4", "-nosplash", *extra]
    elif operation == "build":
        if target not in ALLOWED_TARGETS or platform not in ALLOWED_PLATFORMS or configuration not in ALLOWED_CONFIGS:
            raise ValueError("build target/platform/configuration is outside the allowlist")
        command = _batch_command(found["build_bat"], [target, platform, configuration,
                                 f"-Project={project_path}", "-WaitMutex", "-NoHotReloadFromIDE", *extra])
    elif operation == "package":
        if not archive_directory:
            raise ValueError("package operation requires archive_directory")
        if platform not in ALLOWED_PLATFORMS or configuration not in ALLOWED_CONFIGS:
            raise ValueError("package platform/configuration is outside the allowlist")
        archive = require_within(Path(archive_directory), [Path(root) / "artifacts", Path(r"D:\WanefallBuild")],
                                 "package archive")
        outputs.append(archive)
        command = _batch_command(found["run_uat"], ["BuildCookRun", f"-project={project_path}", "-noP4",
                                 "-build", "-cook", "-stage", "-pak", "-archive",
                                 f"-archivedirectory={archive}", f"-platform={platform}",
                                 f"-clientconfig={configuration}", "-utf8output", *extra])
    else:
        raise ValueError(f"unsupported Unreal operation: {operation}")
    return {"schema_version": 1, "toolchain": "unreal", "operation": operation, "job_id": job_id,
            "project": str(project_path), "project_sha256": sha256_file(project_path), "command": command,
            "outputs": [str(path) for path in outputs], "timeout_seconds": float(timeout),
            "review_ceiling": "PROMOTED_TO_REVIEW", "shell": False, "discovery": found}


def run_job(operation: str, *, allow_mutation: bool = False, runner: Callable | None = None,
            root: Path = ROOT, **kwargs) -> dict:
    plan = plan_job(operation, root=root, **kwargs)
    if not allow_mutation:
        return {"ok": True, "state": "PLAN_ONLY", "plan": plan, "mutation_performed": False}
    job_dir = Path(root) / "artifacts" / "toolchains" / "unreal" / "jobs" / plan["job_id"]
    atomic_json(job_dir / "manifest.json", plan)
    process = run_process(plan["command"], job_dir, cwd=Path(plan["project"]).parent,
                          timeout=plan["timeout_seconds"], runner=runner)
    proofs = output_proofs([Path(path) for path in plan["outputs"]])
    ok = process["returncode"] == 0 and all(proof["exists"] and proof["bytes"] > 0 for proof in proofs)
    result = {"ok": ok, "state": "PASS" if ok else "FAIL", "plan": plan, "process": process,
              "output_proofs": proofs, "mutation_performed": True, "review_ceiling": "PROMOTED_TO_REVIEW"}
    atomic_json(job_dir / "result.json", result)
    return result


def run_python(script: str, **kwargs) -> dict:
    return run_job("python_script", script=script, **kwargs)


def build_project(**kwargs) -> dict:
    return run_job("build", **kwargs)


def package_project(archive_directory: str, **kwargs) -> dict:
    return run_job("package", archive_directory=archive_directory, **kwargs)


def run_commandlet(commandlet: str, **kwargs) -> dict:
    return run_job("commandlet", commandlet=commandlet, **kwargs)
