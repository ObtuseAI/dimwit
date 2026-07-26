# MetaHuman Character Utilization Gate Design

## Purpose

WANEFALL has eight high-detail Hi3D character GLBs, imported Nanite character assets, staged/symmetric GLBs, handcrafted retopo FBXs, and rigging evidence. The current build loop does not yet prove that those 3D character assets are being routed into a MetaHuman-compatible transformation lane.

This slice adds a fail-closed MetaHuman utilization gate. It does not claim that MetaHuman conversion is complete. It proves whether the inputs are ready, whether the version/license boundaries are respected, and whether actual MetaHuman output evidence exists.

## Local Facts

- WANEFALL project: `C:\Users\developer\Documents\Unreal Projects\WanefallGreybox`
- Unreal Engine association: `5.8`
- Enabled project plugins include `RigLogic`, `LiveLinkControlRig`, and `HairStrands`.
- Engine-level MetaHuman plugins exist under `C:\UE_5.8\Engine\Plugins\MetaHuman`.
- Eight Hi3D source GLBs and eight character fidelity records exist in Dimwit artifacts.
- Eight handcrafted retopo FBXs exist in Dimwit artifacts.
- No completed MetaHuman output evidence was found yet.

## Version Gate

Epic’s MetaHuman DNA Calibration repository states that characters created in Unreal Engine 5.6 should use MetaHuman for Maya, and that the DNA Calibration repository remains compatible with characters created in Unreal Engine 5.5 or earlier.

Because WANEFALL is currently UE 5.8, direct use of the public MetaHuman DNA Calibration repository is classified as `BLOCKED_UNREAL_VERSION` unless a specific UE 5.5-or-earlier MetaHuman DNA source is proven. The recommended route is MetaHuman for Maya / UE 5.8 MetaHuman tooling.

## License Gate

- Character DNA Addon / Poly Hammer: `REFERENCE_ONLY`, GPL risk. No GPL code may be copied into WANEFALL.
- Epic MetaHuman DNA Calibration: `OFFICIAL_REFERENCE_WITH_VERSION_GATE`, Epic custom MetaHuman DNA Calibration license. Do not redistribute Epic tooling inside WANEFALL runtime.
- Generated WANEFALL scripts in this slice are original Dimwit/WANEFALL code.

## Architecture

Add `dimwit/pipelines/metahuman_utilization.py`.

The module writes:

- `artifacts/metahuman_utilization/metahuman_utilization_audit.json`

The audit records:

- Unreal engine association and version-gate classification.
- MetaHuman-related project and engine plugin availability.
- Per-character source GLB, character fidelity, retopo, rig, and imported asset evidence.
- External reference license/adoption decisions.
- Whether actual MetaHuman output evidence exists.

Add a validation domain `metahuman_character_pipeline` with fail-closed gates:

- `metahuman_audit_fresh`
- `metahuman_source_3d_assets_ready`
- `metahuman_version_gate_respected`
- `metahuman_license_boundaries_clean`
- `metahuman_transform_output_evidence_present`

The first four should pass when the source pipeline is properly prepared and legally bounded. The final gate should remain `BLOCKED` until real MetaHuman output evidence is present.

## Expected First Result

Expected status: `PARTIAL_BLOCKED_MISSING_METAHUMAN_OUTPUT`

That is the honest outcome: WANEFALL has source character assets ready for the MetaHuman transformation lane, but no completed MetaHuman character output is proven yet.

## Handoff

Mirror the audit JSON, session report, docs, changed source files, and validation output into `C:\Users\developer\Desktop\Shared Folder`.
