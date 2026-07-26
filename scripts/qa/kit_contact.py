"""Wait for the 9 kit previews, build a labeled contact sheet + copy to the Desktop in-game-assets folder."""
import time, glob, os, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RAIN = Path(__file__).resolve().parents[2]
SRC = RAIN / "artifacts" / "kit_render"
DESK = Path(os.path.expanduser("~")) / "Desktop" / "in game assets" / "MapKit"
DESK.mkdir(parents=True, exist_ok=True)

for _ in range(180):
    if len(glob.glob(str(SRC / "*.png"))) >= 16:
        break
    time.sleep(5)
time.sleep(2)

files = sorted(glob.glob(str(SRC / "SM_Kit_*.png")))
for f in files:
    shutil.copyfile(f, DESK / os.path.basename(f))

cols, cell, pad, lab = 3, 380, 16, 30
rows = (len(files) + cols - 1) // cols
W = cols * cell + (cols + 1) * pad
H = rows * (cell + lab) + (rows + 1) * pad
sheet = Image.new("RGB", (W, H), (8, 11, 14))
d = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arialbd.ttf", 22)
except Exception:
    font = ImageFont.load_default()
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB"); im.thumbnail((cell, cell), Image.LANCZOS)
    r, c = divmod(i, cols)
    x = pad + c * (cell + pad) + (cell - im.width) // 2
    y = pad + r * (cell + lab + pad)
    sheet.paste(im, (x, y))
    name = os.path.basename(f).replace("SM_Kit_", "").replace(".png", "").upper()
    d.text((pad + c * (cell + pad) + 6, y + cell + 2), name, fill=(60, 220, 255), font=font)
out = DESK / "_ALL_MapKit_overview.png"
sheet.save(out)
print(f"KIT_CONTACT_DONE {len(files)} -> {out}")
