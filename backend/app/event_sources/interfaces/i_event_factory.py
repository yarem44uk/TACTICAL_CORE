"""
TACTICAL CORE — Event Factory Interface
WO-013-001 (updated WO-013-002)

Contract for converting raw source data into canonical Event objects.

After WO-013-002: factory returns real Event instances from the WO-012 Event Layer,
not dictionaries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.event.event import Event
from app.event.event_types import EventType


class IEventFactory(ABC):
    """Contract for event creation from raw source data.

    The factory is responsible for normalizing protocol-specific raw data
    into canonical Event objects that the Event Processing Layer (WO-012)
    can consume directly.

    After WO-013-002 integration, create_event() returns a real Event
    instance instead of a dictionary.
    """

    @abstractmethod
    def create_event(
        self,
        raw_data: dict[str, Any],
        source_name: str,
        event_type: EventType | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> Event:
        """Create a canonical Event from raw source data.

        Args:
            raw_data: Protocol-specific raw event data from the adapter.
            source_name: Name of the source adapter that provided the data.
            event_type: Explicit event type. Falls back to EventType.CUSTOM.
            metadata: Optional additional metadata to attach to the event.
            event_id: Optional explicit canonical event identity (WO-025). When
                provided it takes precedence over any resolver-derived identity.

        Returns:
            A canonical Event instance from the WO-012 Event Layer.

        Raises:
            ValueError: If source_name is empty or raw_data is None.
        """
        ...
