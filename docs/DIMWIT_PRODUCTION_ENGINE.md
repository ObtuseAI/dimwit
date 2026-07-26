# DIMWIT PRODUCTION ENGINE — Master Spec & Roadmap

*Goal (operator): make Dimwit a fully-proofed, recursively self-improving, autonomous game-production engine for
WANEFALL so we can get to **designing and implementing** instead of working in circles. Use UE5 to its full
capability, prefer open-source/free, achieve breakthrough.*

> The architecture research workflow hit the session token limit before emitting its spec; this doc is the
> direct build plan. The framework + first two pipelines are **built and runnable** today.

---

## 1. The "fully-proofed operation"
Every pipeline subclasses `dimwit/pipelines/base.py::ProductionPipeline` and inherits one doctrine loop:

```
plan -> execute -> QA(judge) -> repair(<=max_repairs) -> hash-chained proof ledger -> gate
```

Invariants (never weakened):
- **plan/mock before execute; validate before promote.**
- **QA is authoritative** — GLM 5V vision + pixel-truth + hard metrics. A judge may FAIL but never silently PASS.
- **thresholds ratchet UP only.**
- **autonomous ceiling = `PROMOTED_TO_REVIEW`.** `HUMAN_ACCEPTED` / active-slice promotion is **operator-gated**.
- **provenance fail-closed** (promotable license + recorded source) and an **append-only, hash-chained** ledger
  (`ledger/pipelines/<name>.jsonl`). "Fully proofed" = for every promoted asset there is a tamper-evident proof
  trail with real (not fabricated) QA evidence, and nothing reaches the active slice without the operator.

Run anything:  `python scripts/pipeline/run_pipeline.py --list` · `python scripts/pipeline/run_pipeline.py <name> <asset> [--threshold X]`

---

## 2. Pipelines

| Pipeline | Status | What it does | Proof |
|---|---|---|---|
| **character_fidelity** | **BUILT** | Full-detail **Nanite** import (no decimation) + Nanite material flag + satin de-chrome — closes the in-game≠creation gap | structural (nanite on, flag on, uasset≥10MB, dechromed) + optional GLM matches-creation |
| **rigging** | **BUILT** | Auto-rig static Hi3D mesh → **UE5 Mannequin** skeletal (Blender automatic weights) → reuses `ABP_Manny` | weight coverage ~1.0, ≤4 influences, bones≥50, UE skeletal imported |
| **animation** | **BUILT (VERIFY)** | Reuse **ABP_Manny** on the rigged SK_Mannequin skeletal (hard-gate skeleton compat); roadmap: Motion Matching + IK Retargeter + ML text-to-motion | rig+skeleton-compat+AnimBP+≥1 anim |
| **environment** | **BUILT (VERIFY)** | Procedural **WANE-LINE arena** from the modular MapKit (seeded, deterministic collapse axis); roadmap: full PCG graph + Hi3D landmarks | level+actors+starts+lighting+spine/core |
| **vfx** | **BUILT (VERIFY)** | **Niagara** per WANE verb (Crystallize/Erode/Snap/Hit/Death) by duplicate+parameterize | system created + emitters/params |
| **audio** | **BUILT (VERIFY)** | **TTS banter** (Piper/pyttsx3/SAPI) → UE SoundWaves + MetaSound scaffold | WAV synthesized + imported + loudness |
| **materials_shaders** | **BUILT (VERIFY)** | **MF_Wane** function + M_WaneSurface (seam mask, saturation, de-chrome) | MF_Wane + master material compile ok |

