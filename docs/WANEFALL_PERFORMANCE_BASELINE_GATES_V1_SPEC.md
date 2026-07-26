# PERFORMANCE_BASELINE_GATES_V1 — Spec (Masterplan Horizon 1, Bundle 4)

**Authored:** 2026-07-02, BEFORE any implementation (intent anchor).
**Masterplan:** `WANEFALL_DIMWIT_MASTERPLAN_S_TIER_TO_PUBLIC_LAUNCH_V1.md` §B7 / §C1 item 4
(audit bundle 8). WANEFALL performance score is 2/10 — the domain is UNMEASURED. This bundle
makes packaged performance a machine-earned, fail-closed, per-run truth.

## Objective

Packaged fps/frametime/memory capture on the two proof surfaces — **ModeShell command deck**
(menu) and **Wanefall_Arena4v4_Prototype_01** (live bot TDM) — during a machine-played session
of the real packaged `WanefallGreybox.exe`, with floors as BLOCKER gates. Law 5 applies:
packaged proof is the only proof.

## Capture mechanism (C++, WanefallGreybox module)

`UWanefallPerfProofSubsystem : UGameInstanceSubsystem` — created ONLY when the command line
carries `-WANEFALLPERFPROOF` (ShouldCreateSubsystem gate; zero cost otherwise).

- Samples `FApp::GetDeltaTime()` every `FCoreDelegates::OnEndFrame` (game thread, every frame),
  tagged by current world name → per-map segments (menu segment, arena segment; transition
  worlds form their own ignorable segments).
- Memory (`FPlatformMemory::GetStats().UsedPhysical`) sampled every 30 frames; peak + mean kept.
- **Pins measurement conditions and RECORDS them** (one-variable law: uncapped wall frametime is
  the measured variable): `r.VSync 0`, `t.MaxFPS 0`, `GEngine->bSmoothFrameRate=false`,
  `bUseFixedFrameRate=false`; re-asserted on every flush (GameUserSettings can re-apply caps
  during boot); resolution recorded from `GSystemResolution`.
- Flushes JSON every ~5 s (temp file + atomic rename; TerminateProcess-safe — no clean-shutdown
  dependency) to `<ProjectSavedDir>/ShowMeAI/WanefallPerfProof/perf_proof_result.json`, which in
  a packaged build resolves inside the archive dir (same tree as the packaged logs).
- JSON carries: schema_version, pid, executable path, session timestamps, measurement conditions,
  per-segment stats — `total` and `steady` windows (steady = segment minus first 5 s warmup:
  map-load/streaming spikes are load truth, not play truth) — each with sample count, seconds,
  avg/p50/p95/p99/max ms, hitch counts (>100 ms, >250 ms), fps_avg; memory peak/avg MB; plus a
  downsampled frame-ms trace (≤2000 points) for independent cross-checks.
- Optional CSV profiler sidecar (`FCsvProfiler`, fixed frame count on entering the arena map,
  auto-stops — no EndCapture dependency) for draw-call/Nanite/texture-pool/audio-voice budget
  columns. **Informational in V1** (budget floors are a follow-up ratchet; frametime/hitch/
  memory floors are the V1 blockers).

## Machine-played timeline (pipeline `performance_baseline`)

Runs against the CURRENT packaged archive (binds to `packaged_build_validation` evidence — no
rebuild in this lane; missing/stale packaged proof ⇒ BLOCKED):

1. Verify manifest executable sha256 == on-disk exe hash (subject binding).
2. Delete any stale perf JSON from the package Saved tree (fresh-run truth).
3. Launch exe: `<menu map URL> -windowed -ResX=1920 -ResY=1080 -nosound -WANEFALLPERFPROOF`.
4. Window found (DesktopEyes) → identity-bound still (`process_identity_check`, pid-bound
   PrintWindow — law 3).
5. Menu dwell ~25 s (menu segment accrues).
6. ENTER deploy via DesktopHands (posted window messages when unfocusable — law 7).
7. Arena map-load log token wait (packaged log, ≤60 s).
8. Arena dwell (default 100 s) with W-hold pulses (3 s every ~20 s) while the bot match runs.
9. Poll perf JSON until arena steady ≥ min coverage (or deadline) → copy JSON + CSV sidecars
   into `artifacts/performance_baseline/` → terminate → assemble checks → write
   `performance_baseline_result.json` + report.

## Gates (new validator domain `performance_baseline` — all BLOCKER, fail-closed)

| Validator | Asserts |
|---|---|
| `perf_baseline_result_fresh` | result exists, parses, age ≤ 6 h |
| `perf_baseline_identity_bound` | perf JSON pid == launched pid; window capture identity-bound; exe inside archive dir; exe sha256 == package manifest sha |
| `perf_baseline_measurement_conditions` | vsync off, t.MaxFPS 0, smoothing off, 1920×1080 — recorded, not assumed |
| `perf_baseline_segment_coverage` | menu steady ≥ 8 s & ≥ 200 frames; arena steady ≥ 30 s & ≥ 1000 frames |
| `perf_arena_frametime_floor` | arena steady p95 ≤ **16.6 ms** (masterplan min-spec proxy @1080p) |
| `perf_arena_hitch_free` | arena steady frames >100 ms == 0 AND >250 ms == 0 |
| `perf_menu_frametime_floor` | menu steady p95 ≤ 16.6 ms |
| `perf_memory_budget` | session peak UsedPhysical ≤ **8192 MB** |
| `perf_baseline_queue_sync` | pipeline in production manifest + director task registered |

Floors are recomputed at validation time from the embedded segment stats (a tampered `passed`
flag cannot rubber-stamp), and the reported arena p95 is cross-checked against a p95 recomputed
from the downsampled trace (generous tolerance — subsample noise — but a fabricated headline
number diverges). Thresholds are ratchet-only: they may tighten, never loosen.

Note: the 16.6 ms floor inherently rejects a vsync-capped capture (60 Hz cap ⇒ ~16.67 ms
frames ⇒ p95 fails), so the conditions gate and the floor gate back each other up.

## Deliverables / exit gates (doctrine §2)

- RED tests first (`dimwit/tests/test_performance_baseline.py`), tmp-isolated (snapshot law).
- C++ compiles in BOTH targets (`both_targets_compile_clean` is already a suite BLOCKER).
- Repackage (UAT BuildCookRun, all heavy I/O on D:) so the subsystem ships in the package;
  packaged domain re-proven on the new archive.
- Real machine-played perf run → all 9 gates green on real evidence (or honest RED + repair).
- Full pytest + full suite with UE probes; own-eyes review of the identity-bound captures;
  bundle report to Shared Folder; ledger sealed; one reviewed commit set per repo.
- Ceiling unchanged: PROMOTED_TO_REVIEW. No validator weakened.

## Known risks

- C: at ~2.5 GB free — packaging I/O is on D:, but watch C: during the cook (engine logs/temp).
- Frame-rate smoothing/GameUserSettings re-capping mid-session → pin + re-assert + record.
- A real p95/hitch FAIL on first capture is an HONEST result: repair (settings/content), never
  loosen the floor.
- CSV profiler availability differs per config — sidecar is optional evidence, never a fake.
