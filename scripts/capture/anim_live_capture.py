"""Anim live capture harness.

Launches WANEFALL in standalone -game mode, deploys from the current command
surface when needed, drives the character with OS-level W-key input, captures
frames showing real locomotion, saves evidence to VAL_ART/anim_video/, writes
anim_live_proof.json.

Run this once before validation to produce fresh evidence for:
  - anim_video_motion_live
  - anim_locomotion_pose_evaluates

The validators read on-disk evidence if no live game window is present.
"""
import ctypes, json, os, subprocess, sys, time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dimwit.pipelines.validation import THRESHOLDS as T
from dimwit.pipelines.character_roster import active_humanoid_characters
from dimwit import perception

# ── paths ──────────────────────────────────────────────────────────────────
UE_EXE   = r"C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
PROJECT  = r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"
DEFAULT_MAP_URL = "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01?game=/Script/WanefallGreybox.WanefallMatchGameMode"
MAP_URL  = os.environ.get(
    "WANEFALL_ANIM_MAP_URL",
    DEFAULT_MAP_URL,
)
VAL_ART  = Path(r"C:\Users\developer\Documents\Dimwit\artifacts\validation")
OUT_DIR  = VAL_ART / "anim_video"
PROOF    = VAL_ART / "anim_live_proof.json"
LOG_SNAPSHOT = VAL_ART / "frontdoor_live_deploy.log"
WAIT_MAX = 75     # seconds to wait for game window
DRIVE_S  = float(os.environ.get("WANEFALL_ANIM_DRIVE_S", "4.0"))    # seconds to hold W
FPS      = float(os.environ.get("WANEFALL_ANIM_FPS", "8"))
DDC_DIR  = Path(os.environ.get("WANEFALL_DDC_DIR", r"D:\WanefallBuild\DDC"))
TEMP_DIR = Path(os.environ.get("WANEFALL_ANIM_TEMP_DIR", r"D:\WanefallBuild\Temp\AnimLiveCapture"))
DEPLOY_FIRST = (
    os.environ.get(
        "WANEFALL_ANIM_DEPLOY_FIRST",
        "1" if ("Wanefall_ModeShell_Prototype_01" in MAP_URL or "Wanefall_Lobby" in MAP_URL) else "0",
    )
    .strip()
    .lower()
    not in {"0", "false", "no", "off"}
)
DEPLOY_WAIT_S = float(os.environ.get("WANEFALL_ANIM_DEPLOY_WAIT_S", "16.0"))
TOGGLE_PERSPECTIVE = os.environ.get("WANEFALL_ANIM_TOGGLE_PERSPECTIVE", "1").strip().lower() not in {"0", "false", "no", "off"}
PERSPECTIVE_WAIT_S = float(os.environ.get("WANEFALL_ANIM_PERSPECTIVE_WAIT_S", "1.5"))
CHARACTER_OPTICS_CANDIDATE = os.environ.get("WANEFALL_ANIM_CHARACTER_OPTICS", "0").strip().lower() in {"1", "true", "yes", "on"}

u32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


KEYEVENTF_KEYUP = 0x0002
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_ENTER = 0x0D
VK_W = 0x57
VK_P = 0x50
SC_ENTER = 0x1C
SC_W = 0x11
SC_P = 0x19


