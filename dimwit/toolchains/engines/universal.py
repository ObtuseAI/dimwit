"""Dimwit's engine-agnostic game factory.

Supported executable adapters: Unreal, Unity, Godot, Defold, Bevy/Rust, web/npm, CMake/native, and
Flutter/Flame. Additional engines can implement the EngineAdapter protocol without changing the controller.
Every build is plan-only by default, argv-only, output-confined, proof-hashed, and capped at review.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Callable

from dimwit.toolchains import unreal
from dimwit.toolchains.common import atomic_json, output_proofs, require_job_id, require_within, run_process, sha256_file
from dimwit.toolchains.engines.contracts import BuildPlan, BuildRequest, EngineProject


ROOT = Path(__file__).resolve().parents[3]
JOB_ROOT = ROOT / "artifacts" / "toolchains" / "universal" / "jobs"
SAFE_PRESET = re.compile(r"^[A-Za-z0-9 _+().-]{1,96}$")
SAFE_METHOD = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{2,128}$")
SKIP_DIRS = frozenset({".git", ".godot", "Library", "Temp", "obj", "bin", "node_modules", "target", "Saved", "Intermediate"})

ENGINE_TARGETS = {
    "unreal": ("windows", "android"),
    "unity": ("windows", "linux", "macos", "web", "android", "ios", "server", "xr"),
    "godot": ("windows", "linux", "macos", "web", "android", "ios", "server"),
    "defold": ("windows", "linux", "macos", "web", "android", "ios"),
    "bevy": ("windows", "linux", "macos", "web", "server"),
    "web": ("web", "android", "ios"),
    "cmake": ("windows", "linux", "macos", "android", "server", "xr"),
    "flutter_flame": ("windows", "linux", "macos", "web", "android", "ios"),
}

# Formally parked until an executable adapter can satisfy the same proof-bearing contract.
REFERENCE_ONLY_ENGINES = {
    "gamemaker": {"markers": ("*.yyp",), "decision": "PARKED_REFERENCE_ONLY", "reason": "closed editor/compiler workflow has no audited argv-only adapter"},
    "o3de": {"markers": ("project.json",), "decision": "PARKED_REFERENCE_ONLY", "reason": "toolchain and project-manager workflow require a dedicated audited adapter"},
    "construct": {"markers": ("*.c3p",), "decision": "PARKED_REFERENCE_ONLY", "reason": "browser/editor export workflow has no audited local CLI contract"},
    "cryengine": {"markers": ("*.cryproject",), "decision": "PARKED_REFERENCE_ONLY", "reason": "detected for inventory only; executable adapter is not audited"},
}


def _which(executable: str) -> str | None:
    found = shutil.which(executable)
    return str(Path(found).resolve()) if found else None


def _unity_executable() -> str | None:
    override = os.environ.get("DIMWIT_UNITY_EXE")
    if override and Path(override).is_file():
        return str(Path(override).resolve())
    root = Path(r"C:\Program Files\Unity\Hub\Editor")
    candidates = sorted(root.glob("*/Editor/Unity.exe"), reverse=True) if root.exists() else []
    return str(candidates[0].resolve()) if candidates else None


def _godot_executable() -> str | None:
    override = os.environ.get("DIMWIT_GODOT_EXE")
    candidates = [Path(override)] if override else []
    for name in ("godot4", "godot"):
        found = _which(name)
        if found:
            candidates.append(Path(found))
    program_files = Path(r"C:\Program Files\Godot")
    if program_files.exists():
        candidates.extend(sorted(program_files.glob("Godot*.exe"), reverse=True))
    return str(next((path.resolve() for path in candidates if path.is_file()), "")) or None


def _defold_bob() -> str | None:
    override = os.environ.get("DIMWIT_DEFOLD_BOB_JAR")
    candidates = [Path(override)] if override else []
    candidates.append(Path.home() / ".Defold" / "bob" / "bob.jar")
    found = next((path.resolve() for path in candidates if path.is_file()), None)
    return str(found) if found else None


def _tool_health(engine: str) -> dict:
    tool = {
        "unreal": unreal.discover().get("run_uat"), "unity": _unity_executable(), "godot": _godot_executable(),
        "defold": _defold_bob(), "bevy": _which("cargo"), "web": _which("npm.cmd") or _which("npm"),
        "cmake": _which("cmake"), "flutter_flame": _which("flutter"),
    }[engine]
    prerequisites = []
    if engine == "defold" and not _which("java"):
        prerequisites.append("java")
    if engine == "unreal":
        found = unreal.discover()
        ok = all(found.get("exists", {}).values())
    else:
        ok = bool(tool) and not prerequisites
    return {"engine": engine, "ok": ok, "tool": tool, "targets": list(ENGINE_TARGETS[engine]),
            "missing": (["engine executable/tool"] if not tool else []) + prerequisites,
            "authority": "PLAN_FIRST", "review_ceiling": "PROMOTED_TO_REVIEW"}


def audit_engines() -> dict:
    rows = [_tool_health(engine) for engine in ENGINE_TARGETS]
    return {
        "schema_version": 1, "state": "PASS", "adapter_count": len(rows),
        "ready_count": sum(row["ok"] for row in rows), "engines": rows,
        "conformance": {"state": "CI_CONTRACTED", "non_unreal_adapters": 7,
                        "fixture_root": "tests/fixtures/engine_projects"},
        "reference_only_count": len(REFERENCE_ONLY_ENGINES),
        "reference_only": [{"engine": engine, **detail} for engine, detail in REFERENCE_ONLY_ENGINES.items()],
        "targets": sorted({target for targets in ENGINE_TARGETS.values() for target in targets}),
        "extension_contract": "dimwit.toolchains.engines.contracts.EngineAdapter",
        "invariants": ["plan-only default", "argv-only execution", "confined outputs",
                       "missing tool means BLOCKED", "review ceiling is PROMOTED_TO_REVIEW"],
    }


def write_engine_audit(path: Path = ROOT / "artifacts" / "toolchains" / "universal" / "engine_audit.json") -> dict:
    report = audit_engines()
    atomic_json(path, report)
    return report


def _text_contains(path: Path, needle: str) -> bool:
    try:
        return needle.lower() in path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def detect_project(path: str | Path) -> EngineProject:
    root = Path(path).resolve()
    if root.is_file():
        root = root.parent
    uprojects = sorted(root.glob("*.uproject"))
    if uprojects:
        return EngineProject("unreal", str(root), str(uprojects[0]), 1.0)
    if (root / "ProjectSettings" / "ProjectVersion.txt").is_file() and (root / "Assets").is_dir():
        return EngineProject("unity", str(root), str(root / "ProjectSettings" / "ProjectVersion.txt"), 1.0)
    if (root / "project.godot").is_file():
        return EngineProject("godot", str(root), str(root / "project.godot"), 1.0)
    if (root / "game.project").is_file():
        return EngineProject("defold", str(root), str(root / "game.project"), 1.0)
    cargo = root / "Cargo.toml"
    if cargo.is_file() and _text_contains(cargo, "bevy"):
        return EngineProject("bevy", str(root), str(cargo), 0.98)
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file() and _text_contains(pubspec, "flame"):
        return EngineProject("flutter_flame", str(root), str(pubspec), 0.98)
    package = root / "package.json"
    if package.is_file() and any(_text_contains(package, name) for name in
                                 ("phaser", "playcanvas", "babylon", "three", "pixi", "melonjs")):
        return EngineProject("web", str(root), str(package), 0.9)
    if (root / "CMakeLists.txt").is_file():
        return EngineProject("cmake", str(root), str(root / "CMakeLists.txt"), 0.75)
    for engine, detail in REFERENCE_ONLY_ENGINES.items():
        for marker in detail["markers"]:
            found = sorted(root.glob(marker))
            if found:
                return EngineProject(engine, str(root), str(found[0]), 0.8,
                                     {"state": "DETECTED_REFERENCE_ONLY", "decision": detail["decision"],
                                      "reason": detail["reason"]})
    raise ValueError(f"no supported game-engine project marker found in {root}")


def scan_projects(path: str | Path, max_depth: int = 5, max_projects: int = 100) -> list[dict]:
    start = Path(path).resolve()
    found: list[dict] = []
    for current, dirs, _files in os.walk(start):
        here = Path(current)
        depth = len(here.relative_to(start).parts)
        dirs[:] = [] if depth >= max_depth else [name for name in dirs if name not in SKIP_DIRS]
        try:
            project = detect_project(here)
        except ValueError:
            continue
        found.append(project.to_dict())
        dirs[:] = []
        if len(found) >= max_projects:
            break
    return sorted(found, key=lambda row: (row["engine"], row["root"]))


def _project_file(project: EngineProject, suffix: str) -> Path:
    marker = Path(project.marker)
    if marker.suffix.lower() == suffix:
        return marker
    matches = sorted(Path(project.root).glob(f"*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"{project.engine} project file {suffix} not found")
    return matches[0]


def _godot_presets(root: Path) -> list[str]:
    path = root / "export_presets.cfg"
    if not path.is_file():
        return []
    return re.findall(r'^name="([^"]+)"', path.read_text(encoding="utf-8", errors="replace"), flags=re.MULTILINE)


def _target_output_extension(engine: str, target: str) -> str:
    if target == "android":
        return ".aab" if engine in {"unity", "flutter_flame"} else ".apk"
    return {"windows": ".exe", "web": ".html", "ios": ".zip"}.get(target, "")


def _plan_for_engine(request: BuildRequest, project: EngineProject, output: Path) -> BuildPlan:
    engine, root = project.engine, Path(project.root)
    health = _tool_health(engine)
    if not health["ok"]:
        raise FileNotFoundError(f"{engine} toolchain blocked: {', '.join(health['missing'])}")
    if request.target not in ENGINE_TARGETS[engine]:
        raise ValueError(f"{engine} does not advertise target {request.target}")
    tool = str(health["tool"])
    metadata: dict = {"project_detection": project.to_dict()}
    if request.brief:
        brief_path = Path(request.brief)
        metadata["brief_path"] = str(brief_path)
        metadata["brief_sha256"] = sha256_file(brief_path)
    if engine == "unreal":
        platform = {"windows": "Win64", "android": "Android"}[request.target]
        base = unreal.plan_job("package", project=_project_file(project, ".uproject"), job_id=request.job_id,
                               platform=platform, configuration="Shipping" if request.profile in {"release", "shipping"} else "Development",
                               archive_directory=str(output), root=ROOT)
        return BuildPlan(engine, "build_cook_package", str(root), request.target, request.profile,
                         tuple(base["command"]), (str(output),), request.job_id, tool, metadata=metadata)
    if engine == "unity":
        target = {"windows": "StandaloneWindows64", "linux": "StandaloneLinux64", "macos": "StandaloneOSX",
                  "web": "WebGL", "android": "Android", "ios": "iOS", "server": "StandaloneWindows64",
                  "xr": "StandaloneWindows64"}[request.target]
        command = (tool, "-batchmode", "-quit", "-projectPath", str(root), "-buildTarget", target,
                   "-build", str(output), "-logFile", "-")
    elif engine == "godot":
        presets = _godot_presets(root)
        preset = request.preset or next((name for name in presets if request.target.lower() in name.lower()), None)
        if not preset or not SAFE_PRESET.fullmatch(preset):
            raise ValueError(f"Godot export preset required for {request.target}; available={presets}")
        metadata["available_presets"] = presets
        command = (tool, "--headless", "--path", str(root),
                   "--export-debug" if request.profile == "debug" else "--export-release", preset, str(output))
    elif engine == "defold":
        platform = {"windows": "x86_64-win32", "linux": "x86_64-linux", "macos": "x86_64-macos",
                    "web": "js-web", "android": "arm64-android", "ios": "arm64-ios"}[request.target]
        command = (_which("java") or "java", "-jar", tool, "--root", str(root), "--archive",
                   "--platform", platform, "--bundle-output", str(output),
                   "--variant", "debug" if request.profile == "debug" else "release", "resolve", "build", "bundle")
    elif engine == "bevy":
        triple = {"windows": "x86_64-pc-windows-msvc", "linux": "x86_64-unknown-linux-gnu",
                  "macos": "aarch64-apple-darwin", "web": "wasm32-unknown-unknown",
                  "server": "x86_64-pc-windows-msvc"}[request.target]
        command = (tool, "build", *(() if request.profile in {"debug", "development"} else ("--release",)),
                   "--target", triple, "--target-dir", str(output))
    elif engine == "web":
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        script = request.preset or "build"
        if script not in {"build", "test"} or script not in scripts:
            raise ValueError("web adapter permits only declared build/test scripts")
        metadata["script"] = scripts[script]
        command = (tool, "run", script, "--", "--outDir", str(output))
    elif engine == "cmake":
        build_dir = root / (request.preset or "build")
        if not build_dir.is_dir():
            raise ValueError("CMake adapter builds an existing confined build directory; configure it first")
        command = (tool, "--build", str(build_dir), "--config",
                   "Debug" if request.profile == "debug" else "Release")
        output = build_dir
    elif engine == "flutter_flame":
        subcommand = {"windows": "windows", "linux": "linux", "macos": "macos", "web": "web",
                      "android": "appbundle", "ios": "ipa"}[request.target]
        command = (tool, "build", subcommand, "--debug" if request.profile == "debug" else "--release")
    else:
        raise ValueError(f"no executable adapter for detected engine {engine}")
    plan = BuildPlan(engine, "build_package", str(root), request.target, request.profile, tuple(command),
                     (str(output),), request.job_id, tool, metadata=metadata)
    plan.validate()
    return plan


def plan_build(project: str, target: str, output: str, *, engine: str = "auto", profile: str = "release",
               preset: str | None = None, job_id: str = "universal_game_build",
               brief: str | None = None,
               allowed_project_roots: list[Path] | None = None,
               allowed_output_roots: list[Path] | None = None) -> dict:
    project_roots = allowed_project_roots or [ROOT, Path.home() / "Documents"]
    root = require_within(Path(project), project_roots, "game project")
    brief_path = None
    if brief:
        brief_path = require_within(Path(brief), project_roots, "production brief")
        if not brief_path.is_file():
            raise FileNotFoundError(f"production brief not found: {brief_path}")
    request = BuildRequest(project, target, output, profile, engine, preset, require_job_id(job_id),
                           str(brief_path) if brief_path else None)
    request.validate()
    detected = detect_project(root)
    if engine != "auto" and detected.engine != engine:
        raise ValueError(f"requested engine {engine} does not match detected engine {detected.engine}")
    if detected.engine not in ENGINE_TARGETS:
        raise ValueError(f"{detected.engine} is detected but has no audited executable adapter")
    output_roots = allowed_output_roots or [ROOT / "artifacts"]
    output_path = require_within(Path(output), output_roots, "game build output")
    plan = _plan_for_engine(request, detected, output_path)
    return {"schema_version": 1, "state": "PLAN_READY", "mutation_performed": False,
            "plan": plan.to_dict(), "review_ceiling": "PROMOTED_TO_REVIEW"}


def run_build(project: str, target: str, output: str, *, allow_mutation: bool = False,
              runner: Callable | None = None, artifact_job_root: Path = JOB_ROOT, **kwargs) -> dict:
    planned = plan_build(project, target, output, **kwargs)
    if not allow_mutation:
        return planned
    plan = planned["plan"]
    job_dir = Path(artifact_job_root) / plan["job_id"]
    atomic_json(job_dir / "manifest.json", planned)
    process = run_process(plan["command"], job_dir, cwd=Path(plan["project"]),
                          timeout=plan["timeout_seconds"], runner=runner)
    proofs = output_proofs([Path(path) for path in plan["outputs"]])
    ok = process["returncode"] == 0 and all(item["exists"] and item["bytes"] > 0 for item in proofs)
    result = {"schema_version": 1, "state": "PASS" if ok else "FAIL", "ok": ok,
              "mutation_performed": True, "plan": plan, "process": process, "output_proofs": proofs,
              "review_ceiling": "PROMOTED_TO_REVIEW"}
    atomic_json(job_dir / "result.json", result)
    return result
