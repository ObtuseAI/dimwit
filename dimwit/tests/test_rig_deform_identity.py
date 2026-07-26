"""CHARACTER_DEFORMATION_GATE_V1 (masterplan H1 bundle 3).

The deformation gate stayed green for days on RESTORED EKRIS-ERA evidence while zythan (the
active character) shipped deformation-unproven. Contract: pose evidence must BE evidence about
the active character's current rig, must prove the key joints actually articulated, and every
pose frame must carry a recorded verdict from the CALIBRATED quorum judge.
1. rig_deform_identity_bound — subject tokens match the active character AND the rig .uasset
   sha256 recorded at capture time matches the file on disk now (re-import invalidates).
2. rig_deform_joints_articulated — per-joint articulation telemetry present; every key joint
   moved at least the floor (a frozen or partially-frozen clip proves nothing).
3. rig_deform_silhouette_judged — bind + every pose judged by the quorum (passed, no hard fail),
   with the judging judge bound to the CURRENT golden calibration manifest.
All three fail closed on the pre-identity (ekris-era) schema.
"""
import hashlib
import json
from pathlib import Path

from dimwit.pipelines import validation_registry as VR


def _arts(tmp_path, monkeypatch):
    art = tmp_path / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(VR, "ROOT", tmp_path)
    return art


def _rig_file(tmp_path, monkeypatch, data=b"RIGDATA-v1"):
    content = tmp_path / "Content"
    rig = content / "Wanefall" / "Dimwit" / "CharactersRigged" / "SM_Char_03_zythan_Rig.uasset"
    rig.parent.mkdir(parents=True, exist_ok=True)
    rig.write_bytes(data)
    monkeypatch.setattr(VR, "CONTENT", content)
    return hashlib.sha256(data).hexdigest()


def _verdict(passed=True, hard_fail=False):
    return {"passed": passed, "hard_fail": hard_fail, "score": 0.8 if passed else 0.3,
            "issues": [] if passed else ["semantic:disfigured_or_morphed"],
            "quorum": {"n": 3, "blocked_votes": 0, "pass_votes": 3 if passed else 0}}


def _artifact(rig_hash, *, subject="SM_Char_03_zythan", joints=None, verdicts=None,
              judge_hash="cal123", poses=("pose_a", "pose_b", "pose_c")):
    ja = {"frames_sampled": 12,
          "max_rot_delta_deg": joints if joints is not None else {
              "thigh_l": 48.0, "thigh_r": 51.0, "calf_l": 62.0, "calf_r": 60.0,
              "upperarm_l": 30.0, "upperarm_r": 33.0, "lowerarm_l": 41.0, "lowerarm_r": 39.0}}
    sv = verdicts if verdicts is not None else {k: _verdict() for k in ("bind",) + tuple(poses)}
    return {"bind": "x/bind.png", "poses": {p: f"x/{p}.png" for p in poses},
            "subject_character": subject,
            "rig_asset": "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_03_zythan_Rig",
            "rig_uasset_sha256": rig_hash, "captured_at": 1782980000.0,
            "anim": "/Game/Mannequins/Animations/Manny/MM_Run_Fwd", "stage": "Wanefall_CleanStage_01",
            "joint_articulation": ja, "silhouette_verdicts": sv,
            "judge_calibration_manifest_hash": judge_hash,
            "source": "scripts/capture/ue_mrq_capture.py emit_capture_artifacts_v2"}


def _write(art, obj):
    (art / "pose_capture_result.json").write_text(json.dumps(obj), encoding="utf-8")


def _setup(tmp_path, monkeypatch, **kw):
    art = _arts(tmp_path, monkeypatch)
    h = _rig_file(tmp_path, monkeypatch)
    monkeypatch.setattr(VR, "_optics_metadata_matches_active_character",
                        lambda meta: meta.get("subject_character") == "SM_Char_03_zythan")
    from dimwit import optics_calibration as oc
    monkeypatch.setattr(oc, "manifest_hash", lambda: "cal123")
    _write(art, _artifact(h, **kw))
    return art, h


