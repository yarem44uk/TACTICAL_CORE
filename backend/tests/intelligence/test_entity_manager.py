"""Tests for EntityManager.

Verifies entity CRUD operations, lookup, registration,
resolution, and relationship management.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app.intelligence.entity.entity import Entity, EntityData
from app.intelligence.entity.entity_manager import EntityManager, EntityRepository
from app.intelligence.entity.relations import Relation
from app.intelligence.entity.types import (
    EntityType, 
    EntityStatus, 
    EntityRelationType,
    Priority,
)


# =============================================================================
# MOCK REPOSITORY
# =============================================================================

class MockEntityRepository(EntityRepository):
    """Mock repository for testing EntityManager."""

    def __init__(self):
        self._entities: Dict[UUID, Entity] = {}

    async def save(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Optional[Entity]:
        return self._entities.get(entity_id)

    async def delete(self, entity_id: UUID) -> bool:
        """Deprecated: Use mark_inactive() instead. Physical deletion forbidden."""
        entity = await self.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            await self.save(entity)
            return True
        return False

    async def mark_inactive(self, entity_id: UUID) -> Optional[Entity]:
        """Mark entity as inactive (constitutional lifecycle)."""
        entity = await self.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def archive(self, entity_id: UUID) -> Optional[Entity]:
        """Archive entity (constitutional lifecycle)."""
        entity = await self.get(entity_id)
        if entity:
            entity.status = EntityStatus.ARCHIVED
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def merge(self, source_id: UUID, target_id: UUID) -> Optional[Entity]:
        """Merge source into target (constitutional lifecycle)."""
        source = await self.get(source_id)
        if source:
            source.status = EntityStatus.MERGED
            source.metadata['merged_into'] = str(target_id)
            source.mark_updated()
            return await self.save(source)
        return None

    async def supersede(self, old_id: UUID, new_id: UUID) -> Optional[Entity]:
        """Mark entity as superseded (constitutional lifecycle)."""
        old_entity = await self.get(old_id)
        if old_entity:
            old_entity.status = EntityStatus.SUPERSEDED
            old_entity.metadata['superseded_by'] = str(new_id)
            old_entity.mark_updated()
            return await self.save(old_entity)
        return None

    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]
    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        return [e for e in self._entities.values() if e.status == status]

    async def find_by_tag(self, tag: str) -> List[Entity]:
        return [
            e for e in self._entities.values()
            if e.data and tag in e.data.tags
        ]

    async def find_by_callsign(self, callsign: str) -> Optional[Entity]:
        """Find entity by callsign."""
        for e in self._entities.values():
            if e.data and e.data.callsign == callsign:
                return e
        return None

    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search entities by text query (abstract method implementation).

        Args:
            query: Search query string.
            limit: Maximum number of results.

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




# =============================================================================
# ENTITY MANAGER TESTS
# =============================================================================

class TestEntityManagerCreation:
    """Tests for EntityManager creation."""

    def test_create_entity_manager(self):
        """Test creating an EntityManager with repository."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        assert manager is not None
        assert manager.repository is repository
        assert manager.identity_resolver is not None
        assert manager.relations is not None


class TestEntityManagerCreate:
    """Tests for EntityManager.create() method."""

    @pytest.mark.asyncio
    async def test_create_entity_minimal(self):
        """Test creating entity with minimal parameters."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, created = await manager.create(entity_type=EntityType.UNIT)

        assert entity is not None
        assert entity.entity_type == EntityType.UNIT
        assert entity.status == EntityStatus.UNKNOWN
        assert entity.id is not None

    @pytest.mark.asyncio
    async def test_create_entity_with_data(self):
        """Test creating entity with initial data."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)
        data = EntityData(callsign="ALPHA-1", name="Alpha Team")

        entity, created = await manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
            data=data,
            priority=Priority.HIGH,
        )

        assert entity.data is not None
        assert entity.data.callsign == "ALPHA-1"
        assert entity.source == "test"
        assert entity.priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_create_entity_persisted(self):
        """Test that created entity is persisted."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, created = await manager.create(entity_type=EntityType.VEHICLE)

        # Should be retrievable
        retrieved = await manager.get(entity.id)
        assert retrieved is not None
        assert retrieved.id == entity.id

    @pytest.mark.asyncio
    async def test_create_multiple_entities_unique_ids(self):
        """Test that multiple created entities have unique IDs."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity1, _ = await manager.create(entity_type=EntityType.UNIT)
        entity2, _ = await manager.create(entity_type=EntityType.UNIT)

        assert entity1.id != entity2.id


class TestEntityManagerGet:
    """Tests for EntityManager.get() method."""

    @pytest.mark.asyncio
    async def test_get_existing_entity(self):
        """Test getting an existing entity by ID."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, created = await manager.create(entity_type=EntityType.CONTACT)
        retrieved = await manager.get(entity.id)

        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.entity_type == EntityType.CONTACT

    @pytest.mark.asyncio
    async def test_get_non_existent_entity(self):
        """Test getting a non-existent entity returns None."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        result = await manager.get(uuid4())

        assert result is None


class TestEntityManagerUpdate:
    """Tests for EntityManager.update() method."""

    @pytest.mark.asyncio
    async def test_update_entity(self):
        """Test updating an entity."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, created = await manager.create(entity_type=EntityType.UNIT)
        original_updated = entity.updated_at

        entity.data = EntityData(callsign="UPDATED")
        updated = await manager.update(entity)

        assert updated.data.callsign == "UPDATED"
        assert updated.updated_at >= original_updated

    @pytest.mark.asyncio
    async def test_update_persisted(self):
        """Test that update is persisted."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, created = await manager.create(entity_type=EntityType.UNIT)
        entity.data = EntityData(status_text="Updated status")
        await manager.update(entity)

        retrieved = await manager.get(entity.id)
        assert retrieved.data.status_text == "Updated status"


