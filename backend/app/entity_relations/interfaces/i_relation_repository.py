from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class IRelationRepository(ABC):
    """Repository contract for Relation persistence."""

    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        """Persist relation data."""
        pass

    @abstractmethod
    def get(self, relation_id: str | UUID) -> Optional[Dict[str, Any]]:
        """Retrieve relation by ID."""
        pass

    @abstractmethod
    def delete(self, relation_id: str | UUID) -> bool:
        """Remove relation by ID."""
        pass

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        """List all relations."""
        pass

    @abstractmethod
    def list_for_entity(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        """List relations involving a specific entity."""
        pass

    @abstractmethod
    def lock(self) -> threading.RLock:
        """Expose lock for atomic cycles."""
        pass
