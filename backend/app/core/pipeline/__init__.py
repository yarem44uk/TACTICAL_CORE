"""
Pipeline Module.

Provides event processing pipeline with ordered stage execution.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext
from app.core.pipeline.pipeline import Pipeline
from app.core.pipeline.stage_result import (
    PipelineResult,
    StageResult,
    StageError,
)

__all__ = [
    "BaseStage",
    "PipelineContext",
    "Pipeline",
    "PipelineResult",
    "StageResult",
    "StageError",
]
