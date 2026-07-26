"""Batch the WANEFALL roster through the Hi3D cloud geometry backend.
Submits all characters concurrently (Hi3D allows 30 queued), polls together, downloads each
GLB + Hi3D's own cover render as it finishes. Vorlax(01) already done -> default does 02..08.
  python scripts/pipeline/hi3d_batch.py            # the 7 remaining
  python scripts/pipeline/hi3d_batch.py 03_zythan  # specific ones
"""
from __future__ import annotations
import sys, json, time, urllib.request
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # avoid cp1252 crashes in bg logs
except Exception: pass

RAIN = Path(__file__).resolve().parents[2]
ART = RAIN / "artifacts"
sys.path.insert(0, str(RAIN))
from dimwit import hi3d
from dimwit.engine import DimwitLedger

ALL = ["01_vorlax","02_ekris","03_zythan","04_qorin","05_therak","06_ullio","07_kelous","08_nexor"]
LEDGER = DimwitLedger(RAIN / "ledger" / "hi3d_geometry_ledger.jsonl")
TASKS_FILE = ART / "hi3d_tasks.json"   # persisted {name: task_id} so a crash can resume w/o re-spending

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dl(url, out):
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Dimwit/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())
    return str(out)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    resume = "--resume" in sys.argv
    names = args or ["02_ekris","03_zythan","04_qorin","05_therak","06_ullio","07_kelous","08_nexor"]
    log(f"balance before: {hi3d.balance():.0f} cr")
    if resume and TASKS_FILE.exists():
        tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        log(f"=== RESUME: polling {len(tasks)} existing tasks (no re-submit, no new spend) ===")
    else:
        log(f"=== submitting {len(names)} tasks: {', '.join(names)} ===")
        tasks = {}
        for n in names:
            cut = RAIN / "source_art" / f"{n}_cutout_rgba.png"
            if not cut.exists():
                log(f"  SKIP {n}: no cutout {cut.name}"); continue
            try:
                tid = hi3d.submit(str(cut))
                tasks[n] = tid
                TASKS_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")  # persist immediately
                log(f"  submitted {n} -> {tid[:24]}...")
            except Exception as e:
                log(f"  SUBMIT FAIL {n}: {e}")
    log(f"--- polling {len(tasks)} tasks ---")
    done, t0 = {}, time.time()
    while len(done) < len(tasks):
        for n, tid in tasks.items():
            if n in done: continue
            try:
                d = hi3d.query(tid)
            except Exception as e:
                log(f"  query err {n}: {e}"); continue
            st = d.get("state", "?")
            if st == "success":
                glb = dl(d["url"], ART / f"hi3d_{n}.glb")
                cov = None
                if d.get("cover_url"):
                    try: cov = dl(d["cover_url"], ART / f"hi3d_{n}_cover.png")
                    except Exception: pass
                done[n] = {"glb": glb, "cover": cov, "task_id": tid}
                LEDGER.append({"asset_id": n, "state": "HI3D_GEOMETRY", "candidate_hash": tid,
                               "kind": "hi3d_v2.1pro", "glb": glb})
                log(f"  [OK] {n} done ({int(time.time()-t0)}s)  [{len(done)}/{len(tasks)}]")
            elif st == "failed":
                done[n] = {"failed": True}
                log(f"  [X] {n} FAILED")
        if len(done) < len(tasks):
            time.sleep(10)
    log(f"=== DONE in {int(time.time()-t0)}s. balance after: {hi3d.balance():.0f} cr ===")
    (ART / "hi3d_batch_result.json").write_text(json.dumps(done, indent=2), encoding="utf-8")
    for n in ALL:
        ok = (ART / f"hi3d_{n}.glb").exists()
        log(f"  {n}: {'GLB ✓' if ok else '—'}")

if __name__ == "__main__":
    main()
