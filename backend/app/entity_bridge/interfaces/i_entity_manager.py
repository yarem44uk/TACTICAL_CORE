"""
IEntityManager Interface.

Defines the contract that any Entity Manager implementation must fulfill.
EntityBridge interacts exclusively through this interface — no concrete
implementations are referenced.

Author: Tactical Core Engineering Team
Version: 1.0
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import UUID


class IEntityManager(ABC):
    """
    Contract for entity state management.

    Provides methods to apply updates derived from incoming events
    to the internal entity graph.  Implementations may back this onto
    any persistence layer (in-memory, database, cache, etc.).

    EntityBridge MUST never import a concrete EntityManager class.
    """

    @abstractmethod
    def apply_update(
        self,
        entity_type: str,
        entity_id: UUID | str,
        updates: Dict[str, Any],
        source_event_id: UUID | str | None = None,
    ) -> bool:
        """
        Apply a partial update to an existing entity.

        Args:
            entity_type: Domain type of the entity (e.g. ``"person"``,
                         ``"location"``, ``"event"``).
            entity_id: Stable identifier of the entity.
            updates: Key-value pairs to merge into the entity record.
            source_event_id: Optional correlation back to the originating
                             pipeline event.

        Returns:
            ``True`` if the update was applied, ``False`` otherwise.
        """
        ...

    @abstractmethod
    def get_entity(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current state of an entity.

        Args:
            entity_type: Domain type of the entity.
            entity_id: Stable identifier of the entity.

        Returns:
            Entity state as a dict, or ``None`` if not found.
        """
        ...
