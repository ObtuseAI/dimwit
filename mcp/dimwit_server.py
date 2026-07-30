"""Dimwit MCP server (task 10) — exposes Dimwit's engine + capability registry as MCP tools so Claude / any
MCP client can run the whole pipeline by name. Complements ue_mcp/server.py (which drives the live editor):
this one is the in-process brain/engine surface.

Transport: newline-delimited JSON-RPC 2.0 over stdio (logs to stderr only).
Wire in:  "dimwit-engine": { "command": "python", "args": ["C:/Users/developer/Documents/Dimwit/mcp/dimwit_server.py"] }
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dimwit.capabilities import registry          # noqa: E402
from dimwit import spec_author                    # noqa: E402

SERVER = {"name": "dimwit-engine", "version": "1.0.0"}
PROTOCOL = "2024-11-05"
MUTATING_DOMAINS = {"DEVELOP", "EXECUTE"}
MUTATION_ENV = "DIMWIT_MCP_ALLOW_MUTATION"
PAID_MODEL_ENV = "DIMWIT_MCP_ALLOW_PAID_MODEL"
PROVIDER_CAPABILITIES = frozenset({
    "DESIGN/brain.plan_queue",
    "DESIGN/brain.concept",
    "TEST/brain.vision_qa",
    "DEVELOP/brain.light_qa",
})
PROVIDER_IMAGE_ROOTS = tuple(
    (ROOT / name).resolve()
    for name in ("artifacts", "captures", "frontend_capture", "source_art")
)
# MARKET chart-vision verbs accept a local image path. Nothing leaves the machine, but an unconfined path
# argument over MCP is still an arbitrary-file-read primitive, so it gets the same root confinement.
MARKET_IMAGE_CAPABILITIES = frozenset({"MARKET/chart.read", "MARKET/chart.describe_foreign"})


def log(*a):
    print("[dimwit-engine-mcp]", *a, file=sys.stderr, flush=True)


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _mutation_block(tool: str) -> dict:
    return {"ok": False, "blocked": True, "error": f"{tool} is mutating; set {MUTATION_ENV}=1 in the MCP server environment to opt in",
            "review_ceiling": "PROMOTED_TO_REVIEW"}


def _provider_block(tool: str) -> dict:
    return {"ok": False, "blocked": True,
            "error": f"{tool} uses a paid remote provider; set {PAID_MODEL_ENV}=1 in the MCP server environment to opt in",
            "review_ceiling": "PROMOTED_TO_REVIEW"}


def _confined_provider_image(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider image path must be a non-empty string")
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or not any(path.is_relative_to(root) for root in PROVIDER_IMAGE_ROOTS):
        raise ValueError("provider image path is outside Dimwit's approved capture roots")
    return str(path)


def _validate_provider_args(capability: str, args: dict) -> dict:
    """Validate local-file disclosure arguments at the MCP/provider boundary."""
    checked = dict(args)
    if capability == "DEVELOP/brain.light_qa" and "image_path" in checked:
        checked["image_path"] = _confined_provider_image(checked["image_path"])
    if capability == "TEST/brain.vision_qa":
        if "concept_path" in checked:
            checked["concept_path"] = _confined_provider_image(checked["concept_path"])
        if "render_paths" in checked:
            if not isinstance(checked["render_paths"], list):
                raise ValueError("render_paths must be a list")
            checked["render_paths"] = [_confined_provider_image(path) for path in checked["render_paths"]]
    return checked


def _run_asset(asset_id: str) -> dict:
    from scripts.pipeline import run_dimwit as R
    from dimwit.engine import DimwitLedger, run_asset_task
    from dimwit.core import AssetTask
    ledger = DimwitLedger(R.LEDGER)
    spec, evidence = R._load_seed(asset_id)
    task = AssetTask(asset_id=asset_id, asset_type=spec.get("asset_type", "arena_prop"))
    report = run_asset_task(task, spec, evidence, ledger, run_id=f"mcp_{asset_id}")
    R.learn(report, run_id=f"mcp_{asset_id}")
    return report.to_dict()


def _tools() -> list:
    caps = registry.list_capabilities()
    base = [
        {"name": "dimwit_capabilities", "description": "List all registered Dimwit capabilities (DESIGN/DEVELOP/EXECUTE/TEST).",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "dimwit_dispatch", "description": "Call a capability by name with kwargs. Names: " + ", ".join(c.name for c in caps),
         "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "args": {"type": "object"}}, "required": ["name"]}},
        {"name": "dimwit_author_seed", "description": "DESIGN: author a seed asset_spec from a brief (concept->runnable spec).",
         "inputSchema": {"type": "object", "properties": {"asset_id": {"type": "string"}, "asset_type": {"type": "string"}, "brief": {"type": "string"}}, "required": ["asset_id", "asset_type"]}},
        {"name": "dimwit_run_asset", "description": "Run a queued/seeded asset through the full lifecycle + learn step. Returns the run report.",
         "inputSchema": {"type": "object", "properties": {"asset_id": {"type": "string"}}, "required": ["asset_id"]}},
        {"name": "dimwit_rollup", "description": "Cross-tool ledger rollup + trend digest.",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    return base


def call_tool(name: str, args: dict):
    if name == "dimwit_capabilities":
        mutation_enabled = _enabled(MUTATION_ENV)
        provider_enabled = _enabled(PAID_MODEL_ENV)
        return {"ok": True, "mutation_enabled": mutation_enabled,
                "paid_model_enabled": provider_enabled,
                "capabilities": [{"name": c.name, "domain": c.domain, "description": c.description,
                                  "enabled": (c.domain not in MUTATING_DOMAINS or mutation_enabled)
                                             and (c.name not in PROVIDER_CAPABILITIES or provider_enabled)}
                                 for c in registry.list_capabilities()]}
    if name == "dimwit_dispatch":
        cap = registry.get(args["name"])
        if cap.domain in MUTATING_DOMAINS and not _enabled(MUTATION_ENV):
            return _mutation_block(args["name"])
        if args["name"] in PROVIDER_CAPABILITIES and not _enabled(PAID_MODEL_ENV):
            return _provider_block(args["name"])
        call_args = args.get("args") or {}
        if not isinstance(call_args, dict):
            raise ValueError("capability args must be an object")
        if args["name"] in PROVIDER_CAPABILITIES:
            call_args = _validate_provider_args(args["name"], call_args)
        if args["name"] in MARKET_IMAGE_CAPABILITIES and call_args.get("path") is not None:
            call_args["path"] = _confined_provider_image(call_args["path"])
        return {"ok": True, "result": registry.dispatch(args["name"], **call_args)}
    if name == "dimwit_author_seed":
        if not _enabled(MUTATION_ENV):
            return _mutation_block(name)
        return spec_author.author_seed(args["asset_id"], args["asset_type"], args.get("brief", ""))
    if name == "dimwit_run_asset":
        if not _enabled(MUTATION_ENV):
            return _mutation_block(name)
        return _run_asset(args["asset_id"])
    if name == "dimwit_rollup":
        sys.path.insert(0, str(ROOT / "reports"))
        import rollup
        return rollup.rollup()
    return {"ok": False, "error": f"unknown tool '{name}'"}


def send(obj):
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def main():
    log("starting Dimwit engine MCP server")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            log("bad json:", e)
            continue
        mid, method, params = msg.get("id"), msg.get("method"), (msg.get("params") or {})
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": SERVER}})
        elif method == "notifications/initialized":
            pass
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": _tools()}})
        elif method == "tools/call":
            try:
                res = call_tool(params.get("name"), params.get("arguments") or {})
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2, default=str)}], "isError": not (isinstance(res, dict) and res.get("ok", True))}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"tool error: {e}"}], "isError": True}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
