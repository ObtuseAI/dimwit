"""Dimwit perception — PIXEL-TRUTH analysis of real rendered output (PNG contact sheets / captures).

This is the Dimwit V2 breakthrough: validators stop trusting *declared* spec fields and instead MEASURE
the actual pixels — magenta/black-blob/white-junk presence, red/orange weak-point read, teal Wane palette,
foreground silhouette contrast, edge density. It is the machine analogue of the human-screenshot-override
law: what the screen actually shows beats what the spec claims.

Deps: numpy + Pillow (both permissive, already present). Vectorized; no per-pixel Python loops.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


MEAN_LUMINANCE_FLOOR = 0.18    # below this a render is "too dark to read" -> hard fail (validation §Phase 0)


def _load_norm(path, max_dim: int = 360):
    """Load a PNG as a normalized float32 RGB array (0..1), downscaled. None if missing/unreadable."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        im = Image.open(p).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    return np.asarray(im, dtype=np.float32) / 255.0


def image_delta(a_path, b_path, max_dim: int = 360) -> float:
    """Mean absolute per-channel difference between two renders (0..1). -1.0 if either is missing (BLOCKED
    signal). Used to prove a character is ANIMATING (two frames must differ) — never trust byte size."""
    a = _load_norm(a_path, max_dim)
    b = _load_norm(b_path, max_dim)
    if a is None or b is None:
        return -1.0
    if a.shape != b.shape:
        bi = Image.fromarray((np.clip(b, 0, 1) * 255).astype("uint8")).resize((a.shape[1], a.shape[0]))
        b = np.asarray(bi, dtype=np.float32) / 255.0
    return round(float(np.mean(np.abs(a - b))), 5)


def image_mirror_diff(path, max_dim: int = 360) -> float:
    """Horizontal-mirror luminance-mass difference (0..1) for silhouette symmetry. -1.0 if missing."""
    a = _load_norm(path, max_dim)
    if a is None:
        return -1.0
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    mirrored = lum[:, ::-1]
    denom = float(lum.mean()) or 1.0
    return round(float(np.mean(np.abs(lum - mirrored)) / denom), 5)


def _rgb_to_hsv(arr: np.ndarray) -> np.ndarray:
    """Vectorized RGB(0..1)->HSV(h 0..360, s 0..1, v 0..1). arr shape (...,3)."""
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.max(arr, axis=-1)
    mn = np.min(arr, axis=-1)
    d = mx - mn
    h = np.zeros_like(mx)
    mask = d > 1e-9
    # red is max
    idx = (mx == r) & mask
    h[idx] = (60 * ((g[idx] - b[idx]) / d[idx]) + 360) % 360
    idx = (mx == g) & mask
    h[idx] = (60 * ((b[idx] - r[idx]) / d[idx]) + 120) % 360
    idx = (mx == b) & mask
    h[idx] = (60 * ((r[idx] - g[idx]) / d[idx]) + 240) % 360
    s = np.where(mx > 1e-9, d / np.where(mx > 1e-9, mx, 1), 0.0)
    v = mx
    return np.stack([h, s, v], axis=-1)


