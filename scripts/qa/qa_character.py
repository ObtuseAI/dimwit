"""Dimwit character render QA — GLM 5V (eyes) judges whether the lobby alien reads correctly: a believable
silver armored alien, NOT a chrome/overglowing blob and NOT a flat featureless grey blob. Reuses the Dimwit
brain (dimwit.llm vision). Logs to ledger/character_qa.jsonl.

Usage: python scripts/qa/qa_character.py <image.png> [character_name]
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)
import sys, json, time
from pathlib import Path
from dimwit import llm

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger" / "character_qa.jsonl"

PROMPT = """You are a senior game technical artist doing QA on a screenshot from a sci-fi game's pre-game LOBBY
(a cavern environment). In the centre stands the player's third-person CHARACTER: a {name}, an armored alien
soldier. Ignore the desktop/taskbar and the HUD text — judge ONLY the character model as rendered.

We are checking two specific failure modes we just tried to fix:
- OVERGLOW / CHROME: the armor mirrors the environment and blows out to a bright white/silver glare (BAD).
- FLAT GREY BLOB: the armor is so flat/dark/low-contrast it looks like a featureless smooth mannequin (BAD).
GOOD = a readable armored alien: you can see armor panels/plates, limbs, head shape, material that looks like
brushed/satin metal (not a mirror, not flat clay), with some shading that reveals 3D form.

Return STRICT JSON, no prose:
{{
  "character_visible": <bool>,
  "reads_as_armored_alien": <bool>,
  "overglow_or_chrome": <bool>,
  "flat_grey_blob": <bool>,
  "detail_score": <int 0-100>,   // how much armor/surface detail reads (0 blob, 100 crisp)
  "issues": ["<short>", ...],
  "verdict": "PASS" | "ADJUST" | "FAIL",
  "summary": "<one sentence>"
}}
PASS only if character_visible and reads_as_armored_alien are true AND overglow_or_chrome is false AND
flat_grey_blob is false AND detail_score >= 60. Be decisive and honest."""


def qa(image: str, name: str = "silver armored alien (Ekris)") -> dict:
    prompt = PROMPT.format(name=name)
    r = llm.vision(prompt, [image], response_json=False, max_tokens=2600, temperature=0.1)
    data = llm.parse_json(r.get("content", "")) or {}
    out = {
        "ok": bool(data), "image": image, "vision_model": r.get("model"),
        "verdict": data.get("verdict"), "character_visible": data.get("character_visible"),
        "reads_as_armored_alien": data.get("reads_as_armored_alien"),
        "overglow_or_chrome": data.get("overglow_or_chrome"),
        "flat_grey_blob": data.get("flat_grey_blob"),
        "detail_score": data.get("detail_score"), "issues": data.get("issues", []),
        "summary": data.get("summary"),
        "raw_tail": "" if data else (r.get("content", "") or "")[-400:],
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": int(time.time()), **out}) + "\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/qa/qa_character.py <image.png> [character_name]"); sys.exit(2)
    img = sys.argv[1]
    nm = sys.argv[2] if len(sys.argv) > 2 else "silver armored alien (Ekris)"
    if not Path(img).exists():
        print(json.dumps({"ok": False, "error": f"image not found: {img}"})); sys.exit(1)
    print(json.dumps(qa(img, nm), indent=2))
