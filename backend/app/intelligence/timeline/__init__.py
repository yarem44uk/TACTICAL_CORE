"""Timeline Module.

Provides event-sourced timeline for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.intelligence.timeline.timeline import Timeline, TimelineConfig
from app.intelligence.timeline.event_store import EventStore, TimelineEvent
from app.intelligence.timeline.queries import TimelineQuery, TimelineQueryBuilder
from app.intelligence.timeline.projections import Projection, ProjectionResult, create_projection
from app.intelligence.timeline.aggregation import Aggregation, AggregationResult, create_aggregation

__all__ = [
    "Timeline",
    "TimelineConfig",
    "EventStore",
    "TimelineEvent",
    "TimelineQuery",
    "TimelineQueryBuilder",
    "Projection",
    "ProjectionResult",
    "create_projection",
    "Aggregation",
    "AggregationResult",
    "create_aggregation",
]
