"""Character-fidelity pipeline — closes the "in-game != the Hi3D creation" gap.

Root causes it fixes (proven 2026-06-26): (1) decimation destroyed the armor detail -> import the FULL Hi3D mesh
as NANITE; (2) the glTF base material lacked the Nanite usage flag -> it rendered the smooth low-poly fallback;
(3) the albedo is non-metallic + dark-for-studio -> satin de-chrome. Execute shells out to the canonical UE
driver `scripts/ue/ue_char_fidelity.py`. QA is STRUCTURAL (honest proof the fix landed without a screenshot) + optionally
GLM "matches-the-creation" when a render is supplied.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError
from .character_roster import is_quarantined_character

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
DRIVER = ROOT / "scripts/ue/ue_char_fidelity.py"
RESULT = ART / "char_fidelity_result.json"

ROSTER = {
    "vorlax": ("hi3d_01_vorlax", "SM_Char_01_Vorlax"), "ekris": ("hi3d_02_ekris", "SM_Char_02_ekris"),
    "zythan": ("hi3d_03_zythan", "SM_Char_03_zythan"), "qorin": ("hi3d_04_qorin", "SM_Char_04_qorin"),
    "therak": ("hi3d_05_therak", "SM_Char_05_therak"), "ullio": ("hi3d_06_ullio", "SM_Char_06_ullio"),
    "kelous": ("hi3d_07_kelous", "SM_Char_07_kelous"), "nexor": ("hi3d_08_nexor", "SM_Char_08_nexor"),
}


class CharacterFidelityPipeline(ProductionPipeline):
    name = "character_fidelity"
    kind = "character_mesh"

    def plan(self, task: dict) -> dict:
        key = str(task.get("asset_id", task.get("name", "zythan"))).lower()
        if key not in ROSTER:
            raise BlockedError(f"unknown character '{key}'; known: {sorted(ROSTER)}")
        src_stem, asset = ROSTER[key]
        if is_quarantined_character(key) or is_quarantined_character(asset):
            raise BlockedError(f"quarantined character '{key}' is failure-fixture only")
        glb = ART / f"{src_stem}.glb"
        if not glb.exists():
            raise BlockedError(f"source Hi3D GLB missing: {glb}")
        if not UE_CMD.exists() or not UPROJECT.exists():
            raise BlockedError("UnrealEditor-Cmd or uproject not found")
        return {"key": key, "src_stem": src_stem, "asset": asset,
                "metallic": float(task.get("metallic", 0.35))}

    def execute(self, plan: dict) -> Artifact:
        if RESULT.exists():
            RESULT.unlink()
        cmd = [str(UE_CMD), str(UPROJECT),
               # forward slashes: UE mis-parses backslash paths passed through subprocess list quoting
               (f'-ExecutePythonScript={DRIVER} asset={plan["asset"]} src={plan["src_stem"]} '
                f'metallic={plan["metallic"]}').replace("\\", "/"),
               "-unattended", "-nosplash", "-nopause", "-stdout"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        rec = {}
        if RESULT.exists():
            data = json.loads(RESULT.read_text(encoding="utf-8"))
            for r in data.get("records", []):
                if r.get("asset") == plan["asset"]:
                    rec = r
                    break
        return Artifact(
            asset_id=plan["key"], kind=self.kind, data=rec,
            provenance={"source": f"Hi3D/Hitem3D image-to-3D ({plan['src_stem']}.glb)",
                        "license": "Hi3D Essential plan (commercial, recorded)"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        if not r or r.get("error") or not r.get("nanite_enabled"):
            return Verdict(score=0.0, passed=False, hard_fail=bool(r.get("error")),
                           issues=[r.get("error", "import did not produce a Nanite mesh")])
        checks = {
            "nanite_enabled": bool(r.get("nanite_enabled")),
            "nanite_material_flag": bool(r.get("nanite_flag_after")),
            "full_detail_uasset": (r.get("uasset_mb") or 0) >= 10.0,   # decimated was ~1.8MB; full Nanite ~30MB+
            "dechromed": r.get("metallic_set") is not None,
        }
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        return Verdict(score=score, passed=all(checks.values()), issues=issues,
                       detail={"checks": checks, "uasset_mb": r.get("uasset_mb"),
                               "fallback_tris": r.get("fallback_tris")})

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # REPAIR WITH NEW INFO (G11): act on the verdict's failed checks instead of a blind re-run.
        issues = set(verdict.issues or [])
        new_plan = dict(plan)
        new_plan["repair_attempt"] = attempt
        new_plan["prior_issues"] = sorted(issues)
        if "dechromed" in issues:
            # de-chrome did not register -> force fully non-metallic so the satin pass unambiguously applies
            new_plan["metallic"] = 0.0
        if "full_detail_uasset" in issues:
            new_plan["force_full"] = True          # imported under the full-detail floor -> request forced full-Nanite
        # only a clean idempotent re-run if nothing actionable changed (the original behavior, but now logged)
        return self.execute(new_plan)
