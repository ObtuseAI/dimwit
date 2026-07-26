"""Dimwit ELITE OPTICS — semantic image/video understanding on top of pixel-truth.

perception.py answers "what colors/contrast are in these pixels". optics.py answers the questions a senior game
artist would: is the character readable, correctly PROPORTIONED (not morphed/disfigured), clean-silhouette, on-
model vs the creation, free of stray placeholder geometry — and for VIDEO, does it move/deform correctly. It
fuses GLM-5V vision (via dimwit.llm) with perception's pixel metrics into one honest verdict.

DOCTRINE (fail-closed, mirrors the validation harness): if the LLM is unavailable the semantic verdict is
BLOCKED, never a fake PASS; the pixel verdict still stands. A measured pixel hard-fail OR a semantic
critical/disfigured finding forces a hard fail. The model may FAIL but never silently PASS.

  from dimwit.optics import judge_character, judge_image, judge_motion
  v = judge_character("render.png", reference="creation_cover.png")
  v["passed"], v["hard_fail"], v["issues"], v["semantic"], v["pixel"]
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from dimwit import perception, llm

OPTICS_SYSTEM = (
    "You are a SENIOR game-art QA lead for WANEFALL (a UE5 third-person arena shooter; clean, crisp, "
    "handcrafted alien characters; NO glow hacks, NO AI-slop ornament clutter). You judge rendered output the "
    "way a human reviewer would on a screenshot, and you are STRICT and HONEST. Report defects plainly. "
    "COLOR/IDENTITY AUTHORITY: every character has its OWN palette and materials — when a reference/creation "
    "image is provided it IS the sole color and identity target for THIS character; never judge against a "
    "generic house palette. Determine color_on_model by CHECKLIST, never by overall impression: "
    "(a) name the hue family of the reference's armor and of the render's armor. Directly NEIGHBORING families "
    "on the color wheel (blue and violet/purple, orange and red, teal and cyan) count as the SAME family, and "
    "saturation/brightness may differ between capture rigs — a darker, lighter, or more saturated take on the "
    "same or a neighboring family MATCHES. A mismatch means a clear jump: a grey/silver DESATURATED figure vs "
    "a violet reference, or orange vs blue. "
    "(b) compare seam CONTRAST, not seam existence: in the reference the plate seams read as clearly DARK "
    "lines against the armor; if the render's seams are faint, washed, or low-contrast so neighboring plates "
    "blur toward one smooth surface, articulation is LOST even if you can trace where seams would be. "
    "color_on_model=true ONLY if the hue families match AND the render's seam contrast is comparable to the "
    "reference's. A pale washed-out figure has LOST the material identity: color_on_model=false and severity "
    "at least major, regardless of how its overall brightness compares to the reference. "
    "Always answer ONLY with the requested JSON object. "
    "IMPORTANT DEFINITIONS: (1) 'stray_placeholder_geometry' means UE engine debug primitives (cubes, spheres, "
    "capsule shapes) physically attached to the character as floating child objects — it does NOT mean the "
    "character itself is using an intentional proof/test material. (2) 'disfigured_or_morphed' means the mesh "
    "geometry is distorted, melted, stretched, or incorrectly deformed — a character rendered with a uniform "
    "proof/studio material (flat grey or silver) is NOT disfigured; judge the MESH FORM and SILHOUETTE, not "
    "whether the material has textures. This proof-material tolerance applies ONLY to mesh-form fields "
    "(disfigured_or_morphed, correctly_proportioned, clean_silhouette): when a REFERENCE image is provided, "
    "material fidelity IS being judged, and a flat/washed/proof-looking surface where the reference shows "
    "articulated colored armor must still set color_on_model=false with severity at least major — never "
    "excuse it as an acceptable QA proof render."
)

CHAR_RUBRIC = (
    "Judge this rendered game CHARACTER. IMAGE ORDER: image 1 is the RENDER UNDER JUDGEMENT; image 2 (when "
    "present) is the AUTHORITATIVE REFERENCE it must match — never the other way around. "
    "Return JSON exactly: {"
    "\"readable\": bool, "
    "\"correctly_proportioned\": bool, "          # false if mesh is morphed/melted/stretched (material irrelevant)
    "\"disfigured_or_morphed\": bool, "           # true ONLY if mesh geometry itself is distorted; proof material ≠ disfigured
    "\"clean_silhouette\": bool, "
    "\"reference_hue_family\": \"one word: the reference armor's hue family, or n/a without a reference\", "
    "\"render_hue_family\": \"one word: the rendered armor's hue family\", "
    "\"seam_lines_visible\": bool, "                  # are the reference's dark plate-seam lines clearly visible in the render?
    "\"color_on_model\": bool, "                      # derive: hue families match AND seam articulation preserved

    "\"stray_placeholder_geometry\": bool, "      # true ONLY if UE debug cubes/spheres/capsules are floating on the character
    "\"weapon_or_attachment_visible\": \"yes|no|n/a\", "
    "\"matches_reference\": \"yes|partial|no|n/a\", "
    "\"defects\": [\"short concrete defect strings\"], "
    "\"severity\": \"none|minor|major|critical\", "
    "\"score\": 0.0-1.0, "
    "\"summary\": \"one sentence\"}"
)


@dataclass
class VisualVerdict:
    ok: bool = False
    passed: bool = False
    hard_fail: bool = False
    score: float = 0.0
    issues: list = field(default_factory=list)
    semantic: dict = field(default_factory=dict)     # GLM-5V structured judgement (or {"blocked": ...})
    pixel: dict = field(default_factory=dict)         # perception metrics + style compliance
    evidence: list = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


def _pixel(image: str | Path, subject_only: bool = False) -> dict:
    m = perception.analyze_image(image, subject_only=subject_only)
    return {"metrics": m, "style": perception.measure_style_compliance(m) if m.get("ok") else {}}


def _semantic(rubric: str, images: list, temperature: float | None = None,
              detail_px: int | None = None, model: str | None = None) -> dict:
    if not llm.is_configured():
        return {"blocked": "LLM not configured (no OPENROUTER_API_KEY)"}
    imgs = [str(p) for p in images if p and Path(p).exists()]
    if not imgs:
        return {"blocked": "no images on disk to analyze"}
    try:
        r = llm.vision(rubric, imgs, response_json=True, system=OPTICS_SYSTEM, temperature=temperature,
                       max_image_px=detail_px, model=model)
    except llm.LLMError as e:
        return {"blocked": f"LLM error: {e}"}
    if not r.get("ok"):
        return {"blocked": "empty LLM response"}
    parsed = llm.parse_json(r.get("content", ""))
    if parsed is None:
        return {"blocked": "unparseable LLM response", "raw": (r.get("content") or "")[:300]}
    parsed["_model"] = r.get("model")
    return parsed


def judge_character(image: str | Path, reference: str | Path | None = None,
                    require_semantic: bool = True, subject_only: bool = False,
                    temperature: float | None = None, model: str | None = None) -> dict:
    """Elite character QA: pixel-truth + GLM-5V semantic judgement fused, fail-closed.

    subject_only: when True, pixel metrics are measured over the foreground subject only —
    correct for HERO/studio captures where the character sits against a dark void backdrop
    (whole-frame measurement falsely reads 'too_dark'). See perception.analyze_image for details.
    """
    v = VisualVerdict(evidence=[str(image)] + ([str(reference)] if reference else []))
    v.pixel = _pixel(image, subject_only=subject_only)
    images = [image] + ([reference] if reference else [])
    # detail_px 1200: character judging hinges on ~1px seam lines in 1200x900 captures — the config
    # 896 downscale blurs exactly the evidence the color_on_model checklist asks the judge to read.
    v.semantic = _semantic(CHAR_RUBRIC, images, temperature=temperature, detail_px=1200, model=model)

    # pixel hard fails (too dark / magenta / white-junk / black-blob)
    pix_hard = (v.pixel.get("style", {}) or {}).get("hard_fails", [])
    if pix_hard:
        v.issues += [f"pixel:{h['trait']}" for h in pix_hard]
        v.hard_fail = True

    sem = v.semantic
    if "blocked" in sem:
        # semantic unavailable: pixel verdict stands, but we CANNOT certify -> not a PASS if semantic required
        v.ok = v.pixel.get("metrics", {}).get("ok", False)
        v.score = round(0.5 if not v.hard_fail else 0.0, 3)
        v.passed = (not require_semantic) and not v.hard_fail and v.ok
        if require_semantic:
            v.issues.append(f"semantic BLOCKED: {sem['blocked']}")
        return v.dict()

    v.ok = True
    # semantic hard fails: disfigured/morphed, critical severity, or stray placeholder geometry
    if sem.get("disfigured_or_morphed") is True or sem.get("severity") == "critical":
        v.hard_fail = True
        v.issues.append("semantic:disfigured_or_morphed")
    if sem.get("stray_placeholder_geometry") is True:
        v.issues.append("semantic:stray_placeholder_geometry")
    for d in (sem.get("defects") or [])[:8]:
        v.issues.append(f"defect:{d}")
    v.score = round(float(sem.get("score", 0.0)), 3)
    # IDENTITY: when a reference is supplied, the render must actually MATCH it. A flawlessly-rendered but
    # WRONG character (readable, proportioned, high score) must NOT pass — matches_reference is load-bearing,
    # not advisory. n/a when a reference WAS given is a non-answer and fails closed.
    matches = sem.get("matches_reference", "n/a")
    if reference is not None and matches not in ("yes", "partial"):
        v.issues.append(f"semantic:matches_reference={matches} (render does not match the declared target)")
    # COLOR: with a reference attached, color_on_model is LOAD-BEARING — a washed/off-palette render of the
    # RIGHT character (readable, proportioned, decent score) must NOT pass. Exactly the hole the low-mip
    # silver captures slipped through: the judge said color_on_model=false and the formula ignored it.
    color_ok = bool(sem.get("color_on_model"))
    if reference is not None and not color_ok:
        v.issues.append("semantic:color_on_model=false (palette/material deviates from the reference)")
    v.passed = (not v.hard_fail) and bool(sem.get("readable")) and bool(sem.get("correctly_proportioned")) \
        and sem.get("severity") in ("none", "minor") and v.score >= 0.6 \
        and (reference is None or (matches in ("yes", "partial") and color_ok))
    return v.dict()


# --------------------------------------------------------------------------- judge quorum (H1B2)
# CROSS-VENDOR panel (operator directive 2026-07-02: MiniMax M3 into the imagery mix): single-model
# quorums proved worthless against run-level provider swings — identical calibration runs minutes
# apart flipped between 4/4 and 2/4 because all three votes rode the same backend mood. One vote per
# MODEL from three different vendors makes the votes actually independent. The panel is EXPLICIT
# (not the config default): glm-5v-turbo was calibration-proven to coin-flip on the goldens
# (0.55-fail <-> 0.9-pass on identical input) and lost its seat. Any change here must re-earn
# a stability-2 golden calibration before the suite goes green.
QUORUM_MODELS = ("google/gemini-3.5-flash", "minimax/minimax-m3", "qwen/qwen3-vl-32b-instruct")


def _aggregate_quorum(verdicts: list) -> dict:
    """Fail-closed aggregation of N independent judge_character verdicts.

    The single-shot judge coin-flipped 0.4-0.65 for days over one unchanged washed subject, so one
    sample is never trusted again: score is the MEDIAN (lower median on even N), passing takes a
    majority of the FULL panel — blocked calls count against passing, never for it (2+ blocked of
    3 -> the whole verdict is blocked; 1 blocked of 3 -> both live calls must pass). Issues keep
    only what a majority of live calls reported, so single-call flake noise dies here while a
    consistently-reported defect survives.
    """
    if not verdicts:
        return VisualVerdict(issues=["quorum: no verdicts"]).dict()
    n = len(verdicts)
    need = n // 2 + 1
    live = [v for v in verdicts if "blocked" not in (v.get("semantic") or {})]
    blocked = [v for v in verdicts if "blocked" in (v.get("semantic") or {})]

    scores = sorted(float(v.get("score", 0.0)) for v in verdicts)
    median = scores[(len(scores) - 1) // 2]

    out = VisualVerdict(evidence=list(verdicts[0].get("evidence") or []),
                        pixel=dict(verdicts[0].get("pixel") or {}))
    quorum = {"n": n, "scores": [round(float(v.get("score", 0.0)), 3) for v in verdicts],
              "pass_votes": sum(1 for v in live if v.get("passed")),
              "hard_fail_votes": sum(1 for v in live if v.get("hard_fail")),
              "blocked_votes": len(blocked),
              "models": [str((v.get("semantic") or {}).get("_model") or "blocked") for v in verdicts],
              "summaries": [str((v.get("semantic") or {}).get("summary")
                                or (v.get("semantic") or {}).get("blocked") or "")[:200] for v in verdicts]}

    if len(blocked) >= need:
        out.score = round(min(median, 0.5), 3)
        out.semantic = {"blocked": f"{len(blocked)}/{n} semantic calls blocked",
                        "blocked_reasons": [str((v.get("semantic") or {}).get("blocked")) for v in blocked]}
        out.issues = [f"quorum: semantic blocked in {len(blocked)}/{n} calls"]
        d = out.dict()
        d["quorum"] = quorum
        return d

    out.ok = True
    out.score = round(median, 3)
    out.hard_fail = quorum["hard_fail_votes"] >= need
    live_need = len(live) // 2 + 1
    counts: dict = {}
    for v in live:
        for i in dict.fromkeys(v.get("issues") or []):
            counts[i] = counts.get(i, 0) + 1
    out.issues = [i for i, c in counts.items() if c >= live_need]
    if blocked:
        out.issues.append(f"quorum: {len(blocked)}/{n} semantic calls blocked")
    out.passed = (not out.hard_fail) and quorum["pass_votes"] >= need
    rep = min(live, key=lambda v: abs(float(v.get("score", 0.0)) - median))
    out.semantic = dict(rep.get("semantic") or {})
    d = out.dict()
    d["quorum"] = quorum
    return d


def judge_character_quorum(image: str | Path, reference: str | Path | None = None, n: int = 3,
                           require_semantic: bool = True, subject_only: bool = False,
                           models: tuple = QUORUM_MODELS) -> dict:
    """N independent judge_character calls fused by _aggregate_quorum (fail-closed, H1B2).
    Each vote goes to a DIFFERENT vision model (QUORUM_MODELS) so the panel is genuinely
    independent — three samples of one model share its backend's run-level mood. A vote that
    comes back BLOCKED (provider failure, not judgement) is re-asked once; persistent blocks
    stay blocked and count against passing."""
    verdicts, retried = [], 0
    for i in range(max(1, int(n))):
        m = models[i % len(models)] if models else None
        v = judge_character(image, reference=reference, require_semantic=require_semantic,
                            subject_only=subject_only, model=m)
        if "blocked" in (v.get("semantic") or {}):
            retried += 1
            v = judge_character(image, reference=reference, require_semantic=require_semantic,
                                subject_only=subject_only, model=m)
        verdicts.append(v)
    agg = _aggregate_quorum(verdicts)
    if isinstance(agg.get("quorum"), dict):
        agg["quorum"]["retried_votes"] = retried
    return agg


# --------------------------------------------------------------------------- target identity confidence
_MATCH_SCORE = {"yes": 1.0, "partial": 0.6, "no": 0.1, "n/a": None}


def target_confidence(capture: str | Path, reference: str | Path | None,
                      require_semantic: bool = True) -> dict:
    """How confident are we the rendered CAPTURE is the SAME asset as the declared REFERENCE — fusing
    perception's pixel-truth structural match with GLM's semantic matches_reference, weakest-link.

    target_confidence = MIN(pixel structural target_similarity, semantic match score).

    FAIL-CLOSED: no reference => blocked (None). require_semantic AND the LLM/match is unavailable =>
    blocked (None) — identity is never certified on pixels alone when semantic confirmation was required,
    and never on a self-reported number when the reference is absent.
    """
    issues: list = []
    if not reference:
        return {"ok": False, "blocked": True, "target_confidence": None,
                "reason": "no reference declared — identity cannot be certified", "pixel": {}, "semantic_match": "n/a"}

    pix = perception.compare_to_target(capture, reference)
    if pix.get("blocked") or pix.get("target_similarity") is None:
        return {"ok": False, "blocked": True, "target_confidence": None,
                "reason": pix.get("reason", "pixel structural match unavailable"),
                "pixel": pix, "semantic_match": "n/a"}
    pixel_ts = float(pix["target_similarity"])

    sem = _semantic(CHAR_RUBRIC, [capture, reference])
    if "blocked" in sem:
        if require_semantic:
            return {"ok": False, "blocked": True, "target_confidence": None,
                    "reason": f"semantic identity BLOCKED: {sem['blocked']}",
                    "pixel": pix, "semantic_match": "blocked"}
        return {"ok": True, "blocked": False, "target_confidence": round(pixel_ts, 4),
                "pixel": pix, "semantic_match": "skipped", "issues": [f"semantic blocked: {sem['blocked']}"]}

    match = sem.get("matches_reference", "n/a")
    sem_score = _MATCH_SCORE.get(match)
    if sem_score is None:
        # GLM gave a non-answer for a comparison it was explicitly asked to make => cannot certify identity
        if require_semantic:
            return {"ok": False, "blocked": True, "target_confidence": None,
                    "reason": f"semantic matches_reference={match} (non-answer)",
                    "pixel": pix, "semantic_match": match}
        sem_score = pixel_ts   # non-binding when semantic not required

    tc = round(min(pixel_ts, float(sem_score)), 4)
    if match == "no":
        issues.append("semantic:matches_reference=no")
    return {"ok": True, "blocked": False, "target_confidence": tc,
            "pixel": pix, "semantic_match": match, "semantic_match_score": sem_score,
            "binding": "pixel" if pixel_ts <= sem_score else "semantic", "issues": issues}


def judge_image(image: str | Path, rubric: str, images_extra: list | None = None,
                require_semantic: bool = True) -> dict:
    """Generic elite optics: judge any render/screen against a free-form rubric (returns JSON in the rubric)."""
    v = VisualVerdict(evidence=[str(image)])
    v.pixel = _pixel(image)
    v.semantic = _semantic(rubric, [image] + (images_extra or []))
    sem = v.semantic
    if "blocked" in sem:
        v.ok = v.pixel.get("metrics", {}).get("ok", False)
        v.passed = False if require_semantic else v.ok
        v.issues.append(f"semantic BLOCKED: {sem['blocked']}")
        return v.dict()
    v.ok = True
    v.score = round(float(sem.get("score", 0.0)), 3) if isinstance(sem.get("score"), (int, float)) else 0.0
    v.passed = bool(sem.get("pass", sem.get("passed", v.score >= 0.6)))
    if not v.passed:
        v.issues += [str(x) for x in (sem.get("defects") or sem.get("issues") or [])][:8]
    return v.dict()


def judge_motion(frames: list, question: str = "", require_semantic: bool = True, sample: int = 4) -> dict:
    """Animation/feel optics from a frame burst (desktop_eyes.capture_stream / record_window frames).
    Pixel: inter-frame motion (is it actually animating?). Semantic: GLM-5V on a sampled contact sheet."""
    v = VisualVerdict()
    frames = [f for f in frames if f and Path(f).exists()]
    if len(frames) < 2:
        v.issues.append("need >=2 frames")
        return v.dict()
    # pixel motion: max inter-consecutive-frame delta (proves it moves; 0 == frozen)
    deltas = [perception.image_delta(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    deltas = [d for d in deltas if d >= 0]
    v.pixel = {"frame_count": len(frames), "max_delta": max(deltas) if deltas else 0.0,
               "mean_delta": round(sum(deltas) / len(deltas), 5) if deltas else 0.0}
    v.evidence = frames
    # sample evenly for the vision pass
    step = max(1, len(frames) // sample)
    sampled = frames[::step][:sample]
    moving = v.pixel["max_delta"] >= 0.015
    if not require_semantic:
        # pixel-only motion verdict (no LLM call)
        v.ok = True
        v.semantic = {"skipped": "require_semantic=False"}
        v.passed = moving
        if not moving:
            v.issues.append(f"pixel: frozen (max_delta {v.pixel['max_delta']})")
        return v.dict()
    rubric = (question or "These are sequential frames of a game character in motion. ") + \
        " Return JSON: {\"is_animating\": bool, \"motion_natural\": bool, \"disfigured_during_motion\": bool, " \
        "\"defects\": [str], \"severity\": \"none|minor|major|critical\", \"score\": 0.0-1.0, \"summary\": str}"
    v.semantic = _semantic(rubric, sampled)
    sem = v.semantic
    if "blocked" in sem:
        v.ok = True
        v.passed = (not require_semantic) and moving
        if not moving:
            v.issues.append(f"pixel: frozen (max_delta {v.pixel['max_delta']})")
        v.issues.append(f"semantic BLOCKED: {sem['blocked']}")
        return v.dict()
    v.ok = True
    if sem.get("disfigured_during_motion") is True or sem.get("severity") == "critical":
        v.hard_fail = True
        v.issues.append("semantic:disfigured_during_motion")
    v.score = round(float(sem.get("score", 0.0)), 3)
    v.passed = (not v.hard_fail) and moving and bool(sem.get("is_animating")) and bool(sem.get("motion_natural"))
    if not moving:
        v.issues.append(f"pixel: frozen (max_delta {v.pixel['max_delta']})")
    return v.dict()


def health() -> dict:
    return {"llm": llm.health(), "perception": True}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(judge_character(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), indent=2))
    else:
        print(json.dumps(health(), indent=2))
