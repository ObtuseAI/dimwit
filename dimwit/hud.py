"""Dimwit HUD — one glanceable status of the WHOLE engine: capabilities (eyes/hands/optics/topology/operator),
pipelines, the validation suite verdict, hash-chained ledgers, the handcraft roster, and the open gap list.
Powers `python dimwit.py status` (console) and a self-contained HTML dashboard (closes the observability gap).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
LED = ROOT / "ledger"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default if default is not None else {"error": str(e)}


def capabilities() -> dict:
    caps = {}
    # eyes
    try:
        import mss, pygetwindow  # noqa
        caps["eyes"] = {"ok": True, "capture": "mss+PrintWindow", "windows": _safe(
            lambda: len(__import__("dimwit.desktop_eyes", fromlist=["DesktopEyes"]).DesktopEyes().list_windows()), 0)}
    except Exception as e:
        caps["eyes"] = {"ok": False, "error": str(e)}
    # hands
    try:
        from dimwit import desktop_hands as H
        caps["hands"] = {"ok": True, "live_enabled": H.live_enabled(), "allow_destructive": H.allow_destructive(),
                         "single_editor": _safe(lambda: H.DesktopHands().single_editor(), {})}
    except Exception as e:
        caps["hands"] = {"ok": False, "error": str(e)}
    # optics
    try:
        from dimwit import llm
        caps["optics"] = {"ok": llm.is_configured(), "vision_model": "z-ai/glm-5v-turbo",
                          "configured": llm.is_configured()}
    except Exception as e:
        caps["optics"] = {"ok": False, "error": str(e)}
    # topology
    try:
        from dimwit import topology
        caps["topology"] = {"ok": topology.BLENDER.exists(), **topology.health()}
    except Exception as e:
        caps["topology"] = {"ok": False, "error": str(e)}
    # operator
    caps["operator"] = {"ok": (ROOT / "dimwit" / "live_operator.py").exists()}
    return caps


def pipelines() -> dict:
    try:
        from dimwit.pipelines import list_pipelines
        return {"ok": True, "count": len(list_pipelines()), "names": list_pipelines()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validation() -> dict:
    rp = ART / "validation" / "validation_report.json"
    if not rp.exists():
        return {"verdict": "NOT_RUN", "hint": "python dimwit.py validate"}
    d = _safe(lambda: json.loads(rp.read_text(encoding="utf-8")), {})
    return {"verdict": d.get("suite_verdict"), "counts": d.get("counts"), "total": d.get("total")}


def ledgers() -> dict:
    out = {}
    from dimwit.engine import DimwitLedger
    files = list((LED / "pipelines").glob("*.jsonl")) if (LED / "pipelines").exists() else []
    files += [LED / n for n in ("director.jsonl", "validation.jsonl", "control.jsonl", "operator.jsonl") if (LED / n).exists()]
    for f in files:
        cc = _safe(lambda f=f: DimwitLedger(f).consistency_check(), {})
        out[f.stem] = {"entries": cc.get("entry_count"), "chain_ok": cc.get("chain_ok"), "chained": cc.get("chained")}
    return out


def roster() -> dict:
    rr = ART / "handcraft" / "roster_report.json"
    if rr.exists():
        d = _safe(lambda: json.loads(rr.read_text(encoding="utf-8")), {})
        return {"done": True, "ok_count": d.get("ok_count"), "total": d.get("total")}
    made = list((ART / "handcraft").glob("*/*_handcraft.json")) if (ART / "handcraft").exists() else []
    return {"done": False, "handcrafted_so_far": len(made)}


GAPS = [
    ("G5", "video/temporal animation validator: capability built (eyes.record_window + optics.judge_motion); gates on a live PIE window", "capability-built"),
    ("vfx", "Niagara color is a per-spawn User param, not a baked default (Python edit-time API limit)", "mitigated"),
    ("field-aligned", "instant-meshes backend for field-aligned retopo on all 8 (voxel-quad is the reliable deformation-ready baseline)", "open"),
]
DONE = ["G2 vision-LLM validator", "G3 geometry fallback chain (offline primitive)", "G6 persistent breaker",
        "G7 always-on scheduler", "G8 HUD", "G9 LOD+UCX collision", "G11 repair-with-new-info",
        "G14 all-in-one CLI", "G15 provenance source verification", "topology+handcraft",
        "eyes/hands/optics/operator"]


def snapshot() -> dict:
    return {"capabilities": capabilities(), "pipelines": pipelines(), "validation": validation(),
            "ledgers": ledgers(), "roster": roster(), "open_gaps": [{"id": g, "what": w, "status": s} for g, w, s in GAPS]}


def render_console(s: dict | None = None) -> str:
    s = s or snapshot()                                    # ASCII-only (Windows cp1252 console safe)
    L = ["", "  === DIMWIT -- all-in-one game builder : status ==="]
    c = s["capabilities"]
    def mark(b): return "[OK]" if b else "[--]"
    L.append(f"  CAPABILITIES: eyes {mark(c['eyes'].get('ok'))}  hands {mark(c['hands'].get('ok'))}"
             f"(live={c['hands'].get('live_enabled')})  optics {mark(c['optics'].get('ok'))}"
             f"  topology {mark(c['topology'].get('ok'))}  operator {mark(c['operator'].get('ok'))}")
    L.append(f"  PIPELINES:    {s['pipelines'].get('count')} -- {', '.join(s['pipelines'].get('names', []))}")
    v = s["validation"]
    L.append(f"  VALIDATION:   {v.get('verdict')}  {v.get('counts') or ''} ({v.get('total')} validators)")
    led = s["ledgers"]
    bad = [k for k, x in led.items() if x.get("chain_ok") is False]
    L.append(f"  LEDGERS:      {len(led)} hash-chained : chain_ok={'all' if not bad else 'BROKEN:'+','.join(bad)}")
    r = s["roster"]
    L.append(f"  HANDCRAFT:    roster {'done '+str(r.get('ok_count'))+'/'+str(r.get('total')) if r.get('done') else 'in progress ('+str(r.get('handcrafted_so_far'))+' so far)'}")
    L.append(f"  OPEN GAPS:    {len(s['open_gaps'])} -- " + ", ".join(g['id'] for g in s['open_gaps']))
    L.append("  " + "=" * 50)
    return "\n".join(L)


def render_html(out: Path | None = None) -> str:
    s = snapshot()
    out = out or (Path.home() / "Desktop" / "WANEFALL Build Review" / "dimwit_hud.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    def chip(ok): return f'<span style="color:{"#39d98a" if ok else "#ff5d5d"}">{"●" if ok else "○"}</span>'
    c = s["capabilities"]
    caps = "".join(f'<div class="cap">{chip(c[k].get("ok"))} <b>{k}</b> <span class="d">{json.dumps({kk:vv for kk,vv in c[k].items() if kk not in ("ok","error")})[:80]}</span></div>'
                   for k in c)
    led = "".join(f"<tr><td>{k}</td><td>{x.get('entries')}</td><td>{'✓' if x.get('chain_ok') else '✗'}</td></tr>" for k, x in s["ledgers"].items())
    gaps = "".join(f"<li><code>{g['id']}</code> {g['what']}</li>" for g in s["open_gaps"])
    v = s["validation"]
    html = f"""<!doctype html><meta charset=utf-8><title>Dimwit HUD</title>
