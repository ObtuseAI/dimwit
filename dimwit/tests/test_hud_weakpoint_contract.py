from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT = Path(os.environ.get("WANEFALL_PROJECT", r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox"))
HUD_CPP = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeHUD.cpp"
HUD_H = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallPrototypeHUD.h"
CHARACTER_CPP = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"
CHARACTER_H = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallPrototypeCharacter.h"
TARGET_H = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallPrototypeTargetDummy.h"


def test_match_hud_projects_actual_target_weakpoint_location():
    cpp = HUD_CPP.read_text(encoding="utf-8")
    header = HUD_H.read_text(encoding="utf-8")
    target_header = TARGET_H.read_text(encoding="utf-8")

    assert "FVector GetWeakPointLocation() const" in target_header
    assert "bDrewWeakpointIndicator" in header
    assert "DrawWeakpointIndicator" in header
    assert "WANEFALL_WEAKPOINT_INDICATOR_PROOF" in cpp
    assert "GetWeakPointLocation()" in cpp
    assert "Canvas->Project" in cpp
    assert "LineTraceSingleByChannel" in cpp


def test_lobby_command_surface_replaces_the_hold_station_blocks():
    lobby_hud = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallLobbyHUD.h"
    lobby_controller = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallLobbyPlayerController.h"
    text = (lobby_hud.read_text(encoding="utf-8") + "\n" + lobby_controller.read_text(encoding="utf-8")).lower()

    assert "command surface" in text
    assert "all-in-one front end" in text
    for channel in ("play", "modes", "loadout", "social", "rank", "stats", "settings"):
        assert channel in text
    assert "the hold" not in text


def test_first_person_view_hides_owner_body_and_never_shows_full_body_fp_clone():
    cpp = CHARACTER_CPP.read_text(encoding="utf-8")
    header = CHARACTER_H.read_text(encoding="utf-8")

    assert "ApplyPerspectiveOwnerVisibility" in header
    assert "ApplyPerspectiveOwnerVisibility();" in cpp
    assert "PerspectiveHiddenFromOwner" in cpp
    assert "MeshComp->SetOwnerNoSee(bFirstPerson)" in cpp
    for component in ("ArmorHelmet", "ArmorBlenderKit", "BodyLegRight", "BodyArmRight"):
        assert component in cpp
    assert "FPArmsMesh->SetVisibility(false, true)" in cpp
    assert "FPArmsMesh->SetHiddenInGame(true, true)" in cpp
    assert "FPArmsMesh->SetVisibility(bFirstPerson)" not in cpp


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
