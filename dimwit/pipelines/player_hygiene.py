"""PLAYER_INPUT_AND_UI_HYGIENE_V1 + AXIS_INPUT_HYGIENE_V1 (Horizon 2) — batched static
player-surface hygiene checks. All pure static scans, no UE runtime / no re-cook:

ActionMapping + UI (V1):
  1. gameplay input parity  — every DefaultInput.ini ActionMapping bound on keyboard AND gamepad
  2. no dead declared action — every ActionMapping name is referenced in Source/ (not ini bloat)
  3. UI debug/placeholder leak — displayed HUD string literals carry no debug/jargon/placeholder tokens
  4. colorblind-safe palette — the deck's semantic colors stay distinguishable under deuteranopia

AxisMapping (Move/Look — the load-bearing continuous controls the V1 scans never saw):
  5. axis gamepad parity     — every AxisMapping reachable on KBM AND gamepad
  6. axis bidirectional      — a discrete-key axis (WASD) offers BOTH + and - directions
  7. no dead declared axis   — every AxisName is BindAxis'd in Source/
  8. no reserved-key capture — no gameplay Action/Axis binds a reserved system key (Escape/console/F11)

Fail-closed on missing/unreadable source.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
SRC = PROJECT / "Source" / "WanefallGreybox"
INI_PATH = PROJECT / "Config" / "DefaultInput.ini"
LOBBY_HUD = SRC / "Private" / "WanefallLobbyHUD.cpp"
# Player-facing HUD-drawing source scanned for displayed-string leaks.
HUD_SOURCES = (
    SRC / "Private" / "WanefallLobbyHUD.cpp",
    SRC / "Private" / "WanefallMatchHUD.cpp",
    SRC / "Private" / "WanefallPrototypeHUD.cpp",
)

# Debug / placeholder tokens that must never reach a displayed HUD string (case-insensitive).
DEBUG_TOKENS = ("todo", "fixme", "xxx", "placeholder", "lorem", "asdf", "wip", "hack",
                "debugonly", "test123", "temp text", "dummy")

_ACTION = re.compile(r'ActionName="([^"]+)".*?Key=(\w+)')
# AxisMappings=(AxisName="MoveForward",Scale=1.000000,Key=W) — capture name, signed scale, key.
_AXIS = re.compile(r'AxisName="([^"]+)",Scale=(-?[\d.]+),Key=(\w+)')
_CONSOLE_KEY = re.compile(r'^\+?ConsoleKeys=(\w+)', re.MULTILINE)
_TEXT_LIT = re.compile(r'TEXT\("([^"]*)"\)')
# Matches `Name(r, g, b` — captures both `FLinearColor Teal(...)` and comma-list `..., Amber(...)`
# declarations. Names whose args are expressions (Bar(Pad+18.0f...)) don't start with a digit, so
# they don't match; a bare FLinearColor(0.0f,...) matches as name "FLinearColor" and is ignored.
_FLINCOLOR = re.compile(r'\b(\w+)\(\s*([\d.]+)f?\s*,\s*([\d.]+)f?\s*,\s*([\d.]+)f?')

# Deuteranopia simulation matrix (Machado 2009, severity 1.0) applied to sRGB (approx, sufficient
# for distinguishability gating). The deck's semantic colors must survive it.
_DEUTAN = ((0.367, 0.861, -0.228), (0.280, 0.673, 0.047), (-0.012, 0.043, 0.969))
# Semantic colors that carry meaning and must stay mutually distinct (names as in the lobby HUD).
SEMANTIC_COLORS = ("Teal", "Amber", "Crimson", "Green", "Violet")
CVD_DISTANCE_FLOOR = 40.0     # min pairwise 0..255 Euclidean distance after CVD sim

# Reserved system keys a gameplay Action/Axis must never claim. Escape is the universal UI/pause
# key; the console key(s) and F11 are DERIVED from the ini's own system config (ConsoleKeys=,
# bF11TogglesFullscreen=True) so the reserved set stays honest to what this project actually reserves.
RESERVED_BASE = ("Escape",)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def parse_action_mappings(ini_text: str) -> dict:
    out: dict = {}
    for name, key in _ACTION.findall(ini_text or ""):
        slot = out.setdefault(name, {"keyboard": [], "gamepad": []})
        (slot["gamepad"] if key.startswith("Gamepad_") else slot["keyboard"]).append(key)
    return out


def check_input_parity(ini_text: str) -> dict:
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"], "actions": {}}
    actions = parse_action_mappings(ini_text)
    if not actions:
        return {"passed": False, "issues": ["no ActionMappings parsed"], "actions": {}}
    issues = []
    for name, slot in sorted(actions.items()):
        if not slot["keyboard"]:
            issues.append(f"action {name} has no keyboard binding")
        if not slot["gamepad"]:
            issues.append(f"action {name} has no gamepad binding (controller player can't do it)")
    return {"passed": not issues, "issues": issues, "actions": {k: v for k, v in actions.items()}}


def check_actions_referenced(ini_text: str, source_blob: str) -> dict:
    """Every declared action must appear somewhere in source (no dead ini declaration)."""
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"], "dead": []}
    actions = parse_action_mappings(ini_text)
    blob = source_blob or ""
    dead = [name for name in actions if f'"{name}"' not in blob and name not in blob]
    if dead:
        return {"passed": False, "issues": [f"declared action never referenced in source: {d}" for d in dead],
                "dead": dead}
    return {"passed": True, "issues": [], "dead": []}


def _displayed_strings(text: str) -> list:
    return _TEXT_LIT.findall(text or "")


def check_ui_no_debug_leaks(hud_texts: dict) -> dict:
    """hud_texts: {filename: source}. Scan DISPLAYED string literals for debug/placeholder tokens."""
    if not hud_texts or not any(hud_texts.values()):
        return {"passed": False, "issues": ["no HUD source available to scan"], "hits": []}
    hits = []
    for name, text in hud_texts.items():
        for lit in _displayed_strings(text):
            low = lit.lower()
            for tok in DEBUG_TOKENS:
                if tok in low:
                    hits.append(f"{name}: displayed string {lit!r} contains debug token {tok!r}")
    return {"passed": not hits, "issues": hits, "hits": hits}


def _parse_named_colors(hud_text: str) -> dict:
    out = {}
    for name, r, g, b in _FLINCOLOR.findall(hud_text or ""):
        if name not in out:
            out[name] = (float(r), float(g), float(b))
    return out


def _cvd(rgb: tuple) -> tuple:
    r, g, b = rgb
    return tuple(sum(m[i] * c for i, c in enumerate((r, g, b))) for m in _DEUTAN)


def _dist255(a: tuple, b: tuple) -> float:
    return (sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5) * 255.0


def check_colorblind_palette(hud_text: str, floor: float = CVD_DISTANCE_FLOOR) -> dict:
    if not hud_text:
        return {"passed": False, "issues": ["lobby HUD source empty/unreadable"], "pairs": []}
    colors = _parse_named_colors(hud_text)
    present = [c for c in SEMANTIC_COLORS if c in colors]
    missing = [c for c in SEMANTIC_COLORS if c not in colors]
    issues = [f"semantic color {c} not found in deck HUD" for c in missing]
    sim = {c: _cvd(colors[c]) for c in present}
    pairs = []
    for i, a in enumerate(present):
        for b in present[i + 1:]:
            d = _dist255(sim[a], sim[b])
            pairs.append({"a": a, "b": b, "cvd_distance": round(d, 1)})
            if d < floor:
                issues.append(f"{a} vs {b} collapse under deuteranopia (dist {d:.1f} < {floor})")
    return {"passed": not issues, "issues": issues, "pairs": pairs}


# ---- AXIS_INPUT_HYGIENE_V1: AxisMappings (movement + camera) parity ------------------------------
# The four ActionMapping checks above never see AxisMappings (Move/Look) — the load-bearing
# continuous controls. These four extend the same hygiene to axes: gamepad parity, keyboard
# bidirectionality, live wiring, and no collision with reserved system keys.

def _is_gamepad(key: str) -> bool:
    return key.startswith("Gamepad_")


def _is_digital_kbd(key: str) -> bool:
    """A discrete keyboard key (WASD/letters) — not an analog gamepad stick or mouse axis."""
    return not _is_gamepad(key) and not key.startswith("Mouse")


def parse_axis_mappings(ini_text: str) -> dict:
    """{AxisName: [(Key, signed_scale), ...]}"""
    out: dict = {}
    for name, scale, key in _AXIS.findall(ini_text or ""):
        out.setdefault(name, []).append((key, float(scale)))
    return out


def check_axis_parity(ini_text: str) -> dict:
    """Every AxisMapping must be reachable on KBM (keyboard/mouse) AND on a gamepad key."""
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"], "axes": {}}
    axes = parse_axis_mappings(ini_text)
    if not axes:
        return {"passed": False, "issues": ["no AxisMappings parsed"], "axes": {}}
    issues = []
    for name, binds in sorted(axes.items()):
        keys = [k for k, _ in binds]
        if not any(_is_gamepad(k) for k in keys):
            issues.append(f"axis {name} has no gamepad binding (controller player can't {name})")
        if not any(not _is_gamepad(k) for k in keys):
            issues.append(f"axis {name} has no keyboard/mouse binding")
    return {"passed": not issues, "issues": issues, "axes": {k: v for k, v in axes.items()}}


def check_axis_bidirectional(ini_text: str) -> dict:
    """An axis driven by discrete keyboard keys must offer BOTH directions (+ and - scale) —
    else a regression that drops one key leaves the player able to walk one way only. Analog
    axes (mouse/stick) are inherently bidirectional and exempt."""
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"]}
    axes = parse_axis_mappings(ini_text)
    if not axes:
        return {"passed": False, "issues": ["no AxisMappings parsed"]}
    issues = []
    for name, binds in sorted(axes.items()):
        digital = [(k, s) for k, s in binds if _is_digital_kbd(k)]
        if not digital:
            continue  # analog-only axis (mouse/stick) — bidirectional by construction
        signs = {("+" if s >= 0 else "-") for _, s in digital}
        if signs != {"+", "-"}:
            missing = "negative" if "-" not in signs else "positive"
            issues.append(f"axis {name} keyboard keys only drive {sorted(signs)} — no {missing} direction")
    return {"passed": not issues, "issues": issues}


def check_axes_referenced(ini_text: str, source_blob: str) -> dict:
    """Every declared AxisName must be BindAxis'd (referenced) in source — no dead axis declaration."""
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"], "dead": []}
    axes = parse_axis_mappings(ini_text)
    blob = source_blob or ""
    dead = [name for name in axes if f'"{name}"' not in blob and name not in blob]
    if dead:
        return {"passed": False, "issues": [f"declared axis never referenced in source: {d}" for d in dead],
                "dead": dead}
    return {"passed": True, "issues": [], "dead": []}


