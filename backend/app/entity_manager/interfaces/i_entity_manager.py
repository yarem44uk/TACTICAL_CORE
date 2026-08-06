from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class IEntityManager(ABC):
    """Core contract for Entity lifecycle management."""

    @abstractmethod
    def apply_update(
        self,
        entity_type: str,
        entity_id: UUID | str,
        payload: Dict[str, Any] | None = None,
        updates: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
        correlation_id: str | None = None,
        source_event_id: UUID | str | None = None,
    ) -> bool:
        pass

    @abstractmethod
    def get_entity(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_entities(
        self,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_entity(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> bool:
        pass
