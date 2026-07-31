"""Entity Manager and Repository implementations.

This module provides the Entity management system including:
- EntityRepository: Abstract base for Entity persistence
- InMemoryEntityRepository: In-memory implementation
- SQLAlchemyEntityRepository: SQLAlchemy/SQLite implementation
- EntityManager: High-level Entity operations with identity resolution

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from app.intelligence.entity.entity import Entity, EntityData
from app.intelligence.entity.types import (
    EntityType,
    EntityStatus,
    EntityRelationType,
    Priority,
)
from app.intelligence.entity.relations import EntityRelations

logger = logging.getLogger(__name__)


class EntityRepository(ABC):
    """Abstract base class for Entity repositories.

    Defines the contract for Entity persistence and retrieval.
    All repository implementations must inherit from this class.
    """

    @abstractmethod
    async def save(self, entity: Entity) -> Entity:
        """Save or update an entity.

        Args:
            entity: Entity to save.

        Returns:
            Saved entity.
        """
        pass

    @abstractmethod
    async def get(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Entity UUID.

        Returns:
            Entity if found, None otherwise.
        """
        pass

    @abstractmethod
    async def delete(self, entity_id: UUID) -> bool:
        """Soft delete an entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    async def mark_inactive(self, entity_id: UUID) -> Optional[Entity]:
        """Mark entity as inactive (lifecycle).

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        pass

    @abstractmethod
    async def archive(self, entity_id: UUID) -> Optional[Entity]:
        """Archive an entity (lifecycle).

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        pass

    @abstractmethod
    async def merge(self, source_id: UUID, target_id: UUID) -> Optional[Entity]:
        """Merge source entity into target.

        Args:
            source_id: Source entity UUID.
            target_id: Target entity UUID.

        Returns:
            Updated target entity or None.
        """
        pass

    @abstractmethod
    async def supersede(self, old_id: UUID, new_id: UUID) -> Optional[Entity]:
        """Mark old entity as superseded by new.

        Args:
            old_id: Old entity UUID.
            new_id: New entity UUID.

        Returns:
            Updated old entity or None.
        """
        pass

    @abstractmethod
    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Find entities by type.

        Args:
            entity_type: Entity type to filter.

        Returns:
            List of matching entities.
        """
        pass

    @abstractmethod
    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        """Find entities by status.

        Args:
            status: Entity status to filter.

        Returns:
            List of matching entities.
        """
        pass

    @abstractmethod
    async def find_by_tag(self, tag: str) -> List[Entity]:
        """Find entities by tag.

        Args:
            tag: Tag to filter.

        Returns:
            List of matching entities.
        """
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search entities by query.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching entities.
        """
        pass

    async def resolve_by_identity(
        self, source: str, external_id: str
    ) -> Optional[UUID]:
        """Resolve entity ID by external identity.

        This method is called by EntityManager.resolve_or_create() to
        implement identity-first resolution. Repository implementations
        must persist identity mappings and return them here.

        Args:
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Entity UUID if found, None otherwise.
        """
        # Default implementation returns None - override in subclasses
        return None


class InMemoryEntityRepository(EntityRepository):
    """In-memory Entity Repository.

    Stores entities in memory. For testing and development.
    """

    def __init__(self) -> None:
        """Initialize the in-memory repository."""
        self._entities: Dict[str, Entity] = {}
        self._identities: Dict[tuple[str, str], UUID] = {}

    async def resolve_by_identity(
        self, source: str, external_id: str
    ) -> Optional[UUID]:
        """Resolve entity ID by external identity.

        Args:
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Entity UUID if found, None otherwise.
        """
        return self._identities.get((source, external_id))

    async def save(self, entity: Entity) -> Entity:
        """Save entity to memory.

        Args:
            entity: Entity to save.

        Returns:
            Saved entity.
        """
        self._entities[str(entity.id)] = entity
        # Store identity mappings
        for source, ext_id in entity.external_ids.items():
            self._identities[(source, ext_id)] = entity.id
        return entity

    async def get(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Entity UUID.

        Returns:
            Entity if found, None otherwise.
        """
        return self._entities.get(str(entity_id))

    async def delete(self, entity_id: UUID) -> bool:
        """Soft delete entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            True if deleted, False if not found.
        """
        entity = self._entities.get(str(entity_id))
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            await self.save(entity)
            return True
        return False

    async def mark_inactive(self, entity_id: UUID) -> Optional[Entity]:
        """Mark entity as inactive.

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        entity = self._entities.get(str(entity_id))
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def archive(self, entity_id: UUID) -> Optional[Entity]:
        """Archive entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        entity = self._entities.get(str(entity_id))
        if entity:
            entity.status = EntityStatus.ARCHIVED
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def merge(self, source_id: UUID, target_id: UUID) -> Optional[Entity]:
        """Merge source into target.

        Args:
            source_id: Source entity UUID.
            target_id: Target entity UUID.

        Returns:
            Updated target entity or None.
        """
        source = self._entities.get(str(source_id))
        target = self._entities.get(str(target_id))
        if source and target:
            source.status = EntityStatus.MERGED
            source.mark_updated()
            await self.save(source)
            return target
        return None

    async def supersede(self, old_id: UUID, new_id: UUID) -> Optional[Entity]:
        """Mark old as superseded.

        Args:
            old_id: Old entity UUID.
            new_id: New entity UUID.

        Returns:
            Updated old entity or None.
        """
        old = self._entities.get(str(old_id))
        if old:
            old.status = EntityStatus.SUPERSEDED
            old.mark_updated()
            return await self.save(old)
        return None

    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Find entities by type.

        Args:
            entity_type: Entity type to filter.

        Returns:
            List of matching entities.
        """
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        """Find entities by status.

        Args:
            status: Entity status to filter.

        Returns:
            List of matching entities.
        """
        return [e for e in self._entities.values() if e.status == status]

    async def find_by_tag(self, tag: str) -> List[Entity]:
        """Find entities by tag.

        Args:
            tag: Tag to filter.

        Returns:
            List of matching entities.
        """
        return [
            e for e in self._entities.values()
            if e.data and tag in e.data.tags
        ]

    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search entities by query.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching entities.
        """
        query_lower = query.lower()
        results = []
        for entity in self._entities.values():
            searchable = [entity.source]
            if entity.data and entity.data.callsign:
                searchable.append(entity.data.callsign)
            if any(query_lower in str(s).lower() for s in searchable):
                results.append(entity)
                if len(results) >= limit:
                    break
        return results[:limit]


