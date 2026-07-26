"""Dimwit cloud LLM client — OpenRouter, stdlib only (urllib).

Gives Dimwit a cloud BRAIN (text + vision) without adding pip deps and without touching the
local GPU pipeline. The heavy image->3D work (Zero123++/InstantMesh) stays on the RTX 3070;
OpenRouter only powers REASONING: vision QA, self-direction, concept prompts.

Key resolution (first hit wins):
  1. env  OPENROUTER_API_KEY
  2. config/secrets.json  -> {"openrouter_api_key": "sk-or-..."}
The secrets file is git-ignored; the key is NEVER committed or logged.

Models are configured in config/llm_config.json (text + vision), overridable per call.
"""
from __future__ import annotations

import os, json, time, base64, io, urllib.request, urllib.error
from pathlib import Path

RAIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG = RAIN_ROOT / "config"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

DEFAULTS = {
    # Match the operator's GLM directive so a partially-loaded config can never misroute to a stale model.
    "text_model":   "z-ai/glm-5.2",
    "vision_model": "z-ai/glm-5v-turbo",
    "max_tokens":   1200,
    "temperature":  0.2,
    "max_image_px": 896,          # downscale long edge before base64 to keep payloads small
    "retries":      3,
    "timeout_s":    120,
    "enable_thinking": False,     # GLM-5.2/5V are THINKING models; for structured QA we want the ANSWER not the
                                  # visible chain-of-thought (it truncates small responses). Disable by default.
}


class LLMError(RuntimeError):
    pass


def _load_config() -> dict:
    cfg = dict(DEFAULTS)
    f = CONFIG / "llm_config.json"
    if f.exists():
        try:
            cfg.update(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def get_api_key() -> str | None:
    k = os.environ.get("OPENROUTER_API_KEY")
    if k and k.strip():
        return k.strip()
    sf = CONFIG / "secrets.json"
    if sf.exists():
        try:
            return (json.loads(sf.read_text(encoding="utf-8")).get("openrouter_api_key") or "").strip() or None
        except Exception:
            return None
    return None


def is_configured() -> bool:
    return bool(get_api_key())


def _b64_image(path: str | Path, max_px: int) -> str:
    """Resize (long edge -> max_px) and return a PNG data URL. Uses Pillow (already a dep)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if max(w, h) > max_px:
        s = max_px / max(w, h)
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _post(payload: dict, cfg: dict) -> dict:
    key = get_api_key()
    if not key:
        raise LLMError("NO_API_KEY: set OPENROUTER_API_KEY env or config/secrets.json {openrouter_api_key}")
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/dimwit",
        "X-Title": "Dimwit Asset Engine",
    }
    last = None
    for attempt in range(int(cfg["retries"])):
        try:
            req = urllib.request.Request(ENDPOINT, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=int(cfg["timeout_s"])) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {e.code}: {body}"
            if e.code in (429, 500, 502, 503, 529) and attempt < int(cfg["retries"]) - 1:
                time.sleep(2 ** attempt + 1)
                continue
            raise LLMError(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"NET: {e}"
            if attempt < int(cfg["retries"]) - 1:
                time.sleep(2 ** attempt + 1)
                continue
            raise LLMError(last)
    raise LLMError(last or "unknown")


def chat(messages: list, model: str | None = None, max_tokens: int | None = None,
         temperature: float | None = None, response_json: bool = False,
         tools: list | None = None, tool_choice=None) -> dict:
    """Plain text chat. Returns {ok, content, model, usage, tool_calls, raw}. response_json asks for a JSON
    object; `tools` (OpenRouter/OpenAI function schemas) enables the brain agent loop (task 14)."""
    cfg = _load_config()
    payload = {
        "model": model or cfg["text_model"],
        "messages": messages,
        "max_tokens": max_tokens or cfg["max_tokens"],
        "temperature": cfg["temperature"] if temperature is None else temperature,
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}
    resolved_model = payload["model"]
    exempt = any(str(resolved_model).startswith(p)
                 for p in cfg.get("thinking_disable_exempt_prefixes", ["google/"]))
    if not cfg.get("enable_thinking", False) and not exempt:
        # disable hidden reasoning so small/structured replies aren't truncated mid-think (both the model-specific
        # GLM knob and OpenRouter's unified control). EXEMPT providers that MANDATE reasoning — gemini-3.5-flash
        # hard-rejects reasoning:{enabled:false} with HTTP 400 "Reasoning is mandatory" (observed live 2026-07-02).
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["reasoning"] = {"enabled": False}
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    # An HTTP-200 completion with an EMPTY message carries no signal (observed live: transient
    # provider blips) — retry it like a transport error; after the last attempt return ok=False.
    attempts = max(1, int(cfg["retries"]))
    for attempt in range(attempts):
        raw = _post(payload, cfg)
        msg = (raw.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content", "")
        ok = bool(content) or bool(msg.get("tool_calls"))
        if ok or attempt == attempts - 1:
            return {"ok": ok, "content": content,
                    "tool_calls": msg.get("tool_calls", []), "model": raw.get("model"),
                    "usage": raw.get("usage", {}), "raw": raw}
        time.sleep(2 ** attempt)


def vision(prompt: str, image_paths: list, model: str | None = None,
           max_tokens: int | None = None, temperature: float | None = None,
           response_json: bool = False, system: str | None = None,
           max_image_px: int | None = None) -> dict:
    """Vision chat: prompt + one or more local images. Returns {ok, content, ...}.
    max_image_px overrides the config downscale for detail-critical judging (e.g. seam lines)."""
    cfg = _load_config()
    content = [{"type": "text", "text": prompt}]
    px = int(max_image_px or cfg["max_image_px"])
    for p in image_paths:
        if Path(p).exists():
            content.append({"type": "image_url",
                            "image_url": {"url": _b64_image(p, px)}})
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": content}]
    return chat(msgs, model=model or cfg["vision_model"],
                max_tokens=max_tokens, temperature=temperature, response_json=response_json)


def parse_json(content: str) -> dict | None:
    """Best-effort JSON extraction (handles ```json fences / surrounding prose)."""
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    try:
        return json.loads(s)
    except Exception:
        return None


def health() -> dict:
    """Cheap connectivity + key check. Returns {ok, model, error}."""
    if not is_configured():
        return {"ok": False, "error": "NO_API_KEY", "model": None}
    try:
        r = chat([{"role": "user", "content": "Reply with exactly: DIMWIT_OK"}], max_tokens=64, temperature=0)
        return {"ok": "DIMWIT_OK" in (r["content"] or ""), "model": r["model"], "content": r["content"]}
    except LLMError as e:
        return {"ok": False, "error": str(e), "model": None}
