"""AUDIO_FOUNDATION_V1 (Horizon 2, masterplan §B5) — fail-closed audio foundation gates.

Pure static/filesystem checks over the WANEFALL audio surface. Everything here is dependency-
injected (functions take source text / manifest dicts / dir paths as args) so tests drive them with
synthetic fixtures and never touch live evidence (snapshot law). The `live_*` loaders + the
registry `v_*` wrappers do the on-disk reading and fail closed (missing input -> BlockedError).

Legs implemented in this module (static / filesystem — no re-cook):
  Leg 2  event-cue coverage matrix   — every combat event maps to a cue or is exempt-with-rationale;
                                        code <-> manifest agree; every required cue resolves to a file.
  Leg 1  bus/submix architecture      — bus manifest well-formed; buses declared with loudness targets.
  Leg 3  loudness/true-peak/silence   — see dimwit/audio_loudness.py (analyzer) + wrappers here.
  Leg 4  sfx provenance               — every cue-backing SFX has a ledgered license+source+sha256.

Leg 5 (packaged-mix loopback silence-proof) lives in dimwit/pipelines/audio_mix_proof.py because it
is a UE-gameplay-cascade lane (operator foreground), not a static check.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from dimwit.audio_loudness import analyze_wav

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
SRC = PROJECT / "Source" / "WanefallGreybox"
COMBAT_EVENT_H = SRC / "Public" / "WanefallCombatEvent.h"
COMBAT_EVENT_LOG_CPP = SRC / "Private" / "WanefallCombatEventLog.cpp"
AUDIO_CFG_DIR = PROJECT / "Config" / "WANEFALL_Audio"
CUE_COVERAGE_MANIFEST = AUDIO_CFG_DIR / "cue_coverage.json"
BUS_MANIFEST = AUDIO_CFG_DIR / "bus_architecture.json"
ARTIFACTS = ROOT / "artifacts"
AUDIO_ART = ARTIFACTS / "audio"

# The five shipped audio buses. Master is the root; the rest route into it.
EXPECTED_BUSES = ("Master", "Music", "SFX", "UI", "Voice")


# ============================================================ source parsing (leg 2)
_ENUM_BLOCK = re.compile(
    r"enum\s+class\s+EWanefallCombatEventType\s*:\s*uint8\s*\{(.*?)\}\s*;",
    re.DOTALL,
)
# a `Case::Value` inside the AudioCueFor switch, mapped to its returned TEXT("...") (empty => unmapped)
_CUE_CASE = re.compile(
    r"case\s+EWanefallCombatEventType::(\w+)\s*:\s*return\s+TEXT\(\"([^\"]*)\"\)",
)
# isolate ONLY the AudioCueFor(...) function body — the .cpp has sibling switch functions (e.g. a
# ToString that returns each event's own name), whose cases must NOT be read as audio cues.
_AUDIO_CUE_FN = re.compile(r"AudioCueFor\s*\([^)]*\)\s*\{(.*?)\n\}", re.DOTALL)


def parse_combat_event_enum(header_text: str) -> list[str]:
    """Return the ordered EWanefallCombatEventType value names from the header text.

    Comments and trailing commas are stripped; a `// ...` line-comment inside the block is ignored.
    """
    m = _ENUM_BLOCK.search(header_text or "")
    if not m:
        return []
    body = m.group(1)
    values: list[str] = []
    for raw in body.split(","):
        # drop line comments, whitespace
        line = re.sub(r"//.*", "", raw).strip()
        if not line:
            continue
        # a value may carry an explicit `= N`; keep only the identifier
        name = re.match(r"([A-Za-z_]\w*)", line)
        if name:
            values.append(name.group(1))
    return values


def parse_audio_cue_map(cpp_text: str) -> dict[str, str]:
    """Return {EventValue: cueName} for every `case ...: return TEXT("cue")` in AudioCueFor.

    Only non-empty cue strings are treated as a mapping; `return FString()` / `TEXT("")` are absent.
    """
    m = _AUDIO_CUE_FN.search(cpp_text or "")
    body = m.group(1) if m else ""  # no AudioCueFor found => no cues (fail-closed downstream)
    out: dict[str, str] = {}
    for value, cue in _CUE_CASE.findall(body):
        if cue:  # empty TEXT("") is not a real cue
            out[value] = cue
    return out


def check_event_cue_coverage(enum_values: list[str], cue_map: dict[str, str], manifest: dict) -> dict:
    """Every combat event value must be covered: a non-empty cue in code, OR an exempt entry with a
    non-empty rationale. Code<->manifest must agree: every code cue is declared in the manifest with
    the same cue id, and every manifest combat_cue names a real enum value with a matching code cue.

    Fail-closed: empty enum / malformed manifest => not passed.
    """
    issues: list[str] = []
    if not enum_values:
        return {"passed": False, "issues": ["no EWanefallCombatEventType values parsed"], "covered": 0}
    if not isinstance(manifest, dict) or not manifest:
        return {"passed": False, "issues": ["cue_coverage manifest missing/empty"], "covered": 0}

    combat_cues = manifest.get("combat_cues") or {}
    exempt = manifest.get("exempt") or {}
    if not isinstance(combat_cues, dict) or not isinstance(exempt, dict):
        return {"passed": False, "issues": ["manifest combat_cues/exempt not objects"], "covered": 0}

    covered = 0
    for value in enum_values:
        code_cue = cue_map.get(value, "")
        if code_cue:
            covered += 1
            # code cue must be declared in manifest with the same id
            decl = combat_cues.get(value)
            if not isinstance(decl, dict):
                issues.append(f"{value}: code cue '{code_cue}' not declared in manifest.combat_cues")
            elif decl.get("cue") != code_cue:
                issues.append(
                    f"{value}: manifest cue '{decl.get('cue')}' != code cue '{code_cue}' (drift)"
                )
        else:
            # unmapped in code => must be exempt with a rationale
            rationale = exempt.get(value)
            if not (isinstance(rationale, str) and rationale.strip()):
                issues.append(f"{value}: no cue in AudioCueFor() and no exempt rationale")

    # reverse drift: a manifest combat_cue that names a non-existent event or an event the code leaves empty
    enum_set = set(enum_values)
    for value, decl in combat_cues.items():
        if value not in enum_set:
            issues.append(f"manifest.combat_cues['{value}'] is not a real EWanefallCombatEventType value")
        elif not cue_map.get(value):
            issues.append(f"manifest declares cue for '{value}' but AudioCueFor() returns empty (drift)")
    # an event cannot be both mapped in code and exempt
    for value in exempt:
        if cue_map.get(value):
            issues.append(f"{value}: exempt AND mapped in code — contradictory")

    return {
        "passed": not issues,
        "issues": issues,
        "covered": covered,
        "total": len(enum_values),
        "exempt": sorted(exempt.keys()),
    }


def _all_declared_cues(manifest: dict) -> dict[str, dict]:
    """Flatten combat_cues + ui_cues into {cue_id: decl} (decl carries bus + optional placeholder)."""
    out: dict[str, dict] = {}
    for group in ("combat_cues", "ui_cues"):
        for _key, decl in (manifest.get(group) or {}).items():
            if isinstance(decl, dict) and decl.get("cue"):
                out[decl["cue"]] = decl
    return out


def check_cue_assets_resolvable(manifest: dict, audio_dir: Path) -> dict:
    """Every cue id declared in the manifest resolves to a real authored WAV in `audio_dir` OR is
    declared `placeholder: true` with a non-empty `target` path. A bare cue string with nothing
    behind it and no placeholder declaration is a fail (no silent 'cue exists' lies).
    """
    issues: list[str] = []
    cues = _all_declared_cues(manifest)
    if not cues:
        return {"passed": False, "issues": ["no cues declared in manifest"], "resolved": 0}
    resolved = 0
    for cue_id, decl in sorted(cues.items()):
        wav = audio_dir / f"{cue_id}.wav"
        if wav.exists() and wav.stat().st_size > 44:  # > empty WAV header
            resolved += 1
            continue
        if decl.get("placeholder") is True and str(decl.get("target", "")).strip():
            resolved += 1
            continue
        issues.append(
            f"cue '{cue_id}' has no {wav.name} and is not a declared placeholder(target=...)"
        )
    return {"passed": not issues, "issues": issues, "resolved": resolved, "total": len(cues)}


# ============================================================ bus manifest (leg 1)
def check_bus_manifest(manifest: dict) -> dict:
    """The bus manifest declares all EXPECTED_BUSES, each routing to Master (Master routes to None),
    each with numeric target_lufs and max_true_peak_dbtp. Fail-closed on any missing/typed-wrong field.
    """
    issues: list[str] = []
    if not isinstance(manifest, dict) or not manifest:
        return {"passed": False, "issues": ["bus manifest missing/empty"]}
    buses = manifest.get("buses")
    if not isinstance(buses, dict):
        return {"passed": False, "issues": ["bus manifest has no 'buses' object"]}
    for name in EXPECTED_BUSES:
        b = buses.get(name)
        if not isinstance(b, dict):
            issues.append(f"bus '{name}' missing")
            continue
        if name == "Master":
            if b.get("parent") not in (None, "", "None"):
                issues.append("Master bus must be root (parent None)")
        elif b.get("parent") != "Master":
            issues.append(f"bus '{name}' must route to Master (parent={b.get('parent')!r})")
        if not isinstance(b.get("target_lufs"), (int, float)):
            issues.append(f"bus '{name}' target_lufs not numeric")
        if not isinstance(b.get("max_true_peak_dbtp"), (int, float)):
            issues.append(f"bus '{name}' max_true_peak_dbtp not numeric")
    extra = set(buses) - set(EXPECTED_BUSES)
    if extra:
        issues.append(f"unexpected buses declared: {sorted(extra)}")
    return {"passed": not issues, "issues": issues, "buses": sorted(buses.keys())}


# ============================================================ live loaders (fail-closed)
def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def live_enum_values() -> list[str]:
    return parse_combat_event_enum(_read(COMBAT_EVENT_H) or "")


def live_cue_map() -> dict[str, str]:
    return parse_audio_cue_map(_read(COMBAT_EVENT_LOG_CPP) or "")


def live_cue_manifest():
    return _read_json(CUE_COVERAGE_MANIFEST)


def live_bus_manifest():
    return _read_json(BUS_MANIFEST)


# ============================================================ loudness gates (leg 3)
def _cue_bus_map(cue_manifest: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for group in ("combat_cues", "ui_cues"):
        for _k, decl in (cue_manifest.get(group) or {}).items():
            if isinstance(decl, dict) and decl.get("cue"):
                out[decl["cue"]] = decl.get("bus")
    return out


def analyze_audio_assets(audio_dir: Path, cue_manifest: dict) -> list[dict]:
    """Analyze every declared cue WAV that exists on disk. Placeholders (no WAV) are skipped here —
    the leg-2 resolvable gate owns 'the cue has SOMETHING behind it'; loudness only grades real audio.
    """
    out: list[dict] = []
    for cue, bus in sorted(_cue_bus_map(cue_manifest).items()):
        wav = Path(audio_dir) / f"{cue}.wav"
        if wav.exists() and wav.stat().st_size > 44:
            out.append({"cue": cue, "bus": bus, "path": str(wav), "analysis": analyze_wav(wav)})
    return out


def _buses(bus_manifest: dict) -> dict:
    return (bus_manifest or {}).get("buses") or {}


def check_loudness_bounds(assets: list[dict], bus_manifest: dict) -> dict:
    """Every real cue WAV within its bus target LUFS ± tolerance. Fail-closed on no assets."""
    if not assets:
        return {"passed": False, "issues": ["no audio assets analyzed"], "checked": 0}
    tol = float((bus_manifest or {}).get("loudness_tolerance_lu", 6.0))
    buses = _buses(bus_manifest)
    issues: list[str] = []
    for a in assets:
        target = (buses.get(a["bus"]) or {}).get("target_lufs")
        lufs = a["analysis"]["lufs"]
        if target is None:
            issues.append(f"{a['cue']}: bus {a['bus']} has no target_lufs")
        elif lufs == -math.inf or abs(lufs - target) > tol:
            issues.append(f"{a['cue']}: {lufs:.1f} LUFS outside {target}±{tol} (bus {a['bus']})")
    return {"passed": not issues, "issues": issues, "checked": len(assets)}


def check_true_peak(assets: list[dict], bus_manifest: dict) -> dict:
    """No real cue WAV exceeds its bus true-peak ceiling (default -1.0 dBTP)."""
    if not assets:
        return {"passed": False, "issues": ["no audio assets analyzed"], "checked": 0}
    buses = _buses(bus_manifest)
    issues: list[str] = []
    for a in assets:
        ceil = (buses.get(a["bus"]) or {}).get("max_true_peak_dbtp", -1.0)
        tp = a["analysis"]["true_peak_dbtp"]
        if tp > ceil:
            issues.append(f"{a['cue']}: true peak {tp:.2f} dBTP > ceiling {ceil}")
    return {"passed": not issues, "issues": issues, "checked": len(assets)}


def check_no_silence(assets: list[dict]) -> dict:
    """No real cue WAV is digital silence (catches empty-synth / dead-encode regressions)."""
    if not assets:
        return {"passed": False, "issues": ["no audio assets analyzed"], "checked": 0}
    issues = [f"{a['cue']}: digital silence / below floor" for a in assets if a["analysis"]["silent"]]
    return {"passed": not issues, "issues": issues, "checked": len(assets)}


# ============================================================ cue playback wiring (AUDIO_RUNTIME_V1)
AUDIO_CUE_SUBSYSTEM_CPP = SRC / "Private" / "WanefallAudioCueSubsystem.cpp"
ARENA_GAMESTATE_CPP = SRC / "Private" / "WanefallArena4v4GameState.cpp"


def check_cue_playback_wired(subsystem_cpp: str, gamestate_cpp: str) -> dict:
    """Prove cues are actually AUDIBLE, not just logged: the cue subsystem must PlaySound, and the
    game-state must resolve AudioCueFor -> PlayCue on each combat event. Fail-closed on missing source.
    """
    issues: list[str] = []
    s = subsystem_cpp or ""
    g = gamestate_cpp or ""
    if not s:
        issues.append("cue subsystem source missing/unreadable")
    else:
        if "PlayCue" not in s:
            issues.append("cue subsystem has no PlayCue")
        if "PlaySound2D" not in s and "PlaySound(" not in s:
            issues.append("cue subsystem never calls PlaySound (cues would be inaudible)")
    if not g:
        issues.append("arena game-state source missing/unreadable")
    elif "AudioCueFor" not in g or "PlayCue" not in g:
        issues.append("game-state does not dispatch AudioCueFor -> PlayCue (combat stays silent)")
    return {"passed": not issues, "issues": issues}


def live_cue_playback_sources():
    return _read(AUDIO_CUE_SUBSYSTEM_CPP) or "", _read(ARENA_GAMESTATE_CPP) or ""


def live_audio_assets() -> list[dict]:
    return analyze_audio_assets(AUDIO_ART, live_cue_manifest() or {})


def live_provenance() -> dict:
    return _read_json(AUDIO_ART / "sfx_provenance.json") or {}
