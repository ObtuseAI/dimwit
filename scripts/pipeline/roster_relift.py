"""Dimwit ROSTER RE-LIFT — fix morphing roster-wide: run the proven handcraft->rig->import pipeline over the
remaining 7 characters (Ekris already done), each becoming clean quad topology + smooth rig + baked albedo/normal/
AO in-game. SERIAL (one Blender/UE process at a time — the box is RAM-tight; parallel would OOM). Per-char
try/except so one failure doesn't sink the batch. Writes artifacts/roster_relift_report.json.

  python scripts/pipeline/roster_relift.py            # the 7 (skip ekris)
  python scripts/pipeline/roster_relift.py 03 05      # just those
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BS = ROOT / "blender_scripts"

# Ekris (02) already landed + verified; do the rest.
ROSTER = [("01", "vorlax"), ("03", "zythan"), ("04", "qorin"), ("05", "therak"),
          ("06", "ullio"), ("07", "kelous"), ("08", "nexor")]


def fs(p):
    return str(p).replace("\\", "/")


def src_glb(nn, name):
    for c in (ART / f"hi3d_{nn}_{name}.glb", ART / f"hi3d_{nn}_{name}_sym.glb", ART / f"hi3d_{name}.glb"):
        if c.exists():
            return c
    return None


def blender(script, args, timeout):
    r = subprocess.run([str(BLENDER), "--background", "--python", str(BS / script), "--"] + args,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode


def ue(arg_str, timeout=1200):
    r = subprocess.run([str(UE_CMD), str(UPROJECT), f"-ExecutePythonScript={arg_str}".replace("\\", "/"),
                        "-unattended", "-nosplash", "-nopause", "-stdout"], capture_output=True, text=True, timeout=timeout)
    return r.returncode


def do_char(nn, name) -> dict:
    asset = f"SM_Char_{nn}_{name}"
    rec = {"char": f"{nn}_{name}", "ok": False, "steps": {}}
    src = src_glb(nn, name)
    if not src:
        rec["error"] = "no source GLB"; return rec
    outdir = ART / "handcraft" / asset
    rep = outdir / f"{asset}_handcraft.json"
    try:
        # 1) handcraft (clean quad topology + normal/AO + albedo from the GLB's own colors)
        blender("handcraft.py", [f"in={fs(src)}", f"outdir={fs(outdir)}", f"name={asset}",
                "target=14000", "res=2048", "samples=8", "albedo=auto", f"report={fs(rep)}"], timeout=1800)
        hc = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else {}
        rec["steps"]["handcraft"] = {"ok": hc.get("ok"), "maps": list((hc.get("maps") or {}).keys())}
        retopo = outdir / f"{asset}_retopo.fbx"
        if not retopo.exists():
            rec["error"] = "handcraft produced no retopo fbx"; return rec
        # 2) rig the clean low-poly onto SK_Mannequin
        rigfbx = ART / "rig" / f"{asset}_handcrafted_rig.fbx"
        blender("rig_to_mannequin.py", [f"mannequin={fs(ART / 'rig' / 'SK_Mannequin_ref.fbx')}",
                f"mesh={fs(retopo)}", f"out={fs(rigfbx)}", "height=180"], timeout=1200)
        rigj = Path(str(rigfbx) + ".rig.json")
        rj = json.loads(rigj.read_text(encoding="utf-8")) if rigj.exists() else {}
        rec["steps"]["rig"] = {"ok": rj.get("ok"), "coverage": rj.get("weight_coverage")}
        if not rigfbx.exists():
            rec["error"] = "rig produced no fbx"; return rec
        # 3) import to UE (skeletal + maps + per-char material)
        nrm = outdir / f"{asset}_normal.png"; ao = outdir / f"{asset}_ao.png"; alb = outdir / f"{asset}_albedo.png"
        mat = f"/Game/Wanefall/Dimwit/CharactersRigged/{name}_mat"
        argstr = (f"{fs(ROOT / 'scripts/ue/ue_import_handcrafted_rig.py')} rig={fs(rigfbx)} normal={fs(nrm)} "
                  f"ao={fs(ao)} albedo={fs(alb)} name={asset}_Rig mat={mat}")
        impres = ART / "import_handcrafted_result.json"
        if impres.exists():
            impres.unlink()
        ue(argstr, timeout=1200)
        ir = json.loads(impres.read_text(encoding="utf-8")) if impres.exists() else {}
        rec["steps"]["import"] = {k: ir.get(k) for k in ("ok", "rig_imported", "albedo_imported", "material_wired")}
        rec["ok"] = bool(ir.get("ok"))
    except subprocess.TimeoutExpired as e:
        rec["error"] = f"timeout: {e}"
    except Exception as e:
        rec["error"] = repr(e)
    return rec


def main(argv):
    want = set(argv) if argv else None
    results = []
    for nn, name in ROSTER:
        if want and nn not in want and name not in want:
            continue
        print(f"[{nn} {name}] re-lifting ...", flush=True)
        t0 = time.time()
        rec = do_char(nn, name)
        rec["secs"] = round(time.time() - t0)
        results.append(rec)
        print(f"[{nn} {name}] ok={rec['ok']} {rec.get('error','')} ({rec['secs']}s)", flush=True)
        (ART / "roster_relift_report.json").write_text(
            json.dumps({"results": results, "ok_count": sum(1 for r in results if r["ok"])}, indent=2),
            encoding="utf-8")
    print(f"ROSTER_RELIFT_DONE {sum(1 for r in results if r['ok'])}/{len(results)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
