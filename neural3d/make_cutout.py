"""Exact-outline cutout: rembg alpha matte -> tight crop to the silhouette -> clean grey bg.
Removes the cell background AND the base platform at the source so TripoSR reconstructs only the character."""
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from rembg import remove, new_session

src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
# u2net matte
cut = remove(im, session=new_session("u2net"))
a = np.array(cut)[..., 3]
ys, xs = np.where(a > 30)
if len(xs) == 0:
    print("NO_FOREGROUND"); sys.exit(1)
x0,x1,y0,y1 = xs.min(), xs.max(), ys.min(), ys.max()
pad = int(0.06*max(x1-x0, y1-y0))
x0,y0 = max(0,x0-pad), max(0,y0-pad); x1,y1 = min(im.width,x1+pad), min(im.height,y1+pad)
cut = cut.crop((x0,y0,x1,y1))
# square canvas, grey bg (TripoSR --no-remove-bg expects grey bg), foreground ~0.85
w,h = cut.size; side = int(max(w,h)/0.82)
canvas = Image.new("RGBA",(side,side),(127,127,127,255))
canvas.alpha_composite(cut,((side-w)//2,(side-h)//2))
canvas.convert("RGB").save(out)
# also save the RGBA cutout (for back-view generation / reference)
cut.save(out.replace(".png","_rgba.png"))
print("CUTOUT_OK", canvas.size, "fg_bbox", (x1-x0, y1-y0))
