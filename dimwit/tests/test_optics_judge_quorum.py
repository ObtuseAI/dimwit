"""OPTICS_JUDGE_QUORUM_AND_CALIBRATION_V1 (masterplan H1 bundle 2).

The single-shot vision judge coin-flipped 0.4-0.65 for days over the same washed subject, and
its system prompt hardcoded a stale palette ("silver/dark with orange/teal accents") that
overrode every character's actual reference. Contract:
1. The optics gate judges via an N=3 quorum - median score, majority verdict, fail-closed
   aggregation (2+ blocked -> blocked; ties/insufficient agreement never pass).
2. With a reference attached, color_on_model is LOAD-BEARING: a render whose color family
   deviates from the reference must not pass regardless of score.
3. A golden calibration set gates the judge itself: misclassified goldens, a stale calibration,
   or a changed manifest fail the new optics_judge_calibrated blocker.
"""
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from dimwit import optics
from dimwit.pipelines import validation_registry as VR


def _verdict(passed=True, score=0.8, hard_fail=False, issues=None, blocked=False):
    v = {"ok": not blocked, "passed": passed, "hard_fail": hard_fail, "score": score,
         "issues": issues or [], "pixel": {}, "evidence": [],
         "semantic": {"blocked": "x"} if blocked else {"score": score, "summary": f"s{score}"}}
    return v


# ---------------------------------------------------------------- quorum aggregation (pure)
def test_quorum_all_pass():
    v = optics._aggregate_quorum([_verdict(True, 0.8), _verdict(True, 0.7), _verdict(True, 0.9)])
    assert v["passed"] is True
    assert v["score"] == 0.8            # median
    assert v["quorum"]["n"] == 3


def test_quorum_majority_pass_survives_one_flake():
    v = optics._aggregate_quorum([_verdict(True, 0.75), _verdict(False, 0.45), _verdict(True, 0.7)])
    assert v["passed"] is True


def test_quorum_majority_fail_fails():
    v = optics._aggregate_quorum([_verdict(False, 0.45), _verdict(True, 0.65), _verdict(False, 0.4)])
    assert v["passed"] is False


def test_quorum_two_blocked_is_blocked():
    v = optics._aggregate_quorum([_verdict(blocked=True), _verdict(blocked=True), _verdict(True, 0.8)])
    assert "blocked" in v["semantic"]
    assert v["passed"] is False


def test_quorum_one_blocked_requires_both_remaining_to_pass():
    v = optics._aggregate_quorum([_verdict(blocked=True), _verdict(True, 0.7), _verdict(False, 0.5)])
    assert v["passed"] is False
    v2 = optics._aggregate_quorum([_verdict(blocked=True), _verdict(True, 0.7), _verdict(True, 0.75)])
    assert v2["passed"] is True


def test_quorum_majority_hard_fail_and_majority_issues():
    v = optics._aggregate_quorum([
        _verdict(False, 0.3, hard_fail=True, issues=["defect:washed", "defect:only_once"]),
        _verdict(False, 0.35, hard_fail=True, issues=["defect:washed"]),
        _verdict(True, 0.65, issues=["defect:washed"]),
    ])
    assert v["hard_fail"] is True
    assert "defect:washed" in v["issues"]
    assert "defect:only_once" not in v["issues"]


def test_quorum_even_split_fails_closed():
    v = optics._aggregate_quorum([_verdict(True, 0.7), _verdict(False, 0.5)])
    assert v["passed"] is False


