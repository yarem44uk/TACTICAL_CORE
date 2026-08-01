"""Integration Test: Entity/Identity Persistence

Tests the Entity/Identity subsystem that was verified in WO-008-008.
This ensures the Entity subsystem works correctly as a standalone
component.

Author: WO-008-009 Implementation
Version: 1.0

BASELINE: WO-008-008 APPROVED
"""

import pytest
from typing import Dict, List, Optional
from uuid import UUID

from app.intelligence.entity import (
    Entity,
    EntityData,
    EntityType,
    EntityStatus,
    EntityManager,
    EntityRelationType,
    Priority,
)
from app.intelligence.entity.entity_manager import EntityRepository


class MockEntityRepository(EntityRepository):
    """Mock repository implementing EntityRepository ABC."""

    def __init__(self):
        self._entities: Dict[UUID, Entity] = {}

    async def save(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Entity:
        return self._entities.get(entity_id)

    async def delete(self, entity_id: UUID) -> bool:
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            await self.save(entity)
            return True
        return False

    async def mark_inactive(self, entity_id: UUID) -> Entity:
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def archive(self, entity_id: UUID) -> Entity:
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.ARCHIVED
            entity.mark_updated()
            return await self.save(entity)
        return None

    async def merge(self, source_id: UUID, target_id: UUID) -> Entity:
        source = self._entities.get(source_id)
        if source:
            source.status = EntityStatus.MERGED
            source.mark_updated()
            return await self.save(source)
        return None

    async def supersede(self, old_id: UUID, new_id: UUID) -> Entity:
        old_entity = self._entities.get(old_id)
        if old_entity:
            old_entity.status = EntityStatus.SUPERSEDED
            old_entity.mark_updated()
            return await self.save(old_entity)
        return None

    async def find_by_type(self, entity_type: EntityType) -> List[Entity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    async def find_by_status(self, status: EntityStatus) -> List[Entity]:
        return [e for e in self._entities.values() if e.status == status]

    async def find_by_tag(self, tag: str) -> List[Entity]:
        return [e for e in self._entities.values() if e.data and tag in e.data.tags]

    async def resolve_by_identity(self, source: str, external_id: str) -> Optional[UUID]:
        """Resolve entity by external identity."""
        for entity in self._entities.values():
            if entity.external_ids:
                for src, ids in entity.external_ids.items():
                    if src == source and external_id in ids:
                        return entity.id
        return None

    async def find_by_callsign(self, callsign: str) -> Entity:
        for e in self._entities.values():
            if e.data and e.data.callsign == callsign:
                return e
        return None

    async def search(self, query: str, limit: int = 100) -> List[Entity]:
        """Search with R6-N1 (limit) and R6-N2 (guard) fixes."""
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


class TestEntityCreation:
    """Test entity creation flows."""

    @pytest.mark.asyncio
    async def test_entity_create_returns_unknown_status(self):
        """Test that Entity.create() returns UNKNOWN status (CV3)."""
        entity = Entity.create(
            entity_type=EntityType.CONTACT,
            source="test-source",
        )
        assert entity.status == EntityStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_entity_create_preserves_confidence(self):
        """Test that confidence is preserved (CV4)."""
        entity = Entity.create(
            entity_type=EntityType.UNIT,
            source="test",
            confidence=0.75,
        )
        assert entity.confidence == 0.75

    @pytest.mark.asyncio
    async def test_manager_create_returns_tuple(self):
        """Test EntityManager.create() returns tuple[Entity, bool]."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity, created = await manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
        )
        assert created is True
        assert entity is not None
        assert entity.id is not None


class TestIdentityResolution:
    """Test identity resolution (CV1 - Identity-First)."""

    @pytest.mark.asyncio
    async def test_resolve_or_create_new_identity(self):
        """Test resolve_or_create with new identity returns created=True."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="EXT-001",
        )
        assert created is True
        assert entity.status == EntityStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_resolve_or_create_existing_identity(self):
        """Test resolve_or_create with existing identity returns created=False."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        # First call
        entity1, created1 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="EXT-001",
        )
        assert created1 is True

        # Second call with same identity
        entity2, created2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="EXT-001",
        )
        assert created2 is False
        assert entity2.id == entity1.id  # Same entity


class TestLifecycleTransitions:
    """Test lifecycle transitions (CV2 - No Physical Delete)."""

    @pytest.mark.asyncio
    async def test_delete_preserves_entity(self):
        """Test delete() transitions to INACTIVE, not physical delete."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity, _ = await manager.create(
            entity_type=EntityType.UNIT,
            source="test",
        )
        entity_id = entity.id

        # Delete
        result = await manager.delete(entity_id)
        assert result is True

        # Entity should still be retrievable (lifecycle, not physical)
        retrieved = await manager.get(entity_id)
        assert retrieved is not None
        assert retrieved.status == EntityStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_archive_preserves_entity(self):
        """Test archive() transitions to ARCHIVED, not physical delete."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity, _ = await manager.create(
            entity_type=EntityType.UNIT,
            source="test",
        )

        result = await repo.archive(entity.id)
        assert result is not None
        assert result.status == EntityStatus.ARCHIVED

        # Entity still retrievable
        retrieved = await repo.get(entity.id)
        assert retrieved is not None


class TestRelations:
    """Test entity relations."""

    @pytest.mark.asyncio
    async def test_relate_creates_relation(self):
        """Test relating two entities."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity1, _ = await manager.create(entity_type=EntityType.UNIT, source="parent")
        entity2, _ = await manager.create(entity_type=EntityType.UNIT, source="child")

        await manager.relate(entity1.id, entity2.id, EntityRelationType.PARENT)

        related = await manager.get_related(entity1.id)
        assert entity2 in related

    @pytest.mark.asyncio
    async def test_get_related_returns_entity_list(self):
        """Test get_related() returns List[Entity]."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        entity1, _ = await manager.create(entity_type=EntityType.UNIT, source="main")
        entity2, _ = await manager.create(entity_type=EntityType.UNIT, source="related")

        await manager.relate(entity1.id, entity2.id, EntityRelationType.PEER)

        related = await manager.get_related(entity1.id)
        assert isinstance(related, list)
        assert entity2 in related


class TestSearch:
    """Test search functionality (R6-N1 fix)."""

    @pytest.mark.asyncio
    async def test_search_returns_list(self):
        """Test search() returns List[Entity]."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        await manager.create(entity_type=EntityType.UNIT, source="alpha-unit")
        await manager.create(entity_type=EntityType.UNIT, source="beta-unit")

        results = await manager.search("alpha")
        assert isinstance(results, list)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_honors_limit(self):
        """Test search() honors limit parameter."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        for i in range(5):
            await manager.create(entity_type=EntityType.UNIT, source=f"unit-{i}")

        results = await manager.search("unit", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_handles_none_data(self):
        """Test search() handles entities with None data (R6-N2)."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        # Entity without data
        entity, _ = await manager.create(entity_type=EntityType.CONTACT, source="no-data")

        # Should not crash
        results = await manager.search("no-data")
        assert isinstance(results, list)


class TestSerialization:
    """Test entity serialization."""

    @pytest.mark.asyncio
    async def test_entity_serialization_round_trip(self):
        """Test Entity.to_dict() / Entity.from_dict()."""
        original = Entity.create(
            entity_type=EntityType.CONTACT,
            source="test",
            data=EntityData(callsign="GAMMA"),
            confidence=0.85,
        )

        serialized = original.to_dict()
        restored = Entity.from_dict(serialized)

        assert restored.id == original.id
        assert restored.entity_type == original.entity_type
        assert restored.status == original.status
        assert restored.confidence == original.confidence


class TestStats:
    """Test statistics gathering."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_structure(self):
        """Test get_stats() returns expected structure."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        await manager.create(entity_type=EntityType.UNIT, source="unit-1")
        await manager.create(entity_type=EntityType.CONTACT, source="contact-1")

        stats = manager.get_stats()
        assert "total_relations" in stats
        assert "by_type" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
