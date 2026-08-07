from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """
    Event type enumeration.
    
    Every event must have exactly one type.
    Types are immutable and extensible only through new Work Orders.
    """

    # Entity lifecycle
    ENTITY_CREATED = "entity.created"
    ENTITY_UPDATED = "entity.updated"
    ENTITY_REMOVED = "entity.removed"

    # Observation
    OBSERVATION_CREATED = "observation.created"
    OBSERVATION_VERIFIED = "observation.verified"
    OBSERVATION_RETRACTED = "observation.retracted"

    # Signal
    SIGNAL_RECEIVED = "signal.received"
    SIGNAL_PROCESSED = "signal.processed"
    SIGNAL_FAILED = "signal.failed"

    # System
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # Custom (extensible)
    CUSTOM = "custom"

    def __str__(self) -> str:
        return self.value
