"""Aggregation Module.

Provides event aggregation for timeline data.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from app.intelligence.timeline.event_store import TimelineEvent


class AggregationType(str, Enum):
    """Aggregation type classifications."""

    COUNT = "count"
    TIME_SERIES = "time_series"
    ENTITY_COUNT = "entity_count"
    SOURCE_COUNT = "source_count"


@dataclass
class AggregationResult:
    """Result of an aggregation.

    Attributes:
        aggregation_type: Type of aggregation.
        value: Aggregation result.
        metadata: Additional metadata.
    """

    aggregation_type: AggregationType
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


class Aggregation(ABC):
    """Abstract aggregation base class."""

    def __init__(self, aggregation_type: AggregationType) -> None:
        """Initialize aggregation."""
        self.aggregation_type = aggregation_type

    @abstractmethod
    async def aggregate(self, events: List[TimelineEvent]) -> AggregationResult:
        """Execute aggregation.

        Args:
            events: Events to aggregate.

        Returns:
            Aggregation result.
        """
        pass


@dataclass
class CountAggregation(Aggregation):
    """Event count aggregation."""

    def __init__(self) -> None:
        """Initialize."""
        super().__init__(AggregationType.COUNT)

    async def aggregate(self, events: List[TimelineEvent]) -> AggregationResult:
        """Count events.

        Args:
            events: Events to count.

        Returns:
            Aggregation result.
        """
        return AggregationResult(
            aggregation_type=self.aggregation_type,
            value=len(events),
        )


@dataclass
class EntityCountAggregation(Aggregation):
    """Unique entity count aggregation."""

    def __init__(self) -> None:
        """Initialize."""
        super().__init__(AggregationType.ENTITY_COUNT)

    async def aggregate(self, events: List[TimelineEvent]) -> AggregationResult:
        """Count unique entities.

        Args:
            events: Events to aggregate.

        Returns:
            Aggregation result.
        """
        entities = set()
        for event in events:
            if event.entity_id:
                entities.add(event.entity_id)

        return AggregationResult(
            aggregation_type=self.aggregation_type,
            value=len(entities),
        )


@dataclass
class TimeSeriesAggregation(Aggregation):
    """Time series aggregation by interval."""

    def __init__(self, interval_minutes: int = 60) -> None:
        """Initialize.

        Args:
            interval_minutes: Bucket interval.
        """
        super().__init__(AggregationType.TIME_SERIES)
        self.interval_minutes = interval_minutes

    async def aggregate(self, events: List[TimelineEvent]) -> AggregationResult:
        """Aggregate by time intervals.

        Args:
            events: Events to aggregate.

        Returns:
            Aggregation result.
        """
        buckets: Dict[str, int] = {}

        for event in events:
            bucket_start = event.timestamp.replace(
                minute=(event.timestamp.minute // self.interval_minutes) * self.interval_minutes,
                second=0,
                microsecond=0,
            )
            key = bucket_start.isoformat()
            buckets[key] = buckets.get(key, 0) + 1

        return AggregationResult(
            aggregation_type=self.aggregation_type,
            value=buckets,
            metadata={"interval_minutes": self.interval_minutes},
        )


def create_aggregation(aggregation_type: AggregationType) -> Aggregation:
    """Factory for creating aggregations.

    Args:
        aggregation_type: Type of aggregation.

    Returns:
        Aggregation instance.
    """
    if aggregation_type == AggregationType.COUNT:
        return CountAggregation()
    elif aggregation_type == AggregationType.ENTITY_COUNT:
        return EntityCountAggregation()
    elif aggregation_type == AggregationType.TIME_SERIES:
        return TimeSeriesAggregation()
    else:
        raise ValueError(f"Unknown aggregation type: {aggregation_type}")
