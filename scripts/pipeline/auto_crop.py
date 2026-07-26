"""Auto-detect items on a concept sheet via rembg + connected components, crop each item's EXACT bbox
(captures full extent incl. crests/wings/spikes — no chopping; separate blobs = no neighbor bleed).
Outputs: per-item cutouts + an overlay PNG (detected boxes drawn) for verification."""
import sys
from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw
import numpy as np, cv2
from rembg import remove, new_session
sess = new_session("isnet-general-use")

def detect(sheet, x_min=0.115, min_area=0.0035, min_h=0.10, close=11, bright=1.3):
    im = Image.open(sheet).convert("RGB"); W, H = im.size
    br = ImageEnhance.Contrast(ImageEnhance.Brightness(im).enhance(bright)).enhance(1.2)
    a = np.array(remove(br.convert("RGBA"), session=sess))[..., 3]
    mask = (a > 40).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))  # connect a mech's parts
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    blobs = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area*W*H or h < min_h*H or w < 0.02*W: continue
        if cent[i][0] < x_min*W: continue                     # skip label/icon column
        blobs.append([int(x), int(y), int(w), int(h), float(cent[i][0]), float(cent[i][1])])
    return im, W, H, mask, blobs

def cluster_rows(blobs, H, tol=0.10):
    blobs = sorted(blobs, key=lambda b: b[5])
    rows, cur = [], []
    for b in blobs:
        if cur and abs(b[5]-cur[-1][5]) > tol*H:
            rows.append(sorted(cur, key=lambda z: z[4])); cur = []
        cur.append(b)
    if cur: rows.append(sorted(cur, key=lambda z: z[4]))
    return rows

def overlay(im, blobs, out):
    o = im.copy(); d = ImageDraw.Draw(o)
    for (x, y, w, h, cx, cy) in blobs:
        d.rectangle([x, y, x+w, y+h], outline=(255, 40, 40), width=4)
    o.thumbnail((1000, 1000)); o.save(out)

if __name__ == "__main__":
    sheet = sys.argv[1]; out = sys.argv[2]
    im, W, H, mask, blobs = detect(sheet)
    rows = cluster_rows(blobs, H)
    overlay(im, blobs, out)
    print(f"{Path(sheet).name}: {len(blobs)} blobs in {len(rows)} rows -> {[len(r) for r in rows]}")
