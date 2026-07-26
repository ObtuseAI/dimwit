from dimwit.capabilities import agent_loop


def _tool_call(name: str):
    return {
        "id": "call-1",
        "function": {"name": name, "arguments": '{"args": {}}'},
    }


def test_agent_rejects_capability_not_advertised_for_run(monkeypatch):
    responses = iter([
        {"tool_calls": [_tool_call("EXECUTE__ue_live")]},
        {"content": "done"},
    ])
    dispatched = []
    monkeypatch.setattr(agent_loop.llm, "is_configured", lambda: True)
    monkeypatch.setattr(agent_loop.llm, "chat", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(agent_loop.registry, "dispatch", lambda name, **kwargs: dispatched.append(name))

    result = agent_loop.run_agent("inspect only", allowed=["TEST/gate.run_all"])

    assert dispatched == []
    assert "rejected unadvertised capability" in result["trace"][0]["result_summary"]


def test_agent_preserves_advertised_capability_dispatch(monkeypatch):
    schemas, namemap = agent_loop._tool_schemas(["TEST/gate.run_all"])
    advertised = schemas[0]["function"]["name"]
    responses = iter([
        {"tool_calls": [_tool_call(advertised)]},
        {"content": "done"},
    ])
    dispatched = []
    monkeypatch.setattr(agent_loop.llm, "is_configured", lambda: True)
    monkeypatch.setattr(agent_loop.llm, "chat", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(
        agent_loop.registry,
        "dispatch",
        lambda name, **kwargs: dispatched.append(name) or {"ok": True},
    )

    result = agent_loop.run_agent("run the allowed gate", allowed=["TEST/gate.run_all"])

    assert dispatched == [namemap[advertised]]
    assert result["trace"][0]["capability"] == "TEST/gate.run_all"
