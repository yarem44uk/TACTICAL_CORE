"""
Pipeline Dispatcher Configuration.

Configures the PipelineDispatcher with Pipeline and EventPersistenceService.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.pipeline import Pipeline
from app.core.pipeline.context import PipelineContext
from app.database import EventPersistenceService


@dataclass
class PipelineDispatcherConfig:
    """Configuration for the PipelineDispatcher."""

    pipeline: Optional[Pipeline] = None
    persistence_service: Optional[EventPersistenceService] = None
    default_source: str = "pipeline_dispatcher"
    default_source_type: str = "system"
    max_retries: int = 3
    retry_delay_ms: int = 100
    timeout_ms: int = 5000
    metrics_enabled: bool = True
    logging_enabled: bool = True
    logging_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.pipeline is None:
            self.pipeline = Pipeline(name="plugin-event-pipeline")

        if self.persistence_service is None:
            raise ValueError(
                "EventPersistenceService is required for PipelineDispatcher"
            )


class PipelineDispatcher:
    """
    Central event dispatcher that routes plugin events through the Pipeline
    to EventPersistenceService.

    Architecture Rule:
    No plugin may write directly to the database.
    All plugin events MUST flow through this dispatcher.

    Usage:
        config = PipelineDispatcherConfig(persistence_service=service)
        dispatcher = PipelineDispatcher(config)
        dispatcher.dispatch(event_data, plugin="signal")
    """

    def __init__(
        self,
        config: Optional[PipelineDispatcherConfig] = None,
    ) -> None:
        """
        Initialize the PipelineDispatcher.

        Args:
            config: Optional configuration. Defaults to a basic config.
        """
        self._config = config or PipelineDispatcherConfig()
        # __post_init__ guarantees these are non-None
        assert self._config.pipeline is not None
        assert self._config.persistence_service is not None
        self._pipeline: Pipeline = self._config.pipeline
        self._persistence_service: EventPersistenceService = (
            self._config.persistence_service
        )
        self._metrics: Dict[str, int] = {
            "dispatched": 0,
            "failed": 0,
            "retried": 0,
        }

    @property
    def metrics(self) -> Dict[str, int]:
        """Get dispatcher metrics."""
        return dict(self._metrics)

    def dispatch(
        self,
        event_data: Dict[str, Any],
        plugin: Optional[str] = None,
        source: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Dispatch an event through the pipeline to persistence.

        Args:
            event_data: Event data dictionary.
            plugin: Optional plugin identifier.
            source: Optional source identifier.
            source_type: Optional source type.

        Returns:
            Event ID string if successful, None otherwise.
        """
        effective_source = source or self._config.default_source
        effective_source_type = source_type or self._config.default_source_type

        result = self._pipeline.execute(
            event_data=event_data,
            source=effective_source,
            source_type=effective_source_type,
            plugin=plugin,
        )

        if result.success:
            self._metrics["dispatched"] += 1
            return str(result.event_id)
        else:
            self._metrics["failed"] += 1
            return None

    def dispatch_batch(
        self,
        events: list[Dict[str, Any]],
        plugin: Optional[str] = None,
    ) -> list[str]:
        """
        Dispatch multiple events through the pipeline.

        Args:
            events: List of event data dictionaries.
            plugin: Optional plugin identifier.

        Returns:
            List of successfully dispatched event IDs.
        """
        dispatched = []
        for event_data in events:
            event_id = self.dispatch(event_data, plugin=plugin)
            if event_id:
                dispatched.append(event_id)
        return dispatched

    def get_pipeline(self) -> Pipeline:
        """Get the configured pipeline."""
        return self._pipeline

    def get_persistence_service(self) -> EventPersistenceService:
        """Get the configured persistence service."""
        return self._persistence_service
