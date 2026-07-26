"""Engine-adapter conformance suite.

Dimwit's README advertises executable game-engine adapters for Unity, Godot, Defold, Bevy,
web, CMake, and Flutter/Flame in addition to the Unreal lane. Unlike Unreal, those adapters
had no proof-bearing tests -- their advertised behaviour was plan-only and uncontracted. This
module gives every *non-Unreal* adapter a real conformance suite so its claims are contract-tested.

The adapters are the engine-dispatch branches of ``dimwit.toolchains.engines.universal`` governed
by the ``EngineAdapter`` protocol in ``dimwit.toolchains.engines.contracts``. Because the whole
architecture is fail-closed, the load-bearing property is *honest toolchain-absent behaviour*:
with no engine toolchain installed, every adapter must report "blocked" cleanly -- it must never
fabricate a PLAN_READY result and never raise an unhandled/untyped error.

Every test here forces toolchain presence/absence via monkeypatch so the outcome is deterministic
on any host (CI runners already have cargo/npm/cmake/java on PATH, so we cannot rely on the host
being clean). Where an adapter has real pure-Python planning logic, it is exercised substantively
against fixture project directories with asserted plan output, not merely smoked.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from dimwit.toolchains.engines import universal
from dimwit.toolchains.engines.contracts import (
    REVIEW_CEILING,
    SUPPORTED_PROFILES,
    SUPPORTED_TARGETS,
    BuildPlan,
    EngineAdapter,
)


# --------------------------------------------------------------------------------------------
# Adapter specification table -- one row per non-Unreal executable adapter under test.
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AdapterSpec:
    engine: str
    # A representative *advertised* target used for the happy-path plan.
    target: str
    # A target that is valid globally but NOT advertised by this adapter (or None if the
    # adapter advertises every supported target, as Unity does).
    unadvertised_target: str | None
    # Substrings that must appear in the planned argv.
    expected_argv: tuple[str, ...]


SPECS: dict[str, AdapterSpec] = {
    "unity": AdapterSpec("unity", "windows", None, ("-batchmode", "-buildTarget", "StandaloneWindows64")),
    "godot": AdapterSpec("godot", "windows", "xr", ("--headless", "--export-release")),
    "defold": AdapterSpec("defold", "linux", "server", ("-jar", "--archive", "bundle")),
    "bevy": AdapterSpec("bevy", "linux", "android", ("build", "--target")),
    "web": AdapterSpec("web", "web", "windows", ("run", "build")),
    "cmake": AdapterSpec("cmake", "linux", "web", ("--build", "--config")),
    "flutter_flame": AdapterSpec("flutter_flame", "windows", "server", ("build", "windows")),
}

# The Unreal adapter already owns a proof-bearing suite; this module contracts everything else.
NON_UE_ENGINES = sorted(SPECS)
assert set(NON_UE_ENGINES) == set(universal.ENGINE_TARGETS) - {"unreal"}, (
    "conformance specs drifted from the registered adapter set"
)


# --------------------------------------------------------------------------------------------
# Fixture project directories (marker files the detector keys off of).
# --------------------------------------------------------------------------------------------
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "engine_projects"


def _make_project(root: Path, engine: str) -> Path:
    source = FIXTURE_ROOT / engine
    if not source.is_dir():  # pragma: no cover - guard against silent spec drift
        raise AssertionError(f"no fixture project recipe for engine {engine}")
    shutil.copytree(source, root)
    return root


def _fake_tool(tmp_path: Path, engine: str) -> str:
    tool = tmp_path / "toolchain" / f"{engine}-tool"
    tool.parent.mkdir(parents=True, exist_ok=True)
    tool.write_bytes(b"fake toolchain binary")
    return str(tool.resolve())


def _force_toolchains_absent(monkeypatch) -> None:
    """Make every non-Unreal adapter's toolchain probe report the tool as missing.

    CI runners ship cargo/npm/cmake/java on PATH, so a clean-clone fail-closed guarantee can only
    be established by neutralising the discovery layer directly.
    """
    monkeypatch.setattr(universal, "_which", lambda executable: None)
    monkeypatch.setattr(universal, "_unity_executable", lambda: None)
    monkeypatch.setattr(universal, "_godot_executable", lambda: None)
    monkeypatch.setattr(universal, "_defold_bob", lambda: None)


def _force_toolchain_present(monkeypatch, engine: str, tool: str) -> None:
    """Make exactly the requested adapter's toolchain resolve to ``tool`` (fail-closed elsewhere)."""
    if engine == "unity":
        monkeypatch.setattr(universal, "_unity_executable", lambda: tool)
    elif engine == "godot":
        monkeypatch.setattr(universal, "_godot_executable", lambda: tool)
    elif engine == "defold":
        # Defold resolves the bob.jar itself plus a java launcher via _which("java").
        monkeypatch.setattr(universal, "_defold_bob", lambda: tool)
        monkeypatch.setattr(universal, "_which", lambda name: str(Path("/usr/bin/java")) if name == "java" else None)
    elif engine == "bevy":
        monkeypatch.setattr(universal, "_which", lambda name: tool if name == "cargo" else None)
    elif engine == "web":
        monkeypatch.setattr(universal, "_which", lambda name: tool if name in {"npm", "npm.cmd"} else None)
    elif engine == "cmake":
        monkeypatch.setattr(universal, "_which", lambda name: tool if name == "cmake" else None)
    elif engine == "flutter_flame":
        monkeypatch.setattr(universal, "_which", lambda name: tool if name == "flutter" else None)
    else:  # pragma: no cover
        raise AssertionError(f"no toolchain-present recipe for engine {engine}")


