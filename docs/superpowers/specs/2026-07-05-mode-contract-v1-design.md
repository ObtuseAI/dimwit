# MODE_CONTRACT_V1 — Design Spec

**Date:** 2026-07-05
**Horizon:** 2 (masterplan §B6 "Modes, progression, persistence" / §C2)
**Bundle type:** Fully headless. No cook, no foreground UE, no optics credits. Pure additive gates.

## Problem

`FWanefallModeSimHarness` (`Source/WanefallGreybox/.../WanefallModeSimHarness.{h,cpp}`) is a
deterministic, world-independent simulation engine that drives the production mode rule machines
(`FWanefallDeathmatchState` / Capture / Control / Hardpoint / SearchDestroy / BattleRoyale /
Extraction / Race / Brawl / Rolling / UI) through full gameplay loops. Every "bot" action calls the
same method the live game calls and asserts on real post-state. It exposes suite runners
`RunArenaSuite()` (13 arena sims), `RunLargeSuite()` (BR + 3 extraction outcomes),
`RunArcadeSuite()` (race/brawl/rolling), `RunUISuite()`.

**Gap:** the ONLY consumer today is `AWanefallBRProofDirector`, which runs the single BR sim inside a
`-game` session and writes `artifacts/br_loop_result.json`; one Dimwit BR gate reads it. The four
suite runners write no proof artifact, so **no Dimwit gate consumes them** — shippable rule-contract
infrastructure sitting dark. Separately, the two registered *demo* modes **WaneTrial** (1v1 +
second-chance redeploy) and **PracticeRange** (no-win practice) have no dedicated sim.

Masterplan §B6: demo modes (TDM + WaneTrial + PracticeRange) each need a mode-contract validator
(win/lose/score/timer paths headlessly simulated via ModeSimHarness every run). This bundle delivers
that AND lights up the full existing suite set.

## Scope (operator: "Full + demo")

1. Expose the existing arena/large/arcade/UI suites via a proof artifact + Dimwit gates.
2. Add two demo-specific sims the harness does not yet model — both grounded in the REAL
   `FWanefallDeathmatchState` rule machine (verified, not invented):
   - **WaneTrial second-chance:** 1v1 duel exercising the existing down→finish loop
     (`RegisterDown` / `RegisterFinish`) — a downed combatant gets exactly one second-chance window
     before a finish counts as the eliminating kill; duel resolves to a single winner + clean reset.
   - **PracticeRange:** untimed-uncapped (`ScoreLimit=0`, `RoundSeconds=0`) — never resolves a
     winner, endless practice, clean reset. Contract = "no false win, no timeout, reset ok".

Out of scope: wane-line mode + the other registered families beyond the harness's current sims
(masterplan lists those as later demo-polish); any rendering/optics; any live packaged lane.

## Approach

**Invocation = commandlet (chosen over director-actor / automation-harvest).** The harness is pure
(no World/RHI/wall-clock/randomness), so a commandlet is the natural fit: no map, no RHI, no game
launch, runs in seconds. The BR director's actor pattern needs a `-game` session + map + is slower —
wasteful when the sim needs no World.

### C++ (WanefallGreybox module)

1. **`UWanefallModeSimProofCommandlet`** (`WanefallModeSimProofCommandlet.{h,cpp}`) — `UCommandlet`
   subclass. `Main()` runs all four suites + the two new demo sims, serializes every
   `FWanefallSimResult` (name, category, result, bPass, per-mode metric Fields incl. score/timer,
   ResetState, bResetOk) into `artifacts/mode_contract/mode_sim_proof.json`. JSON shape mirrors
   `AWanefallBRProofDirector::WriteProof` (reuse the nullable-number helper style). Writes a
   `.done` marker last (atomic-completion signal, BR pattern). Invoked:
   `UnrealEditor-Cmd.exe <uproject> -run=WanefallModeSimProof -stdout -unattended -nosplash`.
2. **Two new `FWanefallModeSimHarness` static methods** driving `FWanefallDeathmatchState`:
   - `FWanefallSimResult WaneTrialSecondChance(const FString& Name);`
   - `FWanefallSimResult PracticeRange(const FString& Name);`
   Each runs a full deterministic loop + a Reset check, same contract style as the existing sims.
   Added to the harness (no new rule machine — reuses the shipped deathmatch state).

