"""
Event Layer — Appendix-only event domain.

Event Layer responds exclusively for events.
An event is a fact. An event never changes. An event is only added.
No UPDATE. No DELETE. Append Only.

Layer Position:
    ENTITY -> EVENT -> TIMELINE -> PLUGIN SYSTEM -> TACTICAL WALL
"""

from app.event.event import Event
from app.event.event_types import EventType
from app.event.event_status import EventStatus
from app.event.event_metadata import EventMetadata

__all__ = [
    "Event",
    "EventType",
    "EventStatus",
    "EventMetadata",
]
