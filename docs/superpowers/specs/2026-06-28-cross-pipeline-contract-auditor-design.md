# Cross-Pipeline Contract Auditor Design

## Purpose

Dimwit already has a production pipeline base class, a lazy registry, a director, and a large validation suite. The current self-check proves that each registered pipeline imports, instantiates, exposes the four hooks, and has a consistent ledger. That is necessary but not strong enough for autonomous frontier-grade game building.

This slice adds an offline contract auditor that evaluates every registered pipeline and the surrounding orchestration metadata without launching Unreal, Blender, or external services. It turns implicit doctrine into explicit, repeatable checks.

## Scope

The auditor covers all registered pipelines in `dimwit.pipelines.PIPELINES`.

It checks:

- Registry entries resolve to `ProductionPipeline` subclasses.
- The class `name` matches the registry key.
- Pipeline names are unique.
- Pipeline `kind` is non-empty and specific.
- Hook methods are implemented by the concrete class, not inherited unchanged from `ProductionPipeline`.
- Thresholds are valid and never below the base floor.
- `max_repairs` is bounded and non-negative.
- Pipeline ledgers are hash-chain consistent.
- Source files do not attempt to write operator-only terminal states.
- `config/production_pipelines.json` documents every registered pipeline.
- `config/director_tasks.json` only references known pipelines.
- Director tasks provide asset ids, priority, cost, and expected value.

The auditor does not execute pipeline production work. It does not fabricate evidence. Plan probing is intentionally limited to structural metadata because many pipeline plans correctly block when UE, Blender, or source assets are unavailable.

## Architecture

Add a focused module `dimwit/pipelines/contract_auditor.py`.

The module exposes pure functions:

- `audit_registered_pipelines(root)` returns one report dictionary.
- `audit_pipeline_contract(name, target, root)` returns one per-pipeline contract result.
- `validate_contract_report(report)` returns a `Verdict`.

The report is written to `artifacts/pipeline_contracts/pipeline_contract_audit.json` by a small runner function. Validation registry gates then read that result file and fail closed if it is missing, stale, or contains blocking contract violations.

## Validation Integration

Add a new validation domain `pipeline_contracts` with blocker validators:

- `pipeline_contract_audit_fresh`: the auditor result exists and is fresh enough.
- `pipeline_contract_registry_clean`: no broken registered pipeline contracts.
- `pipeline_contract_manifest_parity`: production manifest documents every registered pipeline.
- `pipeline_contract_director_tasks_known`: director tasks reference only known pipelines and include scheduling fields.
- `pipeline_contract_no_operator_only_writes`: source files do not write `HUMAN_ACCEPTED` or `PROMOTED_TO_ACTIVE_SLICE` outside comments/docs/boundary strings.

The source scanner must avoid false positives from boundary documentation and report text. It should flag executable assignment, append, dict, or ledger-style writes that contain operator-only states.

## Error Handling

Missing config files, unreadable JSON, unresolved modules, broken ledgers, and absent audit output are blockers. The auditor records specific issues per check so the director can recurse on concrete work instead of vague red status.

## Testing

Add focused tests in `dimwit/tests/test_pipeline_contract_auditor.py`.

Tests cover:

- A healthy audit includes every registered pipeline.
- Manifest parity catches a registered pipeline missing from `production_pipelines.json`.
- Director task validation catches unknown pipeline references.
- Operator-only source scan ignores comments/report strings but rejects executable writes.
- The validation registry includes the new pipeline contract gates.

## Handoff

Mirror the spec, plan, final report, audit JSON, and changed source files into `C:\Users\developer\Desktop\Shared Folder`.

The expected first run may be red if the manifest lacks `real_game_validation` or another contract issue exists. That red result is useful: it is the auditor finding real drift.
