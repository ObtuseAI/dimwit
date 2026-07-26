"""AUDIO_FOUNDATION_V1 (Horizon 2, §B5) — RED-first tests for the static audio-foundation gates.

All fixtures are synthetic strings / tmp dirs — tests never read or mutate live evidence (snapshot
law). RED cases assert the gate FAILS on the real defect it is meant to catch; GREEN cases assert it
passes on a fixed input. A gate that only ever sees green proves nothing.
"""
from __future__ import annotations

from dimwit.pipelines.audio_foundation import (
    EXPECTED_BUSES,
    check_bus_manifest,
    check_cue_assets_resolvable,
    check_event_cue_coverage,
    parse_audio_cue_map,
    parse_combat_event_enum,
)

# ---- synthetic source fixtures -------------------------------------------------------------------
# Mirrors the real enum: 14 values, the last 4 of the "unmapped today" set present.
ENUM_H = r"""
UENUM(BlueprintType)
enum class EWanefallCombatEventType : uint8
{
    DamageApplied,
    TargetDowned,
    TargetFinished,
    TargetEliminated,
    TauntStarted,
    TauntRejected,
    DeathWatchStarted,
    RespawnStarted,
    RespawnCompleted,
    ScoreChanged,
    RoundStarted,
    RoundEnded,
    // V11 combat-feel additions (appended — never reorder existing values).
    BotAcquiredTarget,
    BotFired
};
"""

# The cue map as it ships TODAY: 10 mapped, 4 unmapped (Taunt*/RespawnStarted/BotAcquiredTarget).
CUE_CPP_TODAY = r"""
FString UWanefallCombatEventLog::AudioCueFor(EWanefallCombatEventType T)
{
    switch (T)
    {
    case EWanefallCombatEventType::RoundStarted:      return TEXT("cue_round_start");
    case EWanefallCombatEventType::RoundEnded:        return TEXT("cue_round_complete");
    case EWanefallCombatEventType::BotFired:          return TEXT("cue_bot_fire");
    case EWanefallCombatEventType::DamageApplied:     return TEXT("cue_hit_confirm");
    case EWanefallCombatEventType::TargetDowned:      return TEXT("cue_downed");
    case EWanefallCombatEventType::TargetFinished:    return TEXT("cue_finished");
    case EWanefallCombatEventType::TargetEliminated:  return TEXT("cue_eliminated");
    case EWanefallCombatEventType::ScoreChanged:      return TEXT("cue_score");
    case EWanefallCombatEventType::DeathWatchStarted: return TEXT("cue_death_watch");
    case EWanefallCombatEventType::RespawnCompleted:  return TEXT("cue_respawn");
    default:                                          return FString();
    }
}
"""

# The fixed cue map: TauntStarted + TauntRejected mapped to real cues.
CUE_CPP_FIXED = CUE_CPP_TODAY.replace(
    '    default:                                          return FString();',
    '    case EWanefallCombatEventType::TauntStarted:      return TEXT("cue_taunt");\n'
    '    case EWanefallCombatEventType::TauntRejected:     return TEXT("cue_taunt_reject");\n'
    '    default:                                          return FString();',
)

CODE_CUES = {
    "RoundStarted": "cue_round_start", "RoundEnded": "cue_round_complete",
    "BotFired": "cue_bot_fire", "DamageApplied": "cue_hit_confirm",
    "TargetDowned": "cue_downed", "TargetFinished": "cue_finished",
    "TargetEliminated": "cue_eliminated", "ScoreChanged": "cue_score",
    "DeathWatchStarted": "cue_death_watch", "RespawnCompleted": "cue_respawn",
    "TauntStarted": "cue_taunt", "TauntRejected": "cue_taunt_reject",
}


def _fixed_manifest():
    return {
        "schema_version": 1,
        "combat_cues": {ev: {"cue": cue, "bus": "SFX"} for ev, cue in CODE_CUES.items()},
        "ui_cues": {"deck_deploy": {"cue": "cue_ui_confirm", "bus": "UI"}},
        "exempt": {
            "RespawnStarted": "audible moment is RespawnCompleted (cue_respawn); start is a silent transition",
            "BotAcquiredTarget": "AI-internal targeting signal, not a player-facing event",
        },
    }


# ---- parsers -------------------------------------------------------------------------------------
def test_parse_enum_returns_all_14_values_ignoring_comments():
    vals = parse_combat_event_enum(ENUM_H)
    assert len(vals) == 14
    assert vals[0] == "DamageApplied" and vals[-1] == "BotFired"
    assert "BotAcquiredTarget" in vals


