# WANEFALL — BETA ASSEMBLY PLAN (Lead Architect, Fused)

## The decision

All three design approaches agree on the same backbone and the same single hard gap. I am fusing them into **one** build order and resolving the one real disagreement (sequencing the Wane spine vs. the playable loop).

**The disagreement:** Approach 3 ("WANE Spine First") builds `UWaneSubsystem` + `MF_Wane` + 8 `FWaneSignature` rows as Milestone 1, *before* anything is playable, and pushes bot-fill to M7. That is the wrong altitude for a beta. The requirement is explicit: **the shared CORE milestone makes the FIRST mode playable with bots fastest.** A subsystem that only logs `Wane.Dump` is not a playable beta — it is doctrine for its own sake.

**The ruling:** Lead with **Approach 1 / Approach 2's match spine** (GameMode + bot-fill director + asset wiring + minimal FADE HUD) as M1 so the user is *fighting alien bots from one double-click* after a single compile gate. Then adopt **Approach 2's generalized `AWanefallMatchDirector`** as the mode-expansion spine (it scales to all 24 modes via the already-complete `UWanefallMatchRuntimeComponent`, where Approach 1's bespoke `AWanefallBotSpawnDirector` only ever serves TDM). Then layer in **Approach 3's bible-correct `UWaneSubsystem` + `MF_Wane` spine** as the home for the weapon/character registries and the fuller FADE materials — built *after* there is a playable surface to hang them on, not before. Finally THE HOLD front-end and the first WANE LINE collapse map.

This is verified ground truth, not a guess. I confirmed every load-bearing seam:

- `AWanefallArena4v4GameState::RefreshBotRoster()` (Public header line 128) does `for (TActorIterator<AWanefallBotLiteEnemy> It(W); It; ++It) Bots.Add(*It);` (cpp line 182) — **so any bot spawned at runtime is auto-discovered**; a director only needs to `SpawnActor` + `SetTeam` + call `RefreshBotRoster()`. `AddBotForProof()` (line 132), `ApplyRoundStateToBots()` (136), `TickBotRespawns()` (137) are all public.
- `AWanefallArena4v4GameState::BeginPlay()` auto-calls `BeginCountdown()` (cpp line 33) and `EndRound()` fires on score-limit or timer (lines 103, 146) — **the round loop is self-arming and complete**; it only needs bots placed in the world.
- `AWanefallBotLiteEnemy` roots on a `UStaticMeshComponent` set to `/Engine/BasicShapes/Cube` (cpp lines 24-29) with a `RefreshVisual()` + `BodyDMI` recolor seam — **swap one `SetStaticMesh` call for a Dimwit soldier mesh and bots become aliens.**
- `AWanefallPrototypeCharacter::BuildVisibleWeapon()` (cpp line 1874) hardcodes `/Game/NiagaraExamples/Gallery/Weapons/Rifle/Mesh/SM_Rifle` at line 1881 into `WeaponBodyMesh->SetStaticMesh()` — **one data-driven swap turns the 25 `SM_Wpn_Gun_*` into equippable guns; firing is untouched** (`PulseRifle->TryFire()` → `FireFromView`).
- Pulse rifle getters `GetCurrentAmmo/GetReserveAmmo/GetMagazineSize/GetReloadProgress01` confirmed (header lines 60-63) — the FADE Charge-Rail binds to these unchanged.
- `Config/DefaultEngine.ini` `GlobalDefaultGameMode=/Script/WanefallGreybox.WanefallPrototypeGameMode` (line 8) — the **logic-less** default mode, confirming the single hard gap: **no GameMode spawns/configures a match.** This is what M1 fixes.
- Assets confirmed on disk: 8 soldiers (`SM_Char_01_Vorlax`…`08_nexor`), 8 mechs, 25 guns, 11 melee, 10 grenades, 9 vehicles. The code species enum (`Kharvex`…`Caelrex`) does **not** match the soldier names (Vorlax…) — M5 picks the canonical mapping.
- Launchers confirmed: `HumanTestLaunch/WANEFALL_OPEN_V5_COMBAT_SANDBOX.bat` is the clone template; both UBT targets already compiled (DLL+exe 2026-06-25).

**Run mechanism:** PIE-launch via a one-click `.bat`, **not** a cooked build. Recon confirms heavy marketplace content (Paragon/Soul City/Cave) makes a clean cook slow and fragile, and the existing 342MB `WanefallGreybox.exe` still reads loose Content (not redistributable). The proven ShowMeAI HumanTestLaunch pattern is the fast, safe path.

---

## Milestone M1 — CORE: playable bot-filled TDM from one double-click (THE shared spine)

**Goal:** One compile gate away from the user fighting autonomous alien bots in Arena4v4 TDM. Reuse the entire existing combat/round/pulse-rifle stack; build only the missing GameMode + spawn/fill director, and fold in the cheapest asset + HUD wins so the first runnable already *reads as WANEFALL*, not engine cubes.

This single milestone deliberately fuses what Approach 1 split across M1–M3, because each piece is a few lines on a verified seam and shipping them together makes the FIRST loop land at the right altitude.

**New classes (the only genuinely new code):**
- `AWanefallMatchGameMode : public AWanefallPrototypeGameMode` — keeps the proven pawn/controller/HUD wiring; in `BeginPlay`/`InitGame` finds-or-spawns `AWanefallArena4v4GameState` (so the map need not hand-place it) and spawns one `AWanefallMatchDirector`. *(Approach 2's name — it is the mode-agnostic spine M5+ extends, not a TDM-only mode.)*
- `AWanefallMatchDirector : public AActor` — `FillTeams()`: `TActorIterator<APlayerStart>` to gather spawns, then a real fill loop `while (aliveOnTeam < TeamSize) World->SpawnActor<AWanefallBotLiteEnemy>(...)`, `Bot->SetTeam(EWanefallTeam::TeamB)` (+ a few TeamA allies), then `arena->RefreshBotRoster()`. Model the `SpawnActor` call on the existing `AWanefallPrototypeThreatSpawner::SpawnEnemyAt`. `DesiredBotsPerTeam` is `UPROPERTY(EditAnywhere)=4`, later read from `FWanefallModeDefinition.TeamSize`.

**Reused as-is (do not rebuild):** `AWanefallBotLiteEnemy` (chase/strafe/LOS-fire), `AWanefallArena4v4GameState` (countdown→round→score→respawn), `UWanefallWanePulseRifleComponent::TryFire`→`FireFromView`, `UWanefallDownedStateComponent`/`UWanefallDeathWatchComponent` respawn path.

**Cheap asset + HUD wins folded in:**
- Bot mesh swap: in `AWanefallBotLiteEnemy::RefreshVisual` (or BeginPlay), if a new `TSoftObjectPtr<UStaticMesh> BotBodyMesh` is set, `Body->SetStaticMesh(...)` a `SM_Char_0N` soldier and clear the cube scale; director round-robins the 8 soldiers by team/index. Keep `QueryAndPhysics`/`ECC_WorldDynamic` block so hitscan still registers.
- Player gun mesh: change `BuildVisibleWeapon` line 1881 from `SM_Rifle` to `/Game/Wanefall/Dimwit/Weapons/SM_Wpn_Gun_03_pulse_carbine/StaticMeshes/SM_Wpn_Gun_03_pulse_carbine` (keep the kitbash fallback). Firing path unchanged.
- Minimal FADE HUD in `AWanefallPrototypeHUD::DrawHUD`: replace the ASCII `MakeBar` health/ammo with **WANE CHANNELS** (segmented health that extinguishes green→amber→red from `GetHealthComponent()->GetCurrentHealth/GetMaxHealth`) + **CHARGE-RAIL** (segmented ammo from `GetCurrentAmmo/GetMagazineSize` with a `GetReloadProgress01` sweep) + a minimal **WANE-GHOSTS** canvas pass (`Canvas->Project` each living `AWanefallBotLiteEnemy`, fade alpha by last-seen age via `HasLineOfSight`). Gate the old telemetry behind the existing `[F1] IsDebugHUDVisible()`.

**Boot wiring:** `DefaultEngine.ini` → `GlobalDefaultGameMode=/Script/WanefallGreybox.WanefallMatchGameMode`, `GameDefaultMap=/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01`. New `HumanTestLaunch/WANEFALL_BETA.bat` (clone of the V5 sandbox bat).

**User-testable:** Double-click `WANEFALL_BETA.bat` → boots into `Arena4v4_Prototype_01`, 3-2-1 countdown, a live TDM round vs. **4 alien-soldier bots** that chase/strafe/shoot you; you kill them with the **Dimwit pulse-carbine**; TeamA score ticks on each elimination; bots respawn after 3s; round ends at score-limit 25 or 300s. HUD shows segmented Wane Channels (health) + Charge-Rail (ammo) + on-screen enemy Wane-Ghosts. No hand-placement, no cubes.

---

## Milestone M2 — Weapon & character data spine (the id→asset bridge)

**Goal:** Promote the M1 hardcoded mesh swaps into the bible's data-driven registry so the full 36 guns + 16 characters are reachable, and nothing gets stripped on a future cook.

**New classes:**
- `UWanefallWeaponDef` (`UPrimaryDataAsset`): `UStaticMesh* Mesh`, `EWanefallWeaponClass`, `Damage`, `FireInterval`, `MagazineSize`, `ReserveAmmo`, `Spread`, `bAuto`.
- `UWanefallWeaponRegistry` (`UGameInstanceSubsystem`): `BuildDefaultWeapons()` populates one row per `SM_Wpn_Gun_01..25` + `SM_Wpn_Melee_01..11` + `SM_Wpn_Gren_01..10` by hard path; `ResolveById(FName)`.
- `UWanefallCharacterDef` + `UWanefallCharacterRegistry`: one row per `SM_Char_01_Vorlax..08_nexor` + 8 mechs → `UStaticMesh*` + display name + mapped `EWanefallSpecies` material family.

**Extend (real seams):** `BuildVisibleWeapon` pulls mesh+stats from the active `WeaponDef` and feeds `Damage/FireInterval/MagazineSize` into the existing `UWanefallWanePulseRifleComponent`/`UWanefallPrototypeWeaponComponent` fields — **do not touch `FireFromView`** (single damage source preserved). Add `EquipWeaponById(FName)` + a debug weapon-cycle input. Director assigns a `CharacterDef` per bot.

**Honesty note (carried from all three approaches):** the 16 Dimwit characters are **static meshes with no skeleton** — they cannot drive a locomoting `ACharacter`. They are used as **bot bodies** and **front-end select props**; the human pawn keeps the rigged engine mannequin and treats identity as material/species via the existing `ApplySpeciesProfile`. No rigging is implied.

**User-testable:** In the TDM match, press the weapon-cycle key → the held gun mesh changes through several real Dimwit guns and ammo/fire-rate/damage change per weapon; bots render as distinct soldiers/mechs by team. Firing still hits and kills.

---

## Milestone M3 — THE WANE spine + fuller FADE materials (bible PART 3)

**Goal:** Now that there is a playable surface, stand up the bible-mandated shared spine and promote the canvas FADE to real materials on the world. The weapon/character registries from M2 **move onto `UWaneSubsystem`** as their canonical home.

**New (bible spine):** `UWaneSubsystem` (`UGameInstanceSubsystem`, modeled on the existing `UWanefallArenaScoreSubsystem`) owning 8 `FWaneSignature` rows (accent HDR ~1.0, decay phase, erode/crystallize params) keyed to `EWanefallSpecies`; content `MF_Wane` material function. `UWaneMotion` static helpers (Crystallize/Erode/Snap) so all cues share one implementation. `USensoriumClarity` governor (caps simultaneous ghosts, protects center 60%) + per-ghost `SensoryAge`.

**New content materials:** `M_WaneChannel` (body-emissive vitals on pawn/bot meshes), `M_ChargeRail` (weapon-receiver emissive from the M1 ammo getters), `PP_EdgeBite` (directional damage post-process via a new `UWaneDamageCueComponent` fed by the health-drop delta), `M_WaneGhost` (custom-depth/stencil silhouette replacing the M1 canvas ghost), `PP_Fade` (low-HP desaturate + inverted contrast, center-60% clarity floor) + Re-Light heal.

**Extend:** Demote `AWanefallPrototypeHUD::DrawHUD` to the `[F1]` debug overlay once vitals live on materials; keep a minimal UMG `WidgetComponent` for the etched core HP integer. Reuse the headless harness pattern (`FWanefallGUIAudioHarness`) so the Wane systems stay proof-driven.

**User-testable:** Take damage → screen-edge Edge-Bite from the hit direction + body Wane Channels extinguish inward; fire → receiver Charge-Rail notches deplete red-hot; occluded bots render as accent-colored Wane-Ghosts that age to ash over ~1.5s and re-sharpen on gunfire; low HP → world desaturates but center stays readable; heal → color crystallizes outward.

---

## Milestone M4 — THE HOLD front-end: select → persist → launch

**Goal:** Close the recon-confirmed gap (menu displays but never launches; `OpenLevel` carries no character/loadout) with a real selection→launch chain feeding the existing `AWanefallModeRouter::RequestMode`.

**New:** `UWaneGameInstance`/`UWanefallSelectionState` (`UGameInstanceSubsystem`) holds `SelectedModeId/MapPath/CharacterId/PrimaryWeaponId/GrenadeId` (survives `OpenLevel`). `AWanefallHoldGameMode` + a HOLD map `Wanefall_TheHold_01` (8 soldier meshes as glow-select stands, gun rack from M2 registry — **this is where the species↔soldier-name canonical mapping is fixed**).

**Reuse wholesale (do not rebuild):** `FWanefallModeSelectVM::BuildFromRegistry`, the mode registry, `FWanefallSettings`, `AWanefallModeRouter::RequestMode`→`OpenLevel`, and the existing `AWanefallShellPlayerController` `CreateWidget`+`AddToViewport` pattern. Replace the empty `OpenResults()`/stub nav with real list-select handlers writing into `UWanefallSelectionState`.

**Extend:** `AWanefallMatchGameMode` reads `UWanefallSelectionState` on the destination map to set `DesiredBotsPerTeam` from `TeamSize`, apply the chosen species via `SetSpecies()+ApplySpeciesProfile()` on possess, and `EquipWeaponById`. Surface mode `Status` honestly (PlayablePrototype vs Experimental). Switch boot map/GameMode to THE HOLD.

**User-testable:** Boot → land in THE HOLD; chord-key whip-pan between stations; pick mode (Arena4v4 TDM) + an alien character + gun/grenade; pull deploy lever → travels to the arena with your species + weapon applied and bots filled from `TeamSize`. Other modes clearly marked Experimental.

---

## Milestone M5 — Light up objective modes (CTF / Control / Hardpoint / SND)

**Goal:** Activate the 4 Arena objective modes by wiring the **already-complete** `UWanefallMatchRuntimeComponent` + `AWanefallObjectiveVolume` into the live director — the modes are rule-complete and only ever ran under the headless harness.

**Extend `AWanefallMatchDirector`:** when `Objective != Deathmatch`, create+own a `UWanefallMatchRuntimeComponent`, call the matching `SetupCaptureTheFlag/SetupControl/SetupHardpoint/SetupSearchDestroy` (recon-confirmed) from the mode row, `StartMatch()`, and `TickRuntime(Dt)` in Tick. Spawn `AWanefallObjectiveVolume` actors at flag/zone/hill/bomb anchors in `Wanefall_ArenaCore_Greybox_01` so world overlap drives the rule machine via its existing presence handlers (`OnRelicPickup/OnZoneOccupancyChanged/OnPlantTick`). Add a simple "move toward active objective volume" bot nudge (reuse `StepToward`; the 6s stuck-reset guards it — no navmesh in beta). Flip those 4 registry rows to `PlayablePrototype`.

**User-testable:** From THE HOLD pick CTF/Control/Hardpoint/SND → each loads ArenaCore, fills both teams with bots, and the real objective rules resolve live (capture count climbs, zone score/sec accrues, plant/defuse ends rounds).

---

## Milestone M6 — Large + arcade modes + first WANE LINE collapse map

**Goal:** Light up BattleRoyale (24), Extraction (8), Race/Brawl/Rolling via the same director, wire the 9 vehicle meshes, and land the IP's crown-jewel as a single working map layer.

**Extend `AWanefallMatchDirector`:** route `SetupBattleRoyale(24)` / `SetupExtraction()` / `SetupRace/Brawl/Rolling` (recon-confirmed signatures) with bot-fill to advertised counts at the shell maps' PlayerStarts; wire BR ring-shrink out-of-zone damage through `FWanefallBattleRoyaleState`. **Verify `FWanefallExtractionState::TickExtract`/timeout** (recon flagged it only partially read) before relying on extraction resolution. Wire the 9 `SM_Veh_*` meshes into the `AWanefallScoutSkimmerPawn`/`AWanefallPrototypeVehicle` mesh slot for arcade.

**New WANE LINE:** `AWaneLineDirector` (`AActor`) — a deterministic `WaneProgress` timeline drives a world-position-offset wipe param into `MF_Wane` across registered collapsible (bright-veined) meshes (Pristine→Fallen); reuse the existing `AWanefallWaneHazardField` flee-reaction the bots already respond to as the out-of-zone hazard. One authored map `Wanefall_WaneLine_01` with dual-material slice. The same `WaneProgress` float drives the HOLD crust meter (one float, bible Law).

**User-testable:** From THE HOLD pick WANE ROYALE / WANE EXTRACTION / an Arcade mode → each fills bots and resolves to a winner. On the Wane Line map, a collapse front advances on a fixed timeline, veined geo crumbles Pristine→Fallen through `MF_Wane`, and the fallen zone triggers hazard flee/damage. The full vertical slice (spine + FADE + HOLD + WANE LINE) reads in one place.


---

# PIPELINE

## The repeatable PIPELINE (edit → compile → play, and asset → engine)

**Engine:** `C:/UE_5.8`. **Project:** `C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject`. Both UBT targets are already built (DLL+exe dated 2026-06-25), so the first run needs no compile.

### A. The one-click run (what the user double-clicks every time)
Ship `HumanTestLaunch/WANEFALL_BETA.bat` as a **2-line build-then-launch** combo (clone of `WANEFALL_OPEN_V5_COMBAT_SANDBOX.bat`):

```bat
@echo off
"C:/UE_5.8/Engine/Build/BatchFiles/Build.bat" WanefallGreyboxEditor Win64 Development -Project="C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject" -WaitMutex
"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe" "C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject" /Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01 -game -windowed -ResX=1600 -ResY=900
```

Once `GlobalDefaultGameMode` is repointed to `AWanefallMatchGameMode`, opening that map boots straight into the filled match. From M4 on, change the boot map to `Wanefall_TheHold_01`.

> Build.bat is idempotent: if nothing changed it no-ops fast (or rely on in-editor Live Coding `Ctrl+Alt+F11`). Line 1 is the compile gate; line 2 is play. Edit → save → double-click = compile-if-stale → play.

### B. Headless compile-only (CI / fast gate without launching)
```bat
"C:/UE_5.8/Engine/Build/BatchFiles/Build.bat" WanefallGreyboxEditor Win64 Development -Project="C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject" -WaitMutex
```
Game target: same line with `WanefallGreybox` as the target name. New `.cpp` files need no `.Build.cs` edit — `Private/` and `Public/` are already globbed by the module.

### C. The in-engine proof gate (close the recon gap)
Recon confirmed the sim suites (`FWanefallModeSimHarness::RunArenaSuite` etc.) have **no in-engine caller**. As an early sub-task, add `FAutoConsoleCommand` registrations (one new `Private/WanefallProofConsole.cpp`, no header/Build.cs change) that invoke the existing harnesses and print `FWanefallModeResult` rows. Then every milestone is CI-provable headlessly:
```bat
"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" "...WanefallGreybox.uproject" -run=... -unattended -nosplash -nullrhi
```
or in-session: open console (`~`) and run `Wane.Proof.Arena`. Reuse the existing `Saved/ShowMeAI/.../run_regressions.ps1` watchdog pattern.

### D. The asset → engine loop (data-registry, never per-mesh code)
Assets are already imported (71 static meshes under `Content/Wanefall/Dimwit/`). The repeatable wiring is **one registry row per asset**, never a code edit per mesh:
- **Weapons:** add a `UWanefallWeaponDef` row (mesh hard-path + stats). `BuildVisibleWeapon` already swaps `WeaponBodyMesh->SetStaticMesh()` — it just reads the row.
- **Characters/bots:** add a `UWanefallCharacterDef` row (mesh hard-path + display name + species material). The director assigns it; `RefreshVisual` swaps the bot body mesh.
- Hard-pathing each mesh on a registry that the running game touches **keeps all 71 referenced**, so a future cook will not strip them.
- Naming convention to honor: `SM_Char_0N_<name>`, `SM_Wpn_Gun_NN_<name>`, `SM_Wpn_Melee_NN_<name>`, `SM_Wpn_Gren_NN_<name>`, `SM_Veh_NN_<name>`, each at `<Name>/StaticMeshes/<Name>.uasset`.

### E. Why NOT a cooked build (the explicit run-mechanism ruling)
The project drags heavy marketplace content (Paragon / Soul City / Cave); a clean cook+pak is slow and fragile, and the existing 342MB `WanefallGreybox.exe` is a Development Game exe that still reads loose Content (not redistributable). **Beta run = editor `-game -windowed` PIE via the one-click bat above.** A real cooked/`.pak` package is deferred as a separate late milestone only if external distribution to other machines is ever required.
