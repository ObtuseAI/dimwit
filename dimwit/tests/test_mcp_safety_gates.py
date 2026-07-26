from __future__ import annotations

from mcp import dimwit_server
from ue_mcp import server as ue_server
from ue_mcp import security as ue_security


class _Capability:
    def __init__(self, domain):
        self.domain = domain


def test_engine_mcp_blocks_mutating_dispatch_by_default(monkeypatch):
    monkeypatch.delenv(dimwit_server.MUTATION_ENV, raising=False)
    monkeypatch.setattr(dimwit_server.registry, "get", lambda name: _Capability("EXECUTE"))
    monkeypatch.setattr(dimwit_server.registry, "dispatch", lambda *a, **k: "should-not-run")
    result = dimwit_server.call_tool("dimwit_dispatch", {"name": "EXECUTE/ue.live", "args": {}})
    assert result["blocked"] is True
    assert result["ok"] is False


def test_engine_mcp_allows_explicitly_enabled_mutation(monkeypatch):
    monkeypatch.setenv(dimwit_server.MUTATION_ENV, "1")
    monkeypatch.setattr(dimwit_server.registry, "get", lambda name: _Capability("EXECUTE"))
    monkeypatch.setattr(dimwit_server.registry, "dispatch", lambda *a, **k: "ran")
    result = dimwit_server.call_tool("dimwit_dispatch", {"name": "EXECUTE/ue.live", "args": {}})
    assert result == {"ok": True, "result": "ran"}


def test_engine_mcp_provider_capability_requires_separate_opt_in(monkeypatch):
    monkeypatch.setenv(dimwit_server.MUTATION_ENV, "1")
    monkeypatch.delenv(dimwit_server.PAID_MODEL_ENV, raising=False)
    monkeypatch.setattr(dimwit_server.registry, "get", lambda name: _Capability("DESIGN"))
    monkeypatch.setattr(dimwit_server.registry, "dispatch", lambda *a, **k: "should-not-run")

    result = dimwit_server.call_tool(
        "dimwit_dispatch", {"name": "DESIGN/brain.plan_queue", "args": {"state": []}}
    )

    assert result["blocked"] is True
    assert dimwit_server.PAID_MODEL_ENV in result["error"]


def test_engine_mcp_rejects_provider_image_outside_capture_roots(monkeypatch, tmp_path):
    image = tmp_path / "private.png"
    image.write_bytes(b"not uploaded")
    monkeypatch.setenv(dimwit_server.MUTATION_ENV, "1")
    monkeypatch.setenv(dimwit_server.PAID_MODEL_ENV, "1")
    monkeypatch.setattr(dimwit_server.registry, "get", lambda name: _Capability("DEVELOP"))
    monkeypatch.setattr(dimwit_server.registry, "dispatch", lambda *a, **k: "should-not-run")

    try:
        dimwit_server.call_tool(
            "dimwit_dispatch",
            {"name": "DEVELOP/brain.light_qa", "args": {"image_path": str(image)}},
        )
    except ValueError as exc:
        assert "outside Dimwit's approved capture roots" in str(exc)
    else:
        raise AssertionError("unapproved local image reached provider dispatch")


def test_engine_mcp_allows_approved_provider_image_after_both_opt_ins(monkeypatch, tmp_path):
    root = tmp_path / "captures"
    root.mkdir()
    image = root / "approved.png"
    image.write_bytes(b"approved fixture")
    monkeypatch.setattr(dimwit_server, "PROVIDER_IMAGE_ROOTS", (root.resolve(),))
    monkeypatch.setenv(dimwit_server.MUTATION_ENV, "1")
    monkeypatch.setenv(dimwit_server.PAID_MODEL_ENV, "1")
    monkeypatch.setattr(dimwit_server.registry, "get", lambda name: _Capability("DEVELOP"))
    dispatched = []
    monkeypatch.setattr(
        dimwit_server.registry,
        "dispatch",
        lambda name, **kwargs: dispatched.append((name, kwargs)) or "ran",
    )

    result = dimwit_server.call_tool(
        "dimwit_dispatch",
        {"name": "DEVELOP/brain.light_qa", "args": {"image_path": str(image)}},
    )

    assert result == {"ok": True, "result": "ran"}
    assert dispatched == [("DEVELOP/brain.light_qa", {"image_path": str(image.resolve())})]


