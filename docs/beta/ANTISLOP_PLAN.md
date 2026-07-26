# WANEFALL Anti-Slop Hand-Crafting Fix Plan (audit-verified, compile-safe, pure C++ data/visual)

All findings below were verified against the live source: exact files, lines, and current values match. Conflicts between overlapping findings (duplicate "tuning" vs "authenticity/codecraft" lenses on the same knob) are **deduped to one authored value per knob**. Ordered by impact on the "no AI slop / hand-crafted" goal.

---
## TIER 1 — HIGH IMPACT (the slop a player feels in the first match)

### 1. KILL `StatsForClass()` — author 25 bespoke gun rows  *(THE headline fix)*
`WanefallWeaponRegistry.cpp` — `StatsForClass()` lines 38-55, call site line 74, seed struct line 7.
**Confirmed slop:** every gun's stats are a pure `switch(Class)`. Result: Vanguard AR == Judge Auto; Charger == Bulldog == Plasma Repeater (byte-identical 75/0.09/16/3.5); and **all 7 "Special" guns** (Eclipse Rail, Arc Caster, Disruptor, Void Needler, Mace Heavy, Incinerator, Gravity Hammer) collapse to one line 18/0.20/40/1.0. 25 named identities → 11 stat rows.
**Fix (compile-safe refactor + authored data):**
1. Add 5 fields to `FBetaGunSeed` (line 7): `int32 Mag; float Interval; float Damage; float Spread; bool bAuto;`.
2. Fill all 25 seed rows with the bespoke values in the `weaponStatTable` field of this output.
3. In `BuildDefaultGuns()` (line 74) replace `StatsForClass(Seed.Class, ...)` with direct assignment: `Def.MagazineSize=Seed.Mag; Def.FireInterval=Seed.Interval; Def.Damage=Seed.Damage; Def.HipSpreadDeg=Seed.Spread; Def.bAutomatic=Seed.bAuto;`
4. Delete `StatsForClass()` (lines 38-55). Class enum stays as cosmetic grouping only.
**Why it kills slop:** removes the single biggest procedural-uniformity tell. 25 guns now feel like 25 designed weapons with intentional sibling contrasts (Vanguard vs Judge, Longshot vs Tactical, Reaper vs Helix, Charger vs Bulldog vs Plasma) and personality pieces (Executor hand-cannon, Eclipse Rail, Gravity Hammer single-slam).

### 2. Per-species bot height — kill the 185cm clone normalize
`WanefallBotLiteEnemy.cpp:82` (`185.0f / MeshHeight`) + cube fallback line 30 (`0.9,0.9,1.95` = 195cm).
**Confirmed slop:** all 8 alien species force-scaled to one identical 185cm silhouette — the literal "all bots one height" tell — AND it disagrees with the 195cm greybox cube it replaces.
**Fix (compile-safe):** add `float TargetHeightCm = 185.0f` param to `ApplyBetaBodyMesh(UStaticMesh*, float)`; the caller (`WanefallMatchDirector.cpp:73,94`) already has the spawn index `i`, so pass a per-species height from an authored table keyed by `i % 8`:
`const float SpeciesHeightCm[8] = {196.f, 178.f, 168.f, 188.f, 205.f, 162.f, 191.f, 183.f};` (Vorlax, Ekris, Zythan-squat, Qorin, Therak-brute, Ullio-small, Kelous, Nexor — matches the LoadSoldierMesh array order). Inside, `NormScale = TargetHeightCm / MeshHeight`. Drop the cube fallback (line 30) to `1.90` so greybox ≈ meshed.
**Why:** restores species size variety the roster is supposed to sell; one 3-line change, zero new assets. *(Resolves the duplicate height findings — one table, matching the real mesh order in MatchDirector.)*

### 3. Per-enemy ghost color sources the bot's species accent  *(only `compileSafe:false` item — scoped carefully)*
`WanefallPrototypeHUD.cpp:665-666` — every TeamB enemy renders in one `EnemyAccent()` red (verified `(1.0,0.26,0.22)`), flattening the 8-species palette the bible's crown-jewel "read WHO before you see them" depends on.
**Fix (needs a tiny new accessor, hence not pure-data):** add `FLinearColor AWanefallBotLiteEnemy::GetSpeciesAccent() const` + `bool HasSpeciesAccent() const` that read the same `UWaneSubsystem` signature table by species index, then:
`FLinearColor Ghost = Bot->HasSpeciesAccent() ? Bot->GetSpeciesAccent() : (Bot->GetTeam()==TeamB ? EnemyAccent() : AllyAccent());`
**Sequencing note:** this requires the bot to *know* its species — which today is only implied by spawn index. Land it AFTER fix #2 wires a species id onto the bot (store the `i % 8` index on the bot in `ApplyBetaBodyMesh`). If species id isn't stored, this fix is inert. Flagged as the one non-trivial item; everything else is pure data.

