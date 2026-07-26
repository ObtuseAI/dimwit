"""WANEFALL character source sync contract.

This ties the website-generated Hi3D/Hitem3D meshes to the downstream DCC/game
lanes without pretending one successful file means the whole character pipeline is
healthy:

    Hi3D GLB -> Blender anatomy review -> retopo/rig FBX -> MetaHuman attempt -> Unreal import

The audit is intentionally file/evidence based. It does not fabricate Blender,
MetaHuman, or Unreal proof; missing evidence blocks and bad evidence fails.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Artifact, BlockedError, ProductionPipeline, Verdict
from .character_roster import active_humanoid_characters, quarantine_record, roster_policy_summary
from .metahuman_utilization import EXPECTED_CHARACTERS, _source_linked_attempt_outputs


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
RESULT_DIR = ROOT / "artifacts" / "character_source_sync"
RESULT_PATH = RESULT_DIR / "character_source_sync_report.json"
BLENDER_SCRIPT = ROOT / "blender_scripts" / "character_anatomy_review.py"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _stage(state: str, *, path: str | None = None, issues: list[str] | None = None,
           detail: dict[str, Any] | None = None, command: str | None = None) -> dict[str, Any]:
    out = {"state": state}
    if path:
        out["path"] = path
    if issues:
        out["issues"] = issues
    if detail:
        out["detail"] = detail
    if command:
        out["command"] = command
    return out


def _scale_dirty(scale: list[Any] | None) -> bool:
    if not isinstance(scale, list) or len(scale) != 3:
        return False
    vals = []
    for item in scale:
        try:
            vals.append(abs(float(item)))
        except Exception:
            return False
    return any(v < 0.1 or v > 10.0 for v in vals)


def evaluate_blender_anatomy_review(review: dict[str, Any], *, stage: str) -> dict[str, Any]:
    """Judge a Blender anatomy review packet.

    Pixel/contact-sheet review catches subjective art quality; this catches
    deterministic pipeline faults: fragmented blockout geometry and dirty FBX rig
    transforms that Unreal rebakes into invalid bind poses.
    """
    issues: list[str] = []
    if not review or review.get("ok") is not True:
        return {"passed": False, "score": 0.0, "issues": ["Blender anatomy review missing or not ok"]}
    om = review.get("object_metrics") if isinstance(review.get("object_metrics"), dict) else {}
    am = review.get("anatomy_metrics") if isinstance(review.get("anatomy_metrics"), dict) else {}
    cm = review.get("component_metrics") if isinstance(review.get("component_metrics"), dict) else {}

    if int(om.get("mesh_count") or 0) < 1:
        issues.append("no mesh object in Blender review")
    if int(om.get("face_count") or 0) < 500:
        issues.append("mesh face_count below character-review floor")

    dims = am.get("dimensions") if isinstance(am.get("dimensions"), list) else []
    if len(dims) == 3:
        try:
            sorted_dims = sorted(float(v) for v in dims)
            slenderness = sorted_dims[-1] / max(sorted_dims[-2], 1e-6)
            if slenderness < 1.2:
                issues.append(f"humanoid proportions unreadable: slenderness {slenderness:.2f} < 1.20")
            if slenderness > 6.0:
                issues.append(f"humanoid proportions too needle-like: slenderness {slenderness:.2f} > 6.00")
        except Exception:
            issues.append("dimensions unreadable")

    if cm.get("measured") is True:
        components = int(cm.get("component_count") or 0)
        largest = float(cm.get("largest_component_face_fraction") or 0.0)
        if stage in {"retopo", "rig"} and components > 1:
            issues.append(
                f"fragmented {stage} mesh before Unreal export: {components} disconnected components"
            )
        elif components > 12 and largest < 0.65:
            issues.append(
                f"fragmented/blockout character mesh: {components} components, largest face fraction {largest:.3f}"
            )
        elif components > 48:
            issues.append(f"fragmented character mesh: {components} disconnected components")

    if stage == "rig":
        if int(om.get("armature_count") or 0) < 1:
            issues.append("rig review contains no armature")
        dirty = []
        for obj in om.get("objects") or []:
            if isinstance(obj, dict) and _scale_dirty(obj.get("scale")):
                dirty.append(f"mesh {obj.get('name')} scale={obj.get('scale')}")
        for arm in om.get("armatures") or []:
            if isinstance(arm, dict) and _scale_dirty(arm.get("scale")):
                dirty.append(f"armature {arm.get('name')} scale={arm.get('scale')}")
        if dirty:
            issues.append("dirty rig transform before Unreal import: " + "; ".join(dirty[:4]))

    score = 0.0 if issues else 1.0
    return {
        "passed": not issues,
        "score": score,
        "issues": issues,
        "component_metrics": cm,
        "object_summary": {
            "mesh_count": om.get("mesh_count"),
            "armature_count": om.get("armature_count"),
            "vertex_count": om.get("vertex_count"),
            "face_count": om.get("face_count"),
        },
    }


def _review_command(mesh_path: Path, label: str, root: Path) -> str:
    out_dir = root / "artifacts" / "blender_anatomy_review"
    return (
        f'"{BLENDER_EXE}" --background --python "{BLENDER_SCRIPT}" -- '
        f'in="{mesh_path}" out="{out_dir}" label="{label}"'
    )


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _find_review(root: Path, labels: list[str]) -> Path | None:
    base = root / "artifacts" / "blender_anatomy_review"
    for label in labels:
        path = base / f"{label}_review.json"
        if path.exists():
            return path
    return None


def _char_records(root: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(root / "artifacts" / "char_fidelity_result.json")
    records = data.get("records") if isinstance(data.get("records"), list) else []
    out = {}
    for rec in records:
        if isinstance(rec, dict) and rec.get("asset"):
            out[str(rec["asset"]).lower()] = rec
    return out


def _metahuman_by_key(root: Path) -> dict[str, list[dict[str, Any]]]:
    accepted = _source_linked_attempt_outputs(root).get("accepted") or []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in accepted:
        key = str(item.get("source_character") or item.get("asset_id") or "").lower()
        if key:
            by_key.setdefault(key, []).append(item)
    return by_key


def _active_runtime_deformation_defect(root: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    path = root / "artifacts" / "validation" / "character_deformation_review.json"
    data = _read_json(path)
    if not data:
        return None
    state = str(data.get("state") or "").upper()
    if state in {"RESOLVED", "CLEARED", "OPERATOR_CLEARED"}:
        return None
    issues = data.get("issues") if isinstance(data.get("issues"), list) else [data.get("issue")]
    issues = [str(issue) for issue in issues if issue]
    if not issues:
        return None
    asset = str(data.get("asset") or data.get("subject") or "").lower()
    key = str(item.get("key") or "").lower()
    asset_name = str(item.get("asset_name") or "").lower()
    if key and key in asset or asset_name and asset_name in asset:
        return {"path": str(path), "state": data.get("state"), "asset": data.get("asset"), "issues": issues}
    return None


def _runtime_deformation_clearance_stage(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    qrec = quarantine_record(item.get("key") or item.get("asset_name"), root)
    if qrec:
        return _stage("QUARANTINED", issues=[str(qrec.get("reason") or "character retired from active roster")], detail=qrec)
    defect = _active_runtime_deformation_defect(root, item)
    if defect:
        return _stage("FAIL", path=defect["path"], issues=defect["issues"], detail=defect)
    return _stage("PASS")


def _status_for_review(path: Path | None, stage: str) -> dict[str, Any]:
    if not path:
        return _stage("BLOCKED", issues=[f"missing Blender {stage} anatomy review"])
    verdict = evaluate_blender_anatomy_review(_read_json(path), stage=stage)
    if verdict["passed"]:
        return _stage("PASS", path=str(path), detail=verdict)
    return _stage("FAIL", path=str(path), issues=verdict["issues"], detail=verdict)


def _next_action(stages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    order = [
        "hi3d_source",
        "blender_source_review",
        "retopo_fbx",
        "blender_retopo_review",
        "rig_fbx",
        "blender_rig_review",
        "unreal_import",
        "runtime_deformation_clearance",
        "metahuman_output",
    ]
    for key in order:
        stage = stages[key]
        if stage["state"] == "PASS":
            continue
        if stage.get("command"):
            return {"stage": key, "action": "run_command", "command": stage["command"], "reason": stage.get("issues", [])}
        if key == "blender_source_review":
            return {"stage": key, "action": "regenerate_or_repair_hi3d_source", "reason": stage.get("issues", [])}
        if key == "blender_retopo_review":
            return {"stage": key, "action": "repair_retopo_in_blender", "reason": stage.get("issues", [])}
        if key == "blender_rig_review":
            return {"stage": key, "action": "fix_rig_export_bind_transforms_before_unreal", "reason": stage.get("issues", [])}
        if key == "metahuman_output":
            return {"stage": key, "action": "run_metahuman_output_attempt", "command": "python scripts/pipeline/run_pipeline.py metahuman_output_attempt <asset_id>", "reason": stage.get("issues", [])}
        if key == "unreal_import":
            return {"stage": key, "action": "run_character_fidelity_import", "command": "python scripts/pipeline/run_pipeline.py character_fidelity <asset_id>", "reason": stage.get("issues", [])}
        if key == "runtime_deformation_clearance":
            return {"stage": key, "action": "repair_runtime_deformation_in_unreal", "reason": stage.get("issues", [])}
        return {"stage": key, "action": "satisfy_missing_evidence", "reason": stage.get("issues", [])}
    return {"stage": "complete", "action": "ready_for_operator_review"}


def audit_character_source_sync(root: Path = ROOT, project: Path = PROJECT,
                                characters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    chars = list(characters) if characters is not None else active_humanoid_characters(root)
    records = _char_records(root)
    mh_by_key = _metahuman_by_key(root)
    rows = []
    for item in chars:
        key = str(item["key"])
        token = str(item["asset_id"])
        source_stem = str(item["source_stem"])
        asset_name = str(item["asset_name"])
        art = root / "artifacts"
        source = _first_existing([art / f"{source_stem}.glb", art / "char_backup" / f"{source_stem}.glb"])
        retopo = art / "handcraft" / token / f"{token}_retopo.fbx"
        rig = _first_existing([art / "rig" / f"{token}_handcrafted_rig.fbx", art / "rig" / f"{token}_rigged.fbx"])
        imported = project / "Content" / "Wanefall" / "Dimwit" / "Characters" / asset_name / "StaticMeshes" / f"{asset_name}.uasset"

        source_review = _find_review(root, [source_stem, f"{key}_source_hi3d_glb", f"{source_stem}_glb"])
        retopo_review = _find_review(root, [f"{token}_retopo", f"{key}_scratch_retopo_fbx"])
        rig_review = _find_review(root, [f"{token}_handcrafted_rig", f"{key}_handcrafted_rig_fbx", f"{token}_rigged", f"{key}_old_rigged_fbx"])

        rec = records.get(asset_name.lower()) or records.get(token.lower()) or {}
        qrec = quarantine_record(key, root) or quarantine_record(asset_name, root)
        if qrec:
            stages = {
                "active_roster": _stage(
                    "QUARANTINED",
                    issues=[str(qrec.get("reason") or "character retired from active roster")],
                    detail=qrec,
                )
            }
            rows.append({
                "key": key,
                "asset_name": asset_name,
                "source_provider": "Hi3D/Hitem3D",
                "active_state": str(qrec.get("state") or "QUARANTINED"),
                "excluded_from_active_ready": True,
                "sync_ready": False,
                "ready_for_metahuman_attempt": False,
                "ready_for_unreal_runtime": False,
                "stages": stages,
                "next_action": {
                    "stage": "active_roster",
                    "action": "retired_no_repair_loop",
                    "reason": stages["active_roster"].get("issues", []),
                    "next_lane": "environments_maps_assets",
                },
            })
            continue
        stages: dict[str, dict[str, Any]] = {
            "hi3d_source": _stage("PASS", path=str(source)) if source else _stage("BLOCKED", issues=[f"missing Hi3D source GLB {source_stem}.glb"]),
            "blender_source_review": _status_for_review(source_review, "source"),
            "retopo_fbx": _stage("PASS", path=str(retopo)) if retopo.exists() else _stage("BLOCKED", issues=[f"missing retopo FBX {retopo}"]),
            "blender_retopo_review": _status_for_review(retopo_review, "retopo"),
            "rig_fbx": _stage("PASS", path=str(rig)) if rig else _stage("BLOCKED", issues=[f"missing rig FBX for {token}"]),
            "blender_rig_review": _status_for_review(rig_review, "rig"),
            "metahuman_output": _stage("PASS", detail={"attempts": mh_by_key.get(key.lower(), [])}) if mh_by_key.get(key.lower()) else _stage("BLOCKED", issues=[f"missing source-linked MetaHuman output for {key}"]),
            "unreal_import": _stage("PASS", path=str(imported), detail={"char_fidelity_record": bool(rec and rec.get("ok") and rec.get("nanite_enabled"))}) if imported.exists() and rec.get("ok") and rec.get("nanite_enabled") else _stage("BLOCKED", issues=[f"missing validated Unreal Nanite import for {asset_name}"]),
            "runtime_deformation_clearance": _runtime_deformation_clearance_stage(root, item),
        }
        if source and stages["blender_source_review"]["state"] == "BLOCKED":
            stages["blender_source_review"]["command"] = _review_command(source, source_stem, root)
        if retopo.exists() and stages["blender_retopo_review"]["state"] == "BLOCKED":
            stages["blender_retopo_review"]["command"] = _review_command(retopo, f"{token}_retopo", root)
        if rig and stages["blender_rig_review"]["state"] == "BLOCKED":
            stages["blender_rig_review"]["command"] = _review_command(rig, f"{token}_handcrafted_rig", root)

        sync_ready = all(stage["state"] == "PASS" for stage in stages.values())
        rows.append({
            "key": key,
            "asset_name": asset_name,
            "source_provider": "Hi3D/Hitem3D",
            "active_state": "ACTIVE",
            "excluded_from_active_ready": False,
            "sync_ready": sync_ready,
            "ready_for_metahuman_attempt": all(stages[name]["state"] == "PASS" for name in (
                "hi3d_source", "blender_source_review", "retopo_fbx", "blender_retopo_review"
            )),
            "ready_for_unreal_runtime": all(stages[name]["state"] == "PASS" for name in (
                "hi3d_source", "blender_source_review", "retopo_fbx", "blender_retopo_review",
                "rig_fbx", "blender_rig_review", "unreal_import", "runtime_deformation_clearance"
            )),
            "stages": stages,
            "next_action": _next_action(stages),
        })

    roster_summary = roster_policy_summary(root)
    summary = {
        "expected_character_count": len(rows),
        "sync_ready_count": sum(1 for row in rows if row["sync_ready"]),
        "ready_for_metahuman_attempt_count": sum(1 for row in rows if row["ready_for_metahuman_attempt"]),
        "ready_for_unreal_runtime_count": sum(1 for row in rows if row["ready_for_unreal_runtime"]),
        "active_humanoid_target": roster_summary.get("active_humanoid_target"),
        "active_humanoid_count": roster_summary.get("active_humanoid_count"),
        "quarantined_humanoid_count": roster_summary.get("quarantined_humanoid_count"),
        "active_mech_count": roster_summary.get("active_mech_count"),
        "active_mech_target": roster_summary.get("active_mech_target"),
        "next_lane": roster_summary.get("next_lane"),
    }
    return {"schema_version": 1, "summary": summary, "characters": rows}


def write_character_source_sync_report(root: Path = ROOT, project: Path = PROJECT,
                                       output_path: Path = RESULT_PATH) -> dict[str, Any]:
    report = audit_character_source_sync(root, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class CharacterSourceSyncPipeline(ProductionPipeline):
    name = "character_source_sync"
    kind = "character_source_sync_report"

    def plan(self, task: dict) -> dict:
        asset_id = str(task.get("asset_id") or "all").lower()
        if asset_id in {"all", "active", "roster"}:
            selected = active_humanoid_characters(ROOT)
        elif asset_id in {"catalog", "all_catalog", "source_catalog"}:
            selected = EXPECTED_CHARACTERS
        else:
            selected = [item for item in EXPECTED_CHARACTERS if item["key"].lower() == asset_id or str(item["asset_name"]).lower() == asset_id]
            if not selected:
                raise BlockedError(f"unknown character '{asset_id}'")
        return {"asset_id": asset_id, "characters": selected}

    def execute(self, plan: dict) -> Artifact:
        report = audit_character_source_sync(ROOT, PROJECT, characters=plan["characters"])
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULT_DIR / f"character_source_sync_{plan['asset_id']}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        RESULT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return Artifact(
            asset_id=plan["asset_id"],
            kind=self.kind,
            data={"report_path": str(out), "summary": report["summary"], "characters": report["characters"]},
            provenance={"source": "Hi3D/Hitem3D + Blender review + MetaHuman output + Unreal import evidence",
                        "license": "Hi3D Essential plan plus project-local generated evidence"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        report = {"summary": artifact.data.get("summary") or {}, "characters": artifact.data.get("characters") or []}
        issues = []
        evidence = [artifact.data.get("report_path")] if artifact.data.get("report_path") else []
        for row in report["characters"]:
            if not row.get("sync_ready"):
                action = row.get("next_action") or {}
                issues.append(f"{row.get('key')}: {action.get('stage')} -> {action.get('action')}")
        passed = not issues
        return Verdict(
            score=1.0 if passed else 0.0,
            passed=passed,
            hard_fail=False,
            issues=issues,
            evidence=[item for item in evidence if item],
            detail=report["summary"],
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        # This is an orchestration/evidence sync lane. Repairs require running the next_action commands,
        # not inventing missing proof inside the audit.
        return self.execute(plan)
