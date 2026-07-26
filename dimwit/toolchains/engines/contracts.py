"""Stable contracts shared by every Dimwit game-engine adapter."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


REVIEW_CEILING = "PROMOTED_TO_REVIEW"
SUPPORTED_TARGETS = frozenset({"windows", "linux", "macos", "web", "android", "ios", "server", "xr"})
SUPPORTED_PROFILES = frozenset({"debug", "development", "release", "shipping"})


@dataclass(frozen=True)
class EngineProject:
    engine: str
    root: str
    marker: str
    confidence: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BuildRequest:
    project: str
    target: str
    output: str
    profile: str = "release"
    engine: str = "auto"
    preset: str | None = None
    job_id: str = "universal_game_build"
    brief: str | None = None

    def validate(self) -> None:
        if self.target not in SUPPORTED_TARGETS:
            raise ValueError(f"unsupported universal target: {self.target}")
        if self.profile not in SUPPORTED_PROFILES:
            raise ValueError(f"unsupported build profile: {self.profile}")
        if not self.project or not self.output:
            raise ValueError("project and output are required")


@dataclass(frozen=True)
class BuildPlan:
    engine: str
    operation: str
    project: str
    target: str
    profile: str
    command: tuple[str, ...]
    outputs: tuple[str, ...]
    job_id: str
    tool: str
    timeout_seconds: float = 3600.0
    prerequisites: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)
    review_ceiling: str = REVIEW_CEILING
    shell: bool = False

    def validate(self) -> None:
        if self.review_ceiling != REVIEW_CEILING:
            raise ValueError("universal build review ceiling changed")
        if self.shell is not False:
            raise ValueError("engine plans must use argv-only process execution")
        if not self.command or not all(isinstance(value, str) and value for value in self.command):
            raise ValueError("engine plan command must be a non-empty argv tuple")
        if not self.outputs:
            raise ValueError("engine plan must declare at least one proof output")

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)


class EngineAdapter(Protocol):
    engine_id: str

    def health(self) -> dict: ...

    def detect(self, root: Path) -> EngineProject | None: ...

    def plan(self, request: BuildRequest, project: EngineProject, output: Path) -> BuildPlan: ...
