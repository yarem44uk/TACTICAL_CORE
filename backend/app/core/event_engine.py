"""
Event Engine Module.

Lightweight orchestrator for event processing pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.core.pipeline import Pipeline
from app.core.event_result import EventResult
from app.core.event_context import EventContext, context_factory
from app.core.event_registry import EventRegistry
from app.core.event_bus import EventBus
from app.core.event_history import EventHistory
from app.core.event_hooks import EventHooks

logger = logging.getLogger(__name__)


class EventEngine:
    """
    Lightweight event orchestrator.

    Manages the event processing pipeline and coordinates components.
    Business logic is delegated to pipeline stages.
    """

    def __init__(
        self,
        database_session: Optional[Any] = None,
        repository: Optional[Any] = None,
        websocket_broadcaster: Optional[Callable] = None,
        ai_notifier: Optional[Callable] = None,
        plugin_notifier: Optional[Callable] = None,
        entity_bridge: Optional[Any] = None,
        enable_parallel_dispatch: bool = True,
        max_dispatch_workers: int = 10,
    ) -> None:
        """
        Initialize the Event Engine.

        Args:
            database_session: Database session for persistence.
            repository: Repository for event storage.
            websocket_broadcaster: WebSocket broadcast callback.
            ai_notifier: AI notification callback.
            plugin_notifier: Plugin notification callback.
            entity_bridge: Optional EntityBridge for entity-layer updates.
            enable_parallel_dispatch: Enable parallel event dispatch.
            max_dispatch_workers: Maximum concurrent dispatch workers.
        """
        self._db_session = database_session
        self._repository = repository
        self._ws_broadcaster = websocket_broadcaster
        self._ai_notifier = ai_notifier
        self._plugin_notifier = plugin_notifier
        self._entity_bridge = entity_bridge

        self._registry = EventRegistry()
        self._bus = EventBus()
        self._history = EventHistory(max_size=10000)
        self._hooks = EventHooks()
        self._context_factory = context_factory

        self._pipeline = self._build_pipeline()
        self._running = False

        logger.info("Event Engine initialized")

    def _build_pipeline(self) -> Pipeline:
        """Build the default processing pipeline."""
        from app.core.pipeline import PipelineContext
        from app.core.pipeline.validation_stage import ValidationStage
        from app.core.pipeline.enrichment_stage import EnrichmentStage
        from app.core.pipeline.persistence_stage import PersistenceStage
        from app.core.pipeline.history_stage import HistoryStage
        from app.core.pipeline.dispatch_stage import DispatchStage
        from app.core.pipeline.broadcast_stage import BroadcastStage
        from app.core.pipeline.plugin_stage import PluginStage
        from app.core.pipeline.ai_stage import AIStage

        pipeline = Pipeline(name="event-processing")

        stages = [
            (ValidationStage(), 0),
            (EnrichmentStage(), 1),
            (PersistenceStage(repository=self._repository, session=self._db_session, entity_bridge=self._entity_bridge), 2),
            (HistoryStage(history_manager=self._history), 3),
            (BroadcastStage(broadcaster=self._ws_broadcaster), 4),
            (DispatchStage(dispatcher=None, registry=self._registry), 5),
            (AIStage(ai_notifier=self._ai_notifier), 6),
            (PluginStage(registry=self._registry), 7),
        ]

        for stage, pos in stages:
            pipeline.add(stage, position=pos)

        return pipeline

    @property
    def registry(self) -> EventRegistry:
        """Get the Event Registry."""
        return self._registry

    @property
    def bus(self) -> EventBus:
        """Get the Event Bus."""
        return self._bus

    @property
    def history(self) -> EventHistory:
        """Get the Event History."""
        return self._history

    @property
    def hooks(self) -> EventHooks:
        """Get the Event Hooks."""
        return self._hooks

    @property
    def pipeline(self) -> Pipeline:
        """Get the processing pipeline."""
        return self._pipeline

    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running

    def startup(self) -> None:
        """Start the Event Engine."""
        if self._running:
            return
        self._bus.start_async_processing()
        self._running = True
        logger.info("Event Engine started")

    def shutdown(self) -> None:
        """Shutdown the Event Engine."""
        if not self._running:
            return
        self._running = False
        self._bus.stop_async_processing()
        if self._db_session:
            try:
                self._db_session.close()
            except Exception as e:
                logger.error("Error closing session: " + str(e))

    def _execute_pipeline(self, event_data, context):
        """Execute the processing pipeline."""
        import time
        start_time = time.time()

        pipeline_result = self._pipeline.execute(
            event_data=event_data,
            correlation_id=context.correlation_id,
            source=context.source,
            source_type=context.source_type,
            user=context.user,
            plugin=context.plugin,
        )

        pipeline_result.total_execution_time_ms = (time.time() - start_time) * 1000
        return pipeline_result

    def _build_event_result(self, pipeline_result, event_type, context):
        """Build EventResult from pipeline result."""
        import time
        from app.core.event_result import EventResult

        result = EventResult(
            success=pipeline_result.success,
            event_id=pipeline_result.event_id,
            event_type=event_type,
            correlation_id=context.correlation_id,
            parent_event_id=context.parent_event_id,
        )

        for stage in pipeline_result.stages:
            self._extract_stage_results(stage, result)

        return result

    def _extract_stage_results(self, stage_result, event_result):
        """Extract results from a stage."""
        for error in stage_result.errors:
            event_result.add_error(error.error_code, error.message, stage_result.stage_name)
        for warning in stage_result.warnings:
            event_result.add_warning(
                warning.get("code", "WARNING"),
                warning.get("message", "")
            )

    def publish(
        self,
        event_data: Dict[str, Any],
        context: Optional[EventContext] = None,
        event_type: Optional[str] = None,
    ) -> EventResult:
        """Publish an event through the processing pipeline."""
        import time
        start_time = time.time()

        context = context or self._context_factory.create()
        event_type = event_type or event_data.get("category", "unknown")

        try:
            pipeline_result = self._execute_pipeline(event_data, context)
            result = self._build_event_result(pipeline_result, event_type, context)
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            result = EventResult(
                success=False,
                event_id=uuid.uuid4(),
                event_type=event_type,
            )
            result.add_error("PIPELINE_ERROR", str(e), "pipeline")
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

    def publish_many(
        self,
        events: List[Dict[str, Any]],
        context: Optional[EventContext] = None,
    ) -> List[EventResult]:
        """Publish multiple events."""
        ctx = context or self._context_factory.create()
        return [self.publish(e, ctx) for e in events]

    def register_plugin(self, plugin_id: str, name: str, version: str = "1.0.0",
                       event_types: Optional[List[str]] = None,
                       subscriptions: Optional[List[str]] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> None:
        """Register a plugin."""
        self._registry.register_plugin(
            plugin_id=plugin_id, name=name, version=version,
            event_types=event_types, subscriptions=subscriptions, metadata=metadata,
        )

    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin."""
        return self._registry.unregister_plugin(plugin_id)

    def subscribe(self, subscriber_id: str, handler: Callable,
                  event_types: Optional[List[str]] = None,
                  patterns: Optional[List[str]] = None,
                  priority: int = 0, is_async: bool = False) -> str:
        """Subscribe to event types."""
        self._registry.register_subscriber(
            subscriber_id=subscriber_id, name=subscriber_id, handler=handler,
            event_types=event_types, patterns=patterns, priority=priority, is_async=is_async,
        )
        return self._bus.subscribe(
            subscriber_id=subscriber_id, handler=handler,
            event_types=event_types, patterns=patterns, priority=priority, is_async=is_async,
        )

    def unsubscribe(self, subscriber_id: str) -> bool:
        """Unsubscribe from events."""
        self._registry.unregister_subscriber(subscriber_id)
        self._bus.unsubscribe(subscriber_id)
        return True

    def health(self) -> Dict[str, Any]:
        """Get health status."""
        return {
            "status": "healthy" if self._running else "stopped",
            "running": self._running,
            "pipeline_stages": self._pipeline.stage_count,
            "enabled_stages": len(self._pipeline.enabled_stages),
            "registry": {
                "plugins": len(self._registry.plugins),
                "subscribers": len(self._registry.subscribers),
            },
        }
