"""Dimwit PERMANENT VALIDATION HARNESS — "Dimwit validates everything, going forward."

A single fail-closed suite that runs a registry of `Validator`s against every WANEFALL asset/slice Dimwit
produces (characters, rigs, animation wiring, gameplay code, materials, environment, vfx/audio, cross-pipeline
consistency, and the proof system itself), writes a hash-chained + watermarked proof ledger, and emits one
report (JSON + a section in the WANEFALL Build Review gallery).

DOCTRINE (never weakened, mirrors base.ProductionPipeline):
  - A validator may FAIL but NEVER silently PASS. Field-absent / missing input / missing UE / missing PNG ->
    raise BlockedError -> recorded BLOCKED (NOT pass). There is no path to suite-PASS with an unrun blocker.
  - Verdicts come from CONTENT: perception measures pixels; byte size is telemetry, never a verdict (the
    `png_bytes > N` rubber-stamp is banned, see validators V-META-06).
  - Thresholds live in ONE frozen table (THRESHOLDS) and ratchet UP only.
  - One serialized UE batch (two passes max: nullrhi inspect + GUI capture) — never one boot per validator
    (the machine is disk/RAM tight).

  python scripts/pipeline/run_validation.py            # validate everything
  python scripts/pipeline/run_validation.py --list     # list validators
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from dimwit.pipelines.base import Verdict, BlockedError
from dimwit.engine import DimwitLedger
from dimwit.core import sha256_obj

ROOT = Path(__file__).resolve().parents[2]                      # Dimwit/
PROJECT = Path(r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox")
UE_CMD = Path(r"C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
UPROJECT = PROJECT / "WanefallGreybox.uproject"
ART = ROOT / "artifacts"
VAL_ART = ART / "validation"


# ------------------------------------------------------------------ frozen thresholds (ratchet up only)
THRESHOLDS = {
    "nanite_uasset_min_mb": 30.0,            # full-detail humanoid floor (reconciled to current roster reality)
    "nanite_hires_tri_min": 150_000,         # live Nanite hi-res cluster tri count (the REAL anti-fallback gate)
    "uasset_disk_json_tol_mb": 15.0,
    "metallic_max": 0.50, "rig_metallic_max": 0.10, "metallic_hard": 0.60,
    "roughness_band": (0.45, 0.70), "specular_band": (0.40, 0.60),
    "mean_luminance_floor": 0.18,            # perception hard-fail floor (Phase 0)
    "env_mean_luminance_floor": 0.06, "env_near_black_max": 0.90,
    "teal_frac_floor": 0.04, "magenta_frac_hard": 0.015,
    "pose_delta_image_floor": 0.015,         # inter-frame image_delta for "is animating"
    "mirror_diff_max": 0.12,                 # silhouette symmetry
    "weight_coverage_min": 0.99, "max_influences": (1, 4), "bone_count_min": 50,
    "rig_height_cm": (140.0, 200.0), "promote_floor": 0.70,
    "vfx_stub_min_kb": 50, "lobby_umap_warn_bytes": 50_000_000,
    "env_actor_min": 60, "env_starts_min": 2, "env_vein_min": 3, "env_spire_min": 1,
    "expected_humanoids": ["SM_Char_03_zythan", "SM_Char_04_qorin", "SM_Char_05_therak",
                           "SM_Char_06_ullio", "SM_Char_07_kelous", "SM_Char_08_nexor"],
    "banter_signature": ["banter", "weaponized", "MS_WeaponizedBanter", "crystallize_taunt"],
    "legacy_phong_marker": "FBXLegacyPhongSurfaceMaterial",
    "gltf_base": "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque",
    # --- hardened intent-contract loop: the per-build FUSED-confidence gate to PROMOTED_TO_REVIEW.
    # Ratchet-UP-ONLY. Starts at the operator-chosen 0.95 floor; the 0.99 ceiling is the calibrated
    # destination of the graduated-autonomy ladder. Reaching this gate NEVER auto-accepts — the operator
    # is still the only one who can set HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE. v_threshold_ratchet
    # guards the band [floor, ceiling] so the gate can never be lowered below 0.95 or raised past 0.99.
    "suite_confidence_review_gate": 0.95,
    "suite_confidence_review_ceiling": 0.99,
}


# ------------------------------------------------------------------ frozen per-asset_type acceptance floors
# The gating knobs that decide whether a build may reach PROMOTED_TO_REVIEW live HERE, in the frozen
# ratchet-protected table — NOT in the author-written intent_contract.json. spec_author may only RAISE a
# knob above its asset_type floor; the value used at fuse-time is always max(author_value, frozen_floor).
# An unknown/absent asset_type resolves to the STRICTEST row (fail-closed: a new type is never permissive).
#   require_perception      — pixel-truth measurement mandatory (missing perception lib/evidence => BLOCKED)
#   require_optics_semantic — GLM disfigurement/identity judge mandatory (missing LLM => BLOCKED)
#   target_match_floor      — min identity/structure similarity to the declared reference (silhouette IoU + region)
#   min_required_domains    — each MUST run >=1 applicable validator, else fused confidence => None (unreachable 0.99)
#   min_load_bearing_dims   — dims that cannot be masked by a strong easy dim (weakest-link MIN)
#   required_capture_stages — stages the capture-vs-target compare MUST cover (motion => anim validators BLOCKER)
#   confidence_floor        — per-asset_type fused gate (starts 0.95, ratchets toward 0.99)
_STRICT_FLOOR = {
    "require_perception": True, "require_optics_semantic": True, "target_match_floor": 0.85,
    "min_required_domains": ["perception", "optics", "design_md", "intent_conformance"],
    "min_load_bearing_dims": ["silhouette_readability", "third_person_camera_readability", "hit_destroy_state_clarity"],
    "required_capture_stages": ["plan", "execute", "hero", "player_camera", "motion"],
    "confidence_floor": 0.95,
}
ASSET_TYPE_FLOORS = {
    "character": dict(_STRICT_FLOOR),
    "enemy": dict(_STRICT_FLOOR),
    "hostile_construct_enemy": dict(_STRICT_FLOOR),
    "weapon": {**_STRICT_FLOOR,
               # no first-person dim exists in SCORED_DIMENSIONS; a FP weapon's read is carried by
               # its silhouette + hero (closest object) + general gameplay readability.
               "min_load_bearing_dims": ["silhouette_readability", "hero_readability", "gameplay_readability"]},
    "vehicle": dict(_STRICT_FLOOR),
    "prop": {"require_perception": True, "require_optics_semantic": False, "target_match_floor": 0.82,
             "min_required_domains": ["perception", "design_md", "intent_conformance"],
             "min_load_bearing_dims": ["silhouette_readability"],
             "required_capture_stages": ["plan", "execute", "hero"], "confidence_floor": 0.95},
    "environment": {"require_perception": True, "require_optics_semantic": False, "target_match_floor": 0.80,
                    "min_required_domains": ["perception", "design_md", "intent_conformance"],
                    "min_load_bearing_dims": ["silhouette_readability"],
                    "required_capture_stages": ["plan", "execute", "hero"], "confidence_floor": 0.95},
    "default": dict(_STRICT_FLOOR),
    "_unknown": dict(_STRICT_FLOOR),     # fail-closed: an unrecognized asset_type gets the strictest gate
}


def resolve_asset_type_floors(asset_type: Optional[str]) -> dict:
    """The frozen acceptance-floor row for an asset_type. Unknown/absent => STRICTEST (fail-closed)."""
    if not asset_type:
        return dict(ASSET_TYPE_FLOORS["_unknown"])
    return dict(ASSET_TYPE_FLOORS.get(asset_type, ASSET_TYPE_FLOORS["_unknown"]))


class Severity(str, Enum):
    BLOCKER = "blocker"      # any FAIL/REJECTED/BLOCKED => suite cannot PASS
    WARN = "warn"            # surfaces in report, does not block the suite


class ProbeType(str, Enum):
    STATIC = "static_python"      # reads driver *_result.json / artifact fields (NO UE)
    FILESYSTEM = "filesystem"     # on-disk bytes/paths (NO UE)
    LEDGER = "ledger"             # DimwitLedger.consistency_check + doctrine checks
    COMPILE = "compile"           # UBT / shader / niagara compile (subprocess)
    UE_PYTHON = "ue_python"       # needs the shared headless UE batch
    PERCEPTION = "perception"     # runs on a PNG produced by a ue_python capture


# ------------------------------------------------------------------ Validator
@dataclass
class Validator:
    id: str
    domain: str
    probe_type: ProbeType
    severity: Severity
    target: str
    regression_caught: str
    check: Callable[["ValidationContext"], Verdict]
    requires: list = field(default_factory=list)   # e.g. ["ue"], ["perception"]


def ok(score=1.0, **detail) -> Verdict:
    return Verdict(score=score, passed=True, detail=detail)


def fail(score=0.0, issues=None, hard=False, **detail) -> Verdict:
    return Verdict(score=score, passed=False, hard_fail=hard, issues=issues or [], detail=detail)


# ------------------------------------------------------------------ context (shared, serialized UE)
@dataclass
class ValidationContext:
    root: Path = ROOT
    project: Path = PROJECT
    ue_cmd: Path = UE_CMD
    uproject: Path = UPROJECT
    run_ue: bool = True
    _ue_results: dict = field(default_factory=dict)
    _ue_ran: bool = False
    _perception_cache: dict = field(default_factory=dict)
    # ---- per-build intent contract (hardened loop). None => the suite is running in PROJECT-WIDE mode
    # (the 110-validator "validate everything" sweep); the intent_conformance validators are then n/a.
    # In PER-BUILD mode the caller passes the authored contract + its on-disk path + the capture to compare.
    contract: Optional[dict] = None
    contract_path: Optional[Path] = None
    asset_type: str = ""
    capture_png: Optional[Path] = None     # the final capture to match against the declared reference

    # ---- environment
    def ue_available(self) -> bool:
        return self.ue_cmd.exists() and self.uproject.exists()

    # ---- intent-contract helpers
    def floors(self) -> dict:
        """Frozen acceptance floors for this build's asset_type (strictest for unknown/absent)."""
        return resolve_asset_type_floors(self.asset_type or (self.contract or {}).get("asset_type"))

    def intent_required_stages(self) -> list:
        return list(((self.contract or {}).get("validation_plan") or {}).get("required_capture_stages", []))

    def ue_probe(self, probe_id: str) -> dict:
        """Cached result of one probe from the consolidated UE batch. Fail-closed."""
        if not self.ue_available():
            raise BlockedError("UnrealEditor-Cmd or uproject not found")
        if not self._ue_ran:
            raise BlockedError("UE probe batch was not run (run_ue=False or batch errored)")
        if probe_id not in self._ue_results:
            raise BlockedError(f"UE probe '{probe_id}' produced no result")
        r = self._ue_results[probe_id]
        if isinstance(r, dict) and r.get("error"):
            raise BlockedError(f"UE probe '{probe_id}' errored: {r['error']}")
        return r

    def perceive(self, png_path) -> dict:
        from dimwit import perception
        key = str(png_path)
        if key in self._perception_cache:
            return self._perception_cache[key]
        if not Path(png_path).exists():
            raise BlockedError(f"perception PNG missing: {png_path}")
        m = perception.analyze_image(png_path)
        if not m.get("ok"):
            raise BlockedError(f"analyze_image failed: {m.get('error')}")
        out = {"metrics": m, "style": perception.measure_style_compliance(m)}
        self._perception_cache[key] = out
        return out

    # ---- artifact / source helpers (fail-closed: missing -> BlockedError)
    def result_json(self, rel: str, must_describe: Optional[Path] = None) -> dict:
        p = (self.root / "artifacts" / rel) if not Path(rel).is_absolute() else Path(rel)
        if not p.exists():
            raise BlockedError(f"result JSON missing: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise BlockedError(f"result JSON unreadable {p}: {e}")
        if must_describe is not None and must_describe.exists():
            if p.stat().st_mtime < must_describe.stat().st_mtime - 1:
                raise BlockedError(f"result JSON {p.name} is STALE (older than {must_describe.name})")
        return data

    def read_text(self, path) -> str:
        p = Path(path)
        if not p.exists():
            raise BlockedError(f"source file missing: {p}")
        return p.read_text(encoding="utf-8", errors="replace")

    def content_path(self, rel_game: str) -> Path:
        """/Game/... -> on-disk Content/....uasset path."""
        rel = rel_game.replace("/Game/", "").lstrip("/")
        return self.project / "Content" / (rel + ".uasset")


# ------------------------------------------------------------------ the one serialized UE batch
def run_ue_batch(ctx: ValidationContext, manifest: dict, timeout: int = 1800) -> dict:
    """Run the ONE consolidated probe driver (scripts/ue/ue_validation_probe.py). Returns parsed results dict.
    Fail-closed: raises BlockedError if UE absent or no result file written."""
    if not ctx.ue_available():
        raise BlockedError("UE unavailable")
    VAL_ART.mkdir(parents=True, exist_ok=True)
    mpath = VAL_ART / "probe_manifest.json"
    out = VAL_ART / "ue_probe_batch.json"
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if out.exists():
        out.unlink()                                  # never read a stale batch
    driver = ctx.root / "scripts/ue/ue_validation_probe.py"
    arg = f"-ExecutePythonScript={driver} manifest={mpath} out={out}".replace("\\", "/")
    # -NoTextureStreaming: tick-less sessions never stream mips (probe-proven 2026-07-02,
    # artifacts/exposure_sweep3_nostream) — without it every SceneCapture samples low resident
    # mips and the rig capture photographs a washed, panel-less lie.
    cmd = [str(ctx.ue_cmd), str(ctx.uproject), arg, "-NoTextureStreaming",
           "-unattended", "-nopause", "-nosplash", "-stdout"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BlockedError("UE probe batch timed out")
    if not out.exists():
        raise BlockedError("UE probe batch wrote no result file (crash / headless capture unavailable)")
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"UE probe batch result unreadable: {e}")


# ------------------------------------------------------------------ the suite
class ValidationSuite:
    def __init__(self, ctx: ValidationContext, registry: list):
        self.ctx = ctx
        self.registry = registry
        self.ledger = DimwitLedger(ctx.root / "ledger" / "validation.jsonl")
        self.watermark_path = ctx.root / "ledger" / "validation_watermark.json"

    def _needs_ue(self, sel) -> bool:
        return any(v.probe_type in (ProbeType.UE_PYTHON, ProbeType.PERCEPTION) for v in sel)

    def run(self, domains: Optional[list] = None, manifest: Optional[dict] = None) -> dict:
        sel = [v for v in self.registry if not domains or any(d in v.domain for d in domains)]
        ue_error = None
        if self.ctx.run_ue and self._needs_ue(sel):
            try:
                man = manifest if manifest is not None else build_default_manifest()
                self.ctx._ue_results = run_ue_batch(self.ctx, man)
                self.ctx._ue_ran = True
            except Exception as e:
                ue_error = str(e)
        results = [self._run_one(v) for v in sel]
        report = self._assemble(results, ue_error)
        report["scope"] = "full" if not domains else {"domains": list(domains)}
        report["run_ue"] = bool(self.ctx.run_ue)
        self._write_report(report)
        self._update_watermark()
        if report["scope"] == "full":
            self._sync_state_truth_best_effort()
        return report

    def _run_one(self, v: Validator) -> dict:
        try:
            verdict = v.check(self.ctx)
            state = "REJECTED" if verdict.hard_fail else ("PASS" if verdict.passed else "FAIL")
        except BlockedError as e:
            verdict, state = Verdict(passed=False, detail={"blocked": str(e)}), "BLOCKED"
        except Exception as e:
            verdict, state = Verdict(passed=False, detail={"error": repr(e)}), "BLOCKED"
        entry = {"validator_id": v.id, "domain": v.domain, "severity": v.severity.value,
                 "probe_type": v.probe_type.value, "state": state, "score": round(float(verdict.score), 4),
                 "passed": verdict.passed, "hard_fail": verdict.hard_fail, "issues": verdict.issues,
                 "evidence": verdict.evidence, "detail": verdict.detail,
                 "regression_caught": v.regression_caught, "target": v.target}
        self.ledger.append({"ts": int(time.time()), "actor": "validation_suite",
                            "asset_id": v.id, "state": f"validation.{state}",
                            "candidate_hash": sha256_obj(entry), "detail": entry})
        return entry

    # the two motion validators are WARN by default; when a build's intent contract REQUIRES a 'motion'
    # capture stage, a frozen/non-animating character is load-bearing -> escalate their failures to BLOCKER.
    _MOTION_VALIDATORS = {"anim_video_motion_live", "anim_locomotion_pose_evaluates"}

    def _escalate_motion(self, results: list) -> bool:
        if "motion" not in self.ctx.intent_required_stages():
            return False
        escalated = False
        for r in results:
            if r["validator_id"] in self._MOTION_VALIDATORS and r["state"] in ("FAIL", "BLOCKED", "REJECTED"):
                r["severity"] = "blocker"
                r["severity_escalated"] = "intent contract requires the 'motion' capture stage"
                escalated = True
        return escalated

    def _assemble(self, results: list, ue_error: Optional[str]) -> dict:
        motion_escalated = self._escalate_motion(results)     # contract-driven WARN->BLOCKER (before rollup)
        counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0}
        for r in results:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        blockers = [r for r in results if r["severity"] == "blocker"]
        if any(r["state"] == "REJECTED" for r in blockers):
            verdict = "REJECTED"
        elif any(r["state"] == "FAIL" for r in blockers):
            verdict = "FAIL"
        elif any(r["state"] == "BLOCKED" for r in blockers):
            verdict = "BLOCKED"
        else:
            verdict = "PASS"
        by_domain: dict = {}
        for r in results:
            d = by_domain.setdefault(r["domain"], {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "REJECTED": 0})
            d[r["state"]] = d.get(r["state"], 0) + 1
        report = {"suite_verdict": verdict, "run_ts": int(time.time()), "counts": counts,
                  "by_domain": by_domain, "ue_error": ue_error, "total": len(results), "results": results,
                  "motion_escalated": motion_escalated}
        # per-build comprehensive fused gate (only in PER-BUILD mode; project-wide sweeps have no contract)
        if self.ctx.contract is not None:
            report["suite_fused"] = self._suite_fuse(results)
            report["review_gate_met"] = bool(verdict == "PASS" and report["suite_fused"].get("meets_gate"))
        return report

    # map a validator result to its FUSION domain (evidence type), or None if it isn't a required domain
    @staticmethod
    def _fusion_domain_of(r: dict) -> Optional[str]:
        dom = r.get("domain", "")
        if dom == "optics_semantic":
            return "optics"
        if dom in ("design_md", "design_system"):
            # Z1b: the registry domain string is "design_system"; the strict-floor required-domain label is
            # "design_md". Map BOTH so design evidence actually counts toward the fused gate (it mapped to
            # None before, making the design required-domain permanently unreachable -> gate could never pass).
            return "design_md"
        if dom == "intent_conformance":
            return "intent_conformance"
        if r.get("probe_type") == ProbeType.PERCEPTION.value:
            return "perception"
        return None

    def _suite_fuse(self, results: list) -> dict:
        """Collapse the suite's four required evidence domains into ONE weakest-link confidence via the same
        confidence.fuse() primitive the engine uses — no second scoring world. Target similarity is read from
        the intent_conformance target validator's detail.

        The suite checkpoint fuses over the four evidence DOMAINS + the identity match; the per-load-bearing-dim
        and per-capture-stage coverage are the engine checkpoint's job (and each is its own BLOCKER validator),
        so they are emptied from this view. review_gate_met additionally requires suite_verdict == PASS, which
        already folds in every per-dim BLOCKER and the contract-driven motion escalation."""
        from dimwit import confidence
        floors = dict(self.ctx.floors())
        floors["min_load_bearing_dims"] = []
        floors["required_capture_stages"] = []
        sigs = []
        for r in results:
            fd = self._fusion_domain_of(r)
            if fd is None:
                continue
            blocked = r["state"] in ("BLOCKED",)
            hard = r["state"] == "REJECTED" or (r.get("hard_fail") and r["severity"] == "blocker")
            ts = (r.get("detail") or {}).get("target_similarity") if r["domain"] == "intent_conformance" else None
            sigs.append(confidence.signal(fd, None if blocked else float(r["score"]),
                                          stage="motion" if "motion" in r["validator_id"] else None,
                                          blocked=blocked, hard_fail=bool(hard), id=r["validator_id"]))
            if ts is not None:
                sigs.append(confidence.signal("intent_conformance", float(ts), is_target_similarity=True,
                                              id=f"{r['validator_id']}:target"))
        return confidence.fuse(sigs, self.ctx.contract, floors)

    def _write_report(self, report: dict) -> None:
        VAL_ART.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, indent=2)
        (VAL_ART / "validation_report.json").write_text(payload, encoding="utf-8")
        # Full-scope runs also persist a dedicated full-suite report: domain-scoped runs rewrite
        # validation_report.json wholesale, so meta-artifact generators and truth sync must have a
        # stable "latest COMPLETE suite" source (2026-07-01 audit: scorecard/matrix race).
        if report.get("scope") == "full":
            (VAL_ART / "validation_report_full.json").write_text(payload, encoding="utf-8")

    def _sync_state_truth_best_effort(self) -> None:
        # Failures here must be visible, never suite-fatal: the pipeline_contracts truth validators
        # are the fail-closed net that catches unsynced state on the next run.
        try:
            from ..state_sync import sync_state_truth
            sync_state_truth(self.ctx.root, self.ctx.project)
        except Exception as exc:
            try:
                err_path = self.ctx.root / "artifacts" / "state_sync" / "state_truth_sync_error.json"
                err_path.parent.mkdir(parents=True, exist_ok=True)
                err_path.write_text(json.dumps(
                    {"ok": False, "error": repr(exc), "ts": int(time.time())}, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _update_watermark(self) -> None:
        cc = self.ledger.consistency_check()
        self.watermark_path.write_text(json.dumps(
            {"head": cc.get("head"), "length": cc.get("entry_count"), "ts": int(time.time())},
            indent=2), encoding="utf-8")


def build_default_manifest() -> dict:
    """The full probe set the registry needs from the ONE UE batch. scripts/ue/ue_validation_probe.py executes these
    sequentially inside a single editor process (inspection pass) + a capture pass."""
    try:
        from dimwit.pipelines.character_roster import active_humanoid_characters, active_humanoid_names
        char_items = active_humanoid_characters(ROOT)
        chars = active_humanoid_names(ROOT) or THRESHOLDS["expected_humanoids"]
    except Exception:
        char_items = []
        chars = THRESHOLDS["expected_humanoids"]
    primary = char_items[0] if char_items else {
        "asset_id": "SM_Char_03_zythan",
        "asset_name": "SM_Char_03_zythan",
    }
    primary_rig = f"/Game/Wanefall/Dimwit/CharactersRigged/{primary.get('asset_id') or primary.get('asset_name')}_Rig"
    return {
        "inspect_materials": [f"/Game/Wanefall/Dimwit/Characters/{c}/Materials/pbr_material" for c in chars]
                             + ["/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"],
        "inspect_rig": primary_rig,
        "abp": "/Game/Mannequins/Animations/ABP_Manny",
        "mann_skeleton": "/Game/Mannequins/Meshes/SK_Mannequin",
        "nanite_cluster_meshes": [f"/Game/Wanefall/Dimwit/Characters/{c}/StaticMeshes/{c}" for c in chars],
        "captures": [
            {"id": "rig_ship", "rig": primary_rig,
             "mode": "ship_lighting", "map": "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01",
             "out": str(VAL_ART / "cap_rig_ship.png"), "animate": True},
        ],
        "niagara": ["/Game/Wanefall/Dimwit/VFX/NS_Wane_Crystallize"],
        "out_dir": str(VAL_ART),
    }
