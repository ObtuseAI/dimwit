"""Dimwit VALIDATION REGISTRY — the complete, deduped set of Validators ("validate everything").

Each regression is implemented ONCE as a parameterized check and instantiated per target. UE/perception checks
read the ONE consolidated probe batch via ctx.ue_probe(...)/ctx.perceive(...); static/filesystem/ledger/compile
checks run with no UE. Everything is fail-closed: missing input -> BlockedError -> BLOCKED (never PASS).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from dimwit.pipelines.validation import (
    Validator, Severity as S, ProbeType as P, THRESHOLDS as T, ok, fail, ROOT, PROJECT, VAL_ART,
    ASSET_TYPE_FLOORS,
)
from dimwit.pipelines.base import Verdict, BlockedError
from dimwit.pipelines.character_roster import active_humanoid_characters, active_humanoid_names, is_quarantined_character
from dimwit.pipelines import roster_fidelity as _rfid
from dimwit.core import evaluate_provenance

CHARS = active_humanoid_names(ROOT) or T["expected_humanoids"]
CONTENT = PROJECT / "Content"
SRC = PROJECT / "Source" / "WanefallGreybox"
GLTF = T["gltf_base"]
PHONG = T["legacy_phong_marker"]


def _primary_active_character() -> dict:
    chars = active_humanoid_characters(ROOT)
    if chars:
        return chars[0]
    from dimwit.pipelines.metahuman_utilization import EXPECTED_CHARACTERS
    return EXPECTED_CHARACTERS[0]


def _character_identity_tokens(item: dict) -> set[str]:
    tokens = {
        item.get("key"),
        item.get("asset_name"),
        item.get("asset_id"),
        item.get("source_stem"),
    }
    return {str(token).lower() for token in tokens if token}


def _optics_metadata_matches_active_character(meta: dict) -> bool:
    declared = {
        meta.get("subject_character"),
        meta.get("asset_id"),
        meta.get("asset_name"),
        meta.get("asset_id"),
        meta.get("source_stem"),
    }
    declared_tokens = {str(token).lower() for token in declared if token}
    if not declared_tokens:
        return False
    if any(is_quarantined_character(token, ROOT) for token in declared_tokens):
        return False
    active_tokens = _character_identity_tokens(_primary_active_character())
    return any(token in active_tokens for token in declared_tokens)


def _primary_rig_asset_name() -> str:
    item = _primary_active_character()
    return f"{item.get('asset_id') or item.get('asset_name')}_Rig"


def _primary_rig_path() -> str:
    return f"/Game/Wanefall/Dimwit/CharactersRigged/{_primary_rig_asset_name()}"


def _norm(p):
    return (p or "").split(".")[0].replace("\\", "/")


def _char_record(ctx, c):
    """Case-insensitive char_fidelity record lookup (the roster names mix SM_Char_01_Vorlax/vorlax casing)."""
    recs = {(r.get("asset_id") or r.get("asset") or "").lower(): r
            for r in ctx.result_json("char_fidelity_result.json").get("records", [])}
    r = recs.get(c.lower())
    if r is None:
        raise BlockedError(f"no char_fidelity record for {c}")
    return r


# ============================================================ helpers that read the UE probe batch
def _materials(ctx):
    return ctx.ue_probe("materials")


def _mic(ctx, path):
    mats = _materials(ctx)
    if path not in mats:
        raise BlockedError(f"no material probe for {path}")
    rec = mats[path]
    if rec.get("error") or not rec.get("loaded"):
        raise BlockedError(f"material {path} unloadable: {rec.get('error')}")
    return rec


# ============================================================ CHARACTERS (static full-Nanite)
def _v_char_nanite_enabled(c):
    def check(ctx):
        r = _char_record(ctx, c)
        en = r.get("nanite_enabled")
        if en is not True:
            return fail(issues=[f"{c} nanite_enabled={en!r}"], nanite_enabled=en)
        return ok(nanite_enabled=True)
    return Validator(f"char_nanite_enabled[{c}]", "characters_static_full_nanite", P.STATIC, S.BLOCKER,
                     f"Characters/{c}", "Nanite-fallback flat-grey / never-imported char", check)


def _v_char_nanite_flag(c):
    def check(ctx):
        r = _char_record(ctx, c)
        flag = r.get("nanite_flag_after", r.get("nanite_material_flag"))
        if flag is not True:
            return fail(issues=[f"{c} used_with_nanite flag={flag!r}"], flag=flag)
        return ok(flag=True)
    return Validator(f"char_nanite_material_flag[{c}]", "characters_static_full_nanite", P.STATIC, S.BLOCKER,
                     f"Characters/{c}", "used_with_nanite missing -> smooth fallback render", check)


def _v_char_uasset_bytes(c):
    def check(ctx):
        f = CONTENT / "Wanefall" / "Dimwit" / "Characters" / c / "StaticMeshes" / f"{c}.uasset"
        if not f.exists():
            raise BlockedError(f"uasset missing: {f}")
        mb = f.stat().st_size / 1e6
        if mb < T["nanite_uasset_min_mb"]:
            return fail(issues=[f"{c} uasset {mb:.1f}MB < {T['nanite_uasset_min_mb']}MB (decimated?)"], mb=round(mb, 1))
        return ok(mb=round(mb, 1))
    return Validator(f"char_full_detail_uasset_bytes[{c}]", "characters_static_full_nanite", P.FILESYSTEM, S.BLOCKER,
                     f"Characters/{c}", "decimated-where-full-detail", check)


def _v_char_mic_parent(c):
    def check(ctx):
        rec = _mic(ctx, f"/Game/Wanefall/Dimwit/Characters/{c}/Materials/pbr_material")
        parent = _norm(rec.get("parent"))
        if PHONG.lower() in parent.lower():
            return fail(issues=[f"{c} material parent is legacy-Phong"], hard=True, parent=parent)
        if parent != _norm(GLTF):
            return fail(issues=[f"{c} material parent={parent} != glTF base"], parent=parent)
        return ok(parent=parent)
    return Validator(f"char_mic_parent_gltf[{c}]", "characters_static_full_nanite", P.UE_PYTHON, S.BLOCKER,
                     f"Characters/{c}/pbr_material", "legacy-Phong silver-dark", check, requires=["ue"])


def _v_char_basecolor(c):
    def check(ctx):
        rec = _mic(ctx, f"/Game/Wanefall/Dimwit/Characters/{c}/Materials/pbr_material")
        tex = rec.get("basecolor_tex")
        if not tex:
            return fail(issues=[f"{c} BaseColorTexture not set"], basecolor=tex)
        if rec.get("basecolor_broken"):
            return fail(issues=[f"{c} BaseColorTexture is a broken ref"], hard=True, basecolor=tex)
        return ok(basecolor=tex)
    return Validator(f"char_basecolor_texture_bound[{c}]", "characters_static_full_nanite", P.UE_PYTHON, S.BLOCKER,
                     f"Characters/{c}/pbr_material", "default-grey slot / cross-char mixup", check, requires=["ue"])


def _v_char_metallic(c):
    def check(ctx):
        rec = _mic(ctx, f"/Game/Wanefall/Dimwit/Characters/{c}/Materials/pbr_material")
        met = rec.get("metallic")
        if met is None:
            raise BlockedError(f"{c} metallic unreadable")
        if met > T["metallic_hard"]:
            return fail(issues=[f"{c} metallic {met} > {T['metallic_hard']}"], hard=True, metallic=met)
        if met > T["metallic_max"]:
            return fail(issues=[f"{c} metallic {met} > {T['metallic_max']}"], metallic=met)
        return ok(metallic=met)
    return Validator(f"char_metallic_sane[{c}]", "characters_static_full_nanite", P.UE_PYTHON, S.WARN,
                     f"Characters/{c}/pbr_material", "high-metallic near-black", check, requires=["ue"])


def _v_char_provenance(c):
    def check(ctx):
        r = _char_record(ctx, c)
        prov = r.get("provenance")
        if not prov:
            raise BlockedError(f"{c} provenance not recorded (cannot prove promotable)")
        pv = evaluate_provenance(prov)
        if not pv.get("promotable"):
            return fail(issues=["; ".join(pv.get("reasons", [])) or "provenance not promotable"], hard=True, **pv)
        return ok(license_class=pv.get("license_class"))
    return Validator(f"char_provenance_promotable[{c}]", "characters_static_full_nanite", P.STATIC, S.BLOCKER,
                     f"Characters/{c}", "promoting unlicensed/unknown-source char", check)


def _v_char_no_double_nest(c):
    def check(ctx):
        base = CONTENT / "Wanefall" / "Dimwit" / "Characters" / c
        good = base / "StaticMeshes" / f"{c}.uasset"
        bad = [base / c, base / "StaticMeshes" / c / f"{c}.uasset"]
        if not good.exists():
            raise BlockedError(f"canonical nest missing for {c}")
        doubled = [str(b) for b in bad if b.exists()]
        if doubled:
            return fail(issues=[f"{c} double-nested: {doubled}"], doubled=doubled)
        return ok()
    return Validator(f"char_no_interchange_double_nest[{c}]", "characters_static_full_nanite", P.FILESYSTEM, S.WARN,
                     f"Characters/{c}", "Interchange double-nest mispoint", check)


_MULTIVIEW_ANGLE_THRESHOLDS = {
    "front": {"max_mirror": 0.16},
    "side": {"min_mirror": 0.18, "max_mirror": 0.38},
    "threequarter": {"min_mirror": 0.20, "max_mirror": 0.42},
}


def _char_slug(c: str) -> str:
    m = re.match(r"SM_Char_(\d+)_(.+)", c, re.I)
    if not m:
        return c.lower()
    return f"{m.group(1)}_{m.group(2).lower()}"


def _character_multiview_symmetry_audit(root: Path = ROOT, chars: list | None = None) -> dict:
    """Roster-wide multi-angle anatomy check.

    This intentionally uses rendered pixels, not asset declarations. Front views must stay near mirror-balanced;
    side and three-quarter views must land in sane profile/asymmetry bands so a collapsed profile or arm mass cannot
    pass just because the front render looks acceptable.
    """
    from dimwit import perception

    chars = list(chars or CHARS)
    issues = []
    missing = []
    per_character = {}
    for c in chars:
        slug = _char_slug(c)
        base = Path(root) / "artifacts" / f"{slug}_textured"
        crec = {"slug": slug, "angles": {}}
        for angle, thresholds in _MULTIVIEW_ANGLE_THRESHOLDS.items():
            path = base / f"mview_{angle}.png"
            if not path.exists():
                msg = f"{c} missing {angle} multi-angle render: {path}"
                issues.append(msg)
                missing.append(msg)
                continue
            mirror = perception.image_mirror_diff(path)
            metrics = perception.analyze_image(path, subject_only=True)
            arec = {"path": str(path), "mirror_diff": mirror}
            if metrics.get("ok"):
                arec["subject_fraction"] = metrics.get("subject_fraction")
                arec["mean_luminance"] = metrics.get("mean_luminance")
                arec["edge_density"] = metrics.get("edge_density")
            crec["angles"][angle] = arec
            if mirror < 0:
                issues.append(f"{c} {angle} render unreadable for mirror/symmetry measurement")
                continue
            min_mirror = thresholds.get("min_mirror")
            max_mirror = thresholds.get("max_mirror")
            if min_mirror is not None and mirror < min_mirror:
                issues.append(f"{c} {angle} mirror_diff {mirror:.3f} < {min_mirror:.2f} (profile/limb mass collapsed or wrong angle)")
            if max_mirror is not None and mirror > max_mirror:
                issues.append(f"{c} {angle} mirror_diff {mirror:.3f} > {max_mirror:.2f} (left/right silhouette imbalance)")
            if not metrics.get("ok"):
                issues.append(f"{c} {angle} render unreadable for pixel metrics: {metrics.get('error')}")
            elif metrics.get("subject_fraction", 0.0) < 0.015:
                issues.append(f"{c} {angle} subject_fraction {metrics.get('subject_fraction')} too low to inspect anatomy")
        per_character[c] = crec
    return {
        "passed": not issues,
        "characters_checked": len(chars),
        "angles_required": sorted(_MULTIVIEW_ANGLE_THRESHOLDS),
        "issues": issues,
        "missing": missing,
        "per_character": per_character,
    }


def v_character_multiview_symmetry(ctx):
    audit = _character_multiview_symmetry_audit(ROOT, CHARS)
    audit_path = ROOT / "artifacts" / "character_multiview_symmetry" / "character_multiview_symmetry_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_with_stamp = {"generated_at": time.time(), **audit}
    audit_path.write_text(json.dumps(audit_with_stamp, indent=2), encoding="utf-8")
    if audit["missing"]:
        raise BlockedError("; ".join(audit["missing"][:4]))
    if not audit["passed"]:
        return fail(issues=audit["issues"][:8], hard=True, evidence=[str(audit_path)], **audit)
    return ok(evidence=[str(audit_path)], **audit)


# ============================================================ RIGS
def _rig_json(ctx):
    item = _primary_active_character()
    token = str(item.get("asset_id") or item.get("asset_name"))
    handcrafted = ctx.root / "artifacts" / "rig" / f"{token}_handcrafted_rig.fbx.rig.json"
    if handcrafted.exists():
        return ctx.result_json(handcrafted)
    return ctx.result_json(f"rig/{token}_rigged.fbx.rig.json")


def v_rig_is_skeletal(ctx):
    r = ctx.ue_probe("rig")
    cls = r.get("rig_class")
    if cls != "SkeletalMesh":
        return fail(issues=[f"rig class is {cls}, not SkeletalMesh"], hard=True, rig_class=cls)
    return ok(rig_class=cls)


def v_rig_skeleton(ctx):
    r = ctx.ue_probe("rig")
    rs, ms = _norm(r.get("rig_skeleton")), _norm(ctx.ue_probe("mann_skeleton") if isinstance(ctx.ue_probe("mann_skeleton"), str) else r.get("mann_skeleton"))
    target = "/Game/Mannequins/Meshes/SK_Mannequin"
    if rs != target:
        return fail(issues=[f"rig skeleton {rs} != {target}"], hard=True, rig_skeleton=rs)
    return ok(rig_skeleton=rs)


def v_rig_weight_coverage(ctx):
    wc = _rig_json(ctx).get("weight_coverage")
    if wc is None:
        raise BlockedError("weight_coverage absent")
    if wc <= T["weight_coverage_min"]:
        return fail(issues=[f"weight_coverage {wc} <= {T['weight_coverage_min']}"], weight_coverage=wc)
    return ok(weight_coverage=wc)


def v_rig_max_influences(ctx):
    mi = _rig_json(ctx).get("max_influences")
    lo, hi = T["max_influences"]
    if mi is None:
        raise BlockedError("max_influences absent")
    if not (lo <= mi <= hi):
        return fail(issues=[f"max_influences {mi} not in [{lo},{hi}]"], max_influences=mi)
    return ok(max_influences=mi)


def v_rig_bone_count(ctx):
    b = _rig_json(ctx).get("bones", _rig_json(ctx).get("bone_count"))
    if b is None:
        raise BlockedError("bone count absent")
    if b < T["bone_count_min"]:
        return fail(issues=[f"bones {b} < {T['bone_count_min']}"], bones=b)
    return ok(bones=b)


def v_rig_bounds_height(ctx):
    z = ctx.ue_probe("rig").get("rig_bounds_z_cm")
    lo, hi = T["rig_height_cm"]
    if z is None:
        raise BlockedError("rig bounds absent")
    if not (lo <= z <= hi):
        return fail(issues=[f"rig height {z}cm not in [{lo},{hi}]"], height_cm=z)
    return ok(height_cm=z)


def v_rig_material_not_phong(ctx):
    rec = _mic(ctx, "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material")
    parent = _norm(rec.get("parent"))
    met = rec.get("metallic")
    if PHONG.lower() in parent.lower():
        return fail(issues=["rigged material parent is legacy-Phong"], hard=True, parent=parent)
    if parent != _norm(GLTF):
        return fail(issues=[f"rigged material parent={parent} != glTF base"], parent=parent)
    if met is not None and met > T["rig_metallic_max"]:
        return fail(issues=[f"rigged metallic {met} > {T['rig_metallic_max']} (rechromed)"], metallic=met)
    return ok(parent=parent, metallic=met)


def v_rig_provenance(ctx):
    prov = _rig_json(ctx).get("provenance")
    if not prov:
        raise BlockedError("rig provenance not recorded (cannot prove promotable)")
    pv = evaluate_provenance(prov)
    if not pv.get("promotable"):
        return fail(issues=["; ".join(pv.get("reasons", [])) or "rig provenance not promotable"], hard=True, **pv)
    return ok(license_class=pv.get("license_class"))


def v_rig_perception_ship(ctx):
    res = ctx.perceive(VAL_ART / "cap_rig_ship.png")
    style, m = res["style"], res["metrics"]
    if style.get("hard_fails"):
        return fail(issues=[h["trait"] for h in style["hard_fails"]], hard=True,
                    evidence=[str(VAL_ART / "cap_rig_ship.png")], hard_fails=style["hard_fails"])
    if m["mean_luminance"] < T["mean_luminance_floor"]:
        return fail(issues=[f"too dark: mean_luminance {m['mean_luminance']}"],
                    evidence=[str(VAL_ART / "cap_rig_ship.png")], mean_luminance=m["mean_luminance"])
    return Verdict(score=1.0, passed=True, evidence=[str(VAL_ART / "cap_rig_ship.png")],
                   detail={"mean_luminance": m["mean_luminance"], "silhouette_contrast": m["silhouette_contrast"]})


def v_rig_capture_texture_streaming_off(ctx):
    """Tick-less UnrealEditor-Cmd sessions never stream texture mips (probe-proven 2026-07-02,
    artifacts/exposure_sweep3_nostream): with streaming enabled the rig SceneCapture samples
    permanently-low resident mips and photographs a washed, panel-less figure while the real 4K
    maps sit unstreamed on disk. The batch must run -NoTextureStreaming; the probe reports the
    live r.TextureStreaming cvar, never a hardcoded flag. Fail-closed on missing telemetry."""
    cap = ctx.ue_probe("captures").get("rig_ship", {})
    flag = cap.get("texture_streaming_off")
    if flag is True:
        return ok(texture_streaming_off=True)
    return fail(
        issues=["rig capture ran with texture streaming enabled or unreported "
                f"(texture_streaming_off={flag!r}) — tick-less sessions never stream, so the "
                "capture sampled low-resident mips; launch the UE batch with -NoTextureStreaming"],
        hard=True)


# ============================================================ ANIMATION
def v_anim_skeleton_compatible(ctx):
    r = ctx.ue_probe("rig")
    abp = ctx.ue_probe("abp")
    rs, abps = _norm(r.get("rig_skeleton")), _norm(abp.get("abp_target_skeleton"))
    if rs != abps or rs != "/Game/Mannequins/Meshes/SK_Mannequin":
        return fail(issues=[f"rig_skel={rs} abp_skel={abps}"], hard=True, rig_skeleton=rs, abp_skeleton=abps)
    return ok(skeleton=rs)


def v_anim_video_motion(ctx):
    """G5: gate animation by REAL video of the running game — record a live PIE/standalone game window and prove
    the character actually moves (inter-frame pixel motion). Primary: live window capture. Fallback: on-disk
    evidence from scripts/capture/anim_live_capture.py harness (< 12h). Fail-closed: neither path available -> BLOCKED."""
    import time as _time
    from dimwit.desktop_eyes import DesktopEyes
    from dimwit import optics, perception

    # ── primary: live window ─────────────────────────────────────────────────
    eyes = DesktopEyes()
    w = eyes.find_window("WanefallGreybox") or eyes.find_window("PIE")
    if w:
        burst = eyes.capture_stream(VAL_ART / "anim_video", w["title"], seconds=2.0, fps=8)
        if burst.get("ok") and len(burst.get("frames", [])) >= 2:
            v = optics.judge_motion(burst["frames"], require_semantic=False)
            if not v.get("passed"):
                return fail(issues=v.get("issues", []) or ["no motion detected in live game"],
                            evidence=burst["frames"][:2], detail=v.get("pixel", {}))
            return Verdict(score=1.0, passed=True, evidence=burst["frames"][:2], detail=v.get("pixel", {}))

    # ── fallback: on-disk evidence from scripts/capture/anim_live_capture.py ─────────────────
    proof_path = VAL_ART / "anim_live_proof.json"
    if not proof_path.exists():
        raise BlockedError("no live game window and no on-disk proof (run scripts/capture/anim_live_capture.py then re-validate)")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    age_h = (_time.time() - proof.get("captured_at", 0)) / 3600
    if age_h > 12:
        raise BlockedError(f"anim_live_proof.json is {age_h:.1f}h old (> 12h); re-run scripts/capture/anim_live_capture.py")
    frames = [f for f in (proof.get("frames") or []) if Path(f).exists()]
    if len(frames) < 2:
        raise BlockedError("on-disk proof frames missing; re-run scripts/capture/anim_live_capture.py")
    max_delta = proof.get("max_delta", 0.0)
    if not proof.get("passed") or max_delta < T["pose_delta_image_floor"]:
        return fail(issues=[f"on-disk proof: max_delta={max_delta:.5f} < {T['pose_delta_image_floor']}"],
                    evidence=frames[:2], delta=max_delta)
    return Verdict(score=min(1.0, max_delta / 0.1), passed=True, evidence=frames[:2],
                   detail={"max_delta": max_delta, "age_hours": round(age_h, 2), "source": "anim_live_proof"})


def v_anim_runtime_slot_match(ctx):
    cpp = ctx.read_text(SRC / "Private" / "WanefallLobbyCharacter.cpp")
    if "SetAnimInstanceClass" not in cpp:
        return fail(issues=["SetAnimInstanceClass not called on the runtime mesh slot"], hard=True)
    if "ABP_Manny" not in cpp:
        return fail(issues=["ABP_Manny not referenced in lobby char"])
    return ok()


# ============================================================ TOPOLOGY (elite mesh topology gate)
def _normalize_handcraft_topo(m: dict, outer: dict | None = None) -> dict:
    """Map handcraft pipeline's low_topology field names → topology_qa field names.
    The handcraft pipeline records faces/quad_fraction/non_manifold/has_uv; topology_qa
    expects non_manifold_edges/tri_count_render/ngon_fraction. This is a lossless rename +
    derivation — no threshold changes. `outer` is the parent handcraft record (holds `method`)."""
    if not m:
        return {}
    out = dict(m)
    outer = outer or {}
    # non_manifold → non_manifold_edges
    if "non_manifold" in out and "non_manifold_edges" not in out:
        out["non_manifold_edges"] = out.pop("non_manifold")
    # faces → tri_count_render: for a quad mesh, tris = faces * 2; for a tri mesh, tris = faces
    if "faces" in out and "tri_count_render" not in out:
        qf = float(out.get("quad_fraction", 0.0))
        out["tri_count_render"] = int(out["faces"] * (2.0 * qf + 1.0 * (1.0 - qf)))
    # Derive ngon_fraction if absent. method is stored on the outer record (not inside low_topology).
    # Voxel-quad / quadriflow / any fully-quad mesh has ngon_fraction = 0 by construction.
    if "ngon_fraction" not in out:
        method = outer.get("method", "")
        qf = float(out.get("quad_fraction", 0.0))
        if method.startswith("voxel") or method.startswith("quadri") or qf >= 0.99:
            out["ngon_fraction"] = 0.0
    return out


def v_topology_handcrafted(ctx):
    """Every handcrafted asset must have ELITE topology: quad-dominant, watertight, UV'd, within tri budget.
    Fail-closed: no handcrafted assets yet -> BLOCKED. Triangle-soup / non-manifold / no-UV -> hard_fail.
    Accepts both 'handcrafted_topology' (legacy) and 'low_topology' (current handcraft pipeline output)."""
    from dimwit import topology
    reports = list((ROOT / "artifacts" / "handcraft").glob("*/*_handcraft.json"))
    if not reports:
        raise BlockedError("no handcrafted assets produced yet (run dimwit.topology.handcraft)")
    bad = []
    for rp in reports:
        try:
            d = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw = d.get("handcrafted_topology") or d.get("low_topology") or {}
        m = _normalize_handcraft_topo(raw, outer=d)
        qa = topology.topology_qa(m)
        if not qa.get("passed"):
            bad.append({"asset": d.get("name"), "issues": qa.get("issues", [])})
    if bad:
        joined = str(bad)
        hard = any(s in joined for s in ("triangle soup", "not watertight", "no UVs"))
        return fail(issues=[f"{b['asset']}: {'; '.join(b['issues'][:3])}" for b in bad][:6], hard=hard, bad=bad)
    return ok(handcrafted_assets=len(reports))


# ============================================================ OPTICS (semantic vision QA — closes G2)
def _live_optics_candidate() -> str | None:
    """The live-game character crop, ONLY when its metadata marks it as an optics candidate for
    the active character. Auxiliary evidence for the optics gate — never the primary subject."""
    meta_path = VAL_ART / "char_still_metadata.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if meta.get("subject_type") != "character_optics_candidate" or not _optics_metadata_matches_active_character(meta):
        return None
    for name in ("char_still_focused.png", "char_still.png"):
        p = VAL_ART / name
        if p.exists():
            return str(p)
    return None


def _best_optics_subject() -> str | None:
    """Primary judged subject for character optics (reworked 2026-07-02,
    ZYTHAN_MATERIAL_PRESENTATION_FIDELITY_V1):
    1. cap_rig_ship.png — the saved-display SceneCapture: streaming-true (batch runs
       -NoTextureStreaming, gated), staged in the map's proven-exposure zone, frames the whole
       character large. The highest-detail truthful render available.
    2. live-game crop (metadata-matched) — the character is small/edge-cropped in third person,
       so detail is unresolvable for the judge; used only when no display capture exists.
    The live crop additionally passes _live_subject_hue_sanity before it may serve as evidence
    (a live crop once photographed an enemy bot that walked in front of the camera).
    Returns None if nothing exists."""
    cap = VAL_ART / "cap_rig_ship.png"
    if cap.exists():
        return str(cap)
    return _live_optics_candidate()


def _live_subject_hue_sanity(crop_path, ref_path) -> dict:
    """Machine wrong-subject detector for the live optics crop (2026-07-02 incident: the crop
    heuristic locked onto an ORANGE enemy bot instead of the violet player character). Compares
    the dominant hue family of saturated pixels in the crop against the character's reference
    cover. Fails ONLY on a confident mismatch; desaturated/ambiguous crops are inconclusive-ok —
    quality judgment belongs to the semantic judge, this check only catches the wrong SUBJECT."""
    try:
        from PIL import Image
    except Exception as e:
        return {"ok": True, "inconclusive": True, "reason": f"PIL unavailable: {e}"}
    if not ref_path or not Path(str(ref_path)).exists():
        return {"ok": True, "inconclusive": True, "reason": "no reference cover"}

    def dominant_hue_bin(path, bins=12):
        im = Image.open(path).convert("HSV").resize((96, 96))
        px = list(im.getdata())
        hist = [0] * bins
        saturated = 0
        for h, s, v in px:
            if s > 64 and v > 40:            # saturated + not near-black
                saturated += 1
                hist[int(h * bins / 256) % bins] += 1
        frac = saturated / len(px)
        if frac < 0.02:
            return None, frac
        return max(range(bins), key=lambda i: hist[i]), frac

    crop_bin, crop_frac = dominant_hue_bin(str(crop_path))
    ref_bin, _ = dominant_hue_bin(str(ref_path))
    if crop_bin is None or ref_bin is None:
        return {"ok": True, "inconclusive": True, "reason": "insufficient saturation to identify subject",
                "crop_saturated_fraction": round(crop_frac, 4)}
    dist = min((crop_bin - ref_bin) % 12, (ref_bin - crop_bin) % 12)   # circular hue distance
    return {"ok": dist <= 2, "inconclusive": False, "crop_hue_bin": crop_bin, "ref_hue_bin": ref_bin,
            "hue_bin_distance": dist, "crop_saturated_fraction": round(crop_frac, 4)}


def _active_character_deformation_defect() -> dict | None:
    """User/operator visual defects are load-bearing evidence, not comments.

    A live deformation report must hard-fail character optics until a later fix artifact
    explicitly marks it resolved with new evidence.
    """
    p = VAL_ART / "character_deformation_review.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"state": "UNREADABLE", "issues": [f"character_deformation_review unreadable: {e}"]}
    state = str(data.get("state", "")).upper()
    active_states = {"USER_REPORTED_DEFECT", "OPERATOR_REPORTED_DEFECT", "FAIL", "FAILED", "REJECTED", "OPEN"}
    if state in active_states:
        issues = data.get("issues") or [data.get("issue") or "character_deformation_defect"]
        asset = data.get("asset") or data.get("subject") or ""
        return {
            "state": state,
            "issues": [str(i) for i in issues if i],
            "subject": data.get("subject"),
            "reported_by": data.get("reported_by"),
            "source": str(p),
            "asset": asset,
            "quarantined": is_quarantined_character(asset, ROOT),
        }
    return None


def v_optics_character_semantic(ctx):
    """Elite optics: GLM-5V SEMANTIC judgement of the in-game character render (catches morphed/disfigured/
    placeholder-geometry/off-model that pixel-stats rubber-stamp). Fused with pixel-truth.
    Subject priority: live lobby frame (anim_live_proof) > headless SceneCapture (cap_rig_ship.png).
    Reference: sym_covers/hi3d_02_ekris.png (the authoritative Hi3D render). Fail-closed: LLM down or
    no subject image -> BLOCKED, never a fake PASS."""
    from dimwit import optics, llm
    defect = _active_character_deformation_defect()
    if defect and not defect.get("quarantined"):
        ev = [defect["source"]]
        if defect.get("subject") and Path(str(defect["subject"])).exists():
            ev.append(str(defect["subject"]))
        return fail(
            issues=defect["issues"][:8],
            hard=True,
            evidence=ev,
            state=defect.get("state"),
            reported_by=defect.get("reported_by"),
            subject=defect.get("subject"),
        )
    if not llm.is_configured():
        raise BlockedError("vision-LLM not configured (no OPENROUTER_API_KEY)")
    subject = _best_optics_subject()
    if not subject:
        raise BlockedError("no character render available for optics (run scripts/capture/anim_live_capture.py or UE batch)")
    ref = ROOT / "artifacts" / "sym_covers" / f"{_primary_active_character().get('source_stem')}.png"
    # live-crop wrong-subject guard (2026-07-02: the crop once photographed an enemy bot):
    # a metadata-matched live candidate must hue-match the reference before it counts as evidence
    live = _live_optics_candidate()
    live_sanity = None
    if live:
        live_sanity = _live_subject_hue_sanity(live, str(ref) if ref.exists() else None)
        if not live_sanity.get("ok"):
            return fail(
                issues=["live optics crop photographs the WRONG SUBJECT (hue family mismatch vs "
                        f"reference: {live_sanity}) — the capture heuristic likely locked onto "
                        "another character; re-run scripts/capture/anim_live_capture.py"],
                hard=True, evidence=[live, str(ref)], live_subject_sanity=live_sanity)
    # H1B2: QUORUM judgement — the single-shot judge coin-flipped 0.4-0.65 for days over one
    # unchanged subject; verdicts now take a majority of 3 independent calls (median score,
    # blocked votes count against passing, single-call flake issues die in aggregation).
    v = optics.judge_character_quorum(subject, reference=str(ref) if ref.exists() else None,
                                      subject_only=True)  # hero/studio capture — measure character, not void backdrop
    if live and live_sanity is not None:
        v.setdefault("evidence", []).append(live)
        v["live_subject_sanity"] = live_sanity
    sem = v.get("semantic", {})
    quorum = v.get("quorum", {})
    if "blocked" in sem:
        raise BlockedError(f"optics semantic blocked: {sem['blocked']}")
    ev = v.get("evidence", [])
    if v.get("hard_fail"):
        return fail(score=v.get("score", 0.0), issues=v.get("issues", [])[:8], hard=True,
                    evidence=ev, severity=sem.get("severity"), summary=sem.get("summary"), quorum=quorum)
    if not v.get("passed"):
        return Verdict(score=v.get("score", 0.0), passed=False, issues=v.get("issues", [])[:8],
                       evidence=ev, detail={"severity": sem.get("severity"), "summary": sem.get("summary"),
                                            "subject": subject, "quorum": quorum})
    return Verdict(score=v.get("score", 1.0), passed=True, evidence=ev,
                   detail={"summary": sem.get("summary"), "subject": subject, "quorum": quorum})


def v_optics_judge_calibrated(ctx):
    """H1B2: the vision judge is itself a validator, so it gets validated. A golden set of captures
    with KNOWN verdicts (dimwit/goldens/optics: reference-grade renders that must PASS, washed
    low-mip/emissive-flattened renders that must FAIL) is re-judged through the production quorum
    lane by `python -m dimwit.optics_calibration`. A judge too lax to fail the bad goldens is
    rejected exactly like one too strict to pass the good ones — the non-weakening detector for
    prompt/model drift. Fail-closed: missing/stale (>7d)/manifest-drift artifact fails; no LLM
    calls happen in-suite (the artifact is the proof)."""
    from dimwit import optics_calibration as oc
    p = Path(ROOT) / "artifacts" / "optics_calibration" / "calibration_result.json"
    if not p.exists():
        return fail(issues=["no calibration artifact — run: python -m dimwit.optics_calibration"])
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return fail(issues=[f"unreadable calibration artifact: {e!r}"])
    age = time.time() - float(r.get("ts", 0))
    if age > oc.MAX_AGE_S:
        return fail(issues=[f"calibration stale: {age / 3600:.1f}h old (max {oc.MAX_AGE_S // 3600}h) — "
                            "re-run: python -m dimwit.optics_calibration"], age_h=round(age / 3600, 1))
    if int(r.get("quorum_n", 0)) < 3:
        return fail(issues=[f"calibration ran with quorum_n={r.get('quorum_n')!r} < 3"])
    if int(r.get("stability_runs", 1)) < 2:
        return fail(issues=[f"calibration proved only {r.get('stability_runs', 1)} stability round(s) — "
                            "a single lucky run is jitter-riding; re-run: python -m dimwit.optics_calibration"])
    try:
        current = oc.manifest_hash()
    except Exception as e:
        return fail(issues=[f"golden manifest unreadable: {e!r}"])
    if r.get("manifest_hash") != current:
        return fail(issues=["golden manifest/images changed since calibration — re-run: "
                            "python -m dimwit.optics_calibration"])
    if r.get("misclassified") or r.get("missing") or not r.get("ok"):
        return fail(issues=[f"JUDGE DRIFT: goldens misclassified={r.get('misclassified')} "
                            f"missing={r.get('missing')} — the vision judge no longer separates "
                            "known-good from known-bad captures; fix the judge, never the goldens"],
                    hard=True, misclassified=r.get("misclassified"), missing=r.get("missing"))
    return ok(total=r.get("total"), correct=r.get("correct"), quorum_n=r.get("quorum_n"),
              age_h=round(age / 3600, 1))


def v_anim_locomotion_pose_evaluates(ctx):
    """Proves the AnimBP state machine evaluates poses (not frozen at bind pose). Primary: headless rig_ship
    frames. Fallback: anim_live_proof.json — if the character moved in the lobby, AnimBP was evaluating.
    Fail-closed: neither proves motion -> BLOCKED."""
    import time as _time
    try:
        cap = ctx.ue_probe("captures").get("rig_ship", {})
    except BlockedError:
        cap = {}
    frames = cap.get("frames") or []
    if len(frames) >= 2:
        from dimwit import perception
        d = perception.image_delta(frames[0], frames[1])
        if d > 0.0 and d >= T["pose_delta_image_floor"]:
            return Verdict(score=1.0, passed=True, evidence=frames, detail={"delta": d, "source": "rig_ship"})
        if d > 0.0:
            return fail(issues=[f"low inter-frame delta {d} < {T['pose_delta_image_floor']}"], evidence=frames, delta=d)
        # d == 0 → headless frozen; fall through to live proof

    # ── fallback: live lobby proof from scripts/capture/anim_live_capture.py ─────────────────
    proof_path = VAL_ART / "anim_live_proof.json"
    if not proof_path.exists():
        raise BlockedError("headless render did not animate; no on-disk live proof — run scripts/capture/anim_live_capture.py")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    age_h = (_time.time() - proof.get("captured_at", 0)) / 3600
    if age_h > 12:
        raise BlockedError(f"anim_live_proof.json is {age_h:.1f}h old; re-run scripts/capture/anim_live_capture.py")
    pframes = [f for f in (proof.get("frames") or []) if Path(f).exists()]
    if len(pframes) < 2:
        raise BlockedError("live proof frames missing; re-run scripts/capture/anim_live_capture.py")
    max_delta = proof.get("max_delta", 0.0)
    if not proof.get("passed") or max_delta < T["pose_delta_image_floor"]:
        return fail(issues=[f"live proof: max_delta={max_delta:.5f} < threshold"],
                    evidence=pframes[:2], delta=max_delta)
    # Character locomotion requires AnimBP pose evaluation; proven by live motion evidence.
    return Verdict(score=min(1.0, max_delta / 0.1), passed=True, evidence=pframes[:2],
                   detail={"max_delta": max_delta, "age_hours": round(age_h, 2), "source": "anim_live_proof"})


# ============================================================ GAMEPLAY CODE
def v_lobby_skeletal_not_static(ctx):
    cpp = ctx.read_text(SRC / "Private" / "WanefallLobbyCharacter.cpp")
    has_sk = "SetSkeletalMeshAsset" in cpp and "FObjectFinder<USkeletalMesh>" in cpp
    m = re.search(r'CharactersRigged/(SM_Char_\w+_Rig)', cpp)
    rig_ref = bool(m)
    body_visible = bool(re.search(r"AlienBody->SetVisibility\(\s*true", cpp))
    if not has_sk or not rig_ref:
        return fail(issues=["lobby pawn not driving a skeletal rig as the body"], hard=True,
                    has_skeletal=has_sk, rig_ref=rig_ref)
    rig_name = m.group(1) if m else ""
    if is_quarantined_character(rig_name, ROOT):
        return fail(issues=[f"lobby pawn still references quarantined character rig {rig_name}"], hard=True,
                    rig_ref=rig_name)
    if body_visible:
        return fail(issues=["static AlienBody is set visible (frozen-blob risk)"], hard=True)
    return ok(rig_ref=rig_name)


def v_grapple_uproperties(ctx):
    h = ctx.read_text(SRC / "Public" / "WanefallPrototypeCharacter.h")
    cpp = ctx.read_text(SRC / "Private" / "WanefallPrototypeCharacter.cpp")
    comps = ["GrappleHand", "GrappleCableMesh", "GrappleAnchorMesh", "GrappleDevice"]
    missing = [c for c in comps if c not in h or f'CreateDefaultSubobject' not in cpp or c not in cpp]
    if missing:
        return fail(issues=[f"grapple components missing/not constructed: {missing}"], missing=missing)
    return ok()


def v_defaultinput_grapple(ctx):
    ini = ctx.read_text(PROJECT / "Config" / "DefaultInput.ini")
    has_q = "Grapple" in ini and "Q" in ini
    has_l1 = "Grapple" in ini and "Gamepad_LeftShoulder" in ini
    if not (has_q and has_l1):
        return fail(issues=["Grapple not mapped to Q + Gamepad_LeftShoulder"], has_q=has_q, has_l1=has_l1)
    return ok()


def v_both_targets_compile(ctx):
    build = Path("C:/UE_5.8/Engine/Build/BatchFiles/Build.bat")
    if not build.exists():
        raise BlockedError("UBT Build.bat not found")
    results = {}
    for tgt in ("WanefallGreyboxEditor", "WanefallGreybox"):
        cmd = [str(build), tgt, "Win64", "Development", f"-Project={ctx.uproject}", "-WaitMutex"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            raise BlockedError(f"{tgt} build timed out")
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"(\d+)\s+Error\(s\)", out)
        errs = int(m.group(1)) if m else (0 if "Result: Succeeded" in out else 1)
        results[tgt] = {"exit": r.returncode, "errors": errs, "succeeded": "Result: Succeeded" in out}
        if r.returncode != 0 or errs > 0 or "Result: Succeeded" not in out:
            return fail(issues=[f"{tgt} did not compile clean"], **results)
    return ok(**results)


def v_lobby_inrun_ship(ctx):
    # the regression-class the studio capture HIDES: dark-with-no-HDRI / grey-fallback in the actual lobby
    return v_rig_perception_ship(ctx)


# ============================================================ MATERIALS
def v_all_char_mic_parents_gltf(ctx):
    mats = _materials(ctx)
    bad = []
    for path, rec in mats.items():
        if not rec.get("loaded"):
            continue
        parent = _norm(rec.get("parent"))
        if PHONG.lower() in parent.lower():
            bad.append(path)
    if bad:
        return fail(issues=[f"legacy-Phong material parents: {bad}"], hard=True, bad=bad)
    return ok(checked=len(mats))


def v_mf_master_compile(ctx):
    data = ctx.result_json("materials_build_result.json")
    mf = data.get("mf", {})
    outs = mf.get("outputs")
    if outs is None:
        raise BlockedError("materials_build_result has no mf.outputs")
    n_out = len(outs) if isinstance(outs, (list, tuple)) else int(outs)
    bad_keys = [k for k in data if "err" in k.lower() and data[k]]
    if not mf.get("ok", True) or not mf.get("exists", True):
        return fail(issues=["MF_Wane not ok / does not exist"], hard=True, mf=mf)
    if n_out < 4:
        return fail(issues=[f"MF_Wane outputs {n_out} < 4"], outputs=n_out)
    master = data.get("master", {})
    if isinstance(master, dict) and (master.get("ok") is False or master.get("exists") is False):
        return fail(issues=["M_WaneSurface not ok / does not exist"], hard=True, master=master)
    if bad_keys:
        return fail(issues=[f"compile error keys present: {bad_keys}"], hard=True)
    return ok(outputs=n_out, master_ok=bool(master.get("ok", True)) if isinstance(master, dict) else None)


# ============================================================ ENVIRONMENT
def _env(ctx):
    return ctx.result_json("env_build_result.json")


def v_env_loads(ctx):
    d = _env(ctx)
    if d.get("error") or d.get("saved") is False:
        return fail(issues=[f"env build error/saved-false: {d.get('error')}"], hard=True)
    return ok()


def v_env_actor_count(ctx):
    placed = _env(ctx).get("placed")
    if placed is None:
        raise BlockedError("env placed count absent")
    if placed < T["env_actor_min"]:
        return fail(issues=[f"placed {placed} < {T['env_actor_min']}"], placed=placed)
    return ok(placed=placed)


def v_env_starts(ctx):
    starts = _env(ctx).get("starts")
    if starts is None:
        raise BlockedError("env starts absent")
    if starts < T["env_starts_min"]:
        return fail(issues=[f"starts {starts} < {T['env_starts_min']}"], starts=starts)
    return ok(starts=starts)


def v_env_lighting(ctx):
    lit = _env(ctx).get("lighting", {})
    miss = [k for k in ("directional", "sky", "fog") if not lit.get(k)]
    if miss:
        return fail(issues=[f"lighting missing: {miss}"], missing=miss)
    return ok()


def v_env_wane_line(ctx):
    wl = _env(ctx).get("wane_line", {})
    v, sp = wl.get("vein_count", 0), wl.get("spire_count", 0)
    if v < T["env_vein_min"] or sp < T["env_spire_min"]:
        return fail(issues=[f"WANE-LINE veins={v} spires={sp}"], veins=v, spires=sp)
    return ok(veins=v, spires=sp)


def v_frontend_maps_exist(ctx):
    maps_dir = CONTENT / "Wanefall" / "Maps"
    want = ["Wanefall_ModeShell_Prototype_01.umap"]
    missing = [m for m in want if not (maps_dir / m).exists() or (maps_dir / m).stat().st_size == 0]
    if missing:
        raise BlockedError(f"front-end maps missing/empty: {missing}")
    return ok(maps=want)


def v_frontdoor_deploy_spawn_safe(ctx):
    controller = ctx.read_text(SRC / "Private" / "WanefallLobbyPlayerController.cpp")
    match_gamemode = ctx.read_text(SRC / "Private" / "WanefallMatchGameMode.cpp")
    match_director = ctx.read_text(SRC / "Private" / "WanefallMatchDirector.cpp")
    arena_state_h = ctx.read_text(SRC / "Public" / "WanefallArena4v4GameState.h")
    health_h = ctx.read_text(SRC / "Public" / "WanefallPrototypeHealthComponent.h")
    health_cpp = ctx.read_text(SRC / "Private" / "WanefallPrototypeHealthComponent.cpp")
    maps_dir = CONTENT / "Wanefall" / "Maps"
    target_map = maps_dir / "Wanefall_Arena4v4_Prototype_01.umap"
    spawn_block = match_gamemode.split("void AWanefallMatchGameMode::BeginPlay", 1)[0]
    issues = []
    if "Wanefall_KitArena_01" in controller:
        issues.append("front-door deploy still routes to collision-prone Wanefall_KitArena_01")
    if "Wanefall_Arena4v4_Prototype_01" not in controller:
        issues.append("front-door deploy does not route to Wanefall_Arena4v4_Prototype_01")
    if not target_map.exists() or target_map.stat().st_size == 0:
        issues.append("spawn-safe front-door match map missing or empty")
    if "SpawnDefaultPawnAtTransform_Implementation" not in match_gamemode:
        issues.append("match GameMode does not override default pawn spawn")
    if "AdjustIfPossibleButAlwaysSpawn" not in match_gamemode:
        issues.append("match GameMode lacks spawn collision adjustment guard")
    if "SynchronizeBotRosterForCurrentRound" not in arena_state_h:
        issues.append("arena state exposes no safe roster/current-round synchronization seam")
    if "InArena->SynchronizeBotRosterForCurrentRound();" not in match_director:
        issues.append("match director does not reapply current round state to newly spawned bots")
    if "GrantDamageImmunity" not in health_h:
        issues.append("prototype health component exposes no deploy damage-immunity API")
    if "DamageImmunityUntilWorldTime" not in health_cpp:
        issues.append("prototype health component has no world-time damage-immunity guard")
    if "GrantDamageImmunity(10.0f)" not in spawn_block:
        issues.append("match GameMode does not grant the actual spawned front-door pawn a 10s grace")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(map="Wanefall_Arena4v4_Prototype_01", collision_guard=True, countdown_bot_sync=True, spawn_grace_seconds=10.0)


def v_frontdoor_live_deploy_proof(ctx):
    proof_path = VAL_ART / "anim_live_proof.json"
    if not proof_path.exists():
        raise BlockedError("no live front-door deploy proof; run scripts/capture/anim_live_capture.py with WANEFALL_ANIM_DEPLOY_FIRST=1")
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"anim_live_proof.json unreadable: {e}")

    age_h = (time.time() - float(proof.get("captured_at", 0))) / 3600
    if age_h > 12:
        raise BlockedError(f"anim_live_proof.json is {age_h:.1f}h old (> 12h); re-run front-door deploy proof")
    frames = [Path(f) for f in (proof.get("frames") or [])]
    existing_frames = [f for f in frames if f.exists()]
    if len(existing_frames) < 2:
        raise BlockedError("front-door deploy proof frames missing; re-run scripts/capture/anim_live_capture.py")
    max_delta = float(proof.get("max_delta") or 0.0)
    if not proof.get("passed") or max_delta < T["pose_delta_image_floor"]:
        return fail(issues=[f"front-door deploy proof has no live motion: max_delta={max_delta:.5f}"], hard=True,
                    max_delta=max_delta)
    proof_map = str(proof.get("map_url") or "")
    if not proof.get("deploy_first") or "Wanefall_ModeShell_Prototype_01" not in proof_map:
        return fail(issues=["anim_live_proof.json is not a command-shell front-door deploy proof"], hard=True,
                    map_url=proof.get("map_url"), deploy_first=proof.get("deploy_first"))
    if "Wanefall_Lobby" in proof_map or "Wanefall_TheHold" in proof_map:
        return fail(issues=["front-door proof still uses retired Lobby/Hold background map"], hard=True,
                    map_url=proof.get("map_url"))

    log_path = Path(proof.get("log_snapshot") or (VAL_ART / "frontdoor_live_deploy.log"))
    if not log_path.exists():
        raise BlockedError("front-door live deploy log snapshot missing; re-run scripts/capture/anim_live_capture.py")
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    arena_indices = [
        i for i, line in enumerate(lines)
        if "Browse:" in line and "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01" in line
    ]
    if not arena_indices:
        return fail(issues=["front-door proof log has no Arena4v4 deploy travel"], hard=True)
    start_idx = arena_indices[-1]
    segment = lines[start_idx:]
    if any("Wanefall_KitArena_01" in line for line in segment):
        return fail(issues=["front-door proof still traveled through Wanefall_KitArena_01"], hard=True)
    if not any("Game class is 'WanefallMatchGameMode'" in line for line in segment):
        return fail(issues=["front-door proof did not enter WanefallMatchGameMode"], hard=True)

    def log_seconds(line: str) -> float | None:
        m = re.search(r"\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2}):(\d{3})\]", line)
        if not m:
            return None
        hour, minute, second, ms = map(int, m.groups()[3:])
        return hour * 3600 + minute * 60 + second + ms / 1000.0

    immunity = next((line for line in segment if "WANEFALL deploy immunity: target=WanefallPrototypeCharacter_0" in line), None)
    if immunity is None:
        return fail(issues=["front-door proof log has no player deploy-immunity grant"], hard=True)
    immunity_t = log_seconds(immunity)
    if immunity_t is None:
        raise BlockedError("front-door proof log timestamp unreadable on deploy immunity line")

    first_damage = next((line for line in segment if "prototype damage: target=WanefallPrototypeCharacter_0" in line), None)
    seconds_to_damage = None
    if first_damage is not None:
        damage_t = log_seconds(first_damage)
        if damage_t is None:
            raise BlockedError("front-door proof log timestamp unreadable on first player damage line")
        seconds_to_damage = damage_t - immunity_t
        if seconds_to_damage < 9.5:
            return fail(issues=[f"player took damage {seconds_to_damage:.2f}s after deploy immunity (< 9.5s audit floor)"],
                        hard=True, first_damage_delay_seconds=round(seconds_to_damage, 3))

    return ok(
        max_delta=max_delta,
        age_hours=round(age_h, 2),
        frames=len(existing_frames),
        arena_map="Wanefall_Arena4v4_Prototype_01",
        first_damage_delay_seconds=None if seconds_to_damage is None else round(seconds_to_damage, 3),
        proof=str(proof_path),
        log=str(log_path),
        map_url=proof.get("map_url"),
    )


def v_lobby_umap_not_bloated(ctx):
    f = CONTENT / "Wanefall" / "Maps" / "Wanefall_ModeShell_Prototype_01.umap"
    if not f.exists():
        raise BlockedError("Wanefall_ModeShell_Prototype_01.umap missing")
    b = f.stat().st_size
    if b > T["lobby_umap_warn_bytes"]:
        return fail(issues=[f"ModeShell umap {b/1e6:.1f}MB > {T['lobby_umap_warn_bytes']/1e6}MB (bloated)"], bytes=b)
    return ok(bytes=b)


# ============================================================ VFX / AUDIO
def v_niagara_real(ctx):
    ns = ctx.ue_probe("niagara")
    not_niagara = [p for p, r in ns.items() if not r.get("is_niagara")]
    if not_niagara:
        return fail(issues=[f"not a NiagaraSystem: {not_niagara}"], bad=not_niagara)
    unknown = [p for p, r in ns.items() if r.get("emitter_count") is None]
    if unknown:
        raise BlockedError(f"emitter count not enumerable via Python API: {unknown}")
    zero = [p for p, r in ns.items() if r.get("emitter_count", 0) < 1]
    if zero:
        return fail(issues=[f"niagara 0-emitter: {zero}"], bad=zero)
    return ok(systems=list(ns.keys()))


def v_no_ai_slop_banter_fs(ctx):
    root = CONTENT / "Wanefall"
    sig = [s.lower() for s in T["banter_signature"]]
    hits = []
    for f in root.rglob("*.uasset"):
        n = f.stem.lower()
        if any(s in n for s in sig):
            hits.append(str(f.relative_to(CONTENT)))
    if hits:
        return fail(issues=[f"banter assets present (AI-slop reintroduced): {hits[:5]}"], hits=hits)
    return ok()


def v_vfx_asset_disk(ctx):
    vfx = CONTENT / "Wanefall" / "Dimwit" / "VFX"
    if not vfx.exists():
        raise BlockedError("VFX dir missing")
    stubs = [str(f.name) for f in vfx.glob("NS_Wane_*.uasset") if f.stat().st_size < T["vfx_stub_min_kb"] * 1024]
    found = list(vfx.glob("NS_Wane_*.uasset"))
    if not found:
        raise BlockedError("no NS_Wane_* assets")
    if stubs:
        return fail(issues=[f"VFX stubs < {T['vfx_stub_min_kb']}KB: {stubs}"], stubs=stubs)
    return ok(count=len(found))


def v_content_under_lfs(ctx):
    """Lock the content-versioning decision: authored Content/Wanefall stays Git-LFS-tracked.
    .gitattributes LFS contract + .gitignore carve-out + real on-disk assets resolving to filter=lfs."""
    from dimwit.pipelines.content_vcs import (
        REQUIRED_LFS_EXTS, CONTENT_ROOT, PROJECT as CV_PROJECT,
        live_gitattributes, live_gitignore,
        check_lfs_attrs, check_gitignore_carveout, check_assets_lfs_tracked,
    )
    ga = live_gitattributes()
    if ga is None:
        raise BlockedError(".gitattributes missing/unreadable")
    gi = live_gitignore()
    if gi is None:
        raise BlockedError(".gitignore missing/unreadable")
    a = check_lfs_attrs(ga)
    if not a["passed"]:
        return fail(issues=a["issues"], hard=True, missing=a.get("missing"))
    c = check_gitignore_carveout(gi)
    if not c["passed"]:
        return fail(issues=c["issues"], hard=True)
    t = check_assets_lfs_tracked(CV_PROJECT, CONTENT_ROOT)
    if t.get("blocked"):
        raise BlockedError(t["issues"][0])
    if not t["passed"]:
        return fail(issues=t["issues"], hard=True, untracked=t.get("untracked"))
    return ok(exts=len(REQUIRED_LFS_EXTS), assets_checked=t.get("checked"))


# ============================================================ CROSS-PIPELINE CONSISTENCY
def v_manifest_reconciliation(ctx):
    recs = ctx.result_json("char_fidelity_result.json").get("records", [])
    have = {(_norm(r.get("asset_id") or r.get("asset") or "")).split("/")[-1].lower() for r in recs}
    missing = [c for c in CHARS if c.lower() not in have]
    if missing:
        return fail(issues=[f"{len(missing)} humanoids never re-measured: {missing}"], missing=missing)
    return ok(count=len(have))


def v_reference_consistency(ctx):
    cpp = ctx.read_text(SRC / "Private" / "WanefallLobbyCharacter.cpp")
    m = re.search(r'CharactersRigged/(SM_Char_\w+_Rig)', cpp)
    if not m:
        return fail(issues=["lobby cpp references no rigged char asset"], hard=True)
    rig_name = m.group(1)
    if is_quarantined_character(rig_name, ROOT):
        return fail(issues=[f"lobby references quarantined character {rig_name}"], hard=True, rig=rig_name)
    rig_file = CONTENT / "Wanefall" / "Dimwit" / "CharactersRigged" / f"{rig_name}.uasset"
    if not rig_file.exists():
        return fail(issues=[f"lobby references {rig_name} which is not on disk"], hard=True, rig=rig_name)
    return ok(rig=rig_name)


def v_driver_result_freshness(ctx):
    """Each consumed *_result.json must not be older than the MESH assets it describes (stale self-report guard).
    Scope: StaticMesh uassets only — material uasset touches (re-application, colour tweaks) do not invalidate
    mesh geometry/Nanite data and should not trigger a spurious staleness flag."""
    checks = {
        "char_fidelity_result.json": CONTENT / "Wanefall" / "Dimwit" / "Characters",
        "env_build_result.json": CONTENT / "Wanefall" / "Maps",
    }
    stale = []
    for rj, tree in checks.items():
        p = ROOT / "artifacts" / rj
        if not p.exists() or not tree.exists():
            continue
        # Watch only StaticMesh uassets (subdirs named "StaticMeshes") — materials/textures touching fine.
        mesh_uassets = [
            f for f in tree.rglob("*.uasset")
            if "StaticMeshes" in f.parts or "SkeletalMeshes" in f.parts
        ]
        if not mesh_uassets:
            # Fallback: if directory layout has no StaticMeshes subdir, check all uassets
            mesh_uassets = list(tree.rglob("*.uasset"))
        newest = max((f.stat().st_mtime for f in mesh_uassets), default=0)
        if p.stat().st_mtime < newest - 1:
            stale.append(rj)
    if stale:
        return fail(issues=[f"stale result JSONs (older than the mesh assets): {stale}"], stale=stale)
    return ok()


# ============================================================ PROOF INTEGRITY / META
def v_ledger_chains_intact(ctx):
    from dimwit.engine import DimwitLedger
    led_dir = ROOT / "ledger"
    broken, midlegacy = [], []
    for lf in list((led_dir / "pipelines").glob("*.jsonl")) + [led_dir / "director.jsonl", led_dir / "validation.jsonl"]:
        if not lf.exists():
            continue
        cc = DimwitLedger(lf).consistency_check()
        if not cc["chain_ok"]:
            broken.append(lf.name)
        if cc.get("mid_ledger_legacy"):
            midlegacy.append(lf.name)
    if broken or midlegacy:
        return fail(issues=[f"broken chains: {broken}", f"mid-ledger legacy: {midlegacy}"], hard=True,
                    broken=broken, mid_ledger_legacy=midlegacy)
    return ok()


def v_no_autonomous_operator_states(ctx):
    from dimwit.pipelines.base import OPERATOR_ONLY
    led_dir = ROOT / "ledger"
    bad = []
    for lf in list((led_dir / "pipelines").glob("*.jsonl")) + [led_dir / "director.jsonl", led_dir / "validation.jsonl"]:
        if not lf.exists():
            continue
        for ln in lf.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            e = json.loads(ln)
            st = e.get("state", "").split(".")[-1]
            actor = e.get("actor", "")
            from dimwit.authority import is_ceiling_violation
            if is_ceiling_violation(e):
                bad.append({"ledger": lf.name, "state": st, "actor": actor})
    if bad:
        return fail(issues=[f"autonomous operator-only states: {bad[:3]}"], hard=True, bad=bad)
    return ok()


def v_threshold_ratchet(ctx):
    promo = ROOT / "config" / "promotion"
    if not promo.exists():
        raise BlockedError("promotion config dir missing")
    bad = []
    for f in promo.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        pt = d.get("promote_threshold", d.get("threshold", T["promote_floor"]))
        fl = d.get("threshold_floor", T["promote_floor"])
        if pt < T["promote_floor"] or fl < T["promote_floor"] or pt < fl:
            bad.append({"file": f.name, "promote": pt, "floor": fl})

    # --- hardened intent-contract loop: guard the fused-confidence review gate band.
    # The graduated-autonomy ladder ratchets UP only, inside [0.95, 0.99]. The gate can never be
    # lowered below the operator-chosen 0.95 start, nor raised past the 0.99 calibrated ceiling, and
    # the 0.99 ceiling itself is frozen (it is the destination, not a tunable). Reaching the gate is
    # never auto-acceptance — HUMAN_ACCEPTED / PROMOTED_TO_ACTIVE_SLICE stay operator-only.
    START_FLOOR, CEILING = 0.95, 0.99
    gate = T.get("suite_confidence_review_gate")
    ceil = T.get("suite_confidence_review_ceiling")
    if gate is None or ceil is None:
        bad.append({"gate": "suite_confidence_review_gate/ceiling missing from THRESHOLDS"})
    else:
        if ceil != CEILING:
            bad.append({"ceiling": ceil, "expected": CEILING, "why": "0.99 destination is frozen"})
        if not (START_FLOOR <= gate <= ceil):
            bad.append({"gate": gate, "why": f"must stay in [{START_FLOOR}, {ceil}] (ratchet up only)"})

    # The strict asset_type rows may never be silently weakened — these are the gates that caught the
    # disfigured mesh the pixel-stats rubber-stamped. Any drop below them is a doctrine breach, not a tweak.
    for at in ("character", "enemy", "hostile_construct_enemy", "vehicle", "weapon", "default", "_unknown"):
        row = ASSET_TYPE_FLOORS.get(at, {})
        if not row:
            bad.append({"asset_type": at, "why": "strict asset_type row missing from ASSET_TYPE_FLOORS"})
            continue
        if not row.get("require_perception", False):
            bad.append({"asset_type": at, "why": "require_perception must stay True (pixel-truth gate)"})
        if not row.get("require_optics_semantic", False):
            bad.append({"asset_type": at, "why": "require_optics_semantic must stay True (disfigurement/identity gate)"})
        dn = row.get("min_required_domains", [])
        for need in ("perception", "optics", "intent_conformance"):
            if need not in dn:
                bad.append({"asset_type": at, "why": f"min_required_domains must include {need}"})
        if "motion" not in row.get("required_capture_stages", []):
            bad.append({"asset_type": at, "why": "required_capture_stages must include motion (anim BLOCKER)"})

    # Every asset_type's per-build fused gate stays inside the band (no row may opt out of the floor).
    for at, row in ASSET_TYPE_FLOORS.items():
        cf = row.get("confidence_floor")
        if cf is None or not (START_FLOOR <= cf <= CEILING):
            bad.append({"asset_type": at, "confidence_floor": cf, "why": f"must be in [{START_FLOOR}, {CEILING}]"})

    if bad:
        return fail(issues=[f"threshold/floor ratchet violations: {bad[:8]}"], bad=bad)
    return ok()


def v_provenance_fail_closed(ctx):
    from dimwit.pipelines.base import ProductionPipeline, Artifact
    pp = ProductionPipeline.__new__(ProductionPipeline)
    if pp._provenance_ok(Artifact("x", "k", {}, {"source": "s"})) is not False:
        return fail(issues=["_provenance_ok passed a license-less artifact"], hard=True)
    if pp._provenance_ok(Artifact("x", "k", {}, {})) is not False:
        return fail(issues=["_provenance_ok passed an empty-provenance artifact"], hard=True)
    if pp._provenance_ok(Artifact("x", "k", {}, {"source": "s", "license": "CC0"})) is not True:
        return fail(issues=["_provenance_ok rejected a valid artifact (over-strict)"])
    return ok()


def v_capture_no_filesize_validity(ctx):
    scripts = ["scripts/ue/ue_capture_studio.py", "scripts/ue/ue_capture_hold.py", "scripts/ue/ue_validation_probe.py",
               "dimwit/pipelines/validation.py", "dimwit/pipelines/validation_registry.py"]
    offenders = []
    pat = re.compile(r"(passed\s*=.*png_bytes|Verdict\([^)]*png_bytes|ok\s*=\s*.*png_bytes\s*>)")
    for s in scripts:
        p = ROOT / s
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        for ln in txt.splitlines():
            if pat.search(ln):
                offenders.append({"file": s, "line": ln.strip()[:80]})
    if offenders:
        return fail(issues=[f"byte-size-as-validity: {offenders}"], offenders=offenders)
    return ok()


def v_perception_wiring_exists(ctx):
    from dimwit import perception
    need = ["analyze_image", "measure_style_compliance", "image_delta", "image_mirror_diff", "MEAN_LUMINANCE_FLOOR"]
    missing = [n for n in need if not hasattr(perception, n)]
    if missing:
        return fail(issues=[f"perception missing symbols (validators would stub): {missing}"], missing=missing)
    return ok()


def v_provenance_sources_on_disk(ctx):
    """G15: provenance is no longer trusted as a string — verify each character's recorded geometry SOURCE is a
    real file on disk. A promoted asset whose source GLB doesn't exist is unverifiable provenance -> hard fail."""
    recs = ctx.result_json("char_fidelity_result.json").get("records", [])
    if not recs:
        raise BlockedError("no char fidelity records to verify provenance against")
    missing, verified = [], 0
    for r in recs:
        src = r.get("src")
        if not src:
            missing.append({"asset": r.get("asset"), "why": "no source recorded"}); continue
        cands = [ROOT / "artifacts" / f"{src}.glb", ROOT / "artifacts" / f"{src}_sym.glb"]
        if any(c.exists() for c in cands):
            verified += 1
        else:
            missing.append({"asset": r.get("asset"), "source": src, "why": "source GLB not on disk"})
    if missing:
        return fail(issues=[f"unverifiable provenance: {m}" for m in missing][:5], hard=True, missing=missing)
    return ok(verified=verified)


