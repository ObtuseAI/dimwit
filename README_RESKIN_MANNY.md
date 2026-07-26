# Re-skin roster onto the genuine SK_Mannequin (headless, no external auto-rig)

Landed 2026-07-04. Replaces the fragile Blender auto-rig (off-skeleton → floating weapon + bizarre walk) by
re-skinning the alien **geometry** onto Epic's real **SK_Mannequin**, inheriting Manny's proven skin weights.
Result: alien look + native ABP_Manny motion-matched locomotion + working `hand_r`/`hand_l` sockets. All 6
humanoids done; the same pipeline applies to any new geometry-only humanoid FBX.

## Pipeline (order matters)

1. **Export the source body** — `scripts/ue/ue_reskin_export_manny.py` (UE, **FULL RHI**; `-nullrhi` crashes FBX skeletal
   export). Writes `artifacts/reskin_manny/manny_src/SKM_Manny.fbx` (SK_Mannequin armature + skinned ref, 110 vgroups).
2. **Weight-transfer per char** — `blender --background --python scripts/blender/reskin_manny_blender.py -- <char>` (Blender 4.2+).
   Imports Manny + alien geo, aligns (scale to Manny height, feet→z=0, XY-centre), `data_transfer VGROUP_WEIGHTS
   POLYINTERP_NEAREST`, binds via `parent_set(type='ARMATURE')`, exports `<char>_reskin.fbx`, and writes a
   WORKBENCH deform self-check PNG (`<char>_deform.png`). Own-eyes the PNG for collapse.
3. **Import onto SK_Mannequin** — `scripts/ue/ue_reskin_import.py` (UE, FULL RHI). Imports each to
   `/Game/Wanefall/Dimwit/CharactersRigged/<Char>_ReskinManny` selecting the EXISTING SK_Mannequin skeleton
   (shares ABP_Manny). NON-DESTRUCTIVE — never touches the certified `SM_Char_0X_*_Rig`.
4. **Materials** — `scripts/ue/ue_reskin_materials.py` (UE, headless). Copies each certified rig's UV-matched material.

## Gotchas paid in blood

- **UE FBX carries a 0.01 object scale.** Not applying it (transform_apply on armature+mesh) makes the bound
  alien collapse to 1/100 scale (tiny blob). Step 2 bakes it.
- **Bind with the `parent_set(ARMATURE)` operator, not a hand-added modifier** — the operator sets the correct
  parent-inverse so the rest pose is identity; a manual modifier collapses it.
- **Frame the self-check render on the depsgraph-EVALUATED bbox**, not `bound_box` (which ignores the armature
  modifier) — otherwise a healthy mesh looks like a speck and you misread it as a collapse.
- **`-nullrhi` crashes FBX skeletal export** in UE (native crash, no python exception) — use full RHI for
  export + import.
- Facing: the alien FBXs and Manny both extend more toward −Y (same facing) → no flip. If a future asset faces
  the other way, pass `flipy` to the Blender script.

## Runtime wiring (WanefallGreybox, committed d61b216)

`WanefallPrototypeCharacter.cpp` prefers `Zythan_ReskinManny` via `constexpr bPreferReskinnedAlien=true`; the new
`bUsingReskinnedAlien` flag suppresses the SoulCave rock-armour overlay (the reskin has its own silhouette).
`WanefallLobbyCharacter.cpp` deck pawn updated too. **Revert = flip `bPreferReskinnedAlien` false → grey Manny baseline.**

## Still operator-owed (foreground / own-eyes)

- Formal roster MRQ re-cert of the 6 `_ReskinManny` (`scripts/capture/ue_mrq_capture.py mesh=<asset>`, interactive editor +
  8222 bridge + foregrounded window, against `Wanefall_CleanStage_01`).
- In-game own-eyes of the alien player at runtime.