def test_parse_cue_map_ignores_empty_and_default():
    m = parse_audio_cue_map(CUE_CPP_TODAY)
    assert m["DamageApplied"] == "cue_hit_confirm"
    assert "TauntStarted" not in m  # unmapped today
    assert len(m) == 10


def test_parse_cue_map_ignores_sibling_tostring_function():
    # regression: the real .cpp has a ToString-style sibling whose cases return the event's own name.
    # Only AudioCueFor cases are cues — the sibling must not pollute the map.
    cpp = r'''
FString UWanefallCombatEventLog::EventTypeToString(EWanefallCombatEventType T)
{
    switch (T)
    {
    case EWanefallCombatEventType::RespawnStarted:    return TEXT("RespawnStarted");
    case EWanefallCombatEventType::BotAcquiredTarget: return TEXT("BotAcquiredTarget");
    default:                                          return TEXT("?");
    }
}
''' + CUE_CPP_TODAY
    m = parse_audio_cue_map(cpp)
    assert "RespawnStarted" not in m and "BotAcquiredTarget" not in m
    assert len(m) == 10


# ---- leg 2: event-cue coverage (RED then GREEN) --------------------------------------------------
def test_coverage_RED_today_four_unmapped_without_manifest():
    enum = parse_combat_event_enum(ENUM_H)
    cues = parse_audio_cue_map(CUE_CPP_TODAY)
    # no manifest yet -> fail-closed
    r = check_event_cue_coverage(enum, cues, {})
    assert not r["passed"]


def test_coverage_RED_unmapped_events_flagged_even_with_empty_exempt():
    enum = parse_combat_event_enum(ENUM_H)
    cues = parse_audio_cue_map(CUE_CPP_TODAY)
    manifest = {"combat_cues": {ev: {"cue": c, "bus": "SFX"} for ev, c in cues.items()},
                "exempt": {}}
    r = check_event_cue_coverage(enum, cues, manifest)
    assert not r["passed"]
    joined = " ".join(r["issues"])
    for ev in ("TauntStarted", "TauntRejected", "RespawnStarted", "BotAcquiredTarget"):
        assert ev in joined


def test_coverage_GREEN_when_mapped_or_exempt():
    enum = parse_combat_event_enum(ENUM_H)
    cues = parse_audio_cue_map(CUE_CPP_FIXED)
    r = check_event_cue_coverage(enum, cues, _fixed_manifest())
    assert r["passed"], r["issues"]
    assert r["covered"] == 12
    assert set(r["exempt"]) == {"RespawnStarted", "BotAcquiredTarget"}


def test_coverage_RED_on_manifest_code_drift():
    enum = parse_combat_event_enum(ENUM_H)
    cues = parse_audio_cue_map(CUE_CPP_FIXED)
    m = _fixed_manifest()
    m["combat_cues"]["DamageApplied"]["cue"] = "cue_WRONG"  # drift vs code
    r = check_event_cue_coverage(enum, cues, m)
    assert not r["passed"]
    assert any("drift" in i for i in r["issues"])


def test_coverage_RED_on_exempt_and_mapped_contradiction():
    enum = parse_combat_event_enum(ENUM_H)
    cues = parse_audio_cue_map(CUE_CPP_FIXED)
    m = _fixed_manifest()
    m["exempt"]["DamageApplied"] = "contradictory — it is mapped in code"
    r = check_event_cue_coverage(enum, cues, m)
    assert not r["passed"]
    assert any("contradictory" in i for i in r["issues"])


# ---- leg 2: cue asset resolvability --------------------------------------------------------------
def test_cue_assets_RED_when_missing_and_not_placeholder(tmp_path):
    m = {"combat_cues": {"DamageApplied": {"cue": "cue_hit_confirm", "bus": "SFX"}}}
    r = check_cue_assets_resolvable(m, tmp_path)
    assert not r["passed"]


def test_cue_assets_GREEN_with_real_wav(tmp_path):
    (tmp_path / "cue_hit_confirm.wav").write_bytes(b"RIFF" + b"\x00" * 100)
    m = {"combat_cues": {"DamageApplied": {"cue": "cue_hit_confirm", "bus": "SFX"}}}
    r = check_cue_assets_resolvable(m, tmp_path)
    assert r["passed"], r["issues"]


def test_cue_assets_GREEN_with_declared_placeholder(tmp_path):
    m = {"combat_cues": {"X": {"cue": "cue_x", "bus": "SFX",
                               "placeholder": True, "target": "artifacts/audio/cue_x.wav"}}}
    r = check_cue_assets_resolvable(m, tmp_path)
    assert r["passed"], r["issues"]


