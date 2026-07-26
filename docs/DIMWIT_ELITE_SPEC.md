### 1.2 Capability inventory by domain

Every row marks **what already exists** and **the minimal new work** (file-level).

**DESIGN — concept → spec → plan**

| Verb | Wraps (existing) | New work |
|---|---|---|
| `DESIGN/brain.invent_concepts` | `cloud_brain.concept_prompts` (`cloud_brain.py:102`) | register only |
| `DESIGN/brain.plan_queue` | `cloud_brain.plan_queue` (`cloud_brain.py:74`) | register; feed **prior-failure reason** into prompt (closes brain B/C) |
| `DESIGN/spec.author` | `core.AssetTask` + `asset_task_schema.json` | **NEW** `dimwit/spec_author.py`: concept-prompt → seed `asset_spec.json` (closes invent→render dead-end, brain J / loop C) |
| `DESIGN/recon.ingest` | `reference_intake_schema.json`, `cli.py perceive/intake` | register only |

**DEVELOP — build geometry / materials / levels** (biggest real gap; `character.py` is the elite template)

| Verb | Wraps (existing) | New work |
|---|---|---|
| `DEVELOP/cloud.image_to_3d` | `hi3d.py` + `scripts/pipeline/hi3d_batch.py` (ELITE, resumable, cost-aware) | register; expose `submit_multiview` |
| `DEVELOP/cloud.image_to_3d_local` | `neural3d.py` (TripoSR) | register as explicit **fallback tier** (resolves tools #11) |
| `DEVELOP/blender.build_mesh` | `meshgen.generate` (`meshgen.py:158`, trimesh-measured) | register; route by class |
| `DEVELOP/blender.build_class[enemy\|weapon\|vehicle\|helmet\|prop]` | `character.py` (646-line elite builder) as **template**; `blender_asset_builder_interface.py CLASS_RECIPES` (the V1 stub) | **back the stub** with real per-class builders cloned from `character.py`; unify dangling enemy delegate onto in-Dimwit `meshgen._BLENDER_SCRIPT` (closes loop D, tools 5/6) |
| `DEVELOP/blender.render_views` | `scripts/blender/render_ingame.py` (ELITE) | register as-is |
| `DEVELOP/mesh.postprocess` | `refine.py`, `scripts/blender/decimate_for_ue.py`, `scripts/blender/process_new.py` | register the reusable ones |
| `DEVELOP/level.build` | `scripts/blender/build_map_kit.py` (ELITE kit) + `scripts/ue/build_hold_room.py`/`scripts/ue/build_kit_arena.py` (one-offs) | **NEW** `config/level_spec.schema.json` + one data-driven builder; hardcoded layouts become JSON inputs (closes tools #2) |

**EXECUTE — import / drive live editor**

| Verb | Wraps (existing) | New work |
|---|---|---|
| `EXECUTE/ue.live.*` (`ping/exec/screenshot/list_actors/save`) | `ue_mcp/ue_bridge.py` (EXISTS, correct, game-thread, 8222) + `ue_mcp/ue_client.py` (EXISTS) | **finish** `ue_mcp/server.py` (stdio forwarder) + `ue_mcp/README.md` + `init_unreal.py` autoload — warm loop, highest single ROI (tools #1) |
| `EXECUTE/ue.import` | `scripts/ue/ue_import_assets.py`/`scripts/ue/ue_import_kit.py` + `unreal_import_contract.json` | wrap; **add post-import verify** (slot count, material, collision, bounds) feeding technical gate (tools #4) |
| `EXECUTE/ue.material_translate` | `scripts/ue/fix_kit_material.py`/`scripts/ue/editor_fix.py` prove the need | add `glb→UE material map` step to import contract — correct-by-construction, not repaired (tools #3) |
| `EXECUTE/ue.capture[hero\|player_camera\|dual_gate]` | `adapters.py` (SOLID, watchdog, dry_run) | register as-is — already capability-shaped |
| `EXECUTE/blender.live` | the **already-connected Blender MCP** in this env | register the live MCP so iterative builds skip cold-start (tools #7) |

**TEST — perceive / judge / gate / promote**

| Verb | Wraps (existing) | New work |
|---|---|---|
| `TEST/perception.measure` | `perception.perceive_evidence` (ELITE pixel-truth) | register as-is |
| `TEST/brain.vision_qa` | `cloud_brain.review_character` (`cloud_brain.py:22`) | register; allow returning `need_views[]` the loop honors (brain D) |
| `TEST/brain.light_qa` | `scripts/qa/dimwit_light_qa.py` (emits numeric `deltas`) | register; **wire `deltas`** into `ue.live.exec` lighting-apply (closes brain E, the documented-but-absent apply side) |
| `TEST/gate.run_all` | 8 gates `engine.py:101-162` | register as one capability |
| `TEST/gate.promote_review` | `validate_promotion` + `review.build_review_package` | register; terminal stays `PROMOTED_TO_REVIEW` (ceiling preserved) |

---

## 2. UNIFIED RECURSIVE CONTROL LOOP (RACC)

One **outer director** loop wrapping the **existing inner** `recursive_mutation_loop`. Nothing weakens a validator or auto-promotes.

```
OUTER (director):  pick_next → RUN one asset → learn → (repeat | HALT)
INNER (per asset): provenance pre-gate → recursive_mutation_loop(render_fn) → 8 gates → terminal → ledger
```

### 2.1 Outer director — `scripts/pipeline/run_dimwit.py` gains `pick_next()` + `learn()` (becomes `scripts/pipeline/racc_run.py:main()`)

```
load queue, ledger, lessons, learned_weights
while budget_remaining and not halt_flag:
    task = pick_next(queue, ledger, lessons, budget)        # autonomy
    if task is None: break                                  # nothing actionable → clean HALT
    if requires_human_gate(task): mark BLOCKED; continue    # fail-closed
    record ATTEMPT_STARTED (hash-chained)
    result = run_asset_task(task)                           # EXISTING engine entry, untouched
    lesson = learn(result, ledger)                          # compounding capture
    if lesson: append lessons + recompute learned_weights (capped, ratchet-up only)
    queue.upsert(task ← result.terminal_state)
    record ATTEMPT_FINISHED (prev_hash chain)
ledger.consistency_check() + chain_verify()
```

**`pick_next()` — deterministic-first, brain-advised-second** (degrades safely if LLM offline):
1. Filter to actionable (drop terminal/operator-only states — reuse `scripts/pipeline/run_dimwit.py:50`).
2. Priority = `w1·explicit_priority + w2·expected_value − w3·cost − w4·repeat_failure_penalty`, where `expected_value = (promote_threshold − last_overall)` for close-to-passing cheap wins else class gameplay-criticality; `cost` = Hi3D credits + capture seconds; penalty = prior `NEEDS_RECURSION/REJECTED` count for that `asset_id`.
3. Brain tie-break via `cloud_brain.plan_queue`, **accepted only if schema-valid** (every `action ∈ {generate,redo,skip,accept}`, every `name` in snapshot); else deterministic order. The brain advises, never dispatches.
4. Return single highest-priority task (one asset per outer iter keeps the ledger linear/replayable).

### 2.2 Inner loop — closed in software (the load-bearing fix)

Today the loop mutates a spec dict and re-scores the **same frozen PNGs**, so a measured `black_blob` can never be fixed (audit B/C). Add a **`render_fn` callback** so each kept-best candidate produces **new pixels** before scoring:

```
recursive_mutation_loop(seed, score_fn, mutate_fn, render_fn):
    best = score_fn(render_fn(seed))
    while best.overall < threshold and iters < MAX(6) and stale < 2:
        cand   = mutate_fn(best)            # EXISTING deterministic weakest-dim delta
        cand   = render_fn(cand)            # NEW: regenerate evidence this candidate
        best, stale = keep_best(best, score_fn(cand))   # EXISTING keep-best + pixel-truth
    return best
```

`render_fn` chains existing elite tools (warm via MCP, cold-process fallback via `adapters`):
```
render_fn(cand) =
  DEVELOP/blender.build_class(cand.spec)          # meshgen / per-class builder + trimesh measure
  → EXECUTE/ue.import (verify slots/mat/collision/bounds → technical gate)
  → EXECUTE/ue.capture[hero] + ue.capture[player_camera]   # both required, non-substitutable
  → TEST/perception.measure(pngs)                 # measured pixels override declared
  → cand with fresh evidence + metrics
```
If tools are absent, `render_fn` returns the candidate unchanged → loop degrades to today's declared-only behavior (same guard pattern as `engine._HAS_PERCEPTION`). **`NEEDS_RECURSION` becomes recoverable.**

### 2.3 Thresholded promotion — data-driven per-class, ratchet-up only

- **NEW** `config/promotion/<asset_class>.json`: `promote_threshold` (was the `0.70` constant), `dimension_weights` (was implicit equal-weight mean), `required_evidence`, `hard_gates`. `validate_promotion`/`overall` read this instead of in-code constants. **Default profile = current behavior** (0.70, equal weights) → existing runs byte-identical. New classes (weapon/vehicle/prop) ship their own profiles — no engine edit (closes loop D/F, memory #4/#6).
- Gate ladder unchanged in order: provenance pre-gate (HARD, before any spend) → technical → style (HARD) → hero AND player_camera → performance → weighted overall ≥ threshold → `PROMOTED_TO_REVIEW`.
- **Thresholds ratchet UP only:** director may raise a class threshold when outcomes show easy passes; a guard forbids lowering below the seeded floor (`max(0.70, learned)`). Compounding can only make the bar harder.

### 2.4 Compounding learn step — failure→lesson→law, cross-domain

- **NEW** `learn(result, ledger)`: on `REJECTED/NEEDS_RECURSION`, derive a lesson from `weakest_dimension` + `perception_hard_fails`, tagged with `domain` (asset_class) and `source=candidate_hash` (join key). Dedupe by `(domain,dimension)` with `occurrences++`. Lessons now grow **at runtime** (closes memory #2; the advertised `…→ledger→learn` finally compounds).
- **Soft apply (automatic, capped):** when `occurrences ≥ 3`, bump that dimension's weight in the class profile (and global profiles if `cross_domain`), weight ≤ 3.0, reversible. Palette/provenance/silhouette lessons are **global** (apply to weapons/props too); pose/weak-point lessons stay **class-scoped** — this is how learning crosses domains.
- **Hard apply (operator-gated):** promoting a lesson into `FORBIDDEN_IDENTITY`/`REQUIRED_IDENTITY` (a real veto) is **never automatic** — it surfaces in the review package as a proposed law for human acceptance. Preserves the doctrine that structural vetoes are deliberate.

### 2.5 Self-direction stop conditions (bounded envelope)

- **Budget gate** — Hi3D credits + wall-clock; exhaustion → clean HALT + handoff to `reports/`. Aggregates the brain's `usage` telemetry (currently captured-but-unused, brain H) so the director is burn-rate aware.
- **Per-asset circuit breaker** — `NEEDS_RECURSION` ≥ `MAX_ATTEMPTS=3` (mirrors Blunder ≤3) without improving best `overall` → set `BLOCKED` + `redo_reason`, move on. Outer analogue of the inner `stale≥2` stop.
- **Convergence-aware redo** — attempt N+1 feeds attempt N's `weakest_dimension` + metrics into the next render spec and the GLM redo prompt (fixes brain B/C).
- **No-actionable-work HALT**; **failure isolation** — one asset's exception → `BLOCKED` ledger entry, loop continues (fixes robustness J).

### 2.6 Brain agency (small, high-ceiling, schema-gated)

- **NEW** `dimwit/capabilities/agent_loop.py`: replace `dimwit_cloud.cmd_auto`'s hardcoded `qa→plan→redo` switch with a bounded (≤3) **tool-calling loop** — pass the registry's verbs as `tools` to `llm.chat`, dispatch the model's chosen capability, feed result back. The model can demand more views, re-perceive, query the unified ledger (brain A/B/D).
- **EDIT** `dimwit/llm.py:112 chat`: pass-through `tools`/`tool_choice`, surface `tool_calls`; **fix stale `DEFAULTS`** (`claude-3.5-sonnet` → match GLM directive in `llm_config.json`) so partial config can't misroute (tools #10, brain footgun).
- Add `confidence`/`abstain` to verdict schemas: a model-parse failure **escalates to human** instead of laundering into `redo=True, overall=0` (brain F/I).

---

## 3. MCP TOPOLOGY

Dimwit becomes **both** an MCP server (its capabilities = tools Claude can call) **and** an MCP client/orchestrator driving a live UE editor + the already-connected Blender MCP. Two complementary tiers.

```
                         ┌──────────────── CLAUDE (Opus) ───────────────┐
                         │     orchestrator — sees ALL servers below      │
                         └──── stdio ───────── stdio ───────── stdio ─────┘
                ┌────────────────┐   ┌──────────────────┐   ┌────────────────┐
                │  dimwit-mcp   │   │   unreal-mcp     │   │  Blender MCP   │
                │ mcp/dimwit_   │   │  ue_mcp/server.py │   │  (EXISTING,    │
                │ server.py (NEW)│   │  (NEW forwarder)  │   │  connected)    │
                └──── in-proc ───┘   └──── TCP 8222 ─────┘   └────────────────┘
                 imports dimwit/         ue_bridge.py (EXISTS, in live editor,
                 engine,perception,…      game-thread Slate post-tick marshaling)
                        │
                        └─ Tier-2: dimwit-mcp itself drives UE via ue_client.py (EXISTS)
```

- **Tier 1 — Claude orchestrates** (primary, lowest new work): Claude holds `dimwit` + `unreal` + `blender` simultaneously and sequences `dimwit.score → blender.execute → unreal.import_glb → unreal.hero_capture → dimwit.perceive`. The live, hands-on loop.
- **Tier 2 — Dimwit orchestrates** (autonomous): `dimwit-mcp` drives the UE bridge over TCP 8222 via the existing `ue_client.py`, so `recursive_mutation_loop` produces new pixels per iteration unattended. This *is* `render_fn`'s warm path.

**The in-editor half already exists and is architecturally correct** (`ue_bridge.py`: 127.0.0.1:8222, background thread, newline-JSON, `register_slate_post_tick_callback` game-thread drain, double-start guard via `unreal._dimwit_bridge_running`; cmds `ping/exec/screenshot/list_actors/save_level`). Missing only: the stdio forwarder + autoload doc.

**New MCP files (stdlib-only JSON-RPC stdio, no `mcp` pip dep):**
- `ue_mcp/server.py` (~70 lines) — stdio forwarder over `ue_client.send()`; tools `ue_ping/ue_exec/ue_screenshot/ue_list_actors/ue_save_level/ue_import_glb`.
- `ue_mcp/README.md` + `<Project>/Content/Python/init_unreal.py` (3-line autoload; idempotent via existing guard).
- `mcp/dimwit_server.py` (~80 lines) — in-process wrapper over `engine/perception/meshgen/adapters/review/cloud_brain`; tools `dimwit_run_asset_task/score_candidate/perceive_evidence/generate_mesh/check_gates/build_review/vision_qa`.
- `.mcp.json` at project root (auto-discovered): `dimwit`, `unreal` (port 8222 env), `blender` (already live in-env; explicit block only for standalone Desktop).
- Thin engine helpers (~5 lines each, factored from `run_dimwit.main()`): `run_asset_task_by_id`, `run_all_gates`, `build_review_package_by_id`.

**Safety in the MCP layer (unchanged):** `assert_dimwit_path` still wraps every ledger/queue write; **no `ue_import_to_active_slice` tool exists** (active-slice stays operator-gated); `ue_exec` is localhost-only arbitrary code (prefer typed `ue_import_glb`/`ue_screenshot`); pixel-truth over fresh renders stays authoritative over any declared/LLM score.

---

## 4. PRIORITIZED BUILD TASK LIST (MINIMAL-NEW-WORK)

Each task is independently shippable and leaves the system green. Steps 1–5+8 ship the control loop **before** the renderers are warm (inner loop degrade-safe); step 6 needs the warm bridges from step 7.

| # | Task | Create | Modify | Reuses (EXISTS) | Closes |
|---|---|---|---|---|---|
| **1** | Per-class promotion profiles + data-driven thresholds/weights | `config/promotion/<class>.json` | `engine.py` `validate_promotion` + `score_candidate.overall` (read profile) | gate code verbatim; default profile = current behavior | loop D/F, memory 4/6 |
| **2** | Hash-chain the proof ledger | `dimwit/ledger/hashchain.py` | `engine.py` `DimwitLedger.append` (+`prev_hash`), `consistency_check`(+`chain_verify`) | `core.sha256_obj`, append-only ledger | memory A (top integrity gap) |
| **3** | `learn()` + runtime lesson append (occurrences/domain) | — | `scripts/pipeline/run_dimwit.py` (add `learn`), append to `lessons/dimwit_asset_lessons.jsonl` | `mutate_candidate` delta table as fix-source; ledger verdicts | core A, memory 2 |
| **4** | Lesson→weight soft applier (capped, ratchet-up); law stays operator-gated | `dimwit/learning/lesson_loop.py` | `engine.py` `score_candidate` (read lessons); `review.py` (propose law) | lessons file, class profiles | core A, memory B; control-loop §2.4 |
| **5** | `pick_next()` director: priority math + budget + circuit breaker; brain `plan_queue` schema-validated tie-break | `scripts/pipeline/racc_run.py` (or extend `scripts/pipeline/run_dimwit.py`) | — | `scripts/pipeline/run_dimwit.py:50` filter, `cloud_brain.plan_queue` | autonomy; brain A/I; robustness J |
| **6** | **Close the loop:** `render_fn` regenerates evidence per candidate | `dimwit/capabilities/iterate.py` | `engine.py:265 recursive_mutation_loop` (accept/call `render_fn`) | loop control verbatim; `meshgen` trimesh fallback; `adapters` dry_run | loop B/C, tools 8 (the central fix) |
| **7** | **Finish UE live MCP bridge** (highest single ROI) | `ue_mcp/server.py`, `ue_mcp/README.md`, `Content/Python/init_unreal.py`, `.mcp.json` | `ue_mcp/ue_client.py` (+3-line `send()` if missing) | `ue_mcp/ue_bridge.py` (correct), `ue_client.py` | tools 1; unblocks warm step 6 |
| **8** | Cross-tool rollup: join satellite ledgers on `asset_id`+`candidate_hash`; populate `reports/`+`memory/` | `reports/rollup.py`, `reports/trend.py` | satellite ledger writes (add join key) | 5 existing ledgers | memory C/E, tools 9 |
| **9** | Capability registry + dispatch keystone | `dimwit/capabilities/{registry,base}.py`, `config/capability_registry.json` | one-line decorator import atop existing tool modules | `assert_dimwit_path`, `DimwitLedger`, `Lifecycle`, `opensource_registry.json` pattern | brain I (schema), core (per-call ledger) |
| **10** | `mcp/dimwit_server.py` (Dimwit AS MCP server) + engine `*_by_id`/`run_all_gates` helpers | `mcp/dimwit_server.py` | `engine.py` (thin helpers) | engine/perception/meshgen/adapters/review/cloud_brain | mcp Tier-1 |
| **11** | Back Blender builder contract with real per-class builders | per-class recipes in `blender_asset_builder_interface.py` (model on `character.py`) | unify enemy delegate → `meshgen._BLENDER_SCRIPT` | `character.py` (646-line elite template), `meshgen.py`, `scripts/blender/render_ingame.py` | loop D, tools 5/6 |
| **12** | Data-driven level building | `config/level_spec.schema.json` + one builder | extract from `scripts/ue/build_hold_room.py`/`scripts/ue/build_kit_arena.py` | `scripts/blender/build_map_kit.py` (ELITE kit) | tools 2 |
| **13** | UE import correctness: post-import verify + material-translate contract step | — | `ue_import_*.py` (+verify), `unreal_import_contract.json` (+`glb→UE material map`) | `unreal_import_contract.json`; need proven by `scripts/ue/fix_kit_material.py` | tools 3/4 |
| **14** | Brain agency: tool-calling loop + transport fix | `dimwit/capabilities/agent_loop.py` | `llm.py:112 chat` (tools passthrough + DEFAULTS fix), verdict schemas (+`confidence/abstain`) | `llm.chat`, registry | brain A/B/D/F, tools 10 |
| **15** | `DESIGN/spec.author` (concept→seed spec) closes invent→render | `dimwit/spec_author.py` | — | `asset_task_schema.json`, `core.AssetTask` | brain J, loop C |
| **16** | Extend self-validation | — | `validators/dimwit_self_validation.py` (+4 checks) | existing exit-0 regression pattern | — |

**Recommended order:** 1 → 2 → 3 → 4 → 5 → 7 → 9 → 6 → 11 → 13 → 8 → 10 → 14 → 15 → 12 → 16.
Rationale: ship thresholds/integrity/learning/autonomy (1–5, no tools needed) → finish UE bridge (7) and registry (9) → close the loop (6) → back builders + import correctness (11,13) so the warm loop produces real fixes → rollup/MCP-server/agency/spec-author/level polish (8,10,14,15,12) → harden self-validation (16). Self-validation checks to add: (a) every `capability_registry.json` entry resolves to a real importable fn; (b) hash-chain verifies on the proof ledger; (c) `ue_mcp/server.py`+`README.md` exist; (d) ≥1 per-class Blender builder is executable (not stub).

---

## 5. HONEST "ALREADY DONE vs NEW" TABLE

| Subsystem | Status | Evidence / file | Delta to elite |
|---|---|---|---|
| Recursive keep-best mutation loop | **DONE** | `engine.py:265`, ≤6 iters, stale-stop, deterministic weakest-dim deltas | open at both ends → add `render_fn` (task 6) |
| 16-dim deterministic scoring | **DONE** | `core.py:40`, `engine.py:166`, `overall=mean` | weights → per-class profile (task 1); add pose/topology dims later |
| Pixel-truth perception override | **DONE (ELITE)** | `perception.py`, `engine.py:186-209` measures real PNGs, overrides declared | re-measure **fresh** renders not frozen (task 6) |
| 8 gates + 2 hard gates (style, provenance) | **DONE** | `engine.py:101-162`, `asset_validation_gates.json` | parameterize numbers per class (task 1); add post-import verify (task 13) |
| 16-state lifecycle + autonomy ceiling | **DONE** | `core.py:16-37`, operator-only states unreachable by code | unchanged — invariant preserved |
| Append-only proof ledger | **DONE** | `engine.py:43`, `consistency_check` presence-only | **NO hash chain** → add `prev_hash`+`chain_verify` (task 2) |
| Hash chain / tamper-evidence | **NEW** | grep: zero `prev_hash`/`chain` matches | task 2 (top integrity fix) |
| Blunder path isolation guard | **DONE** | `engine.py:34 assert_dimwit_path` | unchanged |
| Review packaging + human-screenshot override | **DONE** | `review.py:19`, `human_screenshot_override_policy.json` | add proposed-law surfacing (task 4) |
| Provenance fail-closed pre-gate | **DONE** | `engine.py:317`, `core.evaluate_provenance` | unchanged |
| Hi3D cloud image→3D (resumable, cost-aware) | **DONE (ELITE)** | `hi3d.py`, `scripts/pipeline/hi3d_batch.py`, `scripts/pipeline/props_batch.py` | register as capability only (task 9) |
| Blender render/measure/decimate utilities | **DONE (ELITE)** | `scripts/blender/render_ingame.py`, `meshgen.py` trimesh-measure, `scripts/blender/decimate_for_ue.py` | register only |
| Procedural character builder | **DONE (SOLID template)** | `character.py` (646 lines) | clone into per-class builders (task 11) |
| Generalized Blender builder contract | **STUB** | `blender_asset_builder_interface.py` build()=V1 no-op | back with real recipes (task 11) |
| Single asset class really supported | **PARTIAL** | only hostile-construct recipe real; 22 declared types | per-class builders + profiles (tasks 11,1) |
| UE capture adapters (watchdog, dry_run) | **DONE (SOLID)** | `adapters.py:48-83` | register; flip dry_run in warm loop (task 6) |
| UE in-editor game-thread bridge | **DONE (correct)** | `ue_mcp/ue_bridge.py` (8222, post-tick) | unchanged |
| UE stdio MCP forwarder + autoload | **NEW** | `server.py`/`README.md`/`init_unreal.py` absent | task 7 (unblocks warm loop) |
| UE level builders | **ONE-OFF** | `scripts/ue/build_hold_room.py`/`scripts/ue/build_kit_arena.py` hardcoded | data-driven spec (task 12) |
| UE import correctness | **PARTIAL** | imports+saves, no verify; `scripts/ue/fix_kit_material.py` = symptom | verify + material contract (task 13) |
| Cloud brain judgment primitives (vision/plan/concept/light QA) | **DONE (SOLID)** | `cloud_brain.py`, `scripts/qa/dimwit_light_qa.py` (numeric deltas) | wire deltas to apply (task 6/registry); confidence field (task 14) |
| LLM transport (OpenRouter, retry, JSON parse) | **DONE (SOLID)** | `llm.py:79-173` | tools passthrough + stale-DEFAULTS fix (task 14) |
| Tool-calling / brain agency | **MISSING** | `llm.chat` sends no `tools`; `cmd_auto` hardcoded switch | task 14 (agent_loop) |
| Lessons re-ingested into loop (learn step) | **MISSING** | `lessons/*.jsonl` write-once, unread by code | tasks 3+4 (the biggest compounding gap) |
| Threshold/weight learning | **MISSING** | `0.70` hardcoded in 2 places | tasks 1+4 (ratchet-up only) |
| Unified cross-tool ledger + rollup | **MISSING** | 5 disjoint ledgers, no join key | task 8 |
| `memory/` + `reports/` trend layer | **EMPTY** | dirs exist, 0 files | task 8 |
| Autonomous director (pick_next, budget, breaker) | **MISSING** | `scripts/pipeline/run_dimwit.py` iterates file-order, ignores priority | task 5 |
| Closed generate→import→capture→re-perceive loop | **MISSING** | loop mutates spec vs frozen evidence | task 6 (central fix) |
| Capability registry + dispatch | **NEW** | — | task 9 (keystone) |
| Dimwit AS MCP server | **NEW** | — | task 10 |
| concept→spec author (invent→render bridge) | **MISSING** | `concept_prompts` dead-ends | task 15 |
| Self-validation regression gate | **DONE** | `validators/dimwit_self_validation.py` (16 checks) | +4 checks (task 16) |
| TripoSR local image→3D | **DONE (secondary)** | `neural3d.py` isolated venv | register as explicit fallback tier (task 9) |

**Net new surface:** dirs `dimwit/capabilities/`, `dimwit/learning/`, `dimwit/ledger/`, populate `reports/`+`memory/`. ~14 new files: `capabilities/{registry,base,iterate,agent_loop}.py`, `learning/lesson_loop.py`, `ledger/hashchain.py`, `reports/{rollup,trend}.py`, `spec_author.py`, `ue_mcp/{server.py,README.md}`, `mcp/dimwit_server.py`, `init_unreal.py`, `config/{capability_registry,level_spec.schema}.json` + `config/promotion/<class>.json`, `.mcp.json`. ~6 additive edits: `engine.py` (render_fn call, profile reads, prev_hash, helpers, lesson reads), `llm.py` (tools + DEFAULTS), per-class Blender builders, `ue_import_*` verify, `unreal_import_contract.json` material map, `self_validation` checks.

**What is explicitly NOT rebuilt:** `recursive_mutation_loop`, `score_candidate`, the 16 dimensions, all 8 gates + 2 hard gates, the 16-state lifecycle + autonomy ceiling, `perception` pixel-truth, `DimwitLedger`/`DimwitQueue`, `assert_dimwit_path`, `hi3d.py`/`scripts/pipeline/hi3d_batch.py`, `adapters.py`, `scripts/blender/render_ingame.py`, `character.py`, `ue_bridge.py`, the human-screenshot-override law, the provenance pre-gate. The build is a **registry + dispatch shell + three wiring closures (loop, learn, ledger)** around an already-elite core.

**Bottom line:** Dimwit is ~70% built and the built parts are elite. The remaining 30% is wiring the open ends — close the recursive loop with `render_fn` (task 6), finish the UE MCP forwarder (task 7), wire failure→lesson→weight (tasks 3/4), hash-chain + unify the ledger (tasks 2/8), and back the Blender builder stub with real per-class code (task 11). Ship tasks 1–5+8 first: the autonomous, thresholded, compounding control loop runs in degrade-safe declared mode **before** the renderers are warm, then turns real the moment task 6/7 land.