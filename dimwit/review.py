"""Dimwit human-review packaging. After automation reaches PROMOTED_TO_REVIEW (or NEEDS_RECURSION),
Dimwit packages everything a human needs to ACCEPT / REJECT / REQUEST_TASTE_ADJUSTMENT / KEEP_AS_FALLBACK
/ ARCHIVE. Dimwit NEVER chooses these final decisions itself.

Encodes the human-screenshot-override law: a human live screenshot showing an asset/scene is visually
unacceptable OVERRIDES any automated PASS/PASS_WITH_NOTES.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .engine import assert_dimwit_path

HUMAN_DECISIONS = ["ACCEPT_FOR_ACTIVE_SLICE", "REJECT", "REQUEST_TASTE_ADJUSTMENT", "KEEP_AS_FALLBACK", "ARCHIVE"]


def _proposed_laws() -> list:
    """Recurring on-screen forbidden traits the learner proposes as hard identity laws — operator-gated."""
    try:
        from .learning.lesson_loop import propose_identity_laws
        return propose_identity_laws()
    except Exception:
        return []


def _intent_vs_actual(contract: dict | None, report: dict) -> dict:
    """The declared 'initial picture/goals/design' (the intent contract) put SIDE BY SIDE with what the final
    capture actually measured (the fused weakest-link result). This is the comparison the user asked for:
    'the initial picture/goals/design ... is what should be compared against the final capture.'"""
    fused = report.get("fused", {}) or {}
    if not contract:
        return {"applicable": False,
                "note": "no per-build intent contract was authored for this asset — fused gate ran against "
                        "the frozen asset_type floors only",
                "actual_fused_confidence": fused.get("confidence"),
                "actual_meets_gate": bool(fused.get("meets_gate")),
                "actual_binding_constraint": fused.get("binding_constraint")}
    goals = contract.get("goals", {}) or {}
    ea = contract.get("expected_appearance", {}) or {}
    acc = contract.get("acceptance", {}) or {}
    scores = (report.get("best_candidate", {}) or {}).get("scores", {}) or {}
    dim_rows = []
    for dim, floor in sorted((acc.get("dimension_floors", {}) or {}).items()):
        actual = scores.get(dim)
        dim_rows.append({"dimension": dim, "declared_floor": floor, "actual": actual,
                         "meets": actual is not None and actual >= floor})
    meets = bool(fused.get("meets_gate"))
    return {
        "applicable": True,
        "intent_id": contract.get("intent_id"),
        "intent_hash": contract.get("intent_hash"),
        "anchored_before_pixels": bool(contract.get("anchored")),
        "declared_summary": goals.get("summary"),
        "declared_reference_images": ea.get("reference_images", []),
        "declared_must_have_traits": ea.get("must_have_traits", []),
        "declared_forbidden_traits": ea.get("forbidden_traits", []),
        "declared_confidence_target": acc.get("confidence_target"),
        "declared_target_match_floor": acc.get("target_match_floor"),
        "actual_fused_confidence": fused.get("confidence"),
        "actual_meets_gate": meets,
        "actual_target_similarity": fused.get("target_similarity"),
        "actual_binding_constraint": fused.get("binding_constraint"),
        "actual_blocked_reasons": fused.get("blocked_reasons", []),
        "per_dimension": dim_rows,
        "verdict": ("CAPTURE MEETS THE DECLARED INTENT" if meets else
                    f"CAPTURE DOES NOT MEET THE DECLARED INTENT — binding constraint: {fused.get('binding_constraint')}"),
    }


def build_review_package(root: Path, task: dict, report: dict, copy_evidence: bool = True,
                         contract: dict | None = None) -> dict:
    """Write Dimwit/review_packages/<asset_id>/ with spec, provenance, contact-sheet refs, proofs,
    promotion verdict, known weaknesses, and the accept/reject/taste checklist. Returns the manifest.

    When a per-build intent `contract` is supplied, an intent-vs-actual diff (declared picture/goals vs the
    final fused capture result) is written so the human gate sees exactly where the build met or missed its
    own declared target."""
    root = Path(root)
    assert_dimwit_path(root)
    pkg = root / "review_packages" / task["asset_id"]
    pkg.mkdir(parents=True, exist_ok=True)

    best = report.get("best_candidate", {})
    evidence = best.get("evidence", {})
    diff = _intent_vs_actual(contract, report)

    # copy any real contact sheets into the package (so it is self-contained), else just reference paths
    copied = {}
    if copy_evidence:
        for key in ("hero_contact_sheet", "player_camera_contact_sheet"):
            src = evidence.get(key)
            if src and Path(src).exists():
                dst = pkg / (key + Path(src).suffix)
                try:
                    shutil.copyfile(src, dst)
                    copied[key] = str(dst)
                except OSError:
                    copied[key] = f"REFERENCED (copy failed): {src}"
            elif src:
                copied[key] = f"REFERENCED (not on disk): {src}"

    weaknesses = []
    for g in report.get("gates", []):
        if g.get("verdict") == "FAIL":
            weaknesses.append(f"GATE FAIL [{g['gate']}]: {g.get('detail','')}")
    if report.get("weakest_dimension"):
        weaknesses.append(f"weakest scored dimension: {report['weakest_dimension']}")
    if diff.get("applicable") and not diff.get("actual_meets_gate"):
        weaknesses.append(f"INTENT MISS: {diff.get('verdict')}")

    fused = report.get("fused", {}) or {}
    manifest = {
        "asset_id": task["asset_id"],
        "asset_type": task["asset_type"],
        "final_state": report.get("final_state"),
        "overall_score": report.get("overall"),
        "fused_confidence": fused.get("confidence"),         # the AUTHORITATIVE weakest-link gate (not the mean)
        "fused_meets_gate": bool(fused.get("meets_gate")),
        "fused_gate": fused.get("gate"),
        "intent_vs_actual": diff,
        "review_only": True,
        "asset_spec": best.get("spec", {}),
        "provenance": evidence.get("provenance", {}),
        "hero_contact_sheet": copied.get("hero_contact_sheet") or evidence.get("hero_contact_sheet"),
        "player_camera_contact_sheet": copied.get("player_camera_contact_sheet") or evidence.get("player_camera_contact_sheet"),
        "promotion_verdict": next((g for g in report.get("gates", []) if g.get("gate") == "promotion"), {}),
        "known_weaknesses": weaknesses,
        "human_decision_options": HUMAN_DECISIONS,
        "human_decision": None,
        "human_screenshot_override": "A human live screenshot showing this asset/scene is visually unacceptable OVERRIDES any automated PASS/PASS_WITH_NOTES.",
        "proposed_identity_laws": _proposed_laws(),
        "checklist": [
            {"item": "Silhouette reads as the intended WANEFALL asset", "ok": None},
            {"item": "Palette is WANEFALL-native (dark + teal Wane + red/orange weak point, no magenta)", "ok": None},
            {"item": "Readable in third-person gameplay camera (not just hero capture)", "ok": None},
            {"item": "No white/debug junk, no black blob, no AI-slop ornament clutter", "ok": None},
            {"item": "Scale / collision / material sane", "ok": None},
            {"item": "Hit + destroyed states read (if applicable)", "ok": None},
            {"item": "Provenance/license is acceptable for intended use", "ok": None},
        ],
    }
    (pkg / "review_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (pkg / "asset_spec.json").write_text(json.dumps(best.get("spec", {}), indent=2), encoding="utf-8")
    (pkg / "provenance.json").write_text(json.dumps(evidence.get("provenance", {}), indent=2), encoding="utf-8")
    (pkg / "validation_summary.json").write_text(json.dumps(report.get("gates", []), indent=2), encoding="utf-8")
    (pkg / "intent_vs_actual.json").write_text(json.dumps(diff, indent=2), encoding="utf-8")
    return {"package_dir": str(pkg), "manifest": str(pkg / "review_manifest.json"), "files": [p.name for p in pkg.iterdir()]}