def v_golden_regression_corpus(ctx):
    """Replay committed known-BAD / known-GOOD fixtures; assert each FAILS bad and PASSES good every run."""
    from dimwit import perception
    fx = ROOT / "dimwit" / "pipelines" / "fixtures"
    if not fx.exists():
        raise BlockedError("fixtures dir missing")
    failures = []
    # perception fixtures: bad (dark/magenta) must hard_fail; good (silver) must not
    cases = [("bad_dark.png", True), ("bad_magenta.png", True), ("good_silver.png", False)]
    for name, should_fail in cases:
        p = fx / name
        if not p.exists():
            continue
        style = perception.measure_style_compliance(perception.analyze_image(p))
        hard = bool(style.get("hard_fails"))
        if hard != should_fail:
            failures.append({"fixture": name, "expected_hardfail": should_fail, "got": hard})
    # material fixtures: phong JSON must be detected as phong
    pj = fx / "bad_phong_material.json"
    if pj.exists():
        rec = json.loads(pj.read_text())
        is_phong = PHONG.lower() in _norm(rec.get("parent")).lower()
        if not is_phong:
            failures.append({"fixture": "bad_phong_material.json", "expected": "phong-detected", "got": "missed"})
    if failures:
        return fail(issues=[f"golden corpus regressions: {failures}"], hard=True, failures=failures)
    return ok(cases=len(cases))


