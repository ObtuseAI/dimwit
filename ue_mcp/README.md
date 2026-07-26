# Dimwit Live Unreal MCP

Drive a **live UnrealEditor** (and Dimwit's GLM 5.2 brain + GLM 5V eyes) over MCP — the same pattern as your
Blender MCP. Claude / any MCP client calls tools → a stdio forwarder → a localhost socket → an in-editor Python
server that marshals every call onto the UE game thread.

```
MCP client (Claude)  ──stdio JSON-RPC──►  ue_mcp/server.py  ──tcp:8222──►  ue_bridge.py (inside UnrealEditor)
                                              │                                   │ (game-thread via slate tick)
                                              ├─ GLM 5.2  (dimwit_brain)         └─ unreal.* (exec/screenshot/...)
                                              └─ GLM 5V   (dimwit_judge_render)
```

## Components
| File | Role |
|---|---|
| `ue_mcp/ue_bridge.py` | In-editor socket server (game-thread marshaled). The elite UE control surface. |
| `Content/Python/init_unreal.py` (in the UE project) | Auto-starts the bridge on every editor launch. |
| `ue_mcp/ue_client.py` | Tiny socket client (used by the forwarder + for testing). |
| `ue_mcp/server.py` | The stdio **MCP server** — exposes the tools below. |
| `scripts/qa/dimwit_light_qa.py` | GLM 5V render QA (readability + lighting deltas → ledger). |
| `config/llm_config.json` | GLM 5.2 (text) + GLM 5V-turbo (vision) over OpenRouter. |

## Tools exposed
- `ue_ping` — engine + current level
- `ue_exec` — run arbitrary `unreal` Python live on the game thread (universal power tool)
- `ue_screenshot` — high-res viewport capture
- `ue_list_actors` / `ue_save_level`
- `dimwit_brain` — GLM 5.2 reasoning (plan / design / direction)
- `dimwit_judge_render` — GLM 5V vision QA (score + deltas, logged to `ledger/light_qa.jsonl`)
- `dimwit_tune_lighting` — recursive GLM-judged loop: screenshot → judge → apply deltas live → re-shoot until PASS

## Wire it into a client
The editor must be open (the bridge auto-starts via `init_unreal.py`). Then add to your MCP client config:

```json
{
  "mcpServers": {
    "dimwit": { "command": "python", "args": ["C:/Users/developer/Documents/Dimwit/ue_mcp/server.py"] }
  }
}
```
- **Claude Code**: put this in `.mcp.json` at the project root (or `claude mcp add dimwit python C:/Users/developer/Documents/Dimwit/ue_mcp/server.py`).
- **Claude Desktop**: merge into `claude_desktop_config.json`.

## Quick test (no client needed)
```bash
python ue_mcp/ue_client.py ping
python ue_mcp/ue_client.py exec '{"code":"result = len(unreal.EditorActorSubsystem().get_all_level_actors())"}'
```

## Notes
- Port `8222`, localhost only. Guarded against double-start.
- `ue_exec` runs on the game thread (safe for `unreal.*`); long ops block that frame.
- Screenshots are async — poll the file (the forwarder does this in `dimwit_tune_lighting`).
