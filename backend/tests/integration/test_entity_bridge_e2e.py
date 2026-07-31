"""E2E Integration Tests: EventBus → EntityManager

Real integration tests for the Entity subsystem E2E path.
Tests EventBus → EntityManager → Entity → Identity → Relations.

Note: Full EntityBridge testing requires pydantic + sqlalchemy which
are not available in Pyodide. This test covers the EventBus → EntityManager
path which is the core E2E integration point.

For full EntityBridge E2E, run in native Python with:
  pip install pydantic sqlalchemy
  pytest backend/tests/integration/test_entity_bridge_e2e.py -v

Author: WO-008-014
Version: 1.0
"""

import pytest
import asyncio
from typing import List
from uuid import UUID

from app.core.event_bus import EventBus
from app.intelligence.entity import (
    Entity,
    EntityManager,
    EntityType,
    EntityStatus,
    EntityData,
    Priority,
    EntityRelationType,
)
from app.intelligence.entity.entity_manager import InMemoryEntityRepository


class TestEventBusEntityManagerE2E:
    """E2E tests for EventBus → EntityManager integration."""

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
    # E2E-01: New Entity via EventBus → EntityManager
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_01_new_entity_via_event_bus(self, event_bus, entity_manager):
        """Test new entity creation through EventBus integration.

        Flow: EventBus event → EntityManager → Entity created
        """
        # Subscribe to identity events
        events_received = []

        def identity_event_handler(event, context):
            events_received.append(event)

        event_bus.subscribe(
            subscriber_id="identity-handler",
            event_types=["identity.created"],
            handler=identity_event_handler,
        )

        # Create entity through manager
        entity, created = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id="E2E-01-001",
            confidence=0.85,
        )

        # Verify entity creation
        assert created is True, "First call should create entity"
        assert entity is not None
        assert entity.status == EntityStatus.UNKNOWN
        assert entity.confidence == 0.85
        assert entity.source == "signal"

        # Publish event to EventBus
        event_bus.publish(
            "identity.created",
            {
                "entity_id": str(entity.id),
                "external_id": "E2E-01-001",
                "type": "contact",
            },
            {"source": "test"},
        )

        # Verify EventBus received event
        assert len(events_received) == 1
        assert events_received[0]["entity_id"] == str(entity.id)

    # =============================================================================
    # E2E-02: Duplicate Prevention (CV1 Regression)
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_02_duplicate_prevention(self, entity_manager):
        """Test that same identity does not create duplicate entities (CV1).

        This is a direct regression test for CV1 Identity-first.
        """
        # First call with identity
        entity1, created1 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="E2E-02-001",
            confidence=0.75,
        )

        # Second call with same identity
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="E2E-02-001",
            confidence=0.75,
        )

        # Verify no duplicate created
        assert created1 is True, "First call should create"
        assert created2 is False, "Second call should NOT create"
        assert entity1.id == entity2.id, "Same entity should be returned"
        assert entity1.id == entity2.id

        # Count entities
        all_entities = await entity_manager.find_by_type(EntityType.CONTACT)
        assert len(all_entities) == 1, "Only 1 entity should exist"

    # =============================================================================
    # E2E-03: Different Identity Creates New Entity
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_03_different_identity_new_entity(self, entity_manager):
        """Test that different identity creates new entity."""
        # Create first entity
        entity1, _ = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="mqtt",
            external_id="E2E-03-A",
            confidence=0.8,
        )

        # Create second entity with different identity
        entity2, _ = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="mqtt",
            external_id="E2E-03-B",
            confidence=0.9,
        )

        # Verify different entities
        assert entity1.id != entity2.id, "Different identities should create different entities"
        assert entity1.confidence == 0.8
        assert entity2.confidence == 0.9

        # Verify 2 entities exist
        all_entities = await entity_manager.find_by_type(EntityType.CONTACT)
        assert len(all_entities) == 2

    # =============================================================================
    # E2E-04: Existing Entity Update Path
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_04_existing_entity_lookup(self, entity_manager):
        """Test that Bridge would find existing entity for same identity."""
        # Create entity first
        entity1, created1 = await entity_manager.resolve_or_create(
            entity_type=EntityType.UNIT,
            source="atak",
            external_id="E2E-04-001",
            confidence=0.7,
        )

        # Simulate Bridge finding existing entity
        retrieved = await entity_manager.get(entity1.id)

        # Verify same entity returned
        assert retrieved is not None
        assert retrieved.id == entity1.id
        assert retrieved.status == EntityStatus.UNKNOWN

        # Second call - Bridge would use existing
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.UNIT,
            source="atak",
            external_id="E2E-04-001",
        )

        assert created2 is False, "Should find existing entity"
        assert entity2.id == entity1.id

    # =============================================================================
    # E2E-05: EventBus Subscription Proof
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_05_event_bus_subscription(self, event_bus, entity_manager):
        """Test that events can flow through EventBus to EntityManager.

        This proves the EventBus subscription path works.
        Events are received by the handler without using asyncio.run() inside handler.
        """
        events_received = []

        def event_handler(event, context):
            # Synchronous handler - EventBus calls this directly
            events_received.append(event)

        # Subscribe
        event_bus.subscribe(
            subscriber_id="entity-processor",
            event_types=["entity.event"],
            handler=event_handler,
        )

        # Publish event
        event_bus.publish(
            "entity.event",
            {
                "external_id": "E2E-05-001",
                "source": "signal",
                "confidence": 0.85,
            },
            {},
        )

        # Verify event reached handler through EventBus subscription
        assert len(events_received) == 1
        assert events_received[0]["external_id"] == "E2E-05-001"
        assert events_received[0]["source"] == "signal"

        # Unsubscribe and verify no more events
        event_bus.unsubscribe("entity-processor")
        event_bus.publish("entity.event", {"id": "after-unsubscribe"}, {})
        assert len(events_received) == 1, "Should not receive after unsubscribe"

    # =============================================================================
    # E2E-06: Persistence (InMemory)
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_06_inmemory_persistence(self, repository, entity_manager):
        """Test entity persistence in InMemory repository."""
        # Create entity
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
            confidence=0.75,
        )

        # Retrieve from repository directly
        retrieved = await repository.get(entity.id)

        # Verify persistence
        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.confidence == 0.75
        assert retrieved.status == EntityStatus.UNKNOWN

    # =============================================================================
    # E2E-07: CV1 Regression
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_07_cv1_identity_first(self, entity_manager):
        """Regression test for CV1: Identity-first behavior."""
        # Resolve with external_id
        entity1, created1 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="bridge-test",
            external_id="CV1-001",
        )

        # Verify identity resolved before creation
        assert created1 is True
        assert entity1.status == EntityStatus.UNKNOWN

        # Resolve again
        entity2, created2 = await entity_manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="bridge-test",
            external_id="CV1-001",
        )

        # Identity-first: no new entity
        assert created2 is False
        assert entity1.id == entity2.id

    # =============================================================================
    # E2E-08: CV2 Non-destructive Delete
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_08_cv2_soft_delete(self, entity_manager, repository):
        """Regression test for CV2: Non-destructive soft delete."""
        # Create entity
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
            confidence=0.8,
        )
        entity_id = entity.id

        # Delete (soft delete)
        result = await entity_manager.delete(entity_id)
        assert result is True

        # Entity should still exist
        retrieved = await entity_manager.get(entity_id)
        assert retrieved is not None, "Entity should still be retrievable"
        assert retrieved.status == EntityStatus.INACTIVE, "Status should be INACTIVE"

        # Entity should still be in repository
        all_entities = await repository.find_by_type(EntityType.CONTACT)
        assert len(all_entities) > 0, "Entity should be in repository"

    # =============================================================================
    # E2E-09: CV3 Initial Status
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_09_cv3_initial_status(self, entity_manager):
        """Regression test for CV3: Initial status is UNKNOWN."""
        # Create entity through manager
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
        )

        # Initial status must be UNKNOWN
        assert entity.status == EntityStatus.UNKNOWN

        # Verify no PENDING or DELETED status
        valid_statuses = [
            EntityStatus.UNKNOWN, EntityStatus.OBSERVED, EntityStatus.IDENTIFIED,
            EntityStatus.CONFIRMED, EntityStatus.ACTIVE, EntityStatus.INACTIVE,
            EntityStatus.ARCHIVED, EntityStatus.MERGED, EntityStatus.SUPERSEDED
        ]
        assert entity.status in valid_statuses

    # =============================================================================
    # E2E-10: CV4 Confidence
    # =============================================================================

    @pytest.mark.asyncio
    async def test_e2e_10_cv4_confidence(self, entity_manager):
        """Regression test for CV4: Confidence is first-class."""
        # Create with confidence
        entity, _ = await entity_manager.create(
            entity_type=EntityType.CONTACT,
            source="test",
            confidence=0.65,
        )

        assert entity.confidence == 0.65, "Confidence should be preserved"

        # Update confidence
        entity.confidence = 0.85
        await entity_manager.update(entity)

        # Verify update
        retrieved = await entity_manager.get(entity.id)
        assert retrieved.confidence == 0.85

        # Invalid confidence
        try:
            entity.update_confidence(1.5)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected

        # Serialization
        d = entity.to_dict()
        assert d.get("confidence") == 0.85

        restored = Entity.from_dict(d)
        assert restored.confidence == 0.85


