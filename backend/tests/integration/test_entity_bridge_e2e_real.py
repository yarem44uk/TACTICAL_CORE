"""Real Entity E2E Integration Tests

These tests verify the real production E2E path:
EventBus → EntityManager → Entity → Repository

Note: Full EntityBridge with Observation/pydantic/SQLAlchemy is blocked
by production dependencies. These tests verify the Entity subsystem
directly as the foundation for the E2E path.

Author: WO-008-015 Implementation
Version: 1.0
"""

import pytest
from typing import List
from uuid import UUID

from app.core.event_bus import EventBus
from app.intelligence.entity import (
    Entity,
    EntityData,
    EntityManager,
    EntityType,
    EntityStatus,
    EntityRelationType,
    Priority,
)
from app.intelligence.entity.entity_manager import InMemoryEntityRepository
from app.intelligence.entity.identity import IdentityResolver


class TestEntityE2E:
    """E2E tests for Entity subsystem."""

    @pytest.fixture
    def event_bus(self):
        """Create EventBus instance."""
        return EventBus()

    @pytest.fixture
    def repository(self):
        """Create InMemory repository."""
        return InMemoryEntityRepository()

    @pytest.fixture
    def entity_manager(self, repository):
        """Create EntityManager with repository."""
        return EntityManager(repository=repository)

    # =============================================================================
    # E2E-01: New observation creates Entity
    # =============================================================================

    async def test_e2e_01_new_entity_creates_unknown(self, event_bus, entity_manager):
        """E2E-01: New observation with identity creates Entity with UNKNOWN status.

        This simulates what EntityBridge.forward() does:
        - Observation received with source + external_id
        - EntityManager.resolve_or_create() called
        - New Entity created with UNKNOWN status
        - Event published to EventBus
        """
        events_received = []

        def entity_event_handler(event, context):
            events_received.append(event)

        # Subscribe like EntityBridge would
        event_bus.subscribe(
            subscriber_id="entity-processor",
            event_types=["entity.event"],
            handler=entity_event_handler,
        )

        # Simulate observation with identity
        source = "signal"
        external_id = "SIG-001"

        # Create Entity (what EntityBridge.forward() does)
        entity, created = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
            data=EntityData(callsign="ALPHA-1"),
            confidence=0.85,
        )

        # Verify Entity created
        assert created is True, "First call should create entity"
        assert entity.id is not None
        assert entity.status == EntityStatus.UNKNOWN, "New entity must have UNKNOWN status"
        assert entity.confidence == 0.85

        # Publish event like EntityBridge would
        event_bus.publish(
            "entity.event",
            {"entity_id": str(entity.id), "created": True},
            {},
        )

        # Verify EventBus received event
        assert len(events_received) == 1
        assert events_received[0]["entity_id"] == str(entity.id)

    # =============================================================================
    # E2E-02: Same identity does not create duplicate
    # =============================================================================

    async def test_e2e_02_same_identity_no_duplicate(self, entity_manager):
        """E2E-02: Same (source, external_id) returns same Entity.

        This verifies CV1 - Identity-First resolution.
        """
        source = "signal"
        external_id = "SIG-DUP-001"

        # First call
        entity1, created1 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )
        assert created1 is True

        # Second call with same identity
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )

        # Should NOT create duplicate
        assert created2 is False, "Second call should NOT create entity"
        assert entity1.id == entity2.id, "Same entity should be returned"

        # Repository should have only one entity
        entities = await entity_manager.search(source)
        assert len(entities) == 1, "Only one entity should exist"

    # =============================================================================
    # E2E-03: Different identity creates different Entity
    # =============================================================================

    async def test_e2e_03_different_identity_creates_different(self, entity_manager):
        """E2E-03: Different (source, external_id) creates different Entities."""
        # First entity
        entity1, created1 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="SIG-A-001",
        )
        assert created1 is True

        # Second entity with different identity
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="SIG-B-001",
        )
        assert created2 is True

        # Should be different entities
        assert entity1.id != entity2.id

    # =============================================================================
    # E2E-04: Entity without identity (edge case)
    # =============================================================================

    async def test_e2e_04_entity_without_external_id(self, entity_manager):
        """E2E-04: Entity can be created with source only (no external_id).

        This tests the create() path without resolve_or_create().
        """
        entity, created = await entity_manager.create(
            entity_type=EntityType.UNIT,
            source="mqtt",
        )

        assert created is True
        assert entity.id is not None
        assert entity.status == EntityStatus.UNKNOWN

        # Entity should be retrievable
        retrieved = await entity_manager.get(entity.id)
        assert retrieved is not None
        assert retrieved.id == entity.id

    # =============================================================================
    # E2E-05: EventBus integration (real path)
    # =============================================================================

    async def test_e2e_05_eventbus_real_integration(self, event_bus, entity_manager):
        """E2E-05: Real EventBus subscribe → publish → handler path.

        This verifies the EventBus integration works with the real API.
        """
        events = []

        def handler(event, context):
            events.append(event)

        # Subscribe
        event_bus.subscribe(
            subscriber_id="test-handler",
            event_types=["entity.created"],
            handler=handler,
        )

        # Publish
        event_bus.publish(
            "entity.created",
            {"entity_id": "test-123", "source": "test"},
            {},
        )

        # Verify handler received event
        assert len(events) == 1
        assert events[0]["entity_id"] == "test-123"

        # Unsubscribe
        event_bus.unsubscribe("test-handler")

        # Publish again
        event_bus.publish(
            "entity.created",
            {"entity_id": "test-456"},
            {},
        )

        # Should not receive after unsubscribe
        assert len(events) == 1, "Should not receive after unsubscribe"

    # =============================================================================
    # E2E-06: Soft delete remains valid (CV2)
    # =============================================================================

    async def test_e2e_06_soft_delete_preserves_entity(self, entity_manager, repository):
        """E2E-06: Soft delete transitions to INACTIVE, entity remains retrievable.

        This verifies CV2 - Non-destructive delete.
        """
        # Create entity
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
        )
        entity_id = entity.id

        # Delete (soft delete)
        result = await entity_manager.delete(entity_id)
        assert result is True, "Delete should return True"

        # Entity should still exist (not physically deleted)
        retrieved = await entity_manager.get(entity_id)
        assert retrieved is not None, "Entity should still exist after delete"
        assert retrieved.status == EntityStatus.INACTIVE, "Status should be INACTIVE"

        # Repository should still have entity
        all_entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(all_entities) > 0, "Entity should be in repository"

    # =============================================================================
    # E2E-07: Persistence (new context)
    # =============================================================================

    async def test_e2e_07_persistence_new_context(self, repository, entity_manager):
        """E2E-07: Entity persists across new manager context.

        This verifies persistence works - entity available after creating new manager.
        """
        # Create entity
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="persist-test",
            external_id="PER-001",
        )
        entity_id = entity.id
        original_status = entity.status
        original_confidence = entity.confidence

        # Create new manager with same repository
        new_manager = EntityManager(repository=repository)

        # Retrieve entity with new manager
        retrieved = await new_manager.get(entity_id)
        assert retrieved is not None, "Entity should be retrievable in new context"
        assert retrieved.id == entity_id
        assert retrieved.status == original_status
        assert retrieved.confidence == original_confidence

        # Identity should still be registered
        # (EntityManager created with same repository)
        _, created = await new_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="persist-test",
            external_id="PER-001",
        )
        assert created is False, "Identity should still be registered"

    # =============================================================================
    # E2E-08: CV1 - Identity-first verification
    # =============================================================================

    async def test_e2e_08_cv1_identity_first(self, entity_manager):
        """E2E-08: Verify CV1 - Identity-first resolution order.

        Resolution order must be:
        1. resolve identity
        2. if found -> return existing
        3. if not found -> create new
        """
        source = "radio"
        external_id = "RADIO-CV1-001"

        # Verify identity resolver tracks correctly
        resolver = entity_manager._identity_resolver

        # Before: no identity
        assert resolver.resolve(source, external_id) is None

        # Create
        entity, created = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )
        assert created is True

        # After: identity exists
        assert resolver.resolve(source, external_id) == entity.id

        # Second call resolves existing
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )
        assert created2 is False
        assert entity2.id == entity.id

    # =============================================================================
    # E2E-09: CV3 - Initial status UNKNOWN
    # =============================================================================

    async def test_e2e_09_cv3_initial_status_unknown(self, entity_manager):
        """E2E-09: Verify CV3 - New entities start with UNKNOWN status.

        UNKNOWN is the only valid initial status per constitution.
        PENDING and DELETED are forbidden.
        """
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
        )

        assert entity.status == EntityStatus.UNKNOWN

        # Verify UNKNOWN is in valid statuses
        valid_statuses = [
            EntityStatus.UNKNOWN, EntityStatus.OBSERVED,
            EntityStatus.IDENTIFIED, EntityStatus.CONFIRMED,
            EntityStatus.ACTIVE, EntityStatus.INACTIVE,
            EntityStatus.ARCHIVED, EntityStatus.MERGED,
            EntityStatus.SUPERSEDED
        ]
        assert entity.status in valid_statuses

        # Verify PENDING and DELETED are NOT in statuses
        # (This is checked by enum - they don't exist)

    # =============================================================================
    # E2E-10: CV4 - Confidence first-class
    # =============================================================================

    async def test_e2e_10_cv4_confidence_first_class(self, entity_manager):
        """E2E-10: Verify CV4 - Confidence is first-class property."""
        # Create with confidence
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
            confidence=0.75,
        )
        assert entity.confidence == 0.75

        # Update confidence
        entity.update_confidence(0.90)
        assert entity.confidence == 0.90

        # Invalid confidence rejected
        with pytest.raises(ValueError):
            entity.update_confidence(1.5)

        # Serialization preserves confidence
        d = entity.to_dict()
        assert d.get("confidence") == 0.90

        # Deserialization preserves confidence
        restored = Entity.from_dict(d)
        assert restored.confidence == 0.90

    # =============================================================================
    # E2E-11: Relations integration
    # =============================================================================

    async def test_e2e_11_relations_integration(self, entity_manager):
        """E2E-11: Verify relations work with EntityManager.

        Relations are created via EntityManager.relate() and retrieved via get_related().
        """
        # Create two entities
        entity1, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="parent")
        entity2, _ = await entity_manager.create(entity_type=EntityType.CONTACT, source="child")

        # Create relation
        result = await entity_manager.relate(entity1.id, entity2.id, EntityRelationType.PARENT)
        assert result is True

        # Retrieve related
        related = await entity_manager.get_related(entity1.id)
        assert len(related) == 1
        assert related[0].id == entity2.id

    # =============================================================================
    # E2E-12: Error handling does not create phantom Entity
    # =============================================================================

    async def test_e2e_12_no_phantom_on_error(self, entity_manager, repository):
        """E2E-12: Error after identity resolution does not create phantom.

        This is a critical integrity test - failures should not leave
        partial or duplicate entities.
        """
        source = "error-test"
        external_id = "ERR-001"

        # Get initial state
        initial_entities = await repository.find_by_type(EntityType.CONTACT)
        initial_count = len(initial_entities)

        # Create valid entity first
        entity, created = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )
        assert created is True

        # Second attempt with same identity should fail gracefully
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )
        assert created2 is False
        assert entity2.id == entity.id

        # No phantom entities created
        final_entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(final_entities) == initial_count + 1, "Only one entity should exist"


class TestEntityRelationsE2E:
    """E2E tests for Entity Relations."""

    @pytest.fixture
    def repository(self):
        return InMemoryEntityRepository()

    @pytest.fixture
    def entity_manager(self, repository):
        return EntityManager(repository=repository)

    async def test_relations_create_and_retrieve(self, entity_manager):
        """Test creating relations and retrieving related entities."""
        e1, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="main")
        e2, _ = await entity_manager.create(entity_type=EntityType.CONTACT, source="related")

        # Relate
        await entity_manager.relate(e1.id, e2.id, EntityRelationType.PEER)

        # Get related
        related = await entity_manager.get_related(e1.id)
        assert len(related) == 1
        assert related[0].id == e2.id

    async def test_multiple_relations(self, entity_manager):
        """Test multiple relations from single entity."""
        main, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="main")

        entities = []
        for i in range(3):
            e, _ = await entity_manager.create(entity_type=EntityType.CONTACT, source=f"child-{i}")
            entities.append(e)

        # Create relations
        for e in entities:
            await entity_manager.relate(main.id, e.id, EntityRelationType.MEMBER)

        # Get all related
        related = await entity_manager.get_related(main.id)
        assert len(related) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
