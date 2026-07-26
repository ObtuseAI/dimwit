from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


TMP = Path(tempfile.mkdtemp(prefix="dimwit_character_roster_policy_"))
UNREAL = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
CHARACTER_REGISTRY_CPP = UNREAL / "Source/WanefallGreybox/Private/WanefallCharacterRegistry.cpp"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fixture_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="dimwit_character_roster_policy_case_")) / "dimwit"
    _write_json(root / "config" / "character_roster.json", {
        "schema_version": 1,
        "active_humanoid_target": 6,
        "active_mech_target": 8,
        "quarantined_humanoids": {
            "bad_runtime_01": {
                "state": "QUARANTINED_OPERATOR_REJECTED_RUNTIME_DEFECT",
                "asset_name": "SM_Char_01_Vorlax",
                "asset_id": "SM_Char_01_vorlax",
                "reason": "operator rejected active runtime character after hand deformation and abnormal posture",
                "replacement_required": False,
                "capacity_rebalanced_to_mechs": True,
                "evidence": ["artifacts/validation/character_deformation_review_vorlax.json"],
            },
            "retired_prototype_02": {
                "state": "QUARANTINED_RETIRED_PROTOTYPE",
                "asset_name": "SM_Char_02_ekris",
                "reason": "operator retired this prototype after right-arm/runtime deformation failure",
                "replacement_required": False,
                "capacity_rebalanced_to_mechs": True,
                "evidence": ["artifacts/validation/character_deformation_review.json"],
            }
        },
        "mech_characters": [
            {"character_id": "mech_01_glaciera", "asset_name": "SM_Char_Mech_01_Glaciera", "active": True},
            {"character_id": "mech_02_voidrunner", "asset_name": "SM_Char_Mech_02_Voidrunner", "active": True},
            {"character_id": "mech_03_aurelion", "asset_name": "SM_Char_Mech_03_Aurelion", "active": True},
            {"character_id": "mech_04_luxorion", "asset_name": "SM_Char_Mech_04_Luxorion", "active": True},
            {"character_id": "mech_05_pyroclast", "asset_name": "SM_Char_Mech_05_Pyroclast", "active": True},
            {"character_id": "mech_06_jadewind", "asset_name": "SM_Char_Mech_06_Jadewind", "active": True},
            {"character_id": "mech_07_ironline", "asset_name": "SM_Char_Mech_07_Ironline", "active": True},
            {"character_id": "mech_08_nightwire", "asset_name": "SM_Char_Mech_08_Nightwire", "active": True},
        ],
        "next_lane": "environments_maps_assets",
    })
    return root


def test_roster_policy_excludes_retired_prototype_and_counts_mechs():
    from dimwit.pipelines.character_roster import (
        active_humanoid_characters,
        active_humanoid_names,
        active_mech_characters,
        is_quarantined_character,
        roster_policy_summary,
    )

    root = _fixture_root()

    active_humans = active_humanoid_characters(root)
    active_names = active_humanoid_names(root)
    active_mechs = active_mech_characters(root)
    summary = roster_policy_summary(root)

    assert len(active_humans) == 6
    assert "SM_Char_01_Vorlax" not in active_names
    assert "SM_Char_02_ekris" not in active_names
    assert is_quarantined_character("SM_Char_01_Vorlax", root)
    assert is_quarantined_character("retired_prototype_02", root)
    assert is_quarantined_character("SM_Char_02_ekris", root)
    assert len(active_mechs) == 8
    assert summary["active_humanoid_count"] == 6
    assert summary["active_mech_count"] == 8
    assert summary["quarantined_humanoid_count"] == 2
    assert summary["quarantined_humanoids"] == ["bad_runtime_01", "retired_prototype_02"]
    assert summary["next_lane"] == "environments_maps_assets"


def test_roster_policy_gate_requires_no_quarantined_director_tasks():
    from dimwit.pipelines.character_roster_policy import audit_character_roster_policy, validate_character_roster_policy

    root = _fixture_root()
    project = TMP / "wanefall"
    _write_json(root / "config" / "director_tasks.json", {
        "tasks": [
            {"pipeline": "character_source_sync", "asset_id": "active"},
            {"pipeline": "rigging", "asset_id": "SM_Char_01_Vorlax"},
        ]
    })

    report = audit_character_roster_policy(root, project)
    verdict = validate_character_roster_policy(report)

    assert verdict["passed"] is False, verdict
    assert any("quarantined character task" in issue for issue in verdict["issues"]), verdict


def test_roster_policy_report_redacts_retired_display_name():
    from dimwit.pipelines.character_roster_policy import audit_character_roster_policy

    root = _fixture_root()
    project = TMP / "wanefall"

    report = audit_character_roster_policy(root, project)
    text = json.dumps(report).lower()

    assert "retired_prototype_02" in text
    assert "ekris" not in text
    assert "bad_runtime_01" in text
    assert "vorlax" not in text


def test_unreal_runtime_registry_excludes_quarantined_humanoid_from_visible_roster():
    source = CHARACTER_REGISTRY_CPP.read_text(encoding="utf-8")

    active_soldiers = [
        "SM_Char_03_zythan",
        "SM_Char_04_qorin",
        "SM_Char_05_therak",
        "SM_Char_06_ullio",
        "SM_Char_07_kelous",
        "SM_Char_08_nexor",
    ]
    active_mechs = [
        "SM_Char_Mech_01_Glaciera",
        "SM_Char_Mech_02_Voidrunner",
        "SM_Char_Mech_03_Aurelion",
        "SM_Char_Mech_04_Luxorion",
        "SM_Char_Mech_05_Pyroclast",
        "SM_Char_Mech_06_Jadewind",
        "SM_Char_Mech_07_Ironline",
        "SM_Char_Mech_08_Nightwire",
    ]

    for asset in active_soldiers + active_mechs:
        assert asset in source

    assert "SM_Char_01_" not in source
    assert "SM_Char_02_" not in source
    assert source.count("{ TEXT(\"SM_Char_") == 14


def test_runtime_sources_do_not_reference_quarantined_character_rigs():
    unreal = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
    sources = [
        unreal / "Source/WanefallGreybox/Private/WanefallPrototypeCharacter.cpp",
        unreal / "Source/WanefallGreybox/Private/WanefallLobbyCharacter.cpp",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert "SM_Char_01_vorlax_Rig" not in combined
    assert "SM_Char_02_ekris_Rig" not in combined
    assert "vorlax_mat" not in combined
    assert "ekris_mat" not in combined
    assert "SM_Char_03_zythan_Rig" in combined


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
