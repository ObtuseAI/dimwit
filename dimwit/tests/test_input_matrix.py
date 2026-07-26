"""HUMAN_INPUT_MATRIX_V1 (Horizon 2) — RED-first contract tests for deck input parity.

Pure static-scan checks over synthetic controller/HUD source (snapshot law).
"""
from __future__ import annotations

from dimwit.pipelines.input_matrix import (
    GAMEPAD_HINT_TOKENS,
    KEYBOARD_HINT_TOKENS,
    REQUIRED_VERBS,
    check_dual_hints,
    check_gamepad_parity,
    check_input_mode,
    parse_bindings,
)


def _ctrl(gamepad=True, keyboard=True, input_mode=True) -> str:
    lines = ["void AWanefallLobbyPlayerController::BeginPlay(){"]
    if input_mode:
        lines.append("SetInputMode(FInputModeGameOnly());")
    lines.append("}")
    lines.append("void AWanefallLobbyPlayerController::SetupInputComponent(){")
    kb = {"Interact": "E", "NavLeft": "Left", "NavRight": "Right", "Confirm": "Enter",
          "ClosePanel": "Escape"}
    gp = {"Interact": "Gamepad_FaceButton_Left", "NavLeft": "Gamepad_DPad_Left",
          "NavRight": "Gamepad_DPad_Right", "Confirm": "Gamepad_FaceButton_Bottom",
          "ClosePanel": "Gamepad_FaceButton_Right"}
    for verb in REQUIRED_VERBS:
        if keyboard:
            lines.append(f"InputComponent->BindKey(EKeys::{kb[verb]}, IE_Pressed, this, "
                         f"&AWanefallLobbyPlayerController::{verb});")
        if gamepad:
            lines.append(f"InputComponent->BindKey(EKeys::{gp[verb]}, IE_Pressed, this, "
                         f"&AWanefallLobbyPlayerController::{verb});")
    lines.append("}")
    return "\n".join(lines)


HUD_DUAL = 'Text(TEXT("[ENTER] / (A)  DEPLOY")); Text(TEXT("[E] / (X)  cycle")); Text(TEXT("D-PAD"));'
HUD_KB_ONLY = 'Text(TEXT("[ENTER] DEPLOY")); Text(TEXT("[E] cycle"));'


# ---- parity ----

def test_full_parity_passes():
    assert check_gamepad_parity(_ctrl())["passed"]


def test_keyboard_only_fails():
    r = check_gamepad_parity(_ctrl(gamepad=False))
    assert not r["passed"]
    assert any("gamepad" in i for i in r["issues"])


def test_missing_one_verb_gamepad_fails():
    ctrl = _ctrl()
    ctrl = ctrl.replace("InputComponent->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Pressed, this, "
                        "&AWanefallLobbyPlayerController::Confirm);", "")
    assert not check_gamepad_parity(ctrl)["passed"]


def test_empty_source_fails():
    assert not check_gamepad_parity("")["passed"]


def test_parse_groups_keys():
    b = parse_bindings(_ctrl())
    assert b["Confirm"]["keyboard"] and b["Confirm"]["gamepad"]


# ---- input mode ----

def test_input_mode_present_passes():
    assert check_input_mode(_ctrl())["passed"]


def test_input_mode_missing_fails():
    assert not check_input_mode(_ctrl(input_mode=False))["passed"]


# ---- dual hints ----

def test_dual_hints_pass():
    assert check_dual_hints(HUD_DUAL)["passed"]


def test_keyboard_only_hints_fail():
    assert not check_dual_hints(HUD_KB_ONLY)["passed"]


# ---- ratchet ----

def test_required_verbs_cover_all_deck_actions():
    for v in ("Interact", "NavLeft", "NavRight", "Confirm", "ClosePanel"):
        assert v in REQUIRED_VERBS
    assert KEYBOARD_HINT_TOKENS and GAMEPAD_HINT_TOKENS
