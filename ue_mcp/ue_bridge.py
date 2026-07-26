"""Dimwit LIVE Unreal bridge — runs INSIDE a running UnrealEditor (via the Python plugin).

Blender-MCP pattern: a localhost socket server (background thread) accepts newline-delimited JSON commands and
marshals them onto the GAME THREAD via a Slate post-tick callback (UE `unreal.*` calls are main-thread only).
An external stdio MCP forwarder (ue_mcp/server.py) sends commands here so Claude / Dimwit can drive the live
editor: run arbitrary unreal python, screenshot the viewport, list/spawn/edit actors, tune lights, save levels.

Start it from the editor (Output Log > Cmd):   py "C:/Users/developer/Documents/Dimwit/ue_mcp/ue_bridge.py"
Or auto-start by placing this project on the UE Python startup path (see ue_mcp/README.md).

Protocol (one JSON object per line, response one JSON object per line):
  -> {"cmd":"exec","params":{"code":"result = len(unreal.EditorActorSubsystem().get_all_level_actors())"}}
  <- {"ok":true,"stdout":"","result":"79"}
"""
import unreal, socket, threading, json, queue, traceback, io, contextlib
from pathlib import Path

try:
    from ue_mcp.security import (
        MAX_EXEC_CHARS, MAX_REQUEST_BYTES, authenticated, bridge_token,
        confined_screenshot_path, screenshot_resolution,
    )
except ImportError:  # Unreal `py <absolute path>` direct execution
    from security import (
        MAX_EXEC_CHARS, MAX_REQUEST_BYTES, authenticated, bridge_token,
        confined_screenshot_path, screenshot_resolution,
    )

HOST, PORT = "127.0.0.1", 8222
ROOT = Path(__file__).resolve().parent.parent
CAPTURE_ROOTS = (ROOT / "frontend_capture", ROOT / "captures")
BRIDGE_TOKEN = bridge_token()

# Guard against double-start across `py` re-execs (the unreal module persists in the editor interpreter).
if getattr(unreal, "_dimwit_bridge_running", False):
    unreal.log_warning("[DimwitUEBridge] already running; ignoring duplicate start")
else:
    unreal._dimwit_bridge_running = True
    _q = queue.Queue()

    def _handle(cmd, params):
        """Runs on the GAME THREAD."""
        if cmd == "ping":
            return {"ok": True, "pong": True, "engine": unreal.SystemLibrary.get_engine_version(),
                    "level": unreal.EditorLevelLibrary.get_editor_world().get_name() if hasattr(unreal, "EditorLevelLibrary") else "?"}
        if cmd == "exec":
            code = params.get("code", "")
            if not isinstance(code, str) or len(code) > MAX_EXEC_CHARS:
                raise ValueError("exec code must be a bounded string")
            buf = io.StringIO()
            g = {"unreal": unreal, "result": None}
            with contextlib.redirect_stdout(buf):
                exec(code, g)
            return {"ok": True, "stdout": buf.getvalue(), "result": repr(g.get("result"))}
        if cmd == "screenshot":
            path = confined_screenshot_path(params.get("path"), CAPTURE_ROOTS)
            w, h = screenshot_resolution(params.get("res", [1600, 900]))
            unreal.AutomationLibrary.take_high_res_screenshot(int(w), int(h), str(path))
            return {"ok": True, "path": str(path), "note": "async; poll for file"}
        if cmd == "list_actors":
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            out = []
            for a in eas.get_all_level_actors():
                out.append({"label": a.get_actor_label(), "class": a.get_class().get_name()})
            return {"ok": True, "count": len(out), "actors": out}
        if cmd == "save_level":
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            return {"ok": bool(les.save_current_level()), "saved": True}
        return {"ok": False, "error": f"unknown cmd '{cmd}'"}

    def _tick(_delta):
        """GAME THREAD: drain the command queue."""
        try:
            while True:
                req, ev = _q.get_nowait()
                try:
                    req["_result"] = _handle(req.get("cmd"), req.get("params", {}) or {})
                except Exception as e:
                    req["_result"] = {"ok": False, "error": str(e), "trace": traceback.format_exc()[-1000:]}
                ev.set()
        except queue.Empty:
            pass

    def _client(conn):
        conn.settimeout(180)
        try:
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > MAX_REQUEST_BYTES:
                    conn.sendall((json.dumps({"ok": False, "error": "request too large"}) + "\n").encode())
                    return
            line = buf.split(b"\n", 1)[0]
            try:
                req = json.loads(line.decode("utf-8"))
            except Exception as e:
                conn.sendall((json.dumps({"ok": False, "error": f"bad json: {e}"}) + "\n").encode())
                return
            if not authenticated(req.get("token"), BRIDGE_TOKEN):
                conn.sendall((json.dumps({"ok": False, "error": "unauthorized"}) + "\n").encode())
                return
            ev = threading.Event()
            _q.put((req, ev))
            ok = ev.wait(timeout=170)
            res = req.get("_result") if ok else {"ok": False, "error": "game-thread timeout"}
            conn.sendall((json.dumps(res) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(8)
        srv.settimeout(1.0)
        unreal.log(f"[DimwitUEBridge] listening on {HOST}:{PORT}")
        while getattr(unreal, "_dimwit_bridge_running", False):
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=_client, args=(conn,), daemon=True).start()
        srv.close()
        unreal.log("[DimwitUEBridge] stopped")

    unreal._dimwit_bridge_tick = unreal.register_slate_post_tick_callback(_tick)
    threading.Thread(target=_serve, daemon=True).start()
    unreal.log("[DimwitUEBridge] started (game-thread marshaling armed)")
