"""Dimwit adapters — drive the REAL WANEFALL pipeline (Unreal commandlets + capture switches) as external
processes. Each adapter is guarded + watchdog-bounded and defaults to dry_run so a heavy UE render only
fires when explicitly asked. Adapters return the produced artifact path (e.g. a contact sheet) so the
recursive loop can RE-PERCEIVE a freshly rendered candidate — closing the perceptual feedback loop.

Nothing here writes into the active game; captures land in the project's Saved/ShowMeAI bridge dirs.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

UE_EDITOR = r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
UE_CMD = r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
UPROJECT = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"
JAIL_MAP = "/Game/Wanefall/Maps/Wanefall_WaneTrialJailCell_01"
SAVED = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\Saved\ShowMeAI")


def _available() -> bool:
    return Path(UE_EDITOR).exists() and Path(UPROJECT).exists()


def _render(switch: str, done_marker: Path, deadline_s: int = 220) -> dict:
    """Launch a -game -RenderOffScreen capture with the given switch; poll a done-marker; kill on timeout."""
    if not _available():
        return {"ok": False, "error": "UE editor / uproject not found", "switch": switch}
    if done_marker.exists():
        done_marker.unlink()
    args = (f'"{UPROJECT}" {JAIL_MAP} -game -RenderOffScreen -ResX=1280 -ResY=720 '
            f'-ExecCmds="t.IdleWhenNotForeground 0" -{switch} -unattended -nosplash')
    proc = subprocess.Popen(f'"{UE_EDITOR}" {args}', shell=True)
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        if done_marker.exists():
            break
        time.sleep(3)
    ok = done_marker.exists()
    try:
        proc.kill()
    except Exception:
        pass
    return {"ok": ok, "switch": switch, "done_marker": str(done_marker), "elapsed_s": round(time.time() - t0, 1)}


def hero_capture(dry_run: bool = True) -> dict:
    """Real fixed-camera HERO validation capture (-WANEFALLHEROCAPTURE)."""
    marker = SAVED / "hero_capture_done.json"
    if dry_run:
        return {"adapter": "hero_capture", "dry_run": True, "would_run_switch": "WANEFALLHEROCAPTURE",
                "available": _available(), "frames_dir": str(SAVED / "WanefallHeroCaptureFrames")}
    r = _render("WANEFALLHEROCAPTURE", marker)
    r["frames_dir"] = str(SAVED / "WanefallHeroCaptureFrames")
    return r


def player_camera_capture(dry_run: bool = True) -> dict:
    """Real player-camera gameplay-lane capture (-WANEFALLMOVEMENTCAPTURE)."""
    marker = SAVED / "post39d_movement_capture_done.json"
    if dry_run:
        return {"adapter": "player_camera_capture", "dry_run": True, "would_run_switch": "WANEFALLMOVEMENTCAPTURE",
                "available": _available(), "frames_dir": str(SAVED / "Post39DCharacterMovementReviewProof")}
    r = _render("WANEFALLMOVEMENTCAPTURE", marker)
    r["frames_dir"] = str(SAVED / "Post39DCharacterMovementReviewProof")
    return r


def dual_gate(timestamp: str, bridge_dir: str, dry_run: bool = True) -> dict:
    """Run the WANEFALL dual-gate live-QA commandlet (developer + player-experience gates)."""
    if dry_run:
        return {"adapter": "dual_gate", "dry_run": True, "would_run": "WanefallDualGateLiveQA", "available": _available()}
    if not _available():
        return {"ok": False, "error": "UE cmd not found"}
    cmd = [UE_CMD, UPROJECT, "-run=WanefallDualGateLiveQA", f"-Timestamp={timestamp}", f"-BridgeDir={bridge_dir}",
           "-unattended", "-nosplash"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return {"adapter": "dual_gate", "ok": r.returncode == 0, "returncode": r.returncode,
            "stdout_tail": r.stdout.strip().splitlines()[-2:] if r.stdout else []}


ADAPTERS = {"hero_capture": hero_capture, "player_camera_capture": player_camera_capture, "dual_gate": dual_gate}


if __name__ == "__main__":
    print(json.dumps({"ue_available": _available(),
                      "hero": hero_capture(dry_run=True), "lane": player_camera_capture(dry_run=True)}, indent=2))