### 4. Re-Light ring — ease-out burst + bright wavefront  *(the bible's signature "does this feel special" beat)*
`WanefallPrototypeHUD.cpp:764-776` — a perfect 28-gon on a dead-linear expansion/fade, uniform dots. Reads as debug-draw.
**Fix (pure visual):** ease the expansion (`Ease = 1 - pow(1-E, 2.4)`), brighten the leading edge (`Edge = clamp(1.6*ReLightAlpha,0,1)`), vertical-squash `py` by 0.82 so it rises off the body core, bump `Seg` 28→40, size dots by `Edge`. And at line 726 slow the decay `Dt/1.0f → Dt/1.35f` so the bloom lingers.
**Why:** the one effect the bible names as the gut-check is currently the most machine-generated thing in the file.

### 5. FADE Wane-Channel bar — fat core, tapered tips, odd count
`WanefallPrototypeHUD.cpp:582-596` — `N=16` identical 16×10 segments on a uniform 3px gap, symmetric center-out lit. Generic equalizer.
**Fix (pure visual):** `N=15` (odd → one true core), per-segment width tapering core 20px → tips 11px, draw the center bar 13px tall vs 10px so the chest core physically dominates, dim the just-extinguished segment (`Accent*0.28f`) for glow-decay. Re-anchor etched HP at `StartX + TotalW + 10`.
**Why:** expresses the "extremities die first, core dies last" fiction the comment claims but the flat bar contradicts.

---
## TIER 2 — MEDIUM IMPACT (tuning + structure that reads slop on inspection)

### 6. Battle-Royale ring — fit it to the ~64m arena  *(resolve the two disagreeing definitions)*
Two sources disagree, both full-scale templates:
- `WanefallObjectiveRuntime.cpp:30`: `Setup(StartCombatants, 4, 5.f, 10000.f, 5.f)` → 100m ring, 20s collapse.
- `WanefallLargeModes.h:17-22,30`: defaults 24 / 6 / 30s / 12000 / 600 / 5 / 12000.
The whole playfield is `SweepHalfLength 3200` (~64m), so a 10000 ring does nothing for the first ~10s.
**Fix (one authored ring, applied to BOTH so they agree):**
- `WanefallObjectiveRuntime.cpp:30` → `BrState.Setup(StartCombatants, 5, 9.f, 3600.f, 7.f);`
- `WanefallLargeModes.h` → `StartCombatants=10, ShrinkStages=5, StageSeconds=9.f, StartRadius=3600.f, MinRadius=560.f, OutOfZoneDamagePerSec=7.f, ZoneRadius=3600.f`.
3600 hugs the 3200 sweep so the edge threatens from second one; 5×9s = 45s felt tightening; 560 final (odd) = a tight ~11m circle; 7dps actually punishes a 6 m/s lingerer.

### 7. WANE LINE collapse wall — span the lane, ragged spacing  *(resolve 3 conflicting CollapseSeconds proposals)*
`WanefallWaneLineDirector.h:38-41` (`75 / 5 / 620 / 3200`) + `.cpp:27-31,47-51` even comb. 5×620 wall = 2480 wide but the sweep runs 3200 each way, so combatants walk around the ends.
**Fix (one chosen value set — picks the mid authored pace, not the 52/82 outliers):**
- `NumFields=7`, `FieldSpacing=560.0f` (7×560 = 3360, covers the 3200 sweep with solid overlap), `CollapseSeconds=68.0f` (front ≈ 94 cm/s, dodgeable-but-pressing, non-round), `SweepHalfLength=3100.0f` (just inside the new BR ring).
- In `.cpp` replace the even `(i - Mid) * FieldSpacing` comb (lines 30 & 51) with an authored ragged, denser-center offset table: `static const float FieldOffsets[7] = {-1680,-1020,-420,80,560,1180,1760};` indexed by `i`. *(7 entries to match NumFields; denser in the middle.)*
**Why:** the IP crown jewel currently can't even wall the lane and is a perfectly even ruler.

