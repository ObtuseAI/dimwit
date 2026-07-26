"""Render the WANEFALL_DIMWIT_*.md doc set into the WanefallGreybox/docs folder from the real Dimwit
configs, so every required doc exists with real, consistent content (policy prose + the structured rules
+ a pointer to the enforcing config/code). The big report + separation doctrine are hand-authored.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\docs")
DOCS.mkdir(parents=True, exist_ok=True)


def cfg(name):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def vcfg(name):
    return json.loads((ROOT / "validators" / name).read_text(encoding="utf-8"))


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


def kv(d):
    out = []
    for k, v in d.items():
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        out.append(f"- **{k}**: {v}")
    return "\n".join(out)


docs = {}

docs["WANEFALL_DIMWIT_CANONICAL_IDENTITY.md"] = f"""# WANEFALL — Dimwit Canonical Identity

**Canonical name:** Dimwit
**Role:** WANEFALL-specific autonomous asset/build operator
**Derived from:** Blunder (concepts only — no shared mutable state)

{kv(json.loads((ROOT / 'state/dimwit_identity.json').read_text(encoding='utf-8')))}

Dimwit is **not** a Blunder replacement, not a shared branch, not a generic asset scraper, not a random
AI content dumper, and is **not allowed to auto-promote unvalidated assets or bypass dual-gate validation**.
"""

docs["WANEFALL_DIMWIT_ASSET_LIFECYCLE.md"] = f"""# WANEFALL — Dimwit Asset Lifecycle

Machine-readable lifecycle (`Dimwit/config/asset_lifecycle.json`, enforced by `dimwit.engine.run_asset_task`).

**States:** {", ".join(cfg('asset_lifecycle.json')['states'])}

**Dimwit may autonomously reach:** {", ".join(cfg('asset_lifecycle.json')['autonomous_terminals'])}

**Operator-gated (never reached autonomously):** {", ".join(cfg('asset_lifecycle.json')['operator_only_states'])}

> {cfg('asset_lifecycle.json')['rule']}
"""

docs["WANEFALL_DIMWIT_ASSET_TASK_SCHEMA.md"] = f"""# WANEFALL — Dimwit Asset Task Schema

`Dimwit/config/asset_task_schema.json` (modeled by `dimwit.core.AssetTask`).

## Fields
{kv(cfg('asset_task_schema.json')['fields'])}

## Supported asset types
{bullets(cfg('asset_task_schema.json')['supported_asset_types'])}
"""

docs["WANEFALL_DIMWIT_STYLE_LAW.md"] = f"""# WANEFALL — Dimwit Style Law

The WANEFALL identity Dimwit enforces deterministically (`dimwit.core.evaluate_style_law`,
`Dimwit/config/wanefall_style_law.json`). Hard-fails on forbidden identity traits.

## Required
{bullets(cfg('wanefall_style_law.json')['required'])}

## Forbidden
{bullets(cfg('wanefall_style_law.json')['forbidden'])}

## Enforced identity traits
- **Required identity:** {", ".join(cfg('wanefall_style_law.json')['required_identity_traits'])}
- **Forbidden identity (hard fail):** {", ".join(cfg('wanefall_style_law.json')['forbidden_identity_traits'])}

Proof: the flawed test candidate (magenta + near-black blob + ornament clutter) was **REJECTED** by the
style gate even after its average score crossed the promotion threshold.
"""

docs["WANEFALL_DIMWIT_PROVENANCE_AND_LICENSE_POLICY.md"] = f"""# WANEFALL — Dimwit Provenance & License Policy

`Dimwit/config/provenance_policy.json` (fail-closed pre-gate `dimwit.core.evaluate_provenance`).

**Classes:** {", ".join(cfg('provenance_policy.json')['classes'])}
**Promotable:** {", ".join(cfg('provenance_policy.json')['promotable_classes'])}

## Rules
{bullets(cfg('provenance_policy.json')['rules'])}

> {cfg('provenance_policy.json')['hard_fail']}
"""

docs["WANEFALL_DIMWIT_REFERENCE_TO_ASSET_INTAKE.md"] = f"""# WANEFALL — Dimwit Reference/Image-to-Asset Intake

`Dimwit/validators/reference_intake_schema.json`.

## Accepts
{bullets(vcfg('reference_intake_schema.json')['accepts'])}

## Extracts
{bullets(vcfg('reference_intake_schema.json')['extracts'])}

**Output:** {vcfg('reference_intake_schema.json')['output']}
"""

docs["WANEFALL_DIMWIT_WANEFALL_TRANSLATION_ENGINE.md"] = f"""# WANEFALL — Dimwit Translation Engine

> {cfg('wanefall_translation_rules.json')['law']}

## Example translation
```json
{json.dumps(cfg('wanefall_translation_rules.json')['example'], indent=2)}
```

- **Always keep if present:** {", ".join(cfg('wanefall_translation_rules.json')['always_keep_if_present'])}
- **Always reject:** {", ".join(cfg('wanefall_translation_rules.json')['always_reject'])}
"""

docs["WANEFALL_DIMWIT_GENERATION_BACKENDS.md"] = f"""# WANEFALL — Dimwit Generation Backends

`Dimwit/config/generation_backends.json`. Backends are modular adapters; V1 requires **no unavailable
external models** — adapters record intent and call the existing WANEFALL pipeline when present.

## Initial backends
{bullets(cfg('generation_backends.json')['initial'])}

## Optional future backends
{bullets(cfg('generation_backends.json')['optional_future'])}

