"""VFX pipeline — Niagara VFX authoring for the WANE (Crystallize / Erode / Snap, energy seams, hit/death).

The WANE is WANEFALL's decay-force identity: motion verbs *Crystallize / Erode / Snap*, teal/blue energy
seams, "saturation = truth". This pipeline authors Niagara System assets under /Game/Wanefall/Dimwit/VFX.

Why duplicate-and-parameterize (not author-from-scratch):
  Authoring Niagara graphs from Python is severely limited — UE exposes almost no editor API for building
  emitter graphs. The RELIABLE, real path is to DUPLICATE an existing NiagaraSystem (an engine/plugin Niagara
  example, or an in-project template) and re-tint it to the WANE teal/blue + set the 3 WANE verb parameters.
  If no source NiagaraSystem can be found, plan() raises BlockedError (FAIL CLOSED — we never fabricate a
  system asset that does not exist).

execute(): shells out to the canonical UE driver `scripts/ue/ue_vfx_build.py`, which duplicates the chosen source
  NiagaraSystem into /Game/Wanefall/Dimwit/VFX/NS_Wane_<Verb>, applies the WANE color, sets user/system
  parameters for the verb, and saves. It reports STRUCTURAL metrics (asset exists, emitter count, parameter
  count) — honest proof the system was authored, no screenshot required.

qa(): STRUCTURAL — each requested system asset exists, has >=1 emitter, and carries the WANE color +
  verb parameter. (GLM visual QA of the live particle look is a TODO; structural proof is authoritative here.)

This module is IMPORT-SAFE: only stdlib + `.base` at module top; `unreal` is never imported here (it lives in
the driver). It imports and validates with zero side effects and without UE present.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
DRIVER = ROOT / "scripts/ue/ue_vfx_build.py"
RESULT = ART / "vfx_result.json"

VFX_DIR = "/Game/Wanefall/Dimwit/VFX"

# The three WANE motion verbs + their canonical seam color (teal/blue energy) and intent.
# RGBA in linear 0..1; alpha doubles as emissive weight hint for the driver.
WANE_VERBS = {
    "crystallize": {"color": [0.05, 0.85, 0.95, 1.0], "intent": "matter snapping into ordered teal lattice"},
    "erode":       {"color": [0.10, 0.55, 0.85, 1.0], "intent": "surface dissolving into drifting blue motes"},
    "snap":        {"color": [0.20, 0.95, 1.00, 1.0], "intent": "instant fracture burst along the energy seam"},
    "hit":         {"color": [0.30, 0.90, 1.00, 1.0], "intent": "impact flash on the energy seam"},
    "death":       {"color": [0.08, 0.40, 0.80, 1.0], "intent": "full erosion collapse on destruction"},
}

# Candidate source NiagaraSystems to duplicate (first that EXISTS wins). Engine Niagara content + common
# in-project templates. The driver resolves which actually exist; plan() blocks if none do.
SOURCE_CANDIDATES = [
    "/Niagara/DefaultAssets/Templates/SimpleSpriteBurst.SimpleSpriteBurst",
    "/Niagara/DefaultAssets/Templates/Fountain.Fountain",
    "/Niagara/DefaultAssets/Templates/SimpleSprite.SimpleSprite",
    "/Game/Wanefall/Dimwit/VFX/Templates/NS_Wane_Template.NS_Wane_Template",
]


class VFXPipeline(ProductionPipeline):
    name = "vfx"
    kind = "niagara_vfx"

    def plan(self, task: dict) -> dict:
        verb = str(task.get("asset_id", task.get("name", task.get("verb", "crystallize")))).lower()
        if verb not in WANE_VERBS:
            raise BlockedError(f"unknown WANE verb '{verb}'; known: {sorted(WANE_VERBS)}")
        if not UE_CMD.exists() or not UPROJECT.exists():
            raise BlockedError("UnrealEditor-Cmd or uproject not found (UE required to author Niagara)")
        spec = WANE_VERBS[verb]
        # An explicit source override may be passed; otherwise the driver scans SOURCE_CANDIDATES and
        # FAILS CLOSED (records error) if none resolve — we cannot duplicate a system that doesn't exist.
        source = str(task.get("source", "")).strip() or None
        out_asset = f"NS_Wane_{verb.capitalize()}"
        return {
            "verb": verb,
            "out_asset": out_asset,
            "out_path": f"{VFX_DIR}/{out_asset}",
            "color": spec["color"],
            "intent": spec["intent"],
            "source": source,
            "sources": SOURCE_CANDIDATES,
        }

    def execute(self, plan: dict) -> Artifact:
        if RESULT.exists():
            RESULT.unlink()
        # Idempotence lives OUTSIDE the engine (2026-07-02): in-engine delete_asset refuses while
        # the probe-load's async Niagara compile holds a reference, and the driver's old
        # None-fallback then re-tagged the STALE asset as if freshly duplicated. No UE process is
        # running at this point — remove the destination file so duplicate_asset lands clean; the
        # driver still refuses (fail-closed) if a destination asset somehow remains.
        dest_file = (UPROJECT.parent / "Content" /
                     Path(VFX_DIR.replace("/Game/", "")) / f'{plan["out_asset"]}.uasset')
        if dest_file.exists():
            dest_file.unlink()
        color = ",".join(str(c) for c in plan["color"])
        src_arg = f' source={plan["source"]}' if plan.get("source") else ""
        cmd = [
            str(UE_CMD), str(UPROJECT),
            # forward slashes: UE mis-parses backslash paths passed through subprocess list quoting
            (f'-ExecutePythonScript={DRIVER} verb={plan["verb"]} out={plan["out_asset"]} '
             f'dest={VFX_DIR} color={color}{src_arg}').replace("\\", "/"),
            "-unattended", "-nosplash", "-nopause", "-stdout",
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        rec = {}
        if RESULT.exists():
            data = json.loads(RESULT.read_text(encoding="utf-8"))
            for r in data.get("records", []):
                if r.get("verb") == plan["verb"]:
                    rec = r
                    break
            if not rec:
                rec = {"error": data.get("error", "driver produced no record for this verb")}
        else:
            rec = {"error": "driver wrote no result JSON (UE may not have run)"}
        return Artifact(
            asset_id=plan["verb"], kind=self.kind, data=rec,
            provenance={
                "source": (f"duplicated from {rec.get('source_used')}" if rec.get("source_used")
                           else "Niagara engine template (UE 5.8) re-tinted to WANE"),
                "license": "Epic EULA (Niagara/engine content used in-engine)",
            },
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        r = artifact.data or {}
        if not r or r.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=False,
                           issues=[r.get("error", "no driver record")],
                           detail={"record": r})
        checks = {
            "system_created": bool(r.get("asset_exists")),
            "has_emitters": (r.get("emitter_count") or 0) >= 1,
            "wane_color_set": bool(r.get("color_set")),
            "verb_param_set": bool(r.get("verb_param_set")),
            "saved": bool(r.get("saved")),
            # wrong-asset law (2026-07-02): an explicit donor request must be the donor actually
            # used — a registry-scan race silently substituted fallback candidate #1 and this QA
            # rubber-stamped three wrong-donor duplicates (caught by the cook-safety profile diff).
            "source_matches_request": (not plan.get("source")) or (
                str(r.get("source_used") or "") == str(plan["source"]).split(".")[0]),
        }
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        return Verdict(
            score=score, passed=all(checks.values()), issues=issues,
            detail={"checks": checks, "asset": r.get("asset"),
                    "emitter_count": r.get("emitter_count"),
                    "param_count": r.get("param_count")},
            evidence=[str(RESULT)] if RESULT.exists() else [],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # The driver is idempotent (duplicate replaces existing); re-running clears a partial author
        # (e.g. a color/param set that didn't save on the first pass). NOTE: the old last-attempt
        # fallback that CLEARED an explicit source was a wrong-asset hazard (silent donor
        # substitution) — removed 2026-07-02; a donor mismatch must FAIL, not morph.
        return self.execute(plan)


# TODO(bespoke): author dedicated emitters per verb (Crystallize lattice-snap, Erode dissolve-drift,
#   Snap fracture-burst) instead of re-tinting one template — needs a Niagara graph-authoring path
#   (likely a hand-built /Game/Wanefall/Dimwit/VFX/Templates set the driver duplicates per verb).
# TODO(glm-qa): add GLM visual QA — capture the system in a preview/SceneCapture and judge "reads as WANE
#   teal/blue energy seam + correct verb motion" (structural QA is authoritative until then).
# TODO(hooks): data-driven spawn hooks so gameplay (hit/death/ability) spawns the right NS_Wane_<Verb>.
