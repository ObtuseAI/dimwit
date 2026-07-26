"""Brain agency (task 14): a bounded (<=3) tool-calling loop.

Replaces a hardcoded qa->plan->redo switch with GLM 5.2 *choosing* Dimwit capabilities (from the registry) to
reach a goal. Degrade-safe: if the LLM is unconfigured it returns a structured blocker (never a silent empty /
laundered failure). Safe-by-default: only non-mutating TEST/DESIGN capabilities are exposed unless the caller
explicitly passes `allowed` (so the model can't reach EXECUTE/ue.live arbitrary exec by accident).
"""
from __future__ import annotations

import json

from .. import llm
from . import registry

MAX_STEPS = 3
_SAFE_DOMAINS = {"TEST", "DESIGN"}


def _fn_name(cap_name: str) -> str:
    return cap_name.replace("/", "__").replace(".", "_")


def _tool_schemas(allowed):
    caps = registry.list_capabilities()
    if allowed:
        caps = [c for c in caps if c.name in allowed]
    else:
        caps = [c for c in caps if c.domain in _SAFE_DOMAINS]      # safe default
    schemas = [{"type": "function", "function": {
        "name": _fn_name(c.name), "description": f"[{c.domain}] {c.description}",
        "parameters": {"type": "object", "properties": {"args": {"type": "object"}}}}} for c in caps]
    namemap = {_fn_name(c.name): c.name for c in caps}
    return schemas, namemap


def run_agent(goal: str, allowed: list | None = None, context: str = "", max_steps: int = MAX_STEPS) -> dict:
    if not llm.is_configured():
        return {"ok": False, "blocker": "LLM_NOT_CONFIGURED", "goal": goal,
                "note": "set OPENROUTER_API_KEY or config/secrets.json"}
    schemas, namemap = _tool_schemas(allowed)
    messages = [
        {"role": "system", "content": "You are Dimwit's build brain. Use the provided capabilities to reach the "
                                      "goal. Be decisive; call a tool when useful; stop when the goal is met."},
        {"role": "user", "content": f"GOAL: {goal}\nCONTEXT: {context}"},
    ]
    trace = []
    for step in range(max_steps):
        r = llm.chat(messages, tools=schemas, max_tokens=1200)
        calls = r.get("tool_calls") or []
        if not calls:
            return {"ok": True, "final": r.get("content", ""), "steps": step, "trace": trace}
        for call in calls:
            fn = call.get("function") or {}
            requested_name = fn.get("name")
            cap_name = namemap.get(requested_name)
            try:
                args = (json.loads(fn.get("arguments") or "{}") or {}).get("args", {}) or {}
            except Exception:
                args = {}
            if cap_name is None:
                # Provider output is untrusted. Only names in the exact schema set
                # advertised for this run may cross into the registry dispatcher.
                summary = f"ERROR rejected unadvertised capability: {requested_name!r}"
                trace_name = str(requested_name or "")
            else:
                try:
                    result = registry.dispatch(cap_name, **args) if isinstance(args, dict) else registry.dispatch(cap_name)
                    summary = (result if isinstance(result, str) else json.dumps(result, default=str))[:600]
                except Exception as e:
                    summary = f"ERROR dispatching {cap_name}: {e}"
                trace_name = cap_name
            trace.append({"step": step, "capability": trace_name, "result_summary": summary})
            messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
            messages.append({"role": "tool", "tool_call_id": call.get("id", "0"), "content": summary})
    return {"ok": True, "final": "max steps reached", "steps": max_steps, "trace": trace}