def analyze_image(path: str | Path, max_dim: int = 360, subject_only: bool = False,
                  subject_min_frac: float = 0.01, chroma_key=None, chroma_dist: float = 0.34,
                  bg_path=None, bg_dist: float = 0.06) -> dict:
    """Measure WANEFALL-relevant palette + readability metrics from a real PNG. Returns fractions 0..1.

    subject_only: when True, all palette/luminance metrics are computed over the SUBJECT (the foreground
    silhouette) instead of the whole frame. This is for HERO/studio captures where the character sits in a
    void/backdrop — measuring the whole frame falsely reads "too_dark" (the black void) and dilutes the
    palette (teal etc.) by the empty background. Judge the character, not the backdrop. (Default False keeps
    whole-frame behavior for in-game captures + all existing callers/tests.)"""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"missing image {p}"}
    im = Image.open(p).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    a = np.asarray(im, dtype=np.float32) / 255.0
    hsv = _rgb_to_hsv(a)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    n = H.size

    near_black = (V < 0.12)
    white_junk = (V > 0.92) & (S < 0.12)
    magenta = (S > 0.30) & (V > 0.25) & (((H >= 285) & (H <= 340)))
    red = (S > 0.40) & (V > 0.30) & ((H <= 16) | (H >= 344))
    orange = (S > 0.40) & (V > 0.35) & (H > 16) & (H <= 45)
    teal = (S > 0.22) & (V > 0.18) & (H >= 150) & (H <= 210)

    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    fg = (S > 0.35) | (V < 0.10) | (V > 0.85)
    fg_lum = float(lum[fg].mean()) if fg.any() else 0.0
    bg_lum = float(lum[~fg].mean()) if (~fg).any() else 0.0
    silhouette_contrast = abs(fg_lum - bg_lum)
    gy, gx = np.gradient(lum)
    edge_density = float(np.mean(np.sqrt(gx * gx + gy * gy)))

    # SUBJECT mask. The ROBUST way (chroma_key=(r,g,b)) is to capture against a known key-color backdrop and
    # take the subject = pixels FAR from that key color — isolates the character regardless of its palette or
    # the scene behind it (the keyed backdrop is never measured, so a magenta key can't trip not_magenta).
    # The heuristic fallback (subject_only, no key) is saturated-OR-off-median, which is fooled by a lit
    # backdrop/environment — prefer the chroma key for studio/hero captures.
    if bg_path is not None and Path(bg_path).exists():
        # BACKGROUND SUBTRACTION (most robust): subject = pixels that differ from an empty-scene reference shot
        # taken with the SAME camera+lights. Isolates the character against any background, no keyed backdrop.
        bgim = Image.open(bg_path).convert("RGB").resize((a.shape[1], a.shape[0]))
        b = np.asarray(bgim, dtype=np.float32) / 255.0
        subj = np.max(np.abs(a - b), axis=-1) > float(bg_dist)
    elif chroma_key is not None:
        kr, kg, kb = [float(c) for c in chroma_key]
        dist = np.sqrt((a[..., 0] - kr) ** 2 + (a[..., 1] - kg) ** 2 + (a[..., 2] - kb) ** 2)
        subj = dist > float(chroma_dist)
    else:
        subj = (S > 0.20) | (np.abs(lum - float(np.median(lum))) > 0.10)
    use_subj = bool((subject_only or chroma_key is not None or bg_path is not None)
                    and (float(np.count_nonzero(subj)) / n) >= subject_min_frac)
    denom = subj if use_subj else np.ones_like(subj, dtype=bool)
    nd = float(np.count_nonzero(denom)) or 1.0
    frac = lambda m: float(np.count_nonzero(m & denom)) / nd
    mean_lum = float(lum[denom].mean()) if np.any(denom) else 0.0

    return {
        "ok": True, "path": str(p), "pixels": int(n),
        "subject_measured": use_subj, "subject_fraction": round(float(np.count_nonzero(subj)) / n, 4),
        "mean_luminance": round(mean_lum, 4),
        "near_black_fraction": round(frac(near_black), 4),
        "white_junk_fraction": round(frac(white_junk), 4),
        "magenta_fraction": round(frac(magenta), 4),
        "red_fraction": round(frac(red), 4),
        "orange_fraction": round(frac(orange), 4),
        "teal_fraction": round(frac(teal), 4),
        "red_or_orange_fraction": round(frac(red | orange), 4),
        "silhouette_contrast": round(silhouette_contrast, 4),
        "edge_density": round(edge_density, 4),
    }