## Existing WANEFALL pipeline hooks
{kv(cfg('generation_backends.json')['existing_wanefall_pipeline_hooks'])}
"""

docs["WANEFALL_DIMWIT_BLENDER_BUILDER_INTERFACE.md"] = f"""# WANEFALL — Dimwit Blender Builder Interface

`Dimwit/blender_scripts/dimwit_blender_asset_builder_interface.py` + `Dimwit/config/blender_asset_builder_contract.json`.

A single generalized contract for every asset class. `plan_build(spec)` is **headless-safe** (no `bpy`
needed) so the engine can validate the contract; `build()` delegates to a real Blender session / the
existing hostile-construct script when `bpy` is available.

{kv(cfg('blender_asset_builder_contract.json'))}
"""

docs["WANEFALL_DIMWIT_UNREAL_IMPORTER_INTERFACE.md"] = f"""# WANEFALL — Dimwit Unreal Importer Interface

`Dimwit/config/unreal_import_contract.json`. Integrates with the existing `WanefallBlenderImport`
commandlet path when safe. **Autonomous imports go to a STAGING path only**; active-slice import requires
operator approval.

## Input fields
{bullets(cfg('unreal_import_contract.json')['input_fields'])}

- **Staging destination:** {cfg('unreal_import_contract.json')['staging_destination']}
- **Rule:** {cfg('unreal_import_contract.json')['rule']}
"""

docs["WANEFALL_DIMWIT_ASSET_VALIDATION_GATES.md"] = f"""# WANEFALL — Dimwit Asset Validation Gates

`Dimwit/config/asset_validation_gates.json` (run by `dimwit.engine.run_all_gates`).

**Gates:** {", ".join(cfg('asset_validation_gates.json')['gates'])}
**Hard gates:** {", ".join(cfg('asset_validation_gates.json')['hard_gates'])}
**Promotion threshold:** {cfg('asset_validation_gates.json')['promotion_threshold']}

> {cfg('asset_validation_gates.json')['rule']}

Every gate emits its own validation JSON; the promotion verdict aggregates them and is **review-only**
(Dimwit never auto-promotes to the active slice).
"""

docs["WANEFALL_DIMWIT_RECURSIVE_ASSET_MUTATION_LOOP.md"] = f"""# WANEFALL — Dimwit Recursive Asset Mutation Loop

`Dimwit/config/recursive_asset_mutation_loop.json` (implemented in `dimwit.engine.recursive_mutation_loop`).

## Loop
{bullets(cfg('recursive_asset_mutation_loop.json')['loop'])}

## Scored dimensions
{bullets(cfg('recursive_asset_mutation_loop.json')['scored_dimensions'])}

- **Max iterations:** {cfg('recursive_asset_mutation_loop.json')['max_iterations']}
- **Promote threshold:** {cfg('recursive_asset_mutation_loop.json')['promote_threshold']}
- **Keep best:** {cfg('recursive_asset_mutation_loop.json')['keep_best']}

Proof: the flawed test candidate ran multiple mutate→rescore→keep-best iterations; a good candidate
promoted on candidate 0.
"""

docs["WANEFALL_DIMWIT_HUMAN_REVIEW_PACKAGE_STANDARD.md"] = f"""# WANEFALL — Dimwit Human Review Package Standard

`Dimwit/config/human_review_package_schema.json` (built by `dimwit.review.build_review_package`).

## A review package includes
{bullets(cfg('human_review_package_schema.json')['includes'])}

## Human decisions (Dimwit cannot choose these)
{bullets(cfg('human_review_package_schema.json')['human_decisions'])}

> {cfg('human_review_package_schema.json')['rule']}
"""

docs["WANEFALL_DIMWIT_HUMAN_SCREENSHOT_OVERRIDE_POLICY.md"] = f"""# WANEFALL — Dimwit Human Screenshot Override Policy

`Dimwit/config/human_screenshot_override_policy.json` (mandatory).

> {cfg('human_screenshot_override_policy.json')['rule']}

**Precedence (highest first):** {" > ".join(cfg('human_screenshot_override_policy.json')['precedence'])}

This is encoded into every review package manifest.
"""

docs["WANEFALL_DIMWIT_ACTIVE_GAME_BRIDGE_POLICY.md"] = f"""# WANEFALL — Dimwit Active Game Bridge Policy

`Dimwit/config/active_game_bridge_policy.json`.

## Dimwit MAY
{bullets(cfg('active_game_bridge_policy.json')['dimwit_may'])}

## Dimwit MAY NOT
{bullets(cfg('active_game_bridge_policy.json')['dimwit_may_not'])}

- **Human approval required for:** {cfg('active_game_bridge_policy.json')['human_approval_required_for']}
- **Staging paths:** {", ".join(cfg('active_game_bridge_policy.json')['staging_paths'])}
"""

lessons = [json.loads(l)["lesson"] for l in (ROOT / "lessons/dimwit_asset_lessons.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
docs["WANEFALL_DIMWIT_LESSONS_MEMORY.md"] = f"""# WANEFALL — Dimwit Lessons Memory

`Dimwit/lessons/dimwit_asset_lessons.jsonl` (seeded with {len(lessons)} known WANEFALL lessons).

{bullets(lessons)}
"""

for name, body in docs.items():
    (DOCS / name).write_text(body, encoding="utf-8")

print(json.dumps({"docs_written": sorted(docs.keys()), "count": len(docs), "dir": str(DOCS)}, indent=2))
