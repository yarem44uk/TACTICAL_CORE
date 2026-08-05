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

__all__ = [
    "PipelineDispatcher",
    "PipelineDispatcherConfig",
    "PluginEventDispatcher",
]