# ============================================================ intent_conformance (the per-build contract gate)
def v_intent_contract_no_drift(ctx):
    """BLOCKER: the per-build intent contract — the declared 'initial picture/goals/design' — must not have
    been retro-fitted to the result. Catches a tampered scored rubric, a swapped on-disk contract, a global
    DESIGN.md that drifted under the build, and a contract that was never anchored in the proof ledger.
    n/a (PASS) in project-wide validation mode where there is no per-build contract."""
    c = getattr(ctx, "contract", None)
    if not c:
        return ok(note="project-wide validation: no per-build intent contract (n/a)")
    from dimwit.spec_author import intent_hash_of, _design_md_hash
    issues = []
    if intent_hash_of(c) != c.get("intent_hash"):
        issues.append("intent_hash mismatch — the scored rubric was tampered after authoring")
    dl = c.get("design_law", {}) or {}
    cur = _design_md_hash(dl.get("design_md_path"))
    if dl.get("design_md_hash") and cur and dl["design_md_hash"] != cur:
        issues.append("DESIGN.md hash drifted since authoring — the global visual law changed under the build")
    if not c.get("anchored") or not c.get("anchor_entry_hash"):
        issues.append("intent contract was never anchored in the proof ledger before generation (anti-retrofit)")
    cp = getattr(ctx, "contract_path", None)
    if cp and Path(cp).exists():
        try:
            disk = json.loads(Path(cp).read_text(encoding="utf-8"))
        except Exception as e:
            raise BlockedError(f"on-disk intent_contract.json unreadable: {e}")
        if disk.get("intent_hash") != c.get("intent_hash"):
            issues.append("on-disk intent_contract.json was swapped after authoring (intent_hash differs)")
    if issues:
        return fail(issues=issues, hard=True, intent_hash=c.get("intent_hash"))
    return ok(intent_hash=c.get("intent_hash"))


def v_intent_target_conformance(ctx):
    """BLOCKER: the final capture must MATCH the declared reference picture (silhouette + region identity),
    not merely score a high style-mean. This is what stops a flawless render of the WRONG asset from passing.
    Returns target_similarity in detail so the suite fuse reads it as the identity axis. n/a in project-wide mode."""
    c = getattr(ctx, "contract", None)
    if not c:
        return ok(note="project-wide validation: no per-build intent contract (n/a)")
    acc = c.get("acceptance", {}) or {}
    refs = (c.get("expected_appearance", {}) or {}).get("reference_images", []) or []
    floor = max(float(acc.get("target_match_floor", 0.0) or 0.0), float(ctx.floors().get("target_match_floor", 0.85)))
    if not refs:
        if acc.get("allow_textonly_target"):
            return ok(note="text-only target (loose type): no reference image to match", target_similarity=None)
        return fail(issues=["strict build declares no reference image and allow_textonly_target is false"],
                    hard=True, target_similarity=None)
    ref = refs[0]
    cap = getattr(ctx, "capture_png", None)
    if not cap or not Path(cap).exists():
        raise BlockedError("intent target conformance: no final capture to compare to the declared reference")
    if not Path(ref).exists():
        raise BlockedError(f"declared reference image missing on disk: {ref}")
    from dimwit import perception
    cmp = perception.compare_to_target(str(cap), str(ref))
    if not cmp.get("ok") or cmp.get("target_similarity") is None:
        raise BlockedError(f"target comparison could not be computed: {cmp.get('reason', 'unknown')}")
    ts = float(cmp["target_similarity"])
    detail = {"target_similarity": ts, "silhouette_iou": cmp.get("silhouette_iou"),
              "region_match": cmp.get("region_match"), "palette_sim": cmp.get("palette_sim"), "floor": floor}
    if ts < floor:
        return fail(score=ts, issues=[f"capture does not match the declared reference: "
                                      f"target_similarity {ts:.3f} < floor {floor:.3f}"], **detail)
    return ok(score=ts, **detail)


# ============================================================ rig deformation (the #32 layer, suite-level)
def v_rig_deformation(ctx):
    """BLOCKER: the rigged mesh must DEFORM cleanly across the stress poses — the layer structural rig QA
    (weights/influences/bones) is blind to. Reads the latest pose capture (scripts/ue/ue_capture_poses.py output) and
    runs the pixel-truth deformation QA. n/a (PASS) when no capture is present (the per-run RiggingPipeline.qa
    is the per-build gate). FAIL-CLOSED: a FROZEN capture (poses identical to bind — the headless-anim trap)
    or a collapsing/exploding/torn pose hard-fails; it must never pass just because a still frame is clean."""
    res_path = ROOT / "artifacts" / "pose_capture_result.json"
    if not res_path.exists():
        # FAIL-CLOSED (Z1a): a motion-gated rig with NO deformation capture is UNPROVEN, not "n/a".
        # Returning ok() here was a vacuous green that let frozen/uncaptured rigs pass the suite.
        raise BlockedError(
            "no rig pose-deformation capture present (artifacts/pose_capture_result.json); the motion-gated "
            "rig is UNPROVEN until a pose capture exists (run scripts/ue/ue_capture_poses.py). Fail-closed: never green "
            "without deformation proof.")
    try:
        res = json.loads(res_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"pose_capture_result.json unreadable: {e}")
    bind = res.get("bind")
    poses = {n: p for n, p in (res.get("poses") or {}).items() if n != "bind"}
    if not bind or len(poses) < 3:
        return fail(issues=[f"rig deformation capture incomplete: need bind + >=3 stress poses "
                            f"(got bind={bool(bind)}, {len(poses)} poses)"], hard=True)
    from dimwit import perception
    r = perception.rig_deformation_over_poses(bind, poses)
    if r.get("blocked"):
        return fail(issues=[f"rig deformation NOT certifiable (fail-closed): {r.get('reason')}"],
                    hard=True, deformation=r)
    if not r.get("passed"):
        worst = r.get("worst_pose")
        wd = (r.get("per_pose", {}) or {}).get(worst, {}) or {}
        return fail(score=r.get("deformation_score") or 0.0,
                    issues=[f"rig deformation FAIL at worst pose '{worst}': " + "; ".join(wd.get("issues", []))],
                    deformation=r)
    return ok(score=r.get("deformation_score"), worst_pose=r.get("worst_pose"))


def _pose_capture_artifact():
    """Load pose_capture_result.json fail-closed (shared by the H1B3 deformation gates)."""
    p = Path(ROOT) / "artifacts" / "pose_capture_result.json"
    if not p.exists():
        raise BlockedError("no rig pose-deformation capture present (artifacts/pose_capture_result.json)")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"pose_capture_result.json unreadable: {e}")


def v_rig_deform_identity_bound(ctx):
    """H1B3: deformation evidence must BE evidence about the ACTIVE character's CURRENT rig.
    The restored ekris-era capture kept rig_deformation_clean green for days while zythan (the
    active character) shipped deformation-unproven — the artifact never said WHO it photographed.
    Load-bearing now: subject tokens must match the active roster character, and the rig .uasset
    sha256 recorded at capture time must match the file on disk (a re-import/re-skin silently
    invalidates old pose evidence). Fail-closed: the pre-identity schema hard-fails."""
    r = _pose_capture_artifact()
    subject = r.get("subject_character")
    if not subject or not r.get("rig_asset") or not r.get("rig_uasset_sha256"):
        return fail(issues=["pose evidence declares no subject identity/rig binding (pre-H1B3 "
                            "ekris-era schema) — recapture via scripts/capture/ue_mrq_capture.py emit_capture_artifacts_v2"],
                    hard=True, source=r.get("source"))
    if not _optics_metadata_matches_active_character({"subject_character": subject,
                                                      "asset_name": r.get("rig_asset")}):
        return fail(issues=[f"pose evidence photographs '{subject}' but that is NOT the active "
                            "character — stale-roster deformation proof is no proof"],
                    hard=True, subject=subject)
    rel = str(r["rig_asset"]).replace("/Game/", "").lstrip("/").split(".")[0]
    rig_file = CONTENT / (rel + ".uasset")
    if not rig_file.exists():
        return fail(issues=[f"declared rig uasset missing on disk: {rig_file}"], hard=True)
    disk = __import__("hashlib").sha256(rig_file.read_bytes()).hexdigest()
    if disk != r["rig_uasset_sha256"]:
        return fail(issues=["rig .uasset changed since the pose capture (re-import/re-skin) — "
                            "deformation evidence is about a rig that no longer exists; recapture"],
                    recorded=r["rig_uasset_sha256"][:12], on_disk=disk[:12])
    return ok(subject=subject, rig_sha256=disk[:12])


# key joints a locomotion stress clip must actually swing; a frozen or partially-frozen clip
# (e.g. upper body never evaluated) proves nothing about those joints' skinning
_DEFORM_KEY_JOINTS = ("thigh_l", "thigh_r", "calf_l", "calf_r",
                      "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r")
_DEFORM_JOINT_FLOOR_DEG = 12.0


def v_rig_deform_joints_articulated(ctx):
    """H1B3: per-joint articulation telemetry — the pose evidence must prove the key limb joints
    each actually rotated through the captured clip (bone-space angular range sampled from the
    exact anim used, recorded at capture time). Pixel displacement alone can ride on one swinging
    arm while the rest of the body never evaluates. Fail-closed on missing telemetry."""
    r = _pose_capture_artifact()
    ja = r.get("joint_articulation")
    if not isinstance(ja, dict) or not isinstance(ja.get("max_rot_delta_deg"), dict):
        return fail(issues=["no joint_articulation telemetry in pose evidence (pre-H1B3 schema) — "
                            "recapture via scripts/capture/ue_mrq_capture.py emit_capture_artifacts_v2"], hard=True)
    if int(ja.get("frames_sampled", 0)) < 8:
        return fail(issues=[f"joint articulation sampled from only {ja.get('frames_sampled')} frames (<8)"])
    deg = ja["max_rot_delta_deg"]
    weak = {j: deg.get(j) for j in _DEFORM_KEY_JOINTS
            if not isinstance(deg.get(j), (int, float)) or float(deg.get(j)) < _DEFORM_JOINT_FLOOR_DEG}
    if weak:
        return fail(issues=[f"key joint under-articulated in the captured clip (floor "
                            f"{_DEFORM_JOINT_FLOOR_DEG} deg): {j}={d}" for j, d in weak.items()],
                    weak_joints=weak)
    return ok(min_key_joint_deg=min(float(deg[j]) for j in _DEFORM_KEY_JOINTS),
              frames_sampled=ja.get("frames_sampled"))


def v_rig_deform_silhouette_judged(ctx):
    """H1B3: judged silhouette — bind + EVERY stress pose carries a recorded verdict from the
    calibrated cross-vendor quorum (reference-free: readable / correctly proportioned / not
    disfigured / clean silhouette), judged at capture time by a judge bound to the CURRENT golden
    calibration manifest. Pixel metrics can miss semantic breakage (candy-wrapper twists, melted
    hands) that a judge sees instantly. Fail-closed: unjudged frames or a goldens-drifted judge
    prove nothing."""
    from dimwit import optics_calibration as oc
    r = _pose_capture_artifact()
    sv = r.get("silhouette_verdicts")
    if not isinstance(sv, dict) or not sv:
        return fail(issues=["no silhouette_verdicts in pose evidence (pre-H1B3 schema) — recapture "
                            "via scripts/capture/ue_mrq_capture.py emit_capture_artifacts_v2"], hard=True)
    need = ["bind"] + sorted((r.get("poses") or {}).keys())
    unjudged = [k for k in need if k not in sv]
    if unjudged:
        return fail(issues=[f"pose frames never judged: {unjudged}"])
    try:
        current = oc.manifest_hash()
    except Exception as e:
        return fail(issues=[f"golden manifest unreadable: {e!r}"])
    if r.get("judge_calibration_manifest_hash") != current:
        return fail(issues=["pose verdicts were judged under a DIFFERENT golden calibration than the "
                            "current one — re-judge the capture (re-run emit_capture_artifacts_v2)"])
    bad = {k: v for k, v in sv.items() if not v.get("passed")}
    if bad:
        issues = [f"{k}: " + "; ".join((v.get("issues") or ["judge failed the frame"])[:3])
                  for k, v in bad.items()]
        return fail(issues=issues, hard=any(v.get("hard_fail") for v in bad.values()),
                    failed_frames=sorted(bad.keys()))
    thin = [k for k in need if int((sv[k].get("quorum") or {}).get("n", 0)) < 3]
    if thin:
        return fail(issues=[f"frames judged without a full quorum (n<3): {thin}"])
    return ok(frames_judged=len(need),
              min_score=min(float(sv[k].get("score", 0.0)) for k in need))


def v_mrq_capture_advanced(ctx):
    """BLOCKER: the MovieRenderQueue animated capture must contain GENUINELY ADVANCING frames — the Z2 unlock
    that defeats the frozen-bind-pose trap every prior capture method fell into (offscreen SceneCapture2D,
    PoseableMesh, leader-pose, PIE+AlwaysTickPose, Sequencer-scrub all rendered the frozen bind pose). Reads
    artifacts/mrq_capture_result.json (scripts/capture/ue_mrq_capture.py): the avg consecutive inter-frame pixel delta over the
    rendered sequence. FAIL-CLOSED: absent capture BLOCKS (motion unproven); a frozen sequence hard-fails."""
    res_path = ROOT / "artifacts" / "mrq_capture_result.json"
    if not res_path.exists():
        raise BlockedError("no MRQ capture result (artifacts/mrq_capture_result.json); render one with "
                           "scripts/capture/ue_mrq_capture.py. Fail-closed: animated motion is UNPROVEN without an "
                           "advancing-frame capture.")
    try:
        r = json.loads(res_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"mrq_capture_result.json unreadable: {e}")
    n = r.get("frame_count", 0)
    adv = r.get("avg_consecutive_delta")
    if not isinstance(n, int) or n < 8 or adv is None:
        return fail(issues=[f"MRQ capture incomplete: frame_count={n}, avg_consecutive_delta={adv}"], hard=True, mrq=r)
    if float(adv) <= 0.3:
        return fail(score=0.0, hard=True,
                    issues=[f"FROZEN MRQ capture: avg consecutive frame delta {adv} <= 0.3 — the animation did "
                            f"not advance across the rendered frames (bind-pose trap)"], mrq=r)
    return ok(score=min(1.0, float(adv) / 2.0), frames=n, avg_consecutive_delta=adv, advancing=True)


def v_combat_state_clarity(ctx):
    """BLOCKER: the enemy's LIVE / HIT / DESTROYED states must be MUTUALLY, unmistakably distinct — a hit that
    looks like the live state, or a destroyed husk identical to alive, gives the player NO combat feedback.
    Reads artifacts/combat_capture_result.json (the -WANEFALLHEROCAPTURE 3-state hero capture)."""
    res_path = ROOT / "artifacts" / "combat_capture_result.json"
    if not res_path.exists():
        raise BlockedError("no combat capture (artifacts/combat_capture_result.json); run the -WANEFALLHEROCAPTURE "
                           "hero capture. Fail-closed: combat state clarity is UNPROVEN without the 3-state capture.")
    try:
        r = json.loads(res_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"combat_capture_result.json unreadable: {e}")
    sd = r.get("state_deltas") or {}
    mn = r.get("min_state_delta")
    if mn is None or len(sd) < 3:
        return fail(issues=[f"combat capture incomplete: state_deltas={sd}"], hard=True, combat=r)
    if float(mn) <= 3.0:
        worst = min(sd, key=sd.get)
        return fail(score=0.0, hard=True, combat=r,
                    issues=[f"combat states NOT distinct: weakest pair '{worst}' delta {sd.get(worst)} <= 3.0 — "
                            f"the player cannot read the state change"])
    return ok(score=min(1.0, float(mn) / 10.0), state_deltas=sd, min_state_delta=mn)


def v_combat_weakpoint_in_range(ctx):
    """BLOCKER: the in-range weak-point must read as a targetable RED core (red dominates orange AND is actually
    present), not a washed/desaturated orange. Reads artifacts/combat_capture_result.json."""
    res_path = ROOT / "artifacts" / "combat_capture_result.json"
    if not res_path.exists():
        raise BlockedError("no combat capture (artifacts/combat_capture_result.json); run the -WANEFALLHEROCAPTURE hero capture.")
    try:
        r = json.loads(res_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"combat_capture_result.json unreadable: {e}")
    red = float(r.get("weakpoint_red_pct") or 0.0)
    orange = float(r.get("weakpoint_orange_pct") or 0.0)
    if red < 1.0:
        return fail(score=0.0, hard=True, combat=r,
                    issues=[f"weak-point not visible: red {red}% < 1% (no readable in-range red core)"])
    if red <= orange:
        return fail(score=0.0, hard=True, combat=r,
                    issues=[f"weak-point washed: red {red}% <= orange {orange}% (reads orange/desaturated, not RED)"])
    return ok(score=min(1.0, red / 10.0), red_pct=red, orange_pct=orange)