def _launch_command():
    return [
        UE_EXE, PROJECT, MAP_URL,
        "-game", "-windowed", "-ResX=1280", "-ResY=720",
        "-nosound", "-NoScreenMessages",
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


def _input_plan(deploy_first=DEPLOY_FIRST, toggle_perspective=TOGGLE_PERSPECTIVE):
    plan = [{"name": "focus_window", "method": "win32_foreground"}]
    if deploy_first:
        plan.append({"name": "deploy_enter", "method": "sendinput+postmessage", "wait_seconds": DEPLOY_WAIT_S})
        plan.append({"name": "refocus_after_deploy", "method": "win32_foreground"})
    if toggle_perspective:
        plan.append({"name": "toggle_perspective", "method": "sendinput+postmessage", "key": "P", "wait_seconds": PERSPECTIVE_WAIT_S})
    plan.append({"name": "drive_forward", "method": "sendinput+postmessage", "key": "W", "seconds": DRIVE_S})
    return plan


def _subject_type_for_capture(
    deploy_first=DEPLOY_FIRST,
    map_url=MAP_URL,
    toggle_perspective=TOGGLE_PERSPECTIVE,
    character_optics=CHARACTER_OPTICS_CANDIDATE,
):
    if deploy_first or "Wanefall_ModeShell_Prototype_01" in map_url or "Wanefall_Lobby" in map_url:
        return "runtime_ui_or_frontdoor"
    if character_optics and not toggle_perspective:
        return "character_optics_candidate"
    return "runtime_motion_candidate"


def _capture_backend():
    return {
        "tier": "printwindow",
        "title": "WanefallGreybox",
        "proc": "UnrealEditor",
        "reason": "locked-desktop-safe",
    }


def _active_character_metadata():
    chars = active_humanoid_characters(Path(__file__).resolve().parents[2])
    item = chars[0] if chars else {}
    return {
        "subject_character": item.get("key") or "active_primary",
        "asset_name": item.get("asset_name") or "",
        "asset_id": item.get("asset_id") or item.get("asset_name") or "",
        "source_stem": item.get("source_stem") or "",
        "active_roster_policy": "active_humanoid_primary",
    }


def _kill_stray_editors():
    """Kill orphaned UnrealEditor/WanefallGreybox processes that hold the DLL."""
    import subprocess
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match 'UnrealEditor|WanefallGreybox|CrashReport' } | "
         "ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }"],
        capture_output=True, text=True
    )
    time.sleep(2.0)


def _find_window(substring):
    hwnd = None
    def cb(h, _):
        nonlocal hwnd
        n = u32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            if substring.lower() in buf.value.lower() and u32.IsWindowVisible(h):
                hwnd = h
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return hwnd


def _foreground_and_focus(hwnd):
    rect = wintypes.RECT()
    u32.ShowWindow(hwnd, 9)         # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
    time.sleep(1.0)
    u32.GetWindowRect(hwnd, ctypes.byref(rect))
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    u32.SetCursorPos(cx, cy)
    u32.mouse_event(0x0002, 0, 0, 0, 0)    # left down
    u32.mouse_event(0x0004, 0, 0, 0, 0)    # left up
    time.sleep(0.5)


def _key_lparam(scan_code: int, key_up: bool) -> int:
    prev = 1 if key_up else 0
    transition = 1 if key_up else 0
    return 1 | (scan_code << 16) | (prev << 30) | (transition << 31)


def _sendinput_key(vk: int, key_up: bool = False) -> int:
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = _INPUT(type=1, u=_INPUTUNION(ki=_KEYBDINPUT(vk, 0, flags, 0, 0)))
    return u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _post_key(hwnd, vk: int, scan_code: int, key_up: bool = False) -> None:
    u32.PostMessageW(hwnd, WM_KEYUP if key_up else WM_KEYDOWN, vk, _key_lparam(scan_code, key_up))


def _key_down(hwnd, vk: int, scan_code: int) -> None:
    _foreground_and_focus(hwnd)
    _sendinput_key(vk, key_up=False)
    _post_key(hwnd, vk, scan_code, key_up=False)


def _key_up(hwnd, vk: int, scan_code: int) -> None:
    _post_key(hwnd, vk, scan_code, key_up=True)
    _sendinput_key(vk, key_up=True)


def _tap_key(hwnd, vk: int, scan_code: int, taps: int = 1, hold_s: float = 0.08) -> None:
    for _ in range(max(1, taps)):
        _key_down(hwnd, vk, scan_code)
        time.sleep(hold_s)
        _key_up(hwnd, vk, scan_code)
        time.sleep(0.18)


