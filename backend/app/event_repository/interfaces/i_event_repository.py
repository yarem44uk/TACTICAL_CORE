from abc import ABC, abstractmethod
from typing import List, Optional

from app.event.event import Event


class IEventRepository(ABC):
    """Interface for event storage and retrieval."""

    @abstractmethod
    def save(self, event: Event) -> None:
        """Save an event to the repository."""
        ...

    @abstractmethod
    def get(self, event_id: str) -> Optional[Event]:
        """Retrieve an event by ID."""
        ...

    @abstractmethod
    def exists(self, event_id: str) -> bool:
        """Check if an event exists."""
        ...

    @abstractmethod
    def delete(self, event_id: str) -> bool:
        """Delete an event by ID. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    def list_all(self) -> List[Event]:
        """Return all events."""
        ...

    @abstractmethod
    def list_by_type(self, event_type: str) -> List[Event]:
        """Return events filtered by type."""
        ...

    @abstractmethod
    def list_by_source(self, source: str) -> List[Event]:
        """Return events filtered by source."""
        ...

    @abstractmethod
    def list_by_correlation(self, correlation_id: str) -> List[Event]:
        """Return events filtered by correlation_id in metadata."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total number of events."""
        ...
