"""The UE probe batch MUST launch with -NoTextureStreaming.

Probe-proven 2026-07-02 (artifacts/exposure_sweep3_nostream): in tick-less
UnrealEditor-Cmd sessions texture streaming never streams, so SceneCapture
renders sample permanently-low resident mips — the zythan rig photographed as a
washed, panel-less figure while the 4K textures sat unstreamed on disk. Every
capture-bearing batch launch must disable streaming or the capture lane lies.
"""
from pathlib import Path
from types import SimpleNamespace

from dimwit.pipelines import validation as v


def test_ue_batch_launch_disables_texture_streaming(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "VAL_ART", tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        (tmp_path / "ue_probe_batch.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    ctx = SimpleNamespace(
        ue_available=lambda: True,
        root=Path(r"C:\Users\developer\Documents\Dimwit"),
        ue_cmd=Path(r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"),
        uproject=Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"),
    )
    v.run_ue_batch(ctx, {"captures": []})
    assert "-NoTextureStreaming" in captured["cmd"], (
        "UE probe batch launched without -NoTextureStreaming: tick-less sessions "
        "never stream mips, so rig captures would sample low-resident mips and lie"
    )


class _GateCtx(SimpleNamespace):
    def ue_probe(self, probe_id):
        return self.probes[probe_id]


def _gate(flag_present, value=None):
    from dimwit.pipelines.validation_registry import v_rig_capture_texture_streaming_off
    rig_ship = {"texture_streaming_off": value} if flag_present else {}
    ctx = _GateCtx(probes={"captures": {"rig_ship": rig_ship}})
    return v_rig_capture_texture_streaming_off(ctx)


def test_texture_streaming_gate_passes_only_on_true():
    assert _gate(True, True).passed


def test_texture_streaming_gate_fails_on_false():
    verdict = _gate(True, False)
    assert not verdict.passed and verdict.hard_fail


def test_texture_streaming_gate_fails_closed_on_missing_telemetry():
    verdict = _gate(False)
    assert not verdict.passed and verdict.hard_fail


def test_texture_streaming_gate_registered_as_rigged_blocker():
    from dimwit.pipelines.validation_registry import REGISTRY
    match = [r for r in REGISTRY if r.id == "rig_capture_texture_streaming_off"]
    assert len(match) == 1
    gate = match[0]
    assert gate.domain == "rigged_skeletal_meshes"
    assert str(gate.severity).lower().endswith("blocker")
    assert "ue" in (gate.requires or [])
