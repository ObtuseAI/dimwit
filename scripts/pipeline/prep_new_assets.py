"""Crop + cutout the new mech (multi-view) and grenade (single-view) concept sheets, build verify contact sheets.
No credits spent — just prep. Uses isnet+brighten rembg + keep-largest cv2 blob (robust isolation)."""
import sys
from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw
import numpy as np, cv2
from rembg import remove, new_session
RAIN = Path(__file__).resolve().parents[2]
NEW = RAIN/"source_art/new"; CUT = NEW/"cut"; CUT.mkdir(parents=True, exist_ok=True)
sess = new_session("isnet-general-use")

def cutout(crop_img, dst, bright=1.35, contrast=1.25):
    im = ImageEnhance.Contrast(ImageEnhance.Brightness(crop_img.convert("RGB")).enhance(bright)).enhance(contrast)
    c = remove(im.convert("RGBA"), session=sess); arr = np.array(c); a = arr[..., 3]
    mask = (a > 40).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1: return False
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    arr[..., 3] = np.where(lab == big, a, 0)
    ys, xs = np.where(arr[..., 3] > 40)
    if len(xs) == 0: return False
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cc = Image.fromarray(arr).crop((x0, y0, x1+1, y1+1))
    w, h = cc.size; side = int(max(w, h)/0.86); sq = Image.new("RGBA", (side, side), (0,0,0,0))
    sq.alpha_composite(cc, ((side-w)//2, (side-h)//2)); sq.save(dst); return True

def crops(sheet, boxes, prefix):
    im = Image.open(sheet).convert("RGB"); W, H = im.size; out = []
    for name, x0, y0, x1, y1 in boxes:
        c = im.crop((int(x0*W), int(y0*H), int(x1*W), int(y1*H)))
        dst = CUT/f"{prefix}{name}.png"
        ok = cutout(c, dst); out.append((name, dst if ok else None))
    return out

# MECH B (01-04): cols front/side/back ; rows Glaciera/Voidrunner/Aurelion/Luxorion
mb_rows = {"01_glaciera":(0.05,0.30),"02_voidrunner":(0.305,0.55),"03_aurelion":(0.55,0.79),"04_luxorion":(0.79,0.985)}
mb_cols = {"front":(0.125,0.305),"side":(0.305,0.45),"back":(0.625,0.795)}
boxesB = [(f"{r}__{c}", cx0, ry0, cx1, ry1) for r,(ry0,ry1) in mb_rows.items() for c,(cx0,cx1) in mb_cols.items()]
# MECH A (05-08): cols front/side ; rows Pyroclast/Jadewind/Ironline/Nightwire
ma_rows = {"05_pyroclast":(0.03,0.27),"06_jadewind":(0.275,0.51),"07_ironline":(0.515,0.745),"08_nightwire":(0.75,0.975)}
ma_cols = {"front":(0.14,0.335),"side":(0.335,0.505)}
boxesA = [(f"{r}__{c}", cx0, ry0, cx1, ry1) for r,(ry0,ry1) in ma_rows.items() for c,(cx0,cx1) in ma_cols.items()]
# GRENADE sticky (5 rows), hero middle
gs_rows = {"01_anchor_stick":(0.10,0.255),"02_volt_latch":(0.255,0.41),"03_wane_spike":(0.415,0.595),
           "04_null_pin":(0.60,0.785),"05_hive_stick":(0.79,0.965)}
boxesGS = [(n, 0.135, y0, 0.475, y1) for n,(y0,y1) in gs_rows.items()]
# GRENADE frag: 3 top + 2 bottom heroes
boxesGF = [("01_shardburst",0.015,0.10,0.215,0.50),("02_pulse_bloom",0.345,0.10,0.545,0.50),("03_grav_crack",0.665,0.10,0.865,0.52),
           ("04_scatterline",0.02,0.52,0.255,0.95),("05_glassfire",0.495,0.52,0.79,0.96)]

R = {}
R["mechB"] = crops(NEW/"mech_sheet_B.png", boxesB, "mechB_")
R["mechA"] = crops(NEW/"mech_sheet_A.png", boxesA, "mechA_")
R["sticky"] = crops(NEW/"grenade_sheet_1.png", boxesGS, "stky_")
R["frag"] = crops(NEW/"grenade_sheet_2.png", boxesGF, "frag_")

def contact(items, out, cols, title):
    cw,ch,lh=200,200,16; rows=(len(items)+cols-1)//cols
    cv=Image.new("RGB",(cols*(cw+6)+6,rows*(ch+lh+6)+30),(200,200,205)); d=ImageDraw.Draw(cv)
    d.text((8,8),title,fill=(0,0,0))
    for i,(nm,dst) in enumerate(items):
        x=6+(i%cols)*(cw+6); y=26+(i//cols)*(ch+lh+6)
        if dst:
            im=Image.open(dst).convert("RGBA");bg=Image.new("RGBA",im.size,(200,200,205,255));bg.alpha_composite(im)
            t=bg.convert("RGB");t.thumbnail((cw,ch));cv.paste(t,(x,y+lh))
        d.text((x+2,y+2),nm[:22],fill=(10,10,10))
    cv.save(out); print("wrote",out)
contact(R["mechB"], "artifacts/NEW_mechB.png", 3, "MECH 01-04 (front/side/back)")
contact(R["mechA"], "artifacts/NEW_mechA.png", 2, "MECH 05-08 (front/side)")
contact(R["sticky"]+R["frag"], "artifacts/NEW_grenades.png", 5, "GRENADES (10)")
print("DONE prep")
