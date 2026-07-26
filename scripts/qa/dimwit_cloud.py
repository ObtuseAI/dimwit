"""Dimwit CLOUD runner — drives the OpenRouter brain over the generated characters.

  python scripts/qa/dimwit_cloud.py health     # verify the OpenRouter key + connectivity
  python scripts/qa/dimwit_cloud.py qa          # vision-QA all 8 chars vs concept art -> ledger + report
  python scripts/qa/dimwit_cloud.py plan        # self-direction: decide generate/redo/skip/accept from QA state
  python scripts/qa/dimwit_cloud.py concept "<brief>" [n]   # invent N new WANEFALL characters
  python scripts/qa/dimwit_cloud.py auto        # qa -> plan -> (shell redos back into scripts/pipeline/batch_characters.py)

QA/plan are pure-cloud (no GPU). 'auto' redos call the local GPU batch for the flagged names only.
All verdicts are appended to Dimwit's own proof ledger; final acceptance stays a human gate.
"""
from __future__ import annotations
import sys, json, time, subprocess
from pathlib import Path

RAIN = Path(__file__).resolve().parents[2]
ART = RAIN / "artifacts"
sys.path.insert(0, str(RAIN))
from dimwit import llm, cloud_brain
from dimwit.character_roster_ids import CHARACTER_IDS, require_character_id
from dimwit.engine import DimwitLedger, assert_dimwit_path

NAMES = list(CHARACTER_IDS)
DESCS = {
    "01_vorlax":"blue armor, cyan energy seams", "02_ekris":"silver/white plated armor",
    "03_zythan":"purple armor, magenta seams", "04_qorin":"green/mossy organic armor",
    "05_therak":"orange/red molten armor", "06_ullio":"teal/cyan armor",
    "07_kelous":"black + gold trimmed armor", "08_nexor":"pink/white sleek armor",
}
LEDGER = DimwitLedger(RAIN / "ledger" / "cloud_brain_ledger.jsonl")
QA_REPORT = ART / "cloud_qa_report.json"


def _renders(name):
    return [
        str(ART / f"{name}_textured" / "mview_front.png"),
        str(ART / f"{name}_textured" / "mview_threequarter.png"),
        str(ART / f"{name}_clay" / "mview_front.png"),
    ]


def cmd_health():
    h = llm.health()
    print(json.dumps(h, indent=2))
    if not h.get("ok"):
        print("\n>> Add your key: set OPENROUTER_API_KEY env var, OR copy config/secrets.example.json"
              " -> config/secrets.json and paste your key. Then re-run.")
    return h


def cmd_qa():
    if not llm.is_configured():
        print("NO_API_KEY — run `python scripts/qa/dimwit_cloud.py health` for setup steps."); return
    results = []
    for n in NAMES:
        concept = str(ART / "fronts" / f"{n}.png")
        t0 = time.time()
        v = cloud_brain.review_character(n, concept, _renders(n), DESCS.get(n, ""))
        v["seconds"] = round(time.time() - t0, 1)
        results.append(v)
        LEDGER.append({"asset_id": n, "state": "CLOUD_QA", "candidate_hash": "render-v1",
                       "kind": "vision_qa", "verdict": v})
        print(f"  {n}: overall={v.get('overall')} glow={v.get('glow_present')} "
              f"redo={v.get('redo')} ({v.get('seconds')}s) {('ERR '+v.get('error','')) if not v.get('ok') else ''}")
    QA_REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    avg = sum(r.get("overall", 0) for r in results) / max(1, len(results))
    print(f"\nQA report -> {QA_REPORT}   mean overall={avg:.1f}   "
          f"redos={[r['character'] for r in results if r.get('redo')]}")
    return results


def _qa_state():
    if QA_REPORT.exists():
        rs = json.loads(QA_REPORT.read_text(encoding="utf-8"))
        by = {r["character"]: r for r in rs}
    else:
        by = {}
    state = []
    for n in NAMES:
        r = by.get(n, {})
        state.append({"name": n, "exists": (ART / f"{n}_textured" / "mview_front.png").exists(),
                      "qa_overall": r.get("overall"), "qa_redo": r.get("redo", False),
                      "glow": r.get("glow_present", False)})
    return state


def cmd_plan():
    if not llm.is_configured():
        print("NO_API_KEY — run health first."); return
    plan = cloud_brain.plan_queue(_qa_state())
    print(json.dumps(plan, indent=2))
    LEDGER.append({"asset_id": "ROSTER", "state": "CLOUD_PLAN", "candidate_hash": "plan-v1",
                   "kind": "self_direction", "plan": plan})
    return plan


def cmd_concept(brief, n=3):
    if not llm.is_configured():
        print("NO_API_KEY — run health first."); return
    out = cloud_brain.concept_prompts(brief, int(n))
    print(json.dumps(out, indent=2))
    (ART / "concept_prompts.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    LEDGER.append({"asset_id": "NEW_CONCEPTS", "state": "CLOUD_CONCEPT", "candidate_hash": "concept-v1",
                   "kind": "concept_prompts", "brief": brief, "out": out})
    return out


def _validated_redos(plan: dict) -> list[str]:
    """Fail closed before a provider-selected value becomes a local argv item."""
    queue = plan.get("queue")
    if not isinstance(queue, list):
        raise ValueError("provider plan queue must be a list")
    redos = []
    for item in queue:
        if not isinstance(item, dict):
            raise ValueError("provider plan queue items must be objects")
        if item.get("action") == "redo":
            redos.append(require_character_id(item.get("name")))
    return redos


def cmd_auto():
    if not llm.is_configured():
        print("NO_API_KEY — run health first."); return
    qa = cmd_qa()
    plan = cmd_plan()
    if not isinstance(plan, dict) or not plan.get("ok"):
        raise RuntimeError("provider plan unavailable; refusing local batch mutation")
    redos = _validated_redos(plan)
    if not redos:
        print("\nAUTO: no redos required — roster is at target, ready for human review.")
        return
    print(f"\nAUTO: re-generating {redos} on the local GPU ...")
    subprocess.run([sys.executable, str(RAIN / "scripts/pipeline/batch_characters.py"), *redos], cwd=str(RAIN))
    print("AUTO: redos done — re-run `qa` to re-judge.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":   cmd_health()
    elif cmd == "qa":     cmd_qa()
    elif cmd == "plan":   cmd_plan()
    elif cmd == "concept": cmd_concept(sys.argv[2] if len(sys.argv) > 2 else "new elite WANEFALL soldier",
                                       sys.argv[3] if len(sys.argv) > 3 else 3)
    elif cmd == "auto":   cmd_auto()
    else: print(__doc__)
