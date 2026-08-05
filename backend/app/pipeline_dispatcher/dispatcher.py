"""
Pipeline Dispatcher Configuration.

Configures the PipelineDispatcher with Pipeline and EventPersistenceService.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import time
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.pipeline import Pipeline
from app.core.pipeline.context import PipelineContext
from app.database import EventPersistenceService
from app.pipeline_dispatcher.validation import EventValidator, ValidationError
from app.pipeline_dispatcher.error_isolation import ErrorIsolation
from app.pipeline_dispatcher.pipeline_logger import PipelineLogger


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
        assert self._config.pipeline is not None
        assert self._config.persistence_service is not None
        self._pipeline: Pipeline = self._config.pipeline
        self._persistence_service: EventPersistenceService = self._config.persistence_service
        self._validator = EventValidator()
        self._error_isolation = ErrorIsolation()
        self._metrics_lock = threading.Lock()
        self._metrics: Dict[str, int] = {
            "dispatched": 0,
            "failed": 0,
            "retried": 0,
            "validation_errors": 0,
            "timeout": 0,
            "batch_dispatched": 0,
            "batch_failed": 0,
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

        Includes validation, error isolation, and retry logic.

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

        if self._config.logging_enabled:
            PipelineLogger.dispatch_start(plugin=plugin)

        # Validate event data
        validation = self._error_isolation.wrap(
            lambda: self._validator.validate(event_data, plugin=plugin),
            plugin=plugin,
            context="validation",
        )
        if not validation.success or not validation.result.valid:
            with self._metrics_lock:
                self._metrics["validation_errors"] += 1
                self._metrics["failed"] += 1
            if self._config.logging_enabled:
                errors = validation.result.errors if validation.success else ["validation error"]
                PipelineLogger.validation_failed(plugin=plugin, errors=errors)
            return None

        # Execute with retry
        event_id = None
        max_attempts = self._config.max_retries
        retry_delay = self._config.retry_delay_ms / 1000.0
        timeout_ms = self._config.timeout_ms

        deadline = time.monotonic() + (timeout_ms / 1000.0)

        for attempt in range(max_attempts):
            if attempt > 0:
                with self._metrics_lock:
                    self._metrics["retried"] += 1
                if self._config.logging_enabled:
                    PipelineLogger.retry_attempt(
                        plugin=plugin,
                        attempt=attempt,
                        max_retries=max_attempts,
                    )
                time.sleep(retry_delay)

            # Check timeout before each attempt
            elapsed = (time.monotonic() - deadline)
            if elapsed > 0:
                with self._metrics_lock:
                    self._metrics["timeout"] += 1
                    self._metrics["failed"] += 1
                if self._config.logging_enabled:
                    PipelineLogger.timeout(plugin=plugin)
                return None

            # Capture immutable copy to avoid lambda late-binding
            data = dict(event_data)
            dispatch_op = lambda d=data: self._pipeline.execute(
                event_data=d,
                source=effective_source,
                source_type=effective_source_type,
                plugin=plugin,
            )
            result = self._error_isolation.wrap(
                dispatch_op,
                plugin=plugin,
                context=f"dispatch_attempt_{attempt+1}",
            )

            if result.success and result.result and result.result.success:
                event_id = str(result.result.event_id)
                with self._metrics_lock:
                    self._metrics["dispatched"] += 1
                if self._config.logging_enabled:
                    PipelineLogger.dispatch_success(event_id=event_id, plugin=plugin)
                return event_id

        with self._metrics_lock:
            self._metrics["failed"] += 1
        if self._config.logging_enabled:
            error = "pipeline execution failed after retries"
            PipelineLogger.dispatch_failed(plugin=plugin, error=error)
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
                with self._metrics_lock:
                    self._metrics["batch_dispatched"] += 1
            else:
                with self._metrics_lock:
                    self._metrics["batch_failed"] += 1
        return dispatched

    def get_pipeline(self) -> Pipeline:
        """Get the configured pipeline."""
        return self._pipeline

    def get_persistence_service(self) -> EventPersistenceService:
        """Get the configured persistence service."""
        return self._persistence_service
