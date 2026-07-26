from pathlib import Path


UNREAL = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
CONTROLLER_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallLobbyPlayerController.cpp"
MATCH_GAMEMODE_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallMatchGameMode.cpp"
MATCH_DIRECTOR_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallMatchDirector.cpp"
COMBAT_EVENT_LOG_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallCombatEventLog.cpp"
HEALTH_H = UNREAL / "Source/WanefallGreybox/Public/WanefallPrototypeHealthComponent.h"
HEALTH_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallPrototypeHealthComponent.cpp"
MAPS = UNREAL / "Content/Wanefall/Maps"


def _read(path: Path) -> str:
    assert path.exists(), f"missing source file: {path}"
    return path.read_text(encoding="utf-8")


def test_frontdoor_deploy_routes_to_spawn_safe_match_map():
    source = _read(CONTROLLER_CPP)
    assert "Wanefall_KitArena_01" not in source
    assert "Wanefall_Arena4v4_Prototype_01" in source
    assert (MAPS / "Wanefall_Arena4v4_Prototype_01.umap").exists()


def test_match_gamemode_documents_spawn_collision_root_cause():
    source = _read(MATCH_GAMEMODE_CPP)
    assert "front-door deploy collision guard" in source
    assert "AdjustIfPossibleButAlwaysSpawn" in source


def test_match_director_reapplies_round_state_after_roster_refresh():
    source = _read(MATCH_DIRECTOR_CPP)
    assert "InArena->SynchronizeBotRosterForCurrentRound();" in source


def test_frontdoor_match_hud_uses_display_names_not_raw_actor_ids():
    source = _read(COMBAT_EVENT_LOG_CPP)
    assert "DisplayActorName" in source
    assert "SourceDisplay" in source
    assert "TargetDisplay" in source
    assert "*Event.SourceActor, *Event.TargetActor" not in source
    assert "hit %s" in source
    assert "downed %s" in source


def test_frontdoor_match_grants_short_local_player_spawn_grace():
    game_mode = _read(MATCH_GAMEMODE_CPP)
    health_h = _read(HEALTH_H)
    health_cpp = _read(HEALTH_CPP)
    spawn_block = game_mode.split("void AWanefallMatchGameMode::BeginPlay", 1)[0]
    assert "GrantDamageImmunity" in health_h
    assert "DamageImmunityUntilWorldTime" in health_cpp
    assert "GrantDamageImmunity(10.0f)" in game_mode
    assert "GrantDamageImmunity(10.0f)" in spawn_block


def test_validation_registry_contains_frontdoor_spawn_safe_gate():
    from dimwit.pipelines.validation_registry import REGISTRY

    validators = {v.id: v for v in REGISTRY}
    assert "frontdoor_deploy_spawn_safe" in validators
    gate = validators["frontdoor_deploy_spawn_safe"]
    assert gate.domain == "environment_maps"
    assert gate.severity.value == "blocker"
    assert "frontdoor_live_deploy_proof" in validators
    live_gate = validators["frontdoor_live_deploy_proof"]
    assert live_gate.domain == "environment_maps"
    assert live_gate.severity.value == "blocker"


def main() -> int:
    tests = [
        test_frontdoor_deploy_routes_to_spawn_safe_match_map,
        test_match_gamemode_documents_spawn_collision_root_cause,
        test_match_director_reapplies_round_state_after_roster_refresh,
        test_frontdoor_match_hud_uses_display_names_not_raw_actor_ids,
        test_frontdoor_match_grants_short_local_player_spawn_grace,
        test_validation_registry_contains_frontdoor_spawn_safe_gate,
    ]
    for test in tests:
        test()
    print(f"frontdoor_playable_contract: {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
