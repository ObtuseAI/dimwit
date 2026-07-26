"""DIMWIT — the all-in-one elite game-builder front door. One command for every capability:

  python dimwit.py status                 # glanceable engine status (capabilities, pipelines, validation, ledgers, roster)
  python dimwit.py hud                     # write the HTML dashboard (Desktop/WANEFALL Build Review/dimwit_hud.html)
  python dimwit.py health                  # capability health (eyes/hands/optics/topology/operator/brain)
  python dimwit.py validate [--no-ue|--domain D|--list]   # the 105-validator fail-closed suite ("validate everything")
  python dimwit.py handcraft <mesh.glb> [name]            # dense mesh -> clean quad topology + baked maps (handcrafted)
  python dimwit.py roster [NN ...]         # handcraft the whole 8-char roster (fixes the disfigured meshes)
  python dimwit.py eyes <window-title> [out.png]          # capture a live window (PrintWindow, GPU-correct)
  python dimwit.py operate [selftest]      # live operator health / safe see->think self-test
  python dimwit.py director [--dry|--review|--validate]   # autonomous pipeline sweep
  python dimwit.py improve [--execute|--outcomes]         # experiments + operator-owned outcome metrics
  python dimwit.py studio [--execute|--status]            # resumable Blender+Unreal full-game production DAG
  python dimwit.py ecosystem [--write]                    # fail-closed open-source adoption audit (no installs)
  python dimwit.py ide [--port 8765] [--no-open]          # local-first game-production IDE
  python dimwit.py engines [--scan ROOT|--project P ...]  # universal Unreal/Unity/Godot/Defold/Bevy/web factory
  python dimwit.py cross-engine --brief B --receipt A --receipt B  # verify same-brief cross-engine proof
  python dimwit.py mobile [--project P ...]               # Android/iOS build, quality, device, and store gates
  python dimwit.py build                   # meta: validate everything + refresh the HUD + print status
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

HELP = __doc__


def main(argv) -> int:
    cmd = (argv[0] if argv else "status").lower()
    rest = argv[1:]

    if cmd in ("help", "-h", "--help"):
        print(HELP)
        return 0

    if cmd == "status":
        from dimwit import hud
        print(hud.render_console())
        return 0

    if cmd == "hud":
        from dimwit import hud
        print("HUD written ->", hud.render_html())
        return 0

    if cmd == "health":
        from dimwit import hud
        print(json.dumps(hud.capabilities(), indent=2, default=str))
        return 0

    if cmd == "validate":
        from scripts.pipeline import run_validation
        return run_validation.main(rest)

    if cmd == "handcraft":
        if not rest:
            print("usage: dimwit.py handcraft <mesh.glb> [name]")
            return 2
        from dimwit import topology
        b = topology.handcraft(rest[0], rest[1] if len(rest) > 1 else "")
        print(json.dumps({k: b.get(k) for k in ("name", "ok", "method", "high_faces",
              "handcrafted_topology", "handcrafted_verdict", "maps", "proof")}, indent=2, default=str))
        return 0 if b.get("ok") else 1

    if cmd == "roster":
        from scripts.pipeline import roster_handcraft
        return roster_handcraft.main(rest)

    if cmd == "eyes":
        if not rest:
            print("usage: dimwit.py eyes <window-title> [out.png]")
            return 2
        from dimwit.desktop_eyes import DesktopEyes
        out = rest[1] if len(rest) > 1 else str(ROOT / "artifacts" / "eyes" / "cli_capture.png")
        r = DesktopEyes().capture_window(rest[0], out, proc=None)
        print(json.dumps({k: r.get(k) for k in ("ok", "tier", "title", "width", "height", "bytes", "png", "error")}, indent=2))
        return 0 if r.get("ok") else 1

    if cmd == "operate":
        from dimwit.live_operator import Operator
        op = Operator()
        if rest and rest[0] == "selftest":
            print(json.dumps(op.self_test(), indent=2, default=str))
            return 0
        print(json.dumps(op.health(), indent=2, default=str))
        return 0

    if cmd in ("director", "review"):
        from scripts.pipeline import run_director
        return run_director.main((["--review"] if cmd == "review" else []) + rest)

    if cmd == "improve":
        from scripts.pipeline import run_recursive_improvement
        return run_recursive_improvement.main(rest)

    if cmd == "studio":
        from scripts.pipeline import run_studio
        return run_studio.main(rest)

    if cmd in ("ecosystem", "opensource"):
        from scripts.pipeline import run_ecosystem_audit
        return run_ecosystem_audit.main(rest)

    if cmd in ("ide", "studio-ide"):
        from scripts.pipeline import run_studio_ide
        return run_studio_ide.main(rest)

    if cmd in ("engines", "universal", "cross-engine"):
        from scripts.pipeline import run_universal_game_factory
        return run_universal_game_factory.main((["--cross-engine"] if cmd == "cross-engine" else []) + rest)

    if cmd == "mobile":
        from scripts.pipeline import run_mobile_game_factory
        return run_mobile_game_factory.main(rest)

    if cmd == "loop":
        from dimwit import scheduler
        return scheduler.main(rest)

    if cmd == "build":
        # meta "do everything observable": validate everything, refresh HUD, print status
        from dimwit import hud
        from scripts.pipeline import run_validation
        print(">> validating everything (fail-closed suite)…")
        rc = run_validation.main(rest)
        print(">> refreshing HUD →", hud.render_html())
        print(hud.render_console())
        return rc

    print(f"unknown command: {cmd}\n")
    print(HELP)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
