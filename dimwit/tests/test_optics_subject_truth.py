"""Optics subject truth (ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1, 2026-07-02).

Two live incidents drove this contract:
1. The judged subject should be the DISPLAY capture (cap_rig_ship.png): it is streaming-true
   (-NoTextureStreaming gate), staged in the map's proven-exposure zone, and frames the whole
   character large - while the live-game crop shows the character small/edge-cropped and the
   judge FAILs it on unresolvable detail even when the material is right.
2. The live crop heuristic locked onto an ORANGE ENEMY BOT that walked in front of the camera -
   a wrong-subject image that would have been judged as the player character. The live candidate
   now must pass a machine hue-sanity check against the character's reference cover before it is
   attached as evidence; a mismatch is a HARD FAIL (wrong-subject evidence is worse than none).
"""
from pathlib import Path

import pytest
from PIL import Image

from dimwit.pipelines import validation_registry as VR


def _img(path: Path, rgb, size=(64, 64)):
    im = Image.new("RGB", size, rgb)
    im.save(path)
    return str(path)


# ---------------------------------------------------------------- subject priority
def test_display_capture_is_primary_judged_subject(tmp_path, monkeypatch):
    monkeypatch.setattr(VR, "VAL_ART", tmp_path)
    cap = _img(tmp_path / "cap_rig_ship.png", (60, 40, 120))
    _img(tmp_path / "char_still_focused.png", (60, 40, 120))
    _img(tmp_path / "char_still.png", (60, 40, 120))
    (tmp_path / "char_still_metadata.json").write_text(
        '{"subject_type": "character_optics_candidate"}', encoding="utf-8")
    monkeypatch.setattr(VR, "_optics_metadata_matches_active_character", lambda meta: True)
    assert VR._best_optics_subject() == cap


def test_live_candidate_still_returned_when_no_display_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(VR, "VAL_ART", tmp_path)
    focused = _img(tmp_path / "char_still_focused.png", (60, 40, 120))
    (tmp_path / "char_still_metadata.json").write_text(
        '{"subject_type": "character_optics_candidate"}', encoding="utf-8")
    monkeypatch.setattr(VR, "_optics_metadata_matches_active_character", lambda meta: True)
    assert VR._best_optics_subject() == focused


# ---------------------------------------------------------------- live-subject hue sanity
def test_hue_sanity_rejects_wrong_subject_orange_bot(tmp_path):
    # the 2026-07-02 incident: salmon/orange enemy bot filling the crop, violet reference
    crop = _img(tmp_path / "crop.png", (235, 130, 100))
    ref = _img(tmp_path / "ref.png", (90, 60, 160))
    r = VR._live_subject_hue_sanity(crop, ref)
    assert r["ok"] is False


def test_hue_sanity_accepts_matching_violet_subject(tmp_path):
    crop = _img(tmp_path / "crop.png", (110, 80, 190))
    ref = _img(tmp_path / "ref.png", (90, 60, 160))
    r = VR._live_subject_hue_sanity(crop, ref)
    assert r["ok"] is True


def test_hue_sanity_inconclusive_on_desaturated_subject(tmp_path):
    # near-grey crop: too little saturation to identify a subject family - never a false alarm
    crop = _img(tmp_path / "crop.png", (128, 126, 130))
    ref = _img(tmp_path / "ref.png", (90, 60, 160))
    r = VR._live_subject_hue_sanity(crop, ref)
    assert r["ok"] is True
    assert r.get("inconclusive") is True


def test_hue_sanity_inconclusive_without_reference(tmp_path):
    crop = _img(tmp_path / "crop.png", (235, 130, 100))
    r = VR._live_subject_hue_sanity(crop, None)
    assert r["ok"] is True
    assert r.get("inconclusive") is True
