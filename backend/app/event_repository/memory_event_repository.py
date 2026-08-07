import threading
from typing import Dict, List, Optional

from app.event.event import Event
from app.event_repository.interfaces.i_event_repository import IEventRepository


class MemoryEventRepository(IEventRepository):
    """Thread-safe in-memory implementation of IEventRepository."""

    def __init__(self) -> None:
        self._store: Dict[str, Event] = {}
        self._lock = threading.RLock()

    def save(self, event: Event) -> None:
        with self._lock:
            self._store[event.event_id] = event

    def get(self, event_id: str) -> Optional[Event]:
        with self._lock:
            return self._store.get(event_id)

    def exists(self, event_id: str) -> bool:
        with self._lock:
            return event_id in self._store

    def delete(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._store:
                del self._store[event_id]
                return True
            return False

    def list_all(self) -> List[Event]:
        with self._lock:
            return list(self._store.values())

    def list_by_type(self, event_type: str) -> List[Event]:
        with self._lock:
            return [e for e in self._store.values() if e.event_type == event_type]

    def list_by_source(self, source: str) -> List[Event]:
        with self._lock:
            return [e for e in self._store.values() if e.source == source]

    def list_by_correlation(self, correlation_id: str) -> List[Event]:
        with self._lock:
            return [
                e
                for e in self._store.values()
                if e.metadata.correlation_id == correlation_id
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._store)