def measure_style_compliance(metrics: dict) -> dict:
    """Map measured pixels -> the WANEFALL style-law dimensions (0..1). HARD-FAIL on real magenta/white/blob."""
    if not metrics.get("ok"):
        return {"ok": False, "scores": {}, "hard_fails": [], "note": metrics.get("error", "no metrics")}
    m = metrics
    hard_fails = []
    # too-dark-to-read is its own hard fail (an albedo/material that renders near-black under real lighting —
    # the legacy-Phong/dark-blob regression class — independent of the near-black-fraction blob test below)
    if m.get("mean_luminance", 1.0) < MEAN_LUMINANCE_FLOOR:
        hard_fails.append({"trait": "too_dark", "dimension": "not_black_blob", "measured": m.get("mean_luminance")})
    if m["magenta_fraction"] > 0.015:
        hard_fails.append({"trait": "magenta", "dimension": "not_magenta_dominant", "measured": m["magenta_fraction"]})
    if m["white_junk_fraction"] > 0.06:
        hard_fails.append({"trait": "white_debug", "dimension": "not_white_debug_junk", "measured": m["white_junk_fraction"]})
    # black-blob: a lot of near-black AND low silhouette contrast (the mass doesn't separate)
    if m["near_black_fraction"] > 0.45 and m["silhouette_contrast"] < 0.12:
        hard_fails.append({"trait": "black_blob", "dimension": "not_black_blob", "measured": m["near_black_fraction"]})
    scores = {
        "not_magenta_dominant": 0.0 if m["magenta_fraction"] > 0.015 else 1.0,
        "not_white_debug_junk": 0.0 if m["white_junk_fraction"] > 0.06 else 1.0,
        "not_black_blob": float(np.clip(1.0 - max(0.0, (m["near_black_fraction"] - 0.30)) * 1.6, 0.0, 1.0)),
        "palette_discipline": float(np.clip(0.4 + m["teal_fraction"] * 2.5 - m["magenta_fraction"] * 4.0, 0.0, 1.0)),
        "red_weak_point_reads": float(np.clip(m["red_or_orange_fraction"] * 14.0, 0.0, 1.0)),
        "silhouette_readability": float(np.clip(m["silhouette_contrast"] * 3.2, 0.0, 1.0)),
        "third_person_camera_readability": float(np.clip(m["silhouette_contrast"] * 2.6 + m["red_or_orange_fraction"] * 4.0, 0.0, 1.0)),
    }
    return {"ok": True, "scores": {k: round(v, 4) for k, v in scores.items()}, "hard_fails": hard_fails,
            "measured_from_pixels": True}


def perceive_evidence(evidence: dict) -> dict:
    """Analyze whatever real images an asset candidate declares (hero + player-camera contact sheets)."""
    out = {}
    for key in ("hero_contact_sheet", "player_camera_contact_sheet"):
        path = evidence.get(key)
        if path and Path(path).exists():
            metrics = analyze_image(path)
            out[key] = {"metrics": metrics, "style": measure_style_compliance(metrics)}
    return out


# --------------------------------------------------------------------------- target identity / structure
def _silhouette_grid(arr: np.ndarray, grid: int) -> np.ndarray:
    """Foreground occupancy per cell (0..1) on a grid×grid lattice. Foreground = saturated OR clearly
    off-background luminance. Exposure-invariant (uses the image's own median as the background level)."""
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    s = _rgb_to_hsv(arr)[..., 1]
    med = float(np.median(lum))
    fg = ((s > 0.22) | (np.abs(lum - med) > 0.15)).astype(np.float32)
    im = Image.fromarray((fg * 255).astype("uint8")).resize((grid, grid))
    return np.asarray(im, dtype=np.float32) / 255.0


