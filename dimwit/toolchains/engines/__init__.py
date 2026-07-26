"""Extensible engine contracts and Dimwit's built-in universal game factory."""

from dimwit.toolchains.engines.contracts import BuildPlan, BuildRequest, EngineProject
from dimwit.toolchains.engines.universal import audit_engines, detect_project, plan_build, run_build, scan_projects

__all__ = [
    "BuildPlan", "BuildRequest", "EngineProject", "audit_engines", "detect_project",
    "plan_build", "run_build", "scan_projects",
]
