"""FLAGSHIP_ARENA_ART_PASS_V1 (masterplan bundle 10) — RED-first contract tests.

Pure checks over synthetic dress + tour proof payloads (snapshot law; no live proof touched). The
station-image checks use tiny generated PNGs in a tempdir so blank/variance logic is exercised
without the real captures.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from dimwit.pipelines.flagship_arena import (
    MIN_KIT_LANDMARKS,
    MIN_MATERIALS_APPLIED,
    MIN_NONBLANK_STATIONS,
    MIN_PLAYER_STARTS,
    MIN_TOUR_STATIONS,
    MIN_WANE_LANDMARKS,
    check_capture_tour,
    check_dressed,
    check_lighting_rig,
    check_nav_collision,
    check_wane_landmarks,
)


TMP = Path(tempfile.mkdtemp(prefix="dimwit_flagship_"))


def _png(name: str, luma: int) -> str:
    from PIL import Image
    p = TMP / name
    Image.new("L", (16, 16), color=luma).save(p)
    return str(p)


def _dress(kit=25, mats=20, landmarks=2, starts=9, rig=("SkyAtmosphere", "DirectionalLight", "SkyLight",
                                                        "ExponentialHeightFog"),
           emissive=True, saved=True, errors=None):
    mat_list = [f"Vein_{i}:M_WaneCoreEmissive" for i in range(mats // 2)] + \
               [f"Cover_{i}:M_WaneSurface" for i in range(mats - mats // 2)]
    if not emissive:
        mat_list = [m.replace("M_WaneCoreEmissive", "M_WaneSurface") for m in mat_list]
    return {
        "map_saved": saved,
        "authored": {"core_spire": 2, "vein": 7, "pillar": 4, "arch": 2, "cover": max(0, kit - 15)},
        "materials_applied": mat_list,
        "lighting_rig": [{"class": c, "label": c, "spawned": False} for c in rig],
        "wane_landmarks": [f"Flagship_CoreSpire_{i}" for i in range(landmarks)],
        "player_starts": starts,
        "errors": errors or [],
    }


def _tour(n=5, blank_from=None):
    stations = []
    for i, name in enumerate(["overview", "core", "team_a", "team_b", "flank"][:n]):
        luma = 1 if (blank_from is not None and i >= blank_from) else (30 + i * 12)
        stations.append({"name": name, "still": _png(f"{name}.png", luma), "exists": True})
    return {"stations": stations}


# ------------------------------------------------------------------ dressed

def test_dressed_passes():
    assert check_dressed(_dress())["passed"]


def test_greybox_fails_dressed():
    assert not check_dressed(_dress(kit=MIN_KIT_LANDMARKS - 5))["passed"]


def test_too_few_materials_fails():
    assert not check_dressed(_dress(mats=MIN_MATERIALS_APPLIED - 3))["passed"]


def test_unsaved_map_fails():
    assert not check_dressed(_dress(saved=False))["passed"]


def test_dress_errors_fail():
    assert not check_dressed(_dress(errors=["missing kit mesh SM_Kit_Spire"]))["passed"]


# ------------------------------------------------------------------ lighting rig

def test_full_rig_passes():
    assert check_lighting_rig(_dress())["passed"]


def test_missing_skyatmosphere_fails():
    assert not check_lighting_rig(_dress(rig=("DirectionalLight", "SkyLight")))["passed"]


# ------------------------------------------------------------------ wane landmarks

def test_wane_landmarks_pass():
    assert check_wane_landmarks(_dress())["passed"]


def test_no_emissive_landmark_fails():
    assert not check_wane_landmarks(_dress(emissive=False))["passed"]


def test_too_few_landmarks_fails():
    assert not check_wane_landmarks(_dress(landmarks=MIN_WANE_LANDMARKS - 1))["passed"]


# ------------------------------------------------------------------ nav / collision

def test_starts_pass():
    assert check_nav_collision(_dress())["passed"]


def test_too_few_starts_fails():
    assert not check_nav_collision(_dress(starts=MIN_PLAYER_STARTS - 1))["passed"]


# ------------------------------------------------------------------ capture tour

def test_tour_passes():
    assert check_capture_tour(_tour())["passed"]


def test_too_few_stations_fails():
    assert not check_capture_tour(_tour(n=MIN_TOUR_STATIONS - 1))["passed"]


def test_blank_stations_fail():
    # most stations black -> dressed arena did not render
    assert not check_capture_tour(_tour(blank_from=1))["passed"]


def test_identical_stations_fail():
    # all stations same luma -> not real distinct coverage
    from PIL import Image
    same = str(TMP / "same.png")
    Image.new("L", (16, 16), color=40).save(same)
    tour = {"stations": [{"name": f"s{i}", "still": same, "exists": True} for i in range(5)]}
    assert not check_capture_tour(tour)["passed"]


# ------------------------------------------------------------------ ratchet

def test_floors_are_ratchet():
    assert MIN_WANE_LANDMARKS >= 2
    assert MIN_KIT_LANDMARKS >= 20
    assert MIN_MATERIALS_APPLIED >= 15
    assert MIN_PLAYER_STARTS >= 4
    assert MIN_TOUR_STATIONS >= 5
    assert MIN_NONBLANK_STATIONS >= 4