def _plan(tmp_path, monkeypatch, engine: str, *, target: str, preset: str | None = None) -> dict:
    """Set up a fixture project + present toolchain and return the plan_build result dict."""
    root = _make_project(tmp_path / engine, engine)
    tool = _fake_tool(tmp_path, engine)
    _force_toolchain_present(monkeypatch, engine, tool)
    if engine == "godot" and preset is None:
        preset = "Windows Desktop" if target == "windows" else "Linux/X11"
    output = tmp_path / "artifacts" / f"{engine}-out"
    result = universal.plan_build(
        str(root), target, str(output), preset=preset,
        allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
    )
    return result, tool


# --------------------------------------------------------------------------------------------
# 1. Registration / capability declaration.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_adapter_is_registered_with_a_capability_declaration(engine):
    targets = universal.ENGINE_TARGETS[engine]
    assert isinstance(targets, tuple) and targets, f"{engine} advertises no build targets"
    assert set(targets).issubset(SUPPORTED_TARGETS), f"{engine} advertises an unsupported target"
    audit = universal.audit_engines()
    row = next((r for r in audit["engines"] if r["engine"] == engine), None)
    assert row is not None, f"{engine} is not surfaced by audit_engines()"
    assert row["targets"] == list(targets)
    assert row["authority"] == "PLAN_FIRST"
    assert row["review_ceiling"] == REVIEW_CEILING


def test_adapter_registry_matches_the_advertised_readme_lineup():
    assert set(universal.ENGINE_TARGETS) == {"unreal", *NON_UE_ENGINES}
    audit = universal.audit_engines()
    assert audit["adapter_count"] == len(universal.ENGINE_TARGETS) == 8
    assert audit["extension_contract"] == "dimwit.toolchains.engines.contracts.EngineAdapter"
    assert audit["conformance"]["state"] == "CI_CONTRACTED"
    assert audit["conformance"]["fixture_root"] == "tests/fixtures/engine_projects"


# --------------------------------------------------------------------------------------------
# 2. Health probe shape + honest fail-closed when the toolchain is absent.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_health_probe_reports_toolchain_absent_cleanly(engine, monkeypatch):
    _force_toolchains_absent(monkeypatch)
    health = universal._tool_health(engine)
    assert health["engine"] == engine
    assert health["ok"] is False, f"{engine} claims health with no toolchain installed"
    assert health["tool"] is None
    assert health["missing"], f"{engine} does not name what is missing"
    assert "engine executable/tool" in health["missing"]
    assert health["targets"] == list(universal.ENGINE_TARGETS[engine])
    assert health["authority"] == "PLAN_FIRST"
    assert health["review_ceiling"] == REVIEW_CEILING


def test_audit_reports_zero_ready_adapters_when_no_toolchain_is_installed(monkeypatch):
    _force_toolchains_absent(monkeypatch)
    # Unreal is discovered via its own module; neutralise it too so the audit is deterministic.
    monkeypatch.setattr(universal.unreal, "discover", lambda *a, **k: {"run_uat": None, "exists": {"project": False}})
    audit = universal.audit_engines()
    assert audit["state"] == "PASS"  # auditing always succeeds; readiness is a separate signal
    assert audit["ready_count"] == 0
    assert all(row["ok"] is False for row in audit["engines"])
    assert "missing tool means BLOCKED" in audit["invariants"]


