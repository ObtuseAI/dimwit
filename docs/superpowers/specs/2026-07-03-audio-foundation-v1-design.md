# AUDIO_FOUNDATION_V1 — Design Spec

**Bundle:** WANEFALL × Dimwit Horizon 2, masterplan §B5 (AUDIO_FOUNDATION_V1).
**Authored:** 2026-07-03. **Author:** Claude (orchestrator-validator).
**Operator decision folded in:** §C4 #4 audio-licensing resolved to **generated / CC0 only** (option 2:
foundation + CC0 ingest lane); no external licensed content this bundle; music deferred to a later bundle.
**Scope decision:** all 4 legs in one bundle (operator chose full scope incl. the packaged-mix cascade leg).

## Problem

Audio is the weakest shipped-quality pillar (2026-07-01 audit score 3/10) and is near-zero gated. What
exists today:

- `dimwit/pipelines/audio.py` — `AudioPipeline`: TTS "Weaponized Banter" voicelines → SoundWaves +
  MetaSound stub. Not bound into a fail-closed domain.
- `WanefallCombatEventLog::AudioCueFor()` — maps combat event types → cue-name strings, but **log-only**
  (`[WaneAudioCue]`); no `USoundBase` actually plays. 10 of 13 `EWanefallCombatEventType` values mapped;
  `BotAcquiredTarget`, `TauntStarted`, `TauntRejected`, `RespawnStarted` return empty.
- `WanefallGUIAudioHarness`, `WanefallSpatialAudio*`, `WanefallSocialAudio*` — spatial/social audio proof
  sims + components.
- `vfx_audio` domain has 3 validators, but they are VFX (Niagara) + anti-slop-banter — **not** bus
  architecture, event-coverage, loudness, or packaged-mix.

Masterplan §B5 defines the gap: **bus architecture, event-coverage matrix, loudness gates, packaged-mix
proof**. This bundle builds all four as a fail-closed `audio_foundation` domain, plus a $0 CC0/procedural
SFX authoring+ingest lane feeding them.

## Definition of done

New Dimwit domain `audio_foundation`, all BLOCKERs; full suite green (leg-5 evidence produced by an
operator foreground run); pytest green; own-eyes review of judged audio artifacts (Claude); bundle report
to Shared Folder; committed both repos (push = operator terminal). No gate weakened; gates only added.

## Architecture — 5 legs

### Leg 1 — Bus / submix architecture
- **Bus manifest** `WanefallGreybox/Config/WANEFALL_Audio/bus_architecture.json`: declares 5 buses
  (`Master`, `Music`, `SFX`, `UI`, `Voice`), the routing (all → `Master`), and per-bus loudness targets
  (`target_lufs`, `max_true_peak_dbtp`).
- **UE assets:** real `USoundSubmix` assets (one per bus) authored under `/Game/Wanefall/Dimwit/Audio/Submixes`
  and wired parent→child to match the manifest, via an idempotent installer script
  (`scripts/ue/ue_audio_bus_install.py`), saved into content (capture-law: saved content, not session-spawned).
- **Gate `bus_architecture_declared`** (BLOCKER, filesystem+ue): manifest well-formed with all 5 buses and
  numeric targets; UE submix assets exist and their parent wiring matches the manifest (UE-python probe →
  result file, fail-closed/BLOCKED if UE absent). Manifest is the contract; assets must not drift from it.

### Leg 2 — Event-coverage matrix  *(implemented first — cleanest RED)*
- **Cue policy manifest** `Config/WANEFALL_Audio/cue_coverage.json`: every gameplay-relevant
  `EWanefallCombatEventType` → cue id + bus, plus UI-event cues (deploy/back/confirm/error from the deck),
  plus an explicit `exempt` list with per-entry rationale (events that legitimately have no cue).
- **Gate `event_cue_coverage`** (BLOCKER, static): parse the enum from `WanefallCombatEvent.h` and the
  `AudioCueFor()` switch from `WanefallCombatEventLog.cpp`; assert every enum value is either mapped to a
  non-empty cue in `AudioCueFor()` **or** in the manifest `exempt` list with rationale. Cross-check that the
  code mapping and the manifest agree (no cue in code that the manifest doesn't know; no required cue in
  manifest that code leaves empty). **RED today:** 4 unmapped events → gate fails → fix by mapping the
  gameplay-relevant ones in `AudioCueFor()` + manifest (or exempting with rationale) → green.
- **Gate `cue_assets_resolvable`** (BLOCKER, static): every cue id in the manifest resolves to either a real
  authored asset (WAV in `artifacts/audio/` / SoundWave under the UE audio path) or a manifest-declared
  `placeholder: true` with a target path — no cue is a bare string with nothing behind it.

