"""Dimwit GEOMETRY backend — Hi3D / Hitem3D cloud API (Sparc3D/Ultra3D models), stdlib only.

This replaces the local Zero123++/InstantMesh path with a cloud SOTA image-to-3D model that
produces crisp armored characters with real heads + PBR textures at 1536³ — the quality the 8GB
local pipeline can't reach. Dimwit just orchestrates: cutout -> submit -> poll -> download GLB.

Flow (docs.hi3d.ai):
  1. POST /open-api/v1/auth/token   Authorization: Basic b64(AK:SK)        -> accessToken (Bearer)
  2. GET  /open-api/v1/balance      Authorization: Bearer <token>          -> totalBalance
  3. POST /open-api/v1/submit-task  multipart: images, model, request_type, resolution, pbr, format -> task_id
  4. GET  /open-api/v1/query-task?task_id=...                              -> state + url (GLB, 1h)
  5. download url -> .glb

Keys from env (HI3D_ACCESS_KEY / HI3D_SECRET_KEY) or config/secrets.json (hi3d_access_key/secret_key).
Tuning in config/hi3d_config.json. Credits: v2.1 pro (1536³ PBR) ~45cr ($0.90)/char.
"""
from __future__ import annotations

import os, io, json, time, base64, uuid, urllib.request, urllib.error
from pathlib import Path

RAIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG = RAIN_ROOT / "config"
BASE = "https://api.hitem3d.ai"

DEFAULTS = {
    "model": "hitem3dv2.1",     # general v2.1 (best). also: hitem3dv2.0, hitem3dv1.5
    "request_type": 3,          # 1=geometry only, 2=texture(staged), 3=geometry+texture in one go
    "resolution": "1536pro",    # v2.1: 1536fast | 1536pro
    "pbr": 1,                   # 1=PBR on (v2.0/v2.1, needs texture)
    "format": 2,                # 1=obj 2=glb 3=stl 4=fbx 5=usdz
    "poll_interval_s": 8,
    "poll_timeout_s": 900,
    "timeout_s": 120,
}
_TOKEN = {"value": None, "ts": 0.0}     # in-process token cache (~tokens are short-lived; refetch hourly)


class Hi3DError(RuntimeError):
    pass


def _cfg() -> dict:
    cfg = dict(DEFAULTS)
    f = CONFIG / "hi3d_config.json"
    if f.exists():
        try: cfg.update(json.loads(f.read_text(encoding="utf-8")))
        except Exception: pass
    return cfg


def _keys() -> tuple[str, str]:
    ak = os.environ.get("HI3D_ACCESS_KEY"); sk = os.environ.get("HI3D_SECRET_KEY")
    if not (ak and sk):
        sf = CONFIG / "secrets.json"
        if sf.exists():
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
                ak = ak or s.get("hi3d_access_key"); sk = sk or s.get("hi3d_secret_key")
            except Exception: pass
    if not (ak and sk):
        raise Hi3DError("NO_HI3D_KEYS: set HI3D_ACCESS_KEY/HI3D_SECRET_KEY or config/secrets.json")
    return ak.strip(), sk.strip()


def is_configured() -> bool:
    try: _keys(); return True
    except Hi3DError: return False


def _req(method, url, headers, data=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise Hi3DError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8','replace')}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise Hi3DError(f"NET: {e}")


def get_token(force=False) -> str:
    if not force and _TOKEN["value"] and (time.time() - _TOKEN["ts"] < 1800):
        return _TOKEN["value"]
    ak, sk = _keys()
    basic = base64.b64encode(f"{ak}:{sk}".encode()).decode()
    r = _req("POST", BASE + "/open-api/v1/auth/token",
             {"Authorization": "Basic " + basic, "Content-Type": "application/json"},
             data=b"{}", timeout=_cfg()["timeout_s"])
    if str(r.get("code")) != "200":
        raise Hi3DError(f"token failed: {r.get('code')} {r.get('msg') or r.get('message')}")
    tok = r["data"]["accessToken"]
    _TOKEN.update(value=tok, ts=time.time())
    return tok


def balance() -> float:
    r = _req("GET", BASE + "/open-api/v1/balance",
             {"Authorization": "Bearer " + get_token(), "Content-Type": "application/json"},
             timeout=_cfg()["timeout_s"])
    return float((r.get("data") or {}).get("totalBalance", -1))


def _multipart(fields: dict, image_path: str) -> tuple[bytes, str]:
    boundary = "----Dimwit" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    img = Path(image_path)
    ext = img.suffix.lower().lstrip(".") or "png"
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"images\"; filename=\"{img.name}\"\r\n"
              f"Content-Type: {ctype}\r\n\r\n".encode())
    buf.write(img.read_bytes()); buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def submit(image_path: str, **over) -> str:
    cfg = _cfg(); cfg.update(over)
    fields = {"model": cfg["model"], "request_type": str(cfg["request_type"]),
              "resolution": cfg["resolution"], "format": str(cfg["format"])}
    if int(cfg["request_type"]) == 3 and cfg["model"] in ("hitem3dv2.0", "hitem3dv2.1"):
        fields["pbr"] = str(cfg["pbr"])
    body, boundary = _multipart(fields, image_path)
    r = _req("POST", BASE + "/open-api/v1/submit-task",
             {"Authorization": "Bearer " + get_token(),
              "Content-Type": f"multipart/form-data; boundary={boundary}"},
             data=body, timeout=cfg["timeout_s"])
    if str(r.get("code")) != "200":
        raise Hi3DError(f"submit failed: {r.get('code')} {r.get('msg') or r.get('message')}")
    return r["data"]["task_id"]