# --------------------------------------------------------------------------------------------
# 3. Fail-closed planning: no toolchain => typed, honest block; never a fabricated plan.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_plan_build_fails_closed_without_toolchain(engine, tmp_path, monkeypatch):
    _force_toolchains_absent(monkeypatch)
    root = _make_project(tmp_path / engine, engine)
    output = tmp_path / "artifacts" / "out"
    spec = SPECS[engine]
    with pytest.raises(FileNotFoundError) as excinfo:
        universal.plan_build(
            str(root), spec.target, str(output),
            allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
        )
    message = str(excinfo.value).lower()
    assert engine in message and "blocked" in message, "block must name the engine and say it is blocked"


@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_run_build_never_mutates_or_fakes_success_without_toolchain(engine, tmp_path, monkeypatch):
    _force_toolchains_absent(monkeypatch)
    root = _make_project(tmp_path / engine, engine)
    output = tmp_path / "artifacts" / "out"
    spec = SPECS[engine]
    calls: list = []

    def sentinel_runner(*args, **kwargs):  # pragma: no cover - must never be reached
        calls.append(args)
        raise AssertionError("a blocked adapter must not spawn a build process")

    with pytest.raises(FileNotFoundError):
        universal.run_build(
            str(root), spec.target, str(output), allow_mutation=True, runner=sentinel_runner,
            artifact_job_root=tmp_path / "jobs",
            allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
        )
    assert calls == [], "no process was allowed to run"


# --------------------------------------------------------------------------------------------
# 4. Happy path: with a toolchain present, the plan is valid, confined and argv-only.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_plan_build_emits_a_valid_confined_argv_plan_with_toolchain(engine, tmp_path, monkeypatch):
    spec = SPECS[engine]
    result, tool = _plan(tmp_path, monkeypatch, engine, target=spec.target)
    assert result["state"] == "PLAN_READY"
    assert result["mutation_performed"] is False
    assert result["review_ceiling"] == REVIEW_CEILING
    plan = result["plan"]
    assert plan["engine"] == engine
    assert plan["target"] == spec.target
    assert plan["profile"] in SUPPORTED_PROFILES
    assert plan["tool"] == tool
    # argv-only, non-empty, never shell.
    assert plan["shell"] is False
    assert plan["command"] and all(isinstance(a, str) and a for a in plan["command"])
    # declared proof outputs (non-empty), and the plan round-trips its own validation.
    assert plan["outputs"]
    BuildPlan(**plan).validate()
    for token in spec.expected_argv:
        assert token in plan["command"], f"{engine} plan missing expected argv token {token!r}"


@pytest.mark.parametrize("engine", NON_UE_ENGINES)
def test_plan_is_plan_only_until_mutation_is_explicitly_authorised(engine, tmp_path, monkeypatch):
    spec = SPECS[engine]
    root = _make_project(tmp_path / engine, engine)
    tool = _fake_tool(tmp_path, engine)
    _force_toolchain_present(monkeypatch, engine, tool)
    preset = ("Windows Desktop" if engine == "godot" and spec.target == "windows" else None)
    output = tmp_path / "artifacts" / "out"
    planned = universal.run_build(
        str(root), spec.target, str(output), preset=preset, allow_mutation=False,
        artifact_job_root=tmp_path / "jobs",
        allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
    )
    assert planned["state"] == "PLAN_READY"
    assert planned["mutation_performed"] is False
    assert not (tmp_path / "jobs").exists(), "plan-only run must not write a job/receipt directory"


def test_plan_binds_a_source_controlled_production_brief(tmp_path, monkeypatch):
    root = _make_project(tmp_path / "bevy", "bevy")
    tool = _fake_tool(tmp_path, "bevy")
    _force_toolchain_present(monkeypatch, "bevy", tool)
    brief = tmp_path / "arena-brief.md"
    brief.write_text("Build the same arena for every engine.", encoding="utf-8")
    result = universal.plan_build(
        str(root), "linux", str(tmp_path / "artifacts" / "out"), brief=str(brief),
        allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
    )
    metadata = result["plan"]["metadata"]
    assert metadata["brief_path"] == str(brief.resolve())
    assert len(metadata["brief_sha256"]) == 64


