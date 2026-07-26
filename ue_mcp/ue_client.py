"""Tiny client for the in-editor Dimwit UE bridge (ue_bridge.py). Used by the MCP forwarder and for testing.

  python ue_mcp/ue_client.py ping
  python ue_mcp/ue_client.py exec '{"code":"result = 2+2"}'
"""
import socket, json

try:
    from .security import bridge_token
except ImportError:  # direct script execution
    from security import bridge_token

HOST, PORT = "127.0.0.1", 8222


def call(cmd: str, params: dict | None = None, timeout: float = 180.0) -> dict:
    try:
        token = bridge_token()
    except RuntimeError as exc:
        return {"ok": False, "blocked": True, "error": str(exc)}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((HOST, PORT))
        s.sendall((json.dumps({"token": token, "cmd": cmd, "params": params or {}}) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            ch = s.recv(65536)
            if not ch:
                break
            buf += ch
        if not buf:
            return {"ok": False, "error": "empty response (bridge up?)"}
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    except (ConnectionRefusedError, OSError) as e:
        return {"ok": False, "error": f"bridge not reachable on {HOST}:{PORT} ({e}). Is the editor open with the bridge started?"}
    finally:
        s.close()


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "ping"
    p = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    print(json.dumps(call(c, p), indent=2))
