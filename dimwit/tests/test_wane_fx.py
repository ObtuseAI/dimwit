"""FIRSTPARTY_WANE_FX_V1 + NIAGARA_COOK_SAFETY_GATE (bundle 5) — RED-first contract tests.

Law 5 as code: cooked-only Niagara failures (decal / component renderers) become a static
binary-scan gate over every gameplay-referenced NS asset, with the two REAL known-bad systems
on disk serving as permanent golden negatives — a weakened scanner fails its own golden. The
first-party combat surfaces (muzzle / impact / kill-confirm) and their runtime WANE tint are
checked as source contracts; packaged spawn markers prove the systems ran inside the package.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from dimwit.pipelines.wane_fx import (
    COMPONENT_MARKER,
    DECAL_MARKER,
    FIRST_PARTY_FX,
    KNOWN_BAD_SYSTEMS,
    PROJECT,
    check_packaged_wane_fx_markers,
    check_runtime_tint,
    discover_gameplay_niagara_refs,
    game_path_to_content_file,
    parse_combat_fx_surfaces,
    scan_niagara_asset,
    write_cook_safety_report,
)

TMP = Path(tempfile.mkdtemp(prefix="dimwit_wane_fx_"))
EXAMPLES = PROJECT / "Content" / "NiagaraExamples"


# ------------------------------------------------------- binary scanner vs REAL assets on disk

def test_scanner_flags_known_decal_crash_system():
    result = scan_niagara_asset(EXAMPLES / "FX_Player" / "NS_Player_Electricity_Looping.uasset")
    assert result["exists"] is True
    assert result["decal_markers"] > 0
    assert result["cook_safe"] is False


def test_scanner_flags_known_component_renderer_system():
    result = scan_niagara_asset(EXAMPLES / "FX_Misc" / "NS_Fire.uasset")
    assert result["exists"] is True
    assert result["component_markers"] > 0
    assert result["cook_safe"] is False


def test_scanner_passes_cook_clean_donors():
    for rel in ("FX_Weapons/MuzzleFlashes/NS_MuzzleFlash.uasset",
                "FX_Misc/NS_HitDissolve.uasset",
                "FX_PickUp/NS_Pickup_Success.uasset"):
        result = scan_niagara_asset(EXAMPLES / Path(rel))
        assert result["exists"] is True, rel
        assert result["cook_safe"] is True, f"{rel}: {result}"
        assert result["emitter_handles"] >= 1, rel


def test_scanner_reports_stateless_emitters_the_cooked_boot_killer():
    """Duplicated-stateless law: NS_Wane_Death duplicated from NS_Pickup_Success (3 stateless
    emitters) asserted at cooked BOOT (UNiagaraStatelessEmitter::Serialize) and killed the whole
    package. The scanner must surface the marker; first-party FX must be stateless-free."""
    pickup = scan_niagara_asset(EXAMPLES / "FX_PickUp" / "NS_Pickup_Success.uasset")
    assert pickup["stateless_markers"] > 0
    firework = scan_niagara_asset(EXAMPLES / "FX_Misc" / "NS_FireworkBurst.uasset")
    assert firework["stateless_markers"] == 0 and firework["cook_safe"] is True

    report = write_cook_safety_report(result_path=TMP / "stateless" / "report.json")
    for entry in report["referenced"]:
        if entry.get("first_party"):
            assert entry["scan"]["stateless_markers"] == 0, \
                f"first-party FX with stateless emitters must not pass: {entry['game_path']}"
            assert entry["cook_safe"] is True, entry["game_path"]


def test_scanner_fails_closed_on_missing_asset():
    result = scan_niagara_asset(TMP / "NS_DoesNotExist.uasset")
    assert result["exists"] is False
    assert result["cook_safe"] is False


# ------------------------------------------------------- gameplay reference discovery

def test_discover_finds_niagara_finders_and_ignores_other_types():
    src = TMP / "src_a"
    src.mkdir(parents=True, exist_ok=True)
    (src / "Weapon.cpp").write_text(
        'static ConstructorHelpers::FObjectFinder<UNiagaraSystem> MuzzleFinder(TEXT("/Game/A/NS_One.NS_One"));\n'
        'static ConstructorHelpers::FObjectFinder<UStaticMesh> MeshFinder(TEXT("/Game/A/SM_Two.SM_Two"));\n'
        'static ConstructorHelpers::FObjectFinder<UNiagaraSystem> TrailFinder(TEXT("/Game/B/NS_Three.NS_Three"));\n',
        encoding="utf-8")
    refs = discover_gameplay_niagara_refs(src)
    paths = sorted(ref["game_path"] for ref in refs)
    assert paths == ["/Game/A/NS_One.NS_One", "/Game/B/NS_Three.NS_Three"]
    assert all(ref["file"].endswith("Weapon.cpp") for ref in refs)


def test_game_path_maps_to_content_uasset():
    mapped = game_path_to_content_file("/Game/NiagaraExamples/FX_Misc/NS_Fire.NS_Fire", PROJECT)
    assert mapped == PROJECT / "Content" / "NiagaraExamples" / "FX_Misc" / "NS_Fire.uasset"


def test_real_project_gameplay_refs_all_resolve_and_scan():
    refs = discover_gameplay_niagara_refs(PROJECT / "Source" / "WanefallGreybox")
    assert len(refs) >= 4, f"expected the known gameplay NS references, got {refs}"
    for ref in refs:
        mapped = game_path_to_content_file(ref["game_path"], PROJECT)
        assert mapped.exists(), f"dangling gameplay NS reference: {ref}"


# ------------------------------------------------------- cook-safety report (fail-closed truth)

def test_cook_safety_report_flags_known_bad_and_writes_artifact():
    out = TMP / "artifacts" / "wane_fx" / "niagara_cook_safety.json"
    report = write_cook_safety_report(result_path=out)
    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 1
    golden = {entry["game_path"]: entry for entry in report["known_bad_golden"]}
    assert set(golden) == set(KNOWN_BAD_SYSTEMS)
    assert all(entry["flagged"] for entry in golden.values()), \
        "scanner failed its golden negatives — a weakened scanner must not pass"
    assert report["referenced"], "no gameplay references discovered"
    assert isinstance(report["all_referenced_cook_safe"], bool)


# ------------------------------------------------------- combat surface + tint source contracts

GOOD_RIFLE = '''
static ConstructorHelpers::FObjectFinder<UNiagaraSystem> MuzzleFinder(TEXT("/Game/Wanefall/Dimwit/VFX/NS_Wane_Snap.NS_Wane_Snap"));
static ConstructorHelpers::FObjectFinder<UNiagaraSystem> ImpactFinder(TEXT("/Game/Wanefall/Dimwit/VFX/NS_Wane_Hit.NS_Wane_Hit"));
UNiagaraComponent* MuzzleComp = UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, MuzzleFX, MuzzleLocation);
WanefallApplyWaneTint(MuzzleComp, WanefallWaneFx::SnapColor, { TEXT("Flash Base Color"), TEXT("Smoke Color") });
UNiagaraComponent* ImpactComp = UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, ImpactFX, EndPoint);
WanefallApplyWaneTint(ImpactComp, WanefallWaneFx::HitColor, { TEXT("Spark Color Gain") });
'''

GOOD_GAMESTATE = '''
static ConstructorHelpers::FObjectFinder<UNiagaraSystem> KillConfirmFinder(TEXT("/Game/Wanefall/Dimwit/VFX/NS_Wane_Death.NS_Wane_Death"));
UNiagaraComponent* KillComp = UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, KillConfirmFX, Victim->GetActorLocation());
WanefallApplyWaneTint(KillComp, WanefallWaneFx::DeathColor, { TEXT("Color"), TEXT("Color Secondary") });
'''


def test_parse_combat_surfaces_accepts_first_party_wiring():
    surfaces = parse_combat_fx_surfaces(GOOD_RIFLE, GOOD_GAMESTATE)
    assert surfaces["muzzle"].endswith("NS_Wane_Snap.NS_Wane_Snap")
    assert surfaces["impact"].endswith("NS_Wane_Hit.NS_Wane_Hit")
    assert surfaces["kill_confirm"].endswith("NS_Wane_Death.NS_Wane_Death")
    assert surfaces["issues"] == []


def test_parse_combat_surfaces_rejects_example_pack_and_shared_impact():
    stale = GOOD_RIFLE.replace(
        "/Game/Wanefall/Dimwit/VFX/NS_Wane_Hit.NS_Wane_Hit",
        "/Game/Wanefall/Dimwit/VFX/NS_Wane_Snap.NS_Wane_Snap")
    surfaces = parse_combat_fx_surfaces(stale, GOOD_GAMESTATE)
    assert any("impact" in issue and "muzzle" in issue for issue in surfaces["issues"]), \
        "impact reusing the muzzle system must be an issue"

    example = GOOD_RIFLE.replace(
        "/Game/Wanefall/Dimwit/VFX/NS_Wane_Snap.NS_Wane_Snap",
        "/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash.NS_MuzzleFlash")
    surfaces = parse_combat_fx_surfaces(example, GOOD_GAMESTATE)
    assert any("first-party" in issue for issue in surfaces["issues"]), \
        "example-pack muzzle must be an issue"

    surfaces = parse_combat_fx_surfaces(GOOD_RIFLE, "// no kill fx here")
    assert any("kill_confirm" in issue for issue in surfaces["issues"])


def test_runtime_tint_check_requires_tint_on_all_three_paths():
    tint = check_runtime_tint(GOOD_RIFLE, GOOD_GAMESTATE)
    assert tint["passed"] is True, tint

    untinted_rifle = GOOD_RIFLE.replace("WanefallApplyWaneTint", "// WanefallApplyWaneTint")
    tint = check_runtime_tint(untinted_rifle, GOOD_GAMESTATE)
    assert tint["passed"] is False

    tint = check_runtime_tint(GOOD_RIFLE, "// spawn without tint")
    assert tint["passed"] is False


# ------------------------------------------------------- packaged spawn-marker evidence

def test_packaged_markers_require_all_three_surfaces():
    log = ("[WaneFX] muzzle spawn #1\n[WaneFX] impact spawn #1\n"
           "[WaneFX] kill_confirm spawn #1\nLogTemp: other noise\n")
    result = check_packaged_wane_fx_markers(log)
    assert result["passed"] is True
    assert result["muzzle"] and result["impact"] and result["kill_confirm"]

    result = check_packaged_wane_fx_markers("[WaneFX] muzzle spawn #1\n")
    assert result["passed"] is False
    assert any("impact" in issue for issue in result["issues"])

    result = check_packaged_wane_fx_markers("")
    assert result["passed"] is False


# ------------------------------------------------------- registration

def test_validation_registry_contains_wane_fx_gates_all_blockers():
    from dimwit.pipelines.validation import Severity
    from dimwit.pipelines.validation_registry import REGISTRY

    gates = {v.id: v for v in REGISTRY if v.domain == "wane_fx"}
    expected = {
        "niagara_cook_safety_referenced_clean",
        "niagara_cook_safety_catches_known_bad",
        "wane_fx_first_party_combat_surfaces",
        "wane_fx_runtime_tint_wired",
        "wane_fx_spawned_in_packaged_match",
    }
    assert expected.issubset(set(gates)), f"missing: {expected - set(gates)}"
    for name in expected:
        assert gates[name].severity == Severity.BLOCKER, f"{name} must be a BLOCKER"


def test_vfx_qa_rejects_wrong_donor_duplicate():
    """Wrong-asset law: the 2026-07-02 registry-scan race silently substituted fallback donor #1
    for an explicit source and QA rubber-stamped it. QA must now hard-fail a donor mismatch."""
    from dimwit.pipelines.base import Artifact
    from dimwit.pipelines.vfx import VFXPipeline

    pipeline = VFXPipeline()
    record = {"asset_exists": True, "emitter_count": 1, "color_set": True,
              "verb_param_set": True, "saved": True,
              "source_used": "/Game/NiagaraExamples/FX_Misc/NS_HitDissolve"}
    artifact = Artifact(asset_id="death", kind="niagara_vfx", data=record, provenance={})
    plan = {"source": "/Game/NiagaraExamples/FX_PickUp/NS_Pickup_Success.NS_Pickup_Success"}
    verdict = pipeline.qa(artifact, plan)
    assert verdict.passed is False
    assert "source_matches_request" in verdict.issues

    plan_ok = {"source": "/Game/NiagaraExamples/FX_Misc/NS_HitDissolve.NS_HitDissolve"}
    assert pipeline.qa(artifact, plan_ok).passed is True


def test_first_party_fx_constants_are_wane_namespace():
    for surface, game_path in FIRST_PARTY_FX.items():
        assert game_path.startswith("/Game/Wanefall/Dimwit/VFX/NS_Wane_"), (surface, game_path)
    assert DECAL_MARKER == b"NiagaraDecalRendererProperties"
    assert COMPONENT_MARKER == b"NiagaraComponentRendererProperties"


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
