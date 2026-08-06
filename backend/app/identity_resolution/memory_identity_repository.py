from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional
from .interfaces.i_identity_repository import IIdentityRepository

class MemoryIdentityRepository(IIdentityRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def get(self, identity_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(identity_key)

    def save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            key = data.get("identity_key")
            if key:
                self._store[key] = data

    def delete(self, identity_key: str) -> bool:
        with self._lock:
            if identity_key in self._store:
                del self._store[identity_key]
                return True
            return False

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._store.values())

    def lock(self) -> threading.RLock:
        return self._lock
