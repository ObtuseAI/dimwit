# ROSTER_FIDELITY_V1 — Design

**Date:** 2026-07-04
**Horizon:** 2 (content)
**Bundle:** rig + animation certification for the full active WANEFALL roster
**Status:** approved design, pre-implementation

## Goal

Bring all 14 **active** roster characters — 6 humanoids + 8 mechs — to **deformation-free, in-match animated** fidelity, and gate that fidelity in the validation suite. Static Nanite display meshes are already at shipped fidelity (~80MB uassets, dechromed) for all 16; this bundle closes the rig/animation gap that separates a display mesh from a shipped playable.

## Scope

**In scope (14 active characters):**
- Humanoids (6): `zythan`, `qorin`, `therak`, `ullio`, `kelous`, `nexor`
- Mechs (8): `mech_01_glaciera` … `mech_08_nightwire`

**Out of scope:**
- `vorlax` (01) and `ekris` (02) — QUARANTINED by operator (hand/right-arm deformation), `replacement_required: false`, capacity rebalanced to mechs. Remain failure-fixture only. **Not touched. Not un-quarantined.**
- Custom mech skeleton / bespoke mech AnimBP (rejected: mechs are bipeds, retarget to SK_Mannequin fine — YAGNI).
- Static-mesh fidelity (already shipped).

## Key facts established

- All 8 humanoid `_Rig.uasset` skeletal meshes already exist on the SK_Mannequin skeleton; `animation` proven on ekris (ABP_Manny assigned, 20+ compatible anims drive it free).
- Mechs are **bipedal, Mannequin-topology** (head, torso, 2 arms, 2 legs, upright) — confirmed from render inspection (Glaciera, Pyroclast). They retarget to SK_Mannequin and reuse the humanoid rig+anim machinery.
- Mechs currently have **no** rig/anim path: absent from both `ASSET_FOR` maps, no decimated skinning mesh in `ue_staging_sym`, no `_Rig` asset.

## Architecture

Extend the two existing, proven pipelines (`rigging.py`, `animation.py`) to cover all 14 active characters through **one shared SK_Mannequin retarget**. Add a rigid-weight mode for hard-surface mechs. Certify each character's rig + anim + deformation, and gate the full active roster in the suite.

### Components

1. **`blender_scripts/rig_to_mannequin.py` — add `rigid=true` mode.**
   Each vertex assigned 100% to its single nearest bone (no smooth blend). Keeps mech armor plates rigid instead of stretching like cloth under organic automatic weights. Humanoids continue to use smooth automatic weights (`rigid=false`, default).

2. **`rigging.py` — extend to 14.**
   - Extend `ASSET_FOR` with the 8 mech keys → `SM_Char_Mech_0N_Name`.
   - Per-character `rigid` flag: mechs `true`, humanoids `false`.
   - Mech prerequisite: decimated skinning glb in `ue_staging_sym/<Asset>.glb` (BlockedError if absent — existing pattern).

3. **Mech skinning meshes — new generation step.**
   Decimate the 8 full-Nanite mech meshes to ~45k symmetric glb in `artifacts/ue_staging_new` → `ue_staging_sym/`, mirroring how humanoid skinning meshes were produced. The full Nanite mesh stays the static display; the decimated mesh is skinning-only.

4. **`animation.py` — extend to 14.**
   Extend `ASSET_FOR` with the 8 mech keys. No logic change: once a mech is skinned to SK_Mannequin, ABP_Manny + AnimStarterPack drive it for free.

5. **Suite validators — new `character_roster_fidelity` domain.**
   Per active character (14): rig cert (skeletal on SK_Mannequin) + anim cert (ABP assigned, ≥1 compatible anim) + deformation cert (`deformation_score ≥ 0.85`). Plus a **roster-coverage gate**: every active roster character (from `character_roster` policy) is certified — no active character silently uncovered.

## Data flow

```
static Nanite mesh (display, untouched)
  → decimate → ue_staging_sym/<Asset>.glb (skinning)
  → Blender auto-rig to SK_Mannequin  (smooth | rigid)
  → <Asset>_rigged.fbx
  → UE import skeletal on SK_Mannequin → CharactersRigged/<Asset>_Rig
  → animation: assign ABP_Manny (+ enumerate compatible anims)
  → pose-capture stress set (bind + ≥3 stress poses) → PNGs
  → deformation_verdict ≥ 0.85
  → cert JSON
  → suite validator reads cert (fail-closed on missing/stale)
```

## Fail-closed / gates

- **Never weaken.** `DEFORM_FLOOR = 0.85` held for all 14 — mech rigid-weighting is tuned to hit it; the gate is not lowered for mechs.
- Absent pose captures → deformation NOT validated (never a silent pass) — existing behavior.
- Skeleton mismatch → hard gate (no ABP reuse possible) — existing behavior.
- New validators fail-closed on missing/stale cert JSON.
- **Clause 2 (headless render law):** mech deformation-capture must render saved rigged content, not a session-spawned actor with default material. Verify the mech capture uses the same saved-content path the humanoid captures used before trusting a mech deformation score.
- No input injection anywhere in this bundle → background-safe (Clause 3 N/A).
- Doctrine ceiling stays PROMOTED_TO_REVIEW; gates added/hardened only.

## Testing / build order (RED-first)

1. **Pilot Glaciera (mech_01).** Write the mech roster-fidelity validator first (watch it go RED) → decimate → rigid-rig → UE import skeletal → anim assign → deformation capture → certify → GREEN. Proves the entire mech track on ONE character before scaling.
2. Decimate + batch rig+anim the remaining 7 mechs.
3. Refresh the 6 active humanoids through the deformation cert (machinery ready; may just be run + certify).
4. Wire the 14-character suite validators + roster-coverage gate.
5. Full-suite green landing (self_metrics tail) + push both repos.

**pytest units:**
- `rigid=true` mode produces single-influence (max_influences == 1) weights.
- `ASSET_FOR` (both pipelines) covers all 14 active characters.
- roster-fidelity validator gates a missing/stale cert (fail-closed).
- roster-coverage gate fails if any active roster character lacks a cert.

## Risks

- **Mech joint gaps.** Rigid per-plate weighting can show gaps at elbows/knees under extreme poses; deformation score measures stretch, not gaps, so gaps may pass the gate but look wrong. Mitigation: pilot Glaciera render is eyeballed before scaling; if gaps are unacceptable, add a hybrid (rigid plates + smooth-weighted joint sleeves) — deferred unless the pilot demands it.
- **Decimation quality.** A bad mech decimation could break skinning. Mitigation: reuse the proven humanoid decimation path; pilot proves it.
- **Fallback.** If mech rigid-weighting cannot hit 0.85, ship the 6 humanoids as V1 and split mechs to V2 (Approach 3) rather than lower the gate.
