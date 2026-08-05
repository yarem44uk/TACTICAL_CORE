"""
Pipeline Dispatcher Module.

Provides centralized event dispatching through the official Event Pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.pipeline_dispatcher.dispatcher import (
    PipelineDispatcher,
    PipelineDispatcherConfig,
)
from app.pipeline_dispatcher.plugin_event_dispatcher import PluginEventDispatcher
from app.pipeline_dispatcher.validation import (
    EventValidator,
    ValidationError,
    ValidationResult,
)
from app.pipeline_dispatcher.error_isolation import (
    ErrorIsolation,
    ErrorIsolationResult,
)
from app.pipeline_dispatcher.pipeline_logger import PipelineLogger

__all__ = [
    "PipelineDispatcher",
    "PipelineDispatcherConfig",
    "PluginEventDispatcher",
    "EventValidator",
    "ValidationError",
    "ValidationResult",
    "ErrorIsolation",
    "ErrorIsolationResult",
    "PipelineLogger",
]