### 8. Wane hazard field — sharper bite, less metronomic
`WanefallWaneHazardField.h:70,73,79` — `FieldRadius=360, DamagePerSecond=8.0, PulseInterval=4.0`.
**Fix:** `FieldRadius=375.0f` (healthy overlap at the new 560 spacing, non-round), `DamagePerSecond=11.0f` (a 3s brush against the front is now serious on 100hp), `PulseInterval=3.5f` (less metronomic). Keep `PulseDuration 1.2`.

### 9. Control / Hardpoint zones — break the perfect ring
`WanefallObjectiveManager.cpp:72` (radius 900 perfect `(2*PI*z)/N` split), extents lines 40/46/79.
**Fix (authored offset + extent tables, pure data):** replace the cos/sin ring with per-zone anchors. Control (3): `{0,0}` center-contested, `{1040,-360}` far-east, `{-720,820}` near-west; extents `{560, 680, 520}`. Hardpoint (1): offset `{480,-260}` (off-dead-center), extent `660`. Uneven triangle of differently-sized capture areas reads designed, and the contested center is finally inside a zone.

### 10. Per-mode bot counts (de-round the 5/9)
`WanefallMatchGameMode.cpp:65` (`BR ? 9 : DesiredBots`, `DesiredBots=5` in `.h:26`).
**Fix:** mode-aware authored counts in `BeginPlay`: `switch(ObjectiveMode){ case Control: 7; case Hardpoint: 4; case BattleRoyale: 11; default(TDM): 6; }`. 11 in the snug 3600 ring = constant-contact royale; Control 7 gives 3 zones bodies; Hardpoint 4 (one tight zone). *(BR=11 supersedes the older 9; consistent with the new ring.)*

### 11. Vehicle spawn — kill the 45° diagonal
`WanefallMatchGameMode.cpp:86` — `FVector(380.0f, 380.0f, 60.0f)`, a clean symmetric diagonal (auto-placement tell).
**Fix:** `FVector(520.0f, -240.0f, 60.0f)` — parked off to the player's right and slightly behind, an intentional asymmetric stage mark.

### 12. Bot tuning block — lift the floor, break formulaic ratios
`WanefallBotLiteEnemy.h:129-137`. All bots share one round-number row; `EngageRange 850` is exactly half `PerceptionRadius 1600`; `MoveSpeed 340` << player 600 makes bots passive. *(Note: actual firing uses `WanefallCombat::BotDamage/BotPreferredRange` constants, so these UPROPERTYs govern pursuit/spacing/strafe — still real and felt.)*
**Fix (de-round the shared defaults, one consistent set):** `PerceptionRadius=1750, MoveSpeed=390, StrafeSpeed=300, EngageRange=920, TooCloseRange=310, AttackCadence=1.05, StaggerTime=0.6, StaggerKnockback=235, StuckResetTime=5.0`. Replace the "first-pass, human-tunable" comment (line 128) with the design intent. *(Optional follow-on: index a small per-archetype struct by spawn slot in MatchDirector for fast-skirmisher vs slow-heavy variety — pure data, no new code path.)*

