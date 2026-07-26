"""Serial batch: run the proven Vorlax pipeline across all 8 WANEFALL characters.
GPU is a single 8GB card -> every stage is its own short-lived process (frees VRAM) and
runs STRICTLY SERIALLY. Continue-on-error so one bad character never sinks the batch.

Per character N:
  0. upscale the small sheet front-crop (Lanczos) for more working resolution
  1. rembg exact transparent cutout (removes base, isolates figure, keeps head)
  2. Zero123++ 6 white-bg surround views (the fix) via InstantMesh custom UNet
  3. InstantMesh multiview NeRF recon @256 (clean watertight mesh, concept colors baked per-vertex)
  4. clean renders: 'textured' (real concept colors, NO emission) + 'clay' (geometry proof)
"""
from __future__ import annotations
import sys, subprocess, time, traceback
from pathlib import Path
from PIL import Image
from dimwit.character_roster_ids import CHARACTER_IDS, require_character_id

RAIN = Path(__file__).resolve().parents[2]
N3D  = RAIN / "neural3d"
VENV = N3D / "venv" / "Scripts" / "python.exe"
IM   = N3D / "InstantMesh"
IM_RECON = RAIN / "neural3d_extensions" / "instantmesh" / "recon_from_views.py"
SRC  = RAIN / "source_art"
ART  = RAIN / "artifacts"
LOG  = ART / "batch_log.txt"
(SRC).mkdir(exist_ok=True); (ART / "fronts_up").mkdir(parents=True, exist_ok=True)

NAMES = list(CHARACTER_IDS)
RES = "320"   # roomy framing makes the figure smaller in-frame -> a touch more recon res keeps detail


def selected_names(argv: list[str]) -> list[str]:
    """Validate every caller-supplied item before any filesystem operation."""
    return [require_character_id(name) for name in (argv or NAMES)]

def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, cwd, env=None, tag="") -> bool:
    import os
    e = dict(os.environ); e.update(env or {})
    t0 = time.time()
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=e,
                       capture_output=True, text=True)
    dt = time.time() - t0
    tail = (p.stdout or "").strip().splitlines()[-1:] + (p.stderr or "").strip().splitlines()[-2:]
    ok = p.returncode == 0
    log(f"   {tag} {'OK' if ok else 'FAIL rc='+str(p.returncode)} ({dt:.0f}s) :: {' | '.join(tail)[-300:]}")
    return ok

def upscale(name: str):
    im = Image.open(ART / "fronts" / f"{name}.png").convert("RGB")
    w, h = im.size
    scale = max(1.0, 560 / max(w, h))          # bring long side to ~560px
    im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    out = ART / "fronts_up" / f"{name}.png"
    im.save(out)
    return out

def render(name: str, mode: str) -> bool:
    """Call render_mesh in-process (it shells to Blender). cwd must be RAIN for imports."""
    sys.path.insert(0, str(RAIN))
    try:
        from dimwit.character import render_mesh
        obj = ART / f"{name}_recon.obj"
        if not obj.exists():
            log(f"   render:{mode} SKIP (no mesh)"); return False
        r = render_mesh(str(obj), ART / f"{name}_{mode}", mode, rot_x=0.0, flip=True)
        ok = bool(r.get("ok"))
        log(f"   render:{mode} {'OK' if ok else 'FAIL'}")
        return ok
    except Exception:
        log("   render:%s EXC %s" % (mode, traceback.format_exc().splitlines()[-1])); return False

def main():
    only = selected_names(sys.argv[1:])
    log(f"=== BATCH START ({len(only)} chars): {', '.join(only)} ===")
    summary = {}
    for name in only:
        log(f"--- {name} ---")
        stages = {}
        try:
            up = upscale(name); stages["upscale"] = up.exists()
            cut = SRC / f"{name}_cutout.png"
            stages["cutout"] = run([VENV, N3D/"make_cutout.py", up, cut], cwd=RAIN, tag="cutout")
            rgba = SRC / f"{name}_cutout_rgba.png"
            if stages["cutout"] and rgba.exists():
                stages["views"] = run([VENV, "gen_views_im.py", f"../source_art/{name}_cutout_rgba.png",
                                       f"../artifacts/{name}_views"], cwd=N3D, tag="views")
            else:
                stages["views"] = False
            grid = ART / f"{name}_views" / "grid_im.png"
            if stages["views"] and grid.exists():
                stages["recon"] = run([VENV, IM_RECON,
                                       f"../../artifacts/{name}_views/grid_im.png",
                                       f"../../artifacts/{name}_recon.obj", RES],
                                      cwd=IM, env={"PYTHONPATH": "../stubs"}, tag="recon")
            else:
                stages["recon"] = False
            if stages["recon"]:
                stages["textured"] = render(name, "textured")
                stages["clay"]     = render(name, "clay")
        except Exception:
            log("   CHAR EXC %s" % traceback.format_exc().splitlines()[-1])
        summary[name] = stages
        log(f"   -> {name}: " + " ".join(f"{k}={'Y' if v else 'N'}" for k,v in stages.items()))
    log("=== BATCH DONE ===")
    for n, s in summary.items():
        done = s.get("textured") and s.get("clay")
        log(f"   {n}: {'COMPLETE' if done else 'INCOMPLETE'}  {s}")

if __name__ == "__main__":
    main()
