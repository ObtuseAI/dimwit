"""Animation pipeline — makes a rigged Hi3D character (a SkeletalMesh on the UE5 Mannequin skeleton, produced by
the rigging pipeline at /Game/Wanefall/Dimwit/CharactersRigged/<Asset>_Rig) actually MOVE by reusing the
in-project ABP_Manny / AnimStarterPack (UE4 mocap retargeted onto the Mannequin skeleton).

Why this works: the rigging pipeline skins each character to the SAME skeleton as SK_Mannequin. Anything that
animates the Mannequin (ABP_Manny + every AnimSequence under /Game/Mannequins and /Game/AnimStarterPack) therefore
drives the rigged character for free — no per-character animator.

Stages (all real, all proofed via the UE driver `scripts/ue/ue_anim_setup.py`):
  1) load the rigged SkeletalMesh, read its Skeleton.
  2) assert that skeleton == the SK_Mannequin skeleton (compatibility gate — fail-closed if not).
  3) assign ABP_Manny as the SkeletalMesh's post-process / default AnimClass (so it animates on spawn).
  4) enumerate compatible AnimSequences (same skeleton) under /Game/Mannequins + /Game/AnimStarterPack.
QA is STRUCTURAL (honest proof the wiring landed without a screenshot): skeleton-compatible + AnimBP assigned +
>=1 compatible AnimSequence found.

Roadmap (todos): IK Rig + IK Retargeter auto-setup (cross-skeleton retarget); UE5 Motion Matching (PoseSearch)
database build; ML text-to-motion (MDM / MotionGPT, MIT-licensed) for WANEFALL signature moves
(Crystallize / Erode / Snap).

IMPORT-SAFE: only stdlib + .base at module top; `import unreal` lives inside the driver, never here.
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
DRIVER = ROOT / "scripts/ue/ue_anim_setup.py"
RESULT = ART / "anim_setup_result.json"

# UE content path of the rigged skeletal meshes produced by the rigging pipeline.
RIGGED_DIR = "/Game/Wanefall/Dimwit/CharactersRigged"

# Maps the friendly character key -> the rigged SkeletalMesh asset name (matches rigging.py's <Asset>_Rig).
ASSET_FOR = {
    "vorlax": "SM_Char_01_Vorlax", "ekris": "SM_Char_02_ekris", "zythan": "SM_Char_03_zythan",
    "qorin": "SM_Char_04_qorin", "therak": "SM_Char_05_therak", "ullio": "SM_Char_06_ullio",
    "kelous": "SM_Char_07_kelous", "nexor": "SM_Char_08_nexor",
    "mech_01_glaciera": "SM_Char_Mech_01_Glaciera", "mech_02_voidrunner": "SM_Char_Mech_02_Voidrunner",
    "mech_03_aurelion": "SM_Char_Mech_03_Aurelion", "mech_04_luxorion": "SM_Char_Mech_04_Luxorion",
    "mech_05_pyroclast": "SM_Char_Mech_05_Pyroclast", "mech_06_jadewind": "SM_Char_Mech_06_Jadewind",
    "mech_07_ironline": "SM_Char_Mech_07_Ironline", "mech_08_nightwire": "SM_Char_Mech_08_Nightwire",
}


class AnimationPipeline(ProductionPipeline):
    name = "animation"
    kind = "animated_character"

    def plan(self, task: dict) -> dict:
        key = str(task.get("asset_id", task.get("name", "zythan"))).lower()
        if key not in ASSET_FOR:
            raise BlockedError(f"unknown character '{key}'; known: {sorted(ASSET_FOR)}")
        if is_quarantined_character(key) or is_quarantined_character(ASSET_FOR[key]):
            raise BlockedError(f"quarantined character '{key}' is failure-fixture only")
        if not UE_CMD.exists() or not UPROJECT.exists():
            raise BlockedError("UnrealEditor-Cmd or uproject not found")
        if not DRIVER.exists():
            raise BlockedError(f"UE driver missing: {DRIVER}")
        # The rigged SkeletalMesh must already exist in-project (rigging pipeline must have run first).
        # We cannot load UE assets from here, so the driver verifies existence and reports it; plan() proves the
        # prerequisite path is well-formed and lets the driver fail-closed if the asset is absent.
        rig_asset = f"{ASSET_FOR[key]}_Rig"
        return {
            "key": key,
            "rig_asset": rig_asset,
            "rig_path": f"{RIGGED_DIR}/{rig_asset}",
            # An optional AnimBP override; defaults to the in-project ABP_Manny (driver resolves the real path).
            "anim_bp": str(task.get("anim_bp", "ABP_Manny")),
        }

    def execute(self, plan: dict) -> Artifact:
        if RESULT.exists():
            RESULT.unlink()
        cmd = [str(UE_CMD), str(UPROJECT),
               # forward slashes: UE mis-parses backslash paths passed through subprocess list quoting
               (f'-ExecutePythonScript={DRIVER} rig_path={plan["rig_path"]} '
                f'anim_bp={plan["anim_bp"]}').replace("\\", "/"),
               "-unattended", "-nosplash", "-nopause", "-stdout"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        rec = {}
        if RESULT.exists():
            rec = json.loads(RESULT.read_text(encoding="utf-8"))
        return Artifact(
            asset_id=plan["key"], kind=self.kind, data=rec,
            provenance={
                "source": f"{plan['rig_asset']} (UE5-Mannequin-skinned) + ABP_Manny / AnimStarterPack reuse",
                "license": "UE5 Mannequin + AnimStarterPack (Epic Content EULA, in-engine) + Hi3D mesh (Essential)",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        if not r or r.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=bool(r.get("error")),
                           issues=[r.get("error", "driver produced no result")])
        # Skeleton mismatch is a HARD gate: an incompatible skeleton can never reuse ABP_Manny -> no recursion.
        if r.get("rig_exists") and r.get("skeleton_compatible") is False:
            return Verdict(score=0.0, passed=False, hard_fail=True,
                           issues=["skeleton_incompatible: rigged mesh is not on the SK_Mannequin skeleton"],
                           detail={"rig_skeleton": r.get("rig_skeleton"),
                                   "mannequin_skeleton": r.get("mannequin_skeleton")})
        checks = {
            "rig_exists": bool(r.get("rig_exists")),
            "skeleton_compatible": bool(r.get("skeleton_compatible")),
            "anim_bp_assigned": bool(r.get("anim_bp_assigned")),
            "compatible_anims_found": int(r.get("compatible_anim_count") or 0) >= 1,
        }
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        return Verdict(score=score, passed=all(checks.values()), issues=issues,
                       detail={"checks": checks,
                               "anim_bp": r.get("anim_bp_assigned"),
                               "compatible_anim_count": r.get("compatible_anim_count"),
                               "sample_anims": (r.get("compatible_anims") or [])[:8]})

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # The driver is idempotent: re-running re-resolves the AnimBP path and re-assigns it (the common first-pass
        # miss is an unsaved AnimClass assignment or a not-yet-loaded ABP). Re-execute clears that partial state.
        return self.execute(plan)