# --------------------------------------------------------------------------------------------
# 5. Target-capability enforcement: an unadvertised target is rejected, not silently built.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "engine", [e for e in NON_UE_ENGINES if SPECS[e].unadvertised_target is not None]
)
def test_unadvertised_target_is_rejected_even_with_toolchain(engine, tmp_path, monkeypatch):
    spec = SPECS[engine]
    bad_target = spec.unadvertised_target
    assert bad_target in SUPPORTED_TARGETS  # globally valid, just not for this adapter
    root = _make_project(tmp_path / engine, engine)
    tool = _fake_tool(tmp_path, engine)
    _force_toolchain_present(monkeypatch, engine, tool)
    output = tmp_path / "artifacts" / "out"
    with pytest.raises(ValueError):
        universal.plan_build(
            str(root), bad_target, str(output),
            allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
        )


def test_unity_advertises_every_supported_target():
    # Unity is the "universal" adapter; if this changes, the unadvertised-target spec must gain a case.
    assert set(universal.ENGINE_TARGETS["unity"]) == set(SUPPORTED_TARGETS)


# --------------------------------------------------------------------------------------------
# 6. Reference-only engines are honestly blocked, never routed to an executable adapter.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "marker,filename",
    [("gamemaker", "Game.yyp"), ("o3de", "project.json"), ("construct", "Game.c3p")],
)
def test_reference_only_engine_is_blocked_not_executed(marker, filename, tmp_path, monkeypatch):
    _force_toolchains_absent(monkeypatch)
    root = tmp_path / "refonly"
    root.mkdir()
    (root / filename).write_text("{}", encoding="utf-8")
    detected = universal.detect_project(root)
    assert detected.engine not in universal.ENGINE_TARGETS
    assert detected.metadata.get("state") == "DETECTED_REFERENCE_ONLY"
    assert detected.metadata.get("decision") == "PARKED_REFERENCE_ONLY"
    with pytest.raises(ValueError) as excinfo:
        universal.plan_build(
            str(root), "windows", str(tmp_path / "artifacts" / "out"),
            allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
        )
    assert "no audited executable adapter" in str(excinfo.value)


def test_reference_only_engines_are_formally_parked_and_visible_in_audit():
    audit = universal.audit_engines()
    parked = {row["engine"]: row for row in audit["reference_only"]}
    assert {"gamemaker", "o3de", "construct"}.issubset(parked)
    assert all(parked[name]["decision"] == "PARKED_REFERENCE_ONLY"
               for name in ("gamemaker", "o3de", "construct"))
    assert all(parked[name]["reason"] for name in parked)


# --------------------------------------------------------------------------------------------
# 7. Cross-adapter proof/receipt path: an authorised build hashes its real output.
# --------------------------------------------------------------------------------------------
def test_authorised_build_records_hashed_proof_receipts(tmp_path, monkeypatch):
    # Exercise the receipt path through a non-Unreal, non-Godot adapter (Bevy) so proof-bearing
    # execution is contracted for more than one engine.
    root = _make_project(tmp_path / "bevy", "bevy")
    tool = _fake_tool(tmp_path, "bevy")
    _force_toolchain_present(monkeypatch, "bevy", tool)
    output = tmp_path / "artifacts" / "bevy-target"

    def runner(command, **kwargs):
        assert kwargs.get("shell") is False, "adapters must never execute via a shell"
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "game").write_bytes(b"real compiled artifact")
        return subprocess.CompletedProcess(command, 0, stdout="Compiling\nFinished", stderr="")

    result = universal.run_build(
        str(root), "linux", str(output), allow_mutation=True, runner=runner,
        artifact_job_root=tmp_path / "jobs",
        allowed_project_roots=[tmp_path], allowed_output_roots=[tmp_path / "artifacts"],
    )
    assert result["state"] == "PASS" and result["ok"] is True
    assert result["mutation_performed"] is True
    assert result["output_proofs"][0]["sha256"], "proof receipt must carry a content hash"
    assert result["output_proofs"][0]["bytes"] > 0
    assert (tmp_path / "jobs" / "universal_game_build" / "result.json").is_file()
    assert (tmp_path / "jobs" / "universal_game_build" / "manifest.json").is_file()


# --------------------------------------------------------------------------------------------
# 8. The published extension contract is a structurally usable protocol.
# --------------------------------------------------------------------------------------------
def test_engine_adapter_protocol_is_the_declared_extension_point():
    # The audit points third parties at EngineAdapter as the way to add engines without editing
    # the controller; that protocol must actually declare the audit/plan surface the factory uses.
    for method in ("health", "detect", "plan"):
        assert hasattr(EngineAdapter, method), f"EngineAdapter protocol missing {method}"
    assert "engine_id" in EngineAdapter.__annotations__
    assert universal.audit_engines()["extension_contract"].endswith("EngineAdapter")