def query(task_id: str) -> dict:
    """One status check (non-blocking). Returns the data dict {state, url, cover_url, ...}."""
    cfg = _cfg()
    r = _req("GET", BASE + f"/open-api/v1/query-task?task_id={urllib.parse.quote(task_id)}",
             {"Authorization": "Bearer " + get_token(), "Content-Type": "application/json"},
             timeout=cfg["timeout_s"])
    d = r.get("data") or {}
    d["_code"] = r.get("code"); d["_msg"] = r.get("msg") or r.get("message")
    return d


def _multipart_multi(fields: dict, image_paths: list) -> tuple[bytes, str]:
    """Multipart with several 'multi_images' file parts (front/back/left/right order) for multi-view-to-3D."""
    boundary = "----Dimwit" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for p in image_paths:
        img = Path(p); ext = img.suffix.lower().lstrip(".") or "png"
        ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"multi_images\"; filename=\"{img.name}\"\r\n"
                  f"Content-Type: {ctype}\r\n\r\n".encode())
        buf.write(img.read_bytes()); buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def submit_multiview(image_paths: list, bit: str, **over) -> str:
    """Multi-view-to-3D. image_paths in order matching the '1's of `bit` (front,back,left,right).
    e.g. bit='1110' -> [front, back, left]; bit='1010' -> [front, left]. Far better/symmetric than single-image."""
    cfg = _cfg(); cfg.update(over)
    assert len(bit) == 4 and bit.count("1") == len(image_paths), "bit must be len-4 and match image count"
    fields = {"model": cfg["model"], "request_type": str(cfg["request_type"]),
              "resolution": cfg["resolution"], "format": str(cfg["format"]), "multi_images_bit": bit}
    if int(cfg["request_type"]) == 3 and cfg["model"] in ("hitem3dv2.0", "hitem3dv2.1"):
        fields["pbr"] = str(cfg["pbr"])
    body, boundary = _multipart_multi(fields, image_paths)
    r = _req("POST", BASE + "/open-api/v1/submit-task",
             {"Authorization": "Bearer " + get_token(),
              "Content-Type": f"multipart/form-data; boundary={boundary}"},
             data=body, timeout=cfg["timeout_s"])
    if str(r.get("code")) != "200":
        raise Hi3DError(f"submit-mv failed: {r.get('code')} {r.get('msg') or r.get('message')}")
    return r["data"]["task_id"]


def poll(task_id: str, on_update=None) -> dict:
    cfg = _cfg(); t0 = time.time()
    while True:
        d = query(task_id)
        state = d.get("state", "?")
        if on_update: on_update(state, round(time.time() - t0))
        if state == "success":
            return d
        if state == "failed":
            raise Hi3DError(f"task failed: code={d.get('_code')} {d.get('_msg')}")
        if time.time() - t0 > cfg["poll_timeout_s"]:
            raise Hi3DError(f"poll timeout after {cfg['poll_timeout_s']}s (last state={state})")
        time.sleep(cfg["poll_interval_s"])


def download(url: str, out_path: str) -> str:
    out = Path(out_path); out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Dimwit/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())
    return str(out)


def generate(image_path: str, out_glb: str, on_update=None, **over) -> dict:
    """Full pipeline: submit cutout -> poll -> download GLB. Returns {ok, out, task_id, cover_url, seconds}."""
    import urllib.parse  # noqa (used in poll)
    t0 = time.time()
    tid = submit(image_path, **over)
    if on_update: on_update("submitted", 0)
    d = poll(tid, on_update=on_update)
    out = download(d["url"], out_glb)
    return {"ok": True, "out": out, "task_id": tid, "cover_url": d.get("cover_url"),
            "seconds": round(time.time() - t0, 1)}


# needed by poll() at module import time
import urllib.parse  # noqa: E402
