"""Submit the 8 new mechs (multi-view) + 10 grenades (single-view) to Hi3D. Persist task ids, poll, download."""
from __future__ import annotations
import sys, json, time, urllib.request
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIN = Path(__file__).resolve().parents[2]
CUT = RAIN/"source_art/new/cut2"; OUT = RAIN/"artifacts/new_out"; OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(RAIN))
from dimwit import hi3d
from dimwit.engine import DimwitLedger
LED = DimwitLedger(RAIN/"ledger"/"hi3d_new_ledger.jsonl")
TASKS = RAIN/"artifacts/new_tasks.json"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
def dl(url, out):
    req=urllib.request.Request(url, headers={"User-Agent":"Dimwit/1.0"})
    with urllib.request.urlopen(req,timeout=180) as r, open(out,"wb") as f: f.write(r.read())
    return str(out)

# mechs: (key, [view cutouts in front,back,left order], bit)
MB = ["01_glaciera","02_voidrunner","03_aurelion","04_luxorion"]
MA = ["05_pyroclast","06_jadewind","07_ironline","08_nightwire"]
mechs = []
for n in MB:
    mechs.append((f"mech_{n}", [str(CUT/f"mechB_front_{n}.png"), str(CUT/f"mechB_back_{n}.png"), str(CUT/f"mechB_side_{n}.png")], "1110"))
for n in MA:
    mechs.append((f"mech_{n}", [str(CUT/f"mechA_front_{n}.png"), str(CUT/f"mechA_side_{n}.png")], "1010"))
grenades = [f"gren_{n}" for n in
    ["01_anchor_stick","02_volt_latch","03_wane_spike","04_null_pin","05_hive_stick",
     "06_shardburst","07_pulse_bloom","08_grav_crack","09_scatterline","10_glassfire"]]

def main():
    resume = "--resume" in sys.argv
    log(f"balance before: {hi3d.balance():.0f} cr")
    tasks = json.loads(TASKS.read_text()) if (resume and TASKS.exists()) else {}
    if not tasks:
        log("=== submitting 8 mechs (multi-view, pro) ===")
        for key, imgs, bit in mechs:
            try:
                tid = hi3d.submit_multiview(imgs, bit, resolution="1536pro")
                tasks[key] = tid; TASKS.write_text(json.dumps(tasks, indent=2)); log(f"  + {key} ({bit})")
            except Exception as e: log(f"  FAIL {key}: {e}")
        log("=== submitting 10 grenades (single, pro) ===")
        for key in grenades:
            try:
                tid = hi3d.submit(str(CUT/f"{key}.png"), resolution="1536pro")
                tasks[key] = tid; TASKS.write_text(json.dumps(tasks, indent=2)); log(f"  + {key}")
            except Exception as e: log(f"  FAIL {key}: {e}")
    log(f"--- polling {len(tasks)} ---")
    done, t0 = {}, time.time()
    while any(k not in done for k in tasks):
        for key, tid in tasks.items():
            if key in done: continue
            try: d = hi3d.query(tid)
            except Exception as e: log(f"  q-err {key}: {e}"); continue
            st = d.get("state","?")
            if st == "success":
                glb=dl(d["url"], OUT/f"{key}.glb"); cov=dl(d["cover_url"], OUT/f"{key}_cover.png") if d.get("cover_url") else None
                done[key]={"glb":glb,"cover":cov}; LED.append({"asset_id":key,"state":"HI3D_NEW","candidate_hash":tid,"glb":glb})
                log(f"  [OK] {key} ({int(time.time()-t0)}s) [{len(done)}/{len(tasks)}]")
            elif st == "failed":
                done[key]={"failed":True}; log(f"  [X] {key} FAILED")
        if any(k not in done for k in tasks): time.sleep(10)
    log(f"=== DONE. balance: {hi3d.balance():.0f} cr ===")
    (RAIN/"artifacts/new_result.json").write_text(json.dumps(done, indent=2))

if __name__ == "__main__": main()
