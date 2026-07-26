from dimwit.capabilities import ue_live


def test_generic_live_capability_rejects_exec_and_save(monkeypatch):
    calls = []
    monkeypatch.setattr(ue_live.ue_client, "call", lambda *args, **kwargs: calls.append((args, kwargs)))

    for command in ("exec", "save_level", "screenshot"):
        result = ue_live.call(command, {"code": "result = 1"})
        assert result["blocked"] is True

    assert calls == []


def test_generic_live_capability_preserves_read_only_inspection(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ue_live.ue_client,
        "call",
        lambda command, params: calls.append((command, params)) or {"ok": True},
    )

    assert ue_live.call("ping") == {"ok": True}
    assert ue_live.call("list_actors") == {"ok": True}
    assert calls == [("ping", {}), ("list_actors", {})]
