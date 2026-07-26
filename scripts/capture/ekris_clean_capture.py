"""Capture the Ekris character from Wanefall_CleanStage_01 (clean background, no lobby junk).
Writes char_still_focused.png (the priority optics subject) without touching anim_live_proof.json.

Usage: python scripts/capture/ekris_clean_capture.py
"""
import ctypes, json, os, subprocess, sys, time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

UE_EXE  = r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
PROJECT = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"
# GameModeBase override baked into the clean stage level settings
MAP_URL = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
VAL_ART = Path(r"C:\Users\developer\Documents\Dimwit\artifacts\validation")
WAIT_MAX = 75      # seconds to wait for game window
SETTLE_S = 20.0    # seconds for level/animation to settle
DDC_DIR = Path(os.environ.get("WANEFALL_DDC_DIR", r"D:\WanefallBuild\DDC"))
TEMP_DIR = Path(os.environ.get("WANEFALL_EKRIS_TEMP_DIR", r"D:\WanefallBuild\Temp\EkrisCleanCapture"))

u32 = ctypes.windll.user32


def _launch_command():
    return [
        UE_EXE, PROJECT, MAP_URL,
        "-game", "-windowed", "-ResX=1280", "-ResY=720",
        "-nosound",
        "-DDC=InstalledNoZenLocalFallback",
        f"-LocalDataCachePath={DDC_DIR}",
        "-SharedDataCachePath=None",
    ]


def _launch_env():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    DDC_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TEMP_DIR)
    env["TEMP"] = str(TEMP_DIR)
    env["UE-LocalDataCachePath"] = str(DDC_DIR)
    env["UE-SharedDataCachePath"] = "None"
    return env


def _capture_backend():
    return {
        "tier": "printwindow",
        "title": "WanefallGreybox",
        "proc": "UnrealEditor",
        "reason": "locked-desktop-safe",
    }


def _kill_stray():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match 'UnrealEditor|WanefallGreybox|CrashReport' } | "
         "ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }"],
        capture_output=True, text=True
    )
    time.sleep(2.0)


def _find_window(sub):
    hwnd = None
    def cb(h, _):
        nonlocal hwnd
        n = u32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            if sub.lower() in buf.value.lower() and u32.IsWindowVisible(h):
                hwnd = h
        return True
    F = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u32.EnumWindows(F(cb), 0)
    return hwnd


def _capture_still(hwnd, out_path):
    """Capture a single frame from the game window using PrintWindow."""
    from PIL import Image
    from dimwit.desktop_eyes import DesktopEyes

    backend = _capture_backend()
    eyes = DesktopEyes()
    last_error = None
    for _ in range(4):
        result = eyes.capture_window_printwindow(backend["title"], out_path, proc=backend["proc"])
        if result.get("ok") and Path(out_path).exists() and Path(out_path).stat().st_size > 2000:
            with Image.open(out_path) as img:
                return img.size
        last_error = result.get("error") or result
        time.sleep(0.25)
    raise RuntimeError(f"PrintWindow capture failed: {last_error}")


def _write_centered_crop(src, dst, target_size=512):
    """Crop to the center 60% of width and 70% of height (avoids HUD and black borders),
    then resize to target_size x target_size."""
    from PIL import Image
    img = Image.open(src).convert("RGB")
    w, h = img.size
    # Skip HUD (top 12%) and bottom 5%; keep center 65% horizontally
    r0 = int(h * 0.10)
    r1 = int(h * 0.92)
    c0 = int(w * 0.18)
    c1 = int(w * 0.82)
    crop = img.crop((c0, r0, c1, r1))
    cw, ch = crop.size
    side = max(cw, ch)
    sq = Image.new("RGB", (side, side), (0, 0, 0))
    sq.paste(crop, ((side - cw) // 2, (side - ch) // 2))
    sq = sq.resize((target_size, target_size), Image.LANCZOS)
    sq.save(str(dst))
    print(f"  crop ({c0},{r0})-({c1},{r1}) -> {target_size}px  saved {dst}")


def main():
    print("[ekris_clean_capture] step 1: kill stray editors")
    _kill_stray()

    print("[ekris_clean_capture] step 2: launch CleanStage_01")
    proc = subprocess.Popen(_launch_command(), env=_launch_env())
    print(f"  launched PID {proc.pid}")

    print(f"[ekris_clean_capture] step 3: wait for game window (up to {WAIT_MAX}s)")
    hwnd = None
    deadline = time.time() + WAIT_MAX
    while time.time() < deadline:
        hwnd = _find_window("WanefallGreybox") or _find_window("CleanStage")
        if hwnd:
            print(f"  found window hwnd={hwnd}")
            break
        time.sleep(2.0)
    if not hwnd:
        proc.terminate()
        print("ERROR: game window never appeared")
        sys.exit(1)

    print(f"[ekris_clean_capture] step 4: wait {SETTLE_S}s for level + animation to settle")
    time.sleep(SETTLE_S)
    hwnd = _find_window("WanefallGreybox") or _find_window("CleanStage") or hwnd

    # Bring window to foreground
    u32.ShowWindow(hwnd, 9)
    u32.SetForegroundWindow(hwnd)
    time.sleep(1.0)

    print("[ekris_clean_capture] step 5: capture still frame")
    VAL_ART.mkdir(parents=True, exist_ok=True)
    raw_path = VAL_ART / "char_still.png"
    w, h = _capture_still(hwnd, raw_path)
    print(f"  raw still: {w}x{h} -> {raw_path}")

    focused_path = VAL_ART / "char_still_focused.png"
    _write_centered_crop(str(raw_path), str(focused_path))
    print(f"  focused crop -> {focused_path}")
    (VAL_ART / "char_still_metadata.json").write_text(json.dumps({
        "map_url": MAP_URL,
        "deploy_first": False,
        "toggle_perspective": False,
        "still_frame": str(raw_path),
        "focused_frame": str(focused_path),
        "subject_type": "character_optics_candidate",
    }, indent=2), encoding="utf-8")

    print("[ekris_clean_capture] step 6: kill game")
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True, timeout=10)
    except Exception:
        proc.terminate()
    time.sleep(2.0)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process CrashReportClient -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True
    )

    print("[ekris_clean_capture] DONE")
    print(f"  char_still.png:         {raw_path}")
    print(f"  char_still_focused.png: {focused_path}")


if __name__ == "__main__":
    main()
