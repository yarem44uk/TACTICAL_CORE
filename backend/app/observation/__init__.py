"""Observation Service.

The Observation Service converts Canonical Events received from the Event Bus
into Observation objects. This is the ONLY component responsible for creating
Observations from external connector events.

Canonical Flow:
    External Connector -> Canonical Event -> Event Bus -> Observation Service -> Observation -> Repository

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.observation.service import ObservationService
from app.observation.models import (
    CanonicalEvent,
    EventMetadata,
    ObservationMapping,
    ObservationResult,
)
from app.observation.mapper import EventToObservationMapper
from app.observation.processor import ObservationProcessor
from app.observation.factory import ObservationFactory


__all__ = [
    "ObservationService",
    "CanonicalEvent",
    "EventMetadata",
    "ObservationMapping",
    "ObservationResult",
    "EventToObservationMapper",
    "ObservationProcessor",
    "ObservationFactory",
]
