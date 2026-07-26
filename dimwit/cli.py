"""Dimwit CLI — one tool to drive the engine. `python -m dimwit <cmd>`:

  perceive  <image>                      measure WANEFALL pixel metrics + style compliance
  intake    <image> [type] [out_spec]    analyse a reference image -> a WANEFALL-native asset spec draft
  generate  <out_dir> [--backend b] [--scale n]   build a REAL mesh (blender|trimesh) + measured metrics
  run                                     process the asset queue through the lifecycle (pixel-truth)
  capture   [hero|lane] [--live]          dry-run (or --live) the real UE capture adapters
  selftest                                run Dimwit self-validation
  opensource                             show the imported open-source registry
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _intake(image: str, asset_type: str, out_spec: str | None) -> dict:
    from .perception import analyze_image, measure_style_compliance
    m = analyze_image(image)
    if not m.get("ok"):
        return m
    # translate MEASURED palette -> WANEFALL-native traits (never a literal copy)
    traits = ["dark_alien", "clean_silhouette"]
    palette = ["dark_alien"]
    if m["teal_fraction"] > 0.03:
        traits.append("teal_wane_energy"); palette.append("teal_wane_energy")
    if m["red_or_orange_fraction"] > 0.01:
        traits.append("red_or_orange_weak_point"); palette.append("red_or_orange_weak_point")
    reject = []
    if m["magenta_fraction"] > 0.01:
        reject.append("magenta (retint -> red weak point + teal Wane)")
    if m["near_black_fraction"] > 0.45 and m["silhouette_contrast"] < 0.12:
        reject.append("near-black blob (raise body value + rim light for separation)")
    spec = {
        "asset_type": asset_type, "source_kind": "image",
        "source_read": "measured palette/contrast from the reference image (NOT copied literally)",
        "wanefall_translation": "dark WANEFALL-native asset; teal Wane accents; red/orange weak point; clean readable silhouette",
        "palette": palette, "traits": sorted(set(traits)),
        "reject": reject,
        "scale_cm": 270 if asset_type in ("hostile_construct_enemy", "target_dummy", "player_armor") else 120,
        "material_slots": ["dark_body", "red_core", "teal_accent"],
        "collision_proxy": "capsule+box", "tri_estimate": 4200,
        "camera_readability": round(min(0.9, m["silhouette_contrast"] * 3.0), 3),
        "gameplay_readability": round(min(0.9, m["silhouette_contrast"] * 2.6 + m["red_or_orange_fraction"] * 4.0), 3),
        "measured_reference": m,
    }
    if out_spec:
        Path(out_spec).write_text(json.dumps(spec, indent=2), encoding="utf-8")
        spec["_written"] = out_spec
    return spec


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "perceive":
        from .perception import analyze_image, measure_style_compliance
        m = analyze_image(rest[0]); print(json.dumps({"metrics": m, "style": measure_style_compliance(m)}, indent=2))
    elif cmd == "intake":
        image = rest[0]; atype = rest[1] if len(rest) > 1 else "hostile_construct_enemy"
        out = rest[2] if len(rest) > 2 else None
        print(json.dumps(_intake(image, atype, out), indent=2))
    elif cmd == "generate":
        from .meshgen import generate
        out_dir = rest[0] if rest else "artifacts/cli_gen"
        backend = "blender"; scale = 270
        if "--backend" in rest: backend = rest[rest.index("--backend") + 1]
        if "--scale" in rest: scale = int(rest[rest.index("--scale") + 1])
        print(json.dumps(generate({"asset_type": "hostile_construct_enemy", "scale_cm": scale}, Path(out_dir), backend), indent=2))
    elif cmd == "run":
        from scripts.pipeline.run_dimwit import main as run_main
        return run_main("dimwit_cli")
    elif cmd == "capture":
        from . import adapters
        which = rest[0] if rest else "hero"
        live = "--live" in rest
        fn = adapters.hero_capture if which == "hero" else adapters.player_camera_capture
        print(json.dumps(fn(dry_run=not live), indent=2))
    elif cmd == "selftest":
        import runpy
        runpy.run_path(str(ROOT / "validators" / "dimwit_self_validation.py"), run_name="__main__")
    elif cmd == "opensource":
        print((ROOT / "config" / "opensource_registry.json").read_text(encoding="utf-8"))
    else:
        print(__doc__); return 2
    return 0
