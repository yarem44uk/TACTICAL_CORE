from __future__ import annotations

from enum import Enum


class EventStatus(str, Enum):
    """
    Event status enumeration.
    
    Events are append-only. Status tracks processing state, not content changes.
    Once created, an event's status flows forward only.
    """

    REGISTERED = "registered"
    PROCESSED = "processed"
    ACKNOWLEDGED = "acknowledged"
    ARCHIVED = "archived"

    def __str__(self) -> str:
        return self.value
