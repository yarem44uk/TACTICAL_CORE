"""Timeline Query Module.

Provides query builders for timeline events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID


@dataclass
class TimelineQuery:
    """Query parameters for timeline events.

    Attributes:
        entity_id: Filter by entity.
        event_types: Filter by event types.
        start_time: Start of time range.
        end_time: End of time range.
        sources: Filter by sources.
        correlation_id: Filter by correlation.
        limit: Maximum results.
        offset: Result offset.
        order_by: Sort field.
        order_desc: Sort descending.
    """

    entity_id: Optional[UUID] = None
    event_types: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    sources: List[str] = field(default_factory=list)
    correlation_id: Optional[UUID] = None
    limit: int = 100
    offset: int = 0
    order_by: str = "timestamp"
    order_desc: bool = True


class TimelineQueryBuilder:
    """Builder for TimelineQuery objects."""

    def __init__(self) -> None:
        """Initialize builder."""
        self._query = TimelineQuery()

    def for_entity(self, entity_id: UUID) -> "TimelineQueryBuilder":
        """Filter by entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            Self for chaining.
        """
        self._query.entity_id = entity_id
        return self

    def with_types(self, *event_types: str) -> "TimelineQueryBuilder":
        """Filter by event types.

        Args:
            event_types: Event types to include.

        Returns:
            Self for chaining.
        """
        self._query.event_types = list(event_types)
        return self

    def in_time_range(
        self,
        start: datetime,
        end: datetime,
    ) -> "TimelineQueryBuilder":
        """Filter by time range.

        Args:
            start: Start time.
            end: End time.

        Returns:
            Self for chaining.
        """
        self._query.start_time = start
        self._query.end_time = end
        return self

    def from_sources(self, *sources: str) -> "TimelineQueryBuilder":
        """Filter by sources.

        Args:
            sources: Source names.

        Returns:
            Self for chaining.
        """
        self._query.sources = list(sources)
        return self

    def limit_results(self, limit: int, offset: int = 0) -> "TimelineQueryBuilder":
        """Set result limits.

        Args:
            limit: Maximum results.
            offset: Result offset.

        Returns:
            Self for chaining.
        """
        self._query.limit = limit
        self._query.offset = offset
        return self

    def build(self) -> TimelineQuery:
        """Build the query.

        Returns:
            TimelineQuery instance.
        """
        return self._query
