"""Dimwit OPTICS JUDGE CALIBRATION — the golden set that gates the judge itself (masterplan H1B2).

The vision judge is a validator, so it gets validated. A small in-repo golden set of captures with
KNOWN verdicts (reference-grade paneled renders that must PASS; washed low-mip / emissive-flattened
renders that must FAIL) is re-judged through the PRODUCTION quorum lane. Any misclassified golden
means the judge (prompt, model, thresholds) has drifted and every optics verdict is suspect — the
`optics_judge_calibrated` blocker then fails until the judge is fixed and recalibrated.

Fail-closed in BOTH directions: a judge too lax to FAIL the bad goldens is rejected exactly like
one too strict to PASS the good ones — this is the non-weakening detector for prompt changes.
Fix the judge, never the goldens.

  python -m dimwit.optics_calibration            # run the goldens, write the artifact
  python -m dimwit.optics_calibration --check    # re-verify the last artifact (no LLM calls)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).resolve().parent / "goldens" / "optics"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
OUT_DIR = ROOT / "artifacts" / "optics_calibration"
RESULT_PATH = OUT_DIR / "calibration_result.json"
MAX_AGE_S = 7 * 24 * 3600


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def manifest_hash() -> str:
    """Hash of the manifest AND the golden image bytes — swapping an image invalidates calibration."""
    h = hashlib.sha256(MANIFEST_PATH.read_bytes())
    for g in load_manifest().get("goldens", []):
        for key in ("file", "reference"):
            rel = g.get(key)
            if rel:
                fp = GOLDEN_DIR / rel
                h.update(rel.encode())
                h.update(fp.read_bytes() if fp.exists() else b"MISSING")
    return h.hexdigest()


def check_calibration(results: dict, manifest: dict) -> dict:
    """Pure checker: manifest expectations vs actual verdicts ({name: {"passed": bool}}).
    Empty golden set or any golden without a result fails closed."""
    goldens = manifest.get("goldens", [])
    misclassified, missing = [], []
    for g in goldens:
        name, expect = g["name"], g["expect"]
        r = results.get(name)
        if r is None or "passed" not in r:
            missing.append(name)
            continue
        if bool(r["passed"]) != (expect == "pass"):
            misclassified.append(name)
    ok = bool(goldens) and not misclassified and not missing
    return {"ok": ok, "total": len(goldens), "correct": len(goldens) - len(misclassified) - len(missing),
            "misclassified": misclassified, "missing": missing}


def _llm_ready() -> bool:
    from dimwit import llm
    return llm.is_configured()


def run_calibration(n: int = 3, stability: int = 2) -> dict:
    """Judge every golden through the production quorum lane and write the calibration artifact.

    STABILITY PROTOCOL: the whole set is judged `stability` independent times and every golden
    must classify correctly in EVERY round — one lucky run proves nothing (2026-07-02: identical
    back-to-back runs flipped between 4/4 and 2/4 on provider mood). A golden whose verdict
    varies across rounds is recorded in `flipped`, the judge-drift signature.
    Requires a configured LLM — calibration is real judge calls, never fabricated verdicts."""
    from dimwit import optics
    if not _llm_ready():
        raise SystemExit("LLM not configured (no OPENROUTER_API_KEY) — calibration requires real judge calls")
    manifest = load_manifest()
    goldens = manifest.get("goldens", [])
    stability = max(1, int(stability))
    records = {g["name"]: {"expect": g["expect"], "rounds": []} for g in goldens}
    rounds = []
    for _ in range(stability):
        results = {}
        for g in goldens:
            img = GOLDEN_DIR / g["file"]
            ref = (GOLDEN_DIR / g["reference"]) if g.get("reference") else None
            if not img.exists():
                records[g["name"]]["error"] = f"golden image missing: {img}"
                continue
            v = optics.judge_character_quorum(img, reference=ref, n=n,
                                              subject_only=bool(g.get("subject_only")))
            results[g["name"]] = {"passed": bool(v.get("passed"))}
            records[g["name"]]["rounds"].append(
                {"passed": bool(v.get("passed")), "score": v.get("score"),
                 "hard_fail": bool(v.get("hard_fail")), "issues": (v.get("issues") or [])[:6],
                 "quorum": v.get("quorum", {})})
        rounds.append(check_calibration(results, manifest))
    misclassified = sorted({m for r in rounds for m in r["misclassified"]})
    missing = sorted({m for r in rounds for m in r["missing"]})
    flipped = sorted(name for name, rec in records.items()
                     if len({rd["passed"] for rd in rec["rounds"]}) > 1)
    ok = bool(rounds) and all(r["ok"] for r in rounds)
    payload = {"ts": time.time(), "quorum_n": int(n), "stability_runs": stability,
               "manifest_hash": manifest_hash(), "ok": ok,
               "total": len(goldens), "correct": len(goldens) - len(misclassified) - len(missing),
               "misclassified": misclassified, "missing": missing, "flipped": flipped,
               "rounds": [{"ok": r["ok"], "misclassified": r["misclassified"]} for r in rounds],
               "goldens": records}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def check_artifact() -> dict:
    """Re-verify the last written artifact without LLM calls (freshness + manifest binding + verdicts)."""
    if not RESULT_PATH.exists():
        return {"ok": False, "reason": "no calibration artifact — run: python -m dimwit.optics_calibration"}
    try:
        r = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "reason": f"unreadable artifact: {e!r}"}
    age = time.time() - float(r.get("ts", 0))
    if age > MAX_AGE_S:
        return {"ok": False, "reason": f"stale: {age / 3600:.1f}h old (max {MAX_AGE_S // 3600}h)"}
    if r.get("manifest_hash") != manifest_hash():
        return {"ok": False, "reason": "golden manifest/images changed since calibration"}
    if int(r.get("stability_runs", 1)) < 2:
        return {"ok": False, "reason": f"only {r.get('stability_runs', 1)} stability round(s) — a single run proves nothing"}
    if not r.get("ok") or r.get("misclassified") or r.get("missing"):
        return {"ok": False, "reason": f"judge drift: misclassified={r.get('misclassified')} missing={r.get('missing')}"}
    return {"ok": True, "total": r.get("total"), "age_h": round(age / 3600, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run/verify the optics judge golden calibration")
    ap.add_argument("--n", type=int, default=3, help="quorum size per golden (default 3)")
    ap.add_argument("--stability", type=int, default=2,
                    help="independent full-set rounds that must ALL classify correctly (default 2)")
    ap.add_argument("--check", action="store_true", help="verify the existing artifact only (no LLM calls)")
    a = ap.parse_args()
    if a.check:
        r = check_artifact()
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    r = run_calibration(n=a.n, stability=a.stability)
    print(json.dumps({k: v for k, v in r.items() if k != "goldens"}, indent=2))
    for name, rec in r["goldens"].items():
        verdicts = " ".join(f"r{i}:{'PASS' if rd['passed'] else 'FAIL'}@{rd.get('score')}"
                            for i, rd in enumerate(rec.get("rounds", [])))
        print(f"  {name}: expect={rec.get('expect')}  {verdicts}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
