"""
Event Core Module.

This package contains the core Event Engine components for Tactical Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.core.event_engine import EventEngine
from app.core.event_bus import EventBus
from app.core.event_dispatcher import EventDispatcher
from app.core.event_hooks import EventHooks
from app.core.event_registry import EventRegistry, SubscriberInfo, PluginInfo, HandlerInfo
from app.core.event_history import EventHistory, HistoryEntry, HistoryStatistics
from app.core.event_context import EventContext, EventContextFactory, context_factory
from app.core.event_result import EventResult, EventPublishResult
from app.core.event_exceptions import (
    EventCoreException,
    EventValidationError,
    EventPersistenceError,
    EventDispatchError,
    PluginRegistrationError,
    SubscriberError,
    EventBusError,
    EventHistoryError,
)

# Pipeline components
from app.core.pipeline import (
    BaseStage,
    Pipeline,
    PipelineContext,
    PipelineResult,
    StageResult,
    StageError,
)

# Middleware
from app.core.middleware import (
    BaseMiddleware,
    logging_middleware,
    performance_middleware,
    security_middleware,
)

# Health
from app.core.health import (
    HealthManager,
    HealthStatus,
    ComponentHealth,
    HealthCheck,
    get_health_manager,
)

# Metrics
from app.core.metrics import (
    MetricsCollector,
    Counter,
    Timer,
    get_metrics_collector,
)

__all__ = [
    # Core Engine
    "EventEngine",
    # Bus & Dispatcher
    "EventBus",
    "EventDispatcher",
    # Hooks
    "EventHooks",
    # Registry
    "EventRegistry",
    "SubscriberInfo",
    "PluginInfo",
    "HandlerInfo",
    # History
    "EventHistory",
    "HistoryEntry",
    "HistoryStatistics",
    # Context
    "EventContext",
    "EventContextFactory",
    "context_factory",
    # Result
    "EventResult",
    "EventPublishResult",
    # Exceptions
    "EventCoreException",
    "EventValidationError",
    "EventPersistenceError",
    "EventDispatchError",
    "PluginRegistrationError",
    "SubscriberError",
    "EventBusError",
    "EventHistoryError",
    # Pipeline
    "BaseStage",
    "Pipeline",
    "PipelineContext",
    "PipelineResult",
    "StageResult",
    "StageError",
    # Middleware
    "BaseMiddleware",
    "logging_middleware",
    "performance_middleware",
    "security_middleware",
    # Health
    "HealthManager",
    "HealthStatus",
    "ComponentHealth",
    "HealthCheck",
    "get_health_manager",
    # Metrics
    "MetricsCollector",
    "Counter",
    "Timer",
    "get_metrics_collector",
]
