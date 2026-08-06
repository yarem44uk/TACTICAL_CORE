from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional
from uuid import UUID

from .interfaces.i_repository import IRepository


class MemoryRepository(IRepository):
    """Thread-safe in-memory repository for testing and prototyping."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(str(entity_id))

    def save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._store[str(data["entity_id"])] = data

    def delete(self, entity_id: UUID | str) -> bool:
        with self._lock:
            key = str(entity_id)
            if key in self._store:
                del self._store[key]
                return True
            return False

    def list_all(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if entity_type is None:
                return list(self._store.values())
            return [
                v for v in self._store.values()
                if v.get("entity_type") == entity_type
            ]

    def lock(self) -> threading.RLock:
        """Expose lock for atomic read-modify-write cycles."""
        return self._lock