class SQLAlchemyEntityRepository(EntityRepository):
    """SQLAlchemy-backed Entity Repository.

    Persists Entity dataclasses to SQLite using JSON serialization.
    """

    def __init__(self, session) -> None:
        from sqlalchemy import text
        self._session = session
        self._ensure_table()

    def _ensure_table(self) -> None:
        from sqlalchemy import text
        try:
            self._session.execute(text("SELECT 1 FROM entity_store LIMIT 1"))
        except Exception:
            self._session.execute(text("""
                CREATE TABLE IF NOT EXISTS entity_store (
                    entity_id TEXT PRIMARY KEY,
                    entity_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """))
            self._session.commit()

    async def save(self, entity: Entity) -> Entity:
        """Save entity to database.

        Args:
            entity: Entity to save.

        Returns:
            Saved entity.
        """
        import json
        from datetime import datetime
        from sqlalchemy import text

        entity_id = str(entity.id)
        entity_data = json.dumps(entity.to_dict())
        now = datetime.now().isoformat()

        self._session.execute(
            text("""
                INSERT OR REPLACE INTO entity_store 
                (entity_id, entity_data, updated_at, is_deleted)
                VALUES (:entity_id, :entity_data, :updated_at, FALSE)
            """),
            {"entity_id": entity_id, "entity_data": entity_data, "updated_at": now}
        )
        self._session.commit()
        entity.mark_updated()
        return entity

    async def resolve_by_identity(
        self, source: str, external_id: str
    ) -> Optional[UUID]:
        """Resolve entity ID by external identity from persisted state.

        Scans persisted entities to find matching (source, external_id) tuple.
        This is called by EntityManager.resolve_or_create() for identity-first
        resolution across process restarts.

        Args:
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Entity UUID if found, None otherwise.
        """
        import json
        from sqlalchemy import text

        # Query all non-deleted entities
        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE is_deleted = FALSE")
        )
        rows = result.fetchall()

        for row in rows:
            try:
                entity_data = json.loads(row[0])
                external_ids = entity_data.get('external_ids', {})

                # Check if this entity has the requested identity
                if source in external_ids:
                    stored_external_id = external_ids[source]
                    if stored_external_id == external_id:
                        # Found matching identity
                        entity_uuid = entity_data.get('id')
                        if entity_uuid:
                            return UUID(entity_uuid)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip malformed entities
                continue

        return None

    async def get(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Entity UUID.

        Returns:
            Entity if found, None otherwise.
        """
        import json
        from sqlalchemy import text

        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE entity_id = :id AND is_deleted = FALSE"),
            {"id": str(entity_id)}
        )
        row = result.fetchone()
        if row:
            return Entity.from_dict(json.loads(row[0]))
        return None

    async def delete(self, entity_id: UUID) -> bool:
        """CV2 - Soft delete: transition to INACTIVE, preserve Entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            True if deleted, False if not found.
        """
        from sqlalchemy import text

        # Get the entity
        entity = await self.get(entity_id)
        if entity:
            # Soft delete: mark as INACTIVE (lifecycle transition)
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            await self.save(entity)

            return True
        return False

    async def mark_inactive(self, entity_id: UUID) -> Optional[Entity]:
        """Mark entity as inactive.

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        entity = await self.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def archive(self, entity_id: UUID) -> Optional[Entity]:
        """Archive entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            Updated entity or None if not found.
        """
        entity = await self.get(entity_id)
        if entity:
            entity.status = EntityStatus.ARCHIVED
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def merge(self, source_id: UUID, target_id: UUID) -> Optional[Entity]:
        """Merge source into target.

        Args:
            source_id: Source entity UUID.
            target_id: Target entity UUID.

        Returns:
            Updated target entity or None.
        """
        source = await self.get(source_id)
        target = await self.get(target_id)
        if source and target:
            source.status = EntityStatus.MERGED
            source.mark_updated()
            await self.save(source)
            return target
        return None

    async def supersede(self, old_id: UUID, new_id: UUID) -> Optional[Entity]:
        """Mark old as superseded.

        Args:
            old_id: Old entity UUID.
            new_id: New entity UUID.

        Returns:
            Updated old entity or None.
        """
        old = await self.get(old_id)
        if old:
            old.status = EntityStatus.SUPERSEDED
            old.mark_updated()
            return await self.save(old)
        return None

    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Find entities by type.

        Args:
            entity_type: Entity type to filter.

        Returns:
            List of matching entities.
        """
        import json
        from sqlalchemy import text

        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE is_deleted = FALSE")
        )
        entities = []
        for row in result.fetchall():
            try:
                entity = Entity.from_dict(json.loads(row[0]))
                if entity.entity_type == entity_type:
                    entities.append(entity)
            except (json.JSONDecodeError, KeyError):
                continue
        return entities

    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        """Find entities by status.

        Args:
            status: Entity status to filter.

        Returns:
            List of matching entities.
        """
        import json
        from sqlalchemy import text

        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE is_deleted = FALSE")
        )
        entities = []
        for row in result.fetchall():
            try:
                entity = Entity.from_dict(json.loads(row[0]))
                if entity.status == status:
                    entities.append(entity)
            except (json.JSONDecodeError, KeyError):
                continue
        return entities

    async def find_by_tag(self, tag: str) -> List[Entity]:
        """Find entities by tag.

        Args:
            tag: Tag to filter.

        Returns:
            List of matching entities.
        """
        import json
        from sqlalchemy import text

        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE is_deleted = FALSE")
        )
        entities = []
        for row in result.fetchall():
            try:
                entity = Entity.from_dict(json.loads(row[0]))
                if entity.data and tag in entity.data.tags:
                    entities.append(entity)
            except (json.JSONDecodeError, KeyError):
                continue
        return entities

    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search entities by query.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching entities.
        """
        import json
        from sqlalchemy import text

        result = self._session.execute(
            text("SELECT entity_data FROM entity_store WHERE is_deleted = FALSE LIMIT :limit"),
            {"limit": limit}
        )
        query_lower = query.lower()
        entities = []
        for row in result.fetchall():
            try:
                entity = Entity.from_dict(json.loads(row[0]))
                searchable = [entity.source]
                if entity.data and entity.data.callsign:
                    searchable.append(entity.data.callsign)
                if any(query_lower in str(s).lower() for s in searchable):
                    entities.append(entity)
            except (json.JSONDecodeError, KeyError):
                continue
        return entities


class EntityManager:
    """High-level Entity operations with identity resolution.

    This manager provides the canonical API for Entity operations
    and implements identity-first resolution (CV1).
    """

    def __init__(self, repository: Optional[EntityRepository] = None) -> None:
        """Initialize EntityManager.

        Args:
            repository: Repository for persistence. Creates InMemory if None.
        """
        self._repository = repository or InMemoryEntityRepository()
        self._relations = EntityRelations()

    async def create(
        self,
        entity_type: EntityType,
        source: str = "",
        external_id: Optional[str] = None,
        data: Optional[EntityData] = None,
        priority: Priority = Priority.MEDIUM,
        confidence: float = 0.0,
    ) -> tuple[Entity, bool]:
        """Create a new entity with optional external identity.

        If external_id is provided, delegates to resolve_or_create()
        for identity-first resolution.

        Args:
            entity_type: Type of entity.
            source: Source system identifier.
            external_id: Optional external identity.
            data: Initial entity data.
            priority: Entity priority.
            confidence: Initial confidence level.

        Returns:
            Tuple of (entity, created) where created is True for new entities.
        """
        if external_id:
            return await self.resolve_or_create(
                entity_type=entity_type,
                source=source,
                external_id=external_id,
                data=data,
                priority=priority,
                confidence=confidence,
            )

        entity = Entity.create(
            entity_type=entity_type,
            source=source,
            data=data,
            priority=priority,
            confidence=confidence,
        )
        await self._repository.save(entity)
        return entity, True

    async def resolve_or_create(
        self,
        entity_type: EntityType,
        source: str,
        external_id: str,
        data: Optional[EntityData] = None,
        priority: Priority = Priority.MEDIUM,
        confidence: float = 0.0,
    ) -> tuple[Entity, bool]:
        """CV1 - Identity First: Resolve external identity or create new entity.

        This method implements identity-first resolution:
        1. Check repository for existing identity mapping
        2. If found, return existing entity
        3. If not found, create new entity and register identity

        Args:
            entity_type: Type of entity.
            source: Source system identifier.
            external_id: External identity to resolve.
            data: Initial entity data.
            priority: Entity priority.
            confidence: Initial confidence level.

        Returns:
            Tuple of (entity, created) where created is False for existing entities.
        """
        # Try repository identity lookup first (persistent)
        existing_id = await self._repository.resolve_by_identity(source, external_id)
        if existing_id:
            entity = await self._repository.get(existing_id)
            if entity:
                return entity, False

        entity = Entity.create(
            entity_type=entity_type,
            source=source,
            data=data,
            priority=priority,
            confidence=confidence,
        )
        entity.external_ids[source] = external_id
        await self._repository.save(entity)
        return entity, True

    async def get(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Entity UUID.

        Returns:
            Entity if found, None otherwise.
        """
        return await self._repository.get(entity_id)

    async def update(self, entity: Entity) -> Entity:
        """Update entity.

        Args:
            entity: Entity to update.

        Returns:
            Updated entity.
        """
        return await self._repository.save(entity)

    async def delete(self, entity_id: UUID) -> bool:
        """CV2 - Soft delete: transition to INACTIVE, preserve Entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            True if deleted, False if not found.
        """
        return await self._repository.delete(entity_id)

    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Find entities by type.

        Args:
            entity_type: Entity type to filter.

        Returns:
            List of matching entities.
        """
        return await self._repository.find_by_type(entity_type)

    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        """Find entities by status.

        Args:
            status: Entity status to filter.

        Returns:
            List of matching entities.
        """
        return await self._repository.find_by_status(status)

    async def find_by_tag(self, tag: str) -> List[Entity]:
        """Find entities by tag.

        Args:
            tag: Tag to filter.

        Returns:
            List of matching entities.
        """
        return await self._repository.find_by_tag(tag)

    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search entities by query.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching entities.
        """
        return await self._repository.search(query, limit)

    async def relate(
        self,
        source_id: UUID,
        target_id: UUID,
        relation_type: EntityRelationType,
    ) -> bool:
        """Create a relation between entities.

        Args:
            source_id: Source entity UUID.
            target_id: Target entity UUID.
            relation_type: Type of relationship.

        Returns:
            True if relation created, False otherwise.
        """
        source = await self.get(source_id)
        target = await self.get(target_id)

        if source is None or target is None:
            logger.warning(f"Cannot relate: entity not found")
            return False

        self._relations.relate(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
        )

        return True

    async def get_related(self, entity_id: UUID) -> List[Entity]:
        """Get entities related to an entity.

        Args:
            entity_id: Entity UUID.

        Returns:
            List of related entities.
        """
        related_ids = self._relations.get_related(entity_id)

        related_entities = []
        for related_id in related_ids:
            entity = await self.get(related_id)
            if entity is not None:
                related_entities.append(entity)

        return related_entities

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics.

        Returns:
            Statistics dictionary.
        """
        return self._relations.get_stats()
