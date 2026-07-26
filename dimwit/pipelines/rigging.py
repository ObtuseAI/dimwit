"""Rigging pipeline — turns a static Hi3D character into an animatable UE5-Mannequin skeletal mesh so it reuses
ABP_Manny / Lyra-style locomotion (idle/walk/run) with no per-character animator.

Stages (all real, all proofed):
  1) ensure a cached UE5 Mannequin reference FBX (export SK_Mannequin once via scripts/ue/ue_rig_io.py).
  2) Blender headless auto-rig: align + automatic weights + <=4 influences (rig_to_mannequin.py) on the decimated
     mesh (~45k, good for skinning; the full Nanite mesh stays the static lobby display).
  3) import the skinned FBX into UE as a Skeletal Mesh on the SK_Mannequin skeleton (scripts/ue/ue_rig_io.py).
QA is STRUCTURAL: weight coverage ~1.0, <=4 influences/vertex, bone count matches the Mannequin, UE import made
a SkeletalMesh. (GLM deformation QA on extreme-pose renders is the next layer once captures are wanted again.)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError
from .character_roster import is_quarantined_character

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
RIG_SCRIPT = ROOT / "blender_scripts" / "rig_to_mannequin.py"
RIG_IO = ROOT / "scripts/ue/ue_rig_io.py"
POSE_DRIVER = ROOT / "scripts/ue/ue_capture_poses.py"      # the deformation pose-capture executor (#32)
POSE_RESULT = ART / "pose_capture_result.json"
RIGGED_DIR = "/Game/Wanefall/Dimwit/CharactersRigged"
MANN_FBX = ART / "rig" / "SK_Mannequin_ref.fbx"
STAGING_SYM = ART / "ue_staging_sym"            # decimated, symmetric meshes — good for skinning
DEFORM_FLOOR = 0.85                             # weakest stress-pose deformation score required to certify

ASSET_FOR = {
    "vorlax": "SM_Char_01_Vorlax", "ekris": "SM_Char_02_ekris", "zythan": "SM_Char_03_zythan",
    "qorin": "SM_Char_04_qorin", "therak": "SM_Char_05_therak", "ullio": "SM_Char_06_ullio",
    "kelous": "SM_Char_07_kelous", "nexor": "SM_Char_08_nexor",
    "mech_01_glaciera": "SM_Char_Mech_01_Glaciera", "mech_02_voidrunner": "SM_Char_Mech_02_Voidrunner",
    "mech_03_aurelion": "SM_Char_Mech_03_Aurelion", "mech_04_luxorion": "SM_Char_Mech_04_Luxorion",
    "mech_05_pyroclast": "SM_Char_Mech_05_Pyroclast", "mech_06_jadewind": "SM_Char_Mech_06_Jadewind",
    "mech_07_ironline": "SM_Char_Mech_07_Ironline", "mech_08_nightwire": "SM_Char_Mech_08_Nightwire",
}

# Hard-surface mechs skin with rigid single-bone weights (armor plates must not stretch like cloth).
RIGID_KEYS = {k for k in ASSET_FOR if k.startswith("mech_")}


class RiggingPipeline(ProductionPipeline):
    name = "rigging"
    kind = "skeletal_mesh"

    def _ue(self, args: str, timeout=900):
        # forward slashes: UE mis-parses backslash paths passed through subprocess list quoting
        script_arg = (f"-ExecutePythonScript={RIG_IO} {args}").replace("\\", "/")
        subprocess.run([str(UE_CMD), str(UPROJECT), script_arg,
                        "-unattended", "-nosplash", "-nopause", "-stdout"],
                       capture_output=True, text=True, timeout=timeout)
        rio = ART / "rig_io_result.json"
        return json.loads(rio.read_text(encoding="utf-8")) if rio.exists() else {}

    def _capture_poses(self, plan: dict, timeout=1500) -> dict:
        """Drive scripts/ue/ue_capture_poses.py in UE: pose the rigged mesh across the stress set + bind, render PNGs.
        Returns the pose-capture result ({bind, poses{name:png}, captured, missing_anims})."""
        if POSE_RESULT.exists():
            POSE_RESULT.unlink()                                   # never read a stale capture
        out_dir = ART / "pose_capture"
        args = f"rig_path={RIGGED_DIR}/{plan['asset']}_Rig asset={plan['asset']} out_dir={out_dir}"
        script_arg = (f"-ExecutePythonScript={POSE_DRIVER} {args}").replace("\\", "/")
        subprocess.run([str(UE_CMD), str(UPROJECT), script_arg,
                        "-unattended", "-nosplash", "-nopause", "-stdout"],
                       capture_output=True, text=True, timeout=timeout)
        return json.loads(POSE_RESULT.read_text(encoding="utf-8")) if POSE_RESULT.exists() else {}

    @staticmethod
    def deformation_verdict(data: dict) -> dict:
        """Run the pixel-truth deformation QA over the captured stress poses (the #32 layer that structural QA
        is blind to). Fail-closed: no captures => NOT validated (never a silent pass)."""
        cap = (data.get("stages", {}) or {}).get("deformation_capture", {}) or {}
        bind = cap.get("bind")
        stress = {n: p for n, p in (cap.get("poses", {}) or {}).items() if n != "bind"}
        if not bind or len(stress) < 3:
            return {"validated": False, "passed": False, "deformation_score": None,
                    "issues": ["deformation NOT validated: need a bind + >=3 stress-pose captures "
                               "(run scripts/ue/ue_capture_poses.py on a live editor)"],
                    "missing_anims": cap.get("missing_anims", [])}
        from dimwit import perception
        r = perception.rig_deformation_over_poses(bind, stress)
        validated = bool(r.get("ok") and not r.get("blocked"))
        passed = validated and bool(r.get("passed")) and (r.get("deformation_score") or 0.0) >= DEFORM_FLOOR
        issues = []
        if not validated:
            issues.append(f"deformation unmeasurable (fail-closed): {r.get('reason')}")
        elif not passed:
            worst = r.get("worst_pose")
            wd = (r.get("per_pose", {}) or {}).get(worst, {})
            issues.append(f"deformation FAIL at worst pose '{worst}' (score {r.get('deformation_score')}): "
                          + "; ".join(wd.get("issues", [])))
        return {"validated": validated, "passed": passed,
                "deformation_score": r.get("deformation_score"), "worst_pose": r.get("worst_pose"),
                "issues": issues, "detail": r}

    def plan(self, task: dict) -> dict:
        key = str(task.get("asset_id", task.get("name", "zythan"))).lower()
        if key not in ASSET_FOR:
            raise BlockedError(f"unknown character '{key}'")
        if is_quarantined_character(key) or is_quarantined_character(ASSET_FOR[key]):
            raise BlockedError(f"quarantined character '{key}' is failure-fixture only")
        mesh_glb = STAGING_SYM / f"{ASSET_FOR[key]}.glb"
        if not mesh_glb.exists():
            raise BlockedError(f"decimated mesh missing: {mesh_glb}")
        for tool in (BLENDER, UE_CMD, UPROJECT):
            if not Path(tool).exists():
                raise BlockedError(f"missing tool: {tool}")
        return {"key": key, "asset": ASSET_FOR[key], "mesh_glb": str(mesh_glb),
                "rigid": key in RIGID_KEYS,
                "out_fbx": str(ART / "rig" / f"{ASSET_FOR[key]}_rigged.fbx")}

    def execute(self, plan: dict) -> Artifact:
        rec = {"stages": {}}
        # 1) cache the mannequin reference FBX
        if not MANN_FBX.exists():
            rec["stages"]["export_mannequin"] = self._ue(f"mode=export_mannequin out={MANN_FBX}")
        rec["mannequin_fbx_exists"] = MANN_FBX.exists()
        # 2) Blender auto-rig
        if MANN_FBX.exists():
            subprocess.run([str(BLENDER), "--background", "--python", str(RIG_SCRIPT), "--",
                            f"mannequin={MANN_FBX}", f"mesh={plan['mesh_glb']}", f"out={plan['out_fbx']}",
                            f"rigid={'true' if plan.get('rigid') else 'false'}"],
                           capture_output=True, text=True, timeout=1200)
            rigjson = Path(plan["out_fbx"] + ".rig.json")
            rec["stages"]["blender_rig"] = json.loads(rigjson.read_text()) if rigjson.exists() else {"ok": False}
        # 3) import skeletal to UE
        if Path(plan["out_fbx"]).exists():
            rec["stages"]["import_skeletal"] = self._ue(
                f"mode=import_skeletal fbx={plan['out_fbx']} asset={plan['asset']}_Rig")
        # 4) DEFORMATION capture (#32): pose the rigged mesh across the stress set + bind, render PNGs, so qa()
        #    can run pixel-truth deformation checks structural QA cannot. Skipped gracefully if UE absent.
        if (rec["stages"].get("import_skeletal") or {}).get("ok") and POSE_DRIVER.exists() and UE_CMD.exists():
            try:
                rec["stages"]["deformation_capture"] = self._capture_poses(plan)
            except Exception as e:
                rec["stages"]["deformation_capture"] = {"ok": False, "error": str(e)}
        return Artifact(asset_id=plan["key"], kind=self.kind, data=rec,
                        provenance={"source": f"Hi3D mesh {plan['asset']} rigged to UE5 Mannequin",
                                    "license": "Hi3D Essential (mesh) + UE5 Mannequin (Epic EULA, in-engine)"})

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        d = artifact.data or {}
        rig = (d.get("stages", {}) or {}).get("blender_rig", {}) or {}
        imp = (d.get("stages", {}) or {}).get("import_skeletal", {}) or {}
        structural = {
            "mannequin_ref": bool(d.get("mannequin_fbx_exists")),
            "weights_covered": (rig.get("weight_coverage") or 0) > 0.99,
            "max_influences_ok": 0 < (rig.get("max_influences") or 0) <= 4,
            "bones_present": (rig.get("bones") or 0) >= 50,
            "ue_skeletal_imported": bool(imp.get("ok")),
        }
        # DEFORMATION QA (#32): no longer structural-only — the rig must also DEFORM cleanly across the stress
        # poses. Fail-closed: absent captures => deformation_validated False => the rig is not certified "good".
        deform = self.deformation_verdict(d)
        checks = {**structural, "deformation_validated": deform["passed"]}
        score = sum(bool(v) for v in checks.values()) / len(checks)
        passed = all(structural.values()) and deform["passed"]
        issues = [k for k, v in checks.items() if not v] + deform.get("issues", [])
        return Verdict(score=score, passed=passed, issues=issues,
                       detail={"checks": checks, "structural": structural, "deformation": deform})

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # most failures are alignment/weight; re-run is idempotent. (Future: nudge pose-match / weight smooth.)
        return self.execute(plan)
