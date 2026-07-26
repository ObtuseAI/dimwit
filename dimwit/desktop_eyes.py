"""Dimwit DESKTOP EYES — live screen / window / video capture so Dimwit can SEE the running UE editor + PIE
gameplay (not just blind headless commandlets). Read-only: this module never controls input (that's the guarded
desktop_hands layer). py3.14-clean stack: mss (capture) + pygetwindow (window targeting) + imageio (video) + PIL.

  from dimwit.desktop_eyes import DesktopEyes
  eyes = DesktopEyes()
  eyes.list_windows()                              # what's on screen
  eyes.capture_window("Unreal", out)               # one PNG of the UE editor window
  eyes.capture_screen(out, monitor=1)              # a whole monitor
  clip = eyes.record_window("Wanefall", out_mp4, seconds=6, fps=12)   # PIE gameplay video
  frames = eyes.capture_stream(out_dir, "Unreal", seconds=3, fps=6)   # frames for motion/optics QA

Lock-screen note: a desktop framebuffer grab returns the LOCK SCREEN when Windows is locked. capture_window()
fails closed (returns {"ok": False, "error": "window not found"}) if the target window is absent — so a locked
session yields an honest miss, never a fake frame.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

ART = Path(__file__).resolve().parent.parent / "artifacts" / "eyes"
PW_SCRIPT = Path(__file__).resolve().parent / "eyes_ps" / "printwindow_capture.ps1"


def _now():
    return time.time()


def process_identity_check(capture: dict, expected_pid: int | None, expected_proc: str) -> dict:
    """Fail-closed binding of a window capture to the process it must belong to.

    Title-substring window matching cannot distinguish a packaged WanefallGreybox.exe window from a
    stale `UnrealEditor -game` window (same title). The PrintWindow tier reports the captured
    window's owning pid/proc; this check asserts them. `expected_pid=None` is attach mode (no
    launched process): the process NAME must still match. A capture with no pid evidence (region
    fallback) can never pass — identity unprovable means fail, never a silent green.
    """
    issues: list[str] = []
    got_pid = capture.get("pid")
    got_proc = str(capture.get("proc") or "")
    if got_pid is None:
        issues.append(f"capture carries no pid evidence (tier={capture.get('tier')}); process identity unprovable")
    elif expected_pid is not None and int(got_pid) != int(expected_pid):
        issues.append(f"captured window pid {got_pid} != launched pid {expected_pid}")
    if expected_proc and expected_proc.lower() not in got_proc.lower():
        issues.append(f"captured window process {got_proc or '<none>'!r} does not match expected {expected_proc!r}")
    return {
        "passed": not issues,
        "issues": issues,
        "captured_pid": got_pid,
        "captured_proc": got_proc or None,
        "expected_pid": expected_pid,
        "expected_proc": expected_proc,
        "capture_tier": capture.get("tier"),
        "mode": "launched_pid_bound" if expected_pid is not None else "attach_proc_bound",
    }


@dataclass
class DesktopEyes:
    default_monitor: int = 1

    # ---- window discovery -----------------------------------------------------------------------
    def list_windows(self, only_visible: bool = True) -> list:
        import pygetwindow as gw
        out = []
        for w in gw.getAllWindows():
            if only_visible and (not w.title or w.width <= 0 or w.height <= 0):
                continue
            out.append({"title": w.title, "left": w.left, "top": w.top,
                        "width": w.width, "height": w.height,
                        "active": bool(getattr(w, "isActive", False)),
                        "minimized": bool(getattr(w, "isMinimized", False))})
        return out

    def find_window(self, title_substr: str) -> dict | None:
        """First visible, non-minimized window whose title contains title_substr (case-insensitive)."""
        import pygetwindow as gw
        t = title_substr.lower()
        cands = [w for w in gw.getAllWindows()
                 if w.title and t in w.title.lower() and w.width > 0 and w.height > 0
                 and not getattr(w, "isMinimized", False)]
        if not cands:
            return None
        w = max(cands, key=lambda x: x.width * x.height)        # the biggest match = the real editor, not a tooltip
        return {"title": w.title, "left": w.left, "top": w.top, "width": w.width, "height": w.height, "_w": w}

    def focus_window(self, title_substr: str) -> bool:
        """Bring a window to the foreground (read-tier helper; capture only — not input control)."""
        w = self.find_window(title_substr)
        if not w:
            return False
        try:
            win = w["_w"]
            if getattr(win, "isMinimized", False):
                win.restore()
            win.activate()
            return True
        except Exception:
            return False

    # ---- still capture --------------------------------------------------------------------------
    def _grab(self, region: dict, out: str | Path) -> dict:
        import mss
        import mss.tools
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with mss.MSS() as sct:
            img = sct.grab(region)
            mss.tools.to_png(img.rgb, img.size, output=str(out))
        return {"ok": out.exists() and out.stat().st_size > 0, "png": str(out),
                "bytes": out.stat().st_size if out.exists() else 0, "region": region}

    def capture_screen(self, out: str | Path, monitor: int | None = None) -> dict:
        import mss
        with mss.MSS() as sct:
            mon = sct.monitors[monitor or self.default_monitor]
        return self._grab(mon, out)

    def capture_region(self, out, left, top, width, height) -> dict:
        return self._grab({"left": int(left), "top": int(top), "width": int(width), "height": int(height)}, out)

    def capture_window_printwindow(self, title_substr: str, out: str | Path, proc: str | None = None) -> dict:
        """Tier A: PrintWindow(PW_RENDERFULLCONTENT) via PowerShell+.NET — the RELIABLE way to grab a DirectX/
        GPU window (UE editor / PIE), which a desktop framebuffer grab returns BLACK. `proc` (e.g. 'UnrealEditor')
        disambiguates the title collision (the Chrome 'WANEFALL Build Review' window also matches 'Wanefall')."""
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PW_SCRIPT),
               "-title", title_substr, "-out", str(out)]
        if proc:
            cmd += ["-proc", proc]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:
            return {"ok": False, "error": f"powershell failed: {e}", "tier": "printwindow"}
        line = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
        try:
            res = json.loads(line)
        except Exception:
            return {"ok": False, "error": f"unparseable PS output: {line[:200]}", "tier": "printwindow"}
        res["tier"] = "printwindow"
        res["png"] = str(out)
        res["bytes"] = out.stat().st_size if out.exists() else 0
        return res

    def capture_window(self, title_substr: str, out: str | Path, focus: bool = True, pad: int = 0,
                       proc: str | None = "UnrealEditor", prefer: str = "printwindow") -> dict:
        """Capture a window. Default Tier A = PrintWindow (reliable for the UE DirectX viewport); falls back to a
        focused mss region grab (Tier C) if PrintWindow is unavailable/empty. Fail-closed: returns ok=False
        (never a black frame passed as success) when the window can't be found or the grab is empty/too-dark."""
        if prefer == "printwindow" and PW_SCRIPT.exists():
            r = self.capture_window_printwindow(title_substr, out, proc=proc)
            if r.get("ok") and r.get("bytes", 0) > 2000:
                return r
            # fall through to region grab on PrintWindow miss
        w = self.find_window(title_substr)
        if not w:
            return {"ok": False, "error": f"window not found: {title_substr!r}", "tier": "region",
                    "candidates": [x["title"] for x in self.list_windows()][:20]}
        if focus:
            self.focus_window(title_substr)
            time.sleep(0.35)
            w = self.find_window(title_substr) or w
        region = {"left": max(0, w["left"] - pad), "top": max(0, w["top"] - pad),
                  "width": w["width"] + 2 * pad, "height": w["height"] + 2 * pad}
        r = self._grab(region, out)
        r["window_title"] = w["title"]
        r["tier"] = "region"
        return r

    # ---- streams + video ------------------------------------------------------------------------
    def capture_stream(self, out_dir, title_substr: str | None, seconds: float = 3.0, fps: float = 6.0,
                       region: dict | None = None) -> dict:
        """Capture a burst of PNG frames (for motion / animation / optics analysis). Returns frame paths."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if region is None:
            if title_substr:
                w = self.find_window(title_substr)
                if not w:
                    return {"ok": False, "error": f"window not found: {title_substr!r}"}
                if w.get("_w"):
                    self.focus_window(title_substr)
                    time.sleep(0.3)
                    w = self.find_window(title_substr) or w
                region = {"left": w["left"], "top": w["top"], "width": w["width"], "height": w["height"]}
            else:
                import mss
                with mss.MSS() as sct:
                    region = sct.monitors[self.default_monitor]
        n = max(1, int(seconds * fps))
        interval = 1.0 / fps
        frames = []
        import mss
        import mss.tools
        with mss.MSS() as sct:
            for i in range(n):
                t0 = _now()
                p = out_dir / f"frame_{i:03d}.png"
                img = sct.grab(region)
                mss.tools.to_png(img.rgb, img.size, output=str(p))
                frames.append(str(p))
                dt = interval - (_now() - t0)
                if dt > 0 and i < n - 1:
                    time.sleep(dt)
        return {"ok": len(frames) > 0, "frames": frames, "count": len(frames), "fps": fps, "region": region}

    def record_window(self, title_substr: str, out_mp4, seconds: float = 6.0, fps: float = 12.0) -> dict:
        """Record a window to an mp4 (PIE gameplay / animation feel). Frames -> imageio (bundled ffmpeg)."""
        tmp = Path(out_mp4).with_suffix("")
        burst = self.capture_stream(tmp.parent / (tmp.name + "_frames"), title_substr, seconds, fps)
        if not burst.get("ok"):
            return burst
        try:
            import imageio.v3 as iio
            import numpy as np
            from PIL import Image
            stack = [np.asarray(Image.open(f).convert("RGB")) for f in burst["frames"]]
            iio.imwrite(str(out_mp4), stack, fps=int(fps))
        except Exception as e:
            return {"ok": False, "error": f"video encode failed: {e}", "frames": burst["frames"]}
        return {"ok": Path(out_mp4).exists(), "mp4": str(out_mp4), "frames": burst["frames"],
                "count": burst["count"], "fps": fps}


if __name__ == "__main__":
    import json
    e = DesktopEyes()
    print(json.dumps({"windows": [w["title"] for w in e.list_windows()][:25]}, indent=2))
