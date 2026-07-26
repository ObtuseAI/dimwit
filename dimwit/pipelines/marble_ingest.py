"""Marble ingest pipeline — bring a MARBLE (World Labs) AI-generated environment into WANEFALL as a usable UE5.8 env.

Pipeline (the adversarially-verified design, fail-closed at every human/payment boundary):

    Stage 0  INTAKE GATE   file exists / non-empty / extension-whitelisted / magic-bytes sniff.
                           If absent -> BLOCKED ("user must generate + export in Marble first"). NEVER fabricate geometry.
    Stage 1  ROUTE         auto-detect export_kind (collider GLB / high-quality GLB / splat PLY|SPZ), overridable.
                           splat-only with NO paired collider -> not playable (no collision) -> hard issue.
    Stage 2  BLENDER       headless `marble_blender_ingest.py`: OpenCV->Z-up axis fix, scale calibration (fail-closed
                           BLOCKED when a playable env has no reference dimension), weld/cleanup/normals, decimate to a
                           UE-sane tri budget, triangulate, vcol->texture bake for the vertex-color HQ variant, export glTF.
    Stage 3  UE 5.8        headless `scripts/ue/ue_marble_import.py`: Interchange import as StaticMesh, enable Nanite, set a usable
                           fallback %, Collision Complexity = UseComplexAsSimple, spawn at origin + PlayerStart +
                           GameModeBase + neutral manual-exposure PostProcessVolume, save a test map.
                           SPLAT track is BLOCKED until a UE-5.8-compatible Gaussian-splat plugin build is confirmed.

DOCTRINE (never weakened): a validator may FAIL but NEVER silently PASS; missing input/UE/Blender/file -> BLOCKED (not a
fake pass); QA verdicts come from the driver RESULT FILES (UE/Blender exit codes are unreliable); provenance is
fail-closed -> the operator MUST assert a commercial-tier Marble license or the artifact is REJECTED (shipping WANEFALL
needs the Pro/commercial tier; Free/Standard grant no commercial rights). Autonomous ceiling = PROMOTED_TO_REVIEW;
active-slice promotion is operator-gated. Bounded repair <= max_repairs.

HUMAN-ONLY BOUNDARY (cannot be automated by Dimwit or the assistant): create/log into a World Labs account, subscribe to
a plan that allows PLY/GLB export AND grants commercial rights, generate the world, and download the export file. This
pipeline's automation begins ONLY once an export file exists on local disk. See docs/DIMWIT_MARBLE_INGEST.md.

Validators (fail-closed, hash-chained via the base ledger):
  V1 intake (stage 0)            V2 axis fixed to Z-up       V3 mesh non-empty / welded
  V4 scale calibrated            V5 normals/cleanup ok       V6 tri budget within UE-sane range
  V7 textures/vcol resolved      V8 Nanite enabled (vs SOURCE tris, not the fallback)
  V9 collision present (RED if splat-only with no collider)  V10 test map saved + PlayerStart
  V11 OPTICS readability (PIE capture; reject white/black/rotated/disfigured/uniform-albedo) -- deferred to a live capture.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import ProductionPipeline, Artifact, Verdict, BlockedError

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject")
BLENDER = Path(r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")

BLENDER_DRIVER = ROOT / "blender_scripts" / "marble_blender_ingest.py"
UE_DRIVER = ROOT / "scripts/ue/ue_marble_import.py"
BLENDER_RESULT = ART / "marble_blender_result.json"
UE_RESULT = ART / "marble_ue_result.json"
STAGING = ART / "marble_staging"

MAPS_ROOT = "/Game/Wanefall/Maps"
DEST_ROOT = "/Game/Wanefall/Imported/Marble"

# Stage 0 intake: extension whitelist + magic-byte signatures (sniffed, never trusted on extension alone).
MESH_EXTS = {".glb", ".gltf"}
SPLAT_EXTS = {".ply", ".spz"}
ALLOWED_EXTS = MESH_EXTS | SPLAT_EXTS

# UE-sane triangle budget for a single static-mesh backdrop (Nanite handles density, but keep the decimated
# *source* in a range that imports + builds without OOM on the disk-tight machine).
TRI_MIN = 5_000          # below this the mesh is likely empty/broken, not a real environment
TRI_MAX = 1_500_000      # decimate down to here if the HQ mesh ships ~1M+; Nanite still gets full detail in-engine


class MarbleIngestPipeline(ProductionPipeline):
    name = "marble_ingest"
    kind = "environment_mesh"

    # ---- Stage 0 + Stage 1: intake gate + route -------------------------------------------------
    def plan(self, task: dict) -> dict:
        if not BLENDER.exists():
            raise BlockedError(f"Blender not found: {BLENDER}")
        if not BLENDER_DRIVER.exists():
            raise BlockedError(f"Blender driver missing: {BLENDER_DRIVER}")
        if not UE_CMD.exists():
            raise BlockedError(f"UnrealEditor-Cmd not found: {UE_CMD}")
        if not UPROJECT.exists():
            raise BlockedError(f"uproject not found: {UPROJECT}")
        if not UE_DRIVER.exists():
            raise BlockedError(f"UE driver missing: {UE_DRIVER}")

        # Stage 0 INTAKE GATE — the human-only boundary. No file on disk => the user has not generated/exported
        # in Marble yet. Fail closed; do NOT fabricate geometry.
        src_raw = task.get("src") or task.get("file") or ""
        if not src_raw:
            raise BlockedError(
                "no Marble export file supplied. HUMAN-ONLY first: log into marble.worldlabs.ai (commercial-tier "
                "plan for a shipping game), generate the world, download the export (Collider GLB / High-Quality GLB "
                "/ splat PLY|SPZ), then re-run with src=<path>. See docs/DIMWIT_MARBLE_INGEST.md.")
        src = Path(src_raw)
        if not src.exists():
            raise BlockedError(f"Marble export file does not exist on disk: {src} (generate + export in Marble first)")
        if src.stat().st_size == 0:
            raise BlockedError(f"Marble export file is empty (0 bytes): {src}")
        ext = src.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise BlockedError(f"unsupported export extension {ext!r}; expected one of {sorted(ALLOWED_EXTS)}")
        sniff = self._sniff(src)
        if not sniff["ok"]:
            raise BlockedError(f"magic-byte sniff failed for {src.name}: {sniff['why']} "
                               f"(extension says {ext} but the bytes disagree)")

        # Stage 1 ROUTE — kind from sniff, overridable by task. collider vs high-quality is a GLB sub-kind the
        # user declares (the bytes can't tell them apart); default to high-quality (the production visual path).
        kind = str(task.get("kind", sniff["kind"])).lower()       # collider | hq | splat
        if ext in SPLAT_EXTS:
            kind = "splat"
        elif kind not in {"collider", "hq"}:
            kind = "hq"

        collider_raw = task.get("collider")                       # optional paired collider GLB for a splat
        collider = Path(collider_raw) if collider_raw else None

        playable = bool(task.get("playable", True))               # is this meant to be walkable/collidable?
        ref_dim = task.get("ref_dim_meters")                      # real-world reference (e.g. door height) for scale

        # Stage 1 hard issue: a splat with no paired collider is NOT a playable environment (no collision/geometry).
        splat_no_collider = (kind == "splat" and collider is None)
        # SPLAT visual track on UE 5.8: no plugin build confirmed for 5.8 yet -> the UE import stage is BLOCKED for
        # pure splats. The MESH track (collider/hq GLB) is the only fully-supported 5.8 path.
        splat_ue_blocked = (kind == "splat")

        # Scale fail-closed: a PLAYABLE env with no reference dimension imports at an arbitrary scale (Marble has no
        # real-world units) -> gravity/PlayerStart feel wrong. Require a reference unless the caller opts out.
        if playable and kind in {"collider", "hq"} and ref_dim is None and not task.get("allow_unscaled"):
            raise BlockedError(
                "playable mesh env requires a real-world reference dimension for scale calibration "
                "(Marble exports have NO scale). Supply ref_dim_meters=<meters> (+ optional ref_axis=x|y|z) measuring a "
                "known feature, or pass allow_unscaled=1 to accept arbitrary scale (not recommended for a walkable env).")

        STAGING.mkdir(parents=True, exist_ok=True)
        asset_name = str(task.get("asset_name") or f"SM_Marble_{src.stem}")
        out_glb = STAGING / f"{asset_name}.glb"

        return {
            "src": str(src), "ext": ext, "kind": kind, "sniff": sniff,
            "collider": str(collider) if collider else None,
            "playable": playable, "ref_dim_meters": ref_dim, "ref_axis": str(task.get("ref_axis", "z")).lower(),
            "target_tris": int(task.get("target_tris", TRI_MAX)),
            "asset_name": asset_name, "out_glb": str(out_glb),
            "dest": str(task.get("dest", f"{DEST_ROOT}")),
            "level": str(task.get("level", f"{MAPS_ROOT}/Wanefall_Marble_{src.stem}")),
            "license": task.get("license"),               # operator MUST assert commercial rights (provenance gate)
            "splat_no_collider": splat_no_collider,
            "splat_ue_blocked": splat_ue_blocked,
        }

    @staticmethod
    def _sniff(p: Path) -> dict:
        """Magic-byte sniff: glb ('glTF'), gltf (JSON '{'), ply ('ply'), spz (gzip 1f 8b or 'NGSP')."""
        try:
            head = p.read_bytes()[:16]
        except Exception as e:
            return {"ok": False, "why": f"unreadable: {e}", "kind": "unknown"}
        if head[:4] == b"glTF":
            return {"ok": True, "why": "glb magic glTF", "kind": "hq"}
        if head[:1] == b"{" or head[:5] == b"\xef\xbb\xbf{"[:5]:
            return {"ok": True, "why": "gltf json", "kind": "hq"}
        if head[:3] == b"ply":
            return {"ok": True, "why": "ply header", "kind": "splat"}
        if head[:2] == b"\x1f\x8b" or head[:4] == b"NGSP":
            return {"ok": True, "why": "spz/gzip", "kind": "splat"}
        return {"ok": False, "why": f"unrecognized magic {head[:4]!r}", "kind": "unknown"}

    # ---- Stage 2 + Stage 3: Blender ingest then UE import ----------------------------------------
    def execute(self, plan: dict) -> Artifact:
        ART.mkdir(parents=True, exist_ok=True)
        for r in (BLENDER_RESULT, UE_RESULT):
            if r.exists():
                r.unlink()

        rec: dict = {"kind": plan["kind"], "src": plan["src"]}

        # STAGE 2 — Blender (skip for pure splats: no mesh to clean; the splat goes straight to a UE plugin track).
        if plan["kind"] != "splat":
            b_args = [
                str(BLENDER), "--background", "--factory-startup", "--python", str(BLENDER_DRIVER), "--",
                f"src={plan['src']}", f"out={plan['out_glb']}", f"result={BLENDER_RESULT}",
                f"kind={plan['kind']}", f"target_tris={plan['target_tris']}",
                f"ref_axis={plan['ref_axis']}",
            ]
            if plan.get("ref_dim_meters") is not None:
                b_args.append(f"ref_dim={plan['ref_dim_meters']}")
            try:
                subprocess.run(b_args, capture_output=True, text=True, timeout=1800)
            except Exception as e:
                rec["blender"] = {"error": f"blender_invoke_failed: {type(e).__name__}: {e}"}
                return self._artifact(plan, rec)
            rec["blender"] = self._read(BLENDER_RESULT, "blender driver produced no result file")
        else:
            rec["blender"] = {"skipped": "splat track has no Blender mesh stage",
                              "splat_no_collider": plan["splat_no_collider"]}

        # STAGE 3 — UE import. Pure splats are BLOCKED on 5.8 (no confirmed plugin); record it honestly, no fake pass.
        if plan["splat_ue_blocked"]:
            rec["ue"] = {"blocked": "splat visual track requires a UE-5.8-compatible Gaussian-splat plugin build "
                                    "(none confirmed). Use the Collider/High-Quality GLB mesh track for 5.8."}
            return self._artifact(plan, rec)

        # Don't try to import a Blender stage that errored.
        if rec["blender"].get("error") or not Path(plan["out_glb"]).exists():
            rec["ue"] = {"skipped": "blender stage did not produce an exported mesh"}
            return self._artifact(plan, rec)

        u_args = (
            f"-ExecutePythonScript={UE_DRIVER} "
            f"src={plan['out_glb']} dest={plan['dest']} asset={plan['asset_name']} "
            f"level={plan['level']} result={UE_RESULT} nanite=1 collision=complexassimple"
        ).replace("\\", "/")  # UE mis-parses backslash paths through subprocess quoting
        cmd = [str(UE_CMD), str(UPROJECT), u_args, "-unattended", "-nosplash", "-nopause", "-stdout"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except Exception as e:
            rec["ue"] = {"error": f"ue_invoke_failed: {type(e).__name__}: {e}"}
            return self._artifact(plan, rec)
        rec["ue"] = self._read(UE_RESULT, "UE driver produced no result file")
        return self._artifact(plan, rec)

    @staticmethod
    def _read(path: Path, miss: str) -> dict:
        if not path.exists():
            return {"error": miss}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"result_parse_failed: {e}"}

    def _artifact(self, plan: dict, rec: dict) -> Artifact:
        # Provenance fail-closed: the operator MUST assert a commercial-tier Marble license for a shipping game.
        # Absent -> base.run() REJECTS (no silent promotion of legally-unusable assets).
        lic = plan.get("license")
        return Artifact(
            asset_id=plan["asset_name"], kind=self.kind, data=rec,
            provenance={
                "source": f"Marble (World Labs) export kind={plan['kind']} file={Path(plan['src']).name}; "
                          f"Blender {BLENDER_DRIVER.name} -> UE {UE_DRIVER.name}",
                "license": lic if lic else "",   # empty -> provenance_fail_closed -> REJECTED
            },
        )

    # ---- QA: validators V1..V11 (fail-closed) ---------------------------------------------------
    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        rec = artifact.data or {}
        b = rec.get("blender", {}) or {}
        u = rec.get("ue", {}) or {}

        # Hard blocks surfaced as honest non-pass (not hard_fail — they are environment/plugin gaps, salvageable).
        if u.get("blocked"):
            return Verdict(score=0.0, passed=False, issues=[u["blocked"]],
                           detail={"stage": "ue", "blocked": True, "result": rec})
        if b.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=False,
                           issues=[f"blender: {b['error']}"], detail={"result": rec})
        if u.get("error"):
            return Verdict(score=0.0, passed=False, hard_fail=False,
                           issues=[f"ue: {u['error']}"], detail={"result": rec})

        is_splat = plan["kind"] == "splat"
        tris_out = int(b.get("tri_count_out", 0))
        tris_src = int(b.get("tri_count_in", 0))

        checks = {
            # V1 intake already enforced in plan(); record that we got past it.
            "V1_intake": True,
            # V2 axis fixed to Z-up
            "V2_axis_zup": bool(b.get("axis_fixed")) if not is_splat else True,
            # V3 mesh non-empty / welded
            "V3_mesh_nonempty": tris_out >= TRI_MIN if not is_splat else True,
            # V4 scale calibrated (fail-closed: required for playable mesh envs)
            "V4_scale": (bool(b.get("scale_applied")) or not plan["playable"]) if not is_splat else True,
            # V5 normals / cleanup
            "V5_cleanup": bool(b.get("cleanup_ok")) if not is_splat else True,
            # V6 tri budget within UE-sane range
            "V6_tri_budget": (TRI_MIN <= tris_out <= TRI_MAX) if not is_splat else True,
            # V7 textures / vertex-color resolved (HQ vcol variant must bake; collider may be untextured)
            "V7_textures": bool(b.get("textures_ok", True)) if not is_splat else True,
            # V8 Nanite enabled — judged against the SOURCE tri count, never the low-poly fallback
            "V8_nanite": bool(u.get("nanite_enabled")) and int(u.get("source_tris", 0)) >= TRI_MIN,
            # V9 collision present (RED if splat-only with no collider)
            "V9_collision": (str(u.get("collision_complexity", "")).lower().startswith("complex")
                             and not plan["splat_no_collider"]),
            # V10 test map saved + PlayerStart present
            "V10_test_map": bool(u.get("level_saved")) and int(u.get("player_starts", 0)) >= 1,
            # V11 optics readability is a live PIE capture — deferred; recorded as pending, not a silent pass.
        }
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        if plan["splat_no_collider"]:
            issues.append("splat-only with no paired collider GLB -> NOT a playable environment (no collision)")
        return Verdict(
            score=score, passed=all(checks.values()), issues=issues,
            detail={"checks": checks, "kind": plan["kind"], "tri_src": tris_src, "tri_out": tris_out,
                    "blender": b, "ue": u, "optics_v11": "pending live PIE capture"},
            evidence=[p for p in [u.get("level"), b.get("exported")] if p],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # If we overshot the tri budget, decimate harder next pass; if the mesh came in empty, there's nothing to
        # repair (BLOCKED-class) so just re-run as-is and let QA fail honestly.
        plan = dict(plan)
        if "V6_tri_budget" in (verdict.issues or []) or "V8_nanite" in (verdict.issues or []):
            plan["target_tris"] = max(TRI_MIN * 4, int(plan.get("target_tris", TRI_MAX) * 0.6))
        return self.execute(plan)
