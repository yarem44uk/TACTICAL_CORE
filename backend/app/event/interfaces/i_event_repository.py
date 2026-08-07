from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.event.event import Event


class IEventRepository(ABC):
    """
    Repository contract for Event persistence.
    
    Events are append-only.
    No UPDATE. No DELETE.
    Only add and read operations.
    Thread-safe access required.
    """

    @abstractmethod
    def add(self, event: Event) -> str:
        """
        Add an event. Returns the event_id.
        This is the only write operation.
        """
        pass

    @abstractmethod
    def get(self, event_id: str) -> Optional[Event]:
        """Retrieve a single event by ID."""
        pass

    @abstractmethod
    def list_all(self, event_type: Optional[str] = None) -> List[Event]:
        """
        List all events, optionally filtered by event_type.
        Returns events in chronological order.
        """
        pass

    @abstractmethod
    def get_by_entity(self, entity_id: str) -> List[Event]:
        """Retrieve all events for a specific entity."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Return total event count."""
        pass

    @abstractmethod
    def lock(self) -> threading.RLock:
        """Expose lock for atomic read operations."""
        pass