# ---- leg 1: bus manifest -------------------------------------------------------------------------
def _valid_bus_manifest():
    buses = {"Master": {"parent": None, "target_lufs": -14.0, "max_true_peak_dbtp": -1.0}}
    for b in ("Music", "SFX", "UI", "Voice"):
        buses[b] = {"parent": "Master", "target_lufs": -18.0, "max_true_peak_dbtp": -1.0}
    return {"schema_version": 1, "buses": buses}


def test_bus_manifest_GREEN_full():
    r = check_bus_manifest(_valid_bus_manifest())
    assert r["passed"], r["issues"]
    assert set(r["buses"]) == set(EXPECTED_BUSES)


def test_bus_manifest_RED_missing_bus():
    m = _valid_bus_manifest()
    del m["buses"]["Voice"]
    assert not check_bus_manifest(m)["passed"]


def test_bus_manifest_RED_non_numeric_target():
    m = _valid_bus_manifest()
    m["buses"]["SFX"]["target_lufs"] = "loud"
    assert not check_bus_manifest(m)["passed"]


def test_bus_manifest_RED_wrong_routing():
    m = _valid_bus_manifest()
    m["buses"]["SFX"]["parent"] = "Music"  # must route to Master
    assert not check_bus_manifest(m)["passed"]


def test_bus_manifest_RED_empty():
    assert not check_bus_manifest({})["passed"]


# ---- leg 3: loudness analyzer + gates ------------------------------------------------------------
import math  # noqa: E402
import struct  # noqa: E402
import wave  # noqa: E402

from dimwit.audio_loudness import analyze_wav  # noqa: E402
from dimwit.pipelines.audio_foundation import (  # noqa: E402
    check_loudness_bounds,
    check_no_silence,
    check_true_peak,
)
from dimwit.pipelines.audio_sfx import check_sfx_provenance, synth_cue  # noqa: E402


def _tone_wav(path, freq=440.0, sr=48000, dur=0.5, amp=0.5):
    n = int(sr * dur)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(
            struct.pack("<h", int(amp * math.sin(2 * math.pi * freq * i / sr) * 32767)) for i in range(n)))


def _silent_wav(path, sr=48000, dur=0.5):
    n = int(sr * dur)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"\x00\x00" * n)


def test_analyze_tone_has_signal_not_silent(tmp_path):
    p = tmp_path / "t.wav"; _tone_wav(p)
    a = analyze_wav(p)
    assert not a["silent"]
    assert a["lufs"] > -40 and a["true_peak_dbtp"] > -20
    assert a["kweighted"] is True  # 48k


def test_analyze_silence_flagged(tmp_path):
    p = tmp_path / "s.wav"; _silent_wav(p)
    assert analyze_wav(p)["silent"]


def test_no_silence_RED_on_silent_asset(tmp_path):
    p = tmp_path / "cue_x.wav"; _silent_wav(p)
    assets = [{"cue": "cue_x", "bus": "SFX", "path": str(p), "analysis": analyze_wav(p)}]
    assert not check_no_silence(assets)["passed"]


def test_true_peak_RED_over_ceiling(tmp_path):
    p = tmp_path / "cue_hot.wav"; _tone_wav(p, amp=0.999)  # near full-scale -> tp ~0 dBTP
    bus_m = {"buses": {"SFX": {"target_lufs": -18.0, "max_true_peak_dbtp": -1.0}}}
    assets = [{"cue": "cue_hot", "bus": "SFX", "path": str(p), "analysis": analyze_wav(p)}]
    assert not check_true_peak(assets, bus_m)["passed"]


def test_loudness_RED_when_too_quiet(tmp_path):
    p = tmp_path / "cue_q.wav"; _tone_wav(p, amp=0.001)  # ~ -60 LUFS, far from -18
    bus_m = {"buses": {"SFX": {"target_lufs": -18.0, "max_true_peak_dbtp": -1.0}}, "loudness_tolerance_lu": 6.0}
    assets = [{"cue": "cue_q", "bus": "SFX", "path": str(p), "analysis": analyze_wav(p)}]
    assert not check_loudness_bounds(assets, bus_m)["passed"]


def test_loudness_GREEN_when_synth_hits_bus_target(tmp_path):
    rec = synth_cue("cue_hit_confirm", target_lufs=-18.0, out_dir=tmp_path)
    a = analyze_wav(rec["wav"])
    bus_m = {"buses": {"SFX": {"target_lufs": -18.0, "max_true_peak_dbtp": -1.0}}, "loudness_tolerance_lu": 6.0}
    assets = [{"cue": "cue_hit_confirm", "bus": "SFX", "path": rec["wav"], "analysis": a}]
    assert check_loudness_bounds(assets, bus_m)["passed"], a
    assert check_true_peak(assets, bus_m)["passed"]
    assert check_no_silence(assets)["passed"]


def test_loudness_RED_no_assets():
    assert not check_loudness_bounds([], {"buses": {}})["passed"]


