"""Batch the WANEFALL props (vehicles + melee + guns) through Hi3D.
rembg cutout each cropped item -> wave-submit (<=28 to respect the 30-queue cap) -> poll -> download GLB+cover.
Tiers: vehicles=v2.1-pro (45cr), weapons=v2.1-fast (25cr). Task ids persisted for crash-safe resume.
  python scripts/pipeline/props_batch.py            # all categories
  python scripts/pipeline/props_batch.py vehicles   # one category
"""
from __future__ import annotations
import sys, json, time, urllib.request
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
RAIN = Path(__file__).resolve().parents[2]
ART = RAIN / "artifacts"
PROPS = ART / "props"
CUT = ART / "props_cut"; CUT.mkdir(parents=True, exist_ok=True)
OUTD = ART / "props_out"; OUTD.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(RAIN))
from dimwit import hi3d
from dimwit.engine import DimwitLedger
LED = DimwitLedger(RAIN / "ledger" / "hi3d_props_ledger.jsonl")
TASKS = ART / "props_tasks.json"
WAVE = 28

TIER = {"vehicles": {"resolution": "1536pro"}, "melee": {"resolution": "1536fast"}, "guns": {"resolution": "1536fast"}}

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dl(url, out):
    out = Path(out); req = urllib.request.Request(url, headers={"User-Agent": "Dimwit/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f: f.write(r.read())
    return str(out)

def cutout(src: Path, dst_rgba: Path):
    """rembg isolate -> tight transparent crop on a square (drops label text + bg)."""
    from PIL import Image
    import numpy as np
    from rembg import remove, new_session
    im = Image.open(src).convert("RGBA")
    cut = remove(im, session=new_session("u2net"))
    a = np.array(cut)[..., 3]; ys, xs = np.where(a > 30)
    if len(xs) == 0: return False
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cut = cut.crop((x0, y0, x1 + 1, y1 + 1))
    w, h = cut.size; side = int(max(w, h) / 0.82)
    cv = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    cv.alpha_composite(cut, ((side - w) // 2, (side - h) // 2))
    cv.save(dst_rgba); return True

def main():
    cats = sys.argv[1:] or ["vehicles", "melee", "guns"]
    items = []  # (cat, name, cutout_path)
    log("=== cutouts ===")
    for cat in cats:
        for p in sorted((PROPS / cat).glob("*.png")):
            rgba = CUT / f"{cat}__{p.stem}.png"
            if not rgba.exists():
                ok = cutout(p, rgba)
                if not ok: log(f"  no-fg {cat}/{p.stem}, skip"); continue
            items.append((cat, p.stem, rgba))
    log(f"prepared {len(items)} cutouts. balance {hi3d.balance():.0f} cr")

    tasks = json.loads(TASKS.read_text()) if (TASKS.exists() and "--resume" in sys.argv) else {}
    done = {}
    # process in waves
    pending = [it for it in items if f"{it[0]}__{it[1]}" not in tasks]
    waves = [pending[i:i+WAVE] for i in range(0, len(pending), WAVE)] or [[]]
    for wi, wave in enumerate(waves):
        if wave:
            log(f"--- submitting wave {wi+1}/{len(waves)} ({len(wave)}) ---")
            for cat, name, rgba in wave:
                key = f"{cat}__{name}"
                try:
                    tid = hi3d.submit(str(rgba), **TIER.get(cat, {}))
                    tasks[key] = {"task_id": tid, "cat": cat, "name": name}
                    TASKS.write_text(json.dumps(tasks, indent=2))
                    log(f"  + {key}")
                except Exception as e:
                    log(f"  SUBMIT FAIL {key}: {e}")
        # poll everything not yet downloaded
        log(f"--- polling ({len([k for k in tasks if k not in done])} open) ---")
        t0 = time.time()
        while any(k not in done for k in tasks):
            for key, t in tasks.items():
                if key in done: continue
                try: d = hi3d.query(t["task_id"])
                except Exception as e: log(f"  q-err {key}: {e}"); continue
                st = d.get("state", "?")
                if st == "success":
                    glb = dl(d["url"], OUTD / f"{key}.glb")
                    cov = dl(d["cover_url"], OUTD / f"{key}_cover.png") if d.get("cover_url") else None
                    done[key] = {"glb": glb, "cover": cov}
                    LED.append({"asset_id": key, "state": "HI3D_PROP", "candidate_hash": t["task_id"], "glb": glb})
                    log(f"  [OK] {key}  [{len(done)}/{len(tasks)}]")
                elif st == "failed":
                    done[key] = {"failed": True}; log(f"  [X] {key} FAILED")
            if any(k not in done for k in tasks): time.sleep(10)
    log(f"=== DONE. {sum(1 for v in done.values() if not v.get('failed'))}/{len(tasks)} ok. balance {hi3d.balance():.0f} cr ===")
    (ART / "props_result.json").write_text(json.dumps(done, indent=2))

if __name__ == "__main__":
    main()
