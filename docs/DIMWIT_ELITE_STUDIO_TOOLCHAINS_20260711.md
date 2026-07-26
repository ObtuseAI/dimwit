# Dimwit Elite Studio Toolchains — 2026-07-11

## What is now real

Dimwit has one audited execution contract for Blender, one for Unreal, and a resumable full-game studio DAG
that composes both toolchains with the existing fail-closed production pipelines.

### Blender

`dimwit.toolchains.blender` provides:

- discovery with `DIMWIT_BLENDER_EXE` override;
- repository-owned script allowlisting;
- output-root confinement;
- headless, factory-startup, auto-exec-disabled commands;
- argv-only subprocess execution (`shell=False`);
- timeouts, complete stdout/stderr logs, atomic manifests/results;
- script SHA-256 and output file/tree SHA-256 receipts;
- plan-only behavior unless mutation is explicitly enabled.

Verified against Blender **5.1.2**. The live smoke produced:

- `artifacts/toolchain_smoke/elite_blockout.fbx` — 14,412 bytes;
- SHA-256 `7006d6ed729a4acc5a6b89bf72fd3c7769813aa277a335e19c6ebea543aa3867`;
- proof job `artifacts/toolchains/blender/jobs/elite_blender_smoke/result.json`.

### Unreal

`dimwit.toolchains.unreal` provides:

- project/engine/Editor/UBT/UAT discovery with `DIMWIT_UNREAL_ROOT` override;
- allowlisted build targets, platforms, configurations, commandlet names, and arguments;
- repository-confined Unreal Python scripts;
- Editor commandlet, Python automation, C++ build, cook, stage, pak, archive, and package plans;
- Epic `Build.bat` / `RunUAT.bat` entrypoints so the bundled .NET SDK is always established;
- argv-only process execution, budgets, complete logs, atomic receipts, and output-tree hashes;
- plan-only behavior unless mutation is explicitly enabled.

Verified against Unreal **5.8.0**. The live `WanefallGreyboxEditor Win64 Development` build passed through
Epic's bundled .NET 10.0 runtime. Proof job:
`artifacts/toolchains/unreal/jobs/elite_unreal_editor_build_v2/result.json`.

### End-to-end studio

`config/studio_pipeline.json` is a validated, acyclic, 22-node game-production graph covering:

1. Blender/Unreal preflight;
2. gameplay C++ compile proof;
3. active character policy and source chain;
4. fidelity, rigging, and animation;
5. environments, materials, VFX, audio, and flagship world dressing;
6. movement, weapons, HUD, BR loop, accessibility/input, optics, and intent conformance;
7. real-game runtime validation;
8. BuildCookRun packaging and packaged smoke;
9. performance, bot balance, progression, and settings persistence;
10. self-metrics, VCS/build/proof/contract integrity, and final studio review.

The scheduler is resumable, proof-sensitive, budgeted, fail-fast, and critical-path-aware. Completed nodes whose
proofs disappear revert to `PROOF_MISSING`. No node can promote beyond `PROMOTED_TO_REVIEW`.

The real preflight checkpoint is recorded at:
`artifacts/studio/wanefall_elite_full_game/state.json`.

## Commands

```powershell
# Inspect the entire graph; performs no mutation
python dimwit.py studio --status

# Run up to three ready nodes within six cost units
python dimwit.py studio --execute --max-nodes 3 --max-cost 6

# Inspect the next evidence-ranked recursive repair candidates
python dimwit.py improve
```

Direct Blender/Unreal execution is also registered through Dimwit's capability registry. MCP callers remain
read-only by default and require the explicit mutation environment gates documented in the main elite audit.

## Honest boundary

These capabilities make the machinery capable of building the game end to end; they do not claim that every
node is currently fresh or accepted. The studio state remains partial until the real live-capture, optics,
package, performance, balance, progression, and settings gates are regenerated and pass.
