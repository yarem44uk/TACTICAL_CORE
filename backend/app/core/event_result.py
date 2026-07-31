"""
Event Result Model.

Defines the result object returned by the Event Engine after
processing an event through its lifecycle pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class EventResult:
    """
    Result of event processing by the Event Engine.

    Contains all information about the event processing outcome,
    including success status, timing, and any errors or warnings.

    Attributes:
        success: Whether the event was processed successfully.
        event_id: The UUID of the processed event.
        event_type: The type/category of the event.
        execution_time_ms: Time taken to process the event in milliseconds.
        timestamp: When the processing completed.
        database_saved: Whether the event was saved to database.
        websocket_broadcast: Whether the event was broadcast via WebSocket.
        ai_notified: Whether AI engine was notified.
        subscribers_executed: Number of subscribers that received the event.
        plugins_notified: List of plugins that were notified.
        errors: List of errors encountered during processing.
        warnings: List of warnings encountered during processing.
        metadata: Additional processing metadata.
        correlation_id: Correlation ID for request tracing.
        parent_event_id: Parent event ID if this is a reply/response.

    Usage:
        >>> result = EventResult(
        ...     success=True,
        ...     event_id=uuid.uuid4(),
        ...     event_type="radio_transmission",
        ... )
        >>> print(f"Processed in {result.execution_time_ms}ms")
    """

    success: bool
    """Whether the event was processed successfully."""

    event_id: UUID
    """The UUID of the processed event."""

    event_type: str
    """The type/category of the event."""

    execution_time_ms: float = 0.0
    """Time taken to process the event in milliseconds."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When the processing completed."""

    database_saved: bool = False
    """Whether the event was saved to database."""

    websocket_broadcast: bool = False
    """Whether the event was broadcast via WebSocket."""

    ai_notified: bool = False
    """Whether AI engine was notified."""

    subscribers_executed: int = 0
    """Number of subscribers that received the event."""

    plugins_notified: List[str] = field(default_factory=list)
    """List of plugins that were notified."""

    errors: List[Dict[str, Any]] = field(default_factory=list)
    """List of errors encountered during processing."""

    warnings: List[Dict[str, Any]] = field(default_factory=list)
    """List of warnings encountered during processing."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional processing metadata."""

    correlation_id: Optional[str] = None
    """Correlation ID for request tracing."""

    parent_event_id: Optional[UUID] = None
    """Parent event ID if this is a reply/response."""

    def add_error(
        self,
        error_code: str,
        message: str,
        component: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add an error to the result.

        Args:
            error_code: Machine-readable error code.
            message: Human-readable error message.
            component: Component where the error occurred.
            details: Additional error details.
        """
        error = {
            "code": error_code,
            "message": message,
            "component": component,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.errors.append(error)
        self.success = False

    def add_warning(
        self,
        warning_code: str,
        message: str,
        component: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a warning to the result.

        Args:
            warning_code: Machine-readable warning code.
            message: Human-readable warning message.
            component: Component where the warning occurred.
            details: Additional warning details.
        """
        warning = {
            "code": warning_code,
            "message": message,
            "component": component,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "success": self.success,
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "database_saved": self.database_saved,
            "websocket_broadcast": self.websocket_broadcast,
            "ai_notified": self.ai_notified,
            "subscribers_executed": self.subscribers_executed,
            "plugins_notified": self.plugins_notified,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "parent_event_id": str(self.parent_event_id) if self.parent_event_id else None,
        }

    @property
    def error_count(self) -> int:
        """Get the number of errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Get the number of warnings."""
        return len(self.warnings)

    def __str__(self) -> str:
        """Return string representation of the result."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"EventResult({status}, event_id={self.event_id}, "
            f"execution_time={self.execution_time_ms:.2f}ms, "
            f"subscribers={self.subscribers_executed})"
        )


@dataclass
class EventPublishResult:
    """
    Result of publishing multiple events.

    Contains aggregated results from publishing multiple events.

    Attributes:
        total: Total number of events attempted.
        successful: Number of successfully processed events.
        failed: Number of failed events.
        results: Individual event results.
        total_execution_time_ms: Total processing time.
    """

    total: int
    """Total number of events attempted."""

    successful: int = 0
    """Number of successfully processed events."""

    failed: int = 0
    """Number of failed events."""

    results: List[EventResult] = field(default_factory=list)
    """Individual event results."""

    total_execution_time_ms: float = 0.0
    """Total processing time for all events."""

    def add_result(self, result: EventResult) -> None:
        """
        Add an individual event result.

        Args:
            result: The event result to add.
        """
        self.results.append(result)
        if result.success:
            self.successful += 1
        else:
            self.failed += 1
        self.total_execution_time_ms += result.execution_time_ms

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary.

        Returns:
            Dictionary representation of the publish result.
        """
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "total_execution_time_ms": self.total_execution_time_ms,
            "results": [r.to_dict() for r in self.results],
        }