def _reserved_keys(ini_text: str) -> set:
    reserved = set(RESERVED_BASE)
    reserved.update(_CONSOLE_KEY.findall(ini_text or ""))            # e.g. Tilde
    if re.search(r'bF11TogglesFullscreen\s*=\s*True', ini_text or ""):
        reserved.add("F11")
    return reserved


def check_reserved_keys(ini_text: str) -> dict:
    """No gameplay Action or Axis may bind a reserved system key (pause/console/fullscreen)."""
    if not ini_text:
        return {"passed": False, "issues": ["DefaultInput.ini empty/unreadable"], "reserved": []}
    reserved = _reserved_keys(ini_text)
    issues = []
    for name, slot in parse_action_mappings(ini_text).items():
        for k in slot["keyboard"] + slot["gamepad"]:
            if k in reserved:
                issues.append(f"action {name} bound to reserved system key {k}")
    for name, binds in parse_axis_mappings(ini_text).items():
        for k, _ in binds:
            if k in reserved:
                issues.append(f"axis {name} bound to reserved system key {k}")
    return {"passed": not issues, "issues": issues, "reserved": sorted(reserved)}


# ---- live readers (registry validators) ----

def live_ini() -> str | None:
    return _read(INI_PATH)


def live_source_blob() -> str:
    parts = []
    for p in list(SRC.glob("Private/*.cpp")) + list(SRC.glob("Public/*.h")):
        t = _read(p)
        if t:
            parts.append(t)
    return "\n".join(parts)


def live_hud_texts() -> dict:
    return {p.name: (_read(p) or "") for p in HUD_SOURCES}


def live_lobby_hud() -> str | None:
    return _read(LOBBY_HUD)
