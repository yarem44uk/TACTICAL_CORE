"""
Structured Logging for Pipeline Dispatcher.

Provides structured logging with plugin_id, event_id, source fields.
Enables log aggregation and filtering.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PipelineLogger:
    """
    Structured logger for pipeline operations.

    Logs include:
    - event_id
    - plugin_id
    - source
    - operation type
    - status
    """

    @staticmethod
    def dispatch_start(event_id: Optional[str] = None, plugin: Optional[str] = None) -> None:
        logger.info(
            "Pipeline: dispatch started",
            extra={"event_id": event_id, "plugin_id": plugin, "operation": "dispatch.start"},
        )

    @staticmethod
    def dispatch_success(
        event_id: str,
        plugin: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        extra: Dict[str, Any] = {
            "event_id": event_id,
            "plugin_id": plugin,
            "operation": "dispatch.success",
        }
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        logger.info(
            "Pipeline: dispatch completed",
            extra=extra,
        )

    @staticmethod
    def dispatch_failed(
        event_id: Optional[str] = None,
        plugin: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        logger.error(
            "Pipeline: dispatch failed",
            extra={
                "event_id": event_id,
                "plugin_id": plugin,
                "operation": "dispatch.failed",
                "error": error,
            },
        )

    @staticmethod
    def retry_attempt(
        event_id: Optional[str] = None,
        plugin: Optional[str] = None,
        attempt: int = 1,
        max_retries: int = 3,
    ) -> None:
        logger.warning(
            "Pipeline: retry attempt",
            extra={
                "event_id": event_id,
                "plugin_id": plugin,
                "operation": "dispatch.retry",
                "attempt": attempt,
                "max_retries": max_retries,
            },
        )

    @staticmethod
    def validation_failed(
        plugin: Optional[str] = None,
        errors: list[str] | None = None,
    ) -> None:
        logger.warning(
            "Pipeline: validation failed",
            extra={
                "plugin_id": plugin,
                "operation": "validation.failed",
                "errors": errors or [],
            },
        )

    @staticmethod
    def timeout(
        event_id: Optional[str] = None,
        plugin: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> None:
        logger.error(
            "Pipeline: execution timeout",
            extra={
                "event_id": event_id,
                "plugin_id": plugin,
                "operation": "dispatch.timeout",
                "timeout_ms": timeout_ms,
            },
        )
