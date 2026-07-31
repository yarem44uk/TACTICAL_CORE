"""
Event Context Module.

Provides immutable context object that carries request-scoped information
through the Event Engine pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class EventContext:
    """
    Immutable context object for event processing.

    Carries request-scoped information through the Event Engine pipeline.
    Once created, the context cannot be modified.

    Attributes:
        request_id: Unique identifier for this request.
        correlation_id: ID for correlating related events.
        source: Source of the event (module, plugin, API, etc.).
        source_type: Type of source (plugin, api, system, etc.).
        user: User ID if authenticated.
        plugin: Plugin ID if published by a plugin.
        timestamp: When the context was created.
        metadata: Additional context metadata.
        parent_event_id: ID of parent event if this is a reply.
        trace_id: Distributed tracing ID.
        span_id: Span ID for tracing.

    Usage:
        >>> ctx = EventContext(
        ...     source="radio-module",
        ...     source_type="plugin",
        ... )
        >>> ctx.user = "admin"  # AttributeError: can't set attribute
    """

    request_id: UUID = field(default_factory=uuid4)
    """Unique identifier for this request."""

    correlation_id: Optional[str] = None
    """ID for correlating related events."""

    source: str = "system"
    """Source of the event (module, plugin, API, etc.)."""

    source_type: str = "system"
    """Type of source (plugin, api, system, etc.)."""

    user: Optional[str] = None
    """User ID if authenticated."""

    plugin: Optional[str] = None
    """Plugin ID if published by a plugin."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When the context was created."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional context metadata."""

    parent_event_id: Optional[UUID] = None
    """ID of parent event if this is a reply."""

    trace_id: Optional[str] = None
    """Distributed tracing ID."""

    span_id: Optional[str] = None
    """Span ID for tracing."""

    def with_metadata(self, **kwargs: Any) -> "EventContext":
        """
        Create a new context with additional metadata.

        Args:
            **kwargs: Metadata key-value pairs to add.

        Returns:
            New EventContext with merged metadata.
        """
        new_metadata = self.metadata.copy()
        new_metadata.update(kwargs)
        return EventContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            timestamp=self.timestamp,
            metadata=new_metadata,
            parent_event_id=self.parent_event_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def with_correlation_id(self, correlation_id: str) -> "EventContext":
        """
        Create a new context with a different correlation ID.

        Args:
            correlation_id: New correlation ID.

        Returns:
            New EventContext with the new correlation ID.
        """
        return EventContext(
            request_id=self.request_id,
            correlation_id=correlation_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            timestamp=self.timestamp,
            metadata=self.metadata.copy(),
            parent_event_id=self.parent_event_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def with_parent_event(self, parent_event_id: UUID) -> "EventContext":
        """
        Create a new context with a parent event ID.

        Args:
            parent_event_id: ID of the parent event.

        Returns:
            New EventContext with the parent event ID.
        """
        return EventContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            timestamp=self.timestamp,
            metadata=self.metadata.copy(),
            parent_event_id=parent_event_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def with_user(self, user: str) -> "EventContext":
        """
        Create a new context with a user.

        Args:
            user: User ID.

        Returns:
            New EventContext with the user.
        """
        return EventContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            source=self.source,
            source_type=self.source_type,
            user=user,
            plugin=self.plugin,
            timestamp=self.timestamp,
            metadata=self.metadata.copy(),
            parent_event_id=self.parent_event_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def with_plugin(self, plugin: str) -> "EventContext":
        """
        Create a new context with a plugin ID.

        Args:
            plugin: Plugin ID.

        Returns:
            New EventContext with the plugin.
        """
        return EventContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=plugin,
            timestamp=self.timestamp,
            metadata=self.metadata.copy(),
            parent_event_id=self.parent_event_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert context to dictionary.

        Returns:
            Dictionary representation of the context.
        """
        return {
            "request_id": str(self.request_id),
            "correlation_id": self.correlation_id,
            "source": self.source,
            "source_type": self.source_type,
            "user": self.user,
            "plugin": self.plugin,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "parent_event_id": str(self.parent_event_id) if self.parent_event_id else None,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }

    def __str__(self) -> str:
        """Return string representation of the context."""
        return (
            f"EventContext(request_id={self.request_id}, "
            f"source={self.source}, correlation_id={self.correlation_id})"
        )


@dataclass
class EventContextFactory:
    """
    Factory for creating EventContext instances.

    Provides convenient methods for creating contexts with
    common configurations.
    """

    default_source: str = "system"
    """Default source for created contexts."""

    default_source_type: str = "system"
    """Default source type for created contexts."""

    def create(
        self,
        source: Optional[str] = None,
        source_type: Optional[str] = None,
        user: Optional[str] = None,
        plugin: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **metadata: Any,
    ) -> EventContext:
        """
        Create a new EventContext.

        Args:
            source: Source of the event.
            source_type: Type of source.
            user: User ID if authenticated.
            plugin: Plugin ID if published by plugin.
            correlation_id: Correlation ID for request tracing.
            **metadata: Additional metadata.

        Returns:
            New EventContext instance.
        """
        return EventContext(
            source=source or self.default_source,
            source_type=source_type or self.default_source_type,
            user=user,
            plugin=plugin,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def create_for_api(self, user: str, correlation_id: Optional[str] = None) -> EventContext:
        """
        Create a context for API-originated events.

        Args:
            user: Authenticated user ID.
            correlation_id: Optional correlation ID.

        Returns:
            EventContext configured for API source.
        """
        return EventContext(
            source="api",
            source_type="api",
            user=user,
            correlation_id=correlation_id,
        )

    def create_for_plugin(self, plugin_id: str) -> EventContext:
        """
        Create a context for plugin-originated events.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            EventContext configured for plugin source.
        """
        return EventContext(
            source=plugin_id,
            source_type="plugin",
            plugin=plugin_id,
        )

    def create_for_system(self, component: str) -> EventContext:
        """
        Create a context for system-originated events.

        Args:
            component: System component name.

        Returns:
            EventContext configured for system source.
        """
        return EventContext(
            source=component,
            source_type="system",
        )


# Global context factory instance
context_factory = EventContextFactory()
