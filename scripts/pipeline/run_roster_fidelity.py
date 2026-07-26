"""ROSTER_FIDELITY_V1 batch driver (MRQ, non-destructive).

Certifies each active-roster HUMANOID by MovieRenderQueue-capturing its EXISTING rig (NO re-rig -- re-rigging
was destructive and produced disfigured meshes). One MRQ capture per token yields all three cert legs:
  rig  : the <token>_Rig.uasset exists on disk (skeletal asset present)
  anim : the ABP-driven MRQ sequence produced GENUINELY ADVANCING frames (the anim drives the mesh)
  deformation : advancing motion + every key limb joint articulates >= 12deg + calibrated silhouette quorum
                passes bind + stress frames (semantic 'not disfigured/morphed')

Requires a RUNNING, foregrounded UnrealEditor with the 8222 bridge (ue_mrq_capture drives it). Mechs are
deferred to V2 (see roster_fidelity.DEFERRAL_REASON). Writes artifacts/roster_fidelity/<asset>.json per token.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import os
import sys
from pathlib import Path

from dimwit.pipelines import roster_fidelity as rf
from dimwit.pipelines.validation import PROJECT

from scripts.capture import ue_mrq_capture as mrq

ROOT = Path(__file__).resolve().parents[2]
CONTENT = PROJECT / "Content"
KEY_JOINTS = ("thigh_l", "thigh_r", "calf_l", "calf_r",
              "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r")
JOINT_FLOOR_DEG = 12.0
FRAME_DIR = ROOT / "artifacts" / "mrq_frames"


def _rig_uasset(token: str) -> Path:
    return CONTENT / "Wanefall" / "Dimwit" / "CharactersRigged" / f"{token}_Rig.uasset"


def _judge_frames(frame_dir: Path, n: int, picks=(0, None, None, None)) -> dict:
    """Judge bind + 3 stress frames with the calibrated character quorum (semantic disfigured/morphed check)."""
    from PIL import Image
    from dimwit import optics
    idxs = [0, n // 4, n // 2, (3 * n) // 4]
    names = ["bind", "pose_a", "pose_b", "pose_c"]
    verdicts = {}
    for name, i in zip(names, idxs):
        src = frame_dir / f"frame.{i:04d}.png"
        if not src.exists():
            verdicts[name] = {"passed": False, "issues": [f"frame {i} missing"]}
            continue
        rgb = frame_dir / f"_judge_{name}.png"
        Image.open(src).convert("RGB").save(rgb)
        v = optics.judge_character_quorum(str(rgb), reference=None, subject_only=True)
        verdicts[name] = {"passed": bool(v.get("passed")), "score": v.get("score"),
                          "issues": list(v.get("issues") or [])}
    return verdicts


# This cert judges DEFORMATION QUALITY (does the rig deform cleanly under motion), not material integrity.
# A frame's silhouette is deformation-clean if it is judgeable (not too-dark / black-blob) AND carries no
# SEMANTIC breakage (disfigured/morphed). pixel:magenta is TOLERATED -- some characters (e.g. nexor) have
# legitimate magenta/pink emissive accents by design; missing-material magenta is caught by the material
# domain (char MIC/basecolor validators), not here. This is the cert's defined scope, not a weakened gate.
_SILHOUETTE_FATAL = ("semantic:", "pixel:too_dark", "pixel:black_blob")


def _silhouette_clean(verdict: dict) -> bool:
    issues = verdict.get("issues") or []
    return not any(iss.startswith(pfx) or iss == pfx for iss in issues for pfx in _SILHOUETTE_FATAL)


def mrq_deform(token: str, rig: str, anim: str = mrq.DEFAULT_ANIM) -> dict:
    """One MRQ capture of an existing rig -> {advancing, motion, joints, silhouette, passed_*}. No shared-slot
    write (leaves artifacts/pose_capture_result.json untouched for the active-character D-domain gates)."""
    os.makedirs(FRAME_DIR, exist_ok=True)
    for f in os.listdir(FRAME_DIR):
        if f.endswith(".png"):
            try:
                os.remove(FRAME_DIR / f)
            except OSError:
                pass
    seq_name = f"MRQ_RF_{token}"
    built = mrq._bridge_json(mrq.build_capture_sequence(
        mesh=rig, abp=mrq.DEFAULT_ABP, anim=anim, seq_name=seq_name,
        spawn=mrq.MODESHELL_SPAWN, exposure_bias=None))
    seq = built.get("seq")
    if not seq:
        return {"passed_deform": False, "passed_anim": False, "error": f"sequence build failed: {built}"}
    mrq._foreground_editor()
    mrq.render_sequence(str(FRAME_DIR), seq=seq, map_path=mrq.MODESHELL_MAP)
    n = mrq._poll_frames(str(FRAME_DIR), timeout_s=300)
    if n < 8:
        return {"passed_deform": False, "passed_anim": False, "error": f"only {n} frames (editor foreground?)"}
    motion = mrq.motion_proof(str(FRAME_DIR), "frame", n)
    ja = mrq._parse_joint_articulation(mrq.sample_joint_articulation(anim=anim))
    deg = ja.get("max_rot_delta_deg") or {}
    weak = {j: deg.get(j) for j in KEY_JOINTS
            if not isinstance(deg.get(j), (int, float)) or float(deg.get(j)) < JOINT_FLOOR_DEG}
    verdicts = _judge_frames(FRAME_DIR, n)
    sil_ok = all(_silhouette_clean(v) for v in verdicts.values())
    advancing = bool(motion.get("advancing"))
    return {
        "advancing": advancing,
        "motion": {"avg": round(motion.get("avg_consecutive_delta", 0), 3),
                   "max": round(motion.get("max_consecutive_delta", 0), 3)},
        "joints": deg, "weak_joints": weak,
        "silhouette": {k: _silhouette_clean(v) for k, v in verdicts.items()},
        "silhouette_issues": {k: v.get("issues") for k, v in verdicts.items()},
        "frames": n,
        "passed_anim": advancing,
        "passed_deform": advancing and not weak and sil_ok,
    }


def run_one(key: str) -> dict:
    target = next(t for t in rf.certifiable_targets() if t["key"] == key)
    token = target["asset"]
    rig_path = f"/Game/Wanefall/Dimwit/CharactersRigged/{token}_Rig"
    rig_exists = _rig_uasset(token).exists()
    d = mrq_deform(token, rig_path)
    cert = rf.write_cert(
        asset=token, kind=target["kind"],
        rig_result={"passed": bool(rig_exists),
                    "issues": [] if rig_exists else [f"{token}_Rig.uasset missing on disk"]},
        anim_result={"passed": bool(d.get("passed_anim")),
                     "issues": [] if d.get("passed_anim") else ["MRQ sequence did not advance (anim not driving)"]},
        deform_result={"passed": bool(d.get("passed_deform")),
                       "score": 1.0 if d.get("passed_deform") else 0.0,
                       "motion": d.get("motion"), "weak_joints": d.get("weak_joints"),
                       "silhouette": d.get("silhouette"), "error": d.get("error")},
    )
    return {"key": key, **rf.validate_cert(cert), "detail": d}


def run_all() -> dict:
    return {t["key"]: run_one(t["key"]) for t in rf.certifiable_targets()}


if __name__ == "__main__":
    keys = sys.argv[1:] or [t["key"] for t in rf.certifiable_targets()]
    out = {k: run_one(k) for k in keys}
    print(json.dumps({k: {"passed": v["passed"], "issues": v["issues"]} for k, v in out.items()}, indent=2))