# ============================================================ MOVEMENT / TRAVERSAL (the signature "gun + swing" feel)
def _traversal(ctx):
    p = ROOT / "artifacts" / "traversal_capture_result.json"
    if not p.exists():
        raise BlockedError("no traversal capture (artifacts/traversal_capture_result.json); drive the *ForProof "
                           "maneuvers (grapple/mantle/flip/agility) + capture. Fail-closed: traversal feel is "
                           "UNPROVEN without a motion capture.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"traversal_capture_result.json unreadable: {e}")


def v_traversal_maneuvers_fire(ctx):
    """BLOCKER: the signature traversal verbs must actually FIRE in a live/proof run — grapple attach, smart
    mantle/vault, boost-flip, and at least one agility cut. A traversal system that compiles but never triggers
    gives the player none of the 'Spider-Man with a gun' identity. Fail-closed: no capture -> BLOCKED."""
    r = _traversal(ctx)
    m = r.get("maneuvers") or {}
    need = {"grapple": (m.get("grapple") or {}).get("fired"),
            "mantle": (m.get("mantle") or {}).get("fired"),
            "flip": (m.get("flip") or {}).get("fired")}
    dead = [k for k, v in need.items() if v is not True]
    cuts = int(m.get("agility_cuts") or 0)
    if dead or cuts < 1:
        return fail(issues=[f"traversal verbs that did not fire: {dead or '[]'}; agility_cuts={cuts}"],
                    hard=True, maneuvers=m)
    return ok(maneuvers=need, agility_cuts=cuts)


def v_traversal_grapple_continuous(ctx):
    """BLOCKER: the grapple must read as a CONTINUOUS swing/yank that carries the body across real distance — not a
    one-frame teleport-snap to the anchor. Proven by real displacement, multiple motion samples, and no single
    sample-to-sample jump that swallows most of the travel (the teleport tell). The elite-feel gate."""
    r = _traversal(ctx)
    g = (r.get("maneuvers") or {}).get("grapple") or {}
    disp = float(g.get("displacement_cm") or 0.0)
    samples = int(g.get("samples") or 0)
    jump = float(g.get("max_sample_jump_cm") if g.get("max_sample_jump_cm") is not None else disp)
    if disp < 300.0:
        return fail(score=0.0, hard=True, grapple=g,
                    issues=[f"grapple displacement {disp}cm < 300cm — the swing barely moved the player (no real traversal)"])
    if samples < 4:
        return fail(score=0.0, hard=True, grapple=g,
                    issues=[f"grapple captured only {samples} motion samples (<4) — cannot prove a continuous arc vs a snap"])
    if jump > 0.6 * disp:
        return fail(score=0.0, hard=True, grapple=g,
                    issues=[f"grapple teleport-snap: one sample jumped {jump}cm of {disp}cm total (>60%) — reads as a warp, not a swing"])
    return ok(score=min(1.0, disp / 2000.0), displacement_cm=disp, samples=samples, max_sample_jump_cm=jump)


def v_traversal_flip_rotates(ctx):
    """BLOCKER: the boost-flip must produce REAL angular rotation of the body — a somersault that 'fires' but never
    rotates is a dead animation the player can't feel. The proof captures total mesh angular travel over the flip
    window (axis-agnostic quaternion delta, so it survives the mesh's resting yaw and the >90deg Euler-pitch wrap
    that silently read ~0). A full boost-flip sweeps 360deg; require >=180deg so a half/clipped/dead flip fails."""
    r = _traversal(ctx)
    f = (r.get("maneuvers") or {}).get("flip") or {}
    if f.get("fired") is not True:
        return fail(issues=["flip did not fire"], hard=True, flip=f)
    rot = f.get("rotation_deg")
    if rot is None:
        raise BlockedError("flip.rotation_deg not measured (older capture / sampler not upgraded to angular delta)")
    if float(rot) < 180.0:
        return fail(score=0.0, hard=True, flip=f,
                    issues=[f"boost-flip rotated only {float(rot):.1f}deg (<180) — the somersault did not visibly turn the body"])
    return ok(score=min(1.0, float(rot) / 360.0), rotation_deg=float(rot))


def v_traversal_motion_advances(ctx):
    """WARN: if a pixel-motion track was captured alongside the maneuvers, it must actually advance on screen
    (defeats 'state says it moved but the frame is frozen'). Behavioral fire/continuity are the BLOCKERs; this is
    the on-screen corroboration."""
    r = _traversal(ctx)
    mo = r.get("motion") or {}
    n = int(mo.get("frame_count") or 0)
    adv = mo.get("avg_consecutive_delta")
    if n < 2 or adv is None:
        return ok(note="no pixel-motion track in this capture (behavioral gate carries it)", motion=mo)
    if float(adv) <= 0.3:
        return fail(issues=[f"traversal pixel motion frozen: avg consecutive delta {adv} <= 0.3"], motion=mo)
    return ok(score=min(1.0, float(adv) / 2.0), frame_count=n, avg_consecutive_delta=adv)


# ============================================================ WEAPONS (in-play: white-weapon law + ADS reads)
def _weapons(ctx):
    p = ROOT / "artifacts" / "weapons_capture_result.json"
    if not p.exists():
        raise BlockedError("no weapons in-play capture (artifacts/weapons_capture_result.json); cycle the gun "
                           "registry in-hand + capture. Fail-closed: the white-weapon regression is UNPROVEN-clean "
                           "without a per-gun in-hand capture.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"weapons_capture_result.json unreadable: {e}")


def v_weapons_no_white_placeholder(ctx):
    """BLOCKER: every gun, captured IN-HAND, must read as dark gunmetal — not a white/grey placeholder. The
    permanent gate on the recurring white-weapon regression (SetVisibility re-revealing raw BasicShape sub-parts);
    RetintWeaponDark must hold across the whole registry. >=8% near-white pixels on the weapon = fail."""
    r = _weapons(ctx)
    guns = r.get("guns") or []
    if not guns:
        return fail(issues=["weapons capture has no per-gun records"], hard=True)
    # Fail-closed: a gun whose albedo was never measured (white_pct null = barely/not rendered) is UNPROVEN, not
    # "clean". Block rather than let an unrendered gun silently pass the white check.
    unmeasured = [g.get("id") for g in guns if g.get("white_pct") is None]
    if unmeasured:
        return fail(score=0.0, hard=True, unmeasured=unmeasured,
                    issues=[f"{len(unmeasured)} gun(s) had no measurable weapon pixels (capture/render failure, "
                            f"UNPROVEN-clean): {unmeasured[:5]}"])
    white = [(g.get("id"), g.get("white_pct")) for g in guns if float(g.get("white_pct")) >= 8.0]
    if white:
        return fail(score=0.0, hard=True, white=white,
                    issues=[f"white-weapon regression: {len(white)} gun(s) read >=8% near-white in-hand: {white[:5]}"])
    return ok(guns_checked=len(guns), max_white_pct=max((float(g.get("white_pct")) for g in guns), default=0.0))


def v_weapons_ads_changes_camera(ctx):
    """BLOCKER: aiming-down-sights must actually change the camera (tighter FOV + shorter boom). An ADS that does
    not move the camera is a dead feature the player can't feel."""
    r = _weapons(ctx)
    a = r.get("ads") or {}
    hf, af, ha, aa = a.get("hip_fov"), a.get("ads_fov"), a.get("hip_arm"), a.get("ads_arm")
    if None in (hf, af, ha, aa):
        return fail(issues=[f"ADS capture incomplete: {a}"], hard=True, ads=a)
    if not (float(af) < float(hf) and float(aa) < float(ha)):
        return fail(score=0.0, hard=True, ads=a,
                    issues=[f"ADS does not tighten the camera: fov {hf}->{af}, arm {ha}->{aa} (expected both to drop)"])
    return ok(fov_hip=hf, fov_ads=af, arm_hip=ha, arm_ads=aa)


def v_weapons_muzzle_tracks_crosshair(ctx):
    """WARN: the 'with a gun' read — the muzzle should track the crosshair while the body runs/swings. Procedural,
    so a soft gate: corroborates the signature, doesn't block the slice."""
    r = _weapons(ctx)
    if r.get("muzzle_tracks_crosshair") is not True:
        return fail(issues=["muzzle does not track the crosshair (procedural weapon-aim off / not proven)"])
    return ok()


# ============================================================ HUD (live readability + DESIGN.md tokens)
def _hud(ctx):
    p = ROOT / "artifacts" / "hud_capture_result.json"
    if not p.exists():
        raise BlockedError("no HUD capture (artifacts/hud_capture_result.json); capture a live Match HUD frame + "
                           "measure it. Fail-closed: HUD readability is UNPROVEN without a live frame.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"hud_capture_result.json unreadable: {e}")


def v_hud_core_elements_present(ctx):
    """BLOCKER: the playable Match HUD must actually show its core elements — crosshair, health, and the mode/BR
    state. A HUD that compiles but renders blank gives the player no read."""
    r = _hud(ctx)
    e = r.get("elements") or {}
    missing = [k for k in ("crosshair", "health", "mode_state") if e.get(k) is not True]
    if missing:
        return fail(issues=[f"core HUD elements missing on the live frame: {missing}"], hard=True, elements=e)
    return ok(elements=e)


def v_hud_design_tokens(ctx):
    """BLOCKER: the HUD must speak the DESIGN.md color language — teal = ally/tactical present, not a stock-engine
    white/grey overlay. Keeps the HUD on the WANEFALL visual identity."""
    r = _hud(ctx)
    t = r.get("tokens") or {}
    teal = float(t.get("teal_pct") or 0.0)
    if teal < 0.5:
        return fail(issues=[f"HUD shows no Wane teal ({teal}% < 0.5%) — off the DESIGN.md tactical palette"], tokens=t)
    return ok(tokens=t)


def v_hud_legible(ctx):
    """BLOCKER: the HUD frame must clear a minimum contrast — a washed/low-contrast HUD is unreadable in play."""
    r = _hud(ctx)
    leg = r.get("legibility") or {}
    c = leg.get("contrast")
    if c is None:
        raise BlockedError("HUD legibility.contrast not measured")
    if float(c) < 0.10:
        return fail(score=float(c), issues=[f"HUD contrast {c} < 0.10 (washed/illegible)"], legibility=leg)
    return ok(contrast=c)


# ============================================================ BR LOOP (ring collapse + match resolve)
def _br(ctx):
    p = ROOT / "artifacts" / "br_loop_result.json"
    if not p.exists():
        raise BlockedError("no BR-loop sim result (artifacts/br_loop_result.json); run the BattleRoyale mode sim "
                           "(FWanefallModeSimHarness::BattleRoyale / RunLargeSuite). Fail-closed: the BR ring + "
                           "match resolution are UNPROVEN without a sim.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"br_loop_result.json unreadable: {e}")


def v_br_ring_collapses(ctx):
    """BLOCKER: the WANE-LINE / BR ring must actually CONTRACT the playable space over the match — the signature
    entropy pressure. A ring that never shrinks is not a battle royale. Anchored to the REAL sim
    (FWanefallModeSimHarness::BattleRoyale), which exposes shrink_stage + final zone_radius but NO initial radius
    (the sim never returns a start radius). Contraction is proven by multiple completed shrink stages (>=2 real
    contractions over the loop) plus a finite measured end radius — NOT by a fabricated start>end comparison."""
    r = _br(ctx)
    ring = r.get("ring") or {}
    if ring.get("collapsed") is not True:
        return fail(issues=["BR ring never collapsed"], hard=True, ring=ring)
    er = ring.get("end_radius")
    steps = int(ring.get("shrink_steps") or 0)
    if steps < 2:
        return fail(issues=[f"BR ring did not contract over the loop: shrink_steps={steps} (<2 real contractions)"],
                    hard=True, ring=ring)
    if er is None or float(er) < 0.0:
        return fail(issues=[f"BR ring end_radius not measured / invalid: {er}"], hard=True, ring=ring)
    return ok(end_radius=er, shrink_steps=steps)


def v_br_match_resolves(ctx):
    """BLOCKER: the BR match must resolve to a single last-standing survivor with real attrition (combatants
    eliminated over the loop). A match that never ends, or ends with everyone alive, is a broken loop. Anchored to
    the REAL sim (LAST_STANDING_alive_N): the sim resolves by attrition to exactly one survivor and does NOT emit a
    winner NAME — so resolution is proven by resolved==True AND end_combatants==1 AND start>end attrition, NOT by a
    fabricated winner string. Requiring exactly-one-survivor is stricter than the prior any-attrition check."""
    r = _br(ctx)
    m = r.get("match") or {}
    if m.get("resolved") is not True:
        return fail(issues=[f"BR match did not resolve (resolved!=True): {m}"], hard=True, match=m)
    sc, ec = m.get("start_combatants"), m.get("end_combatants")
    if sc is None or ec is None or not (int(ec) < int(sc)):
        return fail(issues=[f"BR match had no attrition: start={sc} end={ec}"], hard=True, match=m)
    if int(ec) != 1:
        return fail(issues=[f"BR match did not resolve to exactly one survivor: end_combatants={ec}"],
                    hard=True, match=m)
    return ok(start_combatants=sc, end_combatants=ec, survivors=int(ec))


def v_br_topdown_reads(ctx):
    """WARN: if a top-down arena frame was captured, lanes/cover must read (minimum contrast). Soft — the sim
    BLOCKERs carry the loop; this corroborates spatial readability."""
    r = _br(ctx)
    td = r.get("topdown") or {}
    lc = td.get("lane_contrast")
    if lc is None:
        return ok(note="no top-down readability capture (sim gate carries the loop)")
    if float(lc) < 0.10:
        return fail(issues=[f"top-down arena low-contrast {lc} < 0.10 (lanes/cover don't read)"], topdown=td)
    return ok(lane_contrast=lc)


# ============================================================ FACET 2 — WEAPONS (deeper layer)
def v_weapon_registry_mesh_resolves(ctx):
    """BLOCKER: all 25 gun meshes in the live content tree must be on disk as .uasset. A gun that compiles
    into a registry slot but has no content file is a broken entry — fires nothing in-hand."""
    weapons_root = ROOT.parent / "Documents/Unreal Projects/WanefallGreybox/Content/Wanefall/Dimwit/Weapons"
    # Resolve relative to the project root (ROOT is Dimwit dir; project is two levels up)
    project_weapons = ROOT.parent / "Unreal Projects" / "WanefallGreybox" / "Content" / "Wanefall" / "Dimwit" / "Weapons"
    if not project_weapons.exists():
        raise BlockedError(f"weapon content dir not found at {project_weapons}; cannot check mesh resolution")
    import glob as _glob
    found = sorted(_glob.glob(str(project_weapons / "SM_Wpn_Gun_*" / "StaticMeshes" / "SM_Wpn_Gun_*.uasset")))
    n = len(found)
    if n < 25:
        return fail(score=n / 25.0, hard=True,
                    issues=[f"only {n}/25 SM_Wpn_Gun_* .uasset files found in content tree; {25 - n} registry entries broken"],
                    found=n, expected=25)
    return ok(resolved=n, expected=25)


def v_weapon_visibility_order(ctx):
    """BLOCKER: the white-weapon ordering law must be codified in source — hide Barrel/Stock/Core AFTER
    WeaponBody parent-show with propagate=false. The law keeps the recurring white-kitbash regression
    (SetVisibility with bPropagateToChildren=true re-reveals children) from silently creeping back in."""
    src = ROOT.parent / "Unreal Projects" / "WanefallGreybox" / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"
    if not src.exists():
        raise BlockedError(f"WanefallPrototypeCharacter.cpp not found at {src}")
    text = src.read_text(encoding="utf-8", errors="ignore")
    has_law = "SetVisibility(false, false)" in text and "bPropagateToChildren=true" in text
    has_comment = "Hide the BasicShapes kitbash sub-parts AFTER showing WeaponBody" in text
    if not has_law:
        return fail(hard=True,
                    issues=["white-weapon ordering law not found: SetVisibility(false, false) call missing in WanefallPrototypeCharacter.cpp"])
    if not has_comment:
        return fail(issues=["white-weapon ordering law comment absent — law may have drifted; verify the hide-after-parent pattern"])
    return ok(law_codified=True)


# ============================================================ FACET 3 — MOVEMENT (deeper layer)
def v_grapple_on_left_forearm(ctx):
    """BLOCKER: the Skyclaw grapple device must be mounted to lowerarm_l (the left forearm bone), not
    hand_l. A grapple launcher sits on the wrist/forearm — mounting to the hand bone misreads the
    anatomy and shifts the cable origin to the wrong point."""
    src = ROOT.parent / "Unreal Projects" / "WanefallGreybox" / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"
    if not src.exists():
        raise BlockedError(f"WanefallPrototypeCharacter.cpp not found at {src}")
    text = src.read_text(encoding="utf-8", errors="ignore")
    # Both the one-time setup and the per-grapple-fire re-home must reference lowerarm_l
    forearm_count = text.count('"lowerarm_l"')
    hand_count = text.count('"hand_l"')
    if forearm_count < 2:
        return fail(hard=True,
                    issues=[f"grapple still on hand_l ({hand_count} refs) instead of lowerarm_l ({forearm_count} refs); "
                            "fix both LeftHandSock and LeftHand FName declarations in WanefallPrototypeCharacter.cpp"])
    if hand_count > 0:
        return fail(issues=[f"residual hand_l refs ({hand_count}) found alongside lowerarm_l — ensure all grapple socket refs are updated"])
    return ok(forearm_refs=forearm_count)


def v_boostflip_fires_and_displaces(ctx):
    """BLOCKER: the boost-flip must have fired AND rotated the body by at least 180 degrees in the
    most recent traversal proof — confirming it's not a flag-only stub but a visually readable somersault.
    Reads from traversal_capture_result.json (same source as traversal_flip_rotates) and requires
    both the fire event and the angular travel to be measured."""
    r = _traversal(ctx)
    f = (r.get("maneuvers") or {}).get("flip") or {}
    if f.get("fired") is not True:
        return fail(hard=True, issues=["boost-flip did not fire in the traversal capture"], flip=f)
    rot = f.get("rotation_deg")
    if rot is None:
        raise BlockedError("flip.rotation_deg not captured (upgrade the traversal proof director to measure angular travel)")
    if float(rot) < 180.0:
        return fail(score=float(rot) / 360.0, hard=True, flip=f,
                    issues=[f"boost-flip only rotated {float(rot):.1f}deg — needs >= 180deg for a readable somersault"])
    return ok(rotation_deg=float(rot), score=min(1.0, float(rot) / 360.0))


def v_evasive_roll_present(ctx):
    """WARN: the evasive roll must be present in source as a functional LaunchCharacter-based displacement,
    not a stub. Checks source for DoEvasiveRoll and its LaunchCharacter call. Behavioral displacement proof
    requires a traversal capture with roll data; this is the static corroboration gate."""
    src = ROOT.parent / "Unreal Projects" / "WanefallGreybox" / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeCharacter.cpp"
    if not src.exists():
        raise BlockedError(f"WanefallPrototypeCharacter.cpp not found at {src}")
    text = src.read_text(encoding="utf-8", errors="ignore")
    has_roll = "DoEvasiveRoll" in text
    # Find if DoEvasiveRoll body contains a LaunchCharacter (confirms it's not a stub)
    idx = text.find("void AWanefallPrototypeCharacter::DoEvasiveRoll()")
    has_launch = "LaunchCharacter" in text[idx:idx + 2000] if idx != -1 else False
    if not has_roll:
        return fail(issues=["DoEvasiveRoll not found in source — evasive roll is absent"])
    if not has_launch:
        return fail(issues=["DoEvasiveRoll found but no LaunchCharacter in its body — may be a stub"])
    return ok(roll_present=True, has_displacement=True)


# ============================================================ FACET 4 — UI_HUD (new domain, deeper layer)
def _ui_hud(ctx):
    """Shared loader for ui_hud validators — same backing file as hud_readability but separate domain."""
    p = ROOT / "artifacts" / "hud_capture_result.json"
    if not p.exists():
        raise BlockedError("no HUD capture (artifacts/hud_capture_result.json); launch a Match map and capture a live HUD frame")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"hud_capture_result.json unreadable: {e}")


def _real_game_result(ctx):
    from dimwit.pipelines.real_game_validation import RESULT_PATH, validate_real_game_result
    return validate_real_game_result(RESULT_PATH)


def _packaged_build_result(ctx):
    from dimwit.pipelines.packaged_build_validation import RESULT_PATH, validate_packaged_build_result
    return validate_packaged_build_result(RESULT_PATH)


def _require_real_game_check(result: dict, check_name: str) -> dict:
    checks = result.get("checks") or {}
    if check_name not in checks:
        raise BlockedError(f"real-game result missing check: {check_name}")
    check = checks[check_name]
    if not isinstance(check, dict):
        raise BlockedError(f"real-game check is not an object: {check_name}")
    return check


def _require_packaged_build_check(result: dict, check_name: str) -> dict:
    checks = result.get("checks") or {}
    if check_name not in checks:
        raise BlockedError(f"packaged-build result missing check: {check_name}")
    check = checks[check_name]
    if not isinstance(check, dict):
        raise BlockedError(f"packaged-build check is not an object: {check_name}")
    return check


def _real_game_project_plugins() -> dict[str, bool]:
    uproject = PROJECT / "WanefallGreybox.uproject"
    if not uproject.exists():
        raise BlockedError(f"uproject missing: {uproject}")
    try:
        data = json.loads(uproject.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"uproject unreadable: {exc}") from exc
    return {str(plugin.get("Name")): bool(plugin.get("Enabled")) for plugin in data.get("Plugins", [])}


def v_hud_live_frame_not_blank(ctx):
    """BLOCKER: the HUD capture must be a real live frame — not a blank/white standalone-launch failure.
    The distinct error mode from hud_legible_contrast: this gate catches the standalone white-frame trap
    (contrast 0.0) before the legibility gate, with its own clear error message."""
    r = _ui_hud(ctx)
    leg = r.get("legibility") or {}
    c = leg.get("contrast")
    if c is None:
        raise BlockedError("HUD legibility.contrast not measured — capture script must measure frame contrast")
    if float(c) < 0.05:
        return fail(score=0.0, hard=True,
                    issues=[f"HUD frame is blank/white (contrast {c} < 0.05) — standalone white-frame trap; "
                            "foreground the window and use mss REGION grab"], legibility=leg)
    return ok(contrast=c, live_frame=True)


def v_hud_crosshair_present_centered(ctx):
    """BLOCKER: the crosshair must be present and on-screen in the live Match HUD. A missing crosshair
    means the player has no aim reference while shooting — the single most critical HUD element for a shooter."""
    r = _ui_hud(ctx)
    e = r.get("elements") or {}
    if e.get("crosshair") is not True:
        return fail(hard=True, issues=["crosshair not found in live HUD capture"], elements=e)
    return ok(crosshair=True)


def v_hud_mode_state_surfaces(ctx):
    """BLOCKER: BR/trial mode state (ring phase, trial countdown, match state) must surface in the live
    HUD. A HUD with no mode read forces players to guess at the round state."""
    r = _ui_hud(ctx)
    e = r.get("elements") or {}
    if e.get("mode_state") is not True:
        return fail(hard=True, issues=["mode_state not found in live HUD capture — BR phase/trial state is absent"], elements=e)
    return ok(mode_state=True)


def v_hud_color_not_white_stock(ctx):
    """BLOCKER: the HUD must use Wane teal (the DESIGN.md tactical color) rather than stock engine
    white/grey. A white HUD blends into the sky and signals an unfinished game."""
    r = _ui_hud(ctx)
    t = r.get("tokens") or {}
    teal = float(t.get("teal_pct") or 0.0)
    if teal < 0.5:
        return fail(hard=True, issues=[f"HUD teal_pct {teal}% < 0.5% — stock white/grey overlay, not WANE-branded"],
                    tokens=t)
    return ok(teal_pct=teal)


def v_hud_weakpoint_indicator_pending(ctx):
    """WARN (ratchets to BLOCKER once implemented): the on-screen weak-point indicator that projects
    the target's RED core to screen space is a declared HUD gap. This gate is honest WARN until the
    C++ HUD weak-point projection (plan step 4.4) is implemented and captured. Codex cannot provide
    live visual perception proof, so a source-contract proof may clear the pending state only when it
    explicitly avoids claiming a live capture and current source still contains the projection path."""
    r = _ui_hud(ctx)
    wp = r.get("weakpoint_indicator")
    if wp is True:
        return ok(weakpoint_indicator=True, proof_source="hud_capture_result.json")
    if wp is not None:
        return fail(issues=[f"weakpoint_indicator present but not confirmed: {wp}"])

    proof_path = ROOT / "artifacts" / "hud_weakpoint_command_surface_proof.json"
    if not proof_path.exists():
        return fail(issues=["weakpoint_indicator not in HUD capture and no source proof artifact found"])
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"hud_weakpoint_command_surface_proof.json unreadable: {e}")

    hud_cpp = PROJECT / "Source" / "WanefallGreybox" / "Private" / "WanefallPrototypeHUD.cpp"
    hud_h = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallPrototypeHUD.h"
    target_h = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallPrototypeTargetDummy.h"
    lobby_h = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallLobbyHUD.h"
    lobby_pc = PROJECT / "Source" / "WanefallGreybox" / "Public" / "WanefallLobbyPlayerController.h"
    source_checks = {}
    try:
        cpp = hud_cpp.read_text(encoding="utf-8")
        header = hud_h.read_text(encoding="utf-8")
        target = target_h.read_text(encoding="utf-8")
        lobby = (lobby_h.read_text(encoding="utf-8") + "\n" + lobby_pc.read_text(encoding="utf-8")).lower()
        source_checks = {
            "target_weakpoint_api": "FVector GetWeakPointLocation() const" in target,
            "hud_declares_indicator_state": "bDrewWeakpointIndicator" in header,
            "hud_declares_draw_helper": "DrawWeakpointIndicator" in header,
            "hud_draws_from_marker": "WANEFALL_WEAKPOINT_INDICATOR_PROOF" in cpp,
            "hud_reads_actual_weakpoint": "GetWeakPointLocation()" in cpp,
            "hud_projects_to_screen": "Canvas->Project" in cpp,
            "hud_visibility_traces": "LineTraceSingleByChannel" in cpp,
            "command_surface_present": "command surface" in lobby and "all-in-one front end" in lobby,
            "command_surface_channels": all(ch in lobby for ch in ("play", "modes", "loadout", "social", "rank", "stats", "settings")),
            "hold_not_frontend": "the hold" not in lobby,
        }
    except Exception as e:
        raise BlockedError(f"HUD weakpoint source proof unreadable: {e}")
    missing = [name for name, passed in source_checks.items() if not passed]

    required_proof = {
        "weakpoint_indicator": True,
        "command_surface": True,
        "live_visual_capture_claimed": False,
        "claim_scope": "source_build_contract_no_live_visual_claim",
    }
    proof_mismatch = [key for key, expected in required_proof.items() if proof.get(key) != expected]
    if missing or proof_mismatch:
        return fail(issues=[
            f"weakpoint source proof incomplete: source_missing={missing}, proof_mismatch={proof_mismatch}"
        ], source_checks=source_checks, proof=str(proof_path))
    return ok(weakpoint_indicator=True, proof_source=str(proof_path), source_checks=source_checks)


def v_real_game_capture_fresh(ctx):
    r = _real_game_result(ctx)
    freshness = r.get("freshness") or {}
    if not freshness.get("passed"):
        return fail(issues=freshness.get("issues") or ["real-game result is stale"], freshness=freshness)
    return ok(age_seconds=freshness.get("age_seconds"), result_path=str(ROOT / "artifacts" / "real_game_validation" / "real_game_validation_result.json"))


def v_real_game_window_nonblank(ctx):
    r = _real_game_result(ctx)
    window = _require_real_game_check(r, "window_found")
    still = _require_real_game_check(r, "still_nonblank")
    issues = []
    if not window.get("passed"):
        issues.extend(window.get("issues") or ["window not found"])
    if not still.get("passed"):
        issues.extend(still.get("issues") or ["still capture blank"])
    if issues:
        return fail(issues=issues, hard=bool(still and not still.get("passed")), window=window, still=still)
    return ok(window=window, still_metrics=(still.get("metrics") or {}))


def v_real_game_no_fatal_log_burst(ctx):
    r = _real_game_result(ctx)
    log_scan = _require_real_game_check(r, "log_scan")
    if not log_scan.get("passed"):
        return fail(issues=log_scan.get("issues") or ["fatal/error log burst"], hard=True,
                    fatal_count=log_scan.get("fatal_count"), error_count=log_scan.get("error_count"),
                    path=log_scan.get("path"))
    return ok(fatal_count=log_scan.get("fatal_count"), error_count=log_scan.get("error_count"), path=log_scan.get("path"))


def v_real_game_runtime_not_placeholder_dominated(ctx):
    r = _real_game_result(ctx)
    placeholder = _require_real_game_check(r, "placeholder_geometry_signal")
    if not placeholder.get("passed"):
        return fail(issues=placeholder.get("issues") or ["placeholder-dominated runtime frame"], hard=True,
                    near_white=placeholder.get("near_white"), contrast=placeholder.get("contrast"),
                    flat_midgray_patch_fraction=placeholder.get("flat_midgray_patch_fraction"),
                    flat_midgray_patch_count=placeholder.get("flat_midgray_patch_count"))
    return ok(near_white=placeholder.get("near_white"), contrast=placeholder.get("contrast"),
              flat_midgray_patch_fraction=placeholder.get("flat_midgray_patch_fraction"),
              flat_midgray_patch_count=placeholder.get("flat_midgray_patch_count"))


def v_real_game_gamefeaturedata_asset_rule(ctx):
    config = PROJECT / "Config" / "DefaultEngine.ini"
    if not config.exists():
        raise BlockedError(f"DefaultEngine.ini missing: {config}")
    text = config.read_text(encoding="utf-8", errors="replace")
    issues = []
    if "[/Script/Engine.AssetManagerSettings]" not in text:
        issues.append("AssetManagerSettings section missing")
    rule = re.search(
        r'PrimaryAssetType\s*=\s*"GameFeatureData"[^)\n]*AssetBaseClass\s*=\s*"?/Script/GameFeatures\.GameFeatureData"?',
        text,
    )
    if not rule:
        issues.append("GameFeatureData PrimaryAssetTypesToScan rule missing")
    if issues:
        return fail(issues=issues, hard=True, config=str(config))
    return ok(config=str(config), primary_asset_type="GameFeatureData")


def v_real_game_no_broken_toolsets_boot_path(ctx):
    plugins = _real_game_project_plugins()
    if plugins.get("AllToolsets") is True:
        return fail(
            hard=True,
            issues=[
                "AllToolsets is an experimental editor-only aggregator that imports NiagaraToolsets at boot "
                "and triggers UE 5.8 LogPython errors in the real-game validation log"
            ],
            all_toolsets_enabled=True,
            preserved_bridge_plugins={
                name: plugins.get(name)
                for name in ("ShowMeAIBridge", "PythonScriptPlugin", "ModelContextProtocol", "CodeEditor", "CodeView")
            },
        )
    return ok(
        all_toolsets_enabled=plugins.get("AllToolsets"),
        preserved_bridge_plugins={
            name: plugins.get(name)
            for name in ("ShowMeAIBridge", "PythonScriptPlugin", "ModelContextProtocol", "CodeEditor", "CodeView")
        },
    )


def v_packaged_build_result_fresh(ctx):
    r = _packaged_build_result(ctx)
    freshness = _require_packaged_build_check(r, "freshness")
    if not freshness.get("passed"):
        return fail(issues=freshness.get("issues") or ["packaged-build result is stale"], freshness=freshness)
    return ok(
        age_seconds=freshness.get("age_seconds"),
        result_path=str(ROOT / "artifacts" / "packaged_build_validation" / "packaged_build_result.json"),
    )


def v_packaged_build_manifest_complete(ctx):
    r = _packaged_build_result(ctx)
    manifest_check = _require_packaged_build_check(r, "package_manifest")
    if not manifest_check.get("passed"):
        return fail(issues=manifest_check.get("issues") or ["packaged build manifest incomplete"], hard=True)
    manifest = manifest_check.get("manifest") if isinstance(manifest_check.get("manifest"), dict) else {}
    executable = manifest.get("executable") if isinstance(manifest.get("executable"), dict) else {}
    return ok(
        archive_dir=manifest.get("package_dir"),
        file_count=manifest.get("file_count"),
        total_bytes=manifest.get("total_bytes"),
        executable=executable.get("path"),
    )


def v_packaged_build_executable_hash_present(ctx):
    r = _packaged_build_result(ctx)
    exe_hash = _require_packaged_build_check(r, "executable_hash")
    if not exe_hash.get("passed"):
        return fail(issues=exe_hash.get("issues") or ["packaged executable hash missing"], hard=True)
    sha = str(exe_hash.get("sha256") or "")
    if len(sha) != 64:
        return fail(issues=["packaged executable sha256 is not a 64-char digest"], hard=True, sha256=sha)
    return ok(path=exe_hash.get("path"), bytes=exe_hash.get("bytes"), sha256=sha)


def v_packaged_build_runtime_smoke_nonblank(ctx):
    r = _packaged_build_result(ctx)
    source = _require_packaged_build_check(r, "runtime_source")
    window = _require_packaged_build_check(r, "window_found")
    still = _require_packaged_build_check(r, "still_nonblank")
    frames = _require_packaged_build_check(r, "frame_burst_nonblank")
    issues = []
    for name, check in (("runtime_source", source), ("window_found", window), ("still_nonblank", still), ("frame_burst_nonblank", frames)):
        if not check.get("passed"):
            issues.extend([f"{name}: {issue}" for issue in check.get("issues", [])] or [f"{name}: failed"])
    if issues:
        return fail(issues=issues, hard=not still.get("passed"))
    return ok(
        runtime_source=source.get("runtime_source"),
        window=window,
        still_metrics=still.get("metrics") or {},
        frame_count=frames.get("frame_count"),
    )


def v_packaged_build_log_scan_clean(ctx):
    r = _packaged_build_result(ctx)
    scan = _require_packaged_build_check(r, "packaged_log_scan")
    if not scan.get("passed"):
        return fail(
            issues=scan.get("issues") or ["packaged log fatal/error burst"],
            hard=True,
            fatal_count=scan.get("fatal_count"),
            error_count=scan.get("error_count"),
            path=scan.get("path"),
        )
    return ok(fatal_count=scan.get("fatal_count"), error_count=scan.get("error_count"), path=scan.get("path"))


def v_packaged_build_gameplay_motion_proven(ctx):
    """PACKAGED_GAMEPLAY_MOTION_PROOF_V1: packaged evidence must contain PLAY, not just a menu.
    The 2026-07-01 audit found the cook held only the command-surface map and every runtime burst
    was static frames. Requires: deploy reached a cooked gameplay map (packaged log token), the
    gameplay capture is process-identity-bound, and frames under movement input show a visible
    motion delta."""
    r = _packaged_build_result(ctx)
    loaded = _require_packaged_build_check(r, "gameplay_map_loaded")
    identity = _require_packaged_build_check(r, "gameplay_process_identity")
    motion = _require_packaged_build_check(r, "gameplay_motion_delta")
    issues = []
    for name, check in (("gameplay_map_loaded", loaded), ("gameplay_process_identity", identity),
                        ("gameplay_motion_delta", motion)):
        if not check.get("passed"):
            issues.extend([f"{name}: {issue}" for issue in (check.get("issues") or [f"{name} failed"])])
    if issues:
        return fail(issues=issues, hard=True,
                    map_token=loaded.get("map_token"),
                    max_mean_delta=motion.get("max_mean_delta"),
                    threshold=motion.get("threshold"))
    return ok(map_token=loaded.get("map_token"),
              max_mean_delta=motion.get("max_mean_delta"),
              threshold=motion.get("threshold"),
              captured_pid=identity.get("captured_pid"))


def v_packaged_build_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "packaged_build_validation" not in pipelines:
        issues.append("production_pipelines.json missing packaged_build_validation")
    if not any(isinstance(task, dict) and task.get("pipeline") == "packaged_build_validation" for task in tasks):
        issues.append("director_tasks.json missing packaged_build_validation task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(
        pipeline_registered=True,
        director_task=True,
        validation_domain="packaged_build",
    )


def v_build_retention(ctx):
    """Fail-closed D: retention gate: the packaged-build workspace must stay bounded to the newest
    KEEP runs (+ the current-manifest run), else the ~4.8G/run pileup threatens the D: pressure
    valve that exists only because C: is chronically full. Workspace unreachable -> BLOCKED."""
    from dimwit.build_retention import check_retention
    r = check_retention()
    if r.get("blocked"):
        raise BlockedError(r["issues"][0])
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True,
                    over_ceiling=r.get("over_ceiling"), keep_last=r.get("keep_last"))
    return ok(keep_last=r.get("keep_last"), kept=r.get("kept"))


# ============================================================ PERFORMANCE_BASELINE_GATES_V1
# (masterplan Horizon 1, bundle 4 / audit bundle 8). Floors are recomputed from the embedded
# perf payload by validate_performance_baseline_result on every read — the validators below
# consume recomputed checks, never stored verdicts. Missing/unreadable evidence raises
# BlockedError -> BLOCKED, never PASS.

def _performance_baseline_result(ctx):
    from dimwit.pipelines.performance_baseline import RESULT_PATH, validate_performance_baseline_result
    return validate_performance_baseline_result(RESULT_PATH)


def _require_perf_check(result: dict, check_name: str) -> dict:
    checks = result.get("checks") or {}
    if check_name not in checks:
        raise BlockedError(f"performance-baseline result missing check: {check_name}")
    check = checks[check_name]
    if not isinstance(check, dict):
        raise BlockedError(f"performance-baseline check is not an object: {check_name}")
    return check


def v_perf_baseline_result_fresh(ctx):
    r = _performance_baseline_result(ctx)
    freshness = _require_perf_check(r, "freshness")
    if not freshness.get("passed"):
        return fail(issues=freshness.get("issues") or ["performance-baseline result is stale"],
                    freshness=freshness)
    return ok(age_seconds=freshness.get("age_seconds"),
              result_path=str(ROOT / "artifacts" / "performance_baseline" / "performance_baseline_result.json"))


def v_perf_baseline_identity_bound(ctx):
    """Perf evidence must be pid-bound to the launched packaged exe, the capture identity-bound
    (law 3), and the exe sha-bound to the current package manifest (law 5: right subject)."""
    r = _performance_baseline_result(ctx)
    identity = _require_perf_check(r, "process_identity")
    evidence = _require_perf_check(r, "perf_evidence_present")
    source = _require_perf_check(r, "runtime_source")
    issues = []
    for name, check in (("process_identity", identity), ("perf_evidence_present", evidence),
                        ("runtime_source", source)):
        if not check.get("passed"):
            issues.extend([f"{name}: {issue}" for issue in (check.get("issues") or [f"{name} failed"])])
    if issues:
        return fail(issues=issues, hard=True)
    return ok(runtime_source=source.get("runtime_source"), pid=evidence.get("pid"),
              executable=evidence.get("executable"))


def v_perf_baseline_measurement_conditions(ctx):
    r = _performance_baseline_result(ctx)
    conditions = _require_perf_check(r, "measurement_conditions")
    if not conditions.get("passed"):
        return fail(issues=conditions.get("issues") or ["measurement conditions unproven"], hard=True)
    m = conditions.get("measurement") or {}
    return ok(vsync=m.get("vsync"), t_max_fps=m.get("t_max_fps"),
              resolution=f"{m.get('resolution_x')}x{m.get('resolution_y')}",
              warmup_seconds=m.get("warmup_seconds"))


def v_perf_baseline_segment_coverage(ctx):
    r = _performance_baseline_result(ctx)
    coverage = _require_perf_check(r, "segment_coverage")
    if not coverage.get("passed"):
        return fail(issues=coverage.get("issues") or ["menu/arena steady windows below minimums"], hard=True)
    return ok(menu_steady=coverage.get("menu_steady"), arena_steady=coverage.get("arena_steady"))


def v_perf_arena_frametime_floor(ctx):
    r = _performance_baseline_result(ctx)
    floor = _require_perf_check(r, "arena_frametime_floor")
    if not floor.get("passed"):
        return fail(issues=floor.get("issues") or ["arena steady p95 over floor"], hard=True,
                    p95_ms=floor.get("p95_ms"), floor_ms=floor.get("floor_ms"))
    return ok(p95_ms=floor.get("p95_ms"), floor_ms=floor.get("floor_ms"), steady=floor.get("steady"))


def v_perf_arena_hitch_free(ctx):
    r = _performance_baseline_result(ctx)
    hitch = _require_perf_check(r, "arena_hitch_free")
    if not hitch.get("passed"):
        return fail(issues=hitch.get("issues") or ["steady arena hitches present"], hard=True,
                    hitch_count=hitch.get("hitch_count"), severe_hitch_count=hitch.get("severe_hitch_count"))
    return ok(hitch_count=hitch.get("hitch_count"), severe_hitch_count=hitch.get("severe_hitch_count"),
              hitch_ms=hitch.get("hitch_ms"))


def v_perf_menu_frametime_floor(ctx):
    r = _performance_baseline_result(ctx)
    floor = _require_perf_check(r, "menu_frametime_floor")
    if not floor.get("passed"):
        return fail(issues=floor.get("issues") or ["menu steady p95 over floor"], hard=True,
                    p95_ms=floor.get("p95_ms"), floor_ms=floor.get("floor_ms"))
    return ok(p95_ms=floor.get("p95_ms"), floor_ms=floor.get("floor_ms"))


def v_perf_memory_budget(ctx):
    r = _performance_baseline_result(ctx)
    memory = _require_perf_check(r, "memory_budget")
    if not memory.get("passed"):
        return fail(issues=memory.get("issues") or ["memory peak over budget"], hard=True,
                    peak_used_physical_mb=memory.get("peak_used_physical_mb"),
                    budget_mb=memory.get("budget_mb"))
    return ok(peak_used_physical_mb=memory.get("peak_used_physical_mb"),
              budget_mb=memory.get("budget_mb"),
              avg_used_physical_mb=memory.get("avg_used_physical_mb"))


# ============================================================ FIRSTPARTY_WANE_FX_V1 +
# NIAGARA_COOK_SAFETY_GATE (masterplan Horizon 1, bundle 5). Law 5 as a static gate: the two
# REAL cooked-build killers stay on disk as golden negatives the scanner must flag every run.
# Reports are regenerated on read (contract-auditor idiom) — never stale, never trusted-stored.

def _wane_fx_report(ctx):
    from dimwit.pipelines.wane_fx import write_cook_safety_report
    return write_cook_safety_report()


def _wane_fx_sources():
    rifle = SRC / "Private" / "WanefallWanePulseRifleComponent.cpp"
    gamestate = SRC / "Private" / "WanefallArena4v4GameState.cpp"
    if not rifle.exists():
        raise BlockedError(f"pulse rifle source missing: {rifle}")
    if not gamestate.exists():
        raise BlockedError(f"arena game state source missing: {gamestate}")
    return (rifle.read_text(encoding="utf-8", errors="replace"),
            gamestate.read_text(encoding="utf-8", errors="replace"))


def v_niagara_cook_safety_referenced_clean(ctx):
    report = _wane_fx_report(ctx)
    referenced = report.get("referenced") or []
    if not referenced:
        raise BlockedError("no gameplay UNiagaraSystem references discovered — scan perimeter empty")
    dirty = [r for r in referenced if not r.get("cook_safe")]
    if dirty:
        return fail(issues=[
            f"{r['game_path']} ({Path(r['file']).name}:{r['line']}): "
            f"decal={r['scan']['decal_markers']} component={r['scan']['component_markers']} "
            f"stateless={r['scan'].get('stateless_markers')} first_party={r.get('first_party')} "
            f"exists={r['scan']['exists']}" for r in dirty], hard=True)
    return ok(referenced_count=len(referenced),
              paths=[r["game_path"] for r in referenced])


def v_niagara_cook_safety_catches_known_bad(ctx):
    """Anti-rubber-stamp golden: the scanner must flag BOTH real killers. A refactor that
    weakens the marker scan (or deletion of a golden asset) fails here, not silently."""
    report = _wane_fx_report(ctx)
    goldens = report.get("known_bad_golden") or []
    if not goldens:
        raise BlockedError("known-bad golden set empty")
    unflagged = [g for g in goldens if not g.get("flagged")]
    if unflagged:
        return fail(issues=[
            f"golden NOT flagged: {g['game_path']} (exists={g['scan']['exists']}, "
            f"decal={g['scan']['decal_markers']}, component={g['scan']['component_markers']}) — {g['why']}"
            for g in unflagged], hard=True)
    return ok(goldens=[g["game_path"] for g in goldens])


def v_wane_fx_first_party_combat_surfaces(ctx):
    from dimwit.pipelines.wane_fx import (
        game_path_to_content_file, parse_combat_fx_surfaces, scan_niagara_asset)
    rifle_text, gamestate_text = _wane_fx_sources()
    surfaces = parse_combat_fx_surfaces(rifle_text, gamestate_text)
    issues = list(surfaces.get("issues") or [])
    assets = {}
    for surface in ("muzzle", "impact", "kill_confirm"):
        game_path = surfaces.get(surface)
        if not game_path:
            continue
        scan = scan_niagara_asset(game_path_to_content_file(game_path))
        assets[surface] = scan
        if not scan["exists"]:
            issues.append(f"{surface} asset missing on disk: {game_path}")
        elif scan["emitter_handles"] < 1:
            issues.append(f"{surface} asset has no emitter handles: {game_path}")
        elif scan.get("stateless_markers", 0) > 0:
            issues.append(f"{surface} asset carries stateless emitters "
                          f"(duplicated-stateless = cooked-boot Serialize assert): {game_path}")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(muzzle=surfaces["muzzle"], impact=surfaces["impact"],
              kill_confirm=surfaces["kill_confirm"],
              emitters={k: v["emitter_handles"] for k, v in assets.items()})


def v_wane_fx_runtime_tint_wired(ctx):
    from dimwit.pipelines.wane_fx import check_runtime_tint
    rifle_text, gamestate_text = _wane_fx_sources()
    tint = check_runtime_tint(rifle_text, gamestate_text)
    if not tint.get("passed"):
        return fail(issues=tint.get("issues") or ["WANE tint not applied at spawn"], hard=True)
    return ok(rifle_tint_calls=tint.get("rifle_tint_calls"),
              gamestate_tint_calls=tint.get("gamestate_tint_calls"))


def v_wane_fx_spawned_in_packaged_match(ctx):
    """Packaged proof of PLAY with the new FX (law 5): the CURRENT packaged machine-played
    match log must contain spawn markers for all three surfaces."""
    from dimwit.pipelines.wane_fx import check_packaged_wane_fx_markers
    r = _packaged_build_result(ctx)
    archive_dir = Path(((r.get("package") or {}).get("archive_dir")) or "")
    log_path = archive_dir / "Windows" / "WanefallGreybox" / "Saved" / "Logs" / "WanefallGreybox.log"
    if not archive_dir or not log_path.exists():
        raise BlockedError(f"packaged match log missing: {log_path}")
    markers = check_packaged_wane_fx_markers(log_path.read_text(encoding="utf-8", errors="replace"))
    if not markers.get("passed"):
        return fail(issues=markers.get("issues") or ["packaged [WaneFX] markers missing"], hard=True,
                    log=str(log_path))
    return ok(muzzle=markers["muzzle"], impact=markers["impact"],
              kill_confirm=markers["kill_confirm"], log=str(log_path))


def v_perf_baseline_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "performance_baseline" not in pipelines:
        issues.append("production_pipelines.json missing performance_baseline")
    if not any(isinstance(task, dict) and task.get("pipeline") == "performance_baseline" for task in tasks):
        issues.append("director_tasks.json missing performance_baseline task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(pipeline_registered=True, director_task=True, validation_domain="performance_baseline")


# ============================================================ BOT BALANCE TELEMETRY (bundle 6 — design gets receipts)
def _bot_balance_result(ctx):
    from dimwit.pipelines.bot_balance_telemetry import BASELINE_PATH, RESULT_PATH, validate_bot_balance_result
    return validate_bot_balance_result(RESULT_PATH, baseline_path=BASELINE_PATH)


def _require_bot_balance_check(result: dict, check_name: str) -> dict:
    checks = result.get("checks") or {}
    if check_name not in checks:
        raise BlockedError(f"bot-balance result missing check: {check_name}")
    check = checks[check_name]
    if not isinstance(check, dict):
        raise BlockedError(f"bot-balance check is not an object: {check_name}")
    return check


def v_bot_balance_result_fresh(ctx):
    r = _bot_balance_result(ctx)
    freshness = _require_bot_balance_check(r, "freshness")
    if not freshness.get("passed"):
        return fail(issues=freshness.get("issues") or ["bot-balance telemetry is stale"],
                    freshness=freshness)
    return ok(age_seconds=freshness.get("age_seconds"),
              result_path=str(ROOT / "artifacts" / "bot_balance" / "bot_balance_result.json"))


def v_bot_balance_identity_bound(ctx):
    """Telemetry must be flag-marked, pid-bound to the launched packaged exe, and exe-sha-bound
    to the current package manifest (law 5: right subject). Recomputed at validation time."""
    r = _bot_balance_result(ctx)
    binding = _require_bot_balance_check(r, "telemetry_evidence_bound")
    if not binding.get("passed"):
        return fail(issues=binding.get("issues") or ["telemetry evidence unbound"], hard=True)
    return ok(pid=binding.get("pid"), executable=binding.get("executable"))


def v_bot_balance_measurement_conditions(ctx):
    r = _bot_balance_result(ctx)
    conditions = _require_bot_balance_check(r, "measurement_conditions")
    if not conditions.get("passed"):
        return fail(issues=conditions.get("issues") or ["measurement conditions unpinned"], hard=True,
                    measurement=conditions.get("measurement"))
    return ok(measurement=conditions.get("measurement"))


def v_bot_balance_match_coverage(ctx):
    r = _bot_balance_result(ctx)
    coverage = _require_bot_balance_check(r, "match_coverage")
    if not coverage.get("passed"):
        return fail(issues=coverage.get("issues") or ["match coverage below floors"],
                    matches=coverage.get("matches"), wane_matches=coverage.get("wane_matches"))
    return ok(matches=coverage.get("matches"), wane_matches=coverage.get("wane_matches"),
              draws=coverage.get("draws"))


def v_bot_balance_sanity_invariants(ctx):
    """Physically impossible TTK, degenerate win rates, unmoved bots, or a wane line that never
    crosses the arena are lies, not data — REJECT."""
    r = _bot_balance_result(ctx)
    sanity = _require_bot_balance_check(r, "sanity_invariants")
    if not sanity.get("passed"):
        return fail(issues=sanity.get("issues") or ["sanity invariants violated"], hard=True,
                    ttk_avg_s=sanity.get("ttk_avg_s"), team_a_win_rate=sanity.get("team_a_win_rate"))
    return ok(ttk_samples=sanity.get("ttk_samples"), ttk_avg_s=sanity.get("ttk_avg_s"),
              team_a_win_rate=sanity.get("team_a_win_rate"), accuracy=sanity.get("accuracy"))


def v_bot_balance_aggregate_recompute(ctx):
    """The reported headline aggregates must match the numbers recomputed from the per-match
    array — a fabricated headline is REJECTED (recomputation law)."""
    r = _bot_balance_result(ctx)
    recompute = _require_bot_balance_check(r, "aggregate_recompute")
    if not recompute.get("passed"):
        return fail(issues=recompute.get("issues") or ["aggregates diverge from per-match truth"], hard=True)
    return ok(recomputed=recompute.get("recomputed"))


def v_bot_balance_drift_gates(ctx):
    """Aggregates must stay inside the drift bands around the PINNED committed baseline (A2:
    design gets receipts). A missing baseline fails closed."""
    r = _bot_balance_result(ctx)
    drift = _require_bot_balance_check(r, "baseline_drift")
    if not drift.get("passed"):
        return fail(issues=drift.get("issues") or ["balance drifted beyond the pinned baseline bands"],
                    deltas=drift.get("deltas"))
    return ok(deltas=drift.get("deltas"), baseline_pinned_at=drift.get("baseline_pinned_at"))


def v_bot_balance_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "bot_balance_telemetry" not in pipelines:
        issues.append("production_pipelines.json missing bot_balance_telemetry")
    if not any(isinstance(task, dict) and task.get("pipeline") == "bot_balance_telemetry" for task in tasks):
        issues.append("director_tasks.json missing bot_balance_telemetry task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(pipeline_registered=True, director_task=True, validation_domain="bot_balance")


# ============================================================ PLAYER INPUT + UI HYGIENE (Horizon 2 — B4/B7)
def v_player_hygiene_gameplay_input_parity(ctx):
    from dimwit.pipelines.player_hygiene import check_input_parity, live_ini
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_input_parity(ini)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(actions=len(r.get("actions", {})))


def v_player_hygiene_no_dead_action(ctx):
    from dimwit.pipelines.player_hygiene import check_actions_referenced, live_ini, live_source_blob
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_actions_referenced(ini, live_source_blob())
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, dead=r.get("dead"))
    return ok(no_dead_actions=True)


def v_player_hygiene_ui_no_debug_leaks(ctx):
    from dimwit.pipelines.player_hygiene import check_ui_no_debug_leaks, live_hud_texts
    r = check_ui_no_debug_leaks(live_hud_texts())
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, hits=r.get("hits"))
    return ok(hud_clean=True)


def v_player_hygiene_colorblind_palette(ctx):
    from dimwit.pipelines.player_hygiene import check_colorblind_palette, live_lobby_hud
    lobby = live_lobby_hud()
    if not lobby:
        raise BlockedError("lobby HUD source missing/unreadable")
    r = check_colorblind_palette(lobby)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, pairs=r.get("pairs"))
    return ok(pairs=r.get("pairs"))


