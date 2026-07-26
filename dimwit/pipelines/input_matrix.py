"""HUMAN_INPUT_MATRIX_V1 (Horizon 2, §B7 input matrix) — command-deck input parity checks.

The desktop launcher's command deck accepted keyboard only and could sit unfocused on a windowed
-game launch, so a human (and every controller player) hit a dead UI. This gate proves, from source,
that EVERY deck verb is bound on BOTH a keyboard key AND a gamepad key, that the controller claims
game input on BeginPlay (FInputModeGameOnly), and that the HUD shows dual keyboard+gamepad hints.

Pure static scans over the lobby controller + HUD source. Fail-closed on missing/unreadable source.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
LOBBY_CTRL = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallLobbyPlayerController.cpp"
LOBBY_HUD = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallLobbyHUD.cpp"

# Every deck verb (the controller handler it maps to) must be reachable on keyboard AND gamepad.
REQUIRED_VERBS = ("Interact", "NavLeft", "NavRight", "Confirm", "ClosePanel")

_BINDKEY = re.compile(r"BindKey\(\s*EKeys::(\w+)\s*,\s*IE_Pressed\s*,\s*this\s*,\s*&\s*\w+::(\w+)\s*\)")

# Dual-input HUD hints must carry both a keyboard token and a gamepad glyph token.
KEYBOARD_HINT_TOKENS = ("[ENTER]", "[E]", "[LEFT/RIGHT]")
GAMEPAD_HINT_TOKENS = ("(A)", "(X)", "D-PAD")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def parse_bindings(text: str) -> dict:
    """handler -> {'keyboard': [keys], 'gamepad': [keys]} parsed from BindKey(...) calls."""
    out: dict = {}
    for key, handler in _BINDKEY.findall(text or ""):
        slot = out.setdefault(handler, {"keyboard": [], "gamepad": []})
        (slot["gamepad"] if key.startswith("Gamepad_") else slot["keyboard"]).append(key)
    return out


def check_gamepad_parity(ctrl_text: str) -> dict:
    if not ctrl_text:
        return {"passed": False, "issues": ["lobby controller source empty/unreadable"], "bindings": {}}
    bindings = parse_bindings(ctrl_text)
    issues = []
    for verb in REQUIRED_VERBS:
        slot = bindings.get(verb) or {"keyboard": [], "gamepad": []}
        if not slot["keyboard"]:
            issues.append(f"deck verb {verb} has no keyboard binding")
        if not slot["gamepad"]:
            issues.append(f"deck verb {verb} has no gamepad binding (controller-only player is stuck)")
    return {"passed": not issues, "issues": issues,
            "bindings": {v: bindings.get(v, {}) for v in REQUIRED_VERBS}}


def check_input_mode(ctrl_text: str) -> dict:
    if not ctrl_text:
        return {"passed": False, "issues": ["lobby controller source empty/unreadable"]}
    issues = []
    if "FInputModeGameOnly" not in ctrl_text:
        issues.append("deck controller never claims game input (no FInputModeGameOnly) — a windowed "
                      "launch can sit unfocused and eat every key")
    return {"passed": not issues, "issues": issues}


def check_dual_hints(hud_text: str) -> dict:
    if not hud_text:
        return {"passed": False, "issues": ["lobby HUD source empty/unreadable"]}
    issues = []
    if not any(t in hud_text for t in KEYBOARD_HINT_TOKENS):
        issues.append("deck HUD shows no keyboard input hints")
    if not any(t in hud_text for t in GAMEPAD_HINT_TOKENS):
        issues.append("deck HUD shows no gamepad glyph hints (controller players get no guidance)")
    return {"passed": not issues, "issues": issues}


# ---- live-file readers (registry validators) ----

def live_ctrl_text() -> str | None:
    return _read(LOBBY_CTRL)


def live_hud_text() -> str | None:
    return _read(LOBBY_HUD)
