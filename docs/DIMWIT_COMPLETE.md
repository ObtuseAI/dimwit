# DIMWIT — Complete: an all-in-one, proof-driven, autonomous game builder

Status as of 2026-06-26: **engine complete + certified**. One command (`python dimwit.py`) drives every
capability; a 107-validator fail-closed harness certifies it; the open-gap audit (G1–G15) is closed or honestly
mitigated. Final certification: **101 / 107 validators PASS** — the only non-passing items are (a) the in-game
rigged character's quality, which is the first WANEFALL task (re-rig the handcrafted topology), and (b) honest
environment-gated BLOCKED (no live PIE running, a Niagara Python-API limit).

## What Dimwit is now

| Layer | Capability |
|---|---|
| **Front door** | `dimwit.py` — `status·hud·health·validate·handcraft·roster·eyes·operate·director·review·loop·build` |
| **Observability** | `dimwit/hud.py` — console + HTML dashboard (capabilities, validation, ledgers, roster, gaps) |
| **Autonomy** | `dimwit/scheduler.py` — always-on heartbeat / full autonomous build+validate ticks (lockfile, abort, deadline, persistent breaker) |
| **Proof pipelines** | 7 production pipelines (character_fidelity, rigging, animation, environment, vfx, audio, materials) on the recursive `plan→execute→QA→repair→ledger→gate` backbone; repair now learns from the verdict |
| **Validation** | `dimwit/pipelines/validation*.py` — **107 fail-closed validators / 11 domains**, hash-chained ledger + watermark, golden corpus, never-silently-PASS |
| **Optics** | `dimwit/optics.py` — GLM-5V semantic vision **fused with** pixel-truth + video/temporal (`judge_motion`); wired as harness validators |
| **Live desktop** | `dimwit/desktop_eyes.py` (PrintWindow GPU-correct capture + video) · `dimwit/desktop_hands.py` (guarded ctypes control) · `dimwit/live_operator.py` (perceive→think→act→verify→ledger, self-correcting) |
| **Geometry** | `dimwit/geometry_backends.py` — pluggable hi3d→triposr→**primitive offline fallback** (never hard-stops without the cloud) |
| **Elite topology** | analyze + Quadriflow/voxel retopo + high→low NORMAL/AO bake = clean deformable quad topology + handcrafted detail; **roster 8/8 deformation-ready** |
| **Finishing** | `scripts/ue/ue_lod_collision.py` — real UCX convex collision + LODs |

## Audit gaps — closed / mitigated
- **Closed + verified:** G2 (vision-LLM in the gate), G3 (geometry fallback), G6 (persistent breaker), G7 (scheduler),
  G8 (HUD), G9 (UCX collision), G11 (repair-with-new-info), G14 (one CLI), G15 (provenance source verification),
  topology+handcraft, eyes/hands/optics/operator.
- **Mitigated/honest:** vfx (real template duplicate; dynamic color is a per-spawn User param — standard practice),
  G5 (video validator built; gates on a live PIE window), field-aligned retopo (voxel-quad is the reliable
  deformation-ready baseline; field-aligned is an instant-meshes quality follow-up).

## Resume WANEFALL here
The harness is already pointing at the first task: `optics_character_semantic` FAILs because the **in-game rigged
character still uses the old disfigured rig**. The fix is to **re-rig the handcrafted clean low-polys** (already
produced under `artifacts/handcraft/SM_Char_0N_*/`) onto SK_Mannequin, import them + the baked maps, and repoint
materials — then the optics validator goes green and the morphing/disfigurement is gone in-game.

## Run it
```
python dimwit.py status            # glance
python dimwit.py build             # validate everything + refresh HUD
python dimwit.py loop --full --interval 3600   # autonomous, continuous
python dimwit.py handcraft <mesh.glb> [name]   # dense -> clean quads + baked maps
```
