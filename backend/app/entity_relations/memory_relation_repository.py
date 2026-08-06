from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional
from uuid import UUID

from .interfaces.i_relation_repository import IRelationRepository


class MemoryRelationRepository(IRelationRepository):
    """Thread-safe in-memory repository for relations."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._store[str(data["relation_id"])] = data

    def get(self, relation_id: str | UUID) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(str(relation_id))

    def delete(self, relation_id: str | UUID) -> bool:
        with self._lock:
            key = str(relation_id)
            if key in self._store:
                del self._store[key]
                return True
            return False

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._store.values())

    def list_for_entity(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        with self._lock:
            eid = str(entity_id)
            return [v for v in self._store.values() if v["source_entity_id"] == eid or v["target_entity_id"] == eid]

    def lock(self) -> threading.RLock:
        return self._lock
