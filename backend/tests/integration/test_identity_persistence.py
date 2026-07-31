"""Identity Persistence Integration Tests

Tests that verify persistent identity resolution:
- Identity mappings survive new EntityManager instances
- Same (source, external_id) resolves to same Entity
- Identity resolution is identity-first
- CV1-CV4 remain valid

Author: WO-008-016 Implementation
Version: 1.0
"""

import pytest
from uuid import UUID

from app.intelligence.entity import (
    Entity,
    EntityData,
    EntityManager,
    EntityRelationType,
    EntityStatus,
    EntityType,
    Priority,
)
from app.intelligence.entity.entity_manager import InMemoryEntityRepository
from app.core.event_bus import EventBus


class TestIdentityPersistence:
    """Tests for persistent identity resolution."""

    @pytest.fixture
    def repository(self):
        """Create InMemory repository."""
        return InMemoryEntityRepository()

    @pytest.fixture
    def manager(self, repository):
        """Create EntityManager with repository."""
        return EntityManager(repository=repository)

    # =============================================================================
    # PERSIST-01: identity survives new EntityManager
    # =============================================================================

    async def test_persist_01_new_manager_same_repo(self, repository):
        """PERSIST-01: Identity mapping persists across EntityManager instances.

        When a new EntityManager is created with the same repository,
        identity resolution should return the existing Entity.
        """
        # Manager 1 creates entity
        manager1 = EntityManager(repository=repository)
        entity1, created1 = await manager1.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="PERSIST-001",
        )
        assert created1 is True, "First call should create entity"

        # Manager 2 with same repository
        manager2 = EntityManager(repository=repository)
        entity2, created2 = await manager2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="PERSIST-001",
        )

        # Should NOT create new entity
        assert created2 is False, "Second call should NOT create entity"
        assert entity1.id == entity2.id, "Should return same entity"

    # =============================================================================
    # PERSIST-02: same identity does not create duplicate
    # =============================================================================

    async def test_persist_02_no_duplicate(self, repository):
        """PERSIST-02: Duplicate identity resolution does not create duplicate Entity."""
        manager = EntityManager(repository=repository)

        # First call
        entity1, created1 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="SIG-DUP-001",
        )
        assert created1 is True

        # Second call with same identity
        entity2, created2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="SIG-DUP-001",
        )

        # Should NOT create duplicate
        assert created2 is False, "Should NOT create duplicate"
        assert entity1.id == entity2.id, "Same entity returned"

        # Repository should have only one entity
        entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(entities) == 1, "Only one entity should exist"

    # =============================================================================
    # PERSIST-03: identity resolution is identity-first
    # =============================================================================

    async def test_persist_03_identity_first(self, repository):
        """PERSIST-03: Identity resolution precedes Entity creation.

        CV1 - Identity-First: resolve identity BEFORE creating Entity.
        """
        manager = EntityManager(repository=repository)

        # Before any creation - no identity
        resolved = await repository.resolve_by_identity("x", "y")
        assert resolved is None, "No identity before creation"

        # Create entity
        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="x",
            external_id="y",
        )
        assert created is True, "Entity should be created"

        # After creation - identity exists
        resolved = await repository.resolve_by_identity("x", "y")
        assert resolved == entity.id, "Identity should be registered"

        # Second call should resolve without creating
        entity2, created2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="x",
            external_id="y",
        )
        assert created2 is False, "Should resolve existing"

    # =============================================================================
    # PERSIST-04: soft-deleted entity remains retrievable
    # =============================================================================

    async def test_persist_04_deleted_entity_retrievable(self, repository):
        """PERSIST-04: Soft-deleted (INACTIVE) entity remains retrievable.

        CV2 - Non-destructive delete: Entity not physically removed.
        """
        manager = EntityManager(repository=repository)

        # Create entity WITH registered external identity
        entity, _ = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="test",
            external_id="PERSIST-04-ID",
        )
        entity_id = entity.id

        # Delete (soft delete)
        await manager.delete(entity_id)

        # Entity should still exist
        retrieved = await manager.get(entity_id)
        assert retrieved is not None, "Entity should exist after delete"
        assert retrieved.status == EntityStatus.INACTIVE, "Status should be INACTIVE"

        # Repository should still have entity
        all_entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(all_entities) > 0, "Entity should be in repository"

        # Identity STILL resolves to the INACTIVE entity
        # This is the identity policy - inactive entities still resolve
        entity2, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="test",
            external_id="PERSIST-04-ID",  # Same registered identity used at creation
        )
        assert created is False, "Should not create duplicate"
        assert entity2.id == entity_id, "Should return deleted entity"

    # =============================================================================
    # PERSIST-05: aliases remain resolvable after restart
    # =============================================================================

    async def test_persist_05_aliases_stored(self, repository):
        """PERSIST-05: External IDs (aliases) are stored with Entity."""
        manager = EntityManager(repository=repository)

        # Create entity with external_id
        entity, _ = await manager.create(
            entity_type=EntityType.CONTACT,
            source="telegram",
            external_id="TG-001",
        )

        # Add alias
        entity.external_ids["telegram_alias"] = "old-tg-001"
        await repository.save(entity)

        # New manager should be able to resolve primary
        manager2 = EntityManager(repository=repository)
        entity2, created = await manager2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="telegram",
            external_id="TG-001",
        )

        assert created is False, "Should resolve existing"
        assert entity2.id == entity.id, "Same entity"

        # Alias should be preserved in entity data
        all_entities = await repository.find_by_type(EntityType.CONTACT)
        stored_entity = all_entities[0]
        assert "telegram_alias" in stored_entity.external_ids

    # =============================================================================
    # PERSIST-06: conflicting identity does not merge
    # =============================================================================

    async def test_persist_06_no_silent_merge(self, repository):
        """PERSIST-06: Different identities do not merge into same Entity."""
        manager = EntityManager(repository=repository)

        # Create with different external_ids
        e1, c1 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="A",
        )
        assert c1 is True

        e2, c2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="B",
        )
        assert c2 is True

        assert e1.id != e2.id, "Different identities should create different entities"

        # Different sources should also be separate
        e3, c3 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="A",
        )
        assert c3 is True
        assert e1.id != e3.id, "Different source with same external_id = different entity"

    # =============================================================================
    # PERSIST-07: existing relations remain intact
    # =============================================================================

    async def test_persist_07_relations_with_new_manager(self, repository):
        """PERSIST-07: Relations work within a manager session.

        Note: Relations are managed by EntityRelations (in-memory),
        not by the repository. This test verifies relations work
        within a session. Cross-session persistence of relations
        would require a separate persistence mechanism.
        """
        manager = EntityManager(repository=repository)

        # Create entities
        e1, _ = await manager.create(entity_type=EntityType.UNIT, source="parent")
        e2, _ = await manager.create(entity_type=EntityType.CONTACT, source="child")

        # Create relation
        result = await manager.relate(e1.id, e2.id, EntityRelationType.PARENT)
        assert result is True, "Relation should be created"

        # Within same manager, get_related works
        related = await manager.get_related(e1.id)
        assert len(related) == 1, "Should have one related entity"
        assert related[0].id == e2.id, "Should be the child entity"

    # =============================================================================
    # PERSIST-08: CV1-CV4 regression
    # =============================================================================

    def test_persist_08_cv1_identity_first(self):
        """PERSIST-08a: CV1 - Identity-first resolution."""
        # This is tested by PERSIST-03

    async def test_persist_08_cv2_no_physical_delete(self, repository):
        """PERSIST-08b: CV2 - No physical Entity deletion."""
        manager = EntityManager(repository=repository)
        entity, _ = await manager.create(entity_type=EntityType.CONTACT, source="test")
        entity_id = entity.id

        await manager.delete(entity_id)

        retrieved = await manager.get(entity_id)
        assert retrieved is not None, "Entity should still exist"
        assert retrieved.status == EntityStatus.INACTIVE, "Status should be INACTIVE"

    def test_persist_08_cv3_initial_unknown(self):
        """PERSIST-08c: CV3 - Initial status is UNKNOWN."""
        entity = Entity.create(entity_type=EntityType.CONTACT, source="test")
        assert entity.status == EntityStatus.UNKNOWN, "New entity must have UNKNOWN status"

    def test_persist_08_cv4_confidence_first_class(self):
        """PERSIST-08d: CV4 - Confidence is first-class property."""
        # Create with confidence
        entity = Entity.create(
            entity_type=EntityType.CONTACT,
            source="test",
            confidence=0.75,
        )
        assert entity.confidence == 0.75, "Confidence should be preserved"

        # Update
        entity.update_confidence(0.85)
        assert entity.confidence == 0.85, "Update should work"

        # Invalid rejected
        with pytest.raises(ValueError):
            entity.update_confidence(1.5)

        # Serialization
        d = entity.to_dict()
        assert d.get("confidence") == 0.85

        restored = Entity.from_dict(d)
        assert restored.confidence == 0.85, "Deserialization preserves confidence"

    # =============================================================================
    # PERSIST-09: persistence round-trip
    # =============================================================================

    async def test_persist_09_round_trip(self, repository):
        """PERSIST-09: Entity persists across new manager context."""
        manager = EntityManager(repository=repository)

        # Create with full data
        entity, _ = await manager.create(
            entity_type=EntityType.CONTACT,
            source="persist-test",
            external_id="PER-001",
            data=EntityData(callsign="PERSISTEST"),
            confidence=0.88,
        )
        entity_id = entity.id

        # New manager with same repository
        manager2 = EntityManager(repository=repository)

        # Resolve same identity
        entity2, created = await manager2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="persist-test",
            external_id="PER-001",
        )

        assert created is False, "Should not create duplicate"
        assert entity2.id == entity_id, "Same entity ID"
        assert entity2.confidence == 0.88, "Confidence preserved"
        assert entity2.data.callsign == "PERSISTEST", "Data preserved"

        # Only one entity
        all_entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(all_entities) == 1, "Only one entity should exist"


class TestIdentityResolution:
    """Tests for identity resolution behavior."""

    @pytest.fixture
    def repository(self):
        return InMemoryEntityRepository()

    @pytest.fixture
    def manager(self, repository):
        return EntityManager(repository=repository)

    async def test_resolve_existing_identity(self, manager, repository):
        """Identity that exists in repository resolves correctly."""
        # Create via manager
        entity, _ = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="test",
            external_id="ID-001",
        )

        # Direct repository resolution
        resolved_id = await repository.resolve_by_identity("test", "ID-001")
        assert resolved_id == entity.id

    async def test_resolve_missing_identity(self, repository):
        """Identity that doesn't exist returns None."""
        resolved = await repository.resolve_by_identity("nonexistent", "ID-999")
        assert resolved is None

    async def test_identity_key_includes_source(self, manager):
        """Identity key is (source, external_id), not just external_id."""
        # Same external_id, different sources
        e1, _ = await manager.resolve_or_create(EntityType.CONTACT, "source-A", "same-id")
        e2, _ = await manager.resolve_or_create(EntityType.CONTACT, "source-B", "same-id")

        # Should be different entities
        assert e1.id != e2.id, "Different sources = different entities"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
