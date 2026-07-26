# Dimwit Blunder and Open-Source Adaptation Audit — 2026-07-11

## Outcome

Dimwit now contains two bounded adaptations from the Blunder review:

1. An advisory quality-diversity layer over the recursive-improvement ledger. It assigns stable improvement
   families, measures stagnation and regression pressure, preserves a review-only champion per family, and
   adds diversity as a tie-break after authoritative validator evidence.
2. A fail-closed open-source adoption registry and audit. It scores value, risk, integration cost, license,
   and local presence without downloading, installing, starting services, executing third-party code, or
   giving any source runtime authority.
3. A local-first game-production IDE inspired by Blunder's cohesive Focus Shell interaction model, rebuilt
   around Dimwit's Blender, Unreal, studio DAG, validator evidence, recursive improvement, ecosystem intake,
   and first-party source boundary.

The Dimwit review ceiling remains `PROMOTED_TO_REVIEW`. The diversity planner cannot execute or promote a
candidate. Unknown or unverified licenses are rejected.

## Source inventory reviewed

The actual Git worktree reviewed was:

`C:\Users\developer\Desktop\Shared Folder\Blunder\blunder-private-repo-prepared-20260710`

It is an initialized repository on `main` with no commits yet; all source is currently untracked. Its own safe
baseline passed 20/20 unit tests on 2026-07-11. Later dated review-tree packages were also inspected so that
newer mechanisms were not missed:

- `C:\Users\developer\Desktop\Shared Folder\Blunder\p21-p40-handoff-20260711-143446\review-tree`
- `C:\Users\developer\Desktop\Shared Folder\Blunder-P41-P50-Published-20260711-153224`

These later packages were treated as review snapshots, not as a substitute for a committed source authority.

## Blunder adaptation decisions

| Mechanism | Decision | Dimwit application |
|---|---|---|
| Adaptive compound evolution | **Adapted now** | `dimwit/evolution/diversity.py` adds family diversity, stagnation pressure, advisory cooldown, and a review-only champion archive. |
| Source trust and quarantine | **Partially adapted now** | `dimwit/opensource_adoption.py` and the curated registry add license/risk/local-presence gates. Raw-source quarantine and replay fixtures remain a next slice. |
| Unknown-license scoring | **Rejected** | Blunder currently gives `UNKNOWN` a positive score and treats any positive score as compatible. Dimwit explicitly rejects unknown/unverified licenses. |
| Deterministic validation shards | **Next highest priority** | Adapt confined selectors, repeated execution, normalized output hashes, redaction, timeout/memory limits, and nondeterminism detection around Dimwit's test/validator lanes. |
| Reliability fault drills | **Next highest priority** | Add atomic-replacement, truncated-JSON, stale-identity, budget-exhaustion, and interrupted-resume drills to the studio and improvement controllers. |
| Intent-diff firewall | **Adopt after shard runner** | Bind proposed file hunks to task terms and require review when semantic scope is weak; do not pretend lexical overlap proves intent. |
| Semantic context compiler | **Adopt after shard runner** | AST/term slices and repository-fingerprint caching can reduce context cost while preserving evidence paths. |
| Typed open-tool foundry | **Selective adaptation** | Dimwit's capability registry and MCP gates already overlap. Add permission/risk/idempotency schemas to new tools instead of replacing the existing dispatch surface. |
| Windows validation broker | **Selective adaptation** | Resource-bound external validators are useful, but must be reconciled with Dimwit's existing toolchain process receipts and Unreal/Blender timeout policy. |

## Open-source decisions

The machine-readable registry is `config/opensource_adoption_candidates.json`; the generated evidence report is
`artifacts/ecosystem/opensource_adoption_report.json`.

