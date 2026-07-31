"""Projection Module.

Provides read model projections for timeline data.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from app.intelligence.timeline.event_store import TimelineEvent


class ProjectionType(str, Enum):
    """Projection type classifications."""

    ENTITY_HISTORY = "entity_history"
    ACTIVITY_SUMMARY = "activity_summary"
    TIMELINE_SUMMARY = "timeline_summary"
    SOURCE_BREAKDOWN = "source_breakdown"
    EVENT_DISTRIBUTION = "event_distribution"


@dataclass
class ProjectionResult:
    """Result of a projection.

    Attributes:
        projection_type: Type of projection.
        data: Projection data.
        generated_at: When generated.
        metadata: Additional metadata.
    """

    projection_type: ProjectionType
    data: Dict[str, Any]
    generated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Projection(ABC):
    """Abstract projection base class."""

    def __init__(self, projection_type: ProjectionType) -> None:
        """Initialize projection."""
        self.projection_type = projection_type

    @abstractmethod
    async def project(self, events: List[TimelineEvent]) -> ProjectionResult:
        """Execute projection.

        Args:
            events: Events to project.

        Returns:
            Projection result.
        """
        pass


@dataclass
class EntityHistoryProjection(Projection):
    """Entity activity history projection."""

    def __init__(self) -> None:
        """Initialize."""
        super().__init__(ProjectionType.ENTITY_HISTORY)

    async def project(self, events: List[TimelineEvent]) -> ProjectionResult:
        """Project entity history.

        Args:
            events: Timeline events.

        Returns:
            Projection result.
        """
        entity_events: Dict[str, List[TimelineEvent]] = {}
        for event in events:
            if event.entity_id:
                key = str(event.entity_id)
                if key not in entity_events:
                    entity_events[key] = []
                entity_events[key].append(event)

        return ProjectionResult(
            projection_type=self.projection_type,
            data={
                "entities": len(entity_events),
                "total_events": len(events),
                "by_entity": {
                    eid: len(evts) for eid, evts in entity_events.items()
                },
            },
        )


@dataclass
class ActivitySummaryProjection(Projection):
    """Activity summary projection."""

    def __init__(self) -> None:
        """Initialize."""
        super().__init__(ProjectionType.ACTIVITY_SUMMARY)

    async def project(self, events: List[TimelineEvent]) -> ProjectionResult:
        """Project activity summary.

        Args:
            events: Timeline events.

        Returns:
            Projection result.
        """
        event_counts: Dict[str, int] = {}
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        return ProjectionResult(
            projection_type=self.projection_type,
            data={
                "total_events": len(events),
                "event_type_counts": event_counts,
            },
        )


def create_projection(projection_type: ProjectionType) -> Projection:
    """Factory for creating projections.

    Args:
        projection_type: Type of projection.

    Returns:
        Projection instance.
    """
    if projection_type == ProjectionType.ENTITY_HISTORY:
        return EntityHistoryProjection()
    elif projection_type == ProjectionType.ACTIVITY_SUMMARY:
        return ActivitySummaryProjection()
    else:
        raise ValueError(f"Unknown projection type: {projection_type}")
