from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
UPROJECT = PROJECT / "WanefallGreybox.uproject"
DEFAULT_ENGINE = PROJECT / "Config" / "DefaultEngine.ini"
PROTOTYPE_PROOF_PLUGIN = PROJECT / "Plugins" / "WanefallPrototypeProof"
PROTOTYPE_PROOF_UPLUGIN = PROTOTYPE_PROOF_PLUGIN / "WanefallPrototypeProof.uplugin"
PROTOTYPE_PROOF_BUILD = (
    PROTOTYPE_PROOF_PLUGIN
    / "Source"
    / "WanefallPrototypeProofEditor"
    / "WanefallPrototypeProofEditor.Build.cs"
)


def _plugin_enabled(name: str) -> bool | None:
    data = json.loads(UPROJECT.read_text(encoding="utf-8"))
    for plugin in data.get("Plugins", []):
        if plugin.get("Name") == name:
            return bool(plugin.get("Enabled"))
    return None


def test_runtime_boot_excludes_broken_all_toolsets_aggregator():
    assert UPROJECT.exists(), f"uproject missing: {UPROJECT}"
    assert _plugin_enabled("AllToolsets") is not True


def test_ai_bridge_and_editor_bridge_plugins_remain_enabled():
    assert _plugin_enabled("ShowMeAIBridge") is True
    assert _plugin_enabled("PythonScriptPlugin") is True
    assert _plugin_enabled("ModelContextProtocol") is True
    assert _plugin_enabled("CodeEditor") is True
    assert _plugin_enabled("CodeView") is True


def test_game_feature_data_primary_asset_rule_is_declared():
    assert DEFAULT_ENGINE.exists(), f"DefaultEngine.ini missing: {DEFAULT_ENGINE}"
    text = DEFAULT_ENGINE.read_text(encoding="utf-8")
    assert "[/Script/Engine.AssetManagerSettings]" in text
    assert 'PrimaryAssetType="GameFeatureData"' in text
    assert "AssetBaseClass=/Script/GameFeatures.GameFeatureData" in text


def test_bare_runtime_defaults_to_command_surface_not_old_trial_map():
    assert DEFAULT_ENGINE.exists(), f"DefaultEngine.ini missing: {DEFAULT_ENGINE}"
    text = DEFAULT_ENGINE.read_text(encoding="utf-8")
    assert "EditorStartupMap=/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01" in text
    assert "GameDefaultMap=/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01" in text
    assert "GlobalDefaultGameMode=/Script/WanefallGreybox.WanefallLobbyGameMode" in text
    assert "GameDefaultMap=/Game/Wanefall/Maps/Wanefall_WaneTrialJailCell_01" not in text


def test_prototype_proof_declares_niagara_plugin_dependency():
    assert PROTOTYPE_PROOF_UPLUGIN.exists(), f"uplugin missing: {PROTOTYPE_PROOF_UPLUGIN}"
    assert PROTOTYPE_PROOF_BUILD.exists(), f"Build.cs missing: {PROTOTYPE_PROOF_BUILD}"
    build_text = PROTOTYPE_PROOF_BUILD.read_text(encoding="utf-8")
    assert '"Niagara"' in build_text

    data = json.loads(PROTOTYPE_PROOF_UPLUGIN.read_text(encoding="utf-8"))
    declared_plugins = {
        plugin.get("Name"): plugin for plugin in data.get("Plugins", []) if isinstance(plugin, dict)
    }
    assert declared_plugins.get("Niagara", {}).get("Enabled") is True


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
