# AUDIO_RUNTIME_V1 — Design Spec

**Bundle:** WANEFALL × Dimwit Horizon 2 — follow-on to AUDIO_FOUNDATION_V1 (§B5). Closes leg 5.
**Authored:** 2026-07-04. **Author:** Claude. **Operator directive:** "follow-on wiring bundle" —
make the cues actually play in-game, then close the packaged-mix silence-proof.

## Problem

AUDIO_FOUNDATION_V1 built the gates, buses, SFX, and provenance, but the combat cues were still
**log-only**: `UWanefallCombatEventLog::AudioCueFor()` returned a cue *name* and logged
`[WaneAudioCue]`, but nothing played a `USoundBase`. So the shipped combat mix was genuinely
near-silent and leg 5 (`audio_packaged_mix_has_signal`) correctly stayed BLOCKED. Also discovered:
this machine has **no OS loopback device** (only a mic), so ffmpeg can't capture the system mix.

## Architecture

### 1. Cues become audible
- Import the 14 Dimwit cue WAVs as `USoundWave` under `/Game/Wanefall/Dimwit/Audio/Cues` (reused
  `scripts/ue/ue_audio_import.py`).
- New `UWanefallAudioCueSubsystem` (GameInstanceSubsystem): on Initialize, derive the distinct cue
  names from `AudioCueFor()` over every event type (single source of truth — no drift), load each
  imported SoundWave by convention path, cache `TMap<FName, USoundBase*>`. `PlayCue(WorldCtx, name)`
  → `UGameplayStatics::PlaySound2D`.
- `AWanefallArena4v4GameState::RecordCombatEvent` resolves `AudioCueFor(E.EventType)` → `PlayCue`
  right after recording, so hits/downs/eliminations/round transitions now produce sound.

### 2. In-engine silence-proof (no OS loopback, no cook)
- `-WANEFALLAUDIOPROOF` flag on the bot-match subsystem: `StartRecordingOutput(Master)` at match-0
  setup, `StopRecordingOutput(WavFile)` at finalize → `Saved/Audio/WanefallAudioProof.wav` + a marker
  JSON. Requires real RHI + audio (launch WITHOUT `-nullrhi`).
- `dimwit/pipelines/audio_mix_proof.py` `run()` launches the **editor in `-game`** with
  `-WANEFALLBOTMATCH -WANEFALLAUDIOPROOF -BotMatchCount=1` (real runtime audio, uses the compiled
  module directly — no cook, no OS loopback), waits for the WAV, and analyzes it: pre-combat window
  (0–2 s) vs combat window (3–15 s) band-energy; combat must clear the silence floor and beat the
  pre-combat baseline. Records `source="editor_game"`. `packaged_exe=<...>` runs the same flags
  against the cooked exe when a packaged-specific proof is wanted.

### 3. Gate
- New static BLOCKER `audio_cue_playback_wired`: the cue subsystem must call PlaySound and the
  game-state must dispatch `AudioCueFor -> PlayCue` — proves cues are audible, not just logged.
- `audio_packaged_mix_has_signal` clears once `mix_proof_result.json` shows combat signal.

## Why editor `-game` instead of a cooked package

The submix recorder runs in the real runtime audio path under editor `-game`; it exercises the same
game loop + audio mixer the package uses, using the freshly-compiled module — avoiding the ~$350
cook cascade. Cooked-only audio failures (law 5) would need the packaged variant; the same
`-WANEFALLAUDIOPROOF` flag supports it (`packaged_exe=`), deferred unless a cook-specific regression
appears.

## Out of scope
Spatialized 3D cue playback (currently 2D), per-character voices, music beds, submix effect chains,
cooked-package mix proof (available via the flag, not run this bundle).
