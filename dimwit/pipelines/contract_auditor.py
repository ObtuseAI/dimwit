"""Offline contract auditor for every registered Dimwit production pipeline."""
from __future__ import annotations

import ast
import importlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dimwit.pipelines.base import OPERATOR_ONLY, ProductionPipeline


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "pipeline_contracts"
RESULT_PATH = ARTIFACT_DIR / "pipeline_contract_audit.json"
OPERATOR_ONLY_STATES = set(OPERATOR_ONLY)
HOOKS = ("plan", "execute", "qa", "repair")
TASK_FIELDS = ("pipeline", "asset_id", "priority", "cost", "expected_value")
MAX_REPAIRS_LIMIT = 10
MAX_AUDIT_AGE_SECONDS = 6 * 60 * 60


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"{path}: {exc}"}
    return data if isinstance(data, dict) else {"_error": f"{path}: root is not an object"}


def _resolve_class(target: str) -> type:
    module_name, class_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    if not isinstance(cls, type):
        raise TypeError(f"{target} did not resolve to a class")
    return cls


def _source_path_for_class(cls: type) -> str | None:
    module = importlib.import_module(cls.__module__)
    path = getattr(module, "__file__", None)
    return str(Path(path)) if path else None


def audit_pipeline_contract(name: str, target: str, root: Path) -> dict[str, Any]:
    issues: list[str] = []
    detail: dict[str, Any] = {"target": target}
    try:
        cls = _resolve_class(target)
        detail["class"] = f"{cls.__module__}:{cls.__name__}"
        detail["source"] = _source_path_for_class(cls)
        if not issubclass(cls, ProductionPipeline):
            issues.append("class is not a ProductionPipeline subclass")
            return {"name": name, "passed": False, "issues": issues, "detail": detail}

        pipe = cls()
        detail["declared_name"] = getattr(pipe, "name", None)
        detail["kind"] = getattr(pipe, "kind", None)
        detail["threshold"] = getattr(pipe, "threshold", None)
        detail["max_repairs"] = getattr(pipe, "max_repairs", None)

        if pipe.name != name:
            issues.append(f"class name {pipe.name!r} does not match registry key {name!r}")
        if not isinstance(pipe.kind, str) or not pipe.kind.strip() or pipe.kind == "artifact":
            issues.append(f"pipeline kind is not specific: {pipe.kind!r}")
        if not isinstance(pipe.threshold, (int, float)) or not 0.0 <= float(pipe.threshold) <= 1.0:
            issues.append(f"threshold out of range 0..1: {pipe.threshold!r}")
        if not isinstance(pipe.max_repairs, int) or pipe.max_repairs < 0 or pipe.max_repairs > MAX_REPAIRS_LIMIT:
            issues.append(f"max_repairs must be 0..{MAX_REPAIRS_LIMIT}: {pipe.max_repairs!r}")

        missing_hooks = [hook for hook in HOOKS if not callable(getattr(pipe, hook, None))]
        inherited_hooks = [hook for hook in HOOKS if hook not in cls.__dict__]
        if missing_hooks:
            issues.append(f"missing hook(s): {missing_hooks}")
        if inherited_hooks:
            issues.append(f"hook(s) inherited without concrete implementation: {inherited_hooks}")

        chain = pipe.ledger.consistency_check()
        detail["ledger"] = chain
        if not chain.get("schema_ok", False):
            issues.append("ledger schema check failed")
        if not chain.get("chain_ok", False):
            issues.append("ledger hash-chain check failed")
    except Exception as exc:
        issues.append(f"contract inspection failed: {type(exc).__name__}: {exc}")

    return {"name": name, "passed": not issues, "issues": issues, "detail": detail}


