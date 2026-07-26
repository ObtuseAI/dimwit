"""Dimwit ROSTER HANDCRAFT — run the elite-topology -> handcrafted-result pipeline over the WHOLE 8-char roster,
one at a time (RAM-tight), so the in-game characters stop morphing/disfiguring: each dense Hi3D source becomes
clean quad topology + baked NORMAL/AO detail, gated by topology_qa. Writes artifacts/handcraft/roster_report.json.

  python scripts/pipeline/roster_handcraft.py            # all 8
  python scripts/pipeline/roster_handcraft.py 02 05      # just those numbers
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import json
import sys
import time
from pathlib import Path

from dimwit import topology

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
ROSTER = [("01", "vorlax"), ("02", "ekris"), ("03", "zythan"), ("04", "qorin"),
          ("05", "therak"), ("06", "ullio"), ("07", "kelous"), ("08", "nexor")]


def src_for(nn, name):
    for cand in (ART / f"hi3d_{nn}_{name}.glb", ART / f"hi3d_{nn}_{name}_sym.glb", ART / f"hi3d_{name}.glb"):
        if cand.exists():
            return cand
    return None


def main(argv):
    want = set(argv) if argv else {nn for nn, _ in ROSTER}
    results = []
    for nn, name in ROSTER:
        if nn not in want and name not in want:
            continue
        src = src_for(nn, name)
        if not src:
            results.append({"char": f"{nn}_{name}", "ok": False, "error": "no source GLB"})
            print(f"[{nn} {name}] SKIP — no source"); continue
        print(f"[{nn} {name}] handcrafting from {src.name} ...")
        try:
            b = topology.handcraft(str(src), name=f"SM_Char_{nn}_{name}")
            v = (b.get("handcrafted_verdict") or {})
            results.append({"char": f"{nn}_{name}", "ok": b.get("ok"), "method": b.get("method"),
                            "high_faces": b.get("high_faces"),
                            "handcrafted": (b.get("handcrafted_topology") or {}),
                            "verdict_passed": v.get("passed"), "score": v.get("score"),
                            "maps": b.get("maps"), "proof": b.get("proof")})
            print(f"[{nn} {name}] ok={b.get('ok')} quad={(b.get('handcrafted_topology') or {}).get('quad_fraction')} "
                  f"verdict={v.get('passed')}")
        except Exception as e:
            results.append({"char": f"{nn}_{name}", "ok": False, "error": repr(e)})
            print(f"[{nn} {name}] ERROR {e}")
    report = {"roster": results, "ok_count": sum(1 for r in results if r.get("ok")),
              "total": len(results)}
    out = ART / "handcraft" / "roster_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"ROSTER_HANDCRAFT_DONE {report['ok_count']}/{report['total']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