class TestEntityManagerDelete:
    """Tests for EntityManager.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_existing_entity(self):
        """Test deleting an existing entity (constitutional lifecycle transition).

        Per ENTITY-001: Physical deletion is FORBIDDEN.
        delete() transitions entity to INACTIVE status.
        Entity remains retrievable with INACTIVE status.
        """
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        # Create entity
        entity, created = await manager.create(entity_type=EntityType.UNIT)
        assert created is True
        assert entity is not None

        # Delete transitions to INACTIVE
        result = await manager.delete(entity.id)
        assert result is True

        # Entity is still retrievable (constitutional requirement)
        retrieved = await manager.get(entity.id)
        assert retrieved is not None, "Entity must remain retrievable after delete"
        assert retrieved.status == EntityStatus.INACTIVE, f"Expected INACTIVE, got {retrieved.status}"

        # Entity data preserved
        assert retrieved.id == entity.id
        assert retrieved.entity_type == entity.entity_type

    @pytest.mark.asyncio
    async def test_delete_non_existent_entity(self):
        """Test deleting a non-existent entity returns False."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        result = await manager.delete(uuid4())

        assert result is False


class TestEntityManagerFind:
    """Tests for EntityManager.find_by_* methods."""

    @pytest.mark.asyncio
    async def test_find_by_type(self):
        """Test finding entities by type."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        _, _ = await manager.create(entity_type=EntityType.UNIT)
        _, _ = await manager.create(entity_type=EntityType.UNIT)
        _, _ = await manager.create(entity_type=EntityType.VEHICLE)

        units = await manager.find_by_type(EntityType.UNIT)

        assert len(units) == 2
        for unit in units:
            assert unit.entity_type == EntityType.UNIT

    @pytest.mark.asyncio
    async def test_find_by_status(self):
        """Test finding entities by status."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        active, _ = await manager.create(entity_type=EntityType.UNIT)
        active.status = EntityStatus.ACTIVE
        await manager.update(active)

        _, _ = await manager.create(entity_type=EntityType.UNIT)  # UNKNOWN

        active_list = await manager.find_by_status(EntityStatus.ACTIVE)

        assert len(active_list) >= 1
        for entity in active_list:
            assert entity.status == EntityStatus.ACTIVE


class TestEntityManagerRelations:
    """Tests for EntityManager.related entity methods."""

    @pytest.mark.asyncio
    async def test_relate_entities(self):
        """Test relating two entities."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity1, _ = await manager.create(entity_type=EntityType.UNIT)
        entity2, _ = await manager.create(entity_type=EntityType.VEHICLE)

        relation = await manager.relate(
            source_id=entity1.id,
            target_id=entity2.id,
            relation_type=EntityRelationType.PARENT,
        )

        assert relation is not None
        assert relation.source_id == entity1.id
        assert relation.target_id == entity2.id

    @pytest.mark.asyncio
    async def test_get_related_entities(self):
        """Test getting related entities."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity1, _ = await manager.create(entity_type=EntityType.UNIT)
        entity2, _ = await manager.create(entity_type=EntityType.VEHICLE)

        await manager.relate(entity1.id, entity2.id, EntityRelationType.PARENT)

        related = await manager.get_related(entity1.id)

        assert entity2 in related


class TestEntityManagerIdentity:
    """Tests for EntityManager identity resolution."""

    @pytest.mark.asyncio
    async def test_register_external_id(self):
        """Test registering an external ID for an entity."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, _ = await manager.create(entity_type=EntityType.CONTACT)

        await manager.register_external_id(
            entity_id=entity.id,
            source="tak",
            external_id="TAK-12345",
        )

        # Verify mapping exists
        mapping = manager.identity_resolver.get_mapping(entity.id)
        assert mapping is not None

    @pytest.mark.asyncio
    async def test_resolve_identity(self):
        """Test resolving entity by external ID."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        entity, _ = await manager.create(entity_type=EntityType.CONTACT)
        await manager.register_external_id(
            entity_id=entity.id,
            source="signal",
            external_id="SIG-001",
        )

        resolved_id = await manager.resolve_identity(
            source="signal",
            external_id="SIG-001",
        )

        assert resolved_id == entity.id


class TestEntityManagerSearch:
    """Tests for EntityManager.search() method."""

    @pytest.mark.asyncio
    async def test_search_entities(self):
        """Test searching entities."""
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        _, _ = await manager.create(entity_type=EntityType.UNIT, data=EntityData(callsign="ALPHA"))
        _, _ = await manager.create(entity_type=EntityType.UNIT, data=EntityData(callsign="BRAVO"))

        results = await manager.search(query="ALPHA")

        assert len(results) >= 1
        assert any(e.data.callsign == "ALPHA" for e in results)


class TestEntityManagerStats:
    """Tests for EntityManager.get_stats() method."""

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting entity statistics.

        Production API returns:
            {
                "identity": {...},
                "relations": {...}
            }
        """
        repository = MockEntityRepository()
        manager = EntityManager(repository=repository)

        # Create entities
        _, _ = await manager.create(entity_type=EntityType.UNIT)
        _, _ = await manager.create(entity_type=EntityType.CONTACT)

        stats = manager.get_stats()

        # Verify production API structure
        assert "identity" in stats, "Stats must contain 'identity' key"
        assert "relations" in stats, "Stats must contain 'relations' key"

        # Verify identity stats structure
        identity_stats = stats["identity"]
        # Note: nested keys vary by implementation, only check stable top-level keys
        assert "total_entities" in identity_stats or "total_external_ids" in identity_stats

        # Verify relations stats structure  
        relations_stats = stats["relations"]
        assert "total_relations" in relations_stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
