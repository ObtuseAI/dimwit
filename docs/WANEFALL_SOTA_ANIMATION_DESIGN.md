# WANEFALL — State-of-the-Art Animation: the "Organic Alien Handcrafted" System

Operator brief: *"gather all [sources] and you put together the most organic, alien, handcrafted-feeling/
looking."* This is the master plan. Foundation: every alien is skinned to **SK_Mannequin**, so it inherits the
entire UE5 Mannequin animation ecosystem; the SOTA plugins (PoseSearch/Motion Matching, MotionWarping, Chooser,
ContextualAnimation, AnimationLocomotionLibrary, IKRig) are now enabled in the .uproject (needs an editor
restart to load). Everything below is gated through the hardened intent loop and live-validated (own eyes + PIE).

## The core insight
Motion-matching off **human** mocap (GASP/Mixamo/AnimStarterPack) looks **human**. "Organic / alien /
handcrafted" is NOT the source data — it is a deliberate **ALIEN-IFY layer** stacked on top. The system below
gathers the best motion from every source, then transforms it into something that doesn't move like a person.

## 1. Gather all sources — what each contributes
| Source | Contributes | Acquire |
|---|---|---|
| **GASP** (Game Animation Sample) | SOTA motion-matching locomotion + **traversal** (vault/mantle/hurdle/climb), strafe/gait/aim. The base. | Operator adds via Fab/Epic Launcher |
| **AnimStarterPack** (in-project) | Immediate baseline mocap (idle/walk/jog/run/jump/turn) to prove the pipeline now | present |
| **Mixamo** | Broad humanoid + acrobatic library (parkour/swing/flips for the agility set) | Operator downloads clips (free) |
| **AI mocap** (DeepMotion/Rokoko) | Bespoke video→motion for moves no library has | Operator account |
| **Cascadeur** | **HANDCRAFTED**, physics-AI keyframed signature alien moves — the soul (Crystallize/Erode/Snap, idles, taunts) | Operator authors / free tier |
| **ML text-to-motion** (MDM/MotionGPT, MIT) | Generate *novel* non-human motion from prompts — alien gaits that no human mocap contains | local GPU venv |

All land on the alien rigs through one **IK Rig + IK Retargeter** path (modern retarget), feeding one shared
**Motion-Matching (PoseSearch) database** + a Chooser-driven AnimBP.

## 2. The ALIEN-IFY layer (the craft — where human motion becomes organic alien)
Applied on top of the retargeted base, in the species AnimBP / post-process:
1. **Non-human retarget offsets** — bias the IK Retargeter toward the alien's real limb ratios + a non-neutral
   base pose (hunched, digitigrade, asymmetric) so even a "walk" reads creature, not person.
2. **Additive alien layers** — custom additive anims (spine undulation, head micro-tilts, shoulder roll,
   asymmetric limb lead) layered over the matched locomotion via AnimBP additive nodes.
3. **Organic procedural noise** — subtle per-bone Perlin/curve noise + left/right asymmetry (ModifyBone /
   ControlRig post-process) so motion is never robotically perfect = alive. Tuned low (life, not jitter).
4. **Per-species gait warping** — retime/scale the cadence + weight-shift per species (Chooser selects the
   species profile) so Vorlax, Ekris, Zythan… each move distinctly.
5. **Secondary motion** — KawaiiPhysics (MIT) on antennae/appendages/tails/carapace flaps = the organic
   follow-through that sells "living creature." Needs sway bones authored into the rigs.
6. **Handcrafted signature moves** — Cascadeur-authored bespoke actions (the named WANEFALL verbs + idles +
   taunts) hand-keyed for character. This is the "handcrafted" payload; everything else is the substrate.
7. **Traversal warped to geometry** — MotionWarping + ContextualAnimation make the procedural grapple/swing
   (AWanefallPrototypeCharacter) + GASP vault/climb hit real surfaces = the "Spider-Man-with-a-gun" agility.

## 3. Pipeline (Dimwit-orchestrated, UE-executed, loop-gated)
ingest (any source) → IK-Retarget to the alien rig → ALIEN-IFY (additives + noise + gait + secondary) →
Motion-Matching DB build (PoseSearch) → Chooser AnimBP (per-species profile + aim + traversal) → live capture →
hardened-loop fused gate → PROMOTED_TO_REVIEW → human gate.

## 4. "Organic / alien / handcrafted" quality criteria (new loop validators)
The loop must judge the *feel*, not just "it animates":
- **not_generic_human_retarget** — base pose + gait deviate measurably from the stock Mannequin (else it's a
  reskinned human).
- **secondary_motion_present** — appendages/antennae actually sway (delta on sub-bones over a motion clip).
- **organic_asymmetry** — left/right + temporal asymmetry above a floor (perfect symmetry = robotic).
- **per_species_distinct** — species motion signatures differ from each other (no shared-clip uniformity).
- **signature_moves_present** — the handcrafted verbs exist + read.
- **reads_in_motion** — silhouette stays clean + on-model across the motion (needs the MRQ animated-capture
  unlock; until then, PIE + own-eyes).

## 5. Build phases
- **P0 (now, no restart):** this design + the Dimwit animation-assembly framework + the alien-feel criteria.
- **P1 (after editor restart):** IK Rig + IK Retargeter on one alien (Ekris); a Motion-Matching DB + AnimBP from
  AnimStarterPack — prove the SOTA pipeline end-to-end on the Mannequin-skinned alien, live-validated.
- **P2 (operator content):** migrate GASP → motion-matching locomotion + traversal on the aliens.
- **P3 (the craft):** the ALIEN-IFY layer — additives, organic noise, per-species gait, KawaiiPhysics secondary,
  Cascadeur signature moves. Iterate each through the loop until it reads organic/alien/handcrafted.
- **P4:** Mixamo / AI-mocap / ML-text-to-motion for the bespoke move set; per-species variation pass.

## 6. Operator / environment actions needed
1. **Restart the editor** (loads the just-enabled SOTA plugins) — required before P1.
2. **Add GASP** via Fab/Epic Launcher (P2) — Claude cannot download or sign in.
3. (Later) Mixamo clips / AI-mocap account / Cascadeur authoring (P3-P4).
4. **MovieRenderQueue** animated-capture unlock for fully-automated motion QA (else PIE + own-eyes).
