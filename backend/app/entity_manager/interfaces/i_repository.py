from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class IRepository(ABC):
    """Repository contract for Entity persistence."""

    @abstractmethod
    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete(self, entity_id: UUID | str) -> bool:
        pass

    @abstractmethod
    def list_all(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def lock(self) -> threading.RLock:
        """Expose lock for atomic read-modify-write cycles."""
        pass