*VERIFY = built + import/self-validated; needs one live UE/Blender run to confirm in-engine ops (verify via the driver's result JSON, not exit code). Orchestrated by `dimwit/director.py` (`scripts/pipeline/run_director.py`).*

Manifest: `config/production_pipelines.json`.

---

## 3. Breakthrough decisions (locked in)
- **Nanite-first characters.** Stop decimating hero meshes; let Nanite render the full ~2M-tri Hi3D geometry.
  The decimation was the root cause of the "coloring gap / looks like shit." (Detail lives in geometry.)
- **No glow/light hacks.** Clean/crisp/handcrafted reads from correct geometry + materials, not per-character lights.
- **The UE5 Mannequin is the rig spine.** Rig every character to `SK_Mannequin` so the entire existing animation
  ecosystem (ABP_Manny, AnimStarterPack, Motion Matching, retargeting) comes for free.
- **GLM 5.2/5V is the autonomous brain+eyes**; UE MCP bridge (`ue_mcp/`) is the live hands; Blender + UE headless
  (`-ExecutePythonScript`, verify via result FILE not exit code) are the deterministic workhorses.
- **Open-source first** (Blender GPL-tool outputs, trimesh MIT, CC0 textures/SFX, MDM/MotionGPT, AccuRig/UniRig
  for rigging) — Hi3D is the only paid dependency (geometry).

---

## 4. Phased build plan
- **Phase 1 (DONE/active): character fidelity.** Framework + `character_fidelity` pipeline built; Ekris proven
  (full Nanite + flag + de-chrome). Next: batch all 8; re-enable GLM matches-creation QA when wanted.
- **Phase 2: rigging → animation.** `rigging` built; run + verify weights, then `animation` (retarget ABP_Manny;
  add Motion Matching; OSS mocap; ML text-to-motion for WANEFALL signature moves).
- **Phase 3: environment.** PCG-driven WANE-LINE arenas + Hi3D landmarks; readability GLM QA.
- **Phase 4: vfx / audio / materials** + the unified **director** (extend `scripts/pipeline/racc_run.py`) that schedules all
  pipelines by expected-value, runs them autonomously to `PROMOTED_TO_REVIEW`, and surfaces a review queue.

---

## 4b. Movement north star — "Spider-Man with a gun"
The rig + animation target: **acrobatic, fluid traversal while aiming/firing**. Four pillars:
1. **Web-swing traversal** = the L1 grapple (built): long-range, unlimited, left-arm cable, **pendulum swing** (rope cancels outward velocity → you arc; reels in for progress; release flings with momentum). Double-tap A cancels into a boost flip. *Status: in C++, tuning exposed; needs a live PIE feel-pass.*
2. **Smooth deformation** = the rig must blend across bones (no rigid 1-bone) so flips/swings look fluid. *Done: `rig_to_mannequin.py` now does inverse-distance K=4 smooth skinning (coverage 1.0, ≤4 influences) headless.*
3. **Aim while acrobatic ("with a gun")** = a **layered AnimBP**: lower body runs/swings/flips from locomotion, **upper body is an Aim Offset** driven by camera pitch/yaw so the gun tracks the crosshair independently. Gun is right-hand, grapple cable is left-hand, so both read at once. *Next: author the layered AnimBP (per-bone blend from `spine_01` up = aim pose) + an AimOffset asset.*
4. **Acrobatic anim set** = run/sprint, jump/double-jump, **flips, wall-run/kick, air-flair, swing pose, landing roll**, + aim poses. *Next: ingest free OSS mocap (Mixamo "swinging"/"flips"/"falling", CMU, Lafan1) via the animation pipeline + IK-Retarget onto SK_Mannequin; layer with Motion Matching (PoseSearch) for fluid blends.*

Honest gap: pillars 1–2 are code/rig (in hand); pillars 3–4 need authored AnimBP + retargeted anim assets + PIE iteration — that's the next animation-pipeline build, not a headless one-shot.

## 5. Known gotchas (carry forward)
- Interchange glTF **nests** `<dest>/<Asset>/StaticMeshes/<Asset>` — `destination_path` = the GROUP folder, never
  include the asset name (else double-nest). Stage the GLB named exactly as the target asset.
- A Nanite mesh that renders **smooth** = it's showing the low-poly **fallback** → the material's base UMaterial
  needs `used_with_nanite=True` (+ re-save). One flag on the shared glTF `M_Default` fixes all imports.
- `get_num_triangles(0)` on a Nanite mesh = the **fallback** count, not the full geometry. Check uasset size.
- Headless screen-grab capture (CopyFromScreen) breaks when the machine **locks**; use offscreen file capture
  (`-RenderOffScreen` + a capture director writing PNGs) instead.
- Verify headless UE jobs by their **result JSON file**, not the process exit code.