### Dimwit (`mode_contract` domain)

`dimwit/pipelines/mode_contract.py`:
- **Runner:** invokes the commandlet, resolves `artifacts/mode_contract/mode_sim_proof.json`
  (+ `.done` marker; git absent / commandlet failure / missing marker → BLOCKED, never silent PASS).
- **Pure checks** over the parsed proof — every pass/fail RECOMPUTED from raw Fields, never trusting
  the reported `bPass` (anti-fabrication, the roster/bot_balance receipts pattern).

Validators (all P.STATIC-over-artifact where possible, S.BLOCKER unless noted):

| Validator | Contract |
|---|---|
| `mode_contract_proof_present` | proof well-formed + fresh (age ceiling), `.done` marker present |
| `mode_contract_arena_suite` | 13 arena sims each resolve a winner within score/time + `bResetOk` |
| `mode_contract_large_suite` | BR last-standing + extraction success/KIA/timeout all correct |
| `mode_contract_arcade_suite` | race (laps/checkpoints), brawl (score), rolling all resolve + reset |
| `mode_contract_ui_foundation` | UI suite builds its registry + passes |
| `mode_contract_wanetrial_second_chance` | down→finish loop exercised; exactly one second-chance window; single winner; reset ok |
| `mode_contract_practice_range` | no winner resolved, no timeout, reset ok (endless-practice contract) |
| `mode_contract_demo_modes_covered` | TDM + WaneTrial + PracticeRange all present & green (demo definition-of-done coverage) |
| `mode_contract_recompute` | reported `bPass` == pass recomputed from raw Fields for EVERY mode (the real correctness/anti-fabrication gate) |

`tests/test_mode_contract.py` — parse fixtures (green proof, malformed, missing marker, a mode with
`bPass=true` but failing raw fields → `mode_contract_recompute` FAILs, second-chance-window-violated
fixture, practice-range-resolved-a-winner fixture). Register the domain in `validation_registry.py`.

## Data flow

```
commandlet -run=WanefallModeSimProof
  → FWanefallModeSimHarness::RunArenaSuite/RunLargeSuite/RunArcadeSuite/RunUISuite
  → + WaneTrialSecondChance + PracticeRange
  → artifacts/mode_contract/mode_sim_proof.json  (+ .done)
      → dimwit mode_contract runner parses
          → 9 BLOCKERs recompute contracts from raw Fields
              → validation_report(_full).json
```

## Error handling / fail-closed

- Commandlet exits non-zero / missing module → runner reports BLOCKED (unreachable proof), not PASS.
- Missing `.done` marker (partial write) → BLOCKED.
- `git`/UE absent → BLOCKED.
- Stale proof (> age ceiling) → freshness FAIL (the artifact is cheap to regenerate; ceiling set with
  the self_metrics radar per `MAX_AGE_BY_VALIDATOR` — commandlet is pure/fast so a tight ceiling is
  fine).
- A mode whose reported `bPass` disagrees with recomputed contract → `mode_contract_recompute` FAIL.

## Testing

- Dimwit: `tests/test_mode_contract.py` (fixtures above) + `--domain mode_contract` live run.
- C++: the sims are self-asserting; the two new demo sims each get a fixture-backed expectation in
  the recompute test (green + adversarial-bad).

## Suite impact

+9 validators, one new `mode_contract` domain. Purely additive; does not touch the reskin/GASP-pending
UE lanes, so it lands without dragging the freshness cascade (only its own `--domain mode_contract`
needs running; a full-green landing still needs the standard self_metrics tail whenever block/fail
counts change).

## Definition of done

- Commandlet builds (editor target, `bUseUnity=false`) + runs headless producing the proof.
- `--domain mode_contract` PASS with all 9 gates green on honest sims.
- pytest `test_mode_contract` green.
- Committed both repos (WG: commandlet + 2 harness methods; RM: pipeline + registry + tests).
- Demo definition-of-done advanced: TDM + WaneTrial + PracticeRange rule contracts gated green.
