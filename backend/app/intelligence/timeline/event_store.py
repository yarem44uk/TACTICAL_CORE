"""Event Store Module.

Event-sourced storage for timeline events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


@dataclass
class TimelineEvent:
    """A single event in the timeline.

    Attributes:
        id: Event identifier.
        entity_id: Associated entity UUID.
        event_type: Type of timeline event.
        timestamp: When event occurred.
        data: Event data payload.
        source: Event source.
        correlation_id: Related event correlation.
        metadata: Additional metadata.
    """

    id: UUID = field(default_factory=uuid4)
    entity_id: Optional[UUID] = None
    event_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    correlation_id: Optional[UUID] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "source": self.source,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "metadata": self.metadata,
        }


class EventStore:
    """Event-sourced storage backend.

    Provides append and query operations for timeline events.
    Implement the abstract methods for different backends.
    """

    def __init__(self) -> None:
        """Initialize EventStore."""
        self._events: List[TimelineEvent] = []
        self._by_entity: Dict[UUID, List[TimelineEvent]] = {}

    async def append(self, event: TimelineEvent) -> TimelineEvent:
        """Append an event to the store.

        Args:
            event: Event to append.

        Returns:
            Appended event.
        """
        self._events.append(event)

        if event.entity_id:
            if event.entity_id not in self._by_entity:
                self._by_entity[event.entity_id] = []
            self._by_entity[event.entity_id].append(event)

        return event

    async def get(self, event_id: UUID) -> Optional[TimelineEvent]:
        """Get event by ID.

        Args:
            event_id: Event UUID.

        Returns:
            Event if found.
        """
        for event in self._events:
            if event.id == event_id:
                return event
        return None

    async def get_for_entity(
        self,
        entity_id: UUID,
        limit: Optional[int] = None,
    ) -> List[TimelineEvent]:
        """Get all events for an entity.

        Args:
            entity_id: Entity UUID.
            limit: Maximum events to return.

        Returns:
            List of events.
        """
        events = self._by_entity.get(entity_id, [])
        if limit:
            events = events[-limit:]
        return events

    async def query_by_time_range(
        self,
        start: datetime,
        end: datetime,
        entity_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
    ) -> List[TimelineEvent]:
        """Query events by time range.

        Args:
            start: Start time.
            end: End time.
            entity_id: Optional entity filter.
            event_type: Optional event type filter.

        Returns:
            Matching events.
        """
        results = []
        for event in self._events:
            if start <= event.timestamp <= end:
                if entity_id and event.entity_id != entity_id:
                    continue
                if event_type and event.event_type != event_type:
                    continue
                results.append(event)
        return results

    async def get_latest(self, entity_id: UUID) -> Optional[TimelineEvent]:
        """Get latest event for entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            Latest event or None.
        """
        events = self._by_entity.get(entity_id, [])
        return events[-1] if events else None

    async def get_count(self, entity_id: Optional[UUID] = None) -> int:
        """Get event count.

        Args:
            entity_id: Optional entity filter.

        Returns:
            Event count.
        """
        if entity_id:
            return len(self._by_entity.get(entity_id, []))
        return len(self._events)

    async def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
        self._by_entity.clear()