# ---- AXIS_INPUT_HYGIENE_V1: AxisMappings (Move/Look) get the same hygiene as ActionMappings ----
def v_player_hygiene_axis_parity(ctx):
    from dimwit.pipelines.player_hygiene import check_axis_parity, live_ini
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_axis_parity(ini)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(axes=len(r.get("axes", {})))


def v_player_hygiene_axis_bidirectional(ctx):
    from dimwit.pipelines.player_hygiene import check_axis_bidirectional, live_ini
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_axis_bidirectional(ini)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(bidirectional=True)


def v_player_hygiene_no_dead_axis(ctx):
    from dimwit.pipelines.player_hygiene import check_axes_referenced, live_ini, live_source_blob
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_axes_referenced(ini, live_source_blob())
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, dead=r.get("dead"))
    return ok(no_dead_axes=True)


def v_player_hygiene_reserved_keys(ctx):
    from dimwit.pipelines.player_hygiene import check_reserved_keys, live_ini
    ini = live_ini()
    if not ini:
        raise BlockedError("DefaultInput.ini missing/unreadable")
    r = check_reserved_keys(ini)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, reserved=r.get("reserved"))
    return ok(reserved=r.get("reserved"))


# ============================================================ HUMAN INPUT MATRIX (Horizon 2 — B7)
def v_input_matrix_gamepad_parity(ctx):
    from dimwit.pipelines.input_matrix import check_gamepad_parity, live_ctrl_text
    text = live_ctrl_text()
    if not text:
        raise BlockedError("lobby controller source missing/unreadable")
    r = check_gamepad_parity(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, bindings=r.get("bindings"))
    return ok(verbs=list(r.get("bindings", {}).keys()))


def v_input_matrix_game_input_claimed(ctx):
    from dimwit.pipelines.input_matrix import check_input_mode, live_ctrl_text
    text = live_ctrl_text()
    if not text:
        raise BlockedError("lobby controller source missing/unreadable")
    r = check_input_mode(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(input_mode="FInputModeGameOnly")


def v_input_matrix_dual_hints(ctx):
    from dimwit.pipelines.input_matrix import check_dual_hints, live_hud_text
    text = live_hud_text()
    if not text:
        raise BlockedError("lobby HUD source missing/unreadable")
    r = check_dual_hints(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(dual_hints=True)


# ============================================================ FLAGSHIP ARENA ART PASS (bundle 10 — B3)
def _flagship_arena(ctx):
    from dimwit.pipelines.flagship_arena import validate_flagship_arena
    return validate_flagship_arena()


def _require_flagship_check(result: dict, name: str) -> dict:
    checks = result.get("checks") or {}
    if name not in checks:
        raise BlockedError(f"flagship-arena result missing check: {name}")
    return checks[name]


def v_flagship_arena_dressed(ctx):
    c = _require_flagship_check(_flagship_arena(ctx), "dressed")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["arena not dressed"], hard=True,
                    kit_landmarks=c.get("kit_landmarks"), materials=c.get("materials"))
    return ok(kit_landmarks=c.get("kit_landmarks"), materials=c.get("materials"))


def v_flagship_arena_lighting_rig(ctx):
    c = _require_flagship_check(_flagship_arena(ctx), "lighting_rig")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["lighting rig incomplete"], hard=True,
                    rig=c.get("rig_classes"))
    return ok(rig=c.get("rig_classes"))


def v_flagship_arena_wane_landmarks(ctx):
    c = _require_flagship_check(_flagship_arena(ctx), "wane_landmarks")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["missing wane-energy landmarks"], hard=True)
    return ok(landmarks=c.get("landmarks"), emissive=c.get("emissive"))


def v_flagship_arena_nav_collision(ctx):
    c = _require_flagship_check(_flagship_arena(ctx), "nav_collision")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["arena unplayable"], hard=True,
                    player_starts=c.get("player_starts"))
    return ok(player_starts=c.get("player_starts"))


def v_flagship_arena_capture_tour(ctx):
    c = _require_flagship_check(_flagship_arena(ctx), "capture_tour")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["capture tour failed"], hard=True,
                    stations=c.get("stations"), nonblank=c.get("nonblank"))
    return ok(stations=c.get("stations"), nonblank=c.get("nonblank"),
              luma_spread=c.get("luma_spread"))


# ============================================================ SELF-METRICS + QUEUE DIRECTOR (bundle 9 — A2)
def _self_metrics_inputs(ctx):
    from dimwit.pipelines.self_metrics import FULL_REPORT_PATH, RESULT_PATH
    if not RESULT_PATH.exists():
        raise BlockedError("self_metrics.json missing; run `python scripts/pipeline/run_pipeline.py self_metrics_director`")
    if not FULL_REPORT_PATH.exists():
        raise BlockedError("validation_report_full.json missing; run a full `python scripts/pipeline/run_validation.py` first")
    try:
        stored = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        report = json.loads(FULL_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"self-metrics inputs unreadable: {exc}")
    return stored, report


def v_self_metrics_present(ctx):
    """The artifact exists and is well-formed (source + the four measured sections). Correctness /
    up-to-date-ness is the RECOMPUTE gate (self_metrics_derived_from_suite) — that recomputes from
    the CURRENT report, so a stale artifact fails there. This gate is idempotent: the self_metrics
    domain is excluded from its own measurement, so the artifact stays valid run-to-run."""
    stored, _ = _self_metrics_inputs(ctx)
    missing = [k for k in ("source", "suite", "domains", "probe_mix", "freshness_radar",
                           "operational_queue") if k not in stored]
    if missing:
        return fail(issues=[f"self_metrics.json missing section(s): {missing}"], hard=True)
    if not isinstance(stored.get("source"), dict) or stored["source"].get("run_ts") is None:
        return fail(issues=["self_metrics.json has no source report reference"], hard=True)
    return ok(source_run_ts=stored["source"].get("run_ts"),
              total=(stored.get("suite") or {}).get("total"))


def v_self_metrics_derived_from_suite(ctx):
    from dimwit.pipelines.self_metrics import recompute_and_compare
    stored, report = _self_metrics_inputs(ctx)
    cmp = recompute_and_compare(stored, report)
    if not cmp["passed"]:
        return fail(issues=cmp["issues"], hard=True)
    return ok(total=(stored.get("suite") or {}).get("total"))


def v_self_metrics_freshness_radar_covers_decaying_lanes(ctx):
    from dimwit.pipelines.self_metrics import compute_freshness_radar
    stored, report = _self_metrics_inputs(ctx)
    fresh_radar = compute_freshness_radar(report)
    stored_radar = stored.get("freshness_radar") if isinstance(stored.get("freshness_radar"), list) else []
    fresh_by_id = {e["validator_id"]: e for e in fresh_radar}
    stored_by_id = {e.get("validator_id"): e for e in stored_radar}
    issues = []
    for vid, e in fresh_by_id.items():
        if vid not in stored_by_id:
            issues.append(f"decaying lane {vid} missing from stored radar (a block could hide)")
        elif stored_by_id[vid].get("status") != e["status"]:
            issues.append(f"radar status for {vid}: stored {stored_by_id[vid].get('status')!r} "
                          f"!= recomputed {e['status']!r}")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(aged_lanes=len(fresh_radar),
              decaying=[e["validator_id"] for e in fresh_radar if e["status"] != "fresh"])


def v_self_metrics_queue_ranked_by_evidence(ctx):
    from dimwit.pipelines.self_metrics import rank_operational_queue
    stored, _ = _self_metrics_inputs(ctx)
    stored_queue = stored.get("operational_queue") if isinstance(stored.get("operational_queue"), list) else []
    recomputed = rank_operational_queue(stored)
    issues = []
    if stored_queue != recomputed:
        issues.append("operational queue is not deterministic / not recomputable from the metrics")
    last_rank = -1
    for it in stored_queue:
        if not it.get("command") or not it.get("evidence"):
            issues.append(f"queue item rank {it.get('rank')} missing command/evidence receipt")
        br = it.get("bucket_rank", 99)
        if br < last_rank:
            issues.append("queue ordering violates broken->stale->warn bucket precedence")
        last_rank = max(last_rank, br)
    if issues:
        return fail(issues=issues, hard=True)
    return ok(queued=len(stored_queue))


def v_self_metrics_no_operator_promotions(ctx):
    stored, _ = _self_metrics_inputs(ctx)
    blob = json.dumps(stored)
    forbidden = [s for s in ("HUMAN_ACCEPTED", "PROMOTED_TO_ACTIVE_SLICE") if s in blob]
    if forbidden or stored.get("operator_only_states_written"):
        return fail(issues=[f"self-metrics leaked operator-only state(s): "
                            f"{forbidden or stored.get('operator_only_states_written')}"], hard=True)
    return ok(ceiling="PROMOTED_TO_REVIEW")


def v_self_metrics_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "self_metrics_director" not in pipelines:
        issues.append("production_pipelines.json missing self_metrics_director")
    if not any(isinstance(t, dict) and t.get("pipeline") == "self_metrics_director" for t in tasks):
        issues.append("director_tasks.json missing self_metrics_director task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(pipeline_registered=True, director_task=True, validation_domain="self_metrics")


# ============================================================ UI SETTINGS PERSISTENCE (bundle 8)
def _ui_settings_result(ctx):
    from dimwit.pipelines.ui_settings import RESULT_PATH, validate_ui_settings_result
    return validate_ui_settings_result(RESULT_PATH)


def _require_ui_settings_check(result: dict, name: str) -> dict:
    checks = result.get("checks") or {}
    if name not in checks:
        raise BlockedError(f"ui-settings result missing check: {name}")
    check = checks[name]
    if not isinstance(check, dict):
        raise BlockedError(f"ui-settings check is not an object: {name}")
    return check


def v_ui_settings_result_fresh(ctx):
    r = _ui_settings_result(ctx)
    fresh = _require_ui_settings_check(r, "freshness")
    if not fresh.get("passed"):
        return fail(issues=fresh.get("issues") or ["ui-settings proof stale"], freshness=fresh)
    return ok(age_seconds=fresh.get("age_seconds"))


def v_ui_settings_evidence_bound(ctx):
    r = _ui_settings_result(ctx)
    b = _require_ui_settings_check(r, "evidence_bound")
    if not b.get("passed"):
        return fail(issues=b.get("issues") or ["settings proof evidence unbound"], hard=True, pids=b.get("pids"))
    return ok(pids=b.get("pids"))


def v_ui_settings_persistence_roundtrip(ctx):
    r = _ui_settings_result(ctx)
    rt = _require_ui_settings_check(r, "persistence_roundtrip")
    if not rt.get("passed"):
        return fail(issues=rt.get("issues") or ["settings did not survive relaunch"], hard=True,
                    fields=rt.get("fields_roundtripped"), mismatches=rt.get("mismatches"))
    return ok(fields_roundtripped=rt.get("fields_roundtripped"))


def v_ui_settings_gameusersettings_applied(ctx):
    r = _ui_settings_result(ctx)
    g = _require_ui_settings_check(r, "gameusersettings_applied")
    if not g.get("passed"):
        return fail(issues=g.get("issues") or ["GameUserSettings not applied/persisted"], hard=True,
                    intended=g.get("intended"))
    return ok(intended=g.get("intended"))


def v_ui_settings_coverage(ctx):
    r = _ui_settings_result(ctx)
    c = _require_ui_settings_check(r, "coverage")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["settings coverage below floor"], hard=True,
                    non_default=c.get("non_default"))
    return ok(non_default=c.get("non_default"))


def v_ui_settings_savereload_wired(ctx):
    """STATIC anti-stub: the profile subsystem must actually save (ToJson->file) and there must be
    a GameUserSettings apply path — a 'persistence' lane over a subsystem that never writes is a lie."""
    project = ctx.project
    header = project / "Source" / "WanefallGreybox" / "Public" / "WanefallProfileSubsystem.h"
    source = project / "Source" / "WanefallGreybox" / "Private" / "WanefallProfileSubsystem.cpp"
    proof = project / "Source" / "WanefallGreybox" / "Private" / "WanefallSettingsProofSubsystem.cpp"
    issues = []
    try:
        htext = header.read_text(encoding="utf-8", errors="replace")
        stext = source.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise BlockedError(f"profile subsystem source unreadable: {e}")
    if "SaveProfile" not in htext or "SaveProfile" not in stext:
        issues.append("UWanefallProfileSubsystem has no SaveProfile save-back")
    if "ToJson" not in stext:
        issues.append("SaveProfile never serializes the profile (no ToJson)")
    apply_text = ""
    try:
        apply_text = proof.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    combined = stext + apply_text
    if "GameUserSettings" not in combined:
        issues.append("no GameUserSettings apply path in profile/settings-proof subsystems")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(save_back=True, gameusersettings=True)


def v_ui_settings_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "ui_settings_persistence" not in pipelines:
        issues.append("production_pipelines.json missing ui_settings_persistence")
    if not any(isinstance(t, dict) and t.get("pipeline") == "ui_settings_persistence" for t in tasks):
        issues.append("director_tasks.json missing ui_settings_persistence task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(pipeline_registered=True, director_task=True, validation_domain="ui_settings")


# ============================================================ PROGRESSION_PERSISTENCE_V1 (masterplan B6)
def _progression_result(ctx):
    from dimwit.pipelines.progression import RESULT_PATH, validate_progression_result
    return validate_progression_result(RESULT_PATH)


def _require_progression_check(result: dict, name: str) -> dict:
    checks = result.get("checks") or {}
    if name not in checks:
        raise BlockedError(f"progression result missing check: {name}")
    check = checks[name]
    if not isinstance(check, dict):
        raise BlockedError(f"progression check is not an object: {name}")
    return check


def v_progression_result_fresh(ctx):
    c = _require_progression_check(_progression_result(ctx), "freshness")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["progression proof stale"], age_seconds=c.get("age_seconds"))
    return ok(age_seconds=c.get("age_seconds"))


def v_progression_evidence_bound(ctx):
    c = _require_progression_check(_progression_result(ctx), "evidence_bound")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["progression proof exe-sha unbound"], hard=True)
    return ok(evidence_bound=True)


def v_progression_earned_from_real_telemetry(ctx):
    c = _require_progression_check(_progression_result(ctx), "earned_from_real_telemetry")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["xp/level not recomputable from real seat telemetry"], hard=True,
                    proofs=c.get("proofs"))
    return ok(proofs=c.get("proofs"))


def v_progression_anti_farm_cap_enforced(ctx):
    c = _require_progression_check(_progression_result(ctx), "anti_farm")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["anti-farm cap not enforced"], hard=True)
    return ok(anti_farm=True)