def _hold_key_while_capturing(hwnd, vk: int, scan_code: int, out_dir, seconds: float, fps: float):
    _key_down(hwnd, vk, scan_code)
    try:
        return _capture_region(hwnd, out_dir, seconds=seconds, fps=fps)
    finally:
        _key_up(hwnd, vk, scan_code)


def _capture_region(hwnd, out_dir, seconds, fps):
    """Capture game frames using PrintWindow so a locked desktop cannot yield fake static framebuffer frames."""
    from dimwit.desktop_eyes import DesktopEyes
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    backend = _capture_backend()
    eyes = DesktopEyes()
    interval = 1.0 / fps
    count = max(1, int(seconds * fps))
    for idx in range(count):
        t0 = time.time()
        p = out_dir / f"frame_{idx:03d}.png"
        last_error = None
        for attempt in range(4):
            result = eyes.capture_window_printwindow(backend["title"], p, proc=backend["proc"])
            if result.get("ok") and p.exists() and p.stat().st_size > 2000:
                frames.append(str(p))
                break
            last_error = result.get("error") or result
            time.sleep(0.25)
        else:
            raise RuntimeError(f"PrintWindow capture failed for frame {idx}: {last_error}")
        elapsed = time.time() - t0
        if elapsed < interval and idx < count - 1:
            time.sleep(interval - elapsed)
    return frames


