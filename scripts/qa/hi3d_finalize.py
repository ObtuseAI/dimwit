"""After hi3d_batch: build the all-8 Hi3D cover contact sheet + run the GLM QA gate on the roster."""
import sys, json
from pathlib import Path
from PIL import Image, ImageDraw
RAIN = Path(__file__).resolve().parents[2]
ART = RAIN / "artifacts"
sys.path.insert(0, str(RAIN))
NAMES = ["01_vorlax","02_ekris","03_zythan","04_qorin","05_therak","06_ullio","07_kelous","08_nexor"]
DESC = {"01_vorlax":"blue armor, cyan seams","02_ekris":"silver/white plated armor",
        "03_zythan":"purple armor, magenta seams","04_qorin":"green/mossy organic armor",
        "05_therak":"orange/red molten armor","06_ullio":"teal/cyan armor",
        "07_kelous":"black + gold trimmed armor","08_nexor":"pink/white sleek armor"}

def contact():
    cols, rows, cw, ch, pad, lh = 4, 2, 300, 300, 8, 22
    cv = Image.new("RGB", (cols*(cw+pad)+pad, rows*(ch+lh+pad)+pad), (10,12,16)); d = ImageDraw.Draw(cv)
    for i, n in enumerate(NAMES):
        p = ART / f"hi3d_{n}_cover.png"
        x = pad+(i % cols)*(cw+pad); y = pad+(i//cols)*(ch+lh+pad)
        if p.exists(): cv.paste(Image.open(p).convert("RGB").resize((cw, ch)), (x, y+lh))
        d.text((x+4, y+4), n.replace("_", " ").upper(), fill=(120,210,225))
    out = ART / "HI3D_ALL8_covers.png"; cv.save(out); print("wrote", out)

def qa():
    from dimwit import cloud_brain
    res = []
    for n in NAMES:
        cov = ART / f"hi3d_{n}_cover.png"
        if not cov.exists(): print(f"  {n}: no cover, skip"); continue
        imgs = [str(cov)]
        for v in ("threequarter", "side"):  # add my GLB renders if present
            r = ART / f"hi3d_{n}_raw" / f"mview_{v}.png"
            if r.exists(): imgs.append(str(r))
        v = cloud_brain.review_character(n, str(ART/"fronts"/f"{n}.png"), imgs, DESC.get(n, ""))
        res.append(v)
        print(f"  {n}: overall={v.get('overall')} shape={v.get('shape')} color={v.get('color')} "
              f"seams={v.get('seams')} head={v.get('head_face')} glow={v.get('glow_present')}")
    (ART / "hi3d_qa_report.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    if res:
        print(f"\nmean overall = {sum(r.get('overall',0) for r in res)/len(res):.1f}  "
              f"(prior local pipeline was ~1.8)")

if __name__ == "__main__":
    contact()
    if "--qa" in sys.argv: qa()
