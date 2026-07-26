from __future__ import annotations

import sys
from pathlib import Path


DIMWIT = Path(__file__).resolve().parents[2]  # this repo's root (the scripts live here)
SCRIPT = DIMWIT / "scripts/ue/ue_runtime_material_usage_repair.py"
ACTIVE_RIG_REPAIR = DIMWIT / "scripts/ue/ue_active_rig_material_repair.py"
UE_PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
MATERIAL_AUTHOR = UE_PROJECT / "Plugins" / "WanefallPrototypeProof" / "Source" / "WanefallPrototypeProofEditor" / "Private" / "WanefallMaterialAuthorCommandlet.cpp"
PROTOTYPE_CHARACTER = UE_PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"


def test_runtime_material_usage_repair_covers_live_default_material_warnings():
    assert SCRIPT.exists(), f"missing runtime material usage repair script: {SCRIPT}"
    source = SCRIPT.read_text(encoding="utf-8")

    for material in [
        "/Game/Wanefall/Materials/M_WaneStructure",
        "/Game/Wanefall/Materials/M_WaneVisorSubtle",
        "/Game/Wanefall/Materials/M_WaneSoldierSuit",
        "/Game/Wanefall/Materials/M_WaneSpecies_Kharvex",
    ]:
        assert material in source

    assert "used_with_nanite" in source
    assert "used_with_skeletal_mesh" in source
    assert "runtime_material_usage_repair_result.json" in source


def test_runtime_character_uses_readable_silver_teal_material_lane():
    assert MATERIAL_AUTHOR.exists(), f"missing material author commandlet: {MATERIAL_AUTHOR}"
    assert PROTOTYPE_CHARACTER.exists(), f"missing runtime character source: {PROTOTYPE_CHARACTER}"
    usage_source = SCRIPT.read_text(encoding="utf-8")
    author_source = MATERIAL_AUTHOR.read_text(encoding="utf-8")
    character_source = PROTOTYPE_CHARACTER.read_text(encoding="utf-8")

    for material in [
        "M_WaneZythan_SourceReadable",
        "M_WaneSoldierSuit_Readable",
        "M_WaneSilverTealArmor",
        "M_WaneVisorProof",
    ]:
        assert material in usage_source, f"{material} missing from usage repair script"
        assert material in author_source, f"{material} missing from material authoring commandlet"
        assert material in character_source, f"{material} missing from live prototype character path"

    assert "M_WaneSoldierSuit_Readable.M_WaneSoldierSuit_Readable" in character_source
    assert "M_WaneZythan_SourceReadable.M_WaneZythan_SourceReadable" in character_source
    assert "M_WaneSilverTealArmor.M_WaneSilverTealArmor" in character_source
    assert "M_WaneVisorProof.M_WaneVisorProof" in character_source


def test_match_runtime_prefers_active_roster_rigged_character_over_flat_mannequin():
    assert PROTOTYPE_CHARACTER.exists(), f"missing runtime character source: {PROTOTYPE_CHARACTER}"
    character_source = PROTOTYPE_CHARACTER.read_text(encoding="utf-8")

    assert "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig" in character_source
    active_branch = character_source.split("if (bUsingActiveRosterCharacterMesh)", 1)[1].split("UMaterialInterface* Suit =", 1)[0]
    assert "M_WaneZythan_SourceReadable.M_WaneZythan_SourceReadable" in active_branch
    assert "M_WaneSoldierSuit_Readable.M_WaneSoldierSuit_Readable" in active_branch
    assert active_branch.index("M_WaneZythan_SourceReadable.M_WaneZythan_SourceReadable") < active_branch.index("M_WaneSoldierSuit_Readable.M_WaneSoldierSuit_Readable")
    assert active_branch.index("M_WaneSoldierSuit_Readable.M_WaneSoldierSuit_Readable") < active_branch.index("zythan_mat.zythan_mat")
    assert "vorlax_mat" not in character_source.lower()
    assert "M_WaneVorlax_SourceReadable" not in character_source
    assert "bUsingActiveRosterCharacterMesh" in character_source
    assert "ActiveRosterRiggedFinder.Succeeded() ? ActiveRosterRiggedFinder.Object" in character_source


def test_active_rig_material_repair_authors_silver_readable_base_factor():
    assert ACTIVE_RIG_REPAIR.exists(), f"missing active rig material repair script: {ACTIVE_RIG_REPAIR}"
    source = ACTIVE_RIG_REPAIR.read_text(encoding="utf-8")

    assert "SM_Char_03_zythan/Textures/Image_0" in source
    assert "/Game/Wanefall/Dimwit/CharactersRigged/zythan_mat" in source
    assert "unreal.LinearColor(4.0, 4.4, 4.8, 1.0)" in source
    assert "EmissiveStrength\": 0.45" in source
    assert "unreal.LinearColor(0.09, 0.11, 0.13, 1.0)" not in source


def test_material_author_refreshes_existing_readable_character_materials():
    assert MATERIAL_AUTHOR.exists(), f"missing material author commandlet: {MATERIAL_AUTHOR}"
    source = MATERIAL_AUTHOR.read_text(encoding="utf-8")

    assert "ShouldRefreshExistingMaterial" in source
    assert "DeleteAllMaterialExpressions" in source
    assert "CreateSourceReadableMaterial" in source
    assert "M_WaneZythan_SourceReadable" in source
    assert "SM_Char_03_zythan/Textures/Image_0" in source
    assert "M_WaneSoldierSuit_Readable" in source
    assert "FLinearColor(0.420f, 0.470f, 0.520f)" in source
    assert "FLinearColor(0.030f, 0.520f, 0.680f)" in source


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
