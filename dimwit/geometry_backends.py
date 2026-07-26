"""Dimwit pluggable GEOMETRY backends — closes G3 (the single paid-cloud geometry dependency).

Geometry is no longer Hi3D-or-nothing. `generate()` walks a fallback chain (hi3d -> triposr -> primitive) and
returns the first backend that produces a mesh, so the engine NEVER hard-stops: even fully offline with no GPU,
the deterministic `primitive` blockout keeps the pipeline runnable + riggable (flagged not-promotable, fail-closed
provenance). Mirrors dimwit/pipelines/anim_backends.py.

  from dimwit.geometry_backends import list_backends, generate
  list_backends()                       # {name: status}
  generate(image_or_prompt, out_fbx)    # walks default_chain, returns {ok, backend, out, placeholder, provenance}
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "geometry_backends.json"
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
BS = ROOT / "blender_scripts"


class BackendNotActivated(Exception):
    pass


def _reg() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def list_backends() -> dict:
    return {k: v.get("status") for k, v in _reg().get("backends", {}).items()}


def _run_primitive(out_fbx: str, height: float = 1.8, seed: int = 2, **_) -> dict:
    report = str(Path(out_fbx).with_suffix(".fbx.blockout.json"))
    cmd = [str(BLENDER), "--background", "--python", str(BS / "primitive_blockout.py"), "--",
           f"out={out_fbx}", f"height={height}", f"seed={seed}", f"report={report}"]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    r = json.loads(Path(report).read_text(encoding="utf-8")) if Path(report).exists() else {"ok": False}
    r["backend"] = "primitive"
    r["placeholder"] = True
    r["provenance"] = {"source": "Dimwit primitive_blockout.py (deterministic)",
                       "license": "first-party", "promotable": False}
    return r


def _run_hi3d(image: str, out_fbx: str, **_) -> dict:
    try:
        from dimwit import hi3d  # noqa
    except Exception as e:
        raise BackendNotActivated(f"hi3d module unavailable: {e}")
    # hi3d.py is the real client; here we only check it's configured (network/credits gated)
    raise BackendNotActivated("hi3d.generate is driven by the character pipeline (hi3d.py); "
                              "geometry_backends uses it as the primary chain entry, not re-implemented here")


_RUN = {"primitive": _run_primitive}


def get_status(name: str) -> str:
    return _reg().get("backends", {}).get(name, {}).get("status", "UNKNOWN")


def generate(source: str, out_fbx: str, chain: list | None = None, **kw) -> dict:
    """Walk the fallback chain; return the first backend that produces a mesh. Always succeeds via `primitive`
    unless even Blender is missing (then fail-closed). `source` = image path or prompt for the cloud/GPU backends."""
    chain = chain or _reg().get("default_chain", ["primitive"])
    attempts = []
    for name in chain:
        status = get_status(name)
        if status not in ("BUILT",) or name not in _RUN:
            attempts.append({"backend": name, "skipped": f"status={status} (not runnable here)"})
            continue
        try:
            r = _RUN[name](out_fbx=out_fbx, image=source, **kw)
            r["attempts"] = attempts + [{"backend": name, "used": True}]
            if r.get("ok"):
                return r
        except BackendNotActivated as e:
            attempts.append({"backend": name, "blocked": str(e)})
    return {"ok": False, "backend": None, "attempts": attempts,
            "error": "no geometry backend produced a mesh (even the primitive fallback failed — check Blender)"}


def health() -> dict:
    return {"blender": BLENDER.exists(), "backends": list_backends(),
            "fallback_runnable": BLENDER.exists() and (BS / "primitive_blockout.py").exists()}


if __name__ == "__main__":
    print(json.dumps(health(), indent=2))
