"""Active roster/quarantine proof for WANEFALL characters."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Artifact, BlockedError, ProductionPipeline, Verdict
from .character_roster import (
    ROOT,
    active_humanoid_characters,
    active_mech_characters,
    is_quarantined_character,
    load_roster_policy,
    quarantine_record,
    roster_policy_summary,
)


PROJECT = Path(r"C:\Users\developer\Documents\Unreal Projects\WanefallGreybox")
RESULT_DIR = ROOT / "artifacts" / "character_roster_policy"
RESULT_PATH = RESULT_DIR / "character_roster_policy_report.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _rel_exists(root: Path, rel: str | None) -> str | None:
    if not rel:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = root / path
    return str(path) if path.exists() else None


def _mech_key_from_asset(asset_name: str) -> str:
    return asset_name.replace("SM_Char_Mech_", "mech_").lower()


def _mech_evidence(root: Path, project: Path, mech: dict[str, Any]) -> dict[str, Any]:
    asset = str(mech.get("asset_name") or "")
    key = str(mech.get("character_id") or _mech_key_from_asset(asset))
    source = _rel_exists(root, mech.get("source_glb")) or _rel_exists(root, f"artifacts/new_out/{key}.glb")
    staged = _rel_exists(root, mech.get("staged_glb")) or _rel_exists(root, f"artifacts/ue_staging_new/{asset}.glb")
    render = _rel_exists(root, mech.get("render_png")) or _rel_exists(root, f"artifacts/ingame_new/{asset}.png")
    imported = project / "Content" / "Wanefall" / "Dimwit" / "Characters" / asset / "StaticMeshes" / f"{asset}.uasset"
    return {
        "key": key,
        "asset_name": asset,
        "source_glb": source,
        "staged_glb": staged,
        "imported_uasset": str(imported) if imported.exists() else None,
        "render_png": render,
    }


def _director_tasks(root: Path) -> list[dict[str, Any]]:
    data = _read_json(root / "config" / "director_tasks.json")
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    return [task for task in tasks if isinstance(task, dict)]


def audit_character_roster_policy(root: Path = ROOT, project: Path = PROJECT) -> dict[str, Any]:
    policy = load_roster_policy(root)
    summary = roster_policy_summary(root)
    tasks = _director_tasks(root)
    quarantined_tasks = []
    for task in tasks:
        asset_id = str(task.get("asset_id") or task.get("name") or "")
        if asset_id and is_quarantined_character(asset_id, root):
            quarantined_tasks.append(task)
    qu_records = []
    for qid, item in policy.get("quarantined_humanoids", {}).items():
        rec = dict(item) if isinstance(item, dict) else {"reason": str(item)}
        report_rec = {
            "quarantine_id": rec.get("key") or qid or "retired_prototype",
            "state": rec.get("state"),
            "reason": rec.get("reason"),
            "replacement_required": rec.get("replacement_required"),
            "capacity_rebalanced_to_mechs": rec.get("capacity_rebalanced_to_mechs"),
        }
        report_rec["evidence_existing"] = [
            path for path in (_rel_exists(root, evidence) for evidence in rec.get("evidence") or [])
            if path
        ]
        qu_records.append(report_rec)
    return {
        "schema_version": 1,
        "summary": summary,
        "active_humanoids": active_humanoid_characters(root),
        "quarantined_humanoids": qu_records,
        "mech_characters": [_mech_evidence(root, project, mech) for mech in active_mech_characters(root)],
        "director": {
            "task_count": len(tasks),
            "quarantined_character_tasks": quarantined_tasks,
        },
    }


def validate_character_roster_policy(report: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    summary = report.get("summary") or {}
    if summary.get("active_humanoid_count") != summary.get("active_humanoid_target"):
        issues.append(
            f"active humanoid count {summary.get('active_humanoid_count')} != target {summary.get('active_humanoid_target')}"
        )
    if summary.get("active_mech_count") != summary.get("active_mech_target"):
        issues.append(f"active mech count {summary.get('active_mech_count')} != target {summary.get('active_mech_target')}")
    if not summary.get("quarantined_humanoid_count"):
        issues.append("no quarantined humanoid record present for retired prototype")
    for rec in report.get("quarantined_humanoids") or []:
        if not rec.get("evidence_existing"):
            issues.append(f"quarantine evidence missing for {rec.get('quarantine_id') or 'retired_prototype'}")
    quarantined_tasks = ((report.get("director") or {}).get("quarantined_character_tasks") or [])
    if quarantined_tasks:
        issues.append(f"quarantined character task still scheduled: {quarantined_tasks[:3]}")
    for mech in report.get("mech_characters") or []:
        missing = [field for field in ("source_glb", "staged_glb", "imported_uasset", "render_png") if not mech.get(field)]
        if missing:
            issues.append(f"{mech.get('asset_name')} missing mech evidence: {', '.join(missing)}")
    return {"passed": not issues, "issues": issues}


def write_character_roster_policy_report(root: Path = ROOT, project: Path = PROJECT,
                                         output_path: Path = RESULT_PATH) -> dict[str, Any]:
    report = audit_character_roster_policy(root, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class CharacterRosterPolicyPipeline(ProductionPipeline):
    name = "character_roster_policy"
    kind = "character_roster_policy_report"

    def __init__(self, threshold: float = 1.0, max_repairs: int = 0, ledger_path: Path | None = None):
        super().__init__(threshold=threshold, max_repairs=max_repairs, ledger_path=ledger_path)

    def plan(self, task: dict) -> dict:
        root = ROOT
        project = PROJECT
        if not (root / "config" / "character_roster.json").exists():
            raise BlockedError("config/character_roster.json missing")
        return {"root": str(root), "project": str(project), "asset_id": task.get("asset_id") or "active_roster"}

    def execute(self, plan: dict) -> Artifact:
        report = write_character_roster_policy_report(Path(plan["root"]), Path(plan["project"]), RESULT_PATH)
        return Artifact(
            asset_id=str(plan.get("asset_id") or "active_roster"),
            kind=self.kind,
            data={"report_path": str(RESULT_PATH), "summary": report.get("summary"), "report": report},
            provenance={"source": "config/character_roster.json + on-disk character/mech evidence",
                        "license": "project-local generated roster policy evidence"},
        )

    def qa(self, artifact: Artifact, plan: dict) -> Verdict:
        result = validate_character_roster_policy(artifact.data.get("report") or {})
        return Verdict(
            score=1.0 if result["passed"] else 0.0,
            passed=result["passed"],
            hard_fail=False,
            issues=result["issues"],
            evidence=[artifact.data.get("report_path")] if artifact.data.get("report_path") else [],
            detail=artifact.data.get("summary") or {},
        )

    def repair(self, artifact: Artifact, verdict: Verdict, attempt: int, plan: dict) -> Artifact:
        return self.execute(plan)
