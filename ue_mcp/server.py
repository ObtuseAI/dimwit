"""Dimwit MCP server (stdio) — the "wired through MCP" surface.

Exposes Dimwit's elite capabilities as MCP tools so Claude / any MCP client can drive them:
  - ue_ping / ue_exec / ue_screenshot / ue_list_actors / ue_save_level  -> forwarded to the LIVE in-editor
    bridge (ue_bridge.py) over localhost:8222, so the running UnrealEditor is driven live.
  - dimwit_brain        -> GLM 5.2 reasoning (planning / design / direction).
  - dimwit_judge_render -> GLM 5V-turbo vision QA on a screenshot (readability + deltas), logged to the ledger.
  - dimwit_tune_lighting-> the recursive GLM loop: screenshot -> judge -> apply deltas live -> re-shoot, until PASS.

Transport: newline-delimited JSON-RPC 2.0 over stdin/stdout (MCP stdio). Logs go to stderr only.

Wire into a client (e.g. Claude) by adding to its MCP config:
  "dimwit": { "command": "python", "args": ["C:/Users/developer/Documents/Dimwit/ue_mcp/server.py"] }
"""
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Dimwit/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ue_mcp"))
import ue_client                                        # noqa: E402
from dimwit import llm                                 # noqa: E402
from scripts.qa import dimwit_light_qa                # noqa: E402

SERVER = {"name": "dimwit", "version": "1.0.0"}
PROTOCOL = "2024-11-05"
MUTATION_ENV = "DIMWIT_UE_MCP_ALLOW_MUTATION"
PAID_MODEL_ENV = "DIMWIT_MCP_ALLOW_PAID_MODEL_CALLS"
MUTATING_TOOLS = {"ue_exec", "ue_save_level", "dimwit_tune_lighting"}
PAID_MODEL_TOOLS = {"dimwit_brain", "dimwit_judge_render", "dimwit_tune_lighting"}


def log(*a):
    print("[dimwit-mcp]", *a, file=sys.stderr, flush=True)


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _policy_block(name: str, env_name: str, reason: str) -> dict:
    return {"ok": False, "blocked": True,
            "error": f"{name} {reason}; set {env_name}=1 in the MCP server environment to opt in",
            "review_ceiling": "PROMOTED_TO_REVIEW"}


# --------------------------------------------------------------------------- lighting delta application
DELTA_CODE = r'''
import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
P, S, D, K, F, EB = {point}, {spot}, {directional}, {skylight}, {fog}, {exposure_bias_add}
ch = {{"point":0,"spot":0,"dir":0,"sky":0,"fog":0,"ppv":0}}
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    if cn=="PointLight":
        c=a.get_component_by_class(unreal.PointLightComponent); c.set_intensity(c.get_editor_property("intensity")*P); ch["point"]+=1
    elif cn=="SpotLight":
        c=a.get_component_by_class(unreal.SpotLightComponent); c.set_intensity(c.get_editor_property("intensity")*S); ch["spot"]+=1
    elif cn=="DirectionalLight":
        c=a.get_component_by_class(unreal.DirectionalLightComponent); c.set_intensity(c.get_editor_property("intensity")*D); ch["dir"]+=1
    elif cn=="SkyLight":
        c=a.get_component_by_class(unreal.SkyLightComponent); c.set_intensity(c.get_editor_property("intensity")*K); ch["sky"]+=1
    elif cn=="ExponentialHeightFog":
        c=a.get_component_by_class(unreal.ExponentialHeightFogComponent); c.set_editor_property("fog_density", c.get_editor_property("fog_density")*F); ch["fog"]+=1
    elif cn=="PostProcessVolume":
        s=a.get_editor_property("settings"); s.set_editor_property("auto_exposure_bias", s.get_editor_property("auto_exposure_bias")+EB); a.set_editor_property("settings", s); ch["ppv"]+=1
result = ch
'''


def _bounded_delta(deltas: dict, name: str, default: float, low: float, high: float) -> float:
    value = deltas.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"lighting delta {name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"lighting delta {name} must be numeric") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"lighting delta {name} is outside [{low}, {high}]")
    return number


def _apply_deltas(d: dict) -> dict:
    if not isinstance(d, dict):
        raise ValueError("lighting deltas must be an object")
    code = DELTA_CODE.format(
        point=_bounded_delta(d, "point_mult", 1.0, 0.25, 4.0),
        spot=_bounded_delta(d, "spot_mult", 1.0, 0.25, 4.0),
        directional=_bounded_delta(d, "directional_mult", 1.0, 0.25, 4.0),
        skylight=_bounded_delta(d, "skylight_mult", 1.0, 0.25, 4.0),
        fog=_bounded_delta(d, "fog_density_mult", 1.0, 0.25, 4.0),
        exposure_bias_add=_bounded_delta(d, "exposure_bias_add", 0.0, -3.0, 3.0))
    return ue_client.call("exec", {"code": code})


