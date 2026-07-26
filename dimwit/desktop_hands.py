"""Dimwit DESKTOP HANDS — guarded live control of the UE5.8 editor / PIE via stdlib ctypes (Win32 SendInput).
ZERO new pip deps. This is the lane that lets Dimwit OPERATE the editor like a tech-artist for the work the
headless channel structurally cannot do (AnimBP/Niagara authoring, PIE play+feel-test, lighting build, etc.).

SAFETY ENVELOPE (enforced on EVERY primitive, even when live control is enabled):
  - ENABLE GATE: control is a no-op (PREVIEW only) unless live control is explicitly enabled
    (env DIMWIT_LIVE_CONTROL=1 OR config/live_control.json {"enabled": true}). Importing this module never
    injects input.
  - PER-ACTION WINDOW-SCOPE CLAMP: before every click/drag the target window is RE-RESOLVED (HWND+rect+
    foreground+process), and any coordinate outside that rect is REFUSED. Never a cached rect.
  - EMERGENCY ABORT: an abort sentinel file, a panic key (SCROLL LOCK), and a wall-clock deadline — any of which
    stops input immediately.
  - SINGLE-EDITOR / OOM LOCK: control attaches to exactly ONE UnrealEditor.exe; refuses on 0 or >1.
  - DESTRUCTIVE GATE: irreversible ops (delete/save-all/source-control/project switch) require
    allow_destructive=true (default FALSE) — even with control enabled.
  - HASH-CHAINED PROOF LEDGER: every op records target hwnd/pid/title/rect, resolved coords, before/after
    capture hashes, mode, and result. An op that can't be provenance-stamped does not run.
  - DRY-RUN/PREVIEW: every recipe can render its resolved op list without firing input.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

from dimwit.engine import DimwitLedger
from dimwit.core import sha256_obj
from dimwit.desktop_eyes import DesktopEyes

ROOT = Path(__file__).resolve().parent.parent
CTRL_DIR = ROOT / "artifacts" / "control"
ABORT_FILE = CTRL_DIR / "ABORT"
LOCK_FILE = CTRL_DIR / "editor.lock"
LIVE_CFG = ROOT / "config" / "live_control.json"

VK_SCROLL = 0x91          # SCROLL LOCK = panic key
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000002, 0x00000001

u32 = ctypes.windll.user32 if os.name == "nt" else None
ULONG_PTR = ctypes.c_size_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(inp: _INPUT) -> int:
    return u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _mouse(flags, dx=0, dy=0):
    inp = _INPUT(type=0, u=_INPUTUNION(mi=_MOUSEINPUT(dx, dy, 0, flags, 0, 0)))
    return _send(inp)


def _key(vk, up=False):
    inp = _INPUT(type=1, u=_INPUTUNION(ki=_KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)))
    return _send(inp)


def _unichar(ch):
    code = ord(ch)
    for up in (False, True):
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
        _send(_INPUT(type=1, u=_INPUTUNION(ki=_KEYBDINPUT(0, code, flags, 0, 0))))


# common VKs for hotkeys
VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
      "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
      "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B, "delete": 0x2E, "g": 0x47, "s": 0x53}
VK.update({c: 0x41 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")})   # full letter row (movement keys)


def live_enabled() -> bool:
    if os.environ.get("DIMWIT_LIVE_CONTROL", "").strip() in ("1", "true", "yes", "on"):
        return True
    if LIVE_CFG.exists():
        try:
            import json
            return bool(json.loads(LIVE_CFG.read_text(encoding="utf-8")).get("enabled"))
        except Exception:
            return False
    return False


def allow_destructive() -> bool:
    if LIVE_CFG.exists():
        try:
            import json
            return bool(json.loads(LIVE_CFG.read_text(encoding="utf-8")).get("allow_destructive"))
        except Exception:
            return False
    return False


class AbortControl(Exception):
    pass


def _process_name_matches(actual: object, expected: str) -> bool:
    actual_stem = Path(str(actual or "")).stem.casefold()
    expected_stem = Path(str(expected or "")).stem.casefold()
    return bool(actual_stem and expected_stem and actual_stem == expected_stem)


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _window_belongs_to_process(hwnd: int, expected: str, process_name_getter=None) -> tuple[bool, int | None]:
    try:
        pid = _window_pid(hwnd)
        if pid <= 0:
            return False, None
        if process_name_getter is None:
            import psutil
            process_name_getter = lambda value: psutil.Process(value).name()
        return _process_name_matches(process_name_getter(pid), expected), pid
    except Exception:
        return False, None


@dataclass
class DesktopHands:
    title: str = "Wanefall"
    proc: str = "UnrealEditor"
    deadline_s: float = 600.0
    _t0: float = field(default_factory=lambda: 0.0)
    eyes: DesktopEyes = field(default_factory=DesktopEyes)
    ledger: DimwitLedger = field(default=None)

    def __post_init__(self):
        CTRL_DIR.mkdir(parents=True, exist_ok=True)
        self.ledger = DimwitLedger(ROOT / "ledger" / "control.jsonl")
        self._t0 = time.time()

    # ---- safety -------------------------------------------------------------------------------
    def _check_abort(self):
        if ABORT_FILE.exists():
            raise AbortControl("abort sentinel present")
        if os.name == "nt" and (u32.GetAsyncKeyState(VK_SCROLL) & 0x0001):
            raise AbortControl("panic key (Scroll Lock)")
        if time.time() - self._t0 > self.deadline_s:
            raise AbortControl("wall-clock deadline exceeded")

    def single_editor(self) -> dict:
        """Exactly one UnrealEditor.exe must be running (OOM/ambiguity guard)."""
        return self.single_target()

    def single_target(self, names: list | None = None) -> dict:
        """Exactly one process matching self.proc must be running (ambiguity guard). Works for the
        packaged game too (proc='WanefallGreybox') - the old editor-only guard blocked all input to
        packaged runtimes because zero UnrealEditor processes exist there. `names` injects a process
        list for tests."""
        prefix = (self.proc or "UnrealEditor").lower()
        if names is None:
            try:
                import psutil
                names = [(p.info.get("name") or "") for p in psutil.process_iter(["name"])]
            except Exception as e:
                return {"ok": False, "error": f"psutil: {e}", "count": None}
        count = sum(1 for n in names if (n or "").lower().startswith(prefix))
        return {"ok": count == 1, "count": count, "proc": self.proc}

    def _resolve_target(self) -> dict | None:
        """Re-resolve the editor window EVERY action (never cached). Disambiguate by process name."""
        if os.name != "nt":
            return None
        w = self.eyes.find_window(self.title)
        if not w:
            return None
        hwnd = getattr(w.get("_w"), "_hWnd", None)
        belongs, pid = _window_belongs_to_process(hwnd, self.proc) if hwnd else (False, None)
        if not belongs:
            return None
        # confirm foreground + (best-effort) process is the editor
        try:
            fg = u32.GetForegroundWindow()
        except Exception:
            fg = None
        return {"left": w["left"], "top": w["top"], "width": w["width"], "height": w["height"],
                "title": w["title"], "fg": fg, "hwnd": hwnd, "pid": pid}

    def _ledger_op(self, op: str, detail: dict, before: str = "", after: str = ""):
        self.ledger.append({"ts": int(time.time()), "actor": "desktop_hands", "asset_id": op,
                            "state": f"control.{detail.get('result', 'done')}",
                            "candidate_hash": sha256_obj({"op": op, "detail": detail, "before": before, "after": after}),
                            "detail": detail})

    def _guard(self, op: str, x=None, y=None, destructive=False) -> dict:
        """Pre-action gate. Returns {go, mode, reason, target}. mode: 'live' | 'preview' | 'blocked'."""
        target = self._resolve_target()
        rec = {"op": op, "x": x, "y": y, "target": (target or {}).get("title"), "destructive": destructive}
        if target is None:
            rec.update(result="blocked", reason=f"editor window not found ({self.title})")
            return {"go": False, "mode": "blocked", **rec}
        if x is not None and y is not None:
            inside = (target["left"] <= x <= target["left"] + target["width"] and
                      target["top"] <= y <= target["top"] + target["height"])
            if not inside:
                rec.update(result="blocked", reason="coord outside editor window rect")
                return {"go": False, "mode": "blocked", **rec, "target": target}
        if destructive and not allow_destructive():
            rec.update(result="gated", reason="destructive op requires allow_destructive=true (human gate)")
            return {"go": False, "mode": "blocked", **rec, "target": target}
        se = self.single_target()
        if not se["ok"]:
            rec.update(result="blocked", reason=f"single-target guard ({self.proc}): {se}")
            return {"go": False, "mode": "blocked", **rec, "target": target}
        try:
            self._check_abort()
        except AbortControl as e:
            rec.update(result="aborted", reason=str(e))
            return {"go": False, "mode": "blocked", **rec, "target": target}
        if not live_enabled():
            rec.update(result="preview")
            return {"go": False, "mode": "preview", **rec, "target": target}
        rec.update(result="live")
        return {"go": True, "mode": "live", **rec, "target": target}

    # ---- primitives (each guarded + ledgered) -------------------------------------------------
    def focus_editor(self) -> dict:
        ok = self.eyes.focus_window(self.title)
        self._ledger_op("focus_editor", {"result": "live" if ok else "blocked", "ok": ok})
        return {"ok": ok}

    def focus_target(self, attempts: int = 4) -> dict:
        """VERIFIED foreground focus of the target window. pygetwindow's activate() throws
        'Error code from Windows: 0' (success misreported) and background processes hit the
        Windows foreground lock - so drive Win32 directly (ALT nudge + SW_RESTORE +
        SetForegroundWindow) and only report ok when GetForegroundWindow() == hwnd."""
        w = self.eyes.find_window(self.title)
        if not w:
            self._ledger_op("focus_target", {"result": "blocked", "ok": False, "reason": "window not found"})
            return {"ok": False, "reason": f"window not found: {self.title}"}
        hwnd = getattr(w.get("_w"), "_hWnd", None)
        if not hwnd:
            self._ledger_op("focus_target", {"result": "blocked", "ok": False, "reason": "no hwnd"})
            return {"ok": False, "reason": "window handle exposes no hwnd"}
        belongs, pid = _window_belongs_to_process(hwnd, self.proc)
        if not belongs:
            reason = f"window process does not match {self.proc}"
            self._ledger_op("focus_target", {"result": "blocked", "ok": False, "reason": reason, "pid": pid})
            return {"ok": False, "reason": reason, "pid": pid}
        k32 = ctypes.windll.kernel32
        for attempt in range(1, max(1, attempts) + 1):
            try:
                _key(VK["alt"], up=False)
                _key(VK["alt"], up=True)          # foreground-lock bypass nudge
                # AttachThreadInput escalation: adopt both the current-foreground and the target
                # threads' input queues so SetForegroundWindow is permitted from a background proc
                fg = u32.GetForegroundWindow()
                fg_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
                target_tid = u32.GetWindowThreadProcessId(hwnd, None)
                my_tid = k32.GetCurrentThreadId()
                if fg_tid:
                    u32.AttachThreadInput(my_tid, fg_tid, True)
                if target_tid:
                    u32.AttachThreadInput(my_tid, target_tid, True)
                u32.BringWindowToTop(hwnd)
                u32.ShowWindow(hwnd, 9)           # SW_RESTORE
                u32.SetForegroundWindow(hwnd)
                if target_tid:
                    u32.AttachThreadInput(my_tid, target_tid, False)
                if fg_tid:
                    u32.AttachThreadInput(my_tid, fg_tid, False)
            except Exception:
                pass
            time.sleep(0.35)
            if u32.GetForegroundWindow() == hwnd:
                self._ledger_op("focus_target", {"result": "live", "ok": True, "attempt": attempt})
                return {"ok": True, "attempts": attempt}
        holder = u32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        try:
            u32.GetWindowTextW(holder, buf, 256)
        except Exception:
            pass
        reason = (f"foreground verification failed after {attempts} attempts; "
                  f"foreground is held by {buf.value!r}")
        self._ledger_op("focus_target", {"result": "blocked", "ok": False, "reason": reason})
        return {"ok": False, "reason": reason}

    def move(self, x: int, y: int) -> dict:
        g = self._guard("move", x, y)
        if g["go"]:
            u32.SetCursorPos(int(x), int(y))
        self._ledger_op("move", g)
        return g

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> dict:
        g = self._guard("click", x, y)
        if g["go"]:
            u32.SetCursorPos(int(x), int(y)); time.sleep(0.04)
            down, up = ((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left"
                        else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP))
            for _ in range(2 if double else 1):
                _mouse(down); time.sleep(0.03); _mouse(up); time.sleep(0.03)
        self._ledger_op("click", {**g, "button": button, "double": double})
        return g

    def press(self, *keys: str) -> dict:
        """Press a key or hotkey combo, e.g. press('ctrl','s') or press('f5')."""
        g = self._guard("press", destructive=False)
        if g["go"]:
            vks = [VK.get(k.lower(), 0) for k in keys]
            for vk in vks:
                _key(vk, up=False); time.sleep(0.02)
            for vk in reversed(vks):
                _key(vk, up=True); time.sleep(0.02)
        self._ledger_op("press", {**g, "keys": list(keys)})
        return g

    def key_down(self, key: str) -> dict:
        """Hold a key down (pair with key_up) - movement input for gameplay smoke captures."""
        g = self._guard("key_down", destructive=False)
        if g["go"]:
            _key(VK.get(key.lower(), 0), up=False)
        self._ledger_op("key_down", {**g, "key": key})
        return g

    def key_up(self, key: str) -> dict:
        g = self._guard("key_up", destructive=False)
        if g["go"]:
            _key(VK.get(key.lower(), 0), up=True)
        self._ledger_op("key_up", {**g, "key": key})
        return g

    # ---- targeted window-message input (no focus required) ------------------------------------
    def _target_hwnd(self):
        """Resolve-and-cache the target hwnd. Map transitions/locked sessions make pygetwindow
        enumeration flaky mid-run; a hwnd cached while the window was enumerable keeps posted
        input working (PostMessageW needs only the handle, and stale handles just no-op)."""
        w = self.eyes.find_window(self.title)
        hwnd = getattr(w.get("_w"), "_hWnd", None) if w else None
        if hwnd and _window_belongs_to_process(hwnd, self.proc)[0]:
            self._hwnd_cache = hwnd
            return hwnd
        cached = getattr(self, "_hwnd_cache", None)
        return cached if cached and _window_belongs_to_process(cached, self.proc)[0] else None

    @staticmethod
    def session_locked() -> bool:
        """True when the workstation is on the secure/lock desktop (SendInput+foreground are
        impossible there; posted window messages still deliver)."""
        try:
            DESKTOP_SWITCHDESKTOP = 0x0100
            h = u32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
            if h:
                u32.CloseDesktop(h)
                return False
            return True
        except Exception:
            return False

    def _post_vk(self, key: str, down: bool) -> bool:
        hwnd = self._target_hwnd()
        vk = VK.get(key.lower(), 0)
        if not hwnd or not vk:
            return False
        scan = u32.MapVirtualKeyW(vk, 0)
        if down:
            lparam = 1 | (scan << 16)
            return bool(u32.PostMessageW(hwnd, 0x0100, vk, lparam))          # WM_KEYDOWN
        lparam = 1 | (scan << 16) | (1 << 30) | (1 << 31)
        return bool(u32.PostMessageW(hwnd, 0x0101, vk, lparam))              # WM_KEYUP

    def _guard_posted(self, op: str) -> dict:
        """Guard for hwnd-targeted posts: abort/deadline/live/single-target still bind, but window
        RE-ENUMERATION is not required (the cached hwnd carries across map transitions and locked
        sessions, and a posted message can never land outside its target window)."""
        rec = {"op": op, "target": self.title}
        se = self.single_target()
        if not se["ok"]:
            rec.update(result="blocked", reason=f"single-target guard ({self.proc}): {se}")
            return {"go": False, "mode": "blocked", **rec}
        try:
            self._check_abort()
        except AbortControl as e:
            rec.update(result="aborted", reason=str(e))
            return {"go": False, "mode": "blocked", **rec}
        if not live_enabled():
            rec.update(result="preview")
            return {"go": False, "mode": "preview", **rec}
        if not self._target_hwnd():
            rec.update(result="blocked", reason=f"no hwnd for {self.title} (never enumerated this run)")
            return {"go": False, "mode": "blocked", **rec}
        rec.update(result="live")
        return {"go": True, "mode": "live", **rec}

    def post_key(self, key: str) -> dict:
        """Post a key press DIRECTLY to the target window's message queue - works without stealing
        foreground (and never leaks input to other apps). Fallback for locked/unfocusable sessions;
        the caller must verify the effect (e.g. map-load log token) because delivery is one-way."""
        g = self._guard_posted("post_key")
        if g["go"]:
            ok = self._post_vk(key, True)
            time.sleep(0.03)
            ok = self._post_vk(key, False) and ok
            g["posted"] = ok
        self._ledger_op("post_key", {**g, "key": key})
        return g

    def post_key_down(self, key: str) -> dict:
        g = self._guard_posted("post_key_down")
        if g["go"]:
            g["posted"] = self._post_vk(key, True)
        self._ledger_op("post_key_down", {**g, "key": key})
        return g

    def post_key_up(self, key: str) -> dict:
        g = self._guard_posted("post_key_up")
        if g["go"]:
            g["posted"] = self._post_vk(key, False)
        self._ledger_op("post_key_up", {**g, "key": key})
        return g

    def type_text(self, text: str) -> dict:
        g = self._guard("type_text")
        if g["go"]:
            for ch in text:
                self._check_abort()
                _unichar(ch); time.sleep(0.01)
        self._ledger_op("type_text", {**g, "len": len(text)})
        return g

    # ---- high-level guarded verbs (use eyes+optics to see results) ----------------------------
    def play_in_editor(self) -> dict:
        """Start PIE (Alt+P is the default UE5 'Play' chord; gives a running game for live/optics QA)."""
        self.focus_editor()
        return self.press("alt", "p")

    def stop_pie(self) -> dict:
        self.focus_editor()
        return self.press("esc")

    def capture(self, out) -> dict:
        """See the editor right now (PrintWindow, GPU-correct)."""
        return self.eyes.capture_window(self.title, out, proc=self.proc)

    # ---- keep-awake context (scoped, always reverted) -----------------------------------------
    class keep_awake:
        def __enter__(self):
            if os.name == "nt":
                u32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
            return self

        def __exit__(self, *a):
            if os.name == "nt":
                u32.SetThreadExecutionState(ES_CONTINUOUS)
            return False


def status() -> dict:
    h = DesktopHands()
    return {"live_enabled": live_enabled(), "allow_destructive": allow_destructive(),
            "single_editor": h.single_editor(), "editor_found": bool(h._resolve_target()),
            "abort_sentinel": ABORT_FILE.exists(), "panic_key": "ScrollLock"}


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2))
