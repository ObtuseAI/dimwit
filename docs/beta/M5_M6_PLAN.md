# WANEFALL M5/M6 — DE-RISKED IMPLEMENTATION PLAN

_Recon + adversarial buildability gate (6 agents). Compile-first, runtime-spawn, no map/material authoring required for the logic._

## ADVERSARIAL VERDICT

compileOnlyViable: **true**

MOSTLY SOUND, with real hazards the spec hides. The core "compile-only, runtime-spawn, no map/material authoring" claim is GENUINELY VIABLE for M5 (CTF/Control/Hardpoint/S&D), M6.A (BR/Extraction routing on the existing shell maps), M6.B (vehicle mesh swap), and M6.C (moving WANE LINE). I verified the load-bearing facts directly: UWanefallMatchRuntimeComponent + AWanefallObjectiveVolume both live in WanefallObjectiveRuntime.h (NOT separately-named files — the spec's prose names are wrong but the RECON corrects this); the volume ctor at cpp:170-179 creates the BoxComponent Trigger and a default-subobject Runtime but NEVER calls SetGenerateOverlapEvents(true) (CONFIRMED at cpp:176-177 — only QueryOnly + ECR_Overlap), so the geometry path (DriveSpatialOccupancy/ContainsPoint, cpp:239-254) is correctly mandatory; AWanefallArena4v4GameState ticks (bCanEverTick=true, cpp:21) and its Tick (cpp:36-41) is the only live host; the director sets bCanEverTick=false (cpp:12); the GameMode has NO ObjectiveMode field (only DesiredBots, h:24) so that selector is real new code; component setup signatures match (SetupControl/Hardpoint/SearchDestroy/CTF + BR/Extraction); all 9 SM_Veh_* meshes, both Blender board/skimmer imports, and both BR/Extraction shell maps exist on disk; foundation_build.json confirms BR=13 starts / Extraction=2 starts. BUT the spec systematically understates several wiring problems (below) that WILL break a naive "compile-only" implementation at runtime or that require more new code than advertised. None force map/material authoring; all are code. The honest verdict: compile-only is achievable, but the spec's plumbing for (a) the GameState->director back-reference, (b) the parallel TDM round machine, (c) the vehicle Rider source, and (d) SearchDestroy/Hardpoint signature details is incomplete and must be fixed before code is written.

### MUST-FIX BEFORE BUILD
- GAMESTATE->DIRECTOR BACK-REF DOES NOT EXIST AND IS NOT SET BY FillTeams. The spec says 'give the GameState a TWeakObjectPtr<AWanefallMatchDirector> ObjectiveDirector set when FillTeams spawns/links it.' Reality: AWanefallMatchDirector::FillTeams (cpp:49-120) does NOT store or expose the spawned bots, does NOT take or hold a director self-ref, and crucially the GameState may be spawned by FillTeams AFTER the director already exists, OR pre-exist in the map — there is no code path today that links them. AWanefallArena4v4GameState.h has NO ObjectiveDirector member. AWanefallMatchGameMode::BeginPlay (cpp:33-36) spawns the director, calls FillTeams, then drops the Director pointer on the floor (local scope). So the wiring chain GameMode->Director->GameState->TickObjective must ALL be added, and the GameMode must retain the director and explicitly set the GameState's back-ref. Write this linkage explicitly; do not assume FillTeams does it.
- PARALLEL TDM ROUND MACHINE WILL FIGHT THE OBJECTIVE MATCH. AWanefallArena4v4GameState::Tick unconditionally runs AdvanceRound + TickBotRespawns (cpp:38-40) and the M1 path arms that TDM loop (FillTeams calls BeginCountdown / RefreshBotRoster, cpp:114-118). That TDM machine independently reaches its own ScoreLimit(25)/RoundDuration(300s) and calls EndRound->RoundEnding->RoundComplete, which ApplyRoundStateToBots() DEACTIVATES every bot (cpp:219-222) mid-objective. So an objective match hosted on the same GameState will have its bots frozen by the TDM round ending, AND bot respawns/eliminations are still driven by the TDM death-watch path. The spec's note 'HUD reads ObjectiveRuntime not the TDM scoreboard' addresses display only, not this lifecycle collision. Decide explicitly: either suppress/neutralize the TDM round loop when ObjectiveMode!=None, or host the objective tick on a separate spawned ticking manager actor instead of the TDM GameState.
- VEHICLE 'controller-free MountRiderForCapture' SILENTLY REQUIRES A RIDER CHARACTER THAT THE DIRECTOR DOES NOT HAVE. MountRiderForCapture (WaneBoardPawn.cpp:228-249) takes AWanefallPrototypeCharacter* Rider and early-returns if null — it mounts an EXISTING character, it does not create one. The spec's M6.B 'controller-free demo uses B->MountRiderForCapture(Rider)' never specifies where Rider comes from in a director-spawned arcade lane. The WideEstablishingCaptureDirector precedent spawns a rider character first. Also note: AWanefallScoutSkimmerPawn has NO controller-free mount equivalent (only EnterVehicle which Possesses only if the driver has a controller) — the RECON flags this and the spec's M6.B only adds a controller-free path for the board, not the skimmer. For a no-player vehicle demo you must spawn a character to mount, or use the player pawn; clarify this before claiming 'compile-only spawn + enter.'
- SearchDestroy SETUP SIGNATURE IS MISREPRESENTED. The component method is SetupSearchDestroy(int32 TeamSize) (h:46) as the spec says, BUT internally it calls SndState.Setup(4.f, 7.f, 40.f, 115.f, 4, TeamSize, true) (cpp:24) — the public single-arg call is fine, so the spec's 'SetupSearchDestroy(4)' compiles. HOWEVER the spec also says drive S&D via the geometry/occupancy path; S&D is NOT an occupancy mode. Scoring it needs OnPlantTick/OnDefuseTick/OnAttackerDown/OnDefenderDown (cpp:94-97), and the only volume role that feeds S&D is BombSite, which on overlap calls OnPlantTick(1e6f,true) to instantly complete the plant (cpp:224). DriveSpatialOccupancy only ever calls OnZoneOccupancyChanged (cpp:253->183) — it will NOT advance a SearchDestroy match. The spec's TickObjective gather+DriveSpatialOccupancy loop scores Control/Hardpoint only; S&D (and CTF relic/base, and Extraction enter/exit) need role-specific event calls the spec's geometry tick does not make. Build per-role drive logic, do not assume DriveSpatialOccupancy covers all four M5 modes.

### ISSUES
- **[high]** GameState has no back-reference to the director and FillTeams never establishes the link; the GameMode discards the spawned director pointer (local scope, cpp:33-36). The entire GameMode->Director->GameState->TickObjective chain is unwritten.
  - FIX: Add a UPROPERTY/TWeakObjectPtr<AWanefallMatchDirector> ObjectiveDirector member to AWanefallArena4v4GameState, retain the Director in GameMode::BeginPlay, and have the GameMode (or FillTeams) explicitly set GameState->ObjectiveDirector after the GameState exists (handle BOTH the pre-existing-in-map and director-spawned-it cases). Gate the GameState::Tick objective call on ObjectiveDirector.IsValid().
- **[high]** The TDM round state machine (AdvanceRound/TickBotRespawns) runs unconditionally in GameState::Tick and will EndRound -> Deactivate all bots mid-objective, and drives its own scoring/respawn in parallel to the objective match.
  - FIX: When ObjectiveMode != None, either (a) do not arm the TDM loop (skip BeginCountdown / hold RoundState), or (b) host TickObjective/TickLargeMode on a dedicated spawned ticking manager actor (bCanEverTick=true) rather than the TDM GameState, so the objective lifecycle is independent of the 25-kill/5-min TDM round.
- **[high]** DriveSpatialOccupancy only routes OnZoneOccupancyChanged, so it scores Control + Hardpoint but NOT CTF, SearchDestroy, or Extraction enter/exit. The spec's single geometry tick is presented as covering all M5 modes.
  - FIX: Implement per-VolumeRole drive logic in TickObjective: ControlZone/Hardpoint via DriveSpatialOccupancy; CtfRelic/CtfBase/BombSite/ExtractZone via ContainsPoint edge-detection that calls the role-specific handlers (OnRelicPickup/OnRelicCapture/OnPlantTick/OnEnterExtract/OnExitExtract). Mirror ApplyRole (cpp:215-232) for which handler each role needs.
- **[medium]** Vehicle arcade lane: MountRiderForCapture needs an existing AWanefallPrototypeCharacter Rider; the director has none, and the skimmer has no controller-free mount at all.
  - FIX: For the board: spawn (or reuse the player) a character to pass as Rider. For the skimmer: either restrict the demo to player-driven Interact()/EnterVehicle (needs a controller), or add a controller-free mount method to AWanefallScoutSkimmerPawn mirroring the board's. State which path the beta uses.
- **[medium]** Skimmer mesh-swap must target the CURRENTLY VISIBLE hull. BeginPlay picks BlenderShellMesh (bUsingBlenderShell true, ctor cpp:114) and hides BodyMesh/kitbash. A naive BodyMesh->SetStaticMesh is invisible. The spec's ApplyBetaVehicleMesh for the skimmer is correct (BlenderShellMesh when bUsingBlenderShell else BodyMesh) but the visibility branch runs in BeginPlay, so a runtime swap before/after BeginPlay must re-assert visibility.
  - FIX: In the skimmer setter, set the visible component AND ensure the chosen mesh component is unhidden (and the others hidden), independent of BeginPlay ordering; or call it post-BeginPlay. Add the bbox auto-scale (Mesh->GetBoundingBox()) like ApplyBetaBodyMesh since the 9 SM_Veh_* import scales are unverified.
- **[medium]** ObjectiveMode UPROPERTY is not actually settable via the ?game= URL (URL selects the class only). The spec leans on '?game= URL, no map edit' for per-mode selection.
  - FIX: Ship one tiny Blueprint GameMode subclass per mode with ObjectiveMode defaulted, OR add an InitGame/GetOptionValue('mode') parser to AWanefallMatchGameMode. The latter is ~10 lines of code and keeps it pure-C++/compile-only; the spec calls it 'nice-to-have' but without it the field cannot be chosen from a bare ?game= launch.
- **[low]** WANE LINE growth (not just advance) requires SetFieldRadius because FieldRadius/FieldVolume are private with no setter (h:57-58,70). The WarningRing DMI is created in BeginPlay specifically to avoid a CDO SavePackage crash (cpp:36-37,62-70).
  - FIX: If adding SetFieldRadius, write FieldRadius + FieldVolume->SetSphereRadius + rescale WarningRingMesh on the live instance ONLY; never recreate the DMI on the CDO. Moving-only (SetActorLocation lerp) needs no field API change and is safe.
- **[low]** Pre-existing fragility: AWanefallArena4v4GameState.cpp lines 194 and 237 contain stray backslash '\' where '//' was intended (also flagged for WaneBoardPawn.cpp:242 in RECON). These currently compile but any edit near them risks breakage.
  - FIX: Do not disturb these lines when adding objective wiring to GameState::Tick; if touching the function, fix the '\' to '//' deliberately.
- **[medium]** BR out-of-zone and elimination feeds are pure synthesis over dumb bots. RegisterDown() is a no-op (h:41-42); only RegisterElimination decrements AliveCount. Bot death must be mapped to OnBRElimination by the new manager (no existing hook fires it for BR).
  - FIX: In TickLargeMode, edge-detect bot defeat (IsDeadBot()/downed-component eliminated edge, as the TDM GameState already does at cpp:262) and call LargeRuntime->OnBRElimination() once per bot per life; feed OnBROutOfZone from a ring-center distance test each tick. Do not rely on OnBRDown for alive-count.
- **[low]** Extraction shell has only 2 PlayerStarts vs TeamSize 8; FillTeams' >=2-starts branch (cpp:81-87) clusters all 8 bots around the single non-player start, not the radial-scatter fallback (which only triggers when starts<2). So bots stack at one point.
  - FIX: Acceptable for a logic beta (AdjustIfPossibleButAlwaysSpawn prevents fails). If clean seating matters, add PlayerStarts to the shell (map tweak) or special-case low-start scatter in the director. Not a blocker.

## M5 SPEC

## M5 — Objective Modes (CTF / Control / Hardpoint / Search&Destroy), compile-FIRST, runtime-spawn

### Verified ground truth (all read directly)
- `AWanefallMatchGameMode::BeginPlay()` (`Private/WanefallMatchGameMode.cpp:15`) is hardcoded TDM: it finds/spawns `AWanefallArena4v4GameState`, spawns `AWanefallMatchDirector`, calls `Director->FillTeams(Arena, DesiredBots)`, then `ApplyBetaSelection()`. **No `?game=` parsing, no `InitGame`/`GetOptionValue` exists** — `?game=` is the engine URL feature, not project code.
- `AWanefallMatchGameMode : public AWanefallPrototypeGameMode` (`Public/WanefallMatchGameMode.h:13`).
- `UWanefallMatchRuntimeComponent` (`Public/WanefallObjectiveRuntime.h:35`) ctor sets `PrimaryComponentTick.bCanEverTick=false` — driven only by explicit `TickRuntime(Dt)` (confirmed `cpp:9-12,62`). Setup methods: `SetupCaptureTheFlag(int32)`, `SetupControl(int32 NumZones,int32 ScoreLimit)`, `SetupHardpoint(int32 NumHills,int32 ScoreLimit)`, `SetupSearchDestroy(int32 TeamSize)`. Presence handlers: `OnZoneOccupancyChanged(ZoneIndex,A,B)`, `OnHardpointOccupancyChanged(A,B)`. Queries: `IsMatchOver()`, `GetWinner()`, `GetActiveSummary()`, `GetActiveMode()`.
- `AWanefallObjectiveVolume` ctor (`cpp:170-179`): creates `Trigger` UBoxComponent (extent 300,300,200), sets `ECR_Overlap`, and `CreateDefaultSubobject<UWanefallMatchRuntimeComponent>("Runtime")`. **CONFIRMED GAP: it never calls `Trigger->SetGenerateOverlapEvents(true)`** — so live physics overlap will not fire on spawned volumes. Use the geometry path instead: `ContainsPoint(FVector)` and `DriveSpatialOccupancy(TeamAPositions, TeamBPositions)` (`h:134-136`, `cpp:247`), plus `SetZoneExtent(FVector)`.
- `AWanefallArena4v4GameState::Tick(float)` EXISTS (`Public/WanefallArena4v4GameState.h:65`) — this is the natural live tick host for `TickRuntime`.
- Bot enumeration proven: `TActorIterator<APlayerStart>` and `World->SpawnActor<AWanefallBotLiteEnemy>` in `FillTeams` (`Private/WanefallMatchDirector.cpp:59,70`). `AWanefallBotLiteEnemy::GetTeam()`/`SetTeam()` (`h:69-70`), `GetActorLocation()` is standard.

### Architecture decision (compile-only-now)
Do NOT add a new GameMode and do NOT rely on volume physics overlaps. Extend the EXISTING `AWanefallMatchDirector` to optionally drive an objective mode, and host the per-frame tick on the already-ticking `AWanefallArena4v4GameState`. Drive occupancy with the proven geometry path (`DriveSpatialOccupancy`/`ContainsPoint`), not collision events. This keeps every step a pure C++ compile gate on an existing map.

### Files touched
- `Public/WanefallMatchDirector.h` / `Private/WanefallMatchDirector.cpp` — add objective fields + setup + a tick-gather method.
- `Public/WanefallMatchGameMode.h` / `Private/WanefallMatchGameMode.cpp` — add an `EditAnywhere` mode selector + route it into the director.
- (optional) `Public/WanefallArena4v4GameState.h` / `.cpp` — hold a back-ref to the director and call its objective tick from the existing `Tick(float)`.

### Exact create-runtime-component sequence (in `AWanefallMatchDirector`)
1. Add header fields:
   - `UPROPERTY() UWanefallMatchRuntimeComponent* ObjectiveRuntime = nullptr;`
   - `UPROPERTY() TArray<AWanefallObjectiveVolume*> ObjectiveVolumes;`
   - `EWanefallRuntimeMode PendingMode = EWanefallRuntimeMode::None;` (enum from `WanefallObjectiveRuntime.h`).
   - new method `void SetupObjective(EWanefallRuntimeMode Mode);` and `void TickObjective(float Dt);`
2. In `SetupObjective`, create ONE shared runtime component so multi-volume modes share a scoreboard (recon SINGLE-MODE-PER-COMPONENT risk):
   - `ObjectiveRuntime = NewObject<UWanefallMatchRuntimeComponent>(this);`
   - `ObjectiveRuntime->RegisterComponent();` **(MANDATORY — a NewObject component after construction is inert without this; confirmed by recon ADD-AT-RUNTIME gotcha)**.
3. Configure by mode on the shared component:
   - CTF: `ObjectiveRuntime->SetupCaptureTheFlag(3);`
   - Control: `ObjectiveRuntime->SetupControl(/*NumZones*/3, 200);`
   - Hardpoint: `ObjectiveRuntime->SetupHardpoint(1, 250);`
   - Search&Destroy: `ObjectiveRuntime->SetupSearchDestroy(/*TeamSize*/4);`
   - then `ObjectiveRuntime->StartMatch();`

### Exact spawn-objective-volumes sequence
Derive anchors at runtime from existing `APlayerStart`s (no map authoring; mirror `FillTeams`):
1. Gather starts: `for (TActorIterator<APlayerStart> It(World); It; ++It) Starts.Add(*It);` Use `Starts[0]` origin as arena center, others as zone anchors. If too few, offset by fixed radial vectors from origin (same fallback math `FillTeams` uses at `cpp:90-92`).
2. For each needed zone (Control=3, Hardpoint=1, CTF base/relic = 2, S&D=1 bombsite):
   - `FActorSpawnParameters SP; SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;`
   - `AWanefallObjectiveVolume* V = World->SpawnActor<AWanefallObjectiveVolume>(AWanefallObjectiveVolume::StaticClass(), Anchor, FRotator::ZeroRotator, SP);`
   - `V->ZoneIndex = z;` `V->VolumeRole = EWanefallVolumeRole::ControlZone;` (or `Hardpoint`/`CtfBase`/`BombSite`).
   - **Re-point the volume at the SHARED runtime so all zones score into one match:** `V->Runtime = ObjectiveRuntime;` (overwrites the volume's own default-subobject Runtime — exactly what the recon prescribes for shared-scoreboard modes). Do NOT call `Setup*` on each volume's own Runtime.
   - `V->SetZoneExtent(FVector(600.f, 600.f, 300.f));`
   - `ObjectiveVolumes.Add(V);`

### Exact tick sequence (geometry path — bypasses the unwired overlap)
Host on `AWanefallArena4v4GameState::Tick(float Dt)` (already ticks): give the GameState a `TWeakObjectPtr<AWanefallMatchDirector> ObjectiveDirector` set when `FillTeams` spawns/links it, and each frame call `ObjectiveDirector->TickObjective(Dt);`. Inside `TickObjective`:
1. Gather live team positions (no helper exists — build it here, recon OCCUPANCY DATA SOURCE):
   - `TArray<FVector> TeamA, TeamB;`
   - `for (TActorIterator<AWanefallBotLiteEnemy> It(World); It; ++It){ const FVector L=It->GetActorLocation(); (It->GetTeam()==EWanefallTeam::TeamA?TeamA:TeamB).Add(L); }`
   - add the local player: `if (APawn* P = World->GetFirstPlayerController()->GetPawn()) TeamA.Add(P->GetActorLocation());`
2. Feed occupancy via geometry (NOT overlap): `for (AWanefallObjectiveVolume* V : ObjectiveVolumes) V->DriveSpatialOccupancy(TeamA, TeamB);` — this internally box-tests `ContainsPoint` and calls `Runtime->OnZoneOccupancyChanged(ZoneIndex,...)` on the shared component.
3. Advance the clock ONCE on the shared component: `if (ObjectiveRuntime && !ObjectiveRuntime->IsMatchOver()) ObjectiveRuntime->TickRuntime(Dt);`
4. On `ObjectiveRuntime->IsMatchOver()`, read `GetWinner()` / `GetActiveSummary()` for HUD/end.

### Mode selection (compile-only, no `?game=` parser needed yet)
Add `UPROPERTY(EditAnywhere) EWanefallRuntimeMode ObjectiveMode = EWanefallRuntimeMode::None;` to `AWanefallMatchGameMode`. In its `BeginPlay`, after spawning the director, `if (ObjectiveMode != None) Director->SetupObjective(ObjectiveMode);`. Selecting the GameMode via the map URL `?game=/Script/WanefallGreybox.WanefallMatchGameMode` already works; the per-mode field is set in a tiny GameMode Blueprint subclass or defaults — no map edit, no ini change. (A real `InitGame` `?mode=` string parser is a nice-to-have, not required to compile/ship.)

### What the user can test (PIE, existing arena map)
Launch the existing arena with `?game=WanefallMatchGameMode`, `ObjectiveMode=Control`. Expect: bots spawn (M1 path unchanged); 3 volumes spawn at player-start-derived anchors; standing bots/player inside a zone advance Control score via the geometry path; `GetActiveSummary()` shows scoring; match ends on score limit with `GetWinner()`. Swap `ObjectiveMode` to Hardpoint/CaptureTheFlag/SearchDestroy to exercise each machine.

### Compile-only-now vs deferred (M5)
- COMPILE-ONLY-NOW: all of the above (rule machines, volume actor, shared component, geometry occupancy, director+GameState wiring). No `.uasset`/`.umap` needed — the volume's collision box and Runtime are pure C++ ctor objects.
- DEFER (content authoring): (a) a VISIBLE mesh/decal on `AWanefallObjectiveVolume` (its Trigger is an invisible UBoxComponent — scoring works blind); (b) optional designer-authored precise flag/hill/bomb marker actors in a `.umap` if art-driven placement is later wanted (today anchors are derived from `APlayerStart`s). Neither blocks the beta.
- NOTE: HUD must read `ObjectiveRuntime->GetActiveSummary()/GetWinner()`, NOT the parallel `AWanefallArena4v4GameState` TDM scoreboard (two separate scoring systems — recon SCORING SCOPE).

## M6 SPEC

## M6 — Battle Royale / Extraction / Vehicles / WANE LINE, compile-FIRST

### Verified ground truth
- `FWanefallBattleRoyaleState` / `FWanefallExtractionState` (`Public/WanefallLargeModes.h:14,63`) are plain world-independent structs. Component handlers (`Public/WanefallObjectiveRuntime.h:48-49,63-64`): `SetupBattleRoyale(int32)`, `SetupExtraction()`, `OnBRElimination()`, `OnBRDown()`, `OnBROutOfZone(int32,float)`, `OnLootPickup(int32)`, `OnEnterExtract()`, `OnExitExtract()`, `OnExtractTick(float)`, `OnThreatDamage(float)`. `BrState.Setup(StartCombatants,4,5.f,10000.f,5.f)` and `ExtractionState.Setup(3,8.f,300.f,100.f)` confirmed in `cpp:30,33`. `RegisterDown()` is a documented no-op placeholder (`h:33,41` — only `RegisterElimination()` decrements `AliveCount`). BR has NO auto out-of-zone detection — `ApplyOutOfZone(NumOutside,Dt)` must be fed externally.
- `AWanefallMatchDirector::FillTeams(Arena, NumBots)` is mode-agnostic — `NumBots` is just a count; passing 24 or 8 works with no spawn-loop change (`cpp:49-120`).
- `AWanefallWaneHazardField` (`Public/WanefallWaneHazardField.h`): plain `AActor`, ticks, `IsPointInField(FVector)` reads LIVE `GetActorLocation()`+`FieldRadius` (`h:48`), `ApplyFieldEffectsToActor`, `GetFieldRadius()`. **CONFIRMED: `FieldRadius` and `FieldVolume` are PRIVATE with NO setter** (`h:57-58,69-70`) — the field can be MOVED freely but cannot GROW without a new 3-line `SetFieldRadius`.
- Vehicle: `AWanefallWaneBoardPawn` (`Public/WanefallWaneBoardPawn.h`): `BoardMesh` is a PRIVATE `UStaticMeshComponent*` (`h:75`), set in ctor via `ConstructorHelpers::FObjectFinder` to `/Game/Wanefall/Imported/Blender/SM_WaneBoard.SM_WaneBoard` (`cpp:39-45`). **No public mesh setter exists.** `MountRiderForCapture(Rider)` is controller-free (`h:54`). Runtime spawn PROVEN: `World->SpawnActor<AWanefallWaneBoardPawn>(...)` then `MountRiderForCapture` at `Private/WanefallWideEstablishingCaptureDirector.cpp:240,247`.
- `ApplyBetaBodyMesh(UStaticMesh*)` reference pattern on bots (`Public/WanefallBotLiteEnemy.h:73`) — `SetStaticMesh` + auto-normalize via bounding box.

### M6.A — BR / Extraction routing (COMPILE-ONLY-NOW on existing shell maps)
Extend the director, do NOT write a new GameMode class unless desired:
1. Add to `AWanefallMatchDirector`: `UPROPERTY() UWanefallMatchRuntimeComponent* LargeRuntime=nullptr;` + `void SetupLargeMode(EWanefallRuntimeMode Mode);` + `void TickLargeMode(float Dt);`
2. `SetupLargeMode`:
   - `LargeRuntime = NewObject<UWanefallMatchRuntimeComponent>(this); LargeRuntime->RegisterComponent();` (REQUIRED — same inert-component gotcha).
   - BR: `FillTeams(nullptr, 24); LargeRuntime->SetupBattleRoyale(24); LargeRuntime->StartMatch();`
   - Extraction: `FillTeams(nullptr, 8); LargeRuntime->SetupExtraction(); LargeRuntime->StartMatch();`
3. Per-frame driver (host on `AWanefallArena4v4GameState::Tick`, the only live tick, since `AWanefallMatchDirector` and the component are both `bCanEverTick=false`). In `TickLargeMode(Dt)`:
   - BR out-of-zone: spawn one `AWanefallWaneHazardField` (or reuse the collapse-ring center); each tick count combatants whose `GetActorLocation()` distance from ring center > current radius and call `LargeRuntime->OnBROutOfZone(NumOutside, Dt)`. Map bot death → `LargeRuntime->OnBRElimination()` (hook the existing bot defeat path / `IsDeadBot()`).
   - Extraction: feed `OnEnterExtract()`/`OnExtractTick(Dt)` from an `AWanefallObjectiveVolume` with `VolumeRole=ExtractZone` spawned at a player start (geometry `ContainsPoint`, NOT overlap); `OnLootPickup(Value)` from proximity to spawned loot anchors; `OnThreatDamage(Amount)` from bot hits.
   - Always: `if (!LargeRuntime->IsMatchOver()) LargeRuntime->TickRuntime(Dt);` then read `GetActiveSummary()`/`IsMatchOver()`.
4. Mode selection: add `ObjectiveMode` enum values `BattleRoyale`/`Extraction` to the `AWanefallMatchGameMode` selector (same field as M5); route to `SetupLargeMode`. Launch the EXISTING shell maps `Wanefall_BattleRoyale_Shell_01` / `Wanefall_Extraction_Shell_01` with `?game=WanefallMatchGameMode` to OVERRIDE their baked `AWanefallPrototypeGameMode` (which spawns no bots) — same URL technique as M1.

**COMPILE-ONLY-NOW:** rule routing, bot-fill to 24/8, ring/zone geometry feed, tick driver. The shell maps already exist (floor/walls/lighting/PlayerStarts, per `foundation_build.json` BR=13 starts, Extraction=2). **DEFER (content):** nothing strictly; optional extra `PlayerStart`s in the Extraction shell (only 2 vs TeamSize 8 — director scatter fallback covers it but seats cluster). **Known logic gaps (no asset, flag in code):** `RegisterDown()` no-op (use `RegisterElimination()` for alive-count); placed `AWanefallBattleRoyaleZone`/`AWanefallExtractZone` map actors are decoupled greybox markers (`*_ForProof` setters) NOT wired to the structs — drive the structs from director geometry, ignore the markers. The networked `AWanefallNetworkExtractionGameMode` is a SEPARATE self-flagged-incomplete loop — do not conflate.

### M6.B — Vehicle mesh swap (COMPILE-ONLY-NOW, one tiny additive method)
The ONLY gap is the missing public setter (mesh component is private). Add, mirroring `ApplyBetaBodyMesh`:
- On `AWanefallWaneBoardPawn`: `void ApplyBetaVehicleMesh(UStaticMesh* M){ if(M && BoardMesh){ BoardMesh->SetStaticMesh(M); /* optional: auto-scale to CollisionRoot extent via M->GetBoundingBox(), like the bot path */ } }`
- On `AWanefallScoutSkimmerPawn`: set the CURRENTLY-VISIBLE component — `BlenderShellMesh->SetStaticMesh(M)` when `bUsingBlenderShell`, else `BodyMesh->SetStaticMesh(M)` (recon: BeginPlay hides the non-chosen part, so a naive `BodyMesh` set may be invisible).
Then in the director (precedent at `WideEstablishingCaptureDirector.cpp:240`):
- `FActorSpawnParameters SP; SP.SpawnCollisionHandlingOverride=AdjustIfPossibleButAlwaysSpawn;`
- `AWanefallWaneBoardPawn* B = World->SpawnActor<AWanefallWaneBoardPawn>(AWanefallWaneBoardPawn::StaticClass(), Loc, Rot, SP);`
- `UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Wanefall/Dimwit/Vehicles/SM_Veh_09_obsidian_maw/StaticMeshes/SM_Veh_09_obsidian_maw.SM_Veh_09_obsidian_maw"));` (same `LoadObject` pattern as `LoadSoldierMesh`); `if(M) B->ApplyBetaVehicleMesh(M);`
- Enter: player path auto-discovers nearest skimmer + `Interact()`→`EnterVehicle` (possesses if controller); controller-free demo uses `B->MountRiderForCapture(Rider)`.
**COMPILE-ONLY-NOW:** spawn + `LoadObject(SM_Veh_*)` + `SetStaticMesh` (meshes exist on disk). **DEFER/none-required:** a dedicated vehicle-arena `.umap` (existing map hosts it). **Risk:** the 9 `SM_Veh_*` meshes have unverified import scale — add the bounding-box auto-scale in the setter (code, not content). Vehicles do NOT replicate — single-player arcade lane only, not the networked TDM.

### M6.C — Minimal compile-only WANE LINE (moving hazard field, existing map)
Net-new `AWaneLineDirector : public AActor` (`PrimaryActorTick.bCanEverTick=true`), spawned from `AWanefallMatchGameMode::BeginPlay` exactly like the M1 director:
1. BeginPlay: `Field = World->SpawnActor<AWanefallWaneHazardField>(AWanefallWaneHazardField::StaticClass(), StartLoc, Rot, SP);` (plain AActor, default ctor — same SpawnActor pattern). Derive `StartLoc`/`EndLoc` from arena `APlayerStart` extents.
2. Tick: `Alpha = FMath::Clamp(Elapsed/CollapseSeconds,0,1); Field->SetActorLocation(FMath::Lerp(StartLoc,EndLoc,Alpha)); Elapsed += Dt;` — `IsPointInField` reads `GetActorLocation()` LIVE (`h:48`), so MOVING the front needs ZERO field API change. All consumers (HUD warning, character slow, skimmer `bWaneDisrupted`, bot-lite) already poll every `AWanefallWaneHazardField` via `TActorIterator` and apply damage/slow automatically — the damage/repel half is FREE.
3. Expose `FString GetCollapsePhaseText() const` (from `Elapsed/CollapseSeconds`) for the HUD, reusing the existing field-warning `DrawWanefallLine` path. Deterministic collapse math reference: reuse `FWanefallBattleRoyaleState` `StartRadius→MinRadius` / `ShrinkFraction()`.
4. Launch: add `Director2 = World->SpawnActor<AWaneLineDirector>();` (~6 lines) in `AWanefallMatchGameMode::BeginPlay`, or a dedicated mode value — selectable via the same `?game=` URL, no map edit, no ini.

**COMPILE-ONLY-NOW:** moving field + auto-consumed damage/slow + phase HUD text on ANY existing arena map. **OPTIONAL tiny code (not content):** add `void AWanefallWaneHazardField::SetFieldRadius(float r){ FieldRadius=r; FieldVolume->SetSphereRadius(r); /* rescale WarningRingMesh on the INSTANCE only, never the CDO DMI */ }` so the front can GROW as well as ADVANCE (else spawn successive larger fields). **DEFER (genuine content):** a bespoke `MF_Wane` dissolve-edge SEAM shader, a purpose-built two-state collapse `.umap`, or a new collapse-wall Niagara — all polish, none blocking. NOTE a runtime Pristine→Fallen MATERIAL flip is ALSO compile-only using existing assets via the `AWanefallMatrixThemeController::ApplyTheme` precedent (`LoadObject` existing `M_WaneGridFloorDark`/`Light` + `SetMaterial` on tag-found `AStaticMeshActor`s) — so a v2 "flip floor tiles behind the front" is achievable without new authoring. **Risks:** moving-only satisfies "advancing front"; growth needs the 3-line setter; the WarningRing DMI must only be recreated on the live instance (CDO `SavePackage` constraint, `cpp:~36`); damage only lands on actors with `UWanefallPrototypeHealthComponent` (player + `AWanefallBotLiteEnemy` already have it); "repel" today = slow, not impulse (true knockback is deferred new code).

## COMPILE-ONLY TASK LIST
1. M5: add ObjectiveRuntime/ObjectiveVolumes fields + SetupObjective(EWanefallRuntimeMode) to AWanefallMatchDirector; NewObject<UWanefallMatchRuntimeComponent>(this) + RegisterComponent() (mandatory) as ONE shared component
2. M5: call SetupCaptureTheFlag(3) / SetupControl(3,200) / SetupHardpoint(1,250) / SetupSearchDestroy(4) then StartMatch() on the shared component
3. M5: runtime World->SpawnActor<AWanefallObjectiveVolume> at APlayerStart-derived anchors, set ZoneIndex/VolumeRole/SetZoneExtent, and re-point each V->Runtime at the shared component
4. M5: build per-frame TickObjective in director that gathers TActorIterator<AWanefallBotLiteEnemy> + player positions by team, calls V->DriveSpatialOccupancy(TeamA,TeamB) (geometry path, NOT physics overlap), then ObjectiveRuntime->TickRuntime(Dt)
5. M5/M6: host the TickRuntime/TickObjective/TickLargeMode call inside AWanefallArena4v4GameState::Tick(float) (only live tick; director+component are bCanEverTick=false)
6. M5/M6: add EWanefallRuntimeMode ObjectiveMode EditAnywhere selector to AWanefallMatchGameMode and route it to the director in BeginPlay (selectable via existing ?game= URL)
7. M6: add SetupLargeMode + TickLargeMode to director; FillTeams(nullptr,24/8) + SetupBattleRoyale(24)/SetupExtraction() + StartMatch() on a registered shared component; launch existing BR/Extraction shell maps with ?game= override
8. M6: feed OnBROutOfZone(NumOutside,Dt) from a ring-center distance test and OnBRElimination() from bot death; feed OnEnterExtract/OnExtractTick/OnLootPickup/OnThreatDamage from a spawned ExtractZone volume + loot anchors (geometry, not overlap)
9. M6: add public ApplyBetaVehicleMesh(UStaticMesh*) to AWanefallWaneBoardPawn (BoardMesh->SetStaticMesh, optional bbox auto-scale) and to AWanefallScoutSkimmerPawn (set the currently-visible BlenderShellMesh/BodyMesh)
10. M6: director spawns AWanefallWaneBoardPawn via SpawnActor + LoadObject<UStaticMesh> of a /Game/Wanefall/Dimwit/Vehicles/SM_Veh_* path + ApplyBetaVehicleMesh; enter via Interact()/EnterVehicle or controller-free MountRiderForCapture
11. M6: net-new AWaneLineDirector (bCanEverTick=true) spawns one AWanefallWaneHazardField and lerps Field->SetActorLocation(Start->End) over CollapseSeconds (IsPointInField reads live location; consumers auto-apply damage/slow)
12. M6: AWaneLineDirector::GetCollapsePhaseText() for HUD; spawn it from AWanefallMatchGameMode::BeginPlay (~6 lines)
13. M6 optional: add 3-line AWanefallWaneHazardField::SetFieldRadius(float) (writes FieldRadius + FieldVolume->SetSphereRadius + instance-only ring rescale) to let the front GROW as well as advance

## DEFERRED (CONTENT AUTHORING)
- DEFER: a visible mesh/decal on AWanefallObjectiveVolume so players SEE the flag/zone/hill/bomb (its Trigger is an invisible UBoxComponent; scoring works blind without it)
- DEFER: optional designer-authored precise flag/hill/bomb marker actors in a .umap if art-driven placement is later wanted (runtime APlayerStart-derived anchors suffice for beta)
- DEFER: add more PlayerStarts to Wanefall_Extraction_Shell_01 (only 2 vs advertised TeamSize 8) for clean bot seating — small map tweak, not a blocker (director scatter fallback covers it)
- DEFER: a dedicated vehicle-arena .umap with bespoke geometry (existing maps host the runtime-spawned vehicle lane)
- DEFER: a bespoke MF_Wane master/dissolve-edge SEAM shader for a glowing collapse boundary at the WANE LINE front (pure polish)
- DEFER: a purpose-built collapse .umap authored in two geometry states (pristine vs fallen) for a true world-converting WANE LINE
- DEFER: any new Niagara .uasset built specifically for the collapse wall (existing NS_Player_Electricity_Looping already used by the hazard field)
- DEFER (optional, not blocking): verify native import scale/origin of the 9 SM_Veh_* Dimwit vehicle meshes; mitigated in code via bounding-box auto-scale in the new setter

## RECON DETAIL (per area)

### objective  (runtimeSpawnable: true)
see above

Key APIs:
- `// NOTE: prompt's class/file names differ from reality. The component is UWanefallMatchRuntimeComponent, the volume is AWanefallObjectiveVolume, BOTH declared in WanefallObjectiveRuntime.h (NOT a file named WanefallMatchRuntimeComponent / WanefallObjectiveVolume).`
- `// ---- UWanefallMatchRuntimeComponent (UActorComponent, ClassGroup=(WANEFALL), BlueprintSpawnableComponent) ----`
- `UWanefallMatchRuntimeComponent::UWanefallMatchRuntimeComponent(); // PrimaryComponentTick.bCanEverTick = false (driven explicitly)`
- `void UWanefallMatchRuntimeComponent::SetupCaptureTheFlag(int32 CaptureLimit); // -> CaptureState.Setup(CaptureLimit, 10.f, 600.f)`
- `void UWanefallMatchRuntimeComponent::SetupControl(int32 NumZones, int32 ScoreLimit); // inits ZoneA/ZoneB arrays to NumZones`
- `void UWanefallMatchRuntimeComponent::SetupHardpoint(int32 NumHills, int32 ScoreLimit);`
- `void UWanefallMatchRuntimeComponent::SetupSearchDestroy(int32 TeamSize);`
- `void UWanefallMatchRuntimeComponent::SetupDeathmatch(int32 Sides, bool bTeam, int32 ScoreLimit);`
- `void UWanefallMatchRuntimeComponent::StartMatch(); // dispatches Start()/StartMatch() on the ActiveMode machine`
- `void UWanefallMatchRuntimeComponent::TickRuntime(float Dt); // applies stored Control/Hardpoint presence then AdvanceTime(Dt)`
- `void UWanefallMatchRuntimeComponent::OnZoneOccupancyChanged(int32 ZoneIndex, int32 TeamACount, int32 TeamBCount);`
- `void UWanefallMatchRuntimeComponent::OnHardpointOccupancyChanged(int32 TeamACount, int32 TeamBCount);`
- `void UWanefallMatchRuntimeComponent::OnRelicPickup(int32 Team); OnRelicCapture(int32 Team); OnRelicCarrierDown(int32 Team); OnRelicReturn(int32 HomeTeam);`
- `void UWanefallMatchRuntimeComponent::OnPlantTick(float Dt, bool bAttackerOnSite); OnDefuseTick(float Dt, bool bDefenderOnSite); OnAttackerDown(); OnDefenderDown();`
- `bool UWanefallMatchRuntimeComponent::IsMatchOver() const; int32 GetWinner() const; FString GetActiveSummary() const; EWanefallRuntimeMode GetActiveMode() const;`
- `// ---- AWanefallObjectiveVolume (AActor) ----`
- `AWanefallObjectiveVolume::AWanefallObjectiveVolume(); // ctor creates UBoxComponent* Trigger (RootComponent), default extent (300,300,200), QueryOnly + ECR_Overlap, AND CreateDefaultSubobject<UWanefallMatchRuntimeComponent>("Runtime") as a default subobject (so each volume OWNS its own Runtime by default)`
- `UPROPERTY(EditAnywhere) int32 AWanefallObjectiveVolume::ZoneIndex = 0;`
- `UPROPERTY(EditAnywhere) EWanefallVolumeRole AWanefallObjectiveVolume::VolumeRole = EWanefallVolumeRole::ControlZone; // {ControlZone,Hardpoint,CtfRelic,CtfBase,BombSite,ExtractZone,RaceCheckpoint,RollCheckpoint,FallBoundary,CollapseRing}`
- `UPROPERTY() UWanefallMatchRuntimeComponent* AWanefallObjectiveVolume::Runtime = nullptr; // points at the owned default-subobject Runtime`
- `virtual void AWanefallObjectiveVolume::NotifyActorBeginOverlap(AActor* Other) override; // casts to AWanefallProofPawn -> ProofPawnEnter(PP->ProofId, PP->Team), else ProofPawnEnter(UniqueID, team 0)`
- `virtual void AWanefallObjectiveVolume::NotifyActorEndOverlap(AActor* Other) override;`
- `void AWanefallObjectiveVolume::ProofPawnEnter(int32 PawnId, int32 Team); void ProofPawnExit(int32 PawnId, int32 Team);`
- `void AWanefallObjectiveVolume::SetZoneExtent(const FVector& Extent); // -> Trigger->SetBoxExtent(Extent)`
- `bool AWanefallObjectiveVolume::ContainsPoint(const FVector& WorldPoint) const; // real AABB built from GetActorLocation()+scaled box extent`
- `void AWanefallObjectiveVolume::DriveSpatialOccupancy(const TArray<FVector>& TeamAPositions, const TArray<FVector>& TeamBPositions); // box-containment -> PushOccupancy() -> Runtime->OnZoneOccupancyChanged(ZoneIndex,...)`
- `// ---- proven runtime-spawn precedent (M1) ----`
- `UWorld::SpawnActor<AWanefallMatchDirector>(); // AWanefallMatchGameMode::BeginPlay()`
- `World->SpawnActor<AWanefallBotLiteEnemy>(AWanefallBotLiteEnemy::StaticClass(), Loc, Rot, SpawnParams); // FActorSpawnParameters.SpawnCollisionHandlingOverride = AdjustIfPossibleButAlwaysSpawn`
- `World->SpawnActor<AWanefallArena4v4GameState>(); // director spawns the game-state actor at runtime when map lacks one`
- `void AWanefallMatchDirector::FillTeams(AWanefallArena4v4GameState* InArena, int32 NumBots); // iterates TActorIterator<APlayerStart>`
- `EWanefallTeam AWanefallBotLiteEnemy::GetTeam() const; void SetTeam(EWanefallTeam); // bot team source for objective occupancy`
- `AWanefallProofPawn: UPROPERTY int32 Team; int32 ProofId; ctor sets USphereComponent OverlapSphere with SetGenerateOverlapEvents(true)`

### large  (runtimeSpawnable: true)
YES, the BR/Extraction RULE LOGIC + bots can run fully at runtime with NO map edit, because the shell maps already exist and are playable. Three independent facts establish this:

(1) RULE MACHINES ARE WORLD-INDEPENDENT. FWanefallBattleRoyaleState and FWanefallExtractionState (WanefallLargeModes.h/.cpp) are plain structs with no UWorld/actor dependency. Ring-shrink, out-of-zone damage accrual, last-standing resolution, extract insert/loot/extract-progress/KIA/timeout are ALL pure state transitions driven by AdvanceTime(Dt) + event calls. They are already exercised live through UWanefallMatchRuntimeComponent (a BlueprintSpawnableComponent) whose handlers OnBROutOfZone/OnBRElimination/OnLootPickup/OnEnterExtract/OnExtractTick/OnThreatDamage mutate them. A component can be NewObject/AddComponent'd onto any spawned actor at runtime, configured via SetupBattleRoyale(24)/SetupExtraction(), and stepped each frame. No .uasset needed for the rules.

(2) BOT-FILL TO ADVERTISED COUNTS WORKS VIA THE M1 PATH, MODE-AGNOSTICALLY. AWanefallMatchDirector::FillTeams(Arena, NumBots) is generic: it SpawnActor's AWanefallBotLiteEnemy at every APlayerStart (TActorIterator), with a radial scatter fallback when starts are insufficient, then assigns Dimwit meshes. NumBots is just a count, so passing 24 (BR) or 8 (Extraction) spawns that many bots with no code change to the spawn loop. The bots are dumb pawns (SetTeam + ApplyBetaBodyMesh only), so for BR you would additionally need to map bot deaths to BrState.RegisterElimination() and a spatial out-of-zone test to ApplyOutOfZone() — AWanefallObjectiveVolume already provides ContainsPoint()/DriveSpatialOccupancy() geometry to compute who is outside the collapse ring from real world positions.

(3) SHELL MAPS ARE ALREADY PLAYABLE — authoring is DONE, not pending. Wanefall_BattleRoyale_Shell_01.umap and Wanefall_Extraction_Shell_01.umap exist on disk and were built by WanefallFoundationBuildCommandlet, which spawns: a collision FloorPlate + 4 perimeter Walls (BlockAll), BrightLighting (directional+sky+postprocess), 2 proof cameras, PlayerStarts, role actors (AWanefallBattleRoyaleZone collapse-ring marker / AWanefallExtractZone + AWanefallExtractionGate + 4 LootCache plates + a threat bot), and crucially WorldSettings->DefaultGameMode = AWanefallPrototypeGameMode + a PlayerStart_Main. foundation_build.json confirms saved=true with player_starts: BR=13, Extraction=2; both have floor+walls. So a human can already PIE these maps and walk around.

HOW TO LIGHT IT UP AT RUNTIME (no editor): launch the shell map with ?game= pointing at a large-mode GameMode (same URL technique M1 uses to override the map's baked AWanefallPrototypeGameMode). In that GameMode's BeginPlay: (a) SpawnActor an AWanefallMatchDirector and call FillTeams(nullptr, 24 or 8); (b) NewObject a UWanefallMatchRuntimeComponent (or attach to a spawned manager actor), call SetupBattleRoyale(24)/SetupExtraction() + StartMatch(); (c) drive it from a ticking actor (the component itself is bCanEverTick=false and is stepped only by explicit TickRuntime(Dt)) — spawn a lightweight manager actor with bCanEverTick=true that each frame calls TickRuntime(DeltaSeconds), feeds OnBROutOfZone from a ring-vs-pawn-position test, and calls OnBRElimination on bot death (BR) / OnEnterExtract+OnExtractTick from the AWanefallExtractZone overlap and OnThreatDamage from hits (Extraction).

Key APIs:
- `FWanefallBattleRoyaleState::Setup(int32 InStartCombatants, int32 InShrinkStages, float InStageSeconds, float InStartRadius, float InOutOfZoneDps)`
- `FWanefallBattleRoyaleState::Start()`
- `FWanefallBattleRoyaleState::RegisterDown()`
- `FWanefallBattleRoyaleState::RegisterElimination()`
- `FWanefallBattleRoyaleState::ApplyOutOfZone(int32 NumOutside, float Dt)`
- `FWanefallBattleRoyaleState::AdvanceTime(float Dt)`
- `FWanefallBattleRoyaleState::IsLive() const`
- `FWanefallBattleRoyaleState::IsOver() const`
- `FWanefallBattleRoyaleState::ShrinkFraction() const`
- `FWanefallExtractionState::Setup(int32 InLootGoal, float InExtractSeconds, float InRaidSeconds, float InMaxHealth)`
- `FWanefallExtractionState::Start()`
- `FWanefallExtractionState::PickUpLoot(int32 Value)`
- `FWanefallExtractionState::EnterExtractZone()`
- `FWanefallExtractionState::ExitExtractZone()`
- `FWanefallExtractionState::TickExtract(float Dt)`
- `FWanefallExtractionState::ApplyThreatDamage(float Amount)`
- `FWanefallExtractionState::AdvanceTime(float Dt)`
- `FWanefallExtractionState::IsSuccess() const`
- `UWanefallMatchRuntimeComponent::SetupBattleRoyale(int32 StartCombatants)`
- `UWanefallMatchRuntimeComponent::SetupExtraction()`
- `UWanefallMatchRuntimeComponent::StartMatch()`
- `UWanefallMatchRuntimeComponent::TickRuntime(float Dt)`
- `UWanefallMatchRuntimeComponent::OnBRElimination()`
- `UWanefallMatchRuntimeComponent::OnBRDown()`
- `UWanefallMatchRuntimeComponent::OnBROutOfZone(int32 NumOutside, float Dt)`
- `UWanefallMatchRuntimeComponent::OnLootPickup(int32 Value)`
- `UWanefallMatchRuntimeComponent::OnEnterExtract()`
- `UWanefallMatchRuntimeComponent::OnExitExtract()`
- `UWanefallMatchRuntimeComponent::OnExtractTick(float Dt)`
- `UWanefallMatchRuntimeComponent::OnThreatDamage(float Amount)`
- `UWanefallMatchRuntimeComponent::IsMatchOver() const`
- `UWanefallMatchRuntimeComponent::GetActiveSummary() const`
- `AWanefallObjectiveVolume::ProofPawnEnter(int32 PawnId, int32 Team)`
- `AWanefallObjectiveVolume::DriveSpatialOccupancy(const TArray<FVector>& TeamAPositions, const TArray<FVector>& TeamBPositions)`
- `AWanefallObjectiveVolume::ContainsPoint(const FVector& WorldPoint) const`
- `AWanefallMatchDirector::FillTeams(AWanefallArena4v4GameState* InArena, int32 NumBots)`
- `AWanefallBotLiteEnemy::SetTeam(EWanefallTeam InTeam)`
- `AWanefallBotLiteEnemy::ApplyBetaBodyMesh(UStaticMesh* Mesh)`

### vehicles  (runtimeSpawnable: true)
YES — runtime spawn + entry of a vehicle is already PROVEN in the shipping code, and a runtime mesh-swap is a small additive change. (1) SPAWN: WanefallWideEstablishingCaptureDirector.cpp:240 already does World->SpawnActor<AWanefallWaneBoardPawn>(AWanefallWaneBoardPawn::StaticClass(), BoardLoc, Rot, SP) at BeginPlay and immediately spawns + mounts a rider (lines 240-248). The same SpawnActor pattern the M1 MatchDirector uses for bots applies 1:1 to AWanefallScoutSkimmerPawn / AWanefallWaneBoardPawn — no map placement needed. A beta arcade lane can SpawnActor a skimmer/board at a PlayerStart or fixed transform at BeginPlay. (2) ENTER: two proven paths exist. Player-driven: the character auto-discovers the nearest skimmer via TActorIterator<AWanefallScoutSkimmerPawn> (WanefallPrototypeCharacter.cpp:358) and Interact() (line 1430) calls Skimmer->EnterVehicle(this) which possesses the pawn IF the driver has a controller — so a runtime-spawned skimmer is enterable with zero map edits. Controller-free mount: AWanefallWaneBoardPawn::MountRiderForCapture() (WaneBoardPawn.cpp:228) attaches+stands a rider without needing a controller (and EnterBoard at line ~200 follows with C->Possess(this) when a controller exists). (3) MESH SWAP to a Dimwit SM_Veh_ mesh: the meshes EXIST on disk at C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/Content/Wanefall/Dimwit/Vehicles/SM_Veh_0N_*/StaticMeshes/SM_Veh_0N_*.uasset (all 9 confirmed: SM_Veh_01_waneboard .. SM_Veh_09_obsidian_maw, each with StaticMeshes/, Materials/pbr_material_*, Textures/). Load at runtime exactly like MatchDirector::LoadSoldierMesh: UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT(\"/Game/Wanefall/Dimwit/Vehicles/SM_Veh_09_obsidian_maw/StaticMeshes/SM_Veh_09_obsidian_maw.SM_Veh_09_obsidian_maw\")). THE GAP: neither pawn currently exposes a public settable mesh slot like the bots' ApplyBetaBodyMesh. The visible hull is bound in the CONSTRUCTOR via ConstructorHelpers::FObjectFinder (Skimmer BodyMesh ctor lines 65-82 + BlenderShellMesh line 107-114; Board BoardMesh line 40-45) and the components are PRIVATE. So to swap at runtime you must ADD ONE small method mirroring ApplyBetaBodyMesh — e.g. AWanefallWaneBoardPawn::ApplyBetaVehicleMesh(UStaticMesh*) doing BoardMesh->SetStaticMesh(M) (and Skimmer: set BlenderShellMesh->SetStaticMesh + flip bUsingBlenderShell so the BeginPlay hide-the-kitbash branch runs). The component is a plain UStaticMeshComponent (Board: BoardMesh; Skimmer: BodyMesh or the preferred BlenderShellMesh), so SetStaticMesh() works exactly as on the bot's root component — no new map, no commandlet, no .uasset authoring. EXACT component+method to drive the swap: WaneBoard -> BoardMesh->SetStaticMesh(M); Skimmer -> BlenderShellMesh->SetStaticMesh(M) (preferred visible hull) or BodyMesh->SetStaticMesh(M), guarded by the existing bUsingBlenderShell / bUsingRealHull visibility branches in BeginPlay.

Key APIs:
- `AWanefallScoutSkimmerPawn::AWanefallScoutSkimmerPawn() — sets BodyMesh/BlenderShellMesh via static ConstructorHelpers::FObjectFinder<UStaticMesh> in ctor; NO settable public mesh slot`
- `void AWanefallScoutSkimmerPawn::EnterVehicle(AWanefallPrototypeCharacter* Driver) — hides+disables driver, possesses pawn if driver has a controller`
- `void AWanefallScoutSkimmerPawn::ExitVehicle()`
- `bool AWanefallScoutSkimmerPawn::IsOccupied() const`
- `int32 AWanefallScoutSkimmerPawn::GetVisibleMeshPartCount() const`
- `AWanefallWaneBoardPawn::AWanefallWaneBoardPawn() — sets BoardMesh via static ConstructorHelpers::FObjectFinder<UStaticMesh>(TEXT("/Game/Wanefall/Imported/Blender/SM_WaneBoard.SM_WaneBoard")); NO public mesh setter`
- `void AWanefallWaneBoardPawn::EnterBoard(AWanefallPrototypeCharacter* Rider)`
- `void AWanefallWaneBoardPawn::MountRiderForCapture(AWanefallPrototypeCharacter* Rider) — controller-FREE mount (attaches+stands rider, no Possess inside)`
- `void AWanefallWaneBoardPawn::ExitBoard()`
- `void AWanefallWaneBoardPawn::SnapToLowHover()`
- `void AWanefallBotLiteEnemy::ApplyBetaBodyMesh(UStaticMesh* Mesh) — REFERENCE PATTERN: Body->SetStaticMesh(Mesh) on root UStaticMeshComponent, then auto-normalize scale via Mesh->GetBoundingBox()`
- `void AWanefallPrototypeCharacter::Interact() — if CurrentNearbySkimmer && !IsOccupied -> Skimmer->EnterVehicle(this)`
- `World->SpawnActor<AWanefallWaneBoardPawn>(AWanefallWaneBoardPawn::StaticClass(), Loc, Rot, SP) — PROVEN runtime vehicle spawn (WanefallWideEstablishingCaptureDirector.cpp:240)`
- `UStaticMesh* LoadObject<UStaticMesh>(nullptr, Path) — runtime mesh load pattern used by MatchDirector::LoadSoldierMesh`

### collapse  (runtimeSpawnable: true)
YES — a compile-only WANE LINE runs on an existing arena map with NO map edit and NO new .uasset, via a new AWaneLineDirector spawned at GameMode BeginPlay exactly like M1's AWanefallMatchDirector. Mechanism is already proven end-to-end: (1) SPAWN — the M1 director already does World->SpawnActor<AWanefallBotLiteEnemy>(...) and World->SpawnActor<AWanefallArena4v4GameState>() at runtime; AWanefallWaneHazardField is a plain AActor with a default ctor, so World->SpawnActor<AWanefallWaneHazardField>(Class, Loc, Rot, SpawnParams) works the same way. (2) CONSUMPTION IS FREE — every hazard consumer polls TActorIterator<AWanefallWaneHazardField> + IsPointInField()/IsPulseActive() each tick rather than holding a hand-wired ref: HUD warning (WanefallPrototypeHUD.cpp ~455-463 draws '>> WANE FIELD - taking damage <<' / '>> WANE PULSE - GET OUT <<'), character slow+HUD-cache (WanefallPrototypeCharacter.cpp ~771-781), skimmer disruption/repel (WanefallScoutSkimmerPawn.cpp ~388-397 sets bWaneDisrupted), bot-lite (WanefallBotLiteEnemy.cpp ~164), and the wane target (WanefallCoreArenaWaneTarget.cpp ~66). So ANY runtime-spawned field is automatically damaging+slowing+disrupting+HUD-warned with zero extra wiring — the damage/repel half of the IP crown jewel already exists. (3) ADVANCE ON A TIMELINE — the director owns the field ptr and each Tick lerps its position from a Pristine origin toward a Fallen origin over a fixed CollapseSeconds (Field->SetActorLocation(FMath::Lerp(Start,End,Alpha))); IsPointInField reads GetActorLocation() live (line 83), so MOVING the front needs no field API change at all. (4) GROW — to expand the front's radius over time you need one tiny API add to the field (e.g. void SetFieldRadius(float) that writes FieldRadius and calls FieldVolume->SetSphereRadius + rescales WarningRingMesh), because FieldRadius/FieldVolume are private with no setter; alternatively spawn a sequence of progressively larger fields with no field edit at all. Either way it is compile-only, no content. (5) PHASE/HUD — the director can read its own elapsed/CollapseSeconds and expose a GetCollapsePhaseText() that the HUD prints next to the existing field warning, reusing the same DrawWanefallLine path the WaneTrial/BR collapse banners already use (WanefallPrototypeHUD.cpp ~262-265, IsCollapseImminent pattern). (6) LAUNCH — identical to M1: select the new GameMode (or extend AWanefallMatchGameMode::BeginPlay to also SpawnActor the AWaneLineDirector) via the map URL ?game= option; no DefaultEngine.ini change, no map edit. RECOMMENDED MINIMAL: new AWaneLineDirector (Tick-driven, owns one spawned AWanefallWaneHazardField, lerps its location across the arena over CollapseSeconds, exposes phase text) + one optional 3-line SetFieldRadius setter on the field if growth (not just advance) is wanted + ~6 lines in the GameMode BeginPlay to spawn it. The deterministic collapse-clock math already exists as a reference in FWanefallBattleRoyaleState (WanefallLargeModes.h/.cpp: StartRadius->MinRadius linear collapse, AdvanceTime, ShrinkFraction()) and AWanefallWaneTrialArena's TrialTimeRemaining/CollapseWarnThreshold/IsCollapseImminent — reuse that pattern for the timeline.

Key APIs:
- `AWanefallWaneHazardField::AWanefallWaneHazardField()  // ctor: InitSphereRadius(FieldRadius=360), OverlapAllDynamic profile, warning-ring Cylinder mesh, point light, Niagara FX; binds Begin/EndOverlap`
- `bool AWanefallWaneHazardField::IsPointInField(const FVector& Point) const  // returns FVector::Dist(Point, GetActorLocation()) <= FieldRadius — reads LIVE actor location + FieldRadius member`
- `bool AWanefallWaneHazardField::ApplyFieldEffectsToActor(AActor* Target, float DeltaSeconds)  // finds UWanefallPrototypeHealthComponent, applies DamagePerSecond*(pulse?PulseDamageMultiplier:1)*Dt`
- `bool AWanefallWaneHazardField::IsPulseActive() const  // inline`
- `float AWanefallWaneHazardField::GetPulsePhase01() const`
- `float AWanefallWaneHazardField::GetFieldRadius() const  // inline getter; NOTE: no SetFieldRadius / no radius setter exists`
- `float AWanefallWaneHazardField::GetPlayerSlowFactor() const  // inline; character applies the slow itself`
- `void AWanefallWaneHazardField::Tick(float DeltaSeconds)  // advances PulseTimer, brightens light on pulse, applies damage to OverlappingActors set`
- `AWanefallMatchDirector::AWanefallMatchDirector()  // PrimaryActorTick.bCanEverTick=false`
- `void AWanefallMatchDirector::FillTeams(AWanefallArena4v4GameState* InArena, int32 NumBots)  // PRECEDENT: TActorIterator<APlayerStart>, World->SpawnActor<T>(Class, Loc, Rot, FActorSpawnParameters w/ AdjustIfPossibleButAlwaysSpawn)`
- `void AWanefallMatchGameMode::BeginPlay()  // PRECEDENT: finds existing GameState via TActorIterator, World->SpawnActor<AWanefallMatchDirector>(), Director->FillTeams(...)`
- `void AWanefallMatrixThemeController::ApplyTheme(bool bDark)  // PRECEDENT for Pristine->Fallen: LoadObject<UMaterialInterface>(existing M_Wane* paths), TActorIterator<AStaticMeshActor> by Tag, C->SetMaterial(i, Use); also retunes ADirectionalLight/ASkyLight/AExponentialHeightFog/APostProcessVolume at runtime — layout/collision untouched`
- `USphereComponent::SetSphereRadius(float, bool bUpdateOverlaps)  // engine API — exists and could grow the volume, but FieldVolume is PRIVATE and unexposed`
- `UStaticMeshComponent::SetMaterial(int32, UMaterialInterface*)  // engine API used by ApplyTheme`