### Leg 3 — Loudness / true-peak gates
- Pure-Python loudness analyzer `dimwit/audio_loudness.py`: ITU-R BS.1770 K-weighting → integrated LUFS;
  true-peak estimate (4x oversample) in dBTP; RMS silence floor; sample-peak clip check. Stdlib `wave` +
  `math` only (no numpy dependency at module top; optional fast path if numpy present).
- **Gate `loudness_within_bounds`** (BLOCKER, filesystem): every WAV under `artifacts/audio/` (authored
  banter + ingested/synth SFX) has integrated LUFS within its bus target +/- tolerance (from the bus manifest).
- **Gate `true_peak_ceiling`** (BLOCKER, filesystem): every WAV true-peak <= `max_true_peak_dbtp` (default
  -1.0 dBTP); no inter-sample clipping.
- **Gate `no_silent_wavs`** (BLOCKER, filesystem): no WAV is digital silence / below the RMS floor (catches
  empty-synth regressions — a real defect class in the existing TTS lane).

### Leg 4 — CC0 / procedural SFX ingest
- Extend `AudioPipeline` (or a sibling `sfx` pipeline) with an always-available **procedural stinger
  synthesizer** (self-authored waveforms for WANE cues: crystallize / erode / hit_confirm / downed /
  eliminated / ui_confirm / ui_back — additive/FM tones + envelopes, written via stdlib `wave`). $0, offline,
  license = self-authored (CC0-equivalent).
- **Optional CC0 file ingest:** drop-in `.wav` under a watched dir with a sidecar declaring source URL +
  license; ingest copies + records provenance. Network fetch (Freesound API) is **operator-gated** (untrusted
  download) — not run autonomously; the lane accepts operator-provided files.
- **Gate `sfx_provenance_ledgered`** (BLOCKER, filesystem+ledger): every SFX asset consumed by the coverage
  matrix has a ledger/provenance record with `license` in {self-authored, CC0, operator-provided} + source +
  sha256. No un-provenanced audio may back a cue.

### Leg 5 — Packaged-mix silence-proof  *(UE cascade, operator-foreground)*
- Pipeline `dimwit/pipelines/audio_mix_proof.py` + `python scripts/pipeline/run_pipeline.py audio_mix_proof ...`: launches
  the packaged game to a machine-played match, records the system mix via **WASAPI loopback** (ffmpeg dshow
  / `pyaudiowpatch` if available; **BLOCKED, never silent-pass, if no loopback backend**), segments the
  recording into menu vs combat windows, and computes per-segment spectral energy (FFT band RMS).
- **Gate `packaged_mix_has_signal`** (BLOCKER, perception/filesystem over the recording): combat segment has
  spectral energy above a floor **and** combat energy > menu-baseline by a margin (silence or menu-only
  blocks). Evidence = the recording + per-segment spectrum, pid/timestamp-stamped.
- **Constraint (capture law clause 3):** the input-driven match needs foreground focus → this lane runs in the
  **operator terminal**, and must run **LAST** in a green-landing pass (a player-neutralized packaged launch
  clobbers the `[WaneFX]` marker log; ordering per the bundle-6/7 law). Until then the gate is honestly
  BLOCKED (no evidence), not PASS.

## Domain registration & TDD

- Register `audio_foundation` domain in `validation_registry.py` with the 8 BLOCKERs above.
- **RED-first per gate:** each validator gets a test that fails before the producing code/manifest exists
  (TDD law — a test that never failed proves nothing). Tests in `dimwit/tests/test_audio_foundation.py`.
  Tests must never mutate live evidence (snapshot/restore law).
- Full `pytest` + full `scripts/pipeline/run_validation.py` are bundle exit gates.

## Freshness / cost sequencing

- Legs 1–4 are static / filesystem / one UE asset-install (no gameplay re-cook) → cheap, no freshness
  cascade. Land these green first.
- Leg 5 is the only UE-gameplay-cascade leg → operator foreground run, **last**, batched with the deferred
  A2 deck CHALLENGES own-eyes capture; then the self_metrics tail (validate → self_metrics_director →
  validate). Refresh any stale 6h UE lane BEFORE the combat/mix lane, run the mix lane last (bundle-6/7 law).

## Risks

- **WASAPI loopback fragility** — first-run capture may need 2–3 iterations on real hardware; fail-closed to
  BLOCKED, never fake signal. Backend detection is explicit.
- **LUFS on short stingers** — integrated LUFS is unstable under ~0.4 s; analyzer uses momentary/short-term
  windowing for sub-second assets and gates true-peak + silence unconditionally.
- **Submix asset ↔ manifest drift** — manifest is the single source of truth; the gate fails closed on any
  mismatch rather than trusting either side alone.

## Out of scope (later bundles)

Music beds / menu theme (licensing-gated), per-character distinct voices, occlusion/spatialization tuning
gates, LUFS-per-bus *live-mix* (vs per-asset) gates, Steam Deck audio verification.
