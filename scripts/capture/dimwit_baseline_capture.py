"""Dimwit BASELINE CAPTURE+JUDGE — the live-game half of the operator's validation loop.

Wait for the standalone game window to appear, grab it via PrintWindow (the reliable way to capture a UE DirectX
viewport — a plain framebuffer grab returns BLACK), then run elite optics on the real on-screen frame (NOT a
headless SceneCapture2D). Fail-closed. Writes artifacts/baseline/<label>_verdict.json + the PNG so the orchestrator
can look at the exact same frame.

  python scripts/capture/dimwit_baseline_capture.py [label] [window=WanefallGreybox] [waitsecs=180]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dimwit.desktop_eyes import DesktopEyes          # noqa: E402
from dimwit import optics                            # noqa: E402


def main(argv):
    label = argv[0] if argv and "=" not in argv[0] else "thirdperson_baseline"
    window = "WanefallGreybox"
    waitsecs = 180
    for a in argv:
        if a.startswith("window="):
            window = a.split("=", 1)[1]
        elif a.startswith("waitsecs="):
            waitsecs = int(a.split("=", 1)[1])

    outdir = ROOT / "artifacts" / "baseline"
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / f"{label}.png"
    eyes = DesktopEyes()

    # 1) poll for the game window to come up
    t0 = time.time()
    found = None
    while time.time() - t0 < waitsecs:
        w = eyes.find_window(window)
        if w:
            found = w
            break
        time.sleep(4)

    report = {"label": label, "window_query": window, "waited_s": round(time.time() - t0, 1)}
    vpath = outdir / f"{label}_verdict.json"

    if not found:
        report.update(ok=False, error=f"game window {window!r} never appeared within {waitsecs}s",
                      windows_seen=[x["title"] for x in eyes.list_windows()][:25])
        vpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("BASELINE_CAPTURE_DONE ok=False (no window)")
        return 1

    report["window_title"] = found["title"]
    eyes.focus_window(window)       # standalone -game throttles + the swapchain must be on top to grab it
    time.sleep(6)                   # let the level finish streaming + a few animation frames pass

    # 2) capture the REAL window the player sees. A standalone -game window uses a raw DXGI flip-model swapchain
    #    that PrintWindow CANNOT read (returns the white GDI background); the editor/PIE window can. So for the
    #    standalone game we grab the COMPOSITED desktop pixels at the window rect (mss region), which is exactly
    #    what is on screen. The window is foregrounded above so nothing occludes it.
    cap = eyes.capture_window(window, png, focus=True, proc="UnrealEditor", prefer="region")
    report["capture"] = {k: cap.get(k) for k in ("ok", "tier", "bytes", "error")}
    if not cap.get("ok"):
        report["ok"] = False
        vpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"BASELINE_CAPTURE_DONE ok=False (capture failed: {cap.get('error')})")
        return 1

    # 3) elite optics on the real frame (semantic if GLM available; pixel always)
    v = optics.judge_character(str(png), require_semantic=False)
    report.update(ok=True, png=str(png),
                  verdict={k: v.get(k) for k in ("passed", "hard_fail", "score", "issues")},
                  semantic=v.get("semantic"),
                  pixel_style=(v.get("pixel") or {}).get("style"))
    vpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"BASELINE_CAPTURE_DONE ok=True png={png}")
    print("VERDICT " + json.dumps(report["verdict"], default=str))
    print("SEMANTIC " + json.dumps(report.get("semantic"), default=str)[:700])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
