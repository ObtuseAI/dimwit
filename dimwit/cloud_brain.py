"""Dimwit cloud BRAIN — the three reasoning capabilities, all on OpenRouter (no GPU, no in-chat human):

  1. review_character()  — VISION QA: judge a generated character vs its concept art (shape/color/seams/
                           head-face) and confirm NO glow. Replaces the chat-session review workflow.
  2. plan_queue()        — SELF-DIRECTION: given artifact + QA state, decide what to generate / redo / skip
                           and with what params. Lets Dimwit run itself instead of needing me in the loop.
  3. concept_prompts()   — CONCEPT-ART PROMPTS: invent new WANEFALL characters/variants as text specs+prompts.

Pure functions -> structured dicts. Proof/ledger writes are done by the caller (runner) so doctrine
stays: validate-before-promote, append-only proof, human gate for final acceptance.
"""
from __future__ import annotations

from pathlib import Path
from . import llm

STYLE = ("WANEFALL style law: dark armored alien soldiers, per-species accent energy (the 'Wane'), "
         "clean readable silhouette, NO magenta slop, NO glow/bloom in these renders (emission OFF).")


# ----------------------------------------------------------------- 1. VISION QA
def review_character(name: str, concept_path: str, render_paths: list, desc: str = "",
                     model: str | None = None) -> dict:
    """Vision-judge one character. render_paths: [textured_front, textured_threequarter, clay_front].
    Returns normalized verdict dict (always has the keys, even on parse failure)."""
    prompt = (
        f"You are a hard-nosed game-art director. Judge an AUTO-GENERATED 3D character against its concept art.\n"
        f"Character: {name}. Concept notes: {desc or 'n/a'}.\n"
        f"The FIRST image is the CONCEPT (ground truth). The remaining images are the GENERATED 3D renders "
        f"(textured front, textured three-quarter, neutral clay geometry).\n"
        f"{STYLE}\n\n"
        f"Score each 0-10 honestly: shape (silhouette/proportions), color (palette/material match), "
        f"seams (armor panel/seam definition present & crisp), head_face (head present + face readable, not a blob).\n"
        f"CRITICAL: the user wants ZERO glow/emission/bloom -> set glow_present=true if you see ANY.\n"
        f"Set redo=true if overall<6, OR head is a blob, OR glow is present, OR a render is blank.\n"
        f"Respond with ONLY this JSON: "
        f'{{"shape":int,"color":int,"seams":int,"head_face":int,"glow_present":bool,'
        f'"overall":int,"issues":[str],"redo":bool,"redo_reason":str}}'
    )
    imgs = [concept_path] + list(render_paths)
    data, r = None, {}
    for attempt in range(2):                      # cheap models occasionally wrap/precede JSON -> retry once, firmer
        p = prompt if attempt == 0 else (prompt + "\n\nIMPORTANT: output ONLY the raw JSON object, "
                                         "starting with { and ending with }. No prose, no code fences.")
        try:
            r = llm.vision(p, imgs, model=model, response_json=False, max_tokens=1000, temperature=0.1)
            data = llm.parse_json(r.get("content", ""))
            if data:
                break
        except llm.LLMError as e:
            if attempt == 1:
                return {"character": name, "ok": False, "error": str(e), "overall": 0, "redo": True,
                        "glow_present": None, "issues": ["LLM error"], "model": None}
    if not data:
        return {"character": name, "ok": False, "error": "UNPARSEABLE_JSON", "overall": 0, "redo": True,
                "glow_present": None, "issues": ["model returned unparseable output"],
                "model": r.get("model"), "raw_tail": (r.get("content", "") or "")[-200:]}

    def i(k, d=0):
        try: return int(data.get(k, d))
        except Exception: return d
    return {
        "character": name, "ok": True, "model": r.get("model"),
        "shape": i("shape"), "color": i("color"), "seams": i("seams"), "head_face": i("head_face"),
        "glow_present": bool(data.get("glow_present", False)),
        "overall": i("overall"),
        "issues": data.get("issues") or [],
        "redo": bool(data.get("redo", data.get("overall", 0) < 6)),
        "redo_reason": data.get("redo_reason", ""),
    }


# ----------------------------------------------------------------- 2. SELF-DIRECTION
def plan_queue(state: list, goal: str = "", model: str | None = None) -> dict:
    """state: [{name, exists:bool, qa_overall:int|None, qa_redo:bool, glow:bool}].
    Returns {queue:[{name,action,reason,params}], summary}. action in generate|redo|skip|accept."""
    import json
    prompt = (
        "You are Dimwit's autonomous asset director for the WANEFALL game. "
        "Decide the next build queue from the current state. Each character can be generated, redone "
        "(if QA flagged it), skipped, or accepted (good enough for human review).\n"
        f"{STYLE}\n"
        f"Goal: {goal or 'Get all 8 characters to QA overall >= 7 with no glow.'}\n\n"
        f"Current state:\n{json.dumps(state, indent=2)}\n\n"
        "Rules: redo characters with qa_redo=true or glow=true or qa_overall<6. "
        "For a redo, suggest params (e.g. higher recon_res like 320, or 're-crop tighter'). "
        "Accept characters with qa_overall>=7 and no glow. Respond with ONLY JSON: "
        '{"queue":[{"name":str,"action":"generate|redo|skip|accept","reason":str,'
        '"params":{"recon_res":int}}],"summary":str}'
    )
    try:
        r = llm.chat([{"role": "user", "content": prompt}], model=model, response_json=False,
                     max_tokens=1200, temperature=0.2)
        data = llm.parse_json(r.get("content", "")) or {}
    except llm.LLMError as e:
        return {"ok": False, "error": str(e), "queue": [], "summary": ""}
    return {"ok": True, "model": r.get("model"), "queue": data.get("queue", []),
            "summary": data.get("summary", "")}


# ----------------------------------------------------------------- 3. CONCEPT PROMPTS
def concept_prompts(brief: str, n: int = 3, model: str | None = None) -> dict:
    """Invent N new WANEFALL characters/variants. Returns {characters:[{...spec, concept_prompt}]}."""
    import json
    prompt = (
        "Invent new playable alien soldier characters for the WANEFALL game.\n"
        f"{STYLE}\n"
        f"Brief: {brief}\n"
        f"Produce exactly {n} distinct characters. Each must be visually different in species, palette, "
        "and silhouette from typical sci-fi armor. For each, give a name, species descriptor, accent palette "
        "(the Wane energy color), silhouette descriptor, 3-5 key features, and a single rich 'concept_prompt' "
        "string suitable for a text-to-image model to render a clean full-body front orthographic concept on a "
        "dark background (no glow/bloom).\n"
        'Respond with ONLY JSON: {"characters":[{"name":str,"species":str,"palette":str,'
        '"silhouette":str,"key_features":[str],"concept_prompt":str}]}'
    )
    data, r = {}, {}
    for attempt in range(2):
        p = prompt if attempt == 0 else prompt + "\n\nOutput ONLY the raw JSON, no prose/fences. Be concise per field."
        try:
            r = llm.chat([{"role": "user", "content": p}], model=model, response_json=False,
                         max_tokens=3000, temperature=0.7)
            data = llm.parse_json(r.get("content", "")) or {}
            if data.get("characters"):
                break
        except llm.LLMError as e:
            if attempt == 1:
                return {"ok": False, "error": str(e), "characters": []}
    return {"ok": True, "model": r.get("model"), "characters": data.get("characters", []),
            "raw_tail": "" if data.get("characters") else (r.get("content", "") or "")[-200:]}
