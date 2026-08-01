"""Integration Test: End-to-End Pipeline

Tests the integration flow from EventBus through to components.
This test documents the current production pipeline capabilities
and identifies gaps.

IMPORTANT:
--------
This test documents the production architecture gap:
  - Observation Service creates Observations
  - Entity/Identity subsystem exists but is NOT automatically wired
  - Full automatic Observation → Entity → Persistence flow is NOT implemented

Per WO-008-009 rules, this architectural gap must be reported
to the Chief Systems Architect for resolution.

Author: WO-008-009 Implementation
Version: 1.0
"""

import pytest
from typing import Dict, Any
from uuid import uuid4

from app.core.event_bus import EventBus
from app.intelligence.entity import (
    Entity,
    EntityType,
    EntityStatus,
    EntityManager,
)


class MockEntityRepository:
    """Minimal mock for EntityRepository ABC."""

    def __init__(self):
        self._entities = {}

    async def save(self, entity):
        self._entities[entity.id] = entity
        return entity

    async def get(self, entity_id):
        return self._entities.get(entity_id)

    async def delete(self, entity_id):
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            return True
        return False

    async def mark_inactive(self, entity_id):
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.INACTIVE
            return entity
        return None

    async def archive(self, entity_id):
        entity = self._entities.get(entity_id)
        if entity:
            entity.status = EntityStatus.ARCHIVED
            return entity
        return None

    async def merge(self, source_id, target_id):
        return None

    async def supersede(self, old_id, new_id):
        return None

    async def resolve_by_identity(self, source: str, external_id: str):
        from uuid import UUID
        for entity in self._entities.values():
            if entity.external_ids:
                for src, ids in entity.external_ids.items():
                    if src == source and external_id in ids:
                        return entity.id
        return None

    async def find_by_type(self, entity_type):
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    async def find_by_status(self, status):
        return [e for e in self._entities.values() if e.status == status]

    async def find_by_tag(self, tag):
        return [e for e in self._entities.values() if e.data and tag in e.data.tags]

    async def search(self, query, limit=100):
        query_lower = query.lower()
        results = []
        for entity in self._entities.values():
            if query_lower in entity.source.lower():
                results.append(entity)
                if len(results) >= limit:
                    break
        return results[:limit]


class TestEventBusToEntityManual:
    """Test EventBus → Entity flow with manual wiring.

    This test demonstrates that:
    1. EventBus works correctly
    2. Entity subsystem works correctly
    3. Manual wiring creates correct results
    4. AUTOMATIC wiring is NOT implemented in production
    """

    @pytest.mark.asyncio
    async def test_eventbus_to_entity_manual_wiring(self):
        """Test EventBus → Event → Entity with manual wiring.

        This simulates what the production pipeline SHOULD do
        automatically, but currently requires manual intervention.
        """
        # Setup
        bus = EventBus()
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        # Capture events
        captured = []

        def event_handler(event: Any, context: Dict[str, Any]) -> None:
            captured.append(event)

        bus.subscribe("entity-processor", event_handler, ["signal.message"])

        # Publish event
        signal_event = {
            "event_type": "signal.message",
            "event_id": "sig-001",
            "timestamp": "2026-01-15T10:30:00Z",
            "source": "signal_connector",
            "data": {
                "message_id": "msg-123",
                "sender": "+1234567890",
                "chat_id": "chat-456",
                "message_text": "Tactical update",
            },
        }

        bus.publish("signal.message", signal_event, {"connector": "signal"})

        # Verify EventBus delivered the event
        assert len(captured) == 1
        assert captured[0]["event_type"] == "signal.message"

        # MANUAL WIRING: Extract identity and create Entity
        # (Production does NOT do this automatically)
        event_data = captured[0]["data"]
        external_id = event_data.get("message_id")
        source = captured[0]["source"]

        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source=source,
            external_id=external_id,
        )

        # Verify Entity was created
        assert created is True
        assert entity.status == EntityStatus.UNKNOWN
        assert entity.id is not None

    @pytest.mark.asyncio
    async def test_manual_wiring_prevents_duplicates(self):
        """Test that manual wiring + resolve_or_create prevents duplicates.

        This shows the desired behavior when identity resolution works.
        """
        bus = EventBus()
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        captured = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            captured.append(event)

        bus.subscribe("handler", handler, ["telegram.message"])

        # First message
        msg1 = {
            "event_type": "telegram.message",
            "event_id": "tg-001",
            "data": {"message_id": 123, "text": "First"},
        }
        bus.publish("telegram.message", msg1, {})
        event1 = captured[0]

        # Create first entity
        entity1, created1 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="telegram",
            external_id="123",
        )
        assert created1 is True

        # Clear and simulate second message
        captured.clear()
        msg2 = {
            "event_type": "telegram.message",
            "event_id": "tg-002",
            "data": {"message_id": 123, "text": "Second"},  # Same message_id
        }
        bus.publish("telegram.message", msg2, {})

        # Create second entity with SAME identity
        entity2, created2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="telegram",
            external_id="123",
        )

        # Should NOT create duplicate
        assert created2 is False
        assert entity2.id == entity1.id  # Same entity returned

    @pytest.mark.asyncio
    async def test_different_identities_create_different_entities(self):
        """Test different external IDs create different entities."""
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        # Entity 1
        entity1, created1 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="FREQ-155.5",
        )
        assert created1 is True

        # Entity 2 (different identity)
        entity2, created2 = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="FREQ-155.7",
        )
        assert created2 is True

        # Should be different entities
        assert entity1.id != entity2.id


