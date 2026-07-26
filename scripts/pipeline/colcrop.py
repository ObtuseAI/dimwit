"""Column-strip auto-crop: for a vertical view-column (e.g. all FRONT views stacked), rembg the full-height
strip and bbox each item -> captures full crest-to-feet extent (no chopping), no neighbor bleed.
Used for the multi-view mech sheets + grenade hero column.  Outputs cutouts + an overlay for verification."""
from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw
import numpy as np, cv2
from rembg import remove, new_session
_sess = new_session("isnet-general-use")

def _items_in_strip(strip, min_h_frac=0.10, min_area_frac=0.02, close=9, bright=1.3):
    """Return bboxes (x,y,w,h) of distinct items stacked in a narrow vertical strip, top->bottom."""
    W, H = strip.size
    br = ImageEnhance.Contrast(ImageEnhance.Brightness(strip).enhance(bright)).enhance(1.2)
    a = np.array(remove(br.convert("RGBA"), session=_sess))[..., 3]
    mask = (a > 40).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if h < min_h_frac*H or area < min_area_frac*(W*H): continue
        out.append((int(x), int(y), int(w), int(h)))
    out.sort(key=lambda b: b[1])
    return out

def crop_column(sheet_img, x0f, x1f, names, dst_dir, prefix, pad=0.06):
    """Crop a view-column [x0f,x1f] of the sheet; detect items; save each as a padded square cutout.
    Returns list of (name, path|None). names = top->bottom item names for this column."""
    W, H = sheet_img.size
    sx0, sx1 = int(x0f*W), int(x1f*W)
    strip = sheet_img.crop((sx0, 0, sx1, H))
    boxes = _items_in_strip(strip)
    res = []
    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    # match detected boxes to expected count (if mismatch, fall back to even split)
    if len(boxes) != len(names):
        boxes = None
    for idx, name in enumerate(names):
        if boxes is not None:
            x, y, w, h = boxes[idx]
        else:  # fallback: even vertical split of the strip
            sh = H/len(names); y = int(idx*sh); h = int(sh); x = 0; w = sx1-sx0
        # pad the bbox (capture any faint antenna tips), clamp to strip
        px, py = int(w*pad), int(h*pad)
        cx0 = max(0, x-px); cy0 = max(0, y-py); cx1 = min(strip.size[0], x+w+px); cy1 = min(H, y+h+py)
        sub = strip.crop((cx0, cy0, cx1, cy1))
        ok = _cutout(sub, Path(dst_dir)/f"{prefix}{name}.png")
        res.append((name, Path(dst_dir)/f"{prefix}{name}.png" if ok else None))
    return res

def _cutout(crop_img, dst, bright=1.3, contrast=1.2, fg=0.80):
    im = ImageEnhance.Contrast(ImageEnhance.Brightness(crop_img.convert("RGB")).enhance(bright)).enhance(contrast)
    arr = np.array(remove(im.convert("RGBA"), session=_sess)); a = arr[..., 3]
    mask = (a > 40).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1: return False
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    arr[..., 3] = np.where(lab == big, a, 0)
    ys, xs = np.where(arr[..., 3] > 40)
    if len(xs) == 0: return False
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cc = Image.fromarray(arr).crop((x0, y0, x1+1, y1+1))
    w, h = cc.size; side = int(max(w, h)/fg); sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(cc, ((side-w)//2, (side-h)//2)); sq.save(dst); return True
