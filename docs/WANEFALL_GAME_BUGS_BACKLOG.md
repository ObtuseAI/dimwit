# WANEFALL — Live Game-Bug Backlog (operator-reported 2026-06-26)

DEFERRED by operator: "get dimwit 100% elite and then we will address." These are the in-game defects the
now-being-built ELITE Dimwit (live desktop eyes + hands + image/video optics) should SEE in PIE and fix
properly — not guess at headless. Recorded verbatim-in-intent so nothing is lost.

## Confirmed GOOD
- ✅ Character is **colored correctly** now (the glTF-material reparent + brightened albedo held in-game).

## Defects to fix (after Dimwit is elite)
1. **Mesh is morphed / disfigured / "weirdly reactive"** — the skeletal **skinning/rigging is bad**. The
   nearest-bone / inverse-distance K=4 weights deform the mesh badly during animation. ROOT CAUSE candidate:
   low-quality auto-weights on the 141-bone Mannequin rig. FIX PATH: an elite rig/skin backend (AccuRig/Tripo/
   proper heat or ML weights via the rig_anim_backends registry) + live PIE deformation QA via the new optics.
   *Highest priority — it's the thing that makes the character unevaluable.*
2. **Placeholder polygons still showing on the character** — Engine cube/sphere carapace / debug shapes are
   visible, "super annoying and hard to evaluate character appearance." HideInheritedVisuals isn't catching
   them all (or they're re-added by a prototype visibility-repair pass). FIX: hunt down every inherited/added
   primitive on the pawn and hide/remove; verify with a clean live capture (no stray polys in frame).
3. **Melee weapon does not display** — HeldMelee is sheathed/hidden or not attaching. FIX: attach + show the
   melee on the correct hand/back socket; verify visible in the hold.
4. **Grapple device = "stupid looking cylinder," not on the right spot** — must be attached to the **LEFT
   FOREARM of ALL characters** (forearm bone e.g. `lowerarm_l`, not just a hand socket; built into the base
   pawn so every character inherits it). Replace the procedural cylinder cable with a proper cable/rope visual
   (or hide until a good one exists).
5. **Grapple does not actually pull the player** — only the cable displays; `UpdateGrapple` force/reel is not
   moving the pawn in PIE. FIX: make the pendulum/reel physics actually apply in a running game (verify in PIE
   with live eyes, not headless).
6. **Backflip does not work** — double-tap A airborne → `DoBoostFlip` not firing / no flip.
7. **Evasive roll does not work** — still non-functional.

## Why these wait for elite Dimwit
Items 1,4,5,6,7 are **feel/PIE-runtime** behaviors that CANNOT be verified headless (AnimBP/physics only tick in
a running game). Items 2,3 need a clean live visual check. The elite uplift (live PIE capture + vision/video
optics + guarded editor control + better rig/skin backend) is the tool that makes fixing these reliable and
verifiable, which is exactly why the operator sequenced it first.
