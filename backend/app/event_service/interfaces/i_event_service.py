from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.event.event import Event


class IEventService(ABC):
    """High-level service interface for event operations."""

    @abstractmethod
    def save_event(self, event: Event) -> None:
        """Persist a single event."""
        ...

    @abstractmethod
    def save_events(self, events: List[Event]) -> None:
        """Persist multiple events atomically."""
        ...

    @abstractmethod
    def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve a single event by ID."""
        ...

    @abstractmethod
    def get_events(self) -> List[Event]:
        """Retrieve all events."""
        ...

    @abstractmethod
    def archive_event(self, event_id: str) -> bool:
        """Mark an event as archived. Returns True if archived, False if not found."""
        ...

    @abstractmethod
    def exists(self, event_id: str) -> bool:
        """Check whether an event exists."""
        ...

    @abstractmethod
    def statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics over stored events."""
        ...

    @abstractmethod
    def export(self) -> List[Dict[str, Any]]:
        """Export all events as serialisable dictionaries."""
        ...

    @abstractmethod
    def import_events(self, data: List[Dict[str, Any]]) -> int:
        """Import events from serialised dictionaries. Returns count of imported events."""
        ...
