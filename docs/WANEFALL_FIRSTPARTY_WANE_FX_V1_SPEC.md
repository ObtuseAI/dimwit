# FIRSTPARTY_WANE_FX_V1 + NIAGARA_COOK_SAFETY_GATE — Spec (Masterplan Horizon 1, Bundle 5)

**Authored:** 2026-07-02, BEFORE implementation (intent anchor).
**Masterplan:** §C1 item 5 (A4/B2). Replace example-pack gameplay FX with first-party WANE FX;
encode law 5 (cooked-only Niagara failures) as a permanent static gate.

## Ground truth (recon, this session)

- 4 gameplay Niagara references, ALL example-pack: pulse-rifle muzzle+impact (`NS_MuzzleFlash`,
  impact literally reuses the muzzle system), hazard field (`NS_Player_Buff_Looping`),
  board+skimmer trails (`NS_Weapon_Buff_Looping`). Only first-party asset: `NS_Wane_Crystallize`.
- Kill-confirm FX does not exist (dummy death = material swap only). Arena eliminations funnel
  through ONE choke point: `AWanefallArena4v4GameState::RegisterElimination` (victim actor in hand).
- The two known cook-killers are still on disk and binary-scannable: `NS_Player_Electricity_Looping`
  (4× `NiagaraDecalRendererProperties` — cooked-crash), `NS_Fire` (166× `NiagaraComponentRendererProperties`
  — cook-fail). All currently-wired systems + donors scan CLEAN (light renderers present in good
  systems — light ≠ hazard; decal + component are the killers).
- `scripts/ue/ue_vfx_build.py` duplicate lane works but its color set is METADATA-ONLY — a duplicated system
  keeps donor visuals. Donors expose REAL color user-params (binary FName scan):
  `NS_MuzzleFlash` → `User.Flash Base Color`/`User.Smoke Color`; `NS_HitDissolve` →
  `User.Spark Color Gain`; `NS_Pickup_Success` → `User.Color`/`User.Color Secondary`.
- WANE verb colors already canon in `vfx.py WANE_VERBS` (snap/hit/death in the DESIGN.md cyan
  family, secondary #59EDF6).

## Design

**First-party set (duplicate donors into `/Game/Wanefall/Dimwit/VFX`, explicit sources):**
| Asset | Donor (cook-clean, scanned) | Gameplay surface | Runtime tint (C++ at spawn) |
|---|---|---|---|
| `NS_Wane_Snap` | `NS_MuzzleFlash` | pulse-rifle muzzle | `Flash Base Color`+`Smoke Color` = snap teal (0.20,0.95,1.0) |
| `NS_Wane_Hit` | `NS_HitDissolve` | pulse-rifle impact (own system at last — impact currently reuses the muzzle) | `Spark Color Gain` = hit teal (0.30,0.90,1.0) |
| `NS_Wane_Death` | `NS_Pickup_Success` | kill-confirm at victim location from `RegisterElimination` (NET-NEW hook, covers bots + player kills in one place) | `Color`+`Color Secondary` = death blue (0.08,0.40,0.80) |

Runtime tint is the honest headless path: `UNiagaraFunctionLibrary::SpawnSystemAtLocation` →
`SetVariableLinearColor` on the returned component (set both `"X"` and `"User.X"` spellings —
the user redirection store answers one of them). The metadata-only asset tag stays as
provenance; the VISUAL claim is carried by runtime code + packaged evidence, not by metadata.

**Machine evidence in the packaged match:** each first-party spawn logs a throttled
`[WaneFX] <surface> spawn #N` marker (first + every 25th). Bots fire constantly and eliminations
happen within the first minute of the machine-played Arena4v4 match, so the packaged log carries
proof the systems actually SPAWNED in the package — not merely got referenced. Own-eyes review
of the gameplay burst frames complements it.

**Cook-safety scanner (law 5 as code, `dimwit/pipelines/wane_fx.py`):**
- Discover every `FObjectFinder<UNiagaraSystem>(TEXT("/Game/..."))` reference in
  `Source/WanefallGreybox/**` (auto-perimeter: a NEW FX reference enters the gate automatically).
- Resolve each to its `Content/**.uasset`; missing file = FAIL (dangling reference).
- Binary-scan: `NiagaraDecalRendererProperties` or `NiagaraComponentRendererProperties` present
  = FAIL. Evidence JSON written to `artifacts/wane_fx/niagara_cook_safety.json`.

## Gates (new domain `wane_fx` — BLOCKERs unless noted)

| Validator | Asserts |
|---|---|
| `niagara_cook_safety_referenced_clean` | every gameplay-referenced NS asset exists on disk and carries no decal/component renderer markers |
| `niagara_cook_safety_catches_known_bad` | the SAME scanner flags BOTH on-disk known-bad systems (anti-rubber-stamp golden: a weakened scanner fails here) |
| `wane_fx_first_party_combat_surfaces` | muzzle, impact, and kill-confirm hooks reference `/Game/Wanefall/Dimwit/VFX/NS_Wane_*`; impact ≠ muzzle system; the three .uassets exist with ≥1 emitter (binary `NiagaraEmitterHandle`) |
| `wane_fx_runtime_tint_wired` | C++ sets the WANE verb color on all three spawn paths (static source check) |
| `wane_fx_spawned_in_packaged_match` | current packaged log contains `[WaneFX]` muzzle + impact + kill-confirm spawn markers (packaged proof of PLAY with the new FX — law 5) |

Suite 179 → 184. Fail-closed: missing evidence/scan → BLOCKED; scanner regression → golden FAIL.

## Process

RED tests first (scanner golden negatives = the two real bad assets; source-scan fixtures) →
scanner+validators → vfx builds (UnrealEditor-Cmd, one heavy process) → C++ rewire + compile →
repackage + machine-played packaged run (also refreshes perf domain evidence on the new archive)
→ full pytest + full suite → own-eyes → report → state_sync → commits. Ceiling
PROMOTED_TO_REVIEW; no validator weakened.

## Risks

- Donor duplication changes internal paths? No — duplicate_asset preserves graph; tint is runtime.
- `SetVariableLinearColor` name mismatch → set both spellings; packaged own-eyes verifies teal.
- Kill-confirm spam (elims cluster) → single spawn per elimination is the design; throttled logs.
- Board/skimmer/hazard remain example-pack (cook-clean, scanned) — full sweep is a later pass;
  the gate perimeter already covers them for cook-safety.
