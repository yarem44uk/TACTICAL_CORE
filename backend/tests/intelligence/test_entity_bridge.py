"""Entity Bridge Unit Tests.

Tests EntityBridge isolation from EventBus and EntityManager.
Verifies subscription, event handling, identity extraction, and
duplicate prevention without external dependencies.

Author: WO-009-001
Version: 1.0
"""

import pytest
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.event_bus import EventBus
from app.intelligence.entity import (
    EntityManager,
    EntityType,
    EntityStatus,
)
from app.intelligence.entity.entity_manager import InMemoryEntityRepository
from app.intelligence.entity.entity_bridge import EntityBridge


@pytest.fixture
def event_bus():
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def repository():
    """Create InMemory repository."""
    return InMemoryEntityRepository()


@pytest.fixture
def entity_manager(repository):
    """Create EntityManager with repository."""
    return EntityManager(repository=repository)


@pytest.fixture
def bridge(event_bus, entity_manager):
    """Create EntityBridge instance."""
    return EntityBridge(event_bus=event_bus, entity_manager=entity_manager)


class TestEntityBridgeInit:
    """Test EntityBridge initialization."""

    def test_default_init(self, event_bus, entity_manager):
        """Test default initialization."""
        b = EntityBridge(event_bus=event_bus, entity_manager=entity_manager)
        assert b.is_subscribed is False
        assert b._subscription_id is None

    def test_custom_event_type_map(self, event_bus, entity_manager):
        """Test custom event type mapping."""
        custom_map = {
            "custom.event": EntityType.ASSET,
        }
        b = EntityBridge(
            event_bus=event_bus,
            entity_manager=entity_manager,
            event_type_map=custom_map,
        )
        assert b._event_type_map == custom_map

    def test_custom_source_field(self, event_bus, entity_manager):
        """Test custom source field name."""
        b = EntityBridge(
            event_bus=event_bus,
            entity_manager=entity_manager,
            source_field="device_id",
        )
        assert b._source_field == "device_id"


class TestEntityBridgeSubscribe:
    """Test EntityBridge subscription to EventBus."""

    def test_subscribe_returns_id(self, bridge, event_bus):
        """Test that subscribe returns a subscription ID."""
        sub_id = bridge.subscribe()
        assert sub_id is not None
        assert isinstance(sub_id, str)
        assert bridge.is_subscribed is True

    def test_subscribe_creates_patterns(self, bridge, event_bus):
        """Test that subscribe uses wildcard patterns."""
        bridge.subscribe()
        # Verify subscription exists
        assert bridge._subscription_id is not None

    def test_unsubscribe(self, bridge, event_bus):
        """Test unsubscribe."""
        bridge.subscribe()
        assert bridge.is_subscribed is True
        bridge.unsubscribe()
        assert bridge.is_subscribed is False

    def test_unsubscribe_when_not_subscribed(self, bridge):
        """Test unsubscribe when already unsubscribed."""
        bridge.unsubscribe()  # Should not raise


class TestEntityBridgeEventHandling:
    """Test event handling and identity extraction."""

    @pytest.mark.asyncio
    async def test_signal_event_creates_entity(self, event_bus, bridge, entity_manager):
        """Test signal event creates new entity."""
        bridge.subscribe()

        # Publish signal event
        event_bus.publish(
            "signal.message",
            {
                "source": "signal",
                "external_id": "SIG-001",
            },
            {},
        )

        # Verify entity was created
        entities = await entity_manager.find_by_type(EntityType.CONTACT)
        assert len(entities) == 1
        assert entities[0].status == EntityStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_radio_event_creates_entity(self, event_bus, bridge, entity_manager):
        """Test radio event creates new entity."""
        bridge.subscribe()

        event_bus.publish(
            "radio.transmission",
            {
                "source": "radio",
                "external_id": "RAD-001",
            },
            {},
        )

        entities = await entity_manager.find_by_type(EntityType.CONTACT)
        assert len(entities) == 1

    @pytest.mark.asyncio
    async def test_mqtt_event_creates_entity(self, event_bus, bridge, entity_manager):
        """Test MQTT event creates new entity."""
        bridge.subscribe()

        event_bus.publish(
            "mqtt.message",
            {
                "source": "mqtt",
                "external_id": "MQT-001",
                "event_type": "mqtt.message",
            },
            {},
        )

        entities = await entity_manager.find_by_type(EntityType.ASSET)
        assert len(entities) == 1

    @pytest.mark.asyncio
    async def test_same_identity_no_duplicate(self, event_bus, bridge, entity_manager):
        """Test same identity does not create duplicate."""
        bridge.subscribe()

        # Publish same identity twice
        event_bus.publish(
            "signal.message",
            {"source": "signal", "external_id": "DUP-001"},
            {},
        )
        event_bus.publish(
            "signal.message",
            {"source": "signal", "external_id": "DUP-001"},
            {},
        )

        entities = await entity_manager.find_by_type(EntityType.CONTACT)
        assert len(entities) == 1

    @pytest.mark.asyncio
    async def test_missing_source_skipped(self, event_bus, bridge):
        """Test event without source is skipped."""
        bridge.subscribe()

        event_bus.publish(
            "signal.message",
            {"external_id": "NO-SOURCE"},
            {},
        )

        entities = await bridge._entity_manager.find_by_type(EntityType.CONTACT)
        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_missing_external_id_skipped(self, event_bus, bridge):
        """Test event without external_id is skipped."""
        bridge.subscribe()

        event_bus.publish(
            "signal.message",
            {"source": "signal"},
            {},
        )

        entities = await bridge._entity_manager.find_by_type(EntityType.CONTACT)
        assert len(entities) == 0


class TestEntityBridgeForward:
    """Test programmatic forward method."""

    @pytest.mark.asyncio
    async def test_forward_creates_entity(self, bridge, entity_manager):
        """Test forward creates entity."""
        entity, created = await bridge.forward(
            source="manual",
            external_id="MAN-001",
        )
        assert created is True
        assert entity is not None
        assert entity.status == EntityStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_forward_no_duplicate(self, bridge, entity_manager):
        """Test forward does not create duplicate."""
        _, _ = await bridge.forward(
            source="manual",
            external_id="MAN-002",
        )
        entity2, created2 = await bridge.forward(
            source="manual",
            external_id="MAN-002",
        )
        assert created2 is False
        assert entity2 is not None

    @pytest.mark.asyncio
    async def test_forward_custom_entity_type(self, bridge, entity_manager):
        """Test forward with custom entity type."""
        entity, _ = await bridge.forward(
            source="test",
            external_id="TEST-001",
            entity_type=EntityType.UNIT,
        )
        assert entity.entity_type == EntityType.UNIT


class TestEntityBridgeEntityTypeResolution:
    """Test entity type resolution from events."""

    def test_explicit_entity_type_in_payload(self, bridge):
        """Test explicit entity_type in event payload."""
        event = {"entity_type": "asset", "source": "test", "external_id": "1"}
        result = bridge._resolve_entity_type(event)
        assert result == EntityType.ASSET

    def test_event_type_mapping(self, bridge):
        """Test event type mapping."""
        event = {"event_type": "signal.message", "source": "t", "external_id": "1"}
        result = bridge._resolve_entity_type(event)
        assert result == EntityType.CONTACT

    def test_fallback_to_contact(self, bridge):
        """Test fallback to CONTACT."""
        event = {"source": "unknown", "external_id": "1"}
        result = bridge._resolve_entity_type(event)
        assert result == EntityType.CONTACT