# ---------------------------------------------------------------- color_on_model gating
def _noisy_img(path: Path, rgb):
    im = Image.new("RGB", (96, 96), rgb)
    d = ImageDraw.Draw(im)
    for i in range(0, 96, 8):
        d.line([(i, 0), (96, 96 - i)], fill=(rgb[0] // 2, rgb[1] // 2, rgb[2] // 2))
    im.save(path)
    return str(path)


def _sem(monkeypatch, **overrides):
    base = {"readable": True, "correctly_proportioned": True, "disfigured_or_morphed": False,
            "clean_silhouette": True, "color_on_model": True, "stray_placeholder_geometry": False,
            "matches_reference": "yes", "defects": [], "severity": "minor", "score": 0.9,
            "summary": "fine"}
    base.update(overrides)
    monkeypatch.setattr(optics, "_semantic", lambda rubric, images, **kw: dict(base))


def test_color_off_model_fails_with_reference(tmp_path, monkeypatch):
    img = _noisy_img(tmp_path / "subject.png", (110, 80, 190))
    ref = _noisy_img(tmp_path / "ref.png", (90, 60, 160))
    _sem(monkeypatch, color_on_model=False)
    v = optics.judge_character(img, reference=ref)
    assert v["passed"] is False
    assert any("color_on_model" in i for i in v["issues"])


def test_color_on_model_passes_with_reference(tmp_path, monkeypatch):
    img = _noisy_img(tmp_path / "subject.png", (110, 80, 190))
    ref = _noisy_img(tmp_path / "ref.png", (90, 60, 160))
    _sem(monkeypatch)
    v = optics.judge_character(img, reference=ref)
    assert v["passed"] is True


def test_quorum_retries_blocked_votes_once(monkeypatch):
    """A blocked vote is infrastructure failure, not judgement - the quorum re-asks it once.
    (Observed live: one transient empty response flipped a calibration verdict.)"""
    calls = []

    def fake_judge(image, reference=None, require_semantic=True, subject_only=False, model=None):
        calls.append(model)
        if model == "m2" and calls.count("m2") == 1:
            return _verdict(blocked=True)
        return _verdict(True, 0.8)

    monkeypatch.setattr(optics, "judge_character", fake_judge)
    v = optics.judge_character_quorum("img.png", n=3, models=("m1", "m2", "m3"))
    assert calls.count("m2") == 2          # blocked vote retried once
    assert v["passed"] is True
    assert v["quorum"]["blocked_votes"] == 0
    assert v["quorum"]["retried_votes"] == 1


def test_quorum_persistent_block_stays_blocked_after_retry(monkeypatch):
    def fake_judge(image, reference=None, require_semantic=True, subject_only=False, model=None):
        return _verdict(blocked=True)

    monkeypatch.setattr(optics, "judge_character", fake_judge)
    v = optics.judge_character_quorum("img.png", n=3, models=("m1", "m2", "m3"))
    assert "blocked" in v["semantic"]
    assert v["passed"] is False


# ---------------------------------------------------------------- calibration checker (pure)
def test_calibration_check_flags_misclassified():
    from dimwit import optics_calibration as oc
    manifest = {"goldens": [{"name": "good1", "expect": "pass"}, {"name": "bad1", "expect": "fail"}]}
    ok_results = {"good1": {"passed": True}, "bad1": {"passed": False}}
    bad_results = {"good1": {"passed": True}, "bad1": {"passed": True}}
    assert oc.check_calibration(ok_results, manifest)["ok"] is True
    r = oc.check_calibration(bad_results, manifest)
    assert r["ok"] is False and r["misclassified"] == ["bad1"]


def test_calibration_check_missing_golden_result_fails():
    from dimwit import optics_calibration as oc
    manifest = {"goldens": [{"name": "good1", "expect": "pass"}]}
    r = oc.check_calibration({}, manifest)
    assert r["ok"] is False


# ---------------------------------------------------------------- stability protocol (lane)
def test_run_calibration_requires_stable_rounds(tmp_path, monkeypatch):
    """One lucky 5/5 run is jitter-riding: identical live runs flipped 4/4<->2/4 on 2026-07-02.
    The lane re-judges the whole set `stability` times and a golden that flips ANY round fails."""
    from dimwit import optics_calibration as oc
    flip = {"count": 0}

    def fake_quorum(image, reference=None, n=3, subject_only=False, **kw):
        flip["count"] += 1
        name = Path(str(image)).stem
        if name.startswith("good"):
            # good golden: passes round 1, flips to fail in round 2
            passed = flip["count"] <= 2
            return {"passed": passed, "score": 0.8 if passed else 0.5, "hard_fail": False,
                    "issues": [], "quorum": {"n": n}}
        return {"passed": False, "score": 0.2, "hard_fail": False, "issues": [], "quorum": {"n": n}}

    manifest = {"goldens": [
        {"name": "good_a", "file": "good_a.png", "expect": "pass"},
        {"name": "bad_a", "file": "bad_a.png", "expect": "fail"},
    ]}
    gdir = tmp_path / "goldens"
    gdir.mkdir()
    for f in ("good_a.png", "bad_a.png"):
        Image.new("RGB", (8, 8), (90, 60, 160)).save(gdir / f)
    monkeypatch.setattr(oc, "GOLDEN_DIR", gdir)
    monkeypatch.setattr(oc, "load_manifest", lambda: manifest)
    monkeypatch.setattr(oc, "manifest_hash", lambda: "h1")
    monkeypatch.setattr(oc, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(oc, "RESULT_PATH", tmp_path / "out" / "calibration_result.json")
    import dimwit.optics as _optics
    monkeypatch.setattr(_optics, "judge_character_quorum", fake_quorum)
    monkeypatch.setattr(oc, "_llm_ready", lambda: True)

    r = oc.run_calibration(n=3, stability=2)
    assert r["stability_runs"] == 2
    assert r["ok"] is False
    assert "good_a" in r["misclassified"]
    assert "good_a" in r["flipped"]
    assert len(r["rounds"]) == 2


# ---------------------------------------------------------------- suite validator
def _write_calib(tmp_path, monkeypatch, *, age_s=0, ok=True, misclassified=None, quorum_n=3,
                 hash_match=True, stability_runs=2):
    art = tmp_path / "artifacts" / "optics_calibration"
    art.mkdir(parents=True)
    from dimwit import optics_calibration as oc
    real_hash = "h123"
    monkeypatch.setattr(oc, "manifest_hash", lambda: real_hash)
    payload = {"ts": time.time() - age_s, "quorum_n": quorum_n,
               "manifest_hash": real_hash if hash_match else "stale_hash",
               "ok": ok, "misclassified": misclassified or [], "stability_runs": stability_runs}
    (art / "calibration_result.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(VR, "ROOT", tmp_path)
    return payload


def test_calibrated_gate_fails_on_single_stability_run(tmp_path, monkeypatch):
    _write_calib(tmp_path, monkeypatch, stability_runs=1)
    assert VR.v_optics_judge_calibrated(None).passed is False


def test_calibrated_gate_passes_on_fresh_correct_result(tmp_path, monkeypatch):
    _write_calib(tmp_path, monkeypatch)
    assert VR.v_optics_judge_calibrated(None).passed is True


def test_calibrated_gate_fails_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(VR, "ROOT", tmp_path)
    v = VR.v_optics_judge_calibrated(None)
    assert v.passed is False


def test_calibrated_gate_fails_when_stale(tmp_path, monkeypatch):
    _write_calib(tmp_path, monkeypatch, age_s=8 * 24 * 3600)
    assert VR.v_optics_judge_calibrated(None).passed is False


def test_calibrated_gate_fails_on_manifest_change(tmp_path, monkeypatch):
    _write_calib(tmp_path, monkeypatch, hash_match=False)
    assert VR.v_optics_judge_calibrated(None).passed is False


def test_calibrated_gate_hard_fails_on_misclassified_golden(tmp_path, monkeypatch):
    _write_calib(tmp_path, monkeypatch, ok=False, misclassified=["bad1"])
    v = VR.v_optics_judge_calibrated(None)
    assert v.passed is False and v.hard_fail is True


def test_calibrated_gate_registered_as_blocker():
    match = [r for r in VR.REGISTRY if r.id == "optics_judge_calibrated"]
    assert len(match) == 1
    assert str(match[0].severity).lower().endswith("blocker")
