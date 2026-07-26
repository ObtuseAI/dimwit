# Dimwit — Gaps, Weaknesses & Areas to Improve (Forward Audit)

_Written 2026-06-26, after the G1–G15 elite-uplift cert (101/107 validators PASS). This is the **next-layer**
audit: the gaps the post-cert WANEFALL work actually exposed, ranked, with the evidence that proves each one and
the fix direction. Builds on `DIMWIT_COMPLETE.md` and the G1–G15 audit in memory `dimwit-elite-uplift`._

---

## The throughline (the one meta-weakness behind all of them)

**Dimwit validates PROXIES of the game, not the real running game.**

Its eyes (`desktop_eyes` PrintWindow) and its optics (GLM-5V semantic + pixel-truth) are genuinely elite. But
**nothing in the validation loop drives the actual game into its runtime state and judges THAT.** Instead the harness
judges three proxies, each of which diverges from what the player sees:

1. **Headless `SceneCapture2D` renders** — ignore exposure, never run `BeginPlay`, lit by a synthetic studio.
2. **Asset files on disk** — "imported ok / file exists" is not "renders correctly."
3. **Constructor-state actor spawns** — show default visibility, not the post-`BeginPlay` runtime truth.

The consequence, proven twice this session in opposite directions:

- **False NEGATIVE (rubber-stamp):** the black-cube/grey-blob **junk geometry shipped to the player** and the
  107-validator harness never caught it. The operator did. No validator ever launched the game and looked at the pawn.
- **False POSITIVE (cry wolf):** the correct dark-albedo Ekris was **false-flagged** "missing textures / disfigured"
  because the optics judged an exposure-broken `SceneCapture2D` grey render. Those were 2 of the cert's 2 FAILs.

A fail-closed harness that both misses real bugs AND raises false alarms keeps the **human as the actual QA**. Closing
that is the highest-leverage work going forward. Every gap below is a facet of it.

---

## New ranked gaps (continuing the G-series)

### G16 — No real-game capture in the validation loop · **CRITICAL**
- **Evidence:** `GrappleDevice` (Skyclaw mesh) + 6 engine-BasicShapes body cubes/sphere + a kitbash rifle rendered on
  the hero lobby pawn in the shipped build; the harness was green. Caught by the operator, not Dimwit.
- **Impact:** every visual/runtime regression is invisible to the harness. The human is the QA.
- **Fix:** a live-capture validator — launch standalone (or PIE) into the target map → `desktop_eyes` PrintWindow grab
  of the real window → `optics.judge`. Judge the window the player sees, never `SceneCapture2D`.
- **Status:** _pattern executing this session_ (we launched the lobby standalone + captured to verify the junk fix).
  Needs to become a wired, repeatable validator.

### G17 — No runtime (post-BeginPlay) actor-state truth · **CRITICAL**
- **Evidence:** `scripts/ue/wanefall_pawn_probe.py` (built this session) spawns the pawn in-editor and reads **constructor**
  visibility only — it cannot see what `BeginPlay::HideInheritedVisuals` does. To learn what actually renders at rest I
  had to read the C++ and infer. A probe that runs PIE, ticks a few frames, and enumerates *actually-visible*
  primitives would have flagged "GrappleDevice renders at rest" automatically.
- **Impact:** Dimwit can't assert runtime scene invariants (visibility, attachment, material-at-runtime). These bugs
  require a human reading C++.
- **Fix:** a headless-PIE component-visibility probe; assert per-map pawn invariants.

### G18 — No structural "stray placeholder geometry" validator · **HIGH**
- **Evidence:** the bug's signature is literally `/Engine/BasicShapes/Cube|Sphere|Cylinder` visible on a hero pawn. A
  trivial deterministic check ("no engine-placeholder mesh is visible on a player/hero actor at runtime") catches the
  whole class instantly and fail-closed — complementing the expensive, sometimes-wrong semantic optics.
- **Impact:** relies entirely on semantic vision for a class of bug with a trivial structural signature.
- **Fix:** structural validator scanning runtime-visible primitives for engine-placeholder meshes on hero actors.

### G19 — Dimwit doesn't own the build→launch→capture→judge→iterate loop · **HIGH**
- **Evidence:** this session the orchestrator ran UBT compile, the standalone launch, and the capture by hand.
  `live_operator` exists but needs the editor already open and is input(hands)-driven; there is no headless "rebuild
  the game module, relaunch, capture the pawn, judge, repeat" pipeline.
- **Impact:** the end-to-end visual-bug-fix loop the operator actually wants is manual, not a Dimwit capability.
- **Fix:** a `build_launch_capture_judge` orchestrator (UBT → standalone launch → eyes capture → optics + structural
  verdict → pass/fail + diff), loopable until green.

### G20 — `optics_character_semantic` gates on the wrong image; emits false FAILs · **HIGH** (known, still open)
- **Evidence:** memory already flags it judges the headless `SceneCapture2D` → false-flags dark albedos. Those were the
  cert's 2 FAILs. A fail-closed validator that cries wolf trains the operator to ignore RED.
- **Impact:** erodes trust in the harness; a real RED can hide among false REDs.
- **Fix:** repoint at a representative capture (live window via G16, or a locked-exposure Blender render). Never the
  exposure-broken `SceneCapture2D`.

