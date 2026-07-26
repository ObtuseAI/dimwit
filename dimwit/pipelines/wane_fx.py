"""FIRSTPARTY_WANE_FX_V1 + NIAGARA_COOK_SAFETY_GATE (masterplan Horizon 1, bundle 5).

Law 5 as code: cooked-only Niagara failures are real — a decal renderer hard-crashed every
packaged match ~25s in (`NS_Player_Electricity_Looping`), and a component renderer failed the
cooker outright (`NS_Fire`). Both remain on disk as PERMANENT golden negatives: the scanner
must flag them every run, so a weakened scanner fails its own golden.

The gate perimeter is auto-discovered: every `FObjectFinder<UNiagaraSystem>(TEXT("/Game/..."))`
in the game module enters the scan — a brand-new FX reference is gated the moment it is written.
Scanning is raw-bytes marker search over the .uasset (the class names of hazardous renderer
properties appear in the asset's name table); proven to discriminate cleanly: the two killers
carry the markers, every currently-wired system and donor does not, and light renderers
(present in known-good systems) are correctly NOT treated as hazards.

First-party combat surfaces (muzzle / impact / kill-confirm) are source contracts: the pulse
rifle and the arena game state must reference `/Game/Wanefall/Dimwit/VFX/NS_Wane_*` systems
(impact may no longer reuse the muzzle system) and apply the WANE verb tint at spawn
(`WanefallApplyWaneTint`). Packaged `[WaneFX]` spawn markers prove the systems actually ran
inside the package during the machine-played match.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
SOURCE_DIR = PROJECT / "Source" / "WanefallGreybox"
RESULT_DIR = ROOT / "artifacts" / "wane_fx"
RESULT_PATH = RESULT_DIR / "niagara_cook_safety.json"

DECAL_MARKER = b"NiagaraDecalRendererProperties"
COMPONENT_MARKER = b"NiagaraComponentRendererProperties"
# 2026-07-02: a DUPLICATED system carrying stateless (lightweight) emitters asserts at cooked
# BOOT (UNiagaraStatelessEmitter::Serialize, ArrayView index 1 of size 0) — NS_Wane_Death from
# NS_Pickup_Success killed the whole package. Stateless emitters are a hazard in our duplicated
# first-party assets until the duplication path is proven for them.
STATELESS_MARKER = b"NiagaraStatelessEmitter"
EMITTER_MARKER = b"NiagaraEmitterHandle"

# The two REAL cooked-build killers (2026-07-02 packaged gameplay proof report). They stay in
# the project as golden negatives; if either is ever deleted the golden goes BLOCKED, not green.
KNOWN_BAD_SYSTEMS = {
    "/Game/NiagaraExamples/FX_Player/NS_Player_Electricity_Looping.NS_Player_Electricity_Looping":
        "decal renderer parameter store asserts in cooked 5.8 (packaged-match crash)",
    "/Game/NiagaraExamples/FX_Misc/NS_Fire.NS_Fire":
        "PointLight component renderer fails the cooker (typed-element registry ensure)",
}

FIRST_PARTY_FX = {
    "muzzle": "/Game/Wanefall/Dimwit/VFX/NS_Wane_Snap",
    "impact": "/Game/Wanefall/Dimwit/VFX/NS_Wane_Hit",
    "kill_confirm": "/Game/Wanefall/Dimwit/VFX/NS_Wane_Death",
}

_FINDER_RE = re.compile(
    r'FObjectFinder<\s*UNiagaraSystem\s*>\s*\w+\s*\(\s*TEXT\(\s*"(/Game/[^"]+)"\s*\)\s*\)')
_NAMED_FINDER_RE = re.compile(
    r'FObjectFinder<\s*UNiagaraSystem\s*>\s*(\w+)\s*\(\s*TEXT\(\s*"(/Game/[^"]+)"\s*\)\s*\)')


def scan_niagara_asset(uasset_path: Path | str) -> dict:
    """Raw-bytes cook-safety scan of one NiagaraSystem asset. Fail-closed: a missing or
    unreadable asset is NOT cook-safe."""
    path = Path(uasset_path)
    result = {
        "path": str(path),
        "exists": path.exists(),
        "decal_markers": 0,
        "component_markers": 0,
        "stateless_markers": 0,
        "emitter_handles": 0,
        "cook_safe": False,
    }
    if not result["exists"]:
        return result
    try:
        data = path.read_bytes()
    except Exception:
        return result
    result["decal_markers"] = data.count(DECAL_MARKER)
    result["component_markers"] = data.count(COMPONENT_MARKER)
    result["stateless_markers"] = data.count(STATELESS_MARKER)
    result["emitter_handles"] = data.count(EMITTER_MARKER)
    result["cook_safe"] = result["decal_markers"] == 0 and result["component_markers"] == 0
    return result


def discover_gameplay_niagara_refs(source_dir: Path | str = SOURCE_DIR) -> list[dict]:
    """Every UNiagaraSystem FObjectFinder in the game module — the automatic gate perimeter."""
    refs: list[dict] = []
    source_dir = Path(source_dir)
    for path in sorted(source_dir.rglob("*")):
        if path.suffix.lower() not in (".cpp", ".h") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _FINDER_RE.finditer(line):
                refs.append({"game_path": match.group(1), "file": str(path), "line": line_no})
    return refs


def game_path_to_content_file(game_path: str, project_dir: Path | str = PROJECT) -> Path:
    """/Game/X/Y.Y -> <project>/Content/X/Y.uasset"""
    rel = game_path.split(".")[0]
    rel = rel[len("/Game/"):] if rel.startswith("/Game/") else rel
    return Path(project_dir) / "Content" / Path(rel + ".uasset")


def write_cook_safety_report(root: Path | str = ROOT, project: Path | str = PROJECT,
                             result_path: Path | str = RESULT_PATH) -> dict:
    """Regenerated-on-read truth (contract-auditor idiom): scan every gameplay reference AND
    re-run the scanner against the known-bad goldens."""
    project = Path(project)
    referenced = []
    for ref in discover_gameplay_niagara_refs(project / "Source" / "WanefallGreybox"):
        scan = scan_niagara_asset(game_path_to_content_file(ref["game_path"], project))
        # duplicated first-party assets additionally must not carry stateless emitters
        # (cooked-boot Serialize assert — see STATELESS_MARKER note)
        first_party = ref["game_path"].startswith("/Game/Wanefall/Dimwit/VFX/")
        entry_safe = scan["cook_safe"] and not (first_party and scan["stateless_markers"] > 0)
        referenced.append({**ref, "scan": scan, "first_party": first_party, "cook_safe": entry_safe})

    known_bad_golden = []
    for game_path, why in KNOWN_BAD_SYSTEMS.items():
        scan = scan_niagara_asset(game_path_to_content_file(game_path, project))
        known_bad_golden.append({
            "game_path": game_path,
            "why": why,
            "scan": scan,
            # golden holds only if the asset EXISTS and the scanner FLAGS it
            "flagged": scan["exists"] and not scan["cook_safe"],
        })

    report = {
        "schema_version": 1,
        "generated_at": time.time(),
        "project": str(project),
        "referenced": referenced,
        "all_referenced_cook_safe": bool(referenced) and all(r["cook_safe"] for r in referenced),
        "known_bad_golden": known_bad_golden,
        "golden_intact": bool(known_bad_golden) and all(g["flagged"] for g in known_bad_golden),
        "decal_marker": DECAL_MARKER.decode(),
        "component_marker": COMPONENT_MARKER.decode(),
    }
    out = Path(result_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


# ---------------------------------------------------------------- source contracts (static)

def _strip_cpp_comments(text: str) -> str:
    """Commented-out wiring must not satisfy a contract check."""
    text = re.sub(r"/\*.*?\*/", "", text or "", flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _finder_paths(text: str) -> dict[str, str]:
    return {name: path for name, path in _NAMED_FINDER_RE.findall(_strip_cpp_comments(text))}


def parse_combat_fx_surfaces(rifle_cpp_text: str, gamestate_cpp_text: str) -> dict:
    """The three combat FX surfaces must reference distinct first-party NS_Wane_* systems."""
    rifle = _finder_paths(rifle_cpp_text)
    gamestate = _finder_paths(gamestate_cpp_text)
    surfaces = {
        "muzzle": rifle.get("MuzzleFinder"),
        "impact": rifle.get("ImpactFinder"),
        "kill_confirm": gamestate.get("KillConfirmFinder"),
    }
    issues: list[str] = []
    prefix = "/Game/Wanefall/Dimwit/VFX/NS_Wane_"
    for surface, path in surfaces.items():
        if not path:
            issues.append(f"{surface} finder missing (expected a named FObjectFinder)")
        elif not path.startswith(prefix):
            issues.append(f"{surface} is not first-party ({path!r} — must live under {prefix}*)")
    if surfaces["muzzle"] and surfaces["impact"] and surfaces["muzzle"] == surfaces["impact"]:
        issues.append("impact reuses the muzzle system — impact must be its own first-party FX")
    surfaces["issues"] = issues
    return surfaces


def check_runtime_tint(rifle_cpp_text: str, gamestate_cpp_text: str) -> dict:
    """The WANE verb color must be applied at spawn on all three paths (the asset duplication
    keeps donor visuals — the tint is runtime, so it must exist in code, not metadata)."""
    rifle_calls = len(re.findall(r"\bWanefallApplyWaneTint\s*\(", _strip_cpp_comments(rifle_cpp_text)))
    gamestate_calls = len(re.findall(r"\bWanefallApplyWaneTint\s*\(", _strip_cpp_comments(gamestate_cpp_text)))
    issues = []
    if rifle_calls < 2:
        issues.append(f"pulse rifle applies WANE tint at {rifle_calls} spawn site(s), need >=2 (muzzle + impact)")
    if gamestate_calls < 1:
        issues.append("kill-confirm spawn does not apply the WANE tint")
    return {"passed": not issues, "issues": issues,
            "rifle_tint_calls": rifle_calls, "gamestate_tint_calls": gamestate_calls}


def check_packaged_wane_fx_markers(log_text: str) -> dict:
    """Packaged proof of PLAY with the new FX: the machine-played match's log must show all
    three surfaces actually spawned (bots fire + eliminate within the first minute)."""
    found = {surface: bool(re.search(rf"\[WaneFX\] {surface} spawn #\d+", log_text or ""))
             for surface in ("muzzle", "impact", "kill_confirm")}
    issues = [f"no packaged [WaneFX] {surface} spawn marker" for surface, ok in found.items() if not ok]
    return {**found, "passed": not issues, "issues": issues}
