"""PLAYER_INPUT_AND_UI_HYGIENE_V1 (Horizon 2) — RED-first contract tests. Pure static-scan checks
over synthetic ini/HUD source (snapshot law)."""
from __future__ import annotations

from dimwit.pipelines.player_hygiene import (
    CVD_DISTANCE_FLOOR,
    DEBUG_TOKENS,
    RESERVED_BASE,
    SEMANTIC_COLORS,
    check_actions_referenced,
    check_axes_referenced,
    check_axis_bidirectional,
    check_axis_parity,
    check_colorblind_palette,
    check_input_parity,
    check_reserved_keys,
    check_ui_no_debug_leaks,
    parse_action_mappings,
    parse_axis_mappings,
)


def _ini(actions):
    lines = []
    for name, keys in actions.items():
        for k in keys:
            lines.append(f'+ActionMappings=(ActionName="{name}",bShift=False,Key={k})')
    return "\n".join(lines)


FULL = {"Jump": ["SpaceBar", "Gamepad_FaceButton_Bottom"], "Fire": ["F", "Gamepad_RightTrigger"],
        "Slide": ["C", "Gamepad_FaceButton_Right"]}


# ---- input parity ----

def test_full_parity_passes():
    assert check_input_parity(_ini(FULL))["passed"]


def test_keyboard_only_action_fails():
    bad = dict(FULL); bad["Slide"] = ["C"]
    r = check_input_parity(_ini(bad))
    assert not r["passed"] and any("gamepad" in i for i in r["issues"])


def test_gamepad_only_action_fails():
    bad = dict(FULL); bad["Fire"] = ["Gamepad_RightTrigger"]
    assert not check_input_parity(_ini(bad))["passed"]


def test_parse_groups_keys():
    a = parse_action_mappings(_ini(FULL))
    assert a["Slide"]["keyboard"] and a["Slide"]["gamepad"]


# ---- dead declared action ----

def test_referenced_action_passes():
    assert check_actions_referenced(_ini(FULL), 'BindAction("Slide"); "Fire"; "Jump";')["passed"]


def test_dead_action_fails():
    r = check_actions_referenced(_ini(FULL), '"Fire"; "Jump";')   # Slide never referenced
    assert not r["passed"] and "Slide" in r["dead"]


# ---- ui debug leaks ----

def test_clean_hud_passes():
    assert check_ui_no_debug_leaks({"H.cpp": 'Text(TEXT("DEPLOY")); Text(TEXT("RANK"));'})["passed"]


def test_debug_string_leak_fails():
    r = check_ui_no_debug_leaks({"H.cpp": 'Text(TEXT("TODO fix rank")); Text(TEXT("OK"));'})
    assert not r["passed"]


def test_debug_token_in_log_not_flagged():
    # a debug token in a LOG/comment (not a displayed TEXT literal) must not trip the gate
    assert check_ui_no_debug_leaks({"H.cpp": 'UE_LOG(LogTemp, "TODO"); Text(TEXT("DEPLOY"));'})["passed"]


def test_no_hud_fails():
    assert not check_ui_no_debug_leaks({})["passed"]


# ---- colorblind palette ----

_GOOD = 'const FLinearColor Teal(0.2f,0.95f,1.0f), Amber(1.0f,0.72f,0.22f), Crimson(0.97f,0.32f,0.24f), Green(0.3f,1.0f,0.55f), Violet(0.74f,0.48f,1.0f);'


def test_distinct_palette_passes():
    assert check_colorblind_palette(_GOOD)["passed"]


def test_colliding_palette_fails():
    # make Green nearly identical to Amber -> collapses under CVD
    bad = _GOOD.replace("Green(0.3f,1.0f,0.55f)", "Green(1.0f,0.72f,0.22f)")
    assert not check_colorblind_palette(bad)["passed"]


def test_missing_semantic_color_fails():
    assert not check_colorblind_palette('const FLinearColor Teal(0.2f,0.95f,1.0f);')["passed"]


# ---- AXIS_INPUT_HYGIENE_V1: axis parity / bidirectional / dead-axis / reserved keys ----

