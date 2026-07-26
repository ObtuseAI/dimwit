"""Dimwit neural image-to-3D adapter — converts a concept reference image into a real 3D mesh using an
open-source single-image-to-3D model (TripoSR, MIT) running on the GPU.

Architecture: the heavy ML stack (PyTorch CUDA + TripoSR + marching cubes) lives in an ISOLATED Python
3.12 venv at Dimwit/neural3d/venv. Dimwit's main engine (Python 3.14) calls it as a SUBPROCESS — the
same clean external-process boundary used for Blender. This keeps the ML deps out of the core engine and
respects provenance (TripoSR is MIT; weights are stabilityai/TripoSR, openrail-permissive for assets).

After the raw mesh is produced, Dimwit cleans it, applies WANEFALL materials, renders a turnaround, and
runs pixel-truth validation (see character/perception). The neural mesh is review-only / staging.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEURAL = ROOT / "neural3d"
VENV_PY = NEURAL / "venv" / "Scripts" / "python.exe"
TRIPOSR_DIR = NEURAL / "TripoSR"


def status() -> dict:
    """Report readiness of each piece so the user/engine knows what is installed."""
    venv = VENV_PY.exists()
    torch_ok = cuda = False
    torch_ver = None
    if venv:
        try:
            r = subprocess.run([str(VENV_PY), "-c",
                "import torch,json;print(json.dumps({'v':torch.__version__,'cuda':torch.cuda.is_available()}))"],
                capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and r.stdout.strip():
                d = json.loads(r.stdout.strip().splitlines()[-1]); torch_ok = True; torch_ver = d["v"]; cuda = d["cuda"]
        except Exception:
            pass
    triposr = (TRIPOSR_DIR / "run.py").exists()
    return {"venv": venv, "torch": torch_ok, "torch_version": torch_ver, "cuda": cuda,
            "triposr": triposr, "ready": bool(venv and torch_ok and triposr)}


def image_to_mesh(image_path: str, out_dir: str, foreground_ratio: float = 0.85,
                  mc_resolution: int = 256, timeout: int = 900) -> dict:
    """Run TripoSR on a single image -> a 3D mesh (OBJ). Returns metadata + measured geometry."""
    st = status()
    if not st["ready"]:
        return {"ok": False, "error": "neural backend not ready", "status": st}
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    img = Path(image_path).resolve()
    if not img.exists():
        return {"ok": False, "error": f"image not found: {img}"}
    cmd = [str(VENV_PY), str(TRIPOSR_DIR / "run.py"), str(img),
           "--output-dir", str(out), "--model-save-format", "obj",
           "--mc-resolution", str(mc_resolution), "--foreground-ratio", str(foreground_ratio),
           "--no-remove-bg" if False else "--remove-bg"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(TRIPOSR_DIR))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    # TripoSR writes output/0/mesh.obj (and input.png)
    mesh = None
    for cand in (out / "0" / "mesh.obj", out / "mesh.obj"):
        if cand.exists():
            mesh = cand; break
    meta = {"ok": mesh is not None, "image": str(img), "mesh": str(mesh) if mesh else None,
            "returncode": r.returncode, "stdout_tail": r.stdout.strip().splitlines()[-4:] if r.stdout else [],
            "stderr_tail": r.stderr.strip().splitlines()[-4:] if r.stderr else []}
    if mesh:
        try:
            import trimesh
            from .meshgen import _measure
            meta["measured"] = _measure(trimesh.load(mesh, force="mesh"))
        except Exception as e:
            meta["measure_error"] = str(e)
    (out / "neural3d_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        print(json.dumps(status(), indent=2))
    else:
        print(json.dumps(image_to_mesh(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "artifacts/neural_out"), indent=2))
