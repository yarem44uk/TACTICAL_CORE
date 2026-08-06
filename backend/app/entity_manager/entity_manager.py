from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from .entity import Entity
from .interfaces.i_entity_manager import IEntityManager
from .interfaces.i_repository import IRepository

logger = logging.getLogger(__name__)


class EntityManager(IEntityManager):
    """Production-ready EntityManager implementing IEntityManager."""

    def __init__(self, repository: IRepository | None = None) -> None:
        from .memory_repository import MemoryRepository
        self._repository = repository or MemoryRepository()

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
        # Accept both 'payload' and 'updates' for EntityBridge compatibility.
        effective_payload = payload if payload is not None else (updates or {})
        effective_metadata = metadata or {}

        lock = self._repository.lock()
        with lock:
            existing = self._repository.get(entity_id)
            now = datetime.now(timezone.utc)

            if existing:
                existing["attributes"].update(effective_payload)
                existing["metadata"].update(effective_metadata)
                existing["updated_at"] = now.isoformat()
                existing["version"] = existing.get("version", 1) + 1
                self._repository.save(existing)
                logger.info(
                    "Entity updated: type=%s id=%s version=%s corr=%s",
                    entity_type, entity_id, existing["version"], correlation_id,
                )
            else:
                new_entity = Entity(
                    entity_id=str(entity_id),
                    entity_type=entity_type,
                    attributes=effective_payload,
                    metadata=effective_metadata,
                )
                self._repository.save(new_entity.to_dict())
                logger.info(
                    "Entity created: type=%s id=%s corr=%s",
                    entity_type, entity_id, correlation_id,
                )
        return True

    def get_entity(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> Optional[Dict[str, Any]]:
        data = self._repository.get(entity_id)
        if data and data.get("entity_type") == entity_type:
            return data
        return None

    def list_entities(
        self,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self._repository.list_all(entity_type)

    def delete_entity(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> bool:
        return self._repository.delete(entity_id)
