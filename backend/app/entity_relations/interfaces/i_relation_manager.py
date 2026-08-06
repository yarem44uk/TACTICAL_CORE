from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class IRelationManager(ABC):
    """Core contract for Relation lifecycle management."""

    @abstractmethod
    def create_relation(
        self,
        source_entity_id: str | UUID,
        target_entity_id: str | UUID,
        relation_type: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new relation, returning its ID."""
        pass

    @abstractmethod
    def remove_relation(self, relation_id: str | UUID) -> bool:
        """Remove a relation by ID."""
        pass

    @abstractmethod
    def get_relations(self, relation_id: str | UUID) -> Optional[Dict[str, Any]]:
        """Retrieve relation by ID."""
        pass

    @abstractmethod
    def get_outgoing(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        """Retrieve relations where entity is source."""
        pass

    @abstractmethod
    def get_incoming(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        """Retrieve relations where entity is target."""
        pass
