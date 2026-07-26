from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dimwit.toolchains import blender, studio, unreal


def _fake_unreal(tmp: Path, monkeypatch) -> Path:
    engine = tmp / "UE_5.8"
    for relative in (
        "Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
        "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe",
        "Engine/Build/BatchFiles/Build.bat",
        "Engine/Build/BatchFiles/RunUAT.bat",
    ):
        path = engine / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tool")
    (engine / "Engine/Build/Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 0}), encoding="utf-8")
    project = tmp / "Game" / "Game.uproject"
    project.parent.mkdir(parents=True)
    project.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DIMWIT_UNREAL_ROOT", str(engine))
    return project


def test_blender_plan_is_headless_no_shell_and_repo_script_only(tmp_path):
    root = tmp_path / "Dimwit"
    script = root / "blender_scripts" / "build.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')", encoding="utf-8")
    output = root / "artifacts" / "mesh.glb"
    plan = blender.plan_script(str(script), [f"out={output}"], [str(output)], root=root)
    assert plan["shell"] is False
    assert "--background" in plan["command"] and "--factory-startup" in plan["command"]
    assert plan["script_sha256"]


def test_blender_rejects_external_script_and_output(tmp_path):
    root = tmp_path / "Dimwit"
    (root / "blender_scripts").mkdir(parents=True)
    external = tmp_path / "external.py"
    external.write_text("pass", encoding="utf-8")
    with pytest.raises(ValueError):
        blender.plan_script(str(external), root=root)
    internal = root / "blender_scripts" / "ok.py"
    internal.write_text("pass", encoding="utf-8")
    with pytest.raises(ValueError):
        blender.plan_script(str(internal), outputs=[str(tmp_path / "escape.glb")], root=root)


def test_blender_rejects_unlisted_report_argument_escape(tmp_path):
    root = tmp_path / "Dimwit"
    script = root / "blender_scripts" / "ok.py"
    script.parent.mkdir(parents=True)
    script.write_text("pass", encoding="utf-8")

    with pytest.raises(ValueError):
        blender.plan_script(
            str(script),
            args=[f"out={root / 'artifacts' / 'mesh.fbx'}", f"report={tmp_path / 'escape.json'}"],
            outputs=[str(root / "artifacts" / "mesh.fbx")],
            root=root,
        )

    plan = blender.plan_script(
        str(script),
        args=[f"report={root / 'artifacts' / 'report.json'}"],
        root=root,
    )
    assert any(value.endswith("report.json") for value in plan["command"])


def test_blender_execution_writes_proof_hash(tmp_path):
    root = tmp_path / "Dimwit"
    script = root / "blender_scripts" / "build.py"
    output = root / "artifacts" / "mesh.glb"
    script.parent.mkdir(parents=True)
    script.write_text("pass", encoding="utf-8")

    def runner(command, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"real mesh bytes")
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    result = blender.run_script(str(script), outputs=[str(output)], root=root,
                                allow_mutation=True, runner=runner)
    assert result["ok"] and result["output_proofs"][0]["sha256"]
    assert (root / "artifacts/toolchains/blender/jobs/blender_job/result.json").is_file()


def test_unreal_build_plan_is_allowlisted_argv(tmp_path, monkeypatch):
    project = _fake_unreal(tmp_path, monkeypatch)
    plan = unreal.plan_job("build", project=project, target="WanefallGreyboxEditor")
    assert plan["shell"] is False
    assert plan["operation"] == "build"
    assert any(value.endswith("Build.bat") for value in plan["command"])
    assert any(value.startswith("-Project=") for value in plan["command"])
    with pytest.raises(ValueError):
        unreal.plan_job("build", project=project, target="ArbitraryTarget")


def test_unreal_android_package_is_allowlisted_for_mobile_factory(tmp_path, monkeypatch):
    project = _fake_unreal(tmp_path, monkeypatch)
    root = tmp_path / "Dimwit"
    archive = root / "artifacts" / "android"
    plan = unreal.plan_job("package", project=project, platform="Android",
                           archive_directory=str(archive), root=root)
    assert any(value == "-platform=Android" for value in plan["command"])
    assert plan["outputs"] == [str(archive.resolve())]


