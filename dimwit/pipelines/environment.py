"""Environment pipeline — procedurally builds a WANE-LINE arena from the modular MapKit.

execute() shells out to the canonical UE driver `scripts/ue/ue_env_build.py`, which creates a brand-new level under
/Game/Wanefall/Maps/Wanefall_GenArena_<n> from scratch: a square floor grid of SM_Kit_Floor, perimeter
SM_Kit_Wall, a deterministic collapse axis (THE WANE LINE — a spine of SM_Kit_Vein down +X bracketed by
SM_Kit_Spire at the contested core), SM_Kit_Ramp verticality, SM_Kit_Pillar landmarks, a seeded asymmetric
SM_Kit_Cover scatter (clear of the spine corridor), flank SM_Kit_Arch portals, N PlayerStarts, and
DirectionalLight + SkyLight + ExponentialHeightFog. Kit collision is forced to CTF_USE_COMPLEX_AS_SIMPLE so the
arena is solid. The driver writes its proof to artifacts/env_build_result.json; QA verifies the FILE (the UE
exit code is unreliable).

QA is STRUCTURAL + metric: level saved, actor_count over threshold, PlayerStarts present, full lighting rig
present, and the WANE LINE actually authored (vein spine + spires). A judge may FAIL but never silently PASS.

Determinism: the same seed -> the same arena (the driver derives all scatter from random.Random(seed)).

TODOs (kept honest; contract intact):
  - full UE5 PCG graph authoring (PCGComponent + procedural graph) instead of deterministic scatter
  - Hi3D hero landmarks at the contested core
  - GLM readability / flow / silhouette QA on a top-down capture
  - World Partition for streamed large arenas
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
DRIVER = ROOT / "scripts/ue/ue_env_build.py"
RESULT = ART / "env_build_result.json"

MAPS_ROOT = "/Game/Wanefall/Maps"
KIT_ROOT = "/Game/Wanefall/Dimwit/MapKit"
# The required identity pieces; the driver records any that are genuinely missing so QA stays honest.
CORE_PIECES = ["SM_Kit_Floor", "SM_Kit_Wall", "SM_Kit_Vein"]

# Minimum readable arena: floor grid + walls + spine veins + cover + lighting + starts.
MIN_ACTORS = 60


class EnvironmentPipeline(ProductionPipeline):
    name = "environment"
    kind = "level"

    def plan(self, task: dict) -> dict:
        # Fail closed: the engine, project, and driver must all exist before we attempt a real build.
        if not UE_CMD.exists():
            raise BlockedError(f"UnrealEditor-Cmd not found: {UE_CMD}")
        if not UPROJECT.exists():
            raise BlockedError(f"uproject not found: {UPROJECT}")
        if not DRIVER.exists():
            raise BlockedError(f"UE driver missing: {DRIVER}")

        n = int(task.get("index", task.get("n", 1)))
        seed = int(task.get("seed", n))
        grid = max(3, int(task.get("grid", 4)))
        starts = max(2, int(task.get("starts", 8)))
        level = str(task.get("level", f"{MAPS_ROOT}/Wanefall_GenArena_{n}"))
        return {
            "n": n, "seed": seed, "grid": grid, "starts": starts,
            "level": level, "kit": KIT_ROOT,
            # informative target floor; QA judges the real count from the result file
            "min_actors": int(task.get("min_actors", MIN_ACTORS)),
        }

    def execute(self, plan: dict) -> Artifact:
        ART.mkdir(parents=True, exist_ok=True)
        if RESULT.exists():
            RESULT.unlink()
        script_args = (
            f"-ExecutePythonScript={DRIVER} "
            f"level={plan['level']} seed={plan['seed']} grid={plan['grid']} "
            f"starts={plan['starts']} kit={plan['kit']} result={RESULT}"
        ).replace("\\", "/")  # UE mis-parses backslash paths via subprocess quoting
        cmd = [str(UE_CMD), str(UPROJECT), script_args,
               "-unattended", "-nosplash", "-nopause", "-stdout"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except Exception as e:
            # Surface as data so QA fails honestly (no silent pass).
            rec = {"error": f"ue_invoke_failed: {type(e).__name__}: {e}", "level": plan["level"]}
            return self._artifact(plan, rec)

        rec = {}
        if RESULT.exists():
            try:
                rec = json.loads(RESULT.read_text(encoding="utf-8"))
            except Exception as e:
                rec = {"error": f"result_parse_failed: {e}"}
        else:
            rec = {"error": "driver produced no result file", "level": plan["level"]}
        return self._artifact(plan, rec)

    def _artifact(self, plan: dict, rec: dict) -> Artifact:
        return Artifact(
            asset_id=str(plan["n"]), kind=self.kind, data=rec,
            provenance={
                "source": f"Dimwit procedural arena from WANEFALL modular MapKit ({plan['kit']}), "
                          f"driver scripts/ue/ue_env_build.py seed={plan['seed']}",
                "license": "WANEFALL first-party MapKit + UE5 (Epic EULA, in-engine)",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        if not r or r.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=bool(r.get("error")),
                           issues=[r.get("error", "no result produced by the UE driver")],
                           detail={"result": r})

        placed = int(r.get("placed", 0))
        starts = int(r.get("starts", 0))
        lighting = r.get("lighting", {}) or {}
        wane = r.get("wane_line", {}) or {}
        min_actors = int(plan.get("min_actors", MIN_ACTORS))

        checks = {
            "level_saved": bool(r.get("saved")),
            "actor_count": placed >= min_actors,
            "has_player_starts": starts >= max(2, int(plan.get("starts", 2))),
            "has_directional_light": bool(lighting.get("directional")),
            "has_sky_light": bool(lighting.get("sky")),
            "has_fog": bool(lighting.get("fog")),
            "wane_line_spine": int(wane.get("vein_count", 0)) >= 3,
            "wane_line_core": int(wane.get("spire_count", 0)) >= 1,
            "no_missing_core_pieces": all(p not in (r.get("missing_pieces") or []) for p in CORE_PIECES),
        }
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        return Verdict(
            score=score, passed=all(checks.values()), issues=issues,
            detail={"checks": checks, "placed": placed, "starts": starts,
                    "by_piece": r.get("by_piece", {}), "missing_pieces": r.get("missing_pieces", []),
                    "wane_line": wane, "lighting": lighting, "level": r.get("level")},
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # The driver is idempotent (new_level rebuilds from scratch + deterministic seed). Bump the grid a
        # little if we fell short on actor count so the next attempt yields a denser, more readable arena.
        if "actor_count" in (verdict.issues or []):
            plan = dict(plan)
            plan["grid"] = min(8, int(plan.get("grid", 4)) + 1)
        return self.execute(plan)