| Project | Mode | Why |
|---|---|---|
| TripoSR | **Evaluate first** | MIT, already present as a local source scaffold, and its documented memory envelope is compatible with the current 8 GB GPU class. It still requires weight, provenance, quality, topology, texture, and runtime measurements before use. |
| MaterialX | **Evaluate** | Strong portable material contract for Blender/Unreal interchange; prefer existing DCC/engine bindings over a new source build. |
| OpenUSD | **Use engine built-ins** | Best scene/hierarchy interchange candidate, but Blender and Unreal integrations should be audited before adding another build. |
| meshoptimizer | **Evaluate as confined sidecar** | Useful for GLB optimization, LOD, and geometry-budget evidence; compare against Nanite and Unreal import results. |
| Hypothesis | **Reference/test-pattern candidate** | High-value property/state-machine testing for ledgers, resumability, and fail-closed gates. Keep it outside runtime authority and review MPL-2.0 dependency policy before formalizing it. |
| ChiR24 Unreal MCP | **Reference only** | Useful typed native automation patterns; Dimwit's current Unreal bridge stays authoritative and every adopted operation needs a permission review. |
| Blender MCP | **Reference only** | Useful workflow ideas, but arbitrary Python, sockets, downloads, telemetry, and service integrations conflict with Dimwit's default safety boundary. |
| TRELLIS | **Hold** | Strong research candidate, but heavier GPU/storage needs and mixed submodule licensing require a separate feasibility and license audit. |
| OpenTelemetry | **Hold/optional** | Local-only tracing could help long jobs, but the append-only Dimwit receipts remain authoritative and no exporter should be enabled by default. |
| DVC | **Hold** | Adopt only if current manifest/Git LFS lineage measurably fails at model/data scale; no remote writes by default. |
| MLflow | **Hold** | Too much overlap and operational weight for the present ledger/reporting needs; no tracking server is justified yet. |

Primary upstreams evaluated:

- https://github.com/VAST-AI-Research/TripoSR
- https://github.com/microsoft/TRELLIS
- https://github.com/AcademySoftwareFoundation/MaterialX
- https://github.com/PixarAnimationStudios/OpenUSD
- https://github.com/zeux/meshoptimizer
- https://github.com/HypothesisWorks/hypothesis
- https://github.com/ChiR24/Unreal_mcp
- https://github.com/ahujasid/blender-mcp
- https://github.com/open-telemetry/opentelemetry-python
- https://github.com/iterative/dvc
- https://github.com/mlflow/mlflow

## Commands

Launch the Dimwit Studio IDE:

```powershell
python dimwit.py ide
```

The IDE binds only to `127.0.0.1`, uses a random per-process API token, strips the token from the visible URL
into session storage, applies a closed Content Security Policy, and exposes fixed actions only. Its four views
are Forge, Studio, Evolve, and Source. Free-form mission text is stored in browser session storage and cannot
become a process command.

Plan-only ecosystem audit:

```powershell
python dimwit.py ecosystem
```

Write the machine-readable report (still no install or execution):

```powershell
python dimwit.py ecosystem --write
```

Recursive improvement plans now include `diversity_plan`:

```powershell
python dimwit.py improve
```

## Closed boundaries

- No external repository was cloned or installed.
- No weights, assets, packages, or paid services were downloaded or invoked.
- No Blender MCP or Unreal MCP server was installed or started.
- The Dimwit Studio IDE was started only for a bounded browser smoke and stopped afterward.
- No source was promoted from a third-party project into runtime authority.
- No candidate exceeded `PROMOTED_TO_REVIEW`.
- No Git commit, push, deploy, or public action was performed.

## Validation evidence

- Blunder safe baseline: 20/20 unit tests passed.
- Dimwit scoped Ruff: passed for every file in this slice.
- Dimwit test suite: 559 passed, 14 deprecation warnings, 0 failed.
- Capability registry: 21/21 targets resolved.
- Browser smoke: Forge, Studio, Evolve, Source search/read, and an allowlisted ecosystem-audit job all passed.
- Mandatory full validator: 255 PASS, 7 FAIL, 2 BLOCKED, 0 REJECTED. The remaining non-pass results are
  stale/live evidence lanes (animation/front-door proof, optics calibration, runtime/package/performance,
  bot balance, progression, and UI settings), not regressions introduced by this slice.
