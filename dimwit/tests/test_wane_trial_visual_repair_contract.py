from __future__ import annotations

import json
import re
import sys
from pathlib import Path


DIMWIT = Path(r"C:\Users\developer\Documents\Dimwit")
UNREAL_PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
STATIC_MESH_DUMP = DIMWIT / "artifacts" / "real_game_validation" / "wane_trial_static_mesh_dump.json"
V4_BUILDER = (
    UNREAL_PROJECT
    / "Plugins"
    / "WanefallPrototypeProof"
    / "Source"
    / "WanefallPrototypeProofEditor"
    / "Private"
    / "WanefallWaneTrialV4JailCellBuildCommandlet.cpp"
)
SLICE_EVO = (
    UNREAL_PROJECT
    / "Plugins"
    / "WanefallPrototypeProof"
    / "Source"
    / "WanefallPrototypeProofEditor"
    / "Private"
    / "WanefallSliceEvolutionEnvCommandlet.cpp"
)

PLACEHOLDER_LABEL = re.compile(r"^(Cover(?:Low|Med|Tall|Central)|EvoCover_|EvoGate(?:Pillar|Lintel))")
FLAT_GRAY_MATERIALS = {
    "/Game/Wanefall/Dimwit/MapKit/M_KitLit.M_KitLit",
}


def test_current_wane_trial_dump_has_no_basicshape_cover_or_gate_slabs():
    assert STATIC_MESH_DUMP.exists(), f"static mesh dump missing: {STATIC_MESH_DUMP}"
    data = json.loads(STATIC_MESH_DUMP.read_text(encoding="utf-8"))
    offenders = [
        actor["label"]
        for actor in data.get("actors", [])
        if PLACEHOLDER_LABEL.search(str(actor.get("label") or ""))
        and str(actor.get("mesh") or "") == "/Engine/BasicShapes/Cube.Cube"
    ]
    assert not offenders, "placeholder cube slabs remain in Wane Trial map: " + ", ".join(offenders[:20])


def test_current_wane_trial_cover_meshes_do_not_use_flat_gray_mapkit_material():
    assert STATIC_MESH_DUMP.exists(), f"static mesh dump missing: {STATIC_MESH_DUMP}"
    data = json.loads(STATIC_MESH_DUMP.read_text(encoding="utf-8"))
    offenders = [
        actor["label"]
        for actor in data.get("actors", [])
        if PLACEHOLDER_LABEL.search(str(actor.get("label") or ""))
        and any(material in FLAT_GRAY_MATERIALS for material in actor.get("materials", []))
    ]
    assert not offenders, "flat gray MapKit material remains on Wane Trial cover/gate actors: " + ", ".join(offenders[:20])


def test_wane_trial_v4_builder_uses_mapkit_cover_meshes():
    text = V4_BUILDER.read_text(encoding="utf-8")
    assert "SM_Kit_Cover/StaticMeshes/SM_Kit_Cover.SM_Kit_Cover" in text
    assert "SM_Kit_Pillar/StaticMeshes/SM_Kit_Pillar.SM_Kit_Pillar" in text
    assert "M_WaneEnemyTealAccent.M_WaneEnemyTealAccent" in text
    assert "CoverMesh ? CoverMesh : Cube" in text
    assert "PillarMesh ? PillarMesh : Cube" in text
    assert "CoverMesh ? nullptr" not in text
    assert "PillarMesh ? nullptr" not in text


def test_slice_evolution_env_uses_mapkit_cover_meshes():
    text = SLICE_EVO.read_text(encoding="utf-8")
    assert "SM_Kit_Cover/StaticMeshes/SM_Kit_Cover.SM_Kit_Cover" in text
    assert "SM_Kit_Crate/StaticMeshes/SM_Kit_Crate.SM_Kit_Crate" in text
    assert "M_WaneEnemyTealAccent.M_WaneEnemyTealAccent" in text
    assert "SpawnStaticMesh(W, CoverMesh" in text
    assert "SpawnStaticMesh(W, CrateMesh" in text
    assert "SpawnStaticMesh(W, CoverMesh, nullptr" not in text
    assert "SpawnStaticMesh(W, CrateMesh, nullptr" not in text
    assert "SpawnStaticMesh(W, PillarMesh, nullptr" not in text


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
