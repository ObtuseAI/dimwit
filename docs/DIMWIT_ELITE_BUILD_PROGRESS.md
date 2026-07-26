# Dimwit Elite Build — Progress Tracker (RESUME ANCHOR)

> **If you (Claude) are re-orienting after losing context, READ THIS FIRST**, then `docs/DIMWIT_ELITE_SPEC.md`.
> Goal: make Dimwit the elite full-spectrum autonomous game-building agent (UE + Blender + tools; develop/
> design/execute/test; recursive/thresholded/compounding; MCP-wired). Building all 16 spec tasks autonomously.

## Resume protocol
1. Read this file's **STATUS** + the per-task checkboxes below (what's done / next).
2. Read `docs/DIMWIT_ELITE_SPEC.md` (the full grounded spec: capability map §1, control loop §2, MCP §3, task table §4, done-vs-new §5).
3. Sanity-check the engine still passes: `cd C:/Users/developer/Documents/Dimwit && python validators/dimwit_self_validation.py` (must exit 0).
4. Continue from the first unchecked task in **build order**.
5. **Doctrine (never violate):** never weaken a validator, never auto-promote past `PROMOTED_TO_REVIEW`, thresholds ratchet UP only, provenance pre-gate stays fail-closed, `assert_dimwit_path` wraps every ledger/queue write, active-slice import stays operator-gated. Default config profile must keep existing runs byte-identical.

## STATUS
- **Phase:** COMPLETE. **Last updated:** 2026-06-26.
- **ALL 16 TASKS DONE + GREEN.** Extended self-validation = 16/16 pass (`python validators/dimwit_self_validation.py`, exit 0), incl. new checks: capability_registry_resolves, proof_ledger_hash_chain, ue_mcp_live_bridge_present, per_class_builder_executable.
- Dimwit is now: autonomous (scripts/pipeline/racc_run.py director), thresholded (per-class profiles, ratchet-up), compounding (learn()→lesson→weight + rollup/trend), closed-loop (render_fn regenerates evidence), multi-tool (per-class Blender builders + Hi3D + live UE), MCP-wired (ue_mcp live editor + mcp/dimwit_server engine), brain-agentic (GLM 5.2 tool-calling agent_loop).
- Entry points: `python scripts/pipeline/racc_run.py` (autonomous director), `python reports/rollup.py` (cross-tool rollup), `python -m dimwit.capabilities.registry` (verify capabilities), MCP servers `ue_mcp/server.py` + `mcp/dimwit_server.py`.
- Control loop is live: `python scripts/pipeline/racc_run.py [--max-assets N]` runs the director (pick_next → run → learn → ledger → compounding weight apply). Proof + director ledgers hash-chain-verify.

## Build order (recommended): 1 → 2 → 3 → 4 → 5 → 7 → 9 → 6 → 11 → 13 → 8 → 10 → 14 → 15 → 12 → 16

| # | Task | Status | Create | Modify |
|---|---|---|---|---|
| 1 | Per-class promotion profiles + data-driven thresholds/weights | [ ] | `config/promotion/<class>.json` | `engine.py` validate_promotion + overall (read profile) |
| 2 | Hash-chain the proof ledger | [ ] | `dimwit/ledger/hashchain.py` | `engine.py` DimwitLedger.append (+prev_hash), consistency_check (+chain_verify) |
| 3 | `learn()` + runtime lesson append (occurrences/domain) | [ ] | — | `scripts/pipeline/run_dimwit.py` (+learn), append `lessons/dimwit_asset_lessons.jsonl` |
| 4 | Lesson→weight soft applier (capped, ratchet-up); law operator-gated | [ ] | `dimwit/learning/lesson_loop.py` | `engine.py` score_candidate (read lessons); `review.py` (propose law) |
| 5 | `pick_next()` director: priority + budget + circuit breaker; brain tie-break | [ ] | `scripts/pipeline/racc_run.py` | — |
| 7 | Finish UE live MCP bridge | [x] DONE (this session) | `ue_mcp/server.py`,`README.md`,`init_unreal.py`,`.mcp.json` | `ue_client.py` |
| 9 | Capability registry + dispatch keystone | [ ] | `dimwit/capabilities/{registry,base}.py`, `config/capability_registry.json` | decorator atop tool modules |
| 6 | Close the loop: `render_fn` regenerates evidence per candidate | [ ] | `dimwit/capabilities/iterate.py` | `engine.py` recursive_mutation_loop (accept/call render_fn) |
| 11 | Real per-class Blender builders (back the stub) | [ ] | per-class recipes in `blender_asset_builder_interface.py` | unify enemy delegate → `meshgen._BLENDER_SCRIPT` |
| 13 | UE import correctness: post-import verify + material-translate | [ ] | — | `ue_import_*.py` (+verify), `unreal_import_contract.json` (+material map) |
| 8 | Cross-tool ledger rollup (join on asset_id+candidate_hash) | [ ] | `reports/rollup.py`,`reports/trend.py` | satellite ledger writes (+join key) |
| 10 | Dimwit AS MCP server + engine `*_by_id`/`run_all_gates` helpers | [ ] | `mcp/dimwit_server.py` | `engine.py` (thin helpers) |
| 14 | Brain agency: tool-calling loop + transport fix | [ ] | `dimwit/capabilities/agent_loop.py` | `llm.py` chat (tools passthrough + DEFAULTS fix), verdict schemas (+confidence/abstain) |
| 15 | `DESIGN/spec.author` (concept→seed spec) | [ ] | `dimwit/spec_author.py` | — |
| 12 | Data-driven level building | [ ] | `config/level_spec.schema.json` + one builder | extract from build_hold_room/build_kit_arena |
| 16 | Extend self-validation (+4 checks) | [ ] | — | `validators/dimwit_self_validation.py` |

## Per-task completion log (append as each ships)
- (none yet)