# ---- leg 4: provenance ---------------------------------------------------------------------------
def test_provenance_GREEN_for_synthed_asset(tmp_path):
    import hashlib
    rec = synth_cue("cue_downed", target_lufs=-18.0, out_dir=tmp_path)
    sha = hashlib.sha256((tmp_path / "cue_downed.wav").read_bytes()).hexdigest()
    m = {"combat_cues": {"TargetDowned": {"cue": "cue_downed", "bus": "SFX"}}}
    prov = {"cue_downed": {"license": "self-authored", "sha256": sha}}
    assert check_sfx_provenance(m, prov, tmp_path)["passed"]


def test_provenance_RED_missing_record(tmp_path):
    synth_cue("cue_downed", target_lufs=-18.0, out_dir=tmp_path)
    m = {"combat_cues": {"TargetDowned": {"cue": "cue_downed", "bus": "SFX"}}}
    assert not check_sfx_provenance(m, {}, tmp_path)["passed"]


def test_provenance_RED_sha_mismatch(tmp_path):
    synth_cue("cue_downed", target_lufs=-18.0, out_dir=tmp_path)
    m = {"combat_cues": {"TargetDowned": {"cue": "cue_downed", "bus": "SFX"}}}
    prov = {"cue_downed": {"license": "self-authored", "sha256": "deadbeef"}}
    assert not check_sfx_provenance(m, prov, tmp_path)["passed"]


def test_provenance_RED_bad_license(tmp_path):
    import hashlib
    synth_cue("cue_downed", target_lufs=-18.0, out_dir=tmp_path)
    sha = hashlib.sha256((tmp_path / "cue_downed.wav").read_bytes()).hexdigest()
    m = {"combat_cues": {"TargetDowned": {"cue": "cue_downed", "bus": "SFX"}}}
    prov = {"cue_downed": {"license": "proprietary-ripped", "sha256": sha}}
    assert not check_sfx_provenance(m, prov, tmp_path)["passed"]


# ---- leg 5: packaged-mix FFT segment-energy core -------------------------------------------------
from dimwit.pipelines.audio_mix_proof import segment_band_energy  # noqa: E402


def test_segment_energy_silence_is_zero():
    assert segment_band_energy([0.0] * 4800, 48000) < 1e-6


def _broadband(n, sr=48000, amp=0.4):
    # deterministic broadband signal (LCG noise) — representative of a real combat mix, robust to
    # the sparse log-spaced Goertzel bins (unlike a single pure tone that can fall between bins).
    seed = 0x1234567
    out = []
    for _ in range(n):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        out.append(amp * ((seed / 0x3FFFFFFF) - 1.0))
    return out


def test_segment_energy_in_band_broadband_has_energy():
    assert segment_band_energy(_broadband(4800), 48000) > 1e-3


def test_segment_energy_combat_beats_silent_menu():
    sr = 48000
    combat = segment_band_energy(_broadband(9600), sr)
    menu = segment_band_energy([0.0] * 9600, sr)
    assert combat > menu and menu < 1e-6


# ---- AUDIO_RUNTIME_V1: cue playback wiring -------------------------------------------------------
from dimwit.pipelines.audio_foundation import check_cue_playback_wired  # noqa: E402

_SUB_OK = r'''
void UWanefallAudioCueSubsystem::Initialize(...) { LoadObject<USoundBase>(...); }
bool UWanefallAudioCueSubsystem::PlayCue(const UObject* W, FName C) { UGameplayStatics::PlaySound2D(W, S); return true; }
'''
_GS_OK = r'''
EventLog->RecordEvent(E);
const FString Cue = UWanefallCombatEventLog::AudioCueFor(E.EventType);
if (!Cue.IsEmpty()) { CueSub->PlayCue(W, FName(*Cue)); }
'''


def test_cue_playback_GREEN_when_wired():
    assert check_cue_playback_wired(_SUB_OK, _GS_OK)["passed"]


def test_cue_playback_RED_when_gamestate_only_logs():
    # log-only game-state (the pre-AUDIO_RUNTIME_V1 state): records the event, never plays a cue
    gs_logonly = "EventLog->RecordEvent(E);  // cue is log-only"
    r = check_cue_playback_wired(_SUB_OK, gs_logonly)
    assert not r["passed"]


def test_cue_playback_RED_when_subsystem_never_plays():
    sub_noplay = "bool UWanefallAudioCueSubsystem::PlayCue(...) { return false; }  // no PlaySound"
    assert not check_cue_playback_wired(sub_noplay, _GS_OK)["passed"]


def test_cue_playback_RED_on_missing_source():
    assert not check_cue_playback_wired("", _GS_OK)["passed"]