def v_progression_challenges_advance_from_events(ctx):
    c = _require_progression_check(_progression_result(ctx), "challenges")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["challenge progress not from real events"], hard=True)
    return ok(challenges=True)


def v_progression_persists_across_relaunch(ctx):
    c = _require_progression_check(_progression_result(ctx), "persists_across_relaunch")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["earnings did not survive a real relaunch"], hard=True,
                    xp_run1=c.get("xp_run1"), xp_run2=c.get("xp_run2"))
    return ok(xp_run1=c.get("xp_run1"), xp_run2=c.get("xp_run2"))


def v_progression_profile_schema_versioned(ctx):
    c = _require_progression_check(_progression_result(ctx), "schema_versioned")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["persisted profile not schema-versioned"], hard=True)
    return ok(schema_versioned=True)


def v_progression_profile_migration_roundtrips(ctx):
    c = _require_progression_check(_progression_result(ctx), "migration_roundtrips")
    if not c.get("passed"):
        return fail(issues=c.get("issues") or ["v0 shape of real profile did not migrate"], hard=True)
    return ok(migration_roundtrips=True)


def v_progression_queue_sync(ctx):
    manifest = ctx.result_json(ROOT / "config" / "production_pipelines.json")
    director = ctx.result_json(ROOT / "config" / "director_tasks.json")
    pipelines = manifest.get("pipelines") if isinstance(manifest.get("pipelines"), dict) else {}
    tasks = director.get("tasks") if isinstance(director.get("tasks"), list) else []
    issues = []
    if "progression" not in pipelines:
        issues.append("production_pipelines.json missing progression")
    if not any(isinstance(t, dict) and t.get("pipeline") == "progression" for t in tasks):
        issues.append("director_tasks.json missing progression task")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(pipeline_registered=True, director_task=True, validation_domain="progression")


# ============================================================ COMMAND DECK TRUTH (bundle 7 — UI honesty)
def v_command_deck_no_ui_fiction(ctx):
    from dimwit.pipelines.command_deck import live_ui_text, scan_ui_fiction
    text = live_ui_text()
    if not text:
        raise BlockedError("command-deck source (WanefallLobbyHUD.cpp) missing/unreadable")
    r = scan_ui_fiction(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, hits=r["hits"])
    return ok(scanned="WanefallLobbyHUD.cpp")


def v_command_deck_reads_real_profile(ctx):
    from dimwit.pipelines.command_deck import check_reads_real_profile, live_ui_text
    text = live_ui_text()
    if not text:
        raise BlockedError("command-deck source missing/unreadable")
    r = check_reads_real_profile(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, found=r["found"])
    return ok(accessors=r["found"])


def v_command_deck_honest_empty_states(ctx):
    from dimwit.pipelines.command_deck import check_honest_empty_states, live_ui_text
    text = live_ui_text()
    if not text:
        raise BlockedError("command-deck source missing/unreadable")
    r = check_honest_empty_states(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, missing=r["missing"])
    return ok()


def v_command_deck_profile_subsystem_real(ctx):
    from dimwit.pipelines.command_deck import check_profile_subsystem, live_subsystem_texts
    header, source = live_subsystem_texts()
    if not header or not source:
        raise BlockedError("WanefallProfileSubsystem source missing/unreadable")
    r = check_profile_subsystem(header, source)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True)
    return ok(subsystem="UWanefallProfileSubsystem")


def v_deck_reads_earned_progression(ctx):
    from dimwit.pipelines.command_deck import check_reads_earned_progression, live_ui_text
    text = live_ui_text()
    if not text:
        raise BlockedError("command-deck source missing/unreadable")
    r = check_reads_earned_progression(text)
    if not r["passed"]:
        return fail(issues=r["issues"], hard=True, found=r["found"])
    return ok(progression_tokens=r["found"])


def _pipeline_contract_report(ctx):
    from dimwit.pipelines.contract_auditor import RESULT_PATH, write_contract_audit

    result_path = RESULT_PATH
    write_contract_audit(ctx.root, result_path)
    try:
        report = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"pipeline contract audit unreadable: {exc}") from exc
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        raise BlockedError("pipeline contract audit generated_at missing or not numeric")
    return report


def _pipeline_contract_check(ctx, check_name):
    report = _pipeline_contract_report(ctx)
    checks = report.get("checks") or {}
    check = checks.get(check_name)
    if not isinstance(check, dict):
        raise BlockedError(f"pipeline contract audit missing check: {check_name}")
    return check, report


def v_pipeline_contract_audit_fresh(ctx):
    from dimwit.pipelines.contract_auditor import RESULT_PATH, MAX_AUDIT_AGE_SECONDS

    report = _pipeline_contract_report(ctx)
    age_seconds = time.time() - float(report.get("generated_at"))
    if age_seconds > MAX_AUDIT_AGE_SECONDS:
        return fail(issues=[f"pipeline contract audit stale: {age_seconds:.1f}s"], age_seconds=age_seconds)
    return ok(age_seconds=round(age_seconds, 3), result_path=str(RESULT_PATH),
              registered_count=(report.get("summary") or {}).get("registered_count"))


def v_pipeline_contract_registry_clean(ctx):
    check, report = _pipeline_contract_check(ctx, "registry_clean")
    if not check.get("passed"):
        return fail(issues=check.get("issues") or ["pipeline registry contract violations"], hard=True,
                    registered_count=(report.get("summary") or {}).get("registered_count"))
    return ok(registered_count=(report.get("summary") or {}).get("registered_count"))


def v_pipeline_contract_manifest_parity(ctx):
    check, _report = _pipeline_contract_check(ctx, "manifest_parity")
    if not check.get("passed"):
        return fail(issues=check.get("issues") or ["production pipeline manifest drift"], hard=True,
                    missing_from_manifest=check.get("missing_from_manifest"),
                    extra_in_manifest=check.get("extra_in_manifest"))
    return ok(missing_from_manifest=check.get("missing_from_manifest"),
              extra_in_manifest=check.get("extra_in_manifest"))


def v_pipeline_contract_director_tasks_known(ctx):
    check, _report = _pipeline_contract_check(ctx, "director_tasks")
    if not check.get("passed"):
        return fail(issues=check.get("issues") or ["director task contract violations"], hard=True,
                    unknown_pipelines=check.get("unknown_pipelines"),
                    tasks_missing_fields=check.get("tasks_missing_fields"))
    return ok(task_count=check.get("task_count"))


def v_pipeline_contract_no_operator_only_writes(ctx):
    check, _report = _pipeline_contract_check(ctx, "operator_only_writes")
    if not check.get("passed"):
        return fail(issues=check.get("issues") or ["operator-only state write found"], hard=True,
                    findings=check.get("findings"))
    return ok(scanned_files=check.get("scanned_files"))


def v_handoff_generated_truth_matches_disk(ctx):
    """State truth gate (2026-07-01 audit): codex_handoff.json claimed a green 173-validator suite
    and 7 active humanoids while disk truth was a REJECTED 162-validator suite and 6 humanoids.
    The handoff's generated_truth block must match the latest full-suite report and the roster."""
    full_path = ctx.root / "artifacts" / "validation" / "validation_report_full.json"
    handoff_path = ctx.root / "codex_handoff.json"
    if not full_path.exists():
        raise BlockedError("validation_report_full.json missing: run one full-scope suite to bootstrap state truth")
    if not handoff_path.exists():
        raise BlockedError("codex_handoff.json missing")
    report = json.loads(full_path.read_text(encoding="utf-8"))
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    truth = handoff.get("generated_truth")
    if not isinstance(truth, dict):
        raise BlockedError("codex_handoff.json has no generated_truth block: state truth sync has not run")
    issues = []
    source = truth.get("source_report") or {}
    if source.get("run_ts") != report.get("run_ts"):
        issues.append(f"handoff truth derives from run_ts {source.get('run_ts')} "
                      f"but the latest full report is run_ts {report.get('run_ts')}")
    if truth.get("suite_verdict") != report.get("suite_verdict"):
        issues.append(f"handoff verdict {truth.get('suite_verdict')!r} != report verdict {report.get('suite_verdict')!r}")
    if truth.get("counts") != report.get("counts"):
        issues.append(f"handoff counts {truth.get('counts')} != report counts {report.get('counts')}")
    roster_path = ctx.root / "config" / "character_roster.json"
    if roster_path.exists():
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        if truth.get("active_humanoid_target") != roster.get("active_humanoid_target"):
            issues.append(f"handoff humanoid target {truth.get('active_humanoid_target')} "
                          f"!= roster {roster.get('active_humanoid_target')}")
        if sorted(truth.get("quarantined_humanoids") or []) != sorted((roster.get("quarantined_humanoids") or {}).keys()):
            issues.append("handoff quarantine list != roster quarantine list")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(run_ts=report.get("run_ts"), suite_verdict=report.get("suite_verdict"))


def v_wanefall_autonomy_queue_copy_synced(ctx):
    """The WANEFALL-side queue copy had silently drifted since 2026-06-28. It is now mirrored by the
    same writer that regenerates the queue; this gate keeps the two byte-identical, fail-closed."""
    import hashlib
    src = ctx.root / "artifacts" / "autonomy" / "recursive_improvement_queue.json"
    dst = ctx.project / "Config" / "WANEFALL_AutonomyQueue" / "recursive_improvement_queue.json"
    if not src.exists():
        raise BlockedError(f"autonomy queue missing: {src}")
    if not dst.exists():
        raise BlockedError(f"WANEFALL queue copy missing: {dst} (regenerate the autonomy matrix to mirror it)")
    src_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    dst_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
    if src_hash != dst_hash:
        return fail(issues=[f"WANEFALL queue copy drifted from source (src {src_hash[:12]}.. != dst {dst_hash[:12]}..)"],
                    hard=True, src=str(src), dst=str(dst))
    return ok(sha256=src_hash)


def _metahuman_utilization_report(ctx):
    from dimwit.pipelines.metahuman_utilization import (
        PROJECT as MH_PROJECT,
        RESULT_PATH,
        UE_ROOT,
        write_metahuman_utilization_audit,
    )

    write_metahuman_utilization_audit(ctx.root, MH_PROJECT, UE_ROOT, RESULT_PATH)
    try:
        return json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlockedError(f"MetaHuman utilization audit unreadable: {exc}") from exc


def v_metahuman_audit_fresh(ctx):
    from dimwit.pipelines.metahuman_utilization import MAX_AUDIT_AGE_SECONDS, RESULT_PATH

    report = _metahuman_utilization_report(ctx)
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        raise BlockedError("MetaHuman utilization audit generated_at missing or not numeric")
    age_seconds = time.time() - float(generated_at)
    if age_seconds > MAX_AUDIT_AGE_SECONDS:
        return fail(issues=[f"MetaHuman utilization audit stale: {age_seconds:.1f}s"], age_seconds=age_seconds)
    return ok(age_seconds=round(age_seconds, 3), result_path=str(RESULT_PATH),
              classification=(report.get("summary") or {}).get("classification"))


def v_metahuman_source_3d_assets_ready(ctx):
    report = _metahuman_utilization_report(ctx)
    missing = [
        item.get("asset_name") for item in report.get("characters", [])
        if not item.get("source_ready")
    ]
    if missing:
        return fail(issues=[f"MetaHuman source assets not ready: {missing}"], hard=True, missing=missing)
    summary = report.get("summary") or {}
    return ok(source_ready_count=summary.get("source_ready_count"),
              expected_character_count=summary.get("expected_character_count"))


def v_metahuman_version_gate_respected(ctx):
    report = _metahuman_utilization_report(ctx)
    gate = ((report.get("unreal") or {}).get("dna_calibration_version_gate") or {})
    classification = gate.get("classification")
    if classification not in {
        "BLOCKED_UNREAL_VERSION",
        "POTENTIALLY_USABLE_INTERNAL_TOOLING",
        "NEEDS_REVIEW",
    }:
        return fail(issues=[f"unknown MetaHuman DNA version gate classification: {classification}"], hard=True)
    if classification == "BLOCKED_UNREAL_VERSION" and gate.get("recommended_workflow") != "MetaHuman for Maya":
        return fail(issues=["UE 5.6+ MetaHuman gate must recommend MetaHuman for Maya"], hard=True, gate=gate)
    return ok(gate=gate)


def v_metahuman_license_boundaries_clean(ctx):
    report = _metahuman_utilization_report(ctx)
    refs = {item.get("source_name"): item for item in report.get("external_references", [])}
    boundaries = report.get("boundaries") or {}
    issues = []
    char_dna = refs.get("Character DNA Addon") or {}
    epic_dna = refs.get("Epic MetaHuman DNA Calibration") or {}
    if char_dna.get("adoption_mode") != "REFERENCE_ONLY" or char_dna.get("license_class") != "GPL_REFERENCE_ONLY":
        issues.append("Character DNA Addon must remain GPL/reference-only")
    if epic_dna.get("adoption_mode") != "OFFICIAL_REFERENCE_WITH_VERSION_GATE":
        issues.append("Epic MetaHuman DNA Calibration must remain official/reference-with-version-gate")
    if boundaries.get("no_gpl_code_copied") is not True:
        issues.append("GPL contamination boundary not proven")
    if boundaries.get("no_epic_tooling_redistributed") is not True:
        issues.append("Epic tooling redistribution boundary not proven")
    if issues:
        return fail(issues=issues, hard=True)
    return ok(reference_count=len(refs), boundaries=boundaries)


def v_metahuman_transform_output_evidence_present(ctx):
    report = _metahuman_utilization_report(ctx)
    outputs = report.get("metahuman_outputs") or {}
    if not outputs.get("present"):
        raise BlockedError("no MetaHuman output evidence found; source 3D assets are ready but transformation is not proven")
    return ok(output_count=outputs.get("count"), paths=outputs.get("paths"))


def _character_source_sync_report(ctx):
    cached = getattr(ctx, "_character_source_sync_report_cache", None)
    if isinstance(cached, dict):
        return cached
    from dimwit.pipelines.character_source_sync import RESULT_PATH, write_character_source_sync_report

    report = write_character_source_sync_report(ctx.root, ctx.project, RESULT_PATH)
    setattr(ctx, "_character_source_sync_report_cache", report)
    return report


def v_character_source_sync_chain(ctx):
    report = _character_source_sync_report(ctx)
    failed = []
    blocked = []
    for row in report.get("characters", []):
        for stage_name, stage in (row.get("stages") or {}).items():
            state = stage.get("state")
            if state == "FAIL":
                failed.append(f"{row.get('key')}:{stage_name}: {'; '.join(stage.get('issues') or [])}")
            elif state == "BLOCKED":
                action = row.get("next_action") or {}
                blocked.append(f"{row.get('key')}:{stage_name}: {action.get('action') or 'missing_evidence'}")
    if failed:
        return fail(issues=failed[:8], hard=True, summary=report.get("summary"))
    if blocked:
        raise BlockedError("; ".join(blocked[:8]))
    return ok(**(report.get("summary") or {}))


def _character_roster_policy_report(ctx):
    cached = getattr(ctx, "_character_roster_policy_report_cache", None)
    if isinstance(cached, dict):
        return cached
    from dimwit.pipelines.character_roster_policy import RESULT_PATH, write_character_roster_policy_report

    report = write_character_roster_policy_report(ctx.root, ctx.project, RESULT_PATH)
    setattr(ctx, "_character_roster_policy_report_cache", report)
    return report


def v_character_roster_policy(ctx):
    from dimwit.pipelines.character_roster_policy import validate_character_roster_policy

    report = _character_roster_policy_report(ctx)
    result = validate_character_roster_policy(report)
    if not result.get("passed"):
        return fail(issues=result.get("issues", [])[:8], hard=True, summary=report.get("summary"))
    return ok(**(report.get("summary") or {}))


def _autonomy_report(ctx):
    cached = getattr(ctx, "_autonomy_report_cache", None)
    if isinstance(cached, dict):
        return cached
    from dimwit.pipelines.autonomy_capability_matrix import (
        FINAL_REPORT_PATH,
        MATRIX_PATH,
        QUEUE_PATH,
        write_autonomy_capability_matrix,
    )

    report = write_autonomy_capability_matrix(ctx.root, ctx.project, MATRIX_PATH, QUEUE_PATH, FINAL_REPORT_PATH)
    setattr(ctx, "_autonomy_report_cache", report)
    return report


def _autonomy_validation(ctx):
    from dimwit.pipelines.autonomy_capability_matrix import validate_autonomy_report

    report = _autonomy_report(ctx)
    return validate_autonomy_report(report)


def v_autonomy_matrix_fresh(ctx):
    from dimwit.pipelines.autonomy_capability_matrix import MAX_ARTIFACT_AGE_SECONDS

    report = _autonomy_report(ctx)
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        raise BlockedError("autonomy report generated_at missing or not numeric")
    age_seconds = time.time() - float(generated_at)
    if age_seconds > MAX_ARTIFACT_AGE_SECONDS:
        raise BlockedError(f"autonomy report age {age_seconds:.1f}s exceeds {MAX_ARTIFACT_AGE_SECONDS}s")
    return ok(age_seconds=round(age_seconds, 3),
              capability_count=len(report.get("capability_matrix") or []),
              queue_count=len(report.get("recursive_improvement_queue") or []))


def v_autonomy_matrix_covers_required_lanes(ctx):
    result = _autonomy_validation(ctx)
    issues = [issue for issue in result.get("issues", []) if str(issue).startswith("missing required lanes")]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(required_lane_count=result.get("required_lane_count"))


def v_autonomy_external_references_classified(ctx):
    result = _autonomy_validation(ctx)
    issues = [
        issue for issue in result.get("issues", [])
        if "external reference" in str(issue) or "missing license" in str(issue)
        or "missing adoption" in str(issue) or "missing dependency" in str(issue)
        or "missing final_classification" in str(issue)
    ]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(reference_count=result.get("reference_count"))


def v_autonomy_queue_ranked_actions(ctx):
    report = _autonomy_report(ctx)
    queue = report.get("recursive_improvement_queue") if isinstance(report.get("recursive_improvement_queue"), list) else []
    if not queue:
        raise BlockedError("autonomy recursive improvement queue is empty")
    ranks = [item.get("rank") for item in queue if isinstance(item, dict)]
    if ranks != list(range(1, len(ranks) + 1)):
        return fail(issues=["autonomy queue ranks are not contiguous from 1"], ranks=ranks, hard=True)
    return ok(queue_count=len(queue), top_candidate=queue[0].get("title"))


def v_autonomy_queue_actions_have_validation_and_rollback(ctx):
    result = _autonomy_validation(ctx)
    issues = [
        issue for issue in result.get("issues", [])
        if "validation_command" in str(issue) or "rollback_notes" in str(issue)
        or "promotion threshold" in str(issue)
    ]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(queue_count=result.get("queue_count"))


def v_autonomy_no_operator_only_promotions(ctx):
    result = _autonomy_validation(ctx)
    issues = [issue for issue in result.get("issues", []) if "operator-only state leaked" in str(issue)]
    if issues:
        return fail(issues=issues, hard=True)
    return ok()


def _unreal_game_builder_report(ctx):
    cached = getattr(ctx, "_unreal_game_builder_report_cache", None)
    if isinstance(cached, dict):
        return cached
    from dimwit.pipelines.unreal_game_builder_engine import (
        DOCTRINE_PATH,
        FINAL_REPORT_PATH,
        SCORECARD_PATH,
        write_unreal_game_builder_report,
    )

    report = write_unreal_game_builder_report(ctx.root, ctx.project, DOCTRINE_PATH, SCORECARD_PATH, FINAL_REPORT_PATH)
    setattr(ctx, "_unreal_game_builder_report_cache", report)
    return report


def _unreal_game_builder_validation(ctx):
    from dimwit.pipelines.unreal_game_builder_engine import validate_unreal_game_builder_report

    report = _unreal_game_builder_report(ctx)
    return validate_unreal_game_builder_report(report)


def v_unreal_game_builder_fresh(ctx):
    from dimwit.pipelines.unreal_game_builder_engine import MAX_ARTIFACT_AGE_SECONDS

    report = _unreal_game_builder_report(ctx)
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        raise BlockedError("unreal game-builder report generated_at missing or not numeric")
    age_seconds = time.time() - float(generated_at)
    if age_seconds > MAX_ARTIFACT_AGE_SECONDS:
        raise BlockedError(f"unreal game-builder report age {age_seconds:.1f}s exceeds {MAX_ARTIFACT_AGE_SECONDS}s")
    return ok(age_seconds=round(age_seconds, 3),
              lane_count=len(report.get("game_builder_lanes") or []),
              queue_count=len(report.get("recursive_game_build_queue") or []),
              classification=report.get("classification"))


def v_unreal_game_builder_covers_required_lanes(ctx):
    result = _unreal_game_builder_validation(ctx)
    issues = [issue for issue in result.get("issues", []) if str(issue).startswith("missing required game-builder lanes")]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(required_lane_count=result.get("required_lane_count"), lane_count=result.get("lane_count"))


def v_unreal_game_builder_lane_validation_and_rollback(ctx):
    result = _unreal_game_builder_validation(ctx)
    issues = [
        issue for issue in result.get("issues", [])
        if "validation_command" in str(issue)
        or "rollback" in str(issue)
        or "non-review promotion threshold" in str(issue)
        or "required_artifacts" in str(issue)
        or "unreal_touchpoints" in str(issue)
    ]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(lane_count=result.get("lane_count"), queue_count=result.get("queue_count"))


def v_unreal_game_builder_current_blockers_visible(ctx):
    result = _unreal_game_builder_validation(ctx)
    issues = [
        issue for issue in result.get("issues", [])
        if "current blocker" in str(issue) or "remaining_global_blockers" in str(issue)
    ]
    if issues:
        return fail(issues=issues, hard=True)
    return ok(blocker_count=result.get("blocker_count"))


def v_unreal_game_builder_queue_prioritizes_blockers(ctx):
    report = _unreal_game_builder_report(ctx)
    queue = report.get("recursive_game_build_queue") if isinstance(report.get("recursive_game_build_queue"), list) else []
    blockers = report.get("remaining_global_blockers") if isinstance(report.get("remaining_global_blockers"), list) else []
    if blockers and not queue:
        raise BlockedError("current validation blockers exist but game-build queue is empty")
    ranks = [item.get("rank") for item in queue if isinstance(item, dict)]
    if ranks and ranks != list(range(1, len(ranks) + 1)):
        return fail(issues=["game-build queue ranks are not contiguous from 1"], hard=True, ranks=ranks)
    top = queue[0] if queue else {}
    if blockers and top.get("current_state") == "PASS":
        return fail(issues=["top game-build queue item is already PASS while blockers remain"], hard=True)
    return ok(queue_count=len(queue), top_candidate=top.get("title"), blocker_count=len(blockers))


def v_unreal_game_builder_no_operator_only_promotions(ctx):
    result = _unreal_game_builder_validation(ctx)
    issues = [issue for issue in result.get("issues", []) if "operator-only state leaked" in str(issue)]
    if issues:
        return fail(issues=issues, hard=True)
    return ok()


# ============================================================ AUDIO FOUNDATION (Horizon 2, §B5)
def v_audio_event_cue_coverage(ctx):
    from dimwit.pipelines.audio_foundation import (
        check_event_cue_coverage, live_cue_manifest, live_cue_map, live_enum_values)
    enum = live_enum_values()
    if not enum:
        raise BlockedError("EWanefallCombatEventType enum not parseable (WanefallCombatEvent.h)")
    manifest = live_cue_manifest()
    if manifest is None:
        raise BlockedError("Config/WANEFALL_Audio/cue_coverage.json missing/unreadable")
    r = check_event_cue_coverage(enum, live_cue_map(), manifest)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(covered=r["covered"], total=r["total"], exempt=r["exempt"])


def v_audio_cue_assets_resolvable(ctx):
    from dimwit.pipelines.audio_foundation import AUDIO_ART, check_cue_assets_resolvable, live_cue_manifest
    manifest = live_cue_manifest()
    if manifest is None:
        raise BlockedError("cue_coverage.json missing/unreadable")
    r = check_cue_assets_resolvable(manifest, AUDIO_ART)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(resolved=r["resolved"], total=r["total"])


def v_audio_bus_architecture_declared(ctx):
    from dimwit.pipelines.audio_foundation import check_bus_manifest, live_bus_manifest
    manifest = live_bus_manifest()
    if manifest is None:
        raise BlockedError("Config/WANEFALL_Audio/bus_architecture.json missing/unreadable")
    r = check_bus_manifest(manifest)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(buses=r["buses"])


def v_audio_loudness_within_bounds(ctx):
    from dimwit.pipelines.audio_foundation import check_loudness_bounds, live_audio_assets, live_bus_manifest
    assets = live_audio_assets()
    if not assets:
        raise BlockedError("no cue WAVs on disk (run dimwit.pipelines.audio_sfx.synthesize_all)")
    r = check_loudness_bounds(assets, live_bus_manifest() or {})
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(checked=r["checked"])


def v_audio_true_peak_ceiling(ctx):
    from dimwit.pipelines.audio_foundation import check_true_peak, live_audio_assets, live_bus_manifest
    assets = live_audio_assets()
    if not assets:
        raise BlockedError("no cue WAVs on disk (run audio_sfx.synthesize_all)")
    r = check_true_peak(assets, live_bus_manifest() or {})
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(checked=r["checked"])


def v_audio_no_silent_wavs(ctx):
    from dimwit.pipelines.audio_foundation import check_no_silence, live_audio_assets
    assets = live_audio_assets()
    if not assets:
        raise BlockedError("no cue WAVs on disk (run audio_sfx.synthesize_all)")
    r = check_no_silence(assets)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(checked=r["checked"])


def v_audio_sfx_provenance(ctx):
    from dimwit.pipelines.audio_foundation import AUDIO_ART, live_cue_manifest, live_provenance
    from dimwit.pipelines.audio_sfx import check_sfx_provenance
    manifest = live_cue_manifest()
    if manifest is None:
        raise BlockedError("cue_coverage.json missing/unreadable")
    r = check_sfx_provenance(manifest, live_provenance(), AUDIO_ART)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(checked=r["checked"])


def v_audio_cue_playback_wired(ctx):
    from dimwit.pipelines.audio_foundation import check_cue_playback_wired, live_cue_playback_sources
    sub, gs = live_cue_playback_sources()
    if not sub or not gs:
        raise BlockedError("cue subsystem / game-state source missing (AUDIO_RUNTIME_V1 not present?)")
    r = check_cue_playback_wired(sub, gs)
    if not r["passed"]:
        return fail(issues=r["issues"][:8], hard=True)
    return ok(wired=True)


def v_audio_bus_submix_assets_present(ctx):
    # UE-authored USoundSubmix assets matching the manifest. The operator UE session (scripts/ue/ue_audio_bus_install.py)
    # writes artifacts/audio/bus_install_result.json; absent => BLOCKED (fail-closed, never silent PASS).
    from dimwit.pipelines.audio_foundation import AUDIO_ART, EXPECTED_BUSES
    res = AUDIO_ART / "bus_install_result.json"
    if not res.exists():
        raise BlockedError("no bus_install_result.json — run scripts/ue/ue_audio_bus_install.py (operator UE session)")
    try:
        rec = json.loads(res.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"bus_install_result.json unreadable: {e}")
    present = set(rec.get("submixes_present") or [])
    missing = [b for b in EXPECTED_BUSES if b not in present]
    if missing:
        return fail(issues=[f"submix asset missing for bus {b}" for b in missing], hard=True)
    return ok(submixes=sorted(present))


def v_audio_packaged_mix_has_signal(ctx):
    # Packaged-mix WASAPI-loopback silence-proof. Operator foreground lane (capture law clause 3):
    # scripts/pipeline/run_pipeline.py audio_mix_proof writes artifacts/audio/mix_proof_result.json; absent => BLOCKED.
    from dimwit.pipelines.audio_foundation import AUDIO_ART
    res = AUDIO_ART / "mix_proof_result.json"
    if not res.exists():
        raise BlockedError("no mix_proof_result.json — run 'scripts/pipeline/run_pipeline.py audio_mix_proof' (operator foreground)")
    try:
        rec = json.loads(res.read_text(encoding="utf-8"))
    except Exception as e:
        raise BlockedError(f"mix_proof_result.json unreadable: {e}")
    if not rec.get("passed"):
        return fail(issues=(rec.get("issues") or ["combat mix has no signal above floor"])[:6], hard=True)
    return ok(combat_peak=rec.get("combat_peak"), baseline_peak=rec.get("baseline_peak"),
              margin_db=rec.get("margin_db"), source=rec.get("source"))


# ============================================================ roster fidelity (14-char rig+anim+deform cert)
def _v_roster_fidelity_char(asset: str):
    def _fn(ctx):
        try:
            cert = _rfid.load_cert(asset)
        except BlockedError as e:
            return fail(issues=[str(e)], hard=True)
        result = _rfid.validate_cert(cert)
        if not result["passed"]:
            return fail(issues=result["issues"],
                        score=(cert.get("deformation") or {}).get("score") or 0.0)
        return ok(score=(cert.get("deformation") or {}).get("score") or 1.0,
                  kind=cert.get("kind"))
    _fn.__name__ = f"v_roster_fidelity_{asset}"
    return _fn


def v_roster_fidelity_coverage(ctx):
    cov = _rfid.roster_fidelity_coverage()
    if not cov["passed"]:
        return fail(issues=[f"V1 roster (humanoids) not fully certified; missing: {cov['missing']}"] + cov["issues"],
                    hard=True)
    return ok(covered=len(cov["covered"]), deferred=len(cov.get("deferred") or []))


def v_roster_fidelity_mechs_deferred_tracked(ctx):
    """Surface (never silently drop) the mech characters deferred out of the V1 fidelity gate. WARN, not a
    blocker: it keeps the deferral visible so V2 is not forgotten, and fails only if the deferral record
    (targets + reason) goes missing/empty while mechs are still active roster."""
    deferred = _rfid.deferred_targets()
    if not deferred:
        return ok(deferred=0)
    if not _rfid.DEFERRAL_REASON:
        return fail(issues=["mechs deferred from fidelity gate but no deferral reason recorded"])
    return ok(deferred=[t["asset"] for t in deferred], reason=_rfid.DEFERRAL_REASON)


