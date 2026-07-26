"""Close the recursive loop (task 6).

Today the mutation loop re-scores the SAME frozen evidence, so a measured failure can never be fixed by
iterating. `render_fn(cand)` regenerates EVIDENCE for each candidate so the next score sees NEW geometry/pixels.

Degrade-safe by design: if a renderer is unavailable, render_fn returns the candidate unchanged and the loop
falls back to today's declared-only behavior (same guard pattern as `engine._HAS_PERCEPTION`). It NEVER
fabricates hero/player-camera contact sheets — pixel-truth gates only ever see evidence that was really
rendered (the live-UE capture path stays conservative until a capture map/commandlet is registered).
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def _regen_mesh(cand) -> bool:
    """Regenerate real geometry from the candidate spec via the headless trimesh backend."""
    try:
        from ..meshgen import generate_trimesh
    except Exception:
        return False
    try:
        out = Path(tempfile.gettempdir()) / "dimwit_render" / str(cand.candidate_id)
        meta = generate_trimesh(cand.spec, out)
        glb = (meta.get("exports") or {}).get("glb")
        if glb:
            cand.spec["mesh_ref"] = glb
            cand.spec.setdefault("material_slots", meta.get("material_slots", []))
            cand.evidence["mesh"] = glb
        measured = meta.get("measured") or {}
        if measured.get("triangles"):
            cand.spec["tri_estimate"] = int(measured["triangles"])
        cand.evidence["mesh_metrics"] = measured
        return True
    except Exception:
        return False


def _regen_ue_capture(cand) -> bool:
    """Regenerate hero + player-camera captures via the live UE bridge — only if it is actually reachable.
    Conservative for V1: returns False (no fabricated pixel evidence) until a capture map/commandlet is wired."""
    try:
        from ue_mcp import ue_client
        if not ue_client.call("ping", timeout=3).get("ok"):
            return False
    except Exception:
        return False
    return False


def make_render_fn(use_mesh: bool = True, use_ue: bool = False):
    """Build a render_fn for recursive_mutation_loop. use_mesh=headless geometry regen; use_ue=live capture."""
    def render_fn(cand):
        if use_mesh:
            _regen_mesh(cand)
        if use_ue:
            _regen_ue_capture(cand)
        return cand
    return render_fn
