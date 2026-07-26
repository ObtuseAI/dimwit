# Autonomy Capability Matrix Design

## Purpose

WANEFALL has many strong gates, but the autonomous loop still relies on a human or agent reading scattered reports and deciding what to repair next. This slice adds a repo-native autonomy capability matrix that turns current proof artifacts into ranked, machine-readable recursive repair candidates.

The matrix does not promote work past `PROMOTED_TO_REVIEW`. It does not fabricate gameplay, MetaHuman, or live visual evidence. Missing evidence remains `BLOCKED` or `NEEDS_EVIDENCE`.

## Approach

Build `dimwit/pipelines/autonomy_capability_matrix.py` as a pure offline evidence aggregator. It reads:

- `artifacts/validation/validation_report.json`
- `artifacts/real_game_validation/real_game_validation_result.json`
- `artifacts/metahuman_utilization/metahuman_utilization_audit.json`
- `artifacts/pipeline_contracts/pipeline_contract_audit.json`
- `codex_handoff.json`
- `config/director_tasks.json`
- the WANEFALL Unreal project descriptor

It writes:

- `artifacts/autonomy/autonomy_capability_matrix.json`
- `artifacts/autonomy/recursive_improvement_queue.json`
- `artifacts/autonomy/AUTONOMY_CAPABILITY_FINAL_REPORT_20260628.json`

The matrix includes rows for runtime validation, movement/traversal, weapons, HUD/UI, BR loop, character assets, MetaHuman conversion, environment, VFX/audio, backend/social, action transitions, external references, tool discovery, pipeline contracts, proof integrity, packaging/build, and recursive orchestration.

## Data Shape

Each capability row contains:

- `capability_id`
- `subsystem`
- `required_lane`
- `state`
- `classification`
- `evidence`
- `blockers`
- `source_references`
- `next_action`
- `validation_command`
- `rollback`
- `adoption_mode`
- `license_risk`
- `dependency_risk`
- `version_risk`
- `promotion_threshold`
- `proof_artifact_path`

Each queue candidate contains:

- `rank`
- `title`
- `affected_subsystem`
- `source_reference`
- `expected_improvement`
- `files_likely_affected`
- `validation_command`
- `failure_risks`
- `rollback_notes`
- `promotion_threshold`
- `proof_artifact_path`
- `adoption_mode`
- `dependency_risk`
- `license_risk`
- `version_risk`
- `repeat_guard`

## Reference Boundaries

The embedded reference catalog records the V3 sources as WANEFALL-native extraction inputs only:

- Embody Unreal Engine Source: reference only for remote/runtime command and embodiment debug ideas.
- Character DNA Addon: GPL/reference-only, no implementation copied.
- Epic MetaHuman DNA Calibration: official reference with Epic license and version gate.
- Claude-Code-Game-Studios: MIT workflow reference, not a wholesale agent import.
- Heroic Labs/Nakama: thin adapter or mock-only backend inspiration, no mandatory live service.
- Cocos2d-x: MIT reference-only action/transition patterns, no engine dependency.
- MagicTools: discovery seed only, no blind adoption.

## Validation

Add `autonomy_engine` validators:

- `autonomy_matrix_fresh`
- `autonomy_matrix_covers_required_lanes`
- `autonomy_external_references_classified`
- `autonomy_queue_ranked_actions`
- `autonomy_queue_actions_have_validation_and_rollback`
- `autonomy_no_operator_only_promotions`

These validators fail closed if the matrix is missing, malformed, omits required lanes, lacks ranked actions, lacks validation/rollback commands, or contains operator-only promotion states.

## Scope

This slice installs the dynamic autonomous decision layer. It does not repair crouch, sprint, roll, flip, gun animation, backend production readiness, or MetaHuman output directly. Those become ranked queue candidates with exact validation commands and proof paths.
