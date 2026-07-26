"""Empty-completion robustness (H1B2): OpenRouter occasionally returns HTTP-200 with an empty
message (observed live 2026-07-02: a calibration vote blocked on 'empty LLM response'). An empty
completion carries no signal and must be retried like a transport error - and still fail closed
(ok=False) when every attempt comes back empty."""
from dimwit import llm


def _raw(content):
    return {"choices": [{"message": {"content": content}}], "model": "m", "usage": {}}


def test_chat_retries_empty_completion(monkeypatch):
    calls = []

    def fake_post(payload, cfg):
        calls.append(1)
        return _raw("" if len(calls) == 1 else '{"ok": 1}')

    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    r = llm.chat([{"role": "user", "content": "x"}])
    assert r["ok"] is True
    assert r["content"] == '{"ok": 1}'
    assert len(calls) == 2


def test_thinking_disable_exempts_reasoning_mandatory_providers(monkeypatch):
    """gemini-3.5-flash rejects reasoning:{enabled:false} with HTTP 400 ('Reasoning is mandatory')
    - observed live 2026-07-02: the exempt provider must get NO thinking-disable knobs, while GLM
    (which needs them to avoid truncated structured replies) keeps them."""
    payloads = []

    def fake_post(payload, cfg):
        payloads.append(payload)
        return _raw("x")

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.chat([{"role": "user", "content": "q"}], model="google/gemini-3.5-flash")
    llm.chat([{"role": "user", "content": "q"}], model="z-ai/glm-5v-turbo")
    goog, glm = payloads
    assert "reasoning" not in goog and "chat_template_kwargs" not in goog
    assert glm["reasoning"] == {"enabled": False}
    assert glm["chat_template_kwargs"] == {"enable_thinking": False}


def test_chat_all_empty_fails_closed(monkeypatch):
    calls = []

    def fake_post(payload, cfg):
        calls.append(1)
        return _raw("")

    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    r = llm.chat([{"role": "user", "content": "x"}])
    assert r["ok"] is False
    assert len(calls) >= 2