### 13. Species palette — split the orange trio, author decay tags
`WanefallWaneSubsystem.cpp:14-21`. Qorin `(1.00,0.55,0.20)` and Therak `(1.00,0.42,0.12)` are near-identical orange; Kelous gold `(1.00,0.80,0.28)` is a third warm neighbor — three of eight species collide at gameplay distance.
**Fix:** keep Qorin ember `(1.00,0.55,0.20)`; push Therak to blood-crimson `(0.86,0.16,0.10)` decay `"crimson-slag"`; shift Kelous to amber-brass `(0.92,0.68,0.14)` decay `"brass-tarnish"`. Now eight legibly distinct hues. *(Note: MatchDirector's mesh array uses `Pyroclast` at mech-index 5 and `therak` at soldier-index 4 — the soldier order is what GetSpeciesAccent must key off.)*

### 14. Charge-rail notches map to real magazine, not tenths
`WanefallPrototypeHUD.cpp:614-617` — 9 dividers from `t/10.0f` chop the rail into base-10 cells; ammo is a magazine, not tenths.
**Fix (pure visual, uses existing `R->GetMagazineSize()`):** `const int32 Ticks = FMath::Clamp(R->GetMagazineSize(), 1, 12); for(t=1;t<Ticks;++t){ FillRect(StartX + RailW*(t/(float)Ticks), ...); }`. Now notches read actual rounds; small mags read shot-by-shot.

### 15. Edge-bite — fray inward instead of a flat rectangle
`WanefallPrototypeHUD.cpp:729-742` + rise line 697 — a solid straight-edged rect popping to full alpha.
**Fix (pure visual):** layer 4 inset bands of falling alpha per edge so the bite dissolves toward center; optionally harden the rise (`-Delta/22.0f`) so meaningful hits bite harder. Keep the 1.2s knit.

### 16. Corner-bracket ghosts — head-up anatomy + sharpness-tracked thickness
`WanefallPrototypeHUD.cpp:661-672` — four identical L-brackets at flat 2px. Generic reticle.
**Fix (pure visual):** `Th = 1 + 1.8*Sharp`, top brackets longer+thicker (`Lt`, `ThTop`) than feet (`Lb`), so the silhouette reads head-up and fades to a faint scratch when stale.

### 17. The FADE vignette — gradient, not a picture frame
`WanefallPrototypeHUD.cpp:744-762` — four solid uniform bands with a razor inner edge; violates "softens / hard clarity floor on center 60%".
**Fix (pure visual):** build each side from ~5 stacked sub-bands whose alpha falls toward center, so the inner edge is soft and stops outside center-60.

### 18. Canonical Wane-alive teal — one constant, not three
`WanefallPrototypeHUD.cpp:499/587/612/769` use `0.25/0.95/1.0` and `0.20/0.95/1.0`; `AllyAccent()` is a third `0.22/0.80/1.0` (verified). Copy-paste-tweak fingerprint.
**Fix:** add `const FLinearColor WaneAlive(0.20f,0.92f,1.0f,1.0f);` in the file's anon namespace, reference at all four sites; align `AllyAccent()` in `WanefallWaneSubsystem.h:36` to the same value so menu color-training transfers to combat.

### 19. Stale-ghost ash smear — drift in travel direction, taper
`WanefallPrototypeHUD.cpp:674-677` — 6 identical dots on a fixed +3px diagonal regardless of enemy movement.
**Fix (pure visual, minimum version):** taper dot size/alpha along the trail (`s = 2.6 - 0.3*k`) and jitter spacing so it isn't a ruler-straight diagonal. (Full directional drift needs last-projected-pos tracking — optional.)

---
## TIER 3 — LOW IMPACT (polish + code craft; do after the above)

### 20. Score targets off the round hundreds
`WanefallObjectiveManager.cpp:39,45` — `SetupHardpoint(1, 250)`, `SetupControl(3, 200)`. → `240` and `175` for authored, non-round match lengths.

### 21. Spawn-offset jitter tables (enemies + allies)
`WanefallMatchDirector.cpp:84-85,101-102` — pure `i%2` mirror + linear `90/60` steps. Replace with authored, non-mirrored `FVector` slot tables; change fallback ring `700 → 680` with ±40 per-bot jitter.

### 22. Authored team rosters instead of array-order round-robin
`WanefallMatchDirector.cpp:94,103` — `LoadSoldierMesh(i)`/`LoadMechMesh(i)` always spawn species in array order. Add `static const int32 EnemyOrder[]`/`AllyOrder[]` index tables so each side reads as a curated faction with a leader. *(Lower than its "high" tag in one finding because it's cosmetic ordering, not felt mechanics; safe pure-data.)*

### 23. Break the mech naming template
`WanefallCharacterRegistry.cpp:10-27` — the `-ion/-wind/-wire/-line` suffix set scans as a wordlist. Rename e.g. `Luxorion → "Halberd"`, `Nightwire → "Cinderjack"`. *(Note: mesh path filenames `SM_Char_Mech_04_Luxorion` etc. are asset-bound — rename only the DisplayName string, NOT the asset path, or it breaks loading.)*

### 24. WANE LINE HUD phase text
`WanefallWaneLineDirector.cpp:57` — bare `"collapse front %d%%"`. Add phase character: `front building` / `collapse advancing` / `COLLAPSE IMMINENT` by progress band.

### 25. Skimmer feel — break the clean 2:1 drain/recharge
`WanefallScoutSkimmerPawn.h:140-155` — drain `0.5` is exactly 2× recharge `0.25`; speeds round hundreds. → `BaseMaxSpeed 1850, BoostMaxSpeed 3250, BoostDrainPerSecond 0.55, BoostRechargePerSecond 0.22, TurnRateDeg 125`.

### 26. FADE band-break thresholds — bespoke + consistent
`WanefallPrototypeHUD.cpp:587-589` (0.50/0.25) vs line ~408 text flip (0.35) — inconsistent danger model. Unify: channel caution at `0.55`, critical at `0.28`, amber `(1.0,0.66,0.18)`, and flip the text at the same `0.28`.

### 27. HUD layout anchors as fractions, banners measured
`WanefallPrototypeHUD.cpp:570` etc. — `SizeY-78` and `-150/-250/-180` banner shoves are resolution-fragile. Anchor `BaseY = SizeY*0.86f`, rail a proportional gap, center banners via `Canvas->StrLen`.

### 28. Code-craft refactors (identical pixels/behavior)
- HUD `Y += 26.0f` repeated ~25× → a local `Row()` lambda (`WanefallPrototypeHUD.cpp:59-60+`).
- `((i%n)+n)%n` duplicated in 6 sites → one `WrapIndex()` helper.
- Duplicate mesh-path tables in `WanefallMatchDirector.cpp:17-47` vs `WanefallCharacterRegistry` → delegate to the registry (single source of truth). *(Verify the registry exposes the same 8 paths first; MatchDirector currently has its own list.)*

---
## Sequencing / safety callouts
- **Do fix #1 first** — biggest craft win, self-contained, compile-safe.
- **#2 must land before #3** (ghost needs the bot to carry a species id; #2 is where to store it). #3 is the only non-pure-data item.
- **#6 + #10** must be chosen together (ring size and combatant count are coupled — 11 bots in a 3600 ring).
- **#7** picks ONE CollapseSeconds (68) and ONE FieldOffsets length (7 to match NumFields=7) — do not mix the 52/82 outliers from the source findings.
- **#13 + #23** are string/color only — never touch the asset path filenames.
- Everything is pure C++ data/number/visual; no maps, no new .uasset materials.

## WEAPON STAT TABLE
// ============================================================================
// BESPOKE 25-GUN STAT TABLE — replaces StatsForClass() entirely.
// Step 1: extend the seed struct (WanefallWeaponRegistry.cpp line 7):
//   struct FBetaGunSeed { const TCHAR* Asset; const TCHAR* Name;
//       EWanefallWeaponClass Class;
//       int32 Mag; float Interval; float Damage; float Spread; bool bAuto; };
// Step 2: paste the rows below over GunSeeds[] (lines 10-36).
// Step 3: in BuildDefaultGuns() (line 74) replace the StatsForClass() call with:
//   Def.MagazineSize = Seed.Mag; Def.FireInterval = Seed.Interval;
//   Def.Damage = Seed.Damage;    Def.HipSpreadDeg = Seed.Spread;
//   Def.bAutomatic = Seed.bAuto;
// Step 4: delete StatsForClass() (lines 38-55).
//
// Columns:                                                                          Mag   Interval  Dmg    Spread  bAuto
const FBetaGunSeed GunSeeds[] = {
    { TEXT("SM_Wpn_Gun_01_vanguard_ar"),     TEXT("Vanguard AR"),     EWanefallWeaponClass::AR,       32,  0.105f,  18.0f,  1.9f,  true  }, // reliable baseline AR
    { TEXT("SM_Wpn_Gun_02_lancer_br"),       TEXT("Lancer BR"),       EWanefallWeaponClass::BR,       30,  0.140f,  21.0f,  1.0f,  true  }, // 3-burst cadence feel, tight
    { TEXT("SM_Wpn_Gun_03_pulse_carbine"),   TEXT("Pulse Carbine"),   EWanefallWeaponClass::Carbine,  26,  0.115f,  16.0f,  1.6f,  true  }, // snappy, light
    { TEXT("SM_Wpn_Gun_04_tempest_smg"),     TEXT("Tempest SMG"),     EWanefallWeaponClass::SMG,      33,  0.066f,  11.0f,  3.4f,  true  }, // bullet-hose, fast, loose
    { TEXT("SM_Wpn_Gun_05_raven_shotgun"),   TEXT("Raven Shotgun"),   EWanefallWeaponClass::Shotgun,   7,  0.920f,  74.0f,  8.6f,  false }, // one heavy pump, 7 shells
    { TEXT("SM_Wpn_Gun_06_judge_auto"),      TEXT("Judge Auto"),      EWanefallWeaponClass::AR,       24,  0.135f,  23.0f,  2.6f,  true  }, // punchier/slower sibling to Vanguard
    { TEXT("SM_Wpn_Gun_07_longshot_dmr"),    TEXT("Longshot DMR"),    EWanefallWeaponClass::DMR,      14,  0.300f,  41.0f,  0.45f, false }, // laser-accurate slow DMR
    { TEXT("SM_Wpn_Gun_08_sentinel_sniper"), TEXT("Sentinel Sniper"), EWanefallWeaponClass::Sniper,    4,  1.250f, 118.0f,  0.10f, false }, // 4-round box, hard hit
    { TEXT("SM_Wpn_Gun_09_eclipse_rail"),    TEXT("Eclipse Rail"),    EWanefallWeaponClass::Special,   3,  1.450f, 132.0f,  0.05f, false }, // charge railgun: tiny mag, pin-accurate
    { TEXT("SM_Wpn_Gun_10_reaper_launcher"), TEXT("Reaper Launcher"), EWanefallWeaponClass::Launcher,  4,  0.950f,  96.0f,  1.1f,  false }, // heavy single rockets
    { TEXT("SM_Wpn_Gun_11_helix_launcher"),  TEXT("Helix Launcher"),  EWanefallWeaponClass::Launcher,  6,  0.620f,  58.0f,  1.4f,  true  }, // twin-spiral auto launcher (vs Reaper)
    { TEXT("SM_Wpn_Gun_12_arc_caster"),      TEXT("Arc Caster"),      EWanefallWeaponClass::Special,  22,  0.180f,  26.0f,  2.2f,  true  }, // chaining lightning, mid/fast
    { TEXT("SM_Wpn_Gun_13_plasma_repeater"), TEXT("Plasma Repeater"), EWanefallWeaponClass::LMG,      80,  0.085f,  15.0f,  3.1f,  true  }, // heat-soak LMG
    { TEXT("SM_Wpn_Gun_14_disruptor"),       TEXT("Disruptor"),       EWanefallWeaponClass::Special,  12,  0.400f,  14.0f,  1.0f,  false }, // EMP utility, low dmg
    { TEXT("SM_Wpn_Gun_15_void_needler"),    TEXT("Void Needler"),    EWanefallWeaponClass::Special,  28,  0.075f,   9.0f,  2.8f,  true  }, // needle swarm, many weak darts
    { TEXT("SM_Wpn_Gun_16_flux_pistol"),     TEXT("Flux Pistol"),     EWanefallWeaponClass::Pistol,   15,  0.170f,  19.0f,  2.1f,  false }, // everyman sidearm
    { TEXT("SM_Wpn_Gun_17_executor"),        TEXT("Executor"),        EWanefallWeaponClass::Pistol,    6,  0.460f,  58.0f,  1.3f,  false }, // hand-cannon: 6 rounds, huge dmg
    { TEXT("SM_Wpn_Gun_18_machine_pistol"),  TEXT("Machine Pistol"),  EWanefallWeaponClass::SMG,      20,  0.058f,  10.0f,  4.0f,  true  }, // fastest+sprayiest of the arsenal
    { TEXT("SM_Wpn_Gun_19_scout_carbine"),   TEXT("Scout Carbine"),   EWanefallWeaponClass::Carbine,  24,  0.125f,  17.0f,  1.4f,  true  }, // tighter scout carbine (vs Pulse)
    { TEXT("SM_Wpn_Gun_20_tactical_dmr"),    TEXT("Tactical DMR"),    EWanefallWeaponClass::DMR,      18,  0.255f,  35.0f,  0.70f, false }, // faster/lighter DMR (vs Longshot)
    { TEXT("SM_Wpn_Gun_21_charger_lmg"),     TEXT("Charger LMG"),     EWanefallWeaponClass::LMG,      60,  0.100f,  19.0f,  2.7f,  true  }, // spin-up heavy hitter, smaller belt
    { TEXT("SM_Wpn_Gun_22_bulldog_lmg"),     TEXT("Bulldog LMG"),     EWanefallWeaponClass::LMG,     100,  0.078f,  14.0f,  3.8f,  true  }, // suppression hose, biggest belt
    { TEXT("SM_Wpn_Gun_23_mace_heavy"),      TEXT("Mace Heavy"),      EWanefallWeaponClass::Special,   5,  0.800f,  88.0f,  1.6f,  false }, // heavy slug thrower
    { TEXT("SM_Wpn_Gun_24_incinerator"),     TEXT("Incinerator"),     EWanefallWeaponClass::Special,  50,  0.050f,   8.0f,  6.5f,  true  }, // flamethrower: huge tank, wide cone
    { TEXT("SM_Wpn_Gun_25_gravity_hammer"),  TEXT("Gravity Hammer"),  EWanefallWeaponClass::Special,   1,  1.700f, 150.0f,  0.0f,  false }, // single-charge slam, mag 1
};