"""Timeline Module.

Main timeline management for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.intelligence.timeline.event_store import EventStore, TimelineEvent
from app.intelligence.timeline.queries import TimelineQuery, TimelineQueryBuilder
from app.intelligence.timeline.projections import (
    Projection,
    ProjectionResult,
    ProjectionType,
    create_projection,
)
from app.intelligence.timeline.aggregation import (
    Aggregation,
    AggregationResult,
    AggregationType,
    create_aggregation,
)


@dataclass
class TimelineConfig:
    """Timeline configuration."""

    max_events: int = 100000
    default_limit: int = 100


class Timeline:
    """Timeline management service.

    Provides event-sourced timeline with query,
    projection, and aggregation capabilities.

    Attributes:
        event_store: Event storage backend.
        config: Timeline configuration.
    """

    def __init__(
        self,
        event_store: EventStore,
        config: Optional[TimelineConfig] = None,
    ) -> None:
        """Initialize Timeline.

        Args:
            event_store: Event storage.
            config: Timeline configuration.
        """
        self.event_store = event_store
        self.config = config or TimelineConfig()

    async def append(
        self,
        entity_id: Optional[UUID],
        event_type: str,
        data: Dict[str, Any],
        source: str = "",
        correlation_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """Append an event to the timeline.

        Args:
            entity_id: Associated entity.
            event_type: Type of event.
            data: Event data.
            source: Event source.
            correlation_id: Correlation ID.
            metadata: Additional metadata.

        Returns:
            Created timeline event.
        """
        event = TimelineEvent(
            entity_id=entity_id,
            event_type=event_type,
            data=data,
            source=source,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        return await self.event_store.append(event)

    async def query(self, query: TimelineQuery) -> List[TimelineEvent]:
        """Query timeline events.

        Args:
            query: Query parameters.

        Returns:
            Matching events.
        """
        if query.start_time and query.end_time:
            return await self.event_store.query_by_time_range(
                query.start_time,
                query.end_time,
                query.entity_id,
                query.event_types[0] if query.event_types else None,
            )
        elif query.entity_id:
            return await self.event_store.get_for_entity(
                query.entity_id,
                query.limit,
            )
        else:
            # Return all events
            events = self.event_store._events
            return events[query.offset:query.offset + query.limit]

    async def get_for_entity(
        self,
        entity_id: UUID,
        limit: Optional[int] = None,
    ) -> List[TimelineEvent]:
        """Get timeline events for an entity.

        Args:
            entity_id: Entity UUID.
            limit: Maximum events.

        Returns:
            Timeline events.
        """
        return await self.event_store.get_for_entity(entity_id, limit)

    async def project(
        self,
        projection_type: ProjectionType,
        events: List[TimelineEvent],
    ) -> ProjectionResult:
        """Create a projection from events.

        Args:
            projection_type: Type of projection.
            events: Events to project.

        Returns:
            Projection result.
        """
        projection = create_projection(projection_type)
        return await projection.project(events)

    async def aggregate(
        self,
        aggregation_type: AggregationType,
        events: List[TimelineEvent],
    ) -> AggregationResult:
        """Aggregate events.

        Args:
            aggregation_type: Type of aggregation.
            events: Events to aggregate.

        Returns:
            Aggregation result.
        """
        aggregation = create_aggregation(aggregation_type)
        return await aggregation.aggregate(events)

    async def get_stats(self) -> Dict[str, Any]:
        """Get timeline statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "total_events": await self.event_store.get_count(),
        }
