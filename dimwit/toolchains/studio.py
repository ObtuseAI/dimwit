"""Resumable full-game studio DAG over Dimwit's Blender, Unreal, pipelines, and fail-closed validators."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from dimwit.core import sha256_obj
from dimwit.engine import DimwitLedger
from dimwit.pipelines import get_pipeline, list_pipelines

from . import blender, unreal
from .common import atomic_json


ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "config" / "studio_pipeline.json"
COMPLETE_STATES = {"PASS", "REVIEW_READY"}
OPERATOR_ONLY = {"HUMAN_ACCEPTED", "PROMOTED_TO_ACTIVE_SLICE"}


def load_graph(path: Path = GRAPH_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_graph(graph: dict, known_pipelines: set[str] | None = None) -> dict:
    issues = []
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    ids = [str(node.get("id") or "") for node in nodes]
    if not nodes or any(not node_id for node_id in ids) or len(ids) != len(set(ids)):
        issues.append("studio nodes must be non-empty with unique ids")
    if graph.get("review_ceiling") != "PROMOTED_TO_REVIEW":
        issues.append("studio review ceiling changed")
    by_id = {str(node.get("id")): node for node in nodes}
    known = known_pipelines if known_pipelines is not None else set(list_pipelines())
    for node in nodes:
        kind = node.get("kind")
        if kind not in {"preflight", "pipeline", "validation"}:
            issues.append(f"{node.get('id')}: unsupported kind {kind}")
        if kind == "pipeline" and node.get("pipeline") not in known:
            issues.append(f"{node.get('id')}: unknown pipeline {node.get('pipeline')}")
        for dep in node.get("deps") or []:
            if dep not in by_id:
                issues.append(f"{node.get('id')}: unknown dependency {dep}")
    visiting, visited = set(), set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            issues.append(f"cycle detected at {node_id}")
            return
        if node_id in visited or node_id not in by_id:
            return
        visiting.add(node_id)
        for dep in by_id[node_id].get("deps") or []:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in ids:
        visit(node_id)
    payload = json.dumps(graph)
    if any(state in payload for state in OPERATOR_ONLY):
        issues.append("operator-only state leaked into studio graph")
    return {"passed": not issues, "issues": sorted(set(issues)), "node_count": len(nodes)}


def topological_order(graph: dict) -> list[str]:
    valid = validate_graph(graph)
    if not valid["passed"]:
        raise ValueError("; ".join(valid["issues"]))
    nodes = {node["id"]: node for node in graph["nodes"]}
    ordered, remaining = [], set(nodes)
    while remaining:
        ready = sorted(node_id for node_id in remaining if set(nodes[node_id].get("deps") or []).issubset(ordered))
        if not ready:
            raise ValueError("studio graph cannot be topologically ordered")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def downstream_counts(graph: dict) -> dict[str, int]:
    """Critical-path proxy used to choose among simultaneously ready nodes."""
    reverse = {node["id"]: set() for node in graph["nodes"]}
    for node in graph["nodes"]:
        for dep in node.get("deps") or []:
            reverse[dep].add(node["id"])

    def descendants(node_id: str) -> set[str]:
        found = set(reverse[node_id])
        for child in list(found):
            found.update(descendants(child))
        return found

    return {node_id: len(descendants(node_id)) for node_id in reverse}


class StudioController:
    def __init__(self, root: Path = ROOT, graph: dict | None = None,
                 pipeline_factory: Callable[[str], object] = get_pipeline,
                 validate_fn: Callable[[list[str] | None], dict] | None = None,
                 state_path: Path | None = None, ledger_path: Path | None = None):
        self.root = Path(root)
        self.graph = graph or load_graph(self.root / "config" / "studio_pipeline.json")
        result = validate_graph(self.graph)
        if not result["passed"]:
            raise ValueError("; ".join(result["issues"]))
        self.nodes = {node["id"]: node for node in self.graph["nodes"]}
        self.pipeline_factory = pipeline_factory
        if validate_fn is None:
            from dimwit.director import Director

            def validate_fn(domains):
                return Director().validate_everything(domains)
        self.validate_fn = validate_fn
        studio_id = self.graph["studio_id"]
        self.state_path = state_path or (self.root / "artifacts" / "studio" / studio_id / "state.json")
        self.ledger = DimwitLedger(ledger_path or (self.root / "ledger" / f"studio_{studio_id}.jsonl"))

    def _state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {"schema_version": 1, "studio_id": self.graph["studio_id"], "nodes": {},
                "review_ceiling": "PROMOTED_TO_REVIEW"}

    def _proofs_present(self, node: dict) -> bool:
        proofs = node.get("proofs") or []
        return all((self.root / proof).is_file() for proof in proofs)

    def plan(self) -> dict:
        state = self._state()
        ordered = topological_order(self.graph)
        criticality = downstream_counts(self.graph)
        effective = {}
        for node_id in ordered:
            node = self.nodes[node_id]
            stored_status = ((state.get("nodes") or {}).get(node_id, {}) or {}).get("status", "PENDING")
            effective[node_id] = ("PROOF_MISSING" if stored_status in COMPLETE_STATES
                                  and not self._proofs_present(node) else stored_status)
        rows = []
        for node_id in ordered:
            node = self.nodes[node_id]
            status = effective[node_id]
            deps_ready = all(effective.get(dep) in COMPLETE_STATES for dep in node.get("deps") or [])
            rows.append({"id": node_id, "kind": node["kind"], "status": status,
                         "deps": node.get("deps") or [], "deps_ready": deps_ready,
                         "cost": float(node.get("cost", 1)), "downstream_count": criticality[node_id],
                         "proofs_present": self._proofs_present(node)})
        return {"studio_id": self.graph["studio_id"], "review_ceiling": "PROMOTED_TO_REVIEW",
                "graph_validation": validate_graph(self.graph), "nodes": rows,
                "complete": sum(row["status"] in COMPLETE_STATES for row in rows), "total": len(rows)}

    def run(self, *, execute: bool = False, max_nodes: int = 3, max_cost: float = 6,
            max_seconds: float = 14400) -> dict:
        if not execute:
            return {"state": "PLAN_ONLY", "mutation_performed": False, **self.plan()}
        state, started, spent, ran = self._state(), time.time(), 0.0, []
        while len(ran) < max_nodes and time.time() - started < max_seconds:
            ordered = topological_order(self.graph)
            criticality = downstream_counts(self.graph)
            ready = []
            for node_id in ordered:
                node = self.nodes[node_id]
                current = (state.get("nodes") or {}).get(node_id, {})
                if current.get("status") in COMPLETE_STATES and self._proofs_present(node):
                    continue
                if all((state.get("nodes") or {}).get(dep, {}).get("status") in COMPLETE_STATES
                       for dep in node.get("deps") or []):
                    ready.append(node)
            if not ready:
                break
            ready.sort(key=lambda item: (-criticality[item["id"]], float(item.get("cost", 1)), item["id"]))
            node = ready[0]
            cost = float(node.get("cost", 1))
            if spent + cost > max_cost:
                break
            result = self._run_node(node)
            spent += cost
            ran.append(result)
            state.setdefault("nodes", {})[node["id"]] = result
            state["updated_at"] = time.time()
            atomic_json(self.state_path, state)
            self._ledger(node, result)
            if result["status"] not in COMPLETE_STATES:
                break
        plan = self.plan()
        final = "PROMOTED_TO_REVIEW" if plan["complete"] == plan["total"] else (
            "BLOCKED" if ran and ran[-1]["status"] not in COMPLETE_STATES else "PARTIAL")
        return {"state": final, "mutation_performed": bool(ran), "ran": ran,
                "spent_cost": round(spent, 3), "elapsed_seconds": round(time.time() - started, 3), **plan}

    def _run_node(self, node: dict) -> dict:
        started = time.time()
        if node["kind"] == "preflight":
            detail = {"blender": blender.health(run_version=True),
                      "unreal": unreal.health(self.graph.get("project", unreal.DEFAULT_PROJECT))}
            passed = detail["blender"]["ok"] and detail["unreal"]["ok"]
            status, pipeline_state = ("PASS" if passed else "BLOCKED"), None
        elif node["kind"] == "validation":
            detail = self.validate_fn(node.get("domains") or [])
            passed = detail.get("suite_verdict") == "PASS"
            status, pipeline_state = ("PASS" if passed else "BLOCKED"), None
        else:
            try:
                pipeline_result = self.pipeline_factory(node["pipeline"]).run({"asset_id": node.get("asset_id")})
                pipeline_state = str(pipeline_result.state).split(".")[-1]
                validation = self.validate_fn(node.get("domains") or [])
                passed = pipeline_state == "PROMOTED_TO_REVIEW" and validation.get("suite_verdict") == "PASS"
                status = "REVIEW_READY" if passed else "BLOCKED"
                detail = {"pipeline_state": pipeline_state, "pipeline_score": pipeline_result.score,
                          "validation": {"suite_verdict": validation.get("suite_verdict"),
                                         "counts": validation.get("counts")}}
            except Exception as exc:
                passed, status, pipeline_state = False, "FAILED", "EXECUTION_ERROR"
                detail = {"error": f"{type(exc).__name__}: {exc}"}
        return {"id": node["id"], "status": status, "pipeline_state": pipeline_state,
                "passed": passed, "detail": detail, "proofs_present": self._proofs_present(node),
                "elapsed_seconds": round(time.time() - started, 3), "review_ceiling": "PROMOTED_TO_REVIEW"}

    def _ledger(self, node: dict, result: dict) -> None:
        self.ledger.append({"ts": int(time.time()), "actor": "dimwit-studio", "asset_id": node["id"],
                            "state": f"studio.{result['status']}",
                            "candidate_hash": sha256_obj({"node": node, "result": result}),
                            "detail": {"node_id": node["id"], "status": result["status"],
                                       "review_ceiling": "PROMOTED_TO_REVIEW"}})


def plan_studio() -> dict:
    return StudioController().plan()


def run_studio(allow_mutation: bool = False, max_nodes: int = 3, max_cost: float = 6) -> dict:
    return StudioController().run(execute=allow_mutation, max_nodes=max_nodes, max_cost=max_cost)
