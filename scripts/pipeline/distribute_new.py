"""Wait for the 18 new dark-env renders, then place them in the Desktop verify folder
(mechs -> Characters/, grenades -> Weapons/), build per-group contact-sheet overviews,
and refresh the manifest. Stdlib + PIL. Run detached; prints DISTRIBUTE_DONE.
"""
import time, glob, os, json, shutil
from pathlib import Path
from PIL import Image

RAIN = Path(__file__).resolve().parents[2]
SRC = RAIN / "artifacts" / "ingame_new"
DESK = Path(os.path.expanduser("~")) / "Desktop" / "in game assets"
CHAR = DESK / "Characters"; WPN = DESK / "Weapons"
for d in (CHAR, WPN): d.mkdir(parents=True, exist_ok=True)

# wait for all 18 renders (poll; detached process, sleep is fine here)
for _ in range(120):
    if len(glob.glob(str(SRC / "*.png"))) >= 18: break
    time.sleep(5)

mechs = sorted(glob.glob(str(SRC / "SM_Char_Mech_*.png")))
grens = sorted(glob.glob(str(SRC / "SM_Wpn_Gren_*.png")))

def place(files, dst):
    out = []
    for f in files:
        d = dst / os.path.basename(f); shutil.copyfile(f, d); out.append(d)
    return out

mc = place(mechs, CHAR); gc = place(grens, WPN)

def contact(files, out_path, cols=4, cell=420, pad=14, label=True):
    if not files: return
    imgs = [Image.open(f).convert("RGB") for f in files]
    rows = (len(imgs) + cols - 1) // cols
    W = cols*cell + (cols+1)*pad; H = rows*cell + (rows+1)*pad
    sheet = Image.new("RGB", (W, H), (8, 11, 14))
    for i, im in enumerate(imgs):
        im.thumbnail((cell, cell), Image.LANCZOS)
        r, c = divmod(i, cols)
        x = pad + c*(cell+pad) + (cell-im.width)//2
        y = pad + r*(cell+pad) + (cell-im.height)//2
        sheet.paste(im, (x, y))
    sheet.save(out_path)

contact(mc, DESK / "_ALL_Mechs_overview.png")
contact(gc, DESK / "_ALL_Grenades_overview.png")

# refresh manifest (merge, don't clobber existing entries)
mf = DESK / "_manifest.json"
man = {}
if mf.exists():
    try: man = json.loads(mf.read_text())
    except Exception: man = {}
man.setdefault("groups", {})
man["groups"]["Mechs"] = {"count": len(mc), "ue_path": "/Game/Wanefall/Dimwit/Characters/",
                          "files": [p.name for p in mc]}
man["groups"]["Grenades"] = {"count": len(gc), "ue_path": "/Game/Wanefall/Dimwit/Weapons/",
                             "files": [p.name for p in gc]}
man["total_in_engine"] = 71
mf.write_text(json.dumps(man, indent=2))
print(f"DISTRIBUTE_DONE mechs={len(mc)} grenades={len(gc)} -> {DESK}")