# ============================================================ MODE_CONTRACT_V1 (masterplan §B6 — headless
# mode-rule gates over FWanefallModeSimHarness via the WanefallModeSimProof commandlet). Every verdict is
# recomputed from the proof's raw `fields` block (mode_contract.py), never the reported `pass`. The
# commandlet is harvested ONCE per suite run (module-level cache in mode_contract.py); a harvest failure
# (UE/uproject absent, commandlet crash, missing .done marker) raises ModeContractBlocked -> BlockedError
# -> BLOCKED for every one of these nine gates, never a silent PASS.
def _mode_contract_proof(ctx):
    from dimwit.pipelines import mode_contract as _mc
    try:
        proof_path = _mc.harvested_proof_path()
    except _mc.ModeContractBlocked as exc:
        raise BlockedError(str(exc)) from exc
    try:
        return _mc.load_proof(proof_path)
    except _mc.ModeProofError as exc:
        raise BlockedError(str(exc)) from exc


def _mode_contract_check(ctx, check_fn):
    proof = _mode_contract_proof(ctx)
    passed, detail = check_fn(proof)
    if not passed:
        return fail(issues=[detail], hard=True, detail=detail)
    return ok(detail=detail)


def v_mode_contract_proof_present(ctx):
    from dimwit.pipelines import mode_contract as _mc
    proof = _mode_contract_proof(ctx)
    # _mc.ARTIFACT_PROOF is now absolute (anchored to _mc.ROOT), the SAME path
    # run_commandlet_and_harvest()/load_proof() write/read -- joining ctx.root here is a no-op
    # (Path.__truediv__ short-circuits to the absolute right operand) but keeps this call-site
    # consistent with every other ctx.root-relative artifact lookup in this file.
    proof_path = ctx.root / _mc.ARTIFACT_PROOF
    if not proof_path.exists():
        raise BlockedError(f"mode-sim proof artifact missing after harvest: {proof_path}")
    age_seconds = time.time() - proof_path.stat().st_mtime
    if age_seconds > _mc.PROOF_MAX_AGE_SECONDS:
        return fail(issues=[f"mode-sim proof stale: age {age_seconds:.1f}s > {_mc.PROOF_MAX_AGE_SECONDS}s"],
                    age_seconds=round(age_seconds, 3), max_age_seconds=_mc.PROOF_MAX_AGE_SECONDS)
    return ok(mode_count=proof.get("mode_count"), age_seconds=round(age_seconds, 3),
              max_age_seconds=_mc.PROOF_MAX_AGE_SECONDS)


def v_mode_contract_arena_suite(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_arena_suite)


def v_mode_contract_large_suite(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_large_suite)


def v_mode_contract_arcade_suite(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_arcade_suite)


def v_mode_contract_ui_foundation(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_ui_foundation)


def v_mode_contract_wanetrial_second_chance(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_wanetrial)


def v_mode_contract_practice_range(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_practice)


def v_mode_contract_demo_modes_covered(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_demo_covered)


def v_mode_contract_recompute(ctx):
    from dimwit.pipelines import mode_contract as _mc
    return _mode_contract_check(ctx, _mc.check_recompute_all)


