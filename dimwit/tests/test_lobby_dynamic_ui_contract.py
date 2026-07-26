from pathlib import Path


UNREAL = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
HUD_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallLobbyHUD.cpp"
STATION_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallLobbyStation.cpp"
CONTROLLER_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallLobbyPlayerController.cpp"
CONTROLLER_H = UNREAL / "Source/WanefallGreybox/Public/WanefallLobbyPlayerController.h"
LOBBY_GAMEMODE_H = UNREAL / "Source/WanefallGreybox/Public/WanefallLobbyGameMode.h"
LOBBY_HUD_H = UNREAL / "Source/WanefallGreybox/Public/WanefallLobbyHUD.h"
LOBBY_STATION_H = UNREAL / "Source/WanefallGreybox/Public/WanefallLobbyStation.h"
MATCH_HUD_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallMatchHUD.cpp"
MATCH_CONTROLLER_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallMatchPlayerController.cpp"
MATCH_CONTROLLER_H = UNREAL / "Source/WanefallGreybox/Public/WanefallMatchPlayerController.h"
PLAY_BAT = UNREAL / "HumanTestLaunch/WANEFALL_PLAY.bat"
LOBBY_BAT = UNREAL / "HumanTestLaunch/WANEFALL_LOBBY.bat"
REMOVED_HOLD_FILES = [
    UNREAL / "HumanTestLaunch/WANEFALL_HOLD.bat",
    UNREAL / "Source/WanefallGreybox/Private/WanefallHoldGameMode.cpp",
    UNREAL / "Source/WanefallGreybox/Private/WanefallHoldHUD.cpp",
    UNREAL / "Source/WanefallGreybox/Private/WanefallHoldPawn.cpp",
    UNREAL / "Source/WanefallGreybox/Public/WanefallHoldGameMode.h",
    UNREAL / "Source/WanefallGreybox/Public/WanefallHoldHUD.h",
    UNREAL / "Source/WanefallGreybox/Public/WanefallHoldPawn.h",
]


def _read(path: Path) -> str:
    assert path.exists(), f"missing source file: {path}"
    return path.read_text(encoding="utf-8")


def test_lobby_hud_is_standalone_command_surface_not_inherited_combat_hud():
    source = _read(HUD_CPP)
    assert "Super::DrawHUD();" not in source
    assert "DrawRect(FLinearColor(0.005f, 0.012f, 0.016f, 1.0f), 0.0f, 0.0f, W, H)" in source
    assert "WANEFALL COMMAND" in source
    assert "QUICK DEPLOY" in source
    assert "MODE INTEL" in source
    assert "RANK / BOARDS" in source
    assert "SOCIAL" in source
    assert "STATS" in source
    assert "SETTINGS" in source
    assert "WANE TRIAL" not in source
    assert "OBJECTIVE:" not in source
    assert "THE HOLD" not in source
    assert "all-in-one lobby UI" not in source
    assert "station meshes" not in source
    assert "player-facing lobby" not in source
    assert "nearby anchor" not in source


def test_lobby_command_surface_avoids_flat_gray_panel_fills():
    source = _read(HUD_CPP)
    assert "DrawRect(FLinearColor(0.005f, 0.012f, 0.016f, 0.62f)" not in source
    assert "Panel(CenterX, BodyY, CenterW, BodyH, Violet, 0.72f)" not in source
    assert "FLinearColor(0.006f, 0.085f, 0.115f, 0.78f)" not in source
    assert "FLinearColor(0.018f, 0.026f, 0.032f" not in source
    assert "FLinearColor(0.03f, 0.045f, 0.055f" not in source
    assert "FLinearColor(0.028f, 0.038f, 0.044f" not in source
    assert "FLinearColor(0.08f, 0.10f, 0.11f" not in source
    assert "0.085f, 0.115f" in source


def test_lobby_station_meshes_are_invisible_ui_anchors_not_gray_world_blocks():
    source = _read(STATION_CPP)
    assert "Console->SetCollisionEnabled(ECollisionEnabled::NoCollision)" in source
    assert "Console->SetVisibility(false)" in source
    assert "Console->SetHiddenInGame(true)" in source
    assert "BlockAllDynamic" not in source


def test_lobby_controller_opens_as_all_in_one_command_surface():
    source = _read(CONTROLLER_CPP)
    assert "ActivePanel = EWanefallStation::ModeSelect;" in source
    assert "bPanelOpen = true;" in source
    assert "if (!bPanelOpen) { return; }" not in source
    assert "if (bIsPartyLeader) { DoDeploy(); }" in source


def test_active_routes_return_to_command_not_hold():
    combined = "\n".join(
        _read(path)
        for path in [
            MATCH_HUD_CPP,
            MATCH_CONTROLLER_CPP,
            MATCH_CONTROLLER_H,
            PLAY_BAT,
            LOBBY_BAT,
        ]
    )
    assert "RETURN TO THE HOLD" not in combined
    assert "ReturnToHold" not in combined
    assert "Wanefall_TheHold_01" not in combined
    assert "Wanefall_Lobby" not in combined
    assert "WanefallHoldGameMode" not in combined
    assert "boots the Hold" not in combined
    assert "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01?game=/Script/WanefallGreybox.WanefallLobbyGameMode" in combined


def test_command_surface_comments_do_not_keep_hold_ux_as_the_design():
    combined = "\n".join(
        _read(path)
        for path in [
            CONTROLLER_H,
            LOBBY_GAMEMODE_H,
            LOBBY_HUD_H,
            LOBBY_STATION_H,
        ]
    )
    assert "THE HOLD" not in combined
    assert "SoulCave HOLD" not in combined
    assert "walk up to a station" not in combined
    assert "walk-up" not in combined


def test_obsolete_hold_frontend_source_and_launcher_are_removed():
    existing = [str(path) for path in REMOVED_HOLD_FILES if path.exists()]
    assert not existing, f"obsolete Hold frontend files still present: {existing}"


def main() -> int:
    tests = [
        test_lobby_hud_is_standalone_command_surface_not_inherited_combat_hud,
        test_lobby_command_surface_avoids_flat_gray_panel_fills,
        test_lobby_station_meshes_are_invisible_ui_anchors_not_gray_world_blocks,
        test_lobby_controller_opens_as_all_in_one_command_surface,
        test_active_routes_return_to_command_not_hold,
        test_command_surface_comments_do_not_keep_hold_ux_as_the_design,
        test_obsolete_hold_frontend_source_and_launcher_are_removed,
    ]
    for test in tests:
        test()
    print(f"lobby_dynamic_ui_contract: {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