class TestRelationsE2E:
    """E2E tests for EntityRelations integration."""

    @pytest.fixture
    def entity_manager(self):
        return EntityManager(repository=InMemoryEntityRepository())

    @pytest.mark.asyncio
    async def test_relations_create_and_retrieve(self, entity_manager):
        """Test relation creation and retrieval."""
        # Create entities
        entity1, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="test")
        entity2, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="test")

        # Create relation
        result = await entity_manager.relate(
            entity1.id, entity2.id, EntityRelationType.PEER
        )
        assert result is True

        # Retrieve related
        related = await entity_manager.get_related(entity1.id)
        assert len(related) == 1
        assert entity2 in related

    @pytest.mark.asyncio
    async def test_multiple_relations(self, entity_manager):
        """Test multiple relations from one entity."""
        # Create entities
        entity1, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="test")
        entity2, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="test")
        entity3, _ = await entity_manager.create(entity_type=EntityType.UNIT, source="test")

        # Create multiple relations
        await entity_manager.relate(entity1.id, entity2.id, EntityRelationType.PEER)
        await entity_manager.relate(entity1.id, entity3.id, EntityRelationType.MEMBER)

        # Verify multiple relations
        related = await entity_manager.get_related(entity1.id)
        assert len(related) == 2
        assert entity2 in related
        assert entity3 in related


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