def _wait_file(path: str, secs: float = 20.0) -> bool:
    end = time.time() + secs
    last = -1
    while time.time() < end:
        p = Path(path)
        if p.exists():
            sz = p.stat().st_size
            if sz > 0 and sz == last:
                return True
            last = sz
        time.sleep(1.0)
    return Path(path).exists()


def _approved_screenshot(path: object) -> str:
    from ue_mcp.security import confined_screenshot_path
    return str(confined_screenshot_path(path, (ROOT / "frontend_capture", ROOT / "captures")))


def tune_lighting(rounds: int = 3) -> dict:
    shot_dir = ROOT / "frontend_capture"
    shot_dir.mkdir(exist_ok=True)
    traj = []
    for i in range(int(rounds)):
        shot = str(shot_dir / f"tune_{i}.png")
        ue_client.call("screenshot", {"path": shot, "res": [1600, 900]})
        _wait_file(shot, 25)
        v = dimwit_light_qa.qa(shot, "THE HOLD front-end; moody cargo-hold but must stay readable")
        traj.append({"round": i, "verdict": v.get("verdict"), "readability": v.get("readability"),
                     "summary": v.get("summary")})
        if v.get("verdict") == "PASS":
            ue_client.call("save_level")
            return {"ok": True, "passed": True, "rounds_used": i + 1, "trajectory": traj}
        if v.get("deltas"):
            _apply_deltas(v["deltas"])
            ue_client.call("save_level")
    return {"ok": True, "passed": False, "rounds_used": int(rounds), "trajectory": traj}


# --------------------------------------------------------------------------- tools
TOOLS = [
    {"name": "ue_ping", "description": "Ping the live in-editor Unreal bridge (engine version + current level).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ue_exec", "description": "Run arbitrary Python in the LIVE UnrealEditor on the game thread. `unreal` is in scope; set `result` to return a value. Returns stdout + result.",
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "ue_screenshot", "description": "Take a high-res screenshot of the live editor viewport to an absolute path (async; poll the file).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "res": {"type": "array", "items": {"type": "integer"}}}, "required": ["path"]}},
    {"name": "ue_list_actors", "description": "List all actors in the current live level (label + class).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ue_save_level", "description": "Save the current live level.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "dimwit_brain", "description": "GLM 5.2 reasoning (planning, design, technical direction). Returns text.",
     "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "max_tokens": {"type": "integer"}}, "required": ["prompt"]}},
    {"name": "dimwit_judge_render", "description": "GLM 5V-turbo vision QA on a screenshot: readability score + issues + concrete lighting deltas (JSON), logged to the ledger.",
     "inputSchema": {"type": "object", "properties": {"image": {"type": "string"}, "context": {"type": "string"}}, "required": ["image"]}},
    {"name": "dimwit_tune_lighting", "description": "Recursive GLM-judged lighting loop on the LIVE level: screenshot -> GLM 5V judge -> apply deltas live -> re-shoot, up to N rounds or until PASS.",
     "inputSchema": {"type": "object", "properties": {"rounds": {"type": "integer"}}}},
]


def call_tool(name: str, args: dict) -> dict:
    if name in MUTATING_TOOLS and not _enabled(MUTATION_ENV):
        return _policy_block(name, MUTATION_ENV, "is mutating")
    if name in PAID_MODEL_TOOLS and not _enabled(PAID_MODEL_ENV):
        return _policy_block(name, PAID_MODEL_ENV, "can incur paid model usage")
    if name == "ue_ping":
        return ue_client.call("ping")
    if name == "ue_exec":
        return ue_client.call("exec", {"code": args.get("code", "")})
    if name == "ue_screenshot":
        return ue_client.call("screenshot", {"path": _approved_screenshot(args["path"]),
                                              "res": args.get("res", [1600, 900])})
    if name == "ue_list_actors":
        return ue_client.call("list_actors")
    if name == "ue_save_level":
        return ue_client.call("save_level")
    if name == "dimwit_brain":
        r = llm.chat([{"role": "user", "content": args["prompt"]}], max_tokens=args.get("max_tokens", 1500))
        return {"ok": r["ok"], "content": r["content"], "model": r["model"]}
    if name == "dimwit_judge_render":
        return dimwit_light_qa.qa(args["image"], args.get("context", ""))
    if name == "dimwit_tune_lighting":
        return tune_lighting(args.get("rounds", 3))
    return {"ok": False, "error": f"unknown tool '{name}'"}


# --------------------------------------------------------------------------- JSON-RPC / MCP stdio loop
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    log("starting; UE bridge @ 127.0.0.1:8222")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            log("bad json:", e)
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": SERVER}})
        elif method == "notifications/initialized":
            pass  # no response to notifications
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                res = call_tool(name, args)
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "isError": not res.get("ok", True)}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"tool error: {e}"}], "isError": True}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