def _axis_ini(axes):
    """axes: {name: [(key, scale), ...]}"""
    lines = []
    for name, binds in axes.items():
        for key, scale in binds:
            lines.append(f'+AxisMappings=(AxisName="{name}",Scale={scale:.6f},Key={key})')
    return "\n".join(lines)


AXES_FULL = {
    "MoveForward": [("W", 1.0), ("S", -1.0), ("Gamepad_LeftY", 1.0)],
    "MoveRight": [("D", 1.0), ("A", -1.0), ("Gamepad_LeftX", 1.0)],
    "Turn": [("MouseX", 1.0), ("Gamepad_RightX", 1.0)],
    "LookUp": [("MouseY", -1.0), ("Gamepad_RightY", 1.0)],
}


def test_axis_parity_full_passes():
    assert check_axis_parity(_axis_ini(AXES_FULL))["passed"]


def test_axis_parity_no_gamepad_fails():
    bad = {k: v for k, v in AXES_FULL.items()}
    bad["MoveForward"] = [("W", 1.0), ("S", -1.0)]   # keyboard-only, no stick
    r = check_axis_parity(_axis_ini(bad))
    assert not r["passed"] and any("gamepad" in i for i in r["issues"])


def test_axis_parity_no_keyboard_fails():
    bad = {k: v for k, v in AXES_FULL.items()}
    bad["MoveForward"] = [("Gamepad_LeftY", 1.0)]    # pad-only, no KBM
    assert not check_axis_parity(_axis_ini(bad))["passed"]


def test_parse_axis_groups_scale():
    a = parse_axis_mappings(_axis_ini(AXES_FULL))
    assert ("W", 1.0) in a["MoveForward"] and ("S", -1.0) in a["MoveForward"]


def test_axis_bidirectional_full_passes():
    assert check_axis_bidirectional(_axis_ini(AXES_FULL))["passed"]


def test_axis_bidirectional_missing_negative_fails():
    bad = {k: v for k, v in AXES_FULL.items()}
    bad["MoveForward"] = [("W", 1.0), ("Gamepad_LeftY", 1.0)]   # only forward on keys
    r = check_axis_bidirectional(_axis_ini(bad))
    assert not r["passed"] and any("MoveForward" in i for i in r["issues"])


def test_axis_bidirectional_analog_only_exempt():
    # mouse-only look axis has no discrete keys -> inherently bidirectional, must not fail
    assert check_axis_bidirectional(_axis_ini({"Turn": [("MouseX", 1.0)]}))["passed"]


def test_dead_axis_fails():
    r = check_axes_referenced(_axis_ini(AXES_FULL), 'BindAxis("MoveForward"); "MoveRight"; "Turn";')
    assert not r["passed"] and "LookUp" in r["dead"]


def test_referenced_axis_passes():
    blob = 'BindAxis(TEXT("MoveForward")); "MoveRight"; "Turn"; "LookUp";'
    assert check_axes_referenced(_axis_ini(AXES_FULL), blob)["passed"]


def test_reserved_key_clean_passes():
    ini = _axis_ini(AXES_FULL) + '\n+ConsoleKeys=Tilde\nbF11TogglesFullscreen=True\n'
    assert check_reserved_keys(ini)["passed"]


def test_reserved_key_console_collision_fails():
    ini = '+ConsoleKeys=Tilde\n' + _ini({"Fire": ["Tilde", "Gamepad_RightTrigger"]})
    r = check_reserved_keys(ini)
    assert not r["passed"] and any("Tilde" in i for i in r["issues"])


def test_reserved_key_escape_collision_fails():
    r = check_reserved_keys(_ini({"Jump": ["Escape", "Gamepad_FaceButton_Bottom"]}))
    assert not r["passed"] and any("Escape" in i for i in r["issues"])


# ---- ratchet ----

def test_floors_and_sets():
    assert CVD_DISTANCE_FLOOR >= 30.0
    assert set(SEMANTIC_COLORS) >= {"Amber", "Crimson", "Green"}
    assert "placeholder" in DEBUG_TOKENS and "todo" in DEBUG_TOKENS
    assert "Escape" in RESERVED_BASE