def _manifest_parity(registry: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("_missing") or manifest.get("_error"):
        return {
            "passed": False,
            "issues": [manifest.get("_missing") or manifest.get("_error")],
            "missing_from_manifest": sorted(registry),
            "extra_in_manifest": [],
        }
    manifest_pipelines = manifest.get("pipelines")
    if not isinstance(manifest_pipelines, dict):
        return {
            "passed": False,
            "issues": ["production manifest has no pipelines object"],
            "missing_from_manifest": sorted(registry),
            "extra_in_manifest": [],
        }
    manifest_names = set(manifest_pipelines)
    registry_names = set(registry)
    missing = sorted(registry_names - manifest_names)
    extra = sorted(manifest_names - registry_names)
    issues = []
    if missing:
        issues.append(f"registered pipeline(s) missing from manifest: {missing}")
    if extra:
        issues.append(f"manifest pipeline(s) not registered: {extra}")
    return {
        "passed": not issues,
        "issues": issues,
        "missing_from_manifest": missing,
        "extra_in_manifest": extra,
    }


def _director_task_contract(registry: dict[str, str], director_tasks: dict[str, Any]) -> dict[str, Any]:
    if director_tasks.get("_missing") or director_tasks.get("_error"):
        return {
            "passed": False,
            "issues": [director_tasks.get("_missing") or director_tasks.get("_error")],
            "unknown_pipelines": [],
            "tasks_missing_fields": [],
        }
    tasks = director_tasks.get("tasks")
    if not isinstance(tasks, list):
        return {
            "passed": False,
            "issues": ["director tasks config has no tasks list"],
            "unknown_pipelines": [],
            "tasks_missing_fields": [],
        }
    unknown: list[str] = []
    missing_fields: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            missing_fields.append({"index": index, "missing": list(TASK_FIELDS)})
            continue
        pipeline = task.get("pipeline")
        if pipeline not in registry:
            unknown.append(str(pipeline))
        missing = [field for field in TASK_FIELDS if field not in task]
        if missing:
            missing_fields.append({"index": index, "pipeline": pipeline, "missing": missing})
    issues = []
    if unknown:
        issues.append(f"director task(s) reference unknown pipelines: {sorted(set(unknown))}")
    if missing_fields:
        issues.append(f"director task(s) missing required fields: {missing_fields}")
    return {
        "passed": not issues,
        "issues": issues,
        "unknown_pipelines": sorted(set(unknown)),
        "tasks_missing_fields": missing_fields,
        "task_count": len(tasks),
    }


def _operator_state_from_node(node: ast.AST, states: set[str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in states:
        return node.value
    return None


def _target_names(targets: list[ast.expr]) -> set[str]:
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


class _OperatorOnlyWriteVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, states: set[str]):
        self.path = path
        self.states = states
        self.findings: list[dict[str, Any]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        target_names = _target_names(list(node.targets))
        self._inspect_assignment(node, target_names, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target_names = _target_names([node.target])
        if node.value is not None:
            self._inspect_assignment(node, target_names, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            self._inspect_state_dict(node, arg, "call")
        self.generic_visit(node)

    def _record(self, node: ast.AST, state: str, context: str) -> None:
        self.findings.append({
            "path": str(self.path),
            "line": int(getattr(node, "lineno", 0)),
            "state": state,
            "context": context,
        })

    def _inspect_assignment(self, node: ast.AST, target_names: set[str], value: ast.AST) -> None:
        if target_names.intersection({"OPERATOR_ONLY", "OPERATOR_ONLY_STATES"}):
            return
        state = _operator_state_from_node(value, self.states)
        if state is not None:
            if state not in target_names:
                self._record(node, state, "assignment")
        self._inspect_state_dict(node, value, "assignment")

    def _inspect_state_dict(self, node: ast.AST, value: ast.AST, context: str) -> None:
        if not isinstance(value, ast.Dict):
            return
        for key, val in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == "state":
                state = _operator_state_from_node(val, self.states)
                if state is not None:
                    self._record(node, state, context)


def detect_operator_only_writes(path: Path, states: set[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        return [{"path": str(path), "line": 0, "state": "", "context": f"unreadable python source: {exc}"}]
    visitor = _OperatorOnlyWriteVisitor(path, states)
    visitor.visit(tree)
    return visitor.findings


def _scan_operator_only_writes(root: Path) -> dict[str, Any]:
    paths = sorted((root / "dimwit").rglob("*.py"))
    findings: list[dict[str, Any]] = []
    for path in paths:
        findings.extend(detect_operator_only_writes(path, OPERATOR_ONLY_STATES))
    issues = [f"{f['path']}:{f['line']} writes operator-only state {f['state']}" for f in findings]
    return {"passed": not findings, "issues": issues, "findings": findings, "scanned_files": len(paths)}


def audit_registered_pipelines(
    root: Path,
    registry: dict[str, str] | None = None,
    manifest: dict[str, Any] | None = None,
    director_tasks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from dimwit.pipelines import PIPELINES

    project_root = Path(root)
    active_registry = dict(registry if registry is not None else PIPELINES)
    active_manifest = manifest if manifest is not None else _load_json_file(project_root / "config" / "production_pipelines.json")
    active_tasks = director_tasks if director_tasks is not None else _load_json_file(project_root / "config" / "director_tasks.json")

    pipelines = [audit_pipeline_contract(name, target, project_root) for name, target in sorted(active_registry.items())]
    duplicate_names = sorted({item["detail"].get("declared_name") for item in pipelines if item["detail"].get("declared_name")})
    registry_clean_issues = [f"{item['name']}: {issue}" for item in pipelines for issue in item["issues"]]

    checks = {
        "registry_clean": {"passed": not registry_clean_issues, "issues": registry_clean_issues},
        "manifest_parity": _manifest_parity(active_registry, active_manifest),
        "director_tasks": _director_task_contract(active_registry, active_tasks),
        "operator_only_writes": _scan_operator_only_writes(project_root),
    }

    blocking_issues = [issue for check in checks.values() for issue in check.get("issues", [])]
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "summary": {
            "registered_count": len(active_registry),
            "pipeline_count": len(pipelines),
            "passed": not blocking_issues,
            "blocking_issue_count": len(blocking_issues),
            "declared_pipeline_names": duplicate_names,
        },
        "pipelines": pipelines,
        "checks": checks,
    }


def write_contract_audit(root: Path, output_path: Path = RESULT_PATH) -> dict[str, Any]:
    report = audit_registered_pipelines(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def validate_contract_report(report: dict[str, Any]) -> dict[str, Any]:
    checks = report.get("checks") if isinstance(report, dict) else None
    if not isinstance(checks, dict):
        return {"passed": False, "issues": ["contract audit report has no checks object"]}
    issues = [issue for check in checks.values() for issue in check.get("issues", [])]
    return {"passed": not issues, "issues": issues, "blocking_issue_count": len(issues)}