# ============================================================ REGISTRY ASSEMBLY
def build_registry() -> list:
    reg = []
    for c in CHARS:
        reg += [_v_char_nanite_enabled(c), _v_char_nanite_flag(c), _v_char_uasset_bytes(c),
                _v_char_mic_parent(c), _v_char_basecolor(c), _v_char_metallic(c),
                _v_char_provenance(c), _v_char_no_double_nest(c)]
    reg += [
        Validator("character_multiview_symmetry", "character_anatomy", P.PERCEPTION, S.BLOCKER,
                  "artifacts/<char>_textured/mview_front|side|threequarter.png",
                  "front-only proof misses side-view arm deformation/asymmetry",
                  v_character_multiview_symmetry),
    ]
    RP = "character_roster_policy"
    reg += [
        Validator("character_roster_policy_gate", RP, P.FILESYSTEM, S.BLOCKER,
                  "config/character_roster.json + mech/static evidence",
                  "retired prototype still blocks or re-enters autonomous work queue",
                  v_character_roster_policy),
    ]
    CS = "character_source_sync"
    reg += [
        Validator("character_source_sync_chain", CS, P.FILESYSTEM, S.BLOCKER,
                  "Hi3D GLB -> Blender reviews -> UE import -> MetaHuman output",
                  "website-generated meshes bypass Blender anatomy, MetaHuman, or Unreal proof",
                  v_character_source_sync_chain),
    ]
    D = "rigged_skeletal_meshes"
    reg += [
        Validator("rig_is_skeletalmesh", D, P.UE_PYTHON, S.BLOCKER, _primary_rig_path(), "static-not-skeletal pawn", v_rig_is_skeletal, ["ue"]),
        Validator("rig_skeleton_is_sk_mannequin", D, P.UE_PYTHON, S.BLOCKER, "rig skeleton", "wrong-skeleton ref-pose freeze", v_rig_skeleton, ["ue"]),
        Validator("rig_weight_coverage", D, P.STATIC, S.BLOCKER, "rig.json", "partial skinning explode", v_rig_weight_coverage),
        Validator("rig_max_influences_le_4", D, P.STATIC, S.BLOCKER, "rig.json", "skinning budget break", v_rig_max_influences),
        Validator("rig_bone_count_ge_50", D, P.STATIC, S.BLOCKER, "rig.json", "stripped skeleton", v_rig_bone_count),
        Validator("rig_bounds_height", D, P.UE_PYTHON, S.WARN, "rig bounds", "import scale blowup", v_rig_bounds_height, ["ue"]),
        Validator("rig_material_not_legacy_phong", D, P.UE_PYTHON, S.BLOCKER, "CharactersRigged/pbr_material", "legacy-Phong dark + fallback blob", v_rig_material_not_phong, ["ue"]),
        Validator("rig_provenance_promotable", D, P.STATIC, S.BLOCKER, "rigging provenance", "promote rig w/o source/license", v_rig_provenance),
        Validator("rig_perception_ship_lighting", D, P.PERCEPTION, S.BLOCKER, "cap_rig_ship.png", "dark/blob/legacy-Phong; byte-size stamp", v_rig_perception_ship, ["ue"]),
        Validator("rig_capture_texture_streaming_off", D, P.UE_PYTHON, S.BLOCKER, "ue_probe_batch.json captures.rig_ship",
                  "washed low-mip rig capture treated as texture truth (tick-less sessions never stream mips)",
                  v_rig_capture_texture_streaming_off, ["ue"]),
        Validator("rig_deformation_clean", D, P.PERCEPTION, S.BLOCKER, "pose_capture_result.json",
                  "frozen / candy-wrapper-collapse / skinning-explosion rig that structural QA rubber-stamps",
                  v_rig_deformation),
        Validator("rig_deform_identity_bound", D, P.STATIC, S.BLOCKER, "pose_capture_result.json identity",
                  "stale-roster (ekris-era) or re-imported-rig pose evidence keeping the deformation gate green",
                  v_rig_deform_identity_bound),
        Validator("rig_deform_joints_articulated", D, P.STATIC, S.BLOCKER, "pose_capture_result.json joints",
                  "partially-frozen clip (limb joints never evaluated) passing as deformation proof",
                  v_rig_deform_joints_articulated),
        Validator("rig_deform_silhouette_judged", D, P.STATIC, S.BLOCKER, "pose_capture_result.json verdicts",
                  "semantic breakage (candy-wrapper twist / melted extremities) that pixel stats rubber-stamp",
                  v_rig_deform_silhouette_judged),
    ]
    A = "animation_wiring"
    reg += [
        Validator("anim_skeleton_compatible", A, P.UE_PYTHON, S.BLOCKER, "rig vs SK_Mannequin", "wrong-skeleton freeze", v_anim_skeleton_compatible, ["ue"]),
        Validator("anim_runtime_slot_match", A, P.STATIC, S.BLOCKER, "WanefallLobbyCharacter.cpp", "proof-vs-runtime slot mismatch", v_anim_runtime_slot_match),
        Validator("anim_video_motion_live", A, P.STATIC, S.WARN, "live game window", "frozen char in the actual running game (G5 video)", v_anim_video_motion),
        Validator("anim_locomotion_pose_evaluates", A, P.PERCEPTION, S.WARN, "two locomotion frames", "frozen-in-ref command character (PIE-only pixel proof)", v_anim_locomotion_pose_evaluates, ["ue"]),
        Validator("mrq_capture_advanced", A, P.FILESYSTEM, S.BLOCKER, "mrq_capture_result.json",
                  "frozen-bind-pose capture (MRQ animation didn't advance) that structural QA can't see",
                  v_mrq_capture_advanced),
    ]
    RF = "character_roster_fidelity"
    # V1 gate: BLOCKER cert per certifiable character (the 6 humanoids). Mechs are deferred to V2 and tracked
    # by the WARN validator below (surfaced, never silently dropped).
    for t in _rfid.certifiable_targets():
        reg.append(Validator(f"roster_fidelity_{t['asset']}", RF, P.STATIC, S.BLOCKER,
                             f"artifacts/roster_fidelity/{t['asset']}.json",
                             "roster character shipped without a rig+anim+deformation cert",
                             _v_roster_fidelity_char(t["asset"])))
    reg.append(Validator("roster_fidelity_coverage", RF, P.STATIC, S.BLOCKER,
                         "artifacts/roster_fidelity/*.json vs V1 certifiable roster (humanoids)",
                         "an active humanoid silently uncertified for rig+anim+deformation",
                         v_roster_fidelity_coverage))
    reg.append(Validator("roster_fidelity_mechs_deferred_tracked", RF, P.STATIC, S.WARN,
                         "roster_fidelity deferred_targets + reason",
                         "mechs dropped from the fidelity gate without a recorded V2 deferral",
                         v_roster_fidelity_mechs_deferred_tracked))
    CB = "combat"
    reg += [
        Validator("combat_state_clarity", CB, P.FILESYSTEM, S.BLOCKER, "combat_capture_result.json",
                  "LIVE/HIT/DESTROYED states indistinguishable -> no combat feedback", v_combat_state_clarity),
        Validator("combat_weakpoint_in_range", CB, P.FILESYSTEM, S.BLOCKER, "combat_capture_result.json",
                  "weak-point not readable as a targetable in-range RED core", v_combat_weakpoint_in_range),
    ]
    G = "gameplay_code"
    reg += [
        Validator("lobby_char_skeletal_not_static", G, P.STATIC, S.BLOCKER, "WanefallLobbyCharacter.cpp", "static/frozen command pawn", v_lobby_skeletal_not_static),
        Validator("grapple_uproperties_present", G, P.STATIC, S.BLOCKER, "WanefallPrototypeCharacter.h/.cpp", "GC-nulled grapple components", v_grapple_uproperties),
        Validator("defaultinput_grapple_mapping", G, P.FILESYSTEM, S.BLOCKER, "DefaultInput.ini", "Grapple mapping dropped", v_defaultinput_grapple),
        Validator("both_targets_compile_clean", G, P.COMPILE, S.BLOCKER, "UBT Editor+Game targets", "uncompilable gameplay edit", v_both_targets_compile),
        Validator("lobby_inrun_ship_lighting", G, P.PERCEPTION, S.BLOCKER, "Wanefall_ModeShell capture", "studio-capture-hidden dark/grey", v_lobby_inrun_ship, ["ue"]),
    ]
    M = "materials_shaders"
    reg += [
        Validator("all_char_mic_parents_gltf", M, P.UE_PYTHON, S.BLOCKER, "all char MICs", "legacy-Phong project-wide", v_all_char_mic_parents_gltf, ["ue"]),
        Validator("mf_master_compile_clean", M, P.STATIC, S.BLOCKER, "materials_build_result.json", "wires-4-but-fails-compile", v_mf_master_compile),
    ]
    E = "environment_maps"
    reg += [
        Validator("gen_arena_loads_no_fatal", E, P.STATIC, S.BLOCKER, "env_build_result.json", "commandlet crashed", v_env_loads),
        Validator("actor_count_min", E, P.STATIC, S.BLOCKER, "env_build_result.json", "empty/inflated arena", v_env_actor_count),
        Validator("player_start_count", E, P.STATIC, S.BLOCKER, "env_build_result.json", "unplayable spawn", v_env_starts),
        Validator("lighting_present_declared", E, P.STATIC, S.BLOCKER, "env_build_result.json", "all-black arena", v_env_lighting),
        Validator("wane_line_spine_core", E, P.STATIC, S.BLOCKER, "env_build_result.json", "missing collapse-axis identity", v_env_wane_line),
        Validator("frontend_maps_exist", E, P.FILESYSTEM, S.BLOCKER, "Maps dir", "deleted deploy target", v_frontend_maps_exist),
        Validator("frontdoor_deploy_spawn_safe", E, P.STATIC, S.BLOCKER, "WanefallLobbyPlayerController.cpp",
                  "command front door deploys into collision-prone map and strands the player",
                  v_frontdoor_deploy_spawn_safe),
        Validator("frontdoor_live_deploy_proof", E, P.FILESYSTEM, S.BLOCKER, "anim_live_proof.json + WanefallGreybox.log",
                  "front door passes static checks but fails live lobby-to-match deploy proof",
                  v_frontdoor_live_deploy_proof),
        Validator("lobby_umap_not_bloated", E, P.FILESYSTEM, S.WARN, "Wanefall_ModeShell_Prototype_01.umap", "dirty/bloated package", v_lobby_umap_not_bloated),
    ]
    V = "vfx_audio"
    reg += [
        Validator("niagara_real_with_emitters", V, P.UE_PYTHON, S.BLOCKER, "NS_Wane_*", "0-emitter rubber-stamp", v_niagara_real, ["ue"]),
        Validator("vfx_asset_on_disk", V, P.FILESYSTEM, S.WARN, "VFX dir", "empty-shell VFX", v_vfx_asset_disk),
        Validator("no_ai_slop_banter_fs", V, P.FILESYSTEM, S.BLOCKER, "Content/Wanefall", "reintroduced AI-slop banter", v_no_ai_slop_banter_fs),
    ]
    CV = "content_vcs"
    reg += [
        Validator("content_under_lfs", CV, P.FILESYSTEM, S.BLOCKER,
                  ".gitattributes LFS rules + Content/Wanefall ignore carve-out + real assets check-attr=lfs",
                  "irreplaceable 2.5G authored Content/Wanefall silently un-LFS'd or re-untracked",
                  v_content_under_lfs),
    ]
    BH = "build_hygiene"
    reg += [
        Validator("build_retention", BH, P.FILESYSTEM, S.BLOCKER,
                  "D:/WanefallBuild packaged run count within keep ceiling (+ current-manifest run)",
                  "unbounded ~4.8G/run packaged-build pileup exhausts the D: pressure valve (C: is full)",
                  v_build_retention),
    ]
    X = "cross_pipeline_consistency"
    reg += [
        Validator("manifest_reconciliation", X, P.STATIC, S.BLOCKER, "char_fidelity_result.json", "7 humanoids never re-measured", v_manifest_reconciliation),
        Validator("reference_consistency", X, P.STATIC, S.BLOCKER, "lobby cpp vs rig asset", "slice green but lobby loads stale/missing", v_reference_consistency),
        Validator("driver_result_freshness", X, P.FILESYSTEM, S.BLOCKER, "all *_result.json", "validators inherit stale self-report", v_driver_result_freshness),
    ]
    TOPO = "topology"
    reg += [
        Validator("topology_handcrafted_elite", TOPO, P.STATIC, S.BLOCKER, "artifacts/handcraft/*",
                  "triangle-soup/non-manifold/no-UV mesh that morphs & disfigures when rigged",
                  v_topology_handcrafted),
    ]
    OPT = "optics_semantic"
    reg += [
        Validator("optics_character_semantic", OPT, P.PERCEPTION, S.BLOCKER, "cap_rig_ship.png + creation cover",
                  "morphed/disfigured/off-model/placeholder-geo that pixel-stats rubber-stamp (vision-LLM)",
                  v_optics_character_semantic, ["ue"]),
        Validator("optics_judge_calibrated", OPT, P.FILESYSTEM, S.BLOCKER, "artifacts/optics_calibration + dimwit/goldens/optics",
                  "drifted/weakened vision judge silently passing washed renders (or flunking good ones)",
                  v_optics_judge_calibrated),
    ]
    # intent_conformance — the per-build INTENT CONTRACT gate: the declared picture/goals are compared to the
    # final capture, and the contract is proven un-retrofitted. Required domain for every strict asset_type.
    IC = "intent_conformance"
    reg += [
        Validator("intent_contract_no_drift", IC, P.STATIC, S.BLOCKER, "assets/<id>/intent_contract.json",
                  "target rubric retro-fitted/tampered or global DESIGN.md drift under the build",
                  v_intent_contract_no_drift),
        Validator("intent_target_conformance", IC, P.PERCEPTION, S.BLOCKER, "final capture vs declared reference",
                  "flawless render of the WRONG asset passing (identity not matched to the declared picture)",
                  v_intent_target_conformance),
    ]
    # DESIGN.md — the declared WANEFALL visual law (Google Labs DESIGN.md format) as a fail-closed gate.
    from dimwit.pipelines.design_md import design_md_validators
    reg += design_md_validators()
    MT = "proof_integrity"
    reg += [
        Validator("ledger_chain_actually_chained", MT, P.LEDGER, S.BLOCKER, "all ledgers", "empty/legacy/forged ledger passing", v_ledger_chains_intact),
        Validator("no_autonomous_operator_only_states", MT, P.LEDGER, S.BLOCKER, "all ledgers", "autonomous self-promotion past gate", v_no_autonomous_operator_states),
        Validator("promotion_threshold_ratchet", MT, P.STATIC, S.BLOCKER, "config/promotion/*.json", "learn-step lowering the bar", v_threshold_ratchet),
        Validator("provenance_fail_closed_triggers", MT, P.STATIC, S.BLOCKER, "base.py", "bypassed provenance gate", v_provenance_fail_closed),
        Validator("provenance_sources_on_disk", MT, P.STATIC, S.BLOCKER, "char_fidelity_result.json sources",
                  "self-asserted provenance strings with no real source file (G15)", v_provenance_sources_on_disk),
        Validator("capture_no_filesize_validity", MT, P.STATIC, S.BLOCKER, "capture scripts", "png_bytes>N rubber-stamp", v_capture_no_filesize_validity),
        Validator("perception_wiring_exists", MT, P.STATIC, S.BLOCKER, "perception.py", "validators stubbed against missing API", v_perception_wiring_exists),
        Validator("golden_regression_corpus", MT, P.STATIC, S.BLOCKER, "fixtures/", "refactor silently weakening a threshold", v_golden_regression_corpus),
    ]
    # ---- The four gameplay-facet CEILING gates (fail-closed; absent evidence -> BLOCKED, never a silent PASS).
    # These close the "deeply built but ungated for live quality" gap: traversal feel, in-play weapons, HUD
    # readability, and the BR loop now each have a pixel-truth / sim gate the recursive loop must satisfy.
    MV = "movement_traversal"
    reg += [
        Validator("traversal_signature_verbs_fire", MV, P.FILESYSTEM, S.BLOCKER, "traversal_capture_result.json",
                  "grapple/mantle/flip/agility compiled but never trigger -> no signature traversal", v_traversal_maneuvers_fire),
        Validator("traversal_grapple_continuous_swing", MV, P.FILESYSTEM, S.BLOCKER, "traversal_capture_result.json",
                  "grapple reads as a one-frame teleport-snap, not a continuous momentum swing", v_traversal_grapple_continuous),
        Validator("traversal_flip_rotates", MV, P.FILESYSTEM, S.BLOCKER, "traversal_capture_result.json",
                  "boost-flip fires but the body never visibly rotates (dead somersault / Euler-pitch read ~0)", v_traversal_flip_rotates),
        Validator("traversal_motion_advances", MV, P.FILESYSTEM, S.WARN, "traversal_capture_result.json",
                  "state says moved but the captured frames are frozen", v_traversal_motion_advances),
    ]
    WP = "weapons_inplay"
    reg += [
        Validator("weapons_no_white_placeholder", WP, P.FILESYSTEM, S.BLOCKER, "weapons_capture_result.json",
                  "recurring white-weapon regression: raw BasicShape sub-parts re-revealed in-hand", v_weapons_no_white_placeholder),
        Validator("weapons_ads_changes_camera", WP, P.FILESYSTEM, S.BLOCKER, "weapons_capture_result.json",
                  "ADS does not tighten FOV/boom -> a dead aim feature", v_weapons_ads_changes_camera),
        Validator("weapons_muzzle_tracks_crosshair", WP, P.FILESYSTEM, S.WARN, "weapons_capture_result.json",
                  "procedural weapon-aim off -> not 'with a gun' while swinging", v_weapons_muzzle_tracks_crosshair),
        # Facet 2 deeper layer (plan steps 2.2, 2.4)
        Validator("weapons_registry_mesh_resolves", WP, P.STATIC, S.BLOCKER, "Content/Wanefall/Dimwit/Weapons",
                  "25 gun registry slots exist in C++ but <25 .uasset files on disk -> broken entries", v_weapon_registry_mesh_resolves),
        Validator("weapons_visibility_order_law", WP, P.STATIC, S.BLOCKER, "WanefallPrototypeCharacter.cpp",
                  "white-weapon ordering law (hide sub-parts AFTER parent-show, propagate=false) absent in source", v_weapon_visibility_order),
    ]
    HUDD = "hud_readability"
    reg += [
        Validator("hud_core_elements_present", HUDD, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "Match HUD compiles but renders blank (no crosshair/health/state)", v_hud_core_elements_present),
        Validator("hud_design_md_tokens", HUDD, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "HUD off the DESIGN.md palette (stock white/grey, no Wane teal)", v_hud_design_tokens),
        Validator("hud_legible_contrast", HUDD, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "washed/low-contrast unreadable HUD", v_hud_legible),
    ]
    # Facet 3 deeper layer (plan steps 3.2, 3.4, 3.5)
    reg += [
        Validator("traversal_grapple_on_left_forearm", MV, P.STATIC, S.BLOCKER, "WanefallPrototypeCharacter.cpp",
                  "grapple device on hand_l instead of lowerarm_l (wrong anatomy, wrong cable origin)", v_grapple_on_left_forearm),
        Validator("traversal_boostflip_fires_and_displaces", MV, P.FILESYSTEM, S.BLOCKER, "traversal_capture_result.json",
                  "boost-flip stub: fires but no measured angular travel (reads dead / unreachable by player)", v_boostflip_fires_and_displaces),
        Validator("traversal_evasive_roll_present", MV, P.STATIC, S.WARN, "WanefallPrototypeCharacter.cpp",
                  "evasive roll absent or stubbed (no LaunchCharacter displacement)", v_evasive_roll_present),
    ]
    # Facet 4 — new ui_hud domain (plan step 4.9; weakpoint/typography pending C++ HUD changes)
    UH = "ui_hud"
    reg += [
        Validator("hud_live_frame_not_blank", UH, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "standalone white-frame trap: HUD capture is blank (DXGI flip + unfocused window)", v_hud_live_frame_not_blank),
        Validator("hud_crosshair_present_centered", UH, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "crosshair absent in live Match HUD — no aim reference while shooting", v_hud_crosshair_present_centered),
        Validator("hud_mode_state_surfaces", UH, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "BR/trial mode state absent from HUD — player can't read ring phase or match state", v_hud_mode_state_surfaces),
        Validator("hud_color_not_white_stock", UH, P.FILESYSTEM, S.BLOCKER, "hud_capture_result.json",
                  "HUD is stock white/grey — not WANE-branded (Wane teal < 0.5%)", v_hud_color_not_white_stock),
        Validator("hud_weakpoint_indicator_pending", UH, P.FILESYSTEM, S.WARN, "hud_capture_result.json",
                  "on-screen weak-point indicator absent (plan step 4.4 C++ projection pending)", v_hud_weakpoint_indicator_pending),
    ]
    BRL = "br_loop"
    reg += [
        Validator("br_ring_collapses", BRL, P.FILESYSTEM, S.BLOCKER, "br_loop_result.json",
                  "BR ring never contracts the playable space -> not a battle royale", v_br_ring_collapses),
        Validator("br_match_resolves", BRL, P.FILESYSTEM, S.BLOCKER, "br_loop_result.json",
                  "BR match never resolves / no attrition -> broken loop", v_br_match_resolves),
        Validator("br_topdown_reads", BRL, P.FILESYSTEM, S.WARN, "br_loop_result.json",
                  "top-down arena lanes/cover don't read", v_br_topdown_reads),
    ]
    PC = "pipeline_contracts"
    reg += [
        Validator("pipeline_contract_audit_fresh", PC, P.FILESYSTEM, S.BLOCKER,
                  "pipeline_contract_audit.json",
                  "stale or missing pipeline contract audit lets registry drift hide", v_pipeline_contract_audit_fresh),
        Validator("pipeline_contract_registry_clean", PC, P.STATIC, S.BLOCKER,
                  "dimwit.pipelines.PIPELINES",
                  "registered pipeline violates base contract while director still schedules it",
                  v_pipeline_contract_registry_clean),
        Validator("pipeline_contract_manifest_parity", PC, P.STATIC, S.BLOCKER,
                  "config/production_pipelines.json",
                  "production manifest silently omits or invents pipelines", v_pipeline_contract_manifest_parity),
        Validator("pipeline_contract_director_tasks_known", PC, P.STATIC, S.BLOCKER,
                  "config/director_tasks.json",
                  "director backlog references unknown or underspecified pipeline tasks",
                  v_pipeline_contract_director_tasks_known),
        Validator("pipeline_contract_no_operator_only_writes", PC, P.STATIC, S.BLOCKER,
                  "dimwit/**/*.py",
                  "autonomous code writes HUMAN_ACCEPTED or PROMOTED_TO_ACTIVE_SLICE",
                  v_pipeline_contract_no_operator_only_writes),
        Validator("handoff_generated_truth_matches_disk", PC, P.STATIC, S.BLOCKER,
                  "codex_handoff.json + artifacts/validation/validation_report_full.json + config/character_roster.json",
                  "handoff baton claims a suite verdict/roster that disk truth contradicts (stale-handoff drift)",
                  v_handoff_generated_truth_matches_disk),
        Validator("wanefall_autonomy_queue_copy_synced", PC, P.FILESYSTEM, S.BLOCKER,
                  "Config/WANEFALL_AutonomyQueue/recursive_improvement_queue.json",
                  "game-side autonomy queue copy silently drifts from the Dimwit source queue",
                  v_wanefall_autonomy_queue_copy_synced),
    ]
    MH = "metahuman_character_pipeline"
    reg += [
        Validator("metahuman_audit_fresh", MH, P.FILESYSTEM, S.BLOCKER,
                  "metahuman_utilization_audit.json",
                  "stale/missing MetaHuman utilization proof lets fake conversion claims pass",
                  v_metahuman_audit_fresh),
        Validator("metahuman_source_3d_assets_ready", MH, P.FILESYSTEM, S.BLOCKER,
                  "Hi3D GLBs + retopo FBXs + character fidelity records",
                  "3D character assets not actually ready for MetaHuman transformation",
                  v_metahuman_source_3d_assets_ready),
        Validator("metahuman_version_gate_respected", MH, P.STATIC, S.BLOCKER,
                  "UE version + MetaHuman DNA workflow gate",
                  "UE 5.6+ MetaHumans incorrectly routed through unsupported DNA Calibration assumptions",
                  v_metahuman_version_gate_respected),
        Validator("metahuman_license_boundaries_clean", MH, P.STATIC, S.BLOCKER,
                  "external character-pipeline reference decisions",
                  "GPL or Epic MetaHuman tooling copied/redistributed into WANEFALL runtime",
                  v_metahuman_license_boundaries_clean),
        Validator("metahuman_transform_output_evidence_present", MH, P.FILESYSTEM, S.BLOCKER,
                  "MetaHuman output evidence",
                  "source assets marked converted without MetaHuman character/DNA/Identity output evidence",
                  v_metahuman_transform_output_evidence_present),
    ]
    RG = "real_game_runtime"
    reg += [
        Validator("real_game_capture_fresh", RG, P.FILESYSTEM, S.BLOCKER, "real_game_validation_result.json",
                  "stale/missing real-game capture being treated as current truth", v_real_game_capture_fresh),
        Validator("real_game_window_nonblank", RG, P.FILESYSTEM, S.BLOCKER, "still.png",
                  "real game window absent, blank, white-frame, or black-frame", v_real_game_window_nonblank),
        Validator("real_game_no_fatal_log_burst", RG, P.FILESYSTEM, S.BLOCKER, "WanefallGreybox/Saved/Logs",
                  "runtime logs show fatal/errors during the real-game validation pass", v_real_game_no_fatal_log_burst),
        Validator("real_game_runtime_not_placeholder_dominated", RG, P.FILESYSTEM, S.BLOCKER, "still.png",
                  "visible runtime frame dominated by placeholder/simple white geometry", v_real_game_runtime_not_placeholder_dominated),
        Validator("real_game_gamefeaturedata_asset_rule", RG, P.STATIC, S.BLOCKER, "DefaultEngine.ini",
                  "GameFeatures plugin boot emits AssetManagerSettings GameFeatureData errors",
                  v_real_game_gamefeaturedata_asset_rule),
        Validator("real_game_no_broken_toolsets_boot_path", RG, P.STATIC, S.BLOCKER, "WanefallGreybox.uproject",
                  "experimental AllToolsets aggregator imports broken NiagaraToolsets Python at boot",
                  v_real_game_no_broken_toolsets_boot_path),
    ]
    PB = "packaged_build"
    reg += [
        Validator("packaged_build_result_fresh", PB, P.FILESYSTEM, S.BLOCKER,
                  "packaged_build_result.json",
                  "stale/missing packaged build proof being treated as release readiness",
                  v_packaged_build_result_fresh),
        Validator("packaged_build_manifest_complete", PB, P.FILESYSTEM, S.BLOCKER,
                  "package_manifest.json",
                  "UAT/package artifact missing while build is claimed ready",
                  v_packaged_build_manifest_complete),
        Validator("packaged_build_executable_hash_present", PB, P.FILESYSTEM, S.BLOCKER,
                  "WanefallGreybox.exe sha256",
                  "packaged executable not hashed/size-checked",
                  v_packaged_build_executable_hash_present),
        Validator("packaged_build_runtime_smoke_nonblank", PB, P.FILESYSTEM, S.BLOCKER,
                  "packaged runtime capture",
                  "package exists but packaged executable was never launched and visually smoked",
                  v_packaged_build_runtime_smoke_nonblank),
        Validator("packaged_build_log_scan_clean", PB, P.FILESYSTEM, S.BLOCKER,
                  "packaged Saved/Logs",
                  "packaged runtime emits fatal/errors during smoke",
                  v_packaged_build_log_scan_clean),
        Validator("packaged_build_queue_sync", PB, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim readiness without requiring packaged proof",
                  v_packaged_build_queue_sync),
        Validator("packaged_build_gameplay_motion_proven", PB, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/packaged_build_validation/gameplay/",
                  "a static menu screenshot passes as 'packaged proof' while no gameplay map is even cooked",
                  v_packaged_build_gameplay_motion_proven),
    ]
    # PERFORMANCE_BASELINE_GATES_V1 (masterplan bundle 4): packaged perf was UNMEASURED — these
    # gates make fps/frametime/memory a per-run, identity-bound, fail-closed truth. Floors are
    # ratchet-only (16.6ms p95 @1080p proxy min-spec; steady hitch count 0; 8192MB peak).
    PF = "performance_baseline"
    reg += [
        Validator("perf_baseline_result_fresh", PF, P.FILESYSTEM, S.BLOCKER,
                  "performance_baseline_result.json",
                  "stale/missing packaged performance proof treated as current perf truth",
                  v_perf_baseline_result_fresh),
        Validator("perf_baseline_identity_bound", PF, P.FILESYSTEM, S.BLOCKER,
                  "perf payload pid + package manifest sha256",
                  "perf numbers from the wrong process/build (or fabricated) passing as packaged truth",
                  v_perf_baseline_identity_bound),
        Validator("perf_baseline_measurement_conditions", PF, P.FILESYSTEM, S.BLOCKER,
                  "perf payload measurement block",
                  "vsync/frame-cap/smoothing silently flattening frametimes into a fake-clean capture",
                  v_perf_baseline_measurement_conditions),
        Validator("perf_baseline_segment_coverage", PF, P.FILESYSTEM, S.BLOCKER,
                  "menu + arena steady windows",
                  "a seconds-long capture speaking for steady-state performance",
                  v_perf_baseline_segment_coverage),
        Validator("perf_arena_frametime_floor", PF, P.FILESYSTEM, S.BLOCKER,
                  "arena steady p95_ms vs 16.6ms floor + steady trace cross-check",
                  "arena bot-match p95 frametime over the 60fps min-spec proxy floor",
                  v_perf_arena_frametime_floor),
        Validator("perf_arena_hitch_free", PF, P.FILESYSTEM, S.BLOCKER,
                  "arena steady hitch counts",
                  "visible stalls (>100ms frames) during play — masterplan hitch-count-0 gate",
                  v_perf_arena_hitch_free),
        Validator("perf_menu_frametime_floor", PF, P.FILESYSTEM, S.BLOCKER,
                  "menu steady p95_ms vs 16.6ms floor",
                  "command deck renders below 60fps p95 on the dev box",
                  v_perf_menu_frametime_floor),
        Validator("perf_memory_budget", PF, P.FILESYSTEM, S.BLOCKER,
                  "session peak UsedPhysical MB",
                  "memory creep/leak past the 8GB packaged budget goes unmeasured",
                  v_perf_memory_budget),
        Validator("perf_baseline_queue_sync", PF, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim perf readiness without the perf pipeline registered",
                  v_perf_baseline_queue_sync),
    ]
    # FIRSTPARTY_WANE_FX_V1 + NIAGARA_COOK_SAFETY_GATE (masterplan bundle 5): law 5 as a static
    # gate (cooked-only decal/component renderer failures) + first-party combat FX contracts.
    WFX = "wane_fx"
    reg += [
        Validator("niagara_cook_safety_referenced_clean", WFX, P.STATIC, S.BLOCKER,
                  "Source/** UNiagaraSystem finders -> Content/**.uasset binary scan",
                  "a decal/component-renderer Niagara re-enters gameplay and only the COOKED build crashes (law 5)",
                  v_niagara_cook_safety_referenced_clean),
        Validator("niagara_cook_safety_catches_known_bad", WFX, P.STATIC, S.BLOCKER,
                  "the two real cook-killer assets as on-disk golden negatives",
                  "a weakened/regressed scanner silently passes everything",
                  v_niagara_cook_safety_catches_known_bad),
        Validator("wane_fx_first_party_combat_surfaces", WFX, P.STATIC, S.BLOCKER,
                  "pulse rifle + arena game state finders vs /Game/Wanefall/Dimwit/VFX/NS_Wane_*",
                  "combat FX quietly stays example-pack (or impact keeps reusing the muzzle system)",
                  v_wane_fx_first_party_combat_surfaces),
        Validator("wane_fx_runtime_tint_wired", WFX, P.STATIC, S.BLOCKER,
                  "WanefallApplyWaneTint at all three spawn sites",
                  "duplicated FX keeps donor colors — 'wane FX' that never reads WANE",
                  v_wane_fx_runtime_tint_wired),
        Validator("wane_fx_spawned_in_packaged_match", WFX, P.FILESYSTEM, S.BLOCKER,
                  "packaged match log [WaneFX] spawn markers",
                  "first-party FX referenced but never proven to actually spawn in the package",
                  v_wane_fx_spawned_in_packaged_match),
    ]
    # BOT_BALANCE_TELEMETRY_HARNESS_V1 (masterplan bundle 6, §B2/A2): headless packaged
    # bot-vs-bot matches at scale; balance numbers become per-run truth with drift gates.
    BB = "bot_balance"
    reg += [
        Validator("bot_balance_result_fresh", BB, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/bot_balance/bot_balance_result.json age",
                  "stale bot-match telemetry speaking for current combat balance",
                  v_bot_balance_result_fresh),
        Validator("bot_balance_identity_bound", BB, P.FILESYSTEM, S.BLOCKER,
                  "telemetry flag/pid + package manifest sha256",
                  "balance numbers from the wrong process/build (or fabricated) passing as packaged truth",
                  v_bot_balance_identity_bound),
        Validator("bot_balance_measurement_conditions", BB, P.FILESYSTEM, S.BLOCKER,
                  "telemetry measurement block (fixed 60Hz deterministic nullrhi + combat constants)",
                  "wall-clock or mistuned sessions producing incomparable balance numbers",
                  v_bot_balance_measurement_conditions),
        Validator("bot_balance_match_coverage", BB, P.FILESYSTEM, S.BLOCKER,
                  "matches[] count + wane variants + per-match combat floors",
                  "a couple of thin matches speaking for balance at scale",
                  v_bot_balance_match_coverage),
        Validator("bot_balance_sanity_invariants", BB, P.FILESYSTEM, S.BLOCKER,
                  "TTK theoretical floor + win-rate band + heatmap spread + wane curve monotonicity",
                  "physically impossible or degenerate telemetry laundered into balance receipts",
                  v_bot_balance_sanity_invariants),
        Validator("bot_balance_aggregate_recompute", BB, P.FILESYSTEM, S.BLOCKER,
                  "reported aggregates vs per-match recomputation",
                  "a fabricated headline aggregate that its own match data contradicts",
                  v_bot_balance_aggregate_recompute),
        Validator("bot_balance_drift_gates", BB, P.FILESYSTEM, S.BLOCKER,
                  "aggregates vs pinned committed baseline bands",
                  "combat tuning silently drifting with no receipt against the pinned baseline",
                  v_bot_balance_drift_gates),
        Validator("bot_balance_queue_sync", BB, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim balance readiness without the bot-balance pipeline registered",
                  v_bot_balance_queue_sync),
    ]
    # PROGRESSION_PERSISTENCE_V1 (Horizon 2, §B6): progression EARNED from a real bot-match seat and
    # PERSISTED across a real relaunch; xp/level/challenges recomputed from emitted apply-proofs.
    PR = "progression"
    reg += [
        Validator("progression_result_fresh", PR, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/progression/progression_result.json age",
                  "stale progression proof speaking for the current earn/persistence path",
                  v_progression_result_fresh),
        Validator("progression_evidence_bound", PR, P.FILESYSTEM, S.BLOCKER,
                  "exe sha256 at run vs package manifest sha256",
                  "earn numbers from the wrong process/build passing as packaged truth",
                  v_progression_evidence_bound),
        Validator("progression_earned_from_real_telemetry", PR, P.FILESYSTEM, S.BLOCKER,
                  "per-match apply-proofs: xp==recompute(events) under cap, level==level_for_xp(xp), chain-accumulation",
                  "fabricated or out-of-nowhere XP/level laundered as earned progression",
                  v_progression_earned_from_real_telemetry),
        Validator("anti_farm_cap_enforced", PR, P.FILESYSTEM, S.BLOCKER,
                  "recomputed grant vs per-match anti-farm cap (2000)",
                  "farming past the per-match cap by inflating event counts",
                  v_progression_anti_farm_cap_enforced),
        Validator("challenges_advance_from_events", PR, P.FILESYSTEM, S.BLOCKER,
                  "daily_kills challenge progress == min(kills, target)",
                  "challenge progress fabricated rather than advanced from real event counts",
                  v_progression_challenges_advance_from_events),
        Validator("progression_persists_across_relaunch", PR, P.FILESYSTEM, S.BLOCKER,
                  "two distinct pids; account_xp after relaunch == run1 + run2 granted; ledger grew",
                  "a 'persistence' claim over a profile that actually reset on relaunch",
                  v_progression_persists_across_relaunch),
        Validator("profile_schema_versioned", PR, P.FILESYSTEM, S.BLOCKER,
                  "persisted local.json carries current schema_version",
                  "an unversioned save that a future migration cannot safely upgrade",
                  v_progression_profile_schema_versioned),
        Validator("profile_migration_roundtrips", PR, P.FILESYSTEM, S.BLOCKER,
                  "v0 shape of the real saved profile migrates + validates",
                  "a migration path that silently drops or corrupts a legacy save",
                  v_progression_profile_migration_roundtrips),
        Validator("progression_queue_sync", PR, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim progression readiness without the lane registered",
                  v_progression_queue_sync),
    ]
    # PLAYER_INPUT_AND_UI_HYGIENE_V1 (Horizon 2, §B4/B7): batched static player-surface hygiene —
    # gameplay input parity, no dead declared actions, no HUD debug leaks, colorblind-safe palette.
    PH = "player_hygiene"
    reg += [
        Validator("player_hygiene_gameplay_input_parity", PH, P.STATIC, S.BLOCKER,
                  "every DefaultInput.ini ActionMapping bound on keyboard AND gamepad",
                  "a gameplay action a controller player can't perform (Slide/Dodge/etc keyboard-only)",
                  v_player_hygiene_gameplay_input_parity),
        Validator("player_hygiene_no_dead_action", PH, P.STATIC, S.BLOCKER,
                  "every declared ActionMapping is referenced in Source/",
                  "dead input declared in the ini but wired to nothing",
                  v_player_hygiene_no_dead_action),
        Validator("player_hygiene_ui_no_debug_leaks", PH, P.STATIC, S.BLOCKER,
                  "displayed HUD string literals across player-facing HUDs",
                  "a debug/placeholder string (TODO/FIXME/placeholder) shipped on a player HUD",
                  v_player_hygiene_ui_no_debug_leaks),
        Validator("player_hygiene_colorblind_palette", PH, P.STATIC, S.BLOCKER,
                  "deck semantic colors distinguishable under simulated deuteranopia",
                  "HUD state/team colors that collapse for colorblind players",
                  v_player_hygiene_colorblind_palette),
        # AXIS_INPUT_HYGIENE_V1: the ActionMapping gates above never saw AxisMappings (Move/Look) —
        # the load-bearing continuous controls. Extend the same hygiene to axes.
        Validator("player_hygiene_axis_parity", PH, P.STATIC, S.BLOCKER,
                  "every DefaultInput.ini AxisMapping bound on keyboard/mouse AND gamepad",
                  "a controller player can't move or look (Move/Look axis missing a gamepad stick)",
                  v_player_hygiene_axis_parity),
        Validator("player_hygiene_axis_bidirectional", PH, P.STATIC, S.BLOCKER,
                  "a discrete-key axis (WASD) offers both + and - directions",
                  "a dropped key leaves the player able to walk one direction only",
                  v_player_hygiene_axis_bidirectional),
        Validator("player_hygiene_no_dead_axis", PH, P.STATIC, S.BLOCKER,
                  "every declared AxisMapping name is BindAxis'd in Source/",
                  "a movement axis declared in the ini but wired to nothing",
                  v_player_hygiene_no_dead_axis),
        Validator("player_hygiene_reserved_keys", PH, P.STATIC, S.BLOCKER,
                  "no gameplay Action/Axis binds a reserved system key (Escape/console/F11)",
                  "a gameplay verb collides with pause/console/fullscreen and fights the engine",
                  v_player_hygiene_reserved_keys),
    ]
    # HUMAN_INPUT_MATRIX_V1 (Horizon 2, §B7): the command deck must be reachable on keyboard AND
    # gamepad, claim game input on launch, and show dual input hints (the deck-was-dead bug class).
    IM = "input_matrix"
    reg += [
        Validator("input_matrix_gamepad_parity", IM, P.STATIC, S.BLOCKER,
                  "every deck verb bound on both a keyboard and a gamepad key",
                  "a controller-only player hits a dead command deck",
                  v_input_matrix_gamepad_parity),
        Validator("input_matrix_game_input_claimed", IM, P.STATIC, S.BLOCKER,
                  "deck controller sets FInputModeGameOnly on BeginPlay",
                  "a windowed -game launch sits unfocused and eats every key",
                  v_input_matrix_game_input_claimed),
        Validator("input_matrix_dual_hints", IM, P.STATIC, S.BLOCKER,
                  "deck HUD shows keyboard + gamepad glyph hints",
                  "controller players get no on-screen guidance",
                  v_input_matrix_dual_hints),
    ]
    # FLAGSHIP_ARENA_ART_PASS_V1 (masterplan bundle 10, §B3): Arena4v4 greybox -> dressed flagship
    # (kit landmarks + wane materials + lighting rig + wane-energy identity), proven by a saved-map
    # dress proof + a per-station capture tour of the dressed map.
    FA = "flagship_arena"
    reg += [
        Validator("flagship_arena_dressed", FA, P.FILESYSTEM, S.BLOCKER,
                  "dress proof: kit landmarks + wane/trim materials over greybox, map saved",
                  "the flagship arena still ships as undressed greybox",
                  v_flagship_arena_dressed),
        Validator("flagship_arena_lighting_rig", FA, P.FILESYSTEM, S.BLOCKER,
                  "SkyAtmosphere + DirectionalLight + SkyLight present (SkyAtmosphere law)",
                  "an unlit / sky-warning arena",
                  v_flagship_arena_lighting_rig),
        Validator("flagship_arena_wane_landmarks", FA, P.FILESYSTEM, S.BLOCKER,
                  "wane-energy landmarks + emissive wane material (IP identity)",
                  "a generic arena with no WANE identity landmarks",
                  v_flagship_arena_wane_landmarks),
        Validator("flagship_arena_nav_collision", FA, P.FILESYSTEM, S.BLOCKER,
                  "PlayerStarts present (playable 4v4 spawns)",
                  "a dressed but unplayable arena",
                  v_flagship_arena_nav_collision),
        Validator("flagship_arena_capture_tour", FA, P.FILESYSTEM, S.BLOCKER,
                  "per-station stills of the dressed map: non-blank + distinct coverage",
                  "the dress claimed but never rendered / a single repeated frame",
                  v_flagship_arena_capture_tour),
    ]
    # SELF_METRICS_AND_QUEUE_DIRECTOR_V1 (masterplan bundle 9, §A2): the recursive loop measures +
    # schedules ITSELF — suite self-metrics, evidence-freshness radar, evidence-ranked next-action queue.
    SM = "self_metrics"
    reg += [
        Validator("self_metrics_present", SM, P.FILESYSTEM, S.BLOCKER,
                  "self_metrics.json exists + well-formed (source + measured sections)",
                  "a missing/malformed self-assessment artifact",
                  v_self_metrics_present),
        Validator("self_metrics_derived_from_suite", SM, P.FILESYSTEM, S.BLOCKER,
                  "suite/domains/probe_mix recomputed from the cited report",
                  "a fabricated self-grade the suite's own results contradict",
                  v_self_metrics_derived_from_suite),
        Validator("self_metrics_freshness_radar_covers_decaying_lanes", SM, P.FILESYSTEM, S.BLOCKER,
                  "every aged lane present in the radar with correct fresh/warn/stale status",
                  "a lane about to block hidden from the freshness radar",
                  v_self_metrics_freshness_radar_covers_decaying_lanes),
        Validator("self_metrics_queue_ranked_by_evidence", SM, P.FILESYSTEM, S.BLOCKER,
                  "operational queue deterministic + evidence-cited + broken->stale->warn order",
                  "the loop scheduling itself by fiction instead of evidence",
                  v_self_metrics_queue_ranked_by_evidence),
        Validator("self_metrics_no_operator_promotions", SM, P.STATIC, S.BLOCKER,
                  "self-metrics artifact writes no operator-only promotion state",
                  "the self-scheduling layer leaking past the PROMOTED_TO_REVIEW ceiling",
                  v_self_metrics_no_operator_promotions),
        Validator("self_metrics_queue_sync", SM, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim self-metrics without the director lane registered",
                  v_self_metrics_queue_sync),
    ]
    # UI_SETTINGS_AND_PERSISTENCE_V1 (masterplan bundle 8, §B4/B6): settings must persist across a
    # real relaunch and reach the engine via GameUserSettings — proven by a two-launch packaged proof.
    US = "ui_settings"
    reg += [
        Validator("ui_settings_result_fresh", US, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/ui_settings/ui_settings_result.json age",
                  "stale settings-persistence proof speaking for the current build",
                  v_ui_settings_result_fresh),
        Validator("ui_settings_evidence_bound", US, P.FILESYSTEM, S.BLOCKER,
                  "both proofs flag/pid-bound + exe-sha vs manifest + two distinct launch pids",
                  "a fabricated or single-process 'relaunch' passing as real persistence",
                  v_ui_settings_evidence_bound),
        Validator("ui_settings_persistence_roundtrip", US, P.FILESYSTEM, S.BLOCKER,
                  "write.intended settings == verify.loaded across relaunch (12 fields)",
                  "a changed setting silently not surviving a real relaunch",
                  v_ui_settings_persistence_roundtrip),
        Validator("ui_settings_gameusersettings_applied", US, P.FILESYSTEM, S.BLOCKER,
                  "GameUserSettings resolution/quality applied + persisted across relaunch",
                  "settings stored in the profile but never reaching the renderer",
                  v_ui_settings_gameusersettings_applied),
        Validator("ui_settings_coverage", US, P.FILESYSTEM, S.BLOCKER,
                  "known write block differs from MakeDefault on all 12 fields",
                  "one lucky default-valued field masking a non-persisting setting",
                  v_ui_settings_coverage),
        Validator("ui_settings_savereload_wired", US, P.STATIC, S.BLOCKER,
                  "UWanefallProfileSubsystem SaveProfile (ToJson->file) + GameUserSettings apply path",
                  "a 'persistence' lane over a subsystem that never actually writes",
                  v_ui_settings_savereload_wired),
        Validator("ui_settings_queue_sync", US, P.STATIC, S.BLOCKER,
                  "production manifest + director task",
                  "recursive queues can claim settings readiness without the lane registered",
                  v_ui_settings_queue_sync),
    ]
    # COMMAND_DECK_TRUTH_V1 (masterplan bundle 7, §B4): the packaged front-door command deck must
    # show real profile data or honest empty states — no rank/leaderboard/stat fiction, no dev jargon.
    CD = "command_deck"
    reg += [
        Validator("command_deck_no_ui_fiction", CD, P.STATIC, S.BLOCKER,
                  "WanefallLobbyHUD.cpp fiction/jargon/debug token scan",
                  "fabricated rank/leaderboard/stats or internal dev jargon shipped to players "
                  "(the 'melee-safe staging' leak class)",
                  v_command_deck_no_ui_fiction),
        Validator("command_deck_reads_real_profile", CD, P.STATIC, S.BLOCKER,
                  "command-deck panels bound to UWanefallProfileSubsystem / profile accessors",
                  "command deck renders literals instead of the real local profile",
                  v_command_deck_reads_real_profile),
        Validator("command_deck_honest_empty_states", CD, P.STATIC, S.BLOCKER,
                  "honest UNRANKED / NO LOCAL RECORDS / COMING SOON fallbacks present",
                  "empty data faked as populated instead of an honest coming-soon/unranked state",
                  v_command_deck_honest_empty_states),
        Validator("command_deck_profile_subsystem_real", CD, P.STATIC, S.BLOCKER,
                  "UWanefallProfileSubsystem is a real load-or-default GameInstanceSubsystem",
                  "the 'real data source' is a stub, not a genuine offline profile loader",
                  v_command_deck_profile_subsystem_real),
        Validator("deck_reads_earned_progression", CD, P.STATIC, S.BLOCKER,
                  "CHALLENGES panel bound to UWanefallProgressionSubsystem challenge book with live "
                  "Progress/Target + honest NO ACTIVE CHALLENGES empty state",
                  "deck fakes or omits earned challenges instead of reading the real progression subsystem",
                  v_deck_reads_earned_progression),
    ]
    AE = "autonomy_engine"
    reg += [
        Validator("autonomy_matrix_fresh", AE, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/autonomy/AUTONOMY_CAPABILITY_FINAL_REPORT_20260628.json",
                  "stale/missing recursive autonomy matrix hides the next repair target", v_autonomy_matrix_fresh),
        Validator("autonomy_matrix_covers_required_lanes", AE, P.STATIC, S.BLOCKER,
                  "autonomy capability matrix",
                  "autonomy queue ignores a required WANEFALL subsystem lane", v_autonomy_matrix_covers_required_lanes),
        Validator("autonomy_external_references_classified", AE, P.STATIC, S.BLOCKER,
                  "external reference catalog",
                  "reference extraction proceeds without license/adoption/dependency classification",
                  v_autonomy_external_references_classified),
        Validator("autonomy_queue_ranked_actions", AE, P.STATIC, S.BLOCKER,
                  "recursive_improvement_queue.json",
                  "recursive loop has no ranked next action or non-deterministic ranks", v_autonomy_queue_ranked_actions),
        Validator("autonomy_queue_actions_have_validation_and_rollback", AE, P.STATIC, S.BLOCKER,
                  "recursive queue candidates",
                  "autonomous candidate lacks validation, rollback, or review ceiling",
                  v_autonomy_queue_actions_have_validation_and_rollback),
        Validator("autonomy_no_operator_only_promotions", AE, P.STATIC, S.BLOCKER,
                  "autonomy reports and queue",
                  "autonomy layer leaks operator-only promotion states", v_autonomy_no_operator_only_promotions),
    ]
    UGB = "unreal_game_builder_engine"
    reg += [
        Validator("unreal_game_builder_fresh", UGB, P.FILESYSTEM, S.BLOCKER,
                  "artifacts/unreal_game_builder/UNREAL_GAME_BUILDER_FINAL_REPORT_20260629.json",
                  "stale/missing all-in-one Unreal builder proof hides current production blockers",
                  v_unreal_game_builder_fresh),
        Validator("unreal_game_builder_covers_required_lanes", UGB, P.STATIC, S.BLOCKER,
                  "unreal game-builder scorecard",
                  "builder ignores a major Unreal game-production lane",
                  v_unreal_game_builder_covers_required_lanes),
        Validator("unreal_game_builder_lane_validation_and_rollback", UGB, P.STATIC, S.BLOCKER,
                  "game-builder lanes and queue",
                  "autonomous builder action lacks validation, rollback, required artifacts, or Unreal touchpoints",
                  v_unreal_game_builder_lane_validation_and_rollback),
        Validator("unreal_game_builder_current_blockers_visible", UGB, P.STATIC, S.BLOCKER,
                  "current validation blockers",
                  "builder report hides active non-pass validation evidence",
                  v_unreal_game_builder_current_blockers_visible),
        Validator("unreal_game_builder_queue_prioritizes_blockers", UGB, P.STATIC, S.BLOCKER,
                  "recursive game-build queue",
                  "builder queue is empty, unranked, or prioritizes pass lanes while blockers remain",
                  v_unreal_game_builder_queue_prioritizes_blockers),
        Validator("unreal_game_builder_no_operator_only_promotions", UGB, P.STATIC, S.BLOCKER,
                  "game-builder report and queue",
                  "game-builder layer leaks operator-only promotion states",
                  v_unreal_game_builder_no_operator_only_promotions),
    ]
    # AUDIO_FOUNDATION_V1 (Horizon 2, masterplan §B5): audio from score-3 near-zero-gated to a
    # fail-closed foundation — bus/submix architecture, event-cue coverage, loudness/true-peak/
    # silence gates over real procedural SFX, provenance, and a packaged-mix silence-proof.
    AF = "audio_foundation"
    reg += [
        Validator("audio_event_cue_coverage", AF, P.STATIC, S.BLOCKER,
                  "every EWanefallCombatEventType maps to a cue (AudioCueFor) or is exempt-with-rationale",
                  "a combat event ships with no audio cue and no declared reason",
                  v_audio_event_cue_coverage),
        Validator("audio_cue_assets_resolvable", AF, P.FILESYSTEM, S.BLOCKER,
                  "every manifest cue resolves to a real WAV or a declared placeholder(target)",
                  "a cue is a bare string with no sound and no placeholder behind it",
                  v_audio_cue_assets_resolvable),
        Validator("audio_bus_architecture_declared", AF, P.FILESYSTEM, S.BLOCKER,
                  "bus manifest declares Master+Music+SFX+UI+Voice routing to Master with loudness targets",
                  "the audio bus/submix architecture is undeclared or malformed",
                  v_audio_bus_architecture_declared),
        Validator("audio_loudness_within_bounds", AF, P.FILESYSTEM, S.BLOCKER,
                  "every authored cue WAV within its bus target LUFS +/- tolerance",
                  "a shipped cue is far off its bus loudness target (mix is inconsistent)",
                  v_audio_loudness_within_bounds),
        Validator("audio_true_peak_ceiling", AF, P.FILESYSTEM, S.BLOCKER,
                  "every cue WAV true-peak <= its bus ceiling (default -1 dBTP)",
                  "a cue clips / inter-sample overs on the output bus",
                  v_audio_true_peak_ceiling),
        Validator("audio_no_silent_wavs", AF, P.FILESYSTEM, S.BLOCKER,
                  "no authored cue WAV is digital silence",
                  "an empty/silent WAV backs a cue (dead audio that reads as 'present')",
                  v_audio_no_silent_wavs),
        Validator("audio_sfx_provenance", AF, P.FILESYSTEM, S.BLOCKER,
                  "every real cue WAV carries a ledgered license (self-authored/CC0/operator) + matching sha256",
                  "un-provenanced or tampered audio backs a cue",
                  v_audio_sfx_provenance),
        Validator("audio_cue_playback_wired", AF, P.STATIC, S.BLOCKER,
                  "cue subsystem PlaySound + game-state dispatches AudioCueFor -> PlayCue per event",
                  "combat cues are logged but never played (the mix stays silent) — AUDIO_RUNTIME_V1",
                  v_audio_cue_playback_wired),
        Validator("audio_bus_submix_assets_present", AF, P.UE_PYTHON, S.BLOCKER,
                  "UE USoundSubmix assets exist matching the bus manifest",
                  "the declared buses have no real UE submix assets (architecture is paper-only)",
                  v_audio_bus_submix_assets_present, ["ue"]),
        Validator("audio_packaged_mix_has_signal", AF, P.PERCEPTION, S.BLOCKER,
                  "packaged combat segment has audio energy above floor and above the menu baseline",
                  "the shipped game plays a silent (or menu-only) mix in combat",
                  v_audio_packaged_mix_has_signal, ["ue"]),
    ]
    # MODE_CONTRACT_V1 (masterplan §B6): every registered mode's rule-machine contract (win/lose/
    # score/timer paths) headlessly simulated via FWanefallModeSimHarness every run, recomputed from
    # raw fields, never the reported bPass. Fully additive: no cook, no map, no foreground UE.
    MC = "mode_contract"
    reg += [
        Validator("mode_contract_proof_present", MC, P.STATIC, S.BLOCKER,
                  "artifacts/mode_contract/mode_sim_proof.json (+ .done marker) via WanefallModeSimProof commandlet",
                  "stale/missing/unparseable mode-sim proof silently passing downstream mode gates",
                  v_mode_contract_proof_present),
        Validator("mode_contract_arena_suite", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json arena.* modes",
                  "an arena mode (13 sims) never resolves a winner or leaves a dirty reset",
                  v_mode_contract_arena_suite),
        Validator("mode_contract_large_suite", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json br.waneroyale + extraction.* modes",
                  "battle royale / extraction success-kia-timeout outcomes misresolve or fail to reset",
                  v_mode_contract_large_suite),
        Validator("mode_contract_arcade_suite", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json arcade.* modes",
                  "race/brawl/rolling arcade modes never resolve or leave a dirty reset",
                  v_mode_contract_arcade_suite),
        Validator("mode_contract_ui_foundation", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json ui.foundation raw boolean fields",
                  "UI model self-check reports UI_MODEL_VALID while its own raw fields disagree",
                  v_mode_contract_ui_foundation),
        Validator("mode_contract_wanetrial_second_chance", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json trial.wanetrial",
                  "WaneTrial down->finish loop skips or double-counts the one second-chance window",
                  v_mode_contract_wanetrial_second_chance),
        Validator("mode_contract_practice_range", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json practice.range",
                  "endless PracticeRange falsely resolves a winner or a timeout",
                  v_mode_contract_practice_range),
        Validator("mode_contract_demo_modes_covered", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json arena.a4v4_tdm + trial.wanetrial + practice.range",
                  "the three demo-definition-of-done modes (TDM/WaneTrial/PracticeRange) not all green",
                  v_mode_contract_demo_modes_covered),
        Validator("mode_contract_recompute", MC, P.STATIC, S.BLOCKER,
                  "mode_sim_proof.json every mode's reported bPass vs recomputed contract",
                  "a mode's self-reported pass is fabricated/stale relative to its own raw fields",
                  v_mode_contract_recompute),
    ]
    return reg


REGISTRY = build_registry()