def _write_focused_crop(src: str, dst: str, target_size: int = 512):
    """Crop the game screenshot to the foreground character zone and resize to a square QA image."""
    try:
        import numpy as np
        from PIL import Image
        img = Image.open(src).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        h_img, w_img = arr.shape[:2]

        rf = arr[:, :, 0] / 255.0
        gf = arr[:, :, 1] / 255.0
        bf = arr[:, :, 2] / 255.0
        v = np.maximum(np.maximum(rf, gf), bf)
        mn = np.minimum(np.minimum(rf, gf), bf)
        delta = v - mn
        with np.errstate(divide='ignore', invalid='ignore'):
            s = np.where(v > 1e-6, delta / v, 0.0)

        luminance = (0.2126 * rf) + (0.7152 * gf) + (0.0722 * bf)
        chroma = delta
        vertical_band = np.zeros((h_img, w_img), dtype=bool)
        vertical_band[int(h_img * 0.08):int(h_img * 0.92), :] = True
        foreground = vertical_band & (
            ((luminance > 0.16) & (chroma > 0.035))
            | ((luminance > 0.24) & (s > 0.08))
        )

        def _runs(indices):
            runs = []
            if len(indices) == 0:
                return runs
            start = int(indices[0])
            prev = start
            for value in indices[1:]:
                value = int(value)
                if value != prev + 1:
                    runs.append((start, prev))
                    start = value
                prev = value
            runs.append((start, prev))
            return runs

        char_box = None
        player_roi = np.zeros((h_img, w_img), dtype=bool)
        player_roi[int(h_img * 0.22):int(h_img * 0.86), int(w_img * 0.35):int(w_img * 0.76)] = True
        player_subject = player_roi & (
            ((luminance < 0.30) & (chroma < 0.40))
            | ((chroma > 0.12) & (luminance > 0.25) & (luminance < 0.78))
        )
        col_counts = player_subject.sum(axis=0)
        candidate_cols = np.where(col_counts >= max(16, int(h_img * 0.04)))[0]
        player_runs = []
        for c0, c1 in _runs(candidate_cols):
            width = c1 - c0 + 1
            if width < int(w_img * 0.08) or width > int(w_img * 0.55):
                continue
            submask = player_subject[:, c0:c1 + 1]
            candidate_rows = np.where(submask.sum(axis=1) >= max(8, int(width * 0.10)))[0]
            if len(candidate_rows) == 0:
                continue
            r0 = int(candidate_rows[0])
            r1 = int(candidate_rows[-1])
            height = r1 - r0 + 1
            if height < int(h_img * 0.25):
                continue
            center_penalty = abs(((c0 + c1) * 0.5) - (w_img * 0.52))
            left_intrusion_penalty = max(0.0, (w_img * 0.38) - c0) * 1.4
            score = float(height + width * 0.18 - center_penalty * 0.7 - left_intrusion_penalty)
            player_runs.append((score, c0, c1, r0, r1))

        if player_runs:
            _, c0, c1, r0, r1 = max(player_runs, key=lambda item: item[0])
            rspan = max(1, r1 - r0)
            cspan = max(1, c1 - c0)
            pad_top = max(48, int(rspan * 0.12))
            pad_bottom = max(18, int(rspan * 0.05))
            pad_c = max(46, int(cspan * 0.11))
            c0 = max(0, c0 - pad_c)
            c1 = min(w_img, c1 + pad_c)
            r0 = max(0, r0 - pad_top)
            r1 = min(int(h_img * 0.81), r1 + pad_bottom)
            char_box = (c0, r0, c1, r1)
            print(f"  centered player crop ({c0},{r0})-({c1},{r1})")

        dark_roi = np.zeros((h_img, w_img), dtype=bool)
        dark_roi[int(h_img * 0.28):int(h_img * 0.88), int(w_img * 0.34):int(w_img * 0.78)] = True
        dark_subject = dark_roi & (luminance < 0.22) & (chroma < 0.26)
        col_counts = dark_subject.sum(axis=0)
        min_col_count = max(12, int(h_img * 0.04))
        candidate_cols = np.where(col_counts >= min_col_count)[0]

        dark_runs = []
        for c0, c1 in _runs(candidate_cols):
            width = c1 - c0 + 1
            if width < 24 or width > int(w_img * 0.22):
                continue
            submask = dark_subject[:, c0:c1 + 1]
            min_row_count = max(5, int(width * 0.12))
            candidate_rows = np.where(submask.sum(axis=1) >= min_row_count)[0]
            ccenter = (c0 + c1) * 0.5
            for r0, r1 in _runs(candidate_rows):
                height = r1 - r0 + 1
                if height < int(h_img * 0.18) or r1 < int(h_img * 0.55):
                    continue
                score = float(height) - abs(ccenter - (w_img * 0.52)) * 1.15
                dark_runs.append((score, c0, c1, r0, r1))

        if char_box is None and dark_runs:
            _, c0, c1, r0, r1 = max(dark_runs, key=lambda item: item[0])
            rspan = max(1, r1 - r0)
            cspan = max(1, c1 - c0)
            pad_top = max(42, int(rspan * 0.20))
            pad_bottom = max(20, int(rspan * 0.06))
            pad_c = max(30, int(cspan * 0.30))
            c0 = max(0, c0 - pad_c)
            c1 = min(w_img, c1 + pad_c)
            r0 = max(0, r0 - pad_top)
            r1 = min(h_img, r1 + pad_bottom)
            char_box = (c0, r0, c1, r1)
            print(f"  dark silhouette crop ({c0},{r0})-({c1},{r1})")

        rows = np.where(foreground.any(axis=1))[0]
        cols = np.where(foreground.any(axis=0))[0]

        if len(rows) >= 12 and len(cols) >= 12:
            rspan = int(rows[-1]) - int(rows[0])
            cspan = int(cols[-1]) - int(cols[0])
            if char_box is None and h_img * 0.15 <= rspan <= h_img * 0.88 and cspan <= w_img * 0.70:
                pad_r = max(36, int(rspan * 0.22))
                pad_c = max(36, int(cspan * 0.28))
                r0 = max(0, int(rows[0]) - pad_r)
                r1 = min(h_img, int(rows[-1]) + pad_r)
                c0 = max(0, int(cols[0]) - pad_c)
                c1 = min(w_img, int(cols[-1]) + pad_c)
                char_box = (c0, r0, c1, r1)
                print(f"  foreground crop ({c0},{r0})-({c1},{r1})")

        if char_box is None:
            c0f = int(w_img * 0.25)
            c1f = int(w_img * 0.75)
            r0f = int(h_img * 0.10)
            r1f = int(h_img * 0.88)
            char_box = (c0f, r0f, c1f, r1f)
            print(f"  centered subject fallback crop ({c0f},{r0f})-({c1f},{r1f})")

        c0, r0, c1, r1 = char_box
        crop = img.crop((c0, r0, c1, r1))
        cw, ch = crop.size
        side = max(cw, ch)
        sq = Image.new("RGB", (side, side), (0, 0, 0))
        sq.paste(crop, ((side - cw) // 2, (side - ch) // 2))
        sq = sq.resize((target_size, target_size), Image.LANCZOS)
        sq.save(dst)
        print(f"  focused crop -> {dst}  ({c0},{r0})-({c1},{r1}) -> {target_size}px")
    except Exception as e:
        print(f"  [warn] focused crop failed: {e}")


def main():
    print("[anim_live_capture] step 1: kill stray editors")
    _kill_stray_editors()

    print("[anim_live_capture] step 2: launch WANEFALL runtime")
    proc = subprocess.Popen(_launch_command(), env=_launch_env())
    print(f"  launched PID {proc.pid}")
    print(f"  map_url={MAP_URL}")
    print(f"  input_plan={_input_plan()}")

    print(f"[anim_live_capture] step 3: wait for game window (up to {WAIT_MAX}s)")
    hwnd = None
    deadline = time.time() + WAIT_MAX
    while time.time() < deadline:
        hwnd = _find_window("WanefallGreybox") or _find_window("Wanefall Lobby")
        if hwnd:
            print(f"  found window hwnd={hwnd}")
            break
        time.sleep(2.0)
    if not hwnd:
        proc.terminate()
        print("ERROR: game window never appeared")
        sys.exit(1)

    # Wait for the level to finish streaming in and input to initialize.
    # The SoulCave lobby + character spawn + input binding takes ~25-35s from cold start.
    print("[anim_live_capture] step 4: wait 30s for level stream + input init")
    time.sleep(30.0)
    hwnd = _find_window("WanefallGreybox") or _find_window("Wanefall Lobby") or hwnd

    print("[anim_live_capture] step 5: foreground + focus")
    _foreground_and_focus(hwnd)

    if DEPLOY_FIRST:
        print(f"[anim_live_capture] step 6a: Enter deploy from command surface, wait {DEPLOY_WAIT_S:.1f}s")
        _tap_key(hwnd, VK_ENTER, SC_ENTER, taps=2)
        time.sleep(DEPLOY_WAIT_S)
        hwnd = _find_window("WanefallGreybox") or _find_window("Wanefall Lobby") or hwnd
        _foreground_and_focus(hwnd)

    if TOGGLE_PERSPECTIVE:
        print(f"[anim_live_capture] step 6b: toggle first-person perspective, wait {PERSPECTIVE_WAIT_S:.1f}s")
        _tap_key(hwnd, VK_P, SC_P, taps=1)
        time.sleep(PERSPECTIVE_WAIT_S)
        hwnd = _find_window("WanefallGreybox") or _find_window("Wanefall Lobby") or hwnd
        _foreground_and_focus(hwnd)

    print(f"[anim_live_capture] step 6c: still at runtime spawn, then drive W + capture motion frames")
    # Clear old frames
    for f in OUT_DIR.glob("frame_*.png"):
        f.unlink(missing_ok=True)
    still_name = "frontdoor_still.png" if DEPLOY_FIRST else "char_still.png"
    focused_name = "frontdoor_still_focused.png" if DEPLOY_FIRST else "char_still_focused.png"
    (VAL_ART / still_name).unlink(missing_ok=True)
    (VAL_ART / focused_name).unlink(missing_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Still frame FIRST — character is at spawn point, close to camera, no motion blur.
    # This gives the optics validator a clear close-up of the material (not a tiny figure
    # far inside the cave after walking).
    still_frames = _capture_region(hwnd, OUT_DIR / "still_tmp", seconds=0.5, fps=4)
    still_path = None
    if still_frames:
        import shutil
        still_path = str(VAL_ART / still_name)
        shutil.copy2(still_frames[-1], still_path)   # last frame = most settled render
        print(f"  still frame -> {still_path}")
        _write_focused_crop(still_frames[-1], str(VAL_ART / focused_name))
        still_meta = {
            "map_url": MAP_URL,
            "deploy_first": DEPLOY_FIRST,
            "toggle_perspective": TOGGLE_PERSPECTIVE,
            "still_frame": still_path,
            "focused_frame": str(VAL_ART / focused_name),
            "subject_type": _subject_type_for_capture(),
            **_active_character_metadata(),
        }
        meta_name = "frontdoor_still_metadata.json" if DEPLOY_FIRST else "char_still_metadata.json"
        (VAL_ART / meta_name).write_text(json.dumps(still_meta, indent=2), encoding="utf-8")
    import shutil as _shutil
    _shutil.rmtree(str(OUT_DIR / "still_tmp"), ignore_errors=True)

    print("[anim_live_capture] step 6d: drive W with SendInput+PostMessage while capturing")
    frames = _hold_key_while_capturing(hwnd, VK_W, SC_W, OUT_DIR, seconds=DRIVE_S, fps=FPS)

    print(f"  captured {len(frames)} motion frames")

    if len(frames) < 2:
        proc.terminate()
        print("ERROR: not enough frames captured")
        sys.exit(1)

    # Measure motion
    deltas = [perception.image_delta(frames[i], frames[i+1]) for i in range(len(frames)-1)]
    max_delta  = max(deltas)
    mean_delta = sum(deltas) / len(deltas)
    print(f"  max_delta={max_delta:.5f}  mean_delta={mean_delta:.5f}")

    print("[anim_live_capture] step 7: kill game")
    try:
        import subprocess as sp
        sp.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
               capture_output=True, timeout=10)
    except Exception:
        proc.terminate()
    time.sleep(2.0)
    # Also kill CrashReportClient if it appeared
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process CrashReportClient -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True
    )

    log_snapshot = None
    if DEPLOY_FIRST:
        src_log = Path(PROJECT).parent / "Saved" / "Logs" / "WanefallGreybox.log"
        if src_log.exists():
            import shutil
            LOG_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_log, LOG_SNAPSHOT)
            log_snapshot = str(LOG_SNAPSHOT)
            print(f"[anim_live_capture] log snapshot -> {LOG_SNAPSHOT}")
        else:
            print(f"[anim_live_capture] [warn] runtime log missing for front-door snapshot: {src_log}")

    # Write proof JSON
    proof = {
        "captured_at":  time.time(),
        "map_url":      MAP_URL,
        "deploy_first": DEPLOY_FIRST,
        "input_plan":   _input_plan(),
        "log_snapshot": log_snapshot,
        "frames":       frames,
        "still_frame":  still_path,
        "max_delta":    max_delta,
        "mean_delta":   mean_delta,
        "frame_count":  len(frames),
        "passed":       max_delta >= T["pose_delta_image_floor"],
        "threshold":    T["pose_delta_image_floor"],
    }
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(f"[anim_live_capture] proof written -> {PROOF}")

    if proof["passed"]:
        print(f"[anim_live_capture] PASS  max_delta={max_delta:.5f} >= {T['pose_delta_image_floor']}")
    else:
        print(f"[anim_live_capture] FAIL  max_delta={max_delta:.5f} < {T['pose_delta_image_floor']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
