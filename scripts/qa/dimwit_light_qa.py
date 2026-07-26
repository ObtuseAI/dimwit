"""Dimwit LIGHTING QA — GLM 5V-turbo (eyes) + GLM 5.2 (brain) judge a UE front-end/level render and return a
structured readability verdict with concrete lighting deltas. This is the vision half of "Dimwit using GLM 5.2
to fix it": the render is graded, issues named, and multiplier deltas proposed so the build can self-correct.

Usage:  python scripts/qa/dimwit_light_qa.py <image.png> [scene_context]
Output: JSON verdict to stdout + appended to ledger/light_qa.jsonl
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)
import sys, json, time
from pathlib import Path
from dimwit import llm

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger" / "light_qa.jsonl"

PROMPT = """You are a senior game technical artist doing QA on a screenshot of a sci-fi game's FRONT-END menu room
(an enclosed cargo hold called "THE HOLD"). The player stands in it and picks their character/weapon/mode.
A character lineup, weapon rack, crates, and glowing teal "Wane" accent seams should ALL be clearly visible.
The desktop/taskbar around the game window is NOT part of the scene — ignore it.

Judge ONLY the rendered 3D scene + its HUD. Decide if a player could clearly read the room.

Return STRICT JSON, no prose, with this exact shape:
{
  "readability": <int 0-100>,            // 0 = black void, 100 = crisp and clearly readable
  "too_dark": <bool>,
  "too_bright": <bool>,
  "surfaces_visible": <bool>,            // are floor/walls/props lit (not pure black)?
  "accents_visible": <bool>,             // do the teal glowing seams read?
  "issues": [ "<short issue>", ... ],
  "deltas": {                            // MULTIPLIERS on current lighting (1.0 = leave as-is)
    "point_mult": <float>,               // overhead/fill point lights
    "spot_mult": <float>,                // station spotlights
    "directional_mult": <float>,
    "skylight_mult": <float>,
    "exposure_bias_add": <float>,        // additive EV to auto-exposure bias
    "fog_density_mult": <float>
  },
  "verdict": "PASS" | "ADJUST" | "FAIL",
  "summary": "<one sentence>"
}
PASS only if readability >= 78 and surfaces_visible is true. Be decisive with the multipliers."""


def qa(image: str, context: str = "") -> dict:
    cfg = llm._load_config()
    prompt = PROMPT + (f"\n\nExtra scene context: {context}" if context else "")
    # GLM reasoning models spend completion tokens on a separate `reasoning` field before `content`,
    # so budget generously or `content` comes back truncated/empty.
    r = llm.vision(prompt, [image], response_json=False, max_tokens=2600, temperature=0.1)
    data = llm.parse_json(r.get("content", "")) or {}
    out = {
        "ok": bool(data),
        "image": image,
        "vision_model": r.get("model"),
        "verdict": data.get("verdict"),
        "readability": data.get("readability"),
        "too_dark": data.get("too_dark"),
        "too_bright": data.get("too_bright"),
        "surfaces_visible": data.get("surfaces_visible"),
        "accents_visible": data.get("accents_visible"),
        "issues": data.get("issues", []),
        "deltas": data.get("deltas", {}),
        "summary": data.get("summary"),
        "raw_tail": "" if data else (r.get("content", "") or "")[-300:],
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": int(time.time()), **out}) + "\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/qa/dimwit_light_qa.py <image.png> [context]"); sys.exit(2)
    img = sys.argv[1]
    ctx = sys.argv[2] if len(sys.argv) > 2 else ""
    if not Path(img).exists():
        print(json.dumps({"ok": False, "error": f"image not found: {img}"})); sys.exit(1)
    print(json.dumps(qa(img, ctx), indent=2))
