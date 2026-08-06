from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class ISQLRepository(ABC):
    """Interface for SQL-backed Entity Repository."""

    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        """Save or upsert an entity."""

    @abstractmethod
    def update(self, entity_id: UUID | str, updates: Dict[str, Any]) -> bool:
        """Update attributes of an existing entity."""

    @abstractmethod
    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        """Retrieve an entity by ID."""

    @abstractmethod
    def delete(self, entity_id: UUID | str) -> bool:
        """Soft delete an entity (alias for soft_delete)."""

    @abstractmethod
    def hard_delete(self, entity_id: UUID | str) -> bool:
        """Permanently remove an entity."""

    @abstractmethod
    def soft_delete(self, entity_id: UUID | str) -> bool:
        """Mark entity as deleted without removing it."""

    @abstractmethod
    def list(self) -> List[Dict[str, Any]]:
        """List all non-deleted entities."""

    @abstractmethod
    def list_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        """List non-deleted entities by type."""

    @abstractmethod
    def list_deleted(self) -> List[Dict[str, Any]]:
        """List soft-deleted entities."""

    @abstractmethod
    def close(self) -> None:
        """Release database connection."""
