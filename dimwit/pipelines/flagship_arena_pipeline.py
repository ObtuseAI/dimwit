"""FLAGSHIP_ARENA_ART_PASS_V1 pipeline wrapper — runs the dress + capture-tour UE drivers, then
validates. Kept in its own module so flagship_arena.py stays pure (the registry validators import
only the pure checks from there)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from dimwit.pipelines.base import Artifact, BlockedError, ProductionPipeline, Verdict
from dimwit.pipelines.flagship_arena import DRESS_PATH, TOUR_PATH, validate_flagship_arena


ROOT = Path(__file__).resolve().parents[2]
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
DRESS_DRIVER = ROOT / "scripts/ue/ue_arena_flagship_dress.py"
TOUR_DRIVER = ROOT / "scripts/ue/ue_arena_capture_tour.py"


class FlagshipArenaArtPassPipeline(ProductionPipeline):
    name = "flagship_arena_art_pass"
    kind = "flagship_arena_art_pass"

    def plan(self, task: dict) -> dict:
        if not UE_CMD.exists() or not UPROJECT.exists():
            raise BlockedError("UnrealEditor-Cmd or uproject not found")
        return {"asset_id": str(task.get("asset_id") or "wanefall_arena4v4_flagship"),
                "run_drivers": bool(task.get("run_drivers", True)),
                "timeout": int(task.get("timeout") or 900)}

    def _run_driver(self, driver: Path, timeout: int) -> None:
        cmd = [str(UE_CMD), str(UPROJECT), f"-ExecutePythonScript={driver}",
               "-NoTextureStreaming", "-unattended", "-nopause", "-nosplash", "-stdout"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def execute(self, plan: dict) -> Artifact:
        if plan.get("run_drivers"):
            self._run_driver(DRESS_DRIVER, plan["timeout"])
            self._run_driver(TOUR_DRIVER, plan["timeout"])
        result = validate_flagship_arena()
        return Artifact(asset_id=str(plan["asset_id"]), kind=self.kind,
                        data={"suite_pass": bool(result.get("suite_pass")),
                              "dress": str(DRESS_PATH), "tour": str(TOUR_PATH)},
                        provenance={"source": "local_wanefall_flagship_arena_dress_and_tour",
                                    "license": "operator-owned-game"})

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_flagship_arena()
        issues = []
        for name, check in (result.get("checks") or {}).items():
            if not check.get("passed"):
                issues.extend([f"{name}: {i}" for i in check.get("issues", [])] or [f"{name}: failed"])
        return Verdict(score=1.0 if result.get("suite_pass") else 0.0,
                       passed=bool(result.get("suite_pass")), hard_fail=False, issues=issues,
                       detail={"state": result.get("state"), "checks": result.get("checks")},
                       evidence=[str(DRESS_PATH), str(TOUR_PATH)])

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return artifact