def test_engine_mcp_blocks_asset_and_seed_writes_by_default(monkeypatch):
    monkeypatch.delenv(dimwit_server.MUTATION_ENV, raising=False)
    assert dimwit_server.call_tool("dimwit_run_asset", {"asset_id": "x"})["blocked"]
    assert dimwit_server.call_tool("dimwit_author_seed", {"asset_id": "x", "asset_type": "prop"})["blocked"]


def test_ue_mcp_keeps_read_only_ping_available(monkeypatch):
    monkeypatch.delenv(ue_server.MUTATION_ENV, raising=False)
    monkeypatch.setattr(ue_server.ue_client, "call", lambda name, args=None: {"ok": True, "name": name})
    assert ue_server.call_tool("ue_ping", {}) == {"ok": True, "name": "ping"}


def test_ue_mcp_blocks_arbitrary_exec_and_save_by_default(monkeypatch):
    monkeypatch.delenv(ue_server.MUTATION_ENV, raising=False)
    assert ue_server.call_tool("ue_exec", {"code": "result = 1"})["blocked"]
    assert ue_server.call_tool("ue_save_level", {})["blocked"]


def test_ue_mcp_paid_model_calls_require_separate_opt_in(monkeypatch):
    monkeypatch.setenv(ue_server.MUTATION_ENV, "1")
    monkeypatch.delenv(ue_server.PAID_MODEL_ENV, raising=False)
    assert ue_server.call_tool("dimwit_brain", {"prompt": "plan"})["blocked"]
    assert ue_server.call_tool("dimwit_tune_lighting", {"rounds": 1})["blocked"]


def test_ue_bridge_requires_strong_shared_token(monkeypatch):
    monkeypatch.delenv(ue_security.TOKEN_ENV, raising=False)
    try:
        ue_security.bridge_token()
    except RuntimeError as exc:
        assert ue_security.TOKEN_ENV in str(exc)
    else:
        raise AssertionError("bridge accepted a missing authentication token")


def test_ue_bridge_authentication_uses_exact_token():
    expected = "a" * 32
    assert ue_security.authenticated(expected, expected)
    assert not ue_security.authenticated("a" * 31 + "b", expected)
    assert not ue_security.authenticated(None, expected)


def test_ue_screenshot_is_confined_and_bounded(tmp_path):
    capture_root = tmp_path / "captures"
    capture_root.mkdir()
    approved = capture_root / "shot.png"
    assert ue_security.confined_screenshot_path(str(approved), (capture_root,)) == approved.resolve()
    assert ue_security.screenshot_resolution([1600, 900]) == (1600, 900)

    for rejected in (tmp_path / "outside.png", capture_root / "shot.exe"):
        try:
            ue_security.confined_screenshot_path(str(rejected), (capture_root,))
        except ValueError:
            pass
        else:
            raise AssertionError(f"unapproved screenshot path accepted: {rejected}")


def test_remote_lighting_deltas_cannot_become_python_source(monkeypatch):
    calls = []
    monkeypatch.setattr(ue_server.ue_client, "call", lambda *args, **kwargs: calls.append((args, kwargs)))

    try:
        ue_server._apply_deltas({"point_mult": "1.0; __import__('os').system('whoami')"})
    except ValueError as exc:
        assert "must be numeric" in str(exc)
    else:
        raise AssertionError("provider-controlled Python syntax reached the Unreal bridge")

    assert calls == []


def test_numeric_lighting_deltas_preserve_live_tuning(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ue_server.ue_client,
        "call",
        lambda command, args: calls.append((command, args)) or {"ok": True},
    )

    assert ue_server._apply_deltas({"point_mult": 1.25, "exposure_bias_add": -0.5}) == {"ok": True}
    command, args = calls[0]
    assert command == "exec"
    assert "P, S, D, K, F, EB = 1.25, 1.0, 1.0, 1.0, 1.0, -0.5" in args["code"]
