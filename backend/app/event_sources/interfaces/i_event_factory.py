"""
TACTICAL CORE — Event Factory Interface
WO-013-001

Contract for converting raw source data into canonical Event objects.
"""

from abc import ABC, abstractmethod
from typing import Any


class IEventFactory(ABC):
    """Contract for event creation from raw source data.

    The factory is responsible for normalizing protocol-specific raw data
    into canonical Event structures that the Event Processing Layer (WO-012)
    can consume.
    """

    @abstractmethod
    def create_event(
        self,
        raw_data: dict[str, Any],
        source_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a canonical event from raw source data.

        Args:
            raw_data: Protocol-specific raw event data from the adapter.
            source_name: Name of the source adapter that provided the data.
            metadata: Optional additional metadata to attach to the event.

        Returns:
            Canonical event dictionary compatible with WO-012 Event Processing Layer.
        """
        ...