class TestProductionGapDocumentation:
    """Document the production architecture gap."""

    def test_production_gap_identified(self):
        """Document that automatic Observation → Entity is NOT implemented.

        This test always passes but serves as documentation of the gap.

        GAP: Production does NOT automatically:
        1. Receive Observation from ObservationService
        2. Extract external identity
        3. Create/update Entity via EntityManager
        4. Link Observation to Entity

        CURRENT PRODUCTION FLOW:
        Connector → EventBus → ObservationService → Observation
                                                              ↓
                                                      (stops here)
                                                              ↓
                                          Entity must be created separately

        DESIRED FLOW (per WO-008-009):
        Connector → EventBus → ObservationService → Observation
                                                              ↓
                                              EntityManager.resolve_or_create()
                                                              ↓
                                              Entity (with identity linked)
                                                              ↓
                                              Persistence
        """
        # This is documentation - always passes
        gap_identified = True
        assert gap_identified, "Production gap must be reported to Architect"

    def test_workaround_exists(self):
        """Document that manual wiring is possible but not production-ready.

        The ObservationEngine has a pipeline_forwarder callback that COULD
        theoretically forward to Entity/Identity, but this is NOT wired up
        in current production code.
        """
        workaround_exists = True
        assert workaround_exists


class TestConnectorCoverage:
    """Test canonical paths for each connector type."""

    @pytest.mark.asyncio
    async def test_signal_connector_canonical_path(self):
        """Test Signal connector event → Entity path."""
        bus = EventBus()
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe("signal-handler", handler, ["signal.message"])

        # Signal event
        signal_evt = {
            "event_type": "signal.message",
            "event_id": "sig-" + str(uuid4()),
            "data": {
                "message_id": "msg-signal-001",
                "sender": "+111",
                "chat_id": "chat-1",
            },
        }

        bus.publish("signal.message", signal_evt, {"connector": "signal"})

        assert len(received) == 1

        # Manual Entity creation
        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="signal",
            external_id=received[0]["data"]["message_id"],
        )
        assert created is True
        assert entity.status == EntityStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_radio_connector_canonical_path(self):
        """Test Radio connector event → Entity path."""
        bus = EventBus()
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe("radio-handler", handler, ["radio.transmission"])

        # Radio event
        radio_evt = {
            "event_type": "radio.transmission",
            "event_id": "radio-" + str(uuid4()),
            "data": {
                "frequency": "155.5",
                "callsign": "ALPHA-1",
            },
        }

        bus.publish("radio.transmission", radio_evt, {"connector": "radio"})

        assert len(received) == 1

        # Manual Entity creation
        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id=received[0]["data"]["callsign"],
        )
        assert created is True

    @pytest.mark.asyncio
    async def test_mqtt_connector_canonical_path(self):
        """Test MQTT connector event → Entity path."""
        bus = EventBus()
        repo = MockEntityRepository()
        manager = EntityManager(repository=repo)

        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe("mqtt-handler", handler, ["mqtt.message"])

        mqtt_evt = {
            "event_type": "mqtt.message",
            "event_id": "mqtt-" + str(uuid4()),
            "data": {"topic": "test/topic", "payload": {"value": 42}},
        }

        bus.publish("mqtt.message", mqtt_evt, {"connector": "mqtt"})

        assert len(received) == 1

        # Manual Entity creation
        entity, created = await manager.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="mqtt",
            external_id=f"mqtt-{received[0]['event_id']}",
        )
        assert created is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
