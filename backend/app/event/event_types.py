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

    # Relation
    # WO-018 — Explicit canonical relation severance.  An explicit
    # operator/system command that a specific existing relation is no longer
    # valid.  Affects ONLY the identified relation (ACTIVE -> INACTIVE, durable
    # terminal); it never mutates either endpoint entity and never cascades.
    # Distinct from ENTITY_REMOVED (which tombstones an entity and cascades to
    # all its relations).
    RELATION_SEVERED = "relation.severed"

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
