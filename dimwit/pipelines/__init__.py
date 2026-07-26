"""Dimwit production pipelines package.

A lazily-resolved registry of WANEFALL production pipelines, all sharing the fully-proofed recursive backbone in
`base.ProductionPipeline`. Add a pipeline by dropping a module here and registering it in PIPELINES.
"""
from __future__ import annotations

import importlib

from .base import ProductionPipeline, Verdict, Artifact, PipelineResult, State, BlockedError

# name -> "module:ClassName" (late-bound so a broken/optional pipeline never breaks import of the package)
PIPELINES = {
    "character_fidelity": "dimwit.pipelines.character_fidelity:CharacterFidelityPipeline",
    "rigging":            "dimwit.pipelines.rigging:RiggingPipeline",
    "animation":          "dimwit.pipelines.animation:AnimationPipeline",
    "environment":        "dimwit.pipelines.environment:EnvironmentPipeline",
    "vfx":                "dimwit.pipelines.vfx:VFXPipeline",
    "audio":              "dimwit.pipelines.audio:AudioPipeline",
    "materials_shaders":  "dimwit.pipelines.materials_shaders:MaterialsShadersPipeline",
    "marble_ingest":      "dimwit.pipelines.marble_ingest:MarbleIngestPipeline",
    "real_game_validation": "dimwit.pipelines.real_game_validation:RealGameValidationPipeline",
    "packaged_build_validation": "dimwit.pipelines.packaged_build_validation:PackagedBuildValidationPipeline",
    "performance_baseline": "dimwit.pipelines.performance_baseline:PerformanceBaselinePipeline",
    "bot_balance_telemetry": "dimwit.pipelines.bot_balance_telemetry:BotBalanceTelemetryPipeline",
    "ui_settings_persistence": "dimwit.pipelines.ui_settings:UiSettingsPersistencePipeline",
    "progression": "dimwit.pipelines.progression:ProgressionPipeline",
    "self_metrics_director": "dimwit.pipelines.self_metrics:SelfMetricsDirectorPipeline",
    "flagship_arena_art_pass": "dimwit.pipelines.flagship_arena_pipeline:FlagshipArenaArtPassPipeline",
    "unreal_game_builder_engine": "dimwit.pipelines.unreal_game_builder_engine:UnrealGameBuilderEnginePipeline",
    "metahuman_output_attempt": "dimwit.pipelines.metahuman_output_attempt:MetaHumanOutputAttemptPipeline",
    "character_source_sync": "dimwit.pipelines.character_source_sync:CharacterSourceSyncPipeline",
    "character_roster_policy": "dimwit.pipelines.character_roster_policy:CharacterRosterPolicyPipeline",
}


def get_pipeline(name: str, **kwargs) -> ProductionPipeline:
    target = PIPELINES[name]
    mod_name, cls_name = target.split(":")
    cls = getattr(importlib.import_module(mod_name), cls_name)
    return cls(**kwargs)


def list_pipelines() -> list:
    return sorted(PIPELINES.keys())


__all__ = ["ProductionPipeline", "Verdict", "Artifact", "PipelineResult", "State", "BlockedError",
           "PIPELINES", "get_pipeline", "list_pipelines"]