### G21 — Headless `SceneCapture2D` treated as color/lighting proof, but isn't · **HIGH**
- **Evidence:** verified — `SceneCapture2D` ignores the PP manual-exposure override (key-light 5→3 + bias 12→9.5 →
  **byte-identical** render); dark albedo (~0.2) washes to flat light-grey. `scripts/ue/ue_capture_studio.py` is structurally
  unable to prove dark-material correctness.
- **Impact:** any validator built on it gives wrong color/lighting verdicts.
- **Fix:** retire SceneCapture-as-color. Use a real viewport/standalone capture or a locked-exposure Blender render.
  Keep SceneCapture only for geometry/silhouette, where exposure is irrelevant.

### G22 — Batch ops report success on "import ok," no per-item visual gate · **HIGH**
- **Evidence:** `roster_relift` returned 7/7 `ok=True` from import-success + file-existence; none were looked at
  in-game. Given G21, "import ok" ≠ "renders correctly."
- **Impact:** an entire roster can pass the batch while any/all look wrong in-game.
- **Fix:** each batch item gets a cheap visual/structural gate before `ok=True`; the batch verdict aggregates real
  evidence, not file existence.

### G23 — Single vision provider; no ensemble / local fallback · **MED**
- **Evidence:** all semantic optics route through GLM-5V via one `llm.py`. Down → semantic BLOCKED (correctly
  fail-closed) but no second opinion and no local vision fallback.
- **Impact:** resilience + single-judge bias; "validate everything" hinges on one external model.
- **Fix:** pluggable vision backends + optional N-judge consensus on critical verdicts.

### G24 — Live hands/operator enabled but never proven on a real UE task · **MED**
- **Evidence:** `desktop_hands` + `live_operator` self-test (see→think, cursor nudge) but per memory `editor_found=
  FALSE` (UE wasn't open); never drove a real edit to completion.
- **Impact:** an "enabled" but unexercised capability is a latent unknown.
- **Fix:** one real guarded recipe end-to-end (open lobby in-editor → toggle a property → save) under the safety
  envelope, ledgered.

### G25 — No game-side observability (UE log errors/ensures, FPS, hitches, memory) · **MED**
- **Evidence:** the HUD tracks Dimwit's own health, never the game's. A play session's `Warning/Error/Ensure` lines
  and perf go unread.
- **Impact:** crashes, missing-asset warnings, perf regressions are invisible to the harness.
- **Fix:** post-run UE-log scrape (count/triage Warnings/Errors/Ensures) + simple FPS/hitch capture as validators.

### G26 — Ad-hoc script sprawl continues; new work isn't pipeline-integrated · **MED** (G14 partial regression)
- **Evidence:** this session added `scripts/ue/wanefall_pawn_probe.py`, `scripts/pipeline/roster_relift.py`, `scripts/ue/ue_import_handcrafted_rig.py` as loose
  scripts beside ~60 others; the front-door CLI exists but these sit outside it.
- **Impact:** capabilities aren't discoverable/reusable; knowledge lives in one-off scripts.
- **Fix:** fold probe/capture/launch into the `dimwit/` package, expose via `dimwit.py`, deprecate the one-offs.

### G27 — Field-aligned retopo still voxel-quad on 7/8; high pole count · **LOW** (quality, carry-forward)
- **Evidence:** quadriflow no-ops on 7/8 even post-voxel; deformation-ready but ~42% poles → suboptimal edge flow for
  fine facial deformation.
- **Impact:** bodies deform fine; faces/hands may pinch under extreme deformation.
- **Fix:** `instant-meshes` backend or an ML retopo backend for field-aligned all-8.

---

## Still-open carry-forwards (from G1–G15)
- **G5** video/temporal optics — capability built, still PIE-gated (needs live frames; G16 unblocks it).
- **G12** two non-interoperating engines (`engine.py` vs `ProductionPipeline`) — still unmerged.
- **G15** provenance closed **shallowly** — verifies a source file *exists*, not that its content is what it claims
  (no content-hash identity).

---

## Prioritized roadmap (WANEFALL-forward)

**P0 — convert Dimwit from "judges proxies" to "judges the real game" (do first; unblocks honest QA):**
G16 live-game capture validator · G17 runtime PIE probe · G20 repoint optics · G21 retire SceneCapture-as-color.

**P1 — let Dimwit autonomously catch + close visual bugs:**
G18 structural placeholder-geometry validator · G19 build→launch→capture→judge loop · G22 per-item visual gate.

**P2 — observability + proven autonomy + consolidation:**
G25 game log/perf validators · G24 prove hands on one real task · G26 fold into package/CLI.

**P3 — quality + resilience:**
G23 vision ensemble · G27 field-aligned retopo · G12 engine merge · G15 content-hash provenance.

---

## How this maps to the operator's working model
The operator's loop (orchestrate → Dimwit prep/execute → polish → Dimwit test/polish → **both validate on the live
desktop, loop to done**) is itself the fix for the throughline: it puts a real-desktop look in the loop on every
change. P0/P1 above are that loop, made into permanent Dimwit capabilities instead of manual steps.
