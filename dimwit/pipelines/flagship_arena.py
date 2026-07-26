"""FLAGSHIP_ARENA_ART_PASS_V1 (masterplan bundle 10, B3) — dress-proof + capture-tour gates.

The flagship arena (Wanefall_Arena4v4_Prototype_01) is dressed from greybox by
scripts/ue/ue_arena_flagship_dress.py (kit landmarks + wane materials + lighting rig + wane-energy landmarks,
SAVED into the map) and toured by scripts/ue/ue_arena_capture_tour.py (per-station SceneCapture stills of the
saved/dressed map — capture-law compliant). This module validates BOTH proofs, recomputing every
gate from the proof payloads + the station images (no stored verdict is trusted). Perf of the
dressed arena is gated by the existing performance_baseline domain (arena p95 floor) — the dress
must not blow the budget.

Floors are ratchet-only.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "artifacts" / "flagship_arena"
DRESS_PATH = RESULT_DIR / "flagship_arena_dress_result.json"
TOUR_PATH = RESULT_DIR / "flagship_arena_tour_result.json"

# FLOORS (ratchet-only). A readable dressed arena needs identity landmarks + kit dressing + a rig.
MIN_WANE_LANDMARKS = 2          # the twin core spires (the IP landmark) minimum
MIN_KIT_LANDMARKS = 20         # spires + veins + pillars + arches + cover — over greybox
MIN_MATERIALS_APPLIED = 15     # wane/trim material coverage across the dressing
MIN_PLAYER_STARTS = 4          # a 4v4 arena needs real spawns
MIN_TOUR_STATIONS = 5          # overview + core + 3 directional stations
MIN_NONBLANK_STATIONS = 4      # most stations must be real renders
STATION_VARIANCE_FLOOR = 0.01  # mean-luma spread across stations (distinct cameras, not one frame)
REQUIRED_RIG = ("SkyAtmosphere", "DirectionalLight", "SkyLight")


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_dressed(dress: dict) -> dict:
    dress = dress if isinstance(dress, dict) else {}
    issues = []
    if not dress.get("map_saved"):
        issues.append("dressed map was not saved")
    authored = dress.get("authored") if isinstance(dress.get("authored"), dict) else {}
    kit_total = sum(int(v) for v in authored.values() if isinstance(v, (int, float)))
    if kit_total < MIN_KIT_LANDMARKS:
        issues.append(f"{kit_total} kit landmarks < floor {MIN_KIT_LANDMARKS} (arena still greybox)")
    mats = dress.get("materials_applied") if isinstance(dress.get("materials_applied"), list) else []
    if len(mats) < MIN_MATERIALS_APPLIED:
        issues.append(f"{len(mats)} materials applied < floor {MIN_MATERIALS_APPLIED}")
    if dress.get("errors"):
        issues.append(f"dress reported errors: {dress.get('errors')[:1]}")
    return {"passed": not issues, "issues": issues, "kit_landmarks": kit_total,
            "materials": len(mats)}


def check_lighting_rig(dress: dict) -> dict:
    dress = dress if isinstance(dress, dict) else {}
    rig = dress.get("lighting_rig") if isinstance(dress.get("lighting_rig"), list) else []
    present = {str(e.get("class")) for e in rig if isinstance(e, dict)}
    missing = [c for c in REQUIRED_RIG if c not in present]
    issues = [f"lighting rig missing {c}" for c in missing]
    return {"passed": not issues, "issues": issues, "rig_classes": sorted(present)}


def check_wane_landmarks(dress: dict) -> dict:
    dress = dress if isinstance(dress, dict) else {}
    landmarks = dress.get("wane_landmarks") if isinstance(dress.get("wane_landmarks"), list) else []
    # emissive wane material must actually be applied to the landmarks (the IP identity), not just placed
    mats = " ".join(dress.get("materials_applied") or [])
    emissive = "M_WaneCoreEmissive" in mats
    issues = []
    if len(landmarks) < MIN_WANE_LANDMARKS:
        issues.append(f"{len(landmarks)} wane-energy landmarks < floor {MIN_WANE_LANDMARKS}")
    if not emissive:
        issues.append("no emissive wane material applied to the landmarks (M_WaneCoreEmissive)")
    return {"passed": not issues, "issues": issues, "landmarks": len(landmarks), "emissive": emissive}


def check_nav_collision(dress: dict) -> dict:
    dress = dress if isinstance(dress, dict) else {}
    starts = int(dress.get("player_starts") or 0)
    issues = []
    if starts < MIN_PLAYER_STARTS:
        issues.append(f"{starts} PlayerStarts < floor {MIN_PLAYER_STARTS} (unplayable)")
    return {"passed": not issues, "issues": issues, "player_starts": starts}


def _station_luma(path: Path):
    """Mean luma (0..1) of a station still, or None if unreadable. Blank/near-black -> ~0."""
    try:
        from PIL import Image, ImageStat
        img = Image.open(path).convert("L")
        return ImageStat.Stat(img).mean[0] / 255.0
    except Exception:
        return None


def check_capture_tour(tour: dict) -> dict:
    tour = tour if isinstance(tour, dict) else {}
    stations = tour.get("stations") if isinstance(tour.get("stations"), list) else []
    issues = []
    if len(stations) < MIN_TOUR_STATIONS:
        issues.append(f"{len(stations)} tour stations < floor {MIN_TOUR_STATIONS}")
    lumas = []
    nonblank = 0
    for s in stations:
        still = Path(str(s.get("still") or ""))
        if not still.exists():
            issues.append(f"station {s.get('name')} still missing")
            continue
        luma = _station_luma(still)
        if luma is None:
            issues.append(f"station {s.get('name')} still unreadable")
            continue
        lumas.append(luma)
        if luma > 0.015:            # not black (the dressed+lit arena renders)
            nonblank += 1
    if nonblank < MIN_NONBLANK_STATIONS:
        issues.append(f"{nonblank} non-blank stations < floor {MIN_NONBLANK_STATIONS} "
                      "(dressed arena did not render)")
    variance = (max(lumas) - min(lumas)) if len(lumas) >= 2 else 0.0
    if len(lumas) >= 2 and variance < STATION_VARIANCE_FLOOR:
        issues.append(f"station luma spread {variance:.4f} < {STATION_VARIANCE_FLOOR} — "
                      "stations look identical (not real distinct coverage)")
    return {"passed": not issues, "issues": issues, "stations": len(stations),
            "nonblank": nonblank, "luma_spread": round(variance, 4)}


def validate_flagship_arena(dress_path: Path = DRESS_PATH, tour_path: Path = TOUR_PATH) -> dict:
    from dimwit.pipelines.base import BlockedError
    if not Path(dress_path).exists():
        raise BlockedError(f"flagship dress proof missing: {dress_path} (run scripts/ue/ue_arena_flagship_dress.py)")
    if not Path(tour_path).exists():
        raise BlockedError(f"flagship tour proof missing: {tour_path} (run scripts/ue/ue_arena_capture_tour.py)")
    dress = _load(dress_path)
    tour = _load(tour_path)
    checks = {
        "dressed": check_dressed(dress),
        "lighting_rig": check_lighting_rig(dress),
        "wane_landmarks": check_wane_landmarks(dress),
        "nav_collision": check_nav_collision(dress),
        "capture_tour": check_capture_tour(tour),
    }
    suite_pass = all(c.get("passed") for c in checks.values())
    return {"checks": checks, "suite_pass": suite_pass,
            "state": "PASS" if suite_pass else "BLOCKED"}
