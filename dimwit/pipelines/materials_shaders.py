"""Materials/shaders pipeline — authors the WANE master shading layer + applies a consistent de-chrome
treatment across assets.

WANE = the game's decay-force identity: motion verbs Crystallize/Erode/Snap; teal/blue energy seams;
"saturation = truth". This pipeline builds, via the canonical UE driver `scripts/ue/ue_materials_build.py`:

  - MF_Wane (Material Function): de-chrome satin metallic default + a teal/blue emissive SEAM mask
    (Fresnel * AO, HDR-safe ~1.0) + a saturation control on base color. Outputs BaseColor / Metallic /
    Roughness / EmissiveColor so it can be reused as a node across assets.
  - M_WaneSurface (master Material): calls MF_Wane and wires its outputs to the material properties,
    recompiles + saves.
  - (optional) retargets character MICs MetallicFactor -> satin for a uniform de-chrome read.

QA is STRUCTURAL + metric-based (honest proof the assets were authored and compiled — no screenshot
required): MF_Wane exists with all 4 outputs, M_WaneSurface exists with all 4 properties connected and
compiled, and (when requested) N assets were retreated. Authoritative; may FAIL but never silently PASS.

Import-safe: only stdlib + base imports at module top; all UE work happens inside methods via subprocess.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
DRIVER = ROOT / "scripts/ue/ue_materials_build.py"
RESULT = ART / "materials_build_result.json"

# WANE energy seam color (teal/blue) + de-chrome / saturation defaults.
DEFAULT_SEAM = (0.0, 0.8, 1.0)
DEFAULT_METALLIC = 0.35
DEFAULT_SATURATION = 1.15


class MaterialsShadersPipeline(ProductionPipeline):
    name = "materials_shaders"
    kind = "material"

    def plan(self, task: dict) -> dict:
        if not UE_CMD.exists():
            raise BlockedError(f"UnrealEditor-Cmd not found: {UE_CMD}")
        if not UPROJECT.exists():
            raise BlockedError(f"uproject not found: {UPROJECT}")
        if not DRIVER.exists():
            raise BlockedError(f"materials driver missing: {DRIVER}")

        seam = task.get("seam", DEFAULT_SEAM)
        try:
            seam = tuple(float(x) for x in seam)
            if len(seam) != 3:
                raise ValueError
        except (TypeError, ValueError):
            raise BlockedError(f"seam must be an RGB triple, got {task.get('seam')!r}")

        metallic = float(task.get("metallic", DEFAULT_METALLIC))
        if not 0.0 <= metallic <= 1.0:
            raise BlockedError(f"metallic out of range 0..1: {metallic}")
        saturation = float(task.get("saturation", DEFAULT_SATURATION))

        # optional retarget list; validated lightly here, existence proven by the driver/QA
        assets = task.get("assets", [])
        if isinstance(assets, str):
            assets = [a.strip() for a in assets.split(",") if a.strip()]
        assets = [str(a) for a in (assets or [])]

        return {
            "asset_id": str(task.get("asset_id", task.get("name", "wane_master"))),
            "seam": seam, "metallic": metallic, "saturation": saturation, "assets": assets,
        }

    def execute(self, plan: dict) -> Artifact:
        if RESULT.exists():
            RESULT.unlink()
        seam = plan["seam"]
        script_arg = (
            f"-ExecutePythonScript={DRIVER} "
            f"seam_r={seam[0]} seam_g={seam[1]} seam_b={seam[2]} "
            f"metallic={plan['metallic']} saturation={plan['saturation']}"
        )
        if plan["assets"]:
            script_arg += f" assets={','.join(plan['assets'])}"
        script_arg = script_arg.replace("\\", "/")  # UE mis-parses backslash paths via subprocess quoting
        cmd = [str(UE_CMD), str(UPROJECT), script_arg,
               "-unattended", "-nosplash", "-nopause", "-stdout"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        rec = {}
        if RESULT.exists():
            rec = json.loads(RESULT.read_text(encoding="utf-8"))

        return Artifact(
            asset_id=plan["asset_id"], kind=self.kind, data=rec,
            provenance={
                "source": "Dimwit scripts/ue/ue_materials_build.py (UE 5.8 MaterialEditingLibrary authoring)",
                "license": "Epic EULA (engine-authored material assets, in-project)",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        if not r or r.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=bool(r.get("error")),
                           issues=[r.get("error", "driver produced no result JSON")],
                           detail={"raw": r})
        mf = r.get("mf", {}) or {}
        master = r.get("master", {}) or {}
        checks = {
            "mf_wane_created": bool(mf.get("exists")),
            "mf_four_outputs": len(mf.get("outputs", [])) == 4,
            "master_created": bool(master.get("exists")),
            "master_four_props_connected": len(master.get("connected", [])) == 4,
            "master_compiled": bool(master.get("compiled")),
        }
        # only gate on retreated assets when the task actually requested some
        if plan.get("assets"):
            checks["assets_retreated"] = (r.get("retreated_ok", 0) == r.get("retreated_total", -1)
                                          and r.get("retreated_total", 0) > 0)
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        return Verdict(
            score=score, passed=all(checks.values()), issues=issues,
            detail={"checks": checks, "mf_expr": mf.get("expr"),
                    "retreated": f"{r.get('retreated_ok', 0)}/{r.get('retreated_total', 0)}",
                    "params": r.get("params")},
            evidence=[str(RESULT)] if RESULT.exists() else [],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # the driver deletes + re-authors MF_Wane / M_WaneSurface each run, so it is idempotent;
        # re-running clears any partial state (e.g. a missed connect on a flaky first compile).
        return self.execute(plan)