# ---------------------------------------------------------------- identity + rig binding
def test_identity_bound_passes_on_current_zythan_evidence(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    v = VR.v_rig_deform_identity_bound(None)
    assert v.passed is True


def test_ekris_era_schema_hard_fails(tmp_path, monkeypatch):
    art = _arts(tmp_path, monkeypatch)
    _write(art, {"bind": "x/bind.png", "poses": {"pose_a": "x/a.png"},
                 "source": "scripts/capture/ue_mrq_capture.py MM_Run_Fwd on ekris_anim (Wanefall_CleanStage_01)"})
    v = VR.v_rig_deform_identity_bound(None)
    assert v.passed is False and v.hard_fail is True


def test_wrong_subject_hard_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, subject="SM_Char_02_ekris")
    v = VR.v_rig_deform_identity_bound(None)
    assert v.passed is False and v.hard_fail is True


def test_reimported_rig_invalidates_evidence(tmp_path, monkeypatch):
    art, _ = _setup(tmp_path, monkeypatch)
    _rig_file(tmp_path, monkeypatch, data=b"RIGDATA-v2-reimported")   # disk changed after capture
    v = VR.v_rig_deform_identity_bound(None)
    assert v.passed is False
    assert any("rig" in i.lower() for i in v.issues)


# ---------------------------------------------------------------- per-joint articulation
def test_articulated_joints_pass(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    v = VR.v_rig_deform_joints_articulated(None)
    assert v.passed is True


def test_weak_key_joint_fails(tmp_path, monkeypatch):
    joints = {"thigh_l": 48.0, "thigh_r": 51.0, "calf_l": 62.0, "calf_r": 60.0,
              "upperarm_l": 2.0, "upperarm_r": 33.0, "lowerarm_l": 41.0, "lowerarm_r": 39.0}
    _setup(tmp_path, monkeypatch, joints=joints)
    v = VR.v_rig_deform_joints_articulated(None)
    assert v.passed is False
    assert any("upperarm_l" in i for i in v.issues)


def test_missing_joint_telemetry_hard_fails(tmp_path, monkeypatch):
    art = _arts(tmp_path, monkeypatch)
    h = _rig_file(tmp_path, monkeypatch)
    a = _artifact(h)
    del a["joint_articulation"]
    _write(art, a)
    v = VR.v_rig_deform_joints_articulated(None)
    assert v.passed is False and v.hard_fail is True


# ---------------------------------------------------------------- judged silhouette
def test_judged_silhouette_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    v = VR.v_rig_deform_silhouette_judged(None)
    assert v.passed is True


def test_disfigured_pose_hard_fails(tmp_path, monkeypatch):
    verdicts = {k: _verdict() for k in ("bind", "pose_a", "pose_b")}
    verdicts["pose_c"] = _verdict(passed=False, hard_fail=True)
    _setup(tmp_path, monkeypatch, verdicts=verdicts)
    v = VR.v_rig_deform_silhouette_judged(None)
    assert v.passed is False and v.hard_fail is True


def test_unjudged_pose_fails_closed(tmp_path, monkeypatch):
    verdicts = {k: _verdict() for k in ("bind", "pose_a", "pose_b")}   # pose_c never judged
    _setup(tmp_path, monkeypatch, verdicts=verdicts)
    v = VR.v_rig_deform_silhouette_judged(None)
    assert v.passed is False


def test_stale_judge_calibration_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, judge_hash="old_goldens_hash")
    v = VR.v_rig_deform_silhouette_judged(None)
    assert v.passed is False
    assert any("calibration" in i.lower() for i in v.issues)


# ---------------------------------------------------------------- registry
def test_new_gates_registered_as_blockers():
    ids = {"rig_deform_identity_bound", "rig_deform_joints_articulated", "rig_deform_silhouette_judged"}
    rows = [r for r in VR.REGISTRY if r.id in ids]
    assert {r.id for r in rows} == ids
    assert all(str(r.severity).lower().endswith("blocker") for r in rows)