def test_unreal_rejects_unsafe_commandlet_args(tmp_path, monkeypatch):
    project = _fake_unreal(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        unreal.plan_job("commandlet", project=project, commandlet="SafeName", args=["x; rm -rf"])
    with pytest.raises(ValueError):
        unreal.plan_job("commandlet", project=project, commandlet="Bad Name")


def test_unreal_plan_only_does_not_run(tmp_path, monkeypatch):
    project = _fake_unreal(tmp_path, monkeypatch)
    result = unreal.run_job("build", project=project, root=tmp_path, allow_mutation=False)
    assert result["state"] == "PLAN_ONLY" and not result["mutation_performed"]


def _graph(nodes):
    return {"schema_version": 1, "studio_id": "test", "review_ceiling": "PROMOTED_TO_REVIEW",
            "project": "Game.uproject", "nodes": nodes}


def test_studio_graph_rejects_cycle():
    graph = _graph([
        {"id": "a", "kind": "validation", "domains": ["x"], "deps": ["b"]},
        {"id": "b", "kind": "validation", "domains": ["x"], "deps": ["a"]},
    ])
    result = studio.validate_graph(graph)
    assert not result["passed"] and any("cycle" in issue for issue in result["issues"])


def test_studio_criticality_prefers_nodes_that_unblock_more_work():
    graph = _graph([
        {"id": "root", "kind": "preflight", "deps": []},
        {"id": "short", "kind": "validation", "domains": ["x"], "deps": ["root"]},
        {"id": "long", "kind": "validation", "domains": ["x"], "deps": ["root"]},
        {"id": "long_2", "kind": "validation", "domains": ["x"], "deps": ["long"]},
        {"id": "long_3", "kind": "validation", "domains": ["x"], "deps": ["long_2"]},
    ])
    counts = studio.downstream_counts(graph)
    assert counts["long"] > counts["short"]


class _PipelineResult:
    state = "PROMOTED_TO_REVIEW"
    score = 1.0


class _Pipeline:
    def run(self, task):
        return _PipelineResult()


def test_studio_runs_and_resumes_two_node_dag(tmp_path, monkeypatch):
    graph = _graph([
        {"id": "preflight", "kind": "preflight", "deps": [], "cost": 0.1},
        {"id": "audio", "kind": "pipeline", "pipeline": "audio", "asset_id": "x",
         "domains": ["audio_foundation"], "deps": ["preflight"], "cost": 1},
    ])
    monkeypatch.setattr(studio.blender, "health", lambda run_version=False: {"ok": True})
    monkeypatch.setattr(studio.unreal, "health", lambda project: {"ok": True})
    controller = studio.StudioController(
        root=tmp_path, graph=graph, pipeline_factory=lambda name: _Pipeline(),
        validate_fn=lambda domains: {"suite_verdict": "PASS", "counts": {"PASS": 1}},
        state_path=tmp_path / "state.json", ledger_path=tmp_path / "studio.jsonl")
    first = controller.run(execute=True, max_nodes=2, max_cost=2)
    assert first["state"] == "PROMOTED_TO_REVIEW" and first["complete"] == 2
    second = controller.run(execute=True, max_nodes=2, max_cost=2)
    assert second["ran"] == [] and second["complete"] == 2


def test_studio_invalidates_completed_node_when_proof_disappears(tmp_path):
    graph = _graph([{"id": "proofed", "kind": "validation", "domains": ["x"], "deps": [],
                     "proofs": ["artifacts/required.json"]}])
    state = {"schema_version": 1, "studio_id": "test", "review_ceiling": "PROMOTED_TO_REVIEW",
             "nodes": {"proofed": {"status": "PASS"}}}
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    controller = studio.StudioController(root=tmp_path, graph=graph,
                                         validate_fn=lambda domains: {"suite_verdict": "PASS"},
                                         state_path=tmp_path / "state.json", ledger_path=tmp_path / "studio.jsonl")
    assert controller.plan()["nodes"][0]["status"] == "PROOF_MISSING"