def _coarse_lum(arr: np.ndarray, grid: int) -> np.ndarray:
    """Per-cell luminance, each grid normalized to its own 0..1 contrast (so the structural layout is
    compared, not the absolute exposure — a render and its reference rarely share exposure)."""
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    im = Image.fromarray((np.clip(lum, 0, 1) * 255).astype("uint8")).resize((grid, grid))
    g = np.asarray(im, dtype=np.float32) / 255.0
    lo, hi = float(g.min()), float(g.max())
    return (g - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(g)


def compare_to_target(capture, reference, sil_grid: int = 64, region_grid: int = 12) -> dict:
    """IDENTITY/STRUCTURE similarity of a rendered capture to its declared reference — the metric that
    catches a flawlessly-rendered WRONG asset. This is deliberately NOT a palette/quality score: structure
    dominates, palette is only a mild multiplier so a recolor can't fake identity and a lighting change
    can't destroy it.

        target_similarity = sqrt(silhouette_iou) * region_match * clamp(palette_sim, 0.5, 1.0)

    * silhouette_iou   — shape agreement (foreground mask IoU). sqrt softens it (an exact 1.0 IoU is
                          unrealistic across render-vs-concept; the sqrt keeps a 0.6 IoU meaningful).
    * region_match     — per-region structural agreement; the WEAKEST QUARTILE of cells sets it, so a
                          wrong head/limb (a localized region) caps the score even if the rest agrees.
    * palette_sim      — palette closeness, CLAMPED to [0.5, 1.0]: it can never raise identity above
                          structure, and a palette mismatch can at most halve it (never zero a real match).

    FAIL-CLOSED: a missing/unreadable reference returns {ok: False, blocked: True, target_similarity: None}
    — identity can never be certified without something to certify against.
    """
    a = _load_norm(capture)
    if a is None:
        return {"ok": False, "blocked": True, "target_similarity": None,
                "reason": f"capture missing/unreadable: {capture}"}
    b = _load_norm(reference)
    if b is None:
        return {"ok": False, "blocked": True, "target_similarity": None,
                "reason": f"reference missing/unreadable: {reference}"}

    # silhouette IoU
    ga, gb = _silhouette_grid(a, sil_grid), _silhouette_grid(b, sil_grid)
    A, B = ga >= 0.5, gb >= 0.5
    union = int(np.count_nonzero(A | B))
    iou = (int(np.count_nonzero(A & B)) / union) if union else 0.0

    # per-region structural agreement; weakest quartile is the binding region
    ca, cb = _coarse_lum(a, region_grid), _coarse_lum(b, region_grid)
    cell_sim = 1.0 - np.abs(ca - cb)               # (region_grid, region_grid) in 0..1
    flat = np.sort(cell_sim.ravel())
    k = max(1, flat.size // 4)
    region_weakest_quartile = float(flat[:k].mean())
    region_weakest_cell = float(flat[0])

    # palette closeness over the WANEFALL-relevant buckets, clamped so it is only a mild multiplier
    ma, mb = analyze_image(capture), analyze_image(reference)
    keys = ("near_black_fraction", "white_junk_fraction", "magenta_fraction",
            "red_or_orange_fraction", "teal_fraction", "mean_luminance")
    if ma.get("ok") and mb.get("ok"):
        palette_sim = 1.0 - float(np.mean([abs(ma[k2] - mb[k2]) for k2 in keys]))
    else:
        palette_sim = 0.5
    palette_mult = float(np.clip(palette_sim, 0.5, 1.0))

    ts = float(np.clip((iou ** 0.5) * region_weakest_quartile * palette_mult, 0.0, 1.0))
    return {
        "ok": True, "blocked": False,
        "target_similarity": round(ts, 4),
        "silhouette_iou": round(float(iou), 4),
        "region_match": round(region_weakest_quartile, 4),
        "region_weakest_cell": round(region_weakest_cell, 4),
        "palette_sim": round(float(palette_sim), 4),
        "palette_mult": round(palette_mult, 4),
        "capture": str(capture), "reference": str(reference),
    }


# --------------------------------------------------------------------------- rig DEFORMATION (the #32 gap)
# Structural rig QA (weight coverage / <=4 influences / bone count) is BLIND to how the mesh actually deforms
# when posed: it cannot see the candy-wrapper twist COLLAPSE (a joint pinches the silhouette to nothing) or
# the skinning EXPLOSION (a bad weight flings vertices into spikes / detached shards). These are pixel-truth
# checks on extreme-pose renders — exactly "GLM deformation QA on extreme-pose renders" that rigging.py:10
# left as the next layer.
def _deform_fg_mask(path, max_dim: int = 120):
    """Exposure-invariant foreground mask of a posed render (same fg rule as _silhouette_grid)."""
    p = Path(path)
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    a = np.asarray(im, dtype=np.float32) / 255.0
    s = _rgb_to_hsv(a)[..., 1]
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    med = float(np.median(lum))
    return (s > 0.22) | (np.abs(lum - med) > 0.15)


def _largest_component_fraction(mask) -> tuple:
    """(largest_connected_fraction, component_count) over a boolean mask, 4-connectivity. Dependency-free
    stack flood-fill (no scipy). A healthy deformation is ONE connected silhouette; detached shards (skinning
    spikes) drop the largest-fraction below 1.0 and raise the component count."""
    h, w = mask.shape
    total = int(mask.sum())
    if total == 0:
        return 0.0, 0
    visited = np.zeros((h, w), dtype=bool)
    best, ncomp = 0, 0
    m = mask
    for i in range(h):
        for j in range(w):
            if m[i, j] and not visited[i, j]:
                ncomp += 1
                size = 0
                stack = [(i, j)]
                visited[i, j] = True
                while stack:
                    y, x = stack.pop()
                    size += 1
                    if y > 0 and m[y - 1, x] and not visited[y - 1, x]:
                        visited[y - 1, x] = True; stack.append((y - 1, x))
                    if y < h - 1 and m[y + 1, x] and not visited[y + 1, x]:
                        visited[y + 1, x] = True; stack.append((y + 1, x))
                    if x > 0 and m[y, x - 1] and not visited[y, x - 1]:
                        visited[y, x - 1] = True; stack.append((y, x - 1))
                    if x < w - 1 and m[y, x + 1] and not visited[y, x + 1]:
                        visited[y, x + 1] = True; stack.append((y, x + 1))
                if size > best:
                    best = size
    return best / total, ncomp


def deformation_health(pose, bind, area_band=(0.55, 1.85), min_connected: float = 0.85) -> dict:
    """Does the rigged mesh DEFORM cleanly at this stress pose vs the bind pose? Catches the COLLAPSE
    (silhouette area pinches well below the bind — candy-wrapper/twist) and the EXPLOSION (area blows up, or
    the silhouette fragments into detached spikes — bad skinning weights). Pixel-truth, exposure-invariant.

        deformation_score = MIN(connectedness, band_health)   # weakest-link: a collapse OR a shard tanks it

    FAIL-CLOSED: a missing/unreadable pose or bind capture returns {ok: False, blocked: True, score: None}."""
    mp, mb = _deform_fg_mask(pose), _deform_fg_mask(bind)
    if mp is None:
        return {"ok": False, "blocked": True, "deformation_score": None, "reason": f"pose capture missing: {pose}"}
    if mb is None:
        return {"ok": False, "blocked": True, "deformation_score": None, "reason": f"bind capture missing: {bind}"}
    pose_area, bind_area = float(mp.sum()), float(mb.sum())
    if bind_area < 1:
        return {"ok": False, "blocked": True, "deformation_score": None, "reason": "bind silhouette empty"}
    area_ratio = pose_area / bind_area
    conn, ncomp = _largest_component_fraction(mp)
    lo, hi = area_band
    if lo <= area_ratio <= hi:
        band_health = 1.0
    elif area_ratio < lo:
        band_health = float(np.clip(area_ratio / lo, 0.0, 1.0))
    else:
        band_health = float(np.clip(hi / area_ratio, 0.0, 1.0))
    score = float(np.clip(min(conn, band_health), 0.0, 1.0))
    issues = []
    if area_ratio < lo:
        issues.append(f"silhouette COLLAPSE: posed area {area_ratio:.2f}x bind (<{lo}) — candy-wrapper/twist pinch")
    if area_ratio > hi:
        issues.append(f"silhouette EXPLOSION: posed area {area_ratio:.2f}x bind (>{hi}) — skinning blowup")
    if conn < min_connected:
        issues.append(f"silhouette FRAGMENTED: largest piece {conn:.2f} across {ncomp} parts — skinning spikes")
    return {"ok": True, "blocked": False, "deformation_score": round(score, 4),
            "passed": bool(lo <= area_ratio <= hi and conn >= min_connected),
            "area_ratio": round(area_ratio, 4), "connectedness": round(conn, 4),
            "components": ncomp, "issues": issues, "pose": str(pose)}


def _mean_abs_delta(a_path, b_path, max_dim: int = 160) -> float:
    """Mean absolute pixel difference between two renders (0..1). ~0 => the two frames are identical."""
    pa, pb = Path(a_path), Path(b_path)
    if not pa.exists() or not pb.exists():
        return -1.0
    ia = Image.open(pa).convert("RGB"); ib = Image.open(pb).convert("RGB")
    w, h = ia.size
    scale = min(1.0, max_dim / max(w, h))
    size = (max(1, int(w * scale)), max(1, int(h * scale)))
    a = np.asarray(ia.resize(size), dtype=np.float32) / 255.0
    b = np.asarray(ib.resize(size), dtype=np.float32) / 255.0
    return float(np.abs(a - b).mean())


def rig_deformation_over_poses(bind, pose_captures: dict, min_pose_displacement: float = 0.004, **kw) -> dict:
    """Weakest-link deformation health across a set of stress poses ({pose_name: png}). The WORST pose sets
    the rig's score — a rig is only as good as its worst joint.

    FAIL-CLOSED on two ways the evidence can be vacuous:
      * an unscorable pose (missing/unreadable capture) BLOCKS — you cannot certify what you couldn't measure;
      * a FROZEN rig BLOCKS — if every stress pose is pixel-identical to bind, the animation never actually
        evaluated (the headless-anim-needs-PIE trap), so there was NO deformation to validate. A rig that
        never moved must NEVER pass deformation QA just because a still frame has no artifacts."""
    if not pose_captures:
        return {"ok": False, "blocked": True, "deformation_score": None, "reason": "no pose captures declared"}
    per = {name: deformation_health(png, bind, **kw) for name, png in pose_captures.items()}
    scorable = {n: v for n, v in per.items() if v.get("deformation_score") is not None}
    if len(scorable) != len(pose_captures):
        missing = [n for n in pose_captures if n not in scorable]
        return {"ok": False, "blocked": True, "deformation_score": None, "per_pose": per,
                "reason": f"unmeasurable poses (fail-closed): {missing}"}
    # anti-frozen: the stress poses must actually DIFFER from bind (otherwise the rig never posed)
    displacement = {n: _mean_abs_delta(p, bind) for n, p in pose_captures.items()}
    moved = max(displacement.values()) if displacement else 0.0
    if moved < min_pose_displacement:
        return {"ok": False, "blocked": True, "deformation_score": None, "per_pose": per,
                "pose_displacement": {n: round(d, 5) for n, d in displacement.items()},
                "reason": f"FROZEN rig: every stress pose is identical to bind (max displacement {moved:.5f} "
                          f"< {min_pose_displacement}) — animation did not evaluate; deformation NOT exercised"}
    worst_name = min(scorable, key=lambda n: scorable[n]["deformation_score"])
    return {"ok": True, "blocked": False, "deformation_score": scorable[worst_name]["deformation_score"],
            "worst_pose": worst_name, "passed": all(v["passed"] for v in scorable.values()),
            "pose_displacement": {n: round(d, 5) for n, d in displacement.items()}, "per_pose": per}


if __name__ == "__main__":
    import sys
    for img in sys.argv[1:]:
        print(json.dumps(analyze_image(img), indent=2))
        print(json.dumps(measure_style_compliance(analyze_image(img)), indent=2))
