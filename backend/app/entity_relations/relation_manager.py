from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional
from uuid import UUID

from .relation import Relation
from .interfaces.i_relation_manager import IRelationManager
from .interfaces.i_relation_repository import IRelationRepository

logger = logging.getLogger(__name__)

SUPPORTED_RELATIONS = {
    "owns", "controls", "belongs_to", "connected_to",
    "parent", "child", "located_at", "identified_as", "communicates_with",
}


class RelationManager(IRelationManager):
    """Production-ready RelationManager implementing IRelationManager."""

    def __init__(self, repository: IRelationRepository | None = None) -> None:
        from .memory_relation_repository import MemoryRelationRepository
        self._repository: IRelationRepository = repository or MemoryRelationRepository()
        self._lock = threading.RLock()

    def create_relation(
        self,
        source_entity_id: str | UUID,
        target_entity_id: str | UUID,
        relation_type: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if relation_type not in SUPPORTED_RELATIONS:
            raise ValueError(f"Unsupported relation type: {relation_type}")

        with self._lock:
            # Duplicate check
            existing = self._repository.list_for_entity(source_entity_id)
            for r in existing:
                if r["target_entity_id"] == str(target_entity_id) and r["relation_type"] == relation_type:
                    raise ValueError("Duplicate relation already exists.")

            rel = Relation(
                source_entity_id=str(source_entity_id),
                target_entity_id=str(target_entity_id),
                relation_type=relation_type,
                confidence=confidence,
                metadata=metadata or {},
            )
            self._repository.save(rel.__dict__)
            logger.info("Relation created: %s", rel.relation_id)
            return rel.relation_id

    def remove_relation(self, relation_id: str | UUID) -> bool:
        return self._repository.delete(relation_id)

    def get_relations(self, relation_id: str | UUID) -> Optional[Dict[str, Any]]:
        return self._repository.get(relation_id)

    def get_outgoing(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        eid = str(entity_id)
        return [r for r in self._repository.list_for_entity(eid) if r["source_entity_id"] == eid]

    def get_incoming(self, entity_id: str | UUID) -> List[Dict[str, Any]]:
        eid = str(entity_id)
        return [r for r in self._repository.list_for_entity(eid) if r["target_entity_id"] == eid]
