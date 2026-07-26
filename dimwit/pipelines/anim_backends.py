"""Dimwit pluggable RIGGING + ANIMATION backends.

Lets Dimwit use the best-of-breed rig/anim tools interchangeably (Blender smooth-rig today; AccuRig / Tripo /
Mixamo / Cascadeur / AI-mocap / ML-text-to-motion / a layered aim AnimBP as they're activated). Whatever
'Auro 15.0' turns out to be registers here as one more backend. Registry: config/rig_anim_backends.json.

  from dimwit.pipelines.anim_backends import list_backends, get_backend
  list_backends()                       # {'rigging': {...status...}, 'animation': {...}}
  get_backend('rigging', 'blender_smooth').run(**kwargs)   # BUILT/READY run; SCAFFOLD raises with activation steps
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "rig_anim_backends.json"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")


class BackendNotActivated(Exception):
    """Raised when a SCAFFOLD backend is invoked before its tool/key/web step is set up (carries how-to)."""


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def list_backends() -> dict:
    r = _registry()
    return {
        "rigging": {k: v.get("status") for k, v in r.get("rigging_backends", {}).items()},
        "animation": {k: v.get("status") for k, v in r.get("animation_backends", {}).items()},
    }


class Backend:
    def __init__(self, domain: str, name: str, spec: dict):
        self.domain, self.name, self.spec = domain, name, spec
        self.status = spec.get("status", "SCAFFOLD")

    def run(self, **kwargs):
        if self.status in ("BUILT", "READY"):
            return _RUNNERS[(self.domain, self.name)](**kwargs)
        raise BackendNotActivated(
            f"[{self.domain}/{self.name}] is SCAFFOLD ({self.spec.get('tool')}). "
            f"Activate: {self.spec.get('activate', self.spec.get('integration'))}"
        )


def get_backend(domain: str, name: str) -> Backend:
    r = _registry()
    key = "rigging_backends" if domain == "rigging" else "animation_backends"
    spec = r.get(key, {}).get(name)
    if spec is None:
        raise KeyError(f"unknown {domain} backend '{name}'")
    return Backend(domain, name, spec)


# ---- runnable backends -----------------------------------------------------------------------------
def _ue(script_args: str, timeout: int = 1200):
    cmd = [str(UE_CMD), str(UPROJECT),
           (f"-ExecutePythonScript={script_args}").replace("\\", "/"),
           "-unattended", "-nosplash", "-nopause", "-stdout"]
    subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _rig_blender_smooth(mannequin_fbx: str, mesh: str, out_fbx: str, **_):
    bl = r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"
    script = ROOT / "blender_scripts" / "rig_to_mannequin.py"
    subprocess.run([bl, "--background", "--python", str(script), "--",
                    f"mannequin={mannequin_fbx}", f"mesh={mesh}", f"out={out_fbx}"],
                   capture_output=True, text=True, timeout=1800)
    rj = Path(out_fbx + ".rig.json")
    return json.loads(rj.read_text()) if rj.exists() else {"ok": False}


def _anim_animstarterpack_retarget(**_):
    driver = ROOT / "scripts/ue/ue_retarget_animstarterpack.py"
    res = ROOT / "artifacts" / "retarget_result.json"
    if res.exists():
        res.unlink()
    _ue(str(driver))
    return json.loads(res.read_text()) if res.exists() else {"ok": False}


_RUNNERS = {
    ("rigging", "blender_smooth"): _rig_blender_smooth,
    ("animation", "animstarterpack_retarget"): _anim_animstarterpack_retarget,
}


if __name__ == "__main__":
    print(json.dumps(list_backends(), indent=2))