<style>body{{background:#0a0d12;color:#dfe7ef;font:14px system-ui;margin:0;padding:24px}}
h1{{color:#27c4ff}}h2{{border-left:3px solid #27c4ff;padding-left:8px;font-size:16px;margin-top:24px}}
.cap{{padding:4px 0}}.d{{color:#8aa0b3;font:12px monospace}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #1e2730;padding:6px 10px;text-align:left}}code{{background:#11161d;padding:2px 6px;border-radius:4px;color:#6fb3d6}}
.big{{font-size:22px;font-weight:700}}</style>
<h1>DIMWIT — all-in-one game builder</h1>
<div class="big">Validation: <span style="color:{'#39d98a' if v.get('verdict')=='PASS' else '#e0b341'}">{v.get('verdict')}</span>
&nbsp; · &nbsp; {s['pipelines'].get('count')} pipelines · {v.get('total')} validators</div>
<h2>Capabilities</h2>{caps}
<h2>Validation</h2><div>{json.dumps(v.get('counts'))}</div>
<h2>Hash-chained ledgers</h2><table><tr><th>ledger</th><th>entries</th><th>chain ok</th></tr>{led}</table>
<h2>Handcraft roster</h2><div>{json.dumps(s['roster'])}</div>
<h2>Open gaps</h2><ul>{gaps}</ul>
<p class="d">Generated by dimwit.hud</p>"""
    out.write_text(html, encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    print(render_console())
