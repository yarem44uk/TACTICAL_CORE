"""Test suite for MQTT Connector.

Tests verify:
- Valid MQTT message parsing
- Topic extraction
- Payload extraction and decoding
- Malformed/invalid payload handling
- Canonical Event creation
- Event Bus publication
- Dependency injection
- No direct Repository access
- Observation Service integration

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from app.core.event_bus import EventBus
from app.connectors.mqtt.connector import MQTTConnector, MQTTConnectorError
from app.connectors.mqtt.parser import MQTTParser, MQTTParserError
from app.connectors.mqtt.models import MQTTMessage, MQTTEvent
from app.connectors.mqtt.service import MQTTService, get_mqtt_service


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a clean EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def parser():
    """Create an MQTTParser instance for testing."""
    return MQTTParser()


@pytest.fixture
def connector(event_bus, parser):
    """Create an MQTTConnector with injected dependencies."""
    return MQTTConnector(event_bus=event_bus, parser=parser)


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestMQTTParser:
    """Tests for MQTTParser."""

    def test_parse_valid_message(self, parser):
        """Test parsing a valid MQTT message."""
        message = parser.parse(
            topic="tactical/sensors/temperature",
            payload="Temperature: 25.5C",
            qos=1,
            client_id="sensor-001",
        )

        assert isinstance(message, MQTTMessage)
        assert message.topic == "tactical/sensors/temperature"
        assert message.payload == "Temperature: 25.5C"
        assert message.qos == 1
        assert message.client_id == "sensor-001"

    def test_parse_with_bytes_payload(self, parser):
        """Test parsing bytes payload."""
        message = parser.parse(
            topic="tactical/data",
            payload=b"Binary data here",
        )

        assert message.payload == "Binary data here"

    def test_parse_with_dict_payload(self, parser):
        """Test parsing dict payload (JSON)."""
        message = parser.parse(
            topic="tactical/sensors",
            payload={"temperature": 25.5, "humidity": 60},
        )

        assert "temperature" in message.payload
        assert "25.5" in message.payload

    def test_parse_empty_topic_raises_error(self, parser):
        """Test that empty topic raises MQTTParserError."""
        with pytest.raises(MQTTParserError) as exc_info:
            parser.parse(topic="", payload="data")
        assert "Empty topic" in str(exc_info.value)

    def test_parse_empty_payload_raises_error(self, parser):
        """Test that empty payload raises MQTTParserError."""
        with pytest.raises(MQTTParserError) as exc_info:
            parser.parse(topic="test/topic", payload=None)
        assert "Empty payload" in str(exc_info.value)

    def test_parse_with_timestamp(self, parser):
        """Test parsing with explicit timestamp."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        message = parser.parse(
            topic="test/topic",
            payload="data",
            timestamp=ts,
        )

        assert message.timestamp == ts

    def test_parse_timestamp_to_utc(self, parser):
        """Test that timestamp is normalized to UTC."""
        message = parser.parse(
            topic="test/topic",
            payload="data",
            timestamp=1700000000,
        )

        assert message.timestamp.tzinfo == timezone.utc

    def test_parse_dict_valid(self, parser):
        """Test parsing from dictionary."""
        message_dict = {
            "topic": "test/topic",
            "payload": "test data",
            "qos": 2,
            "client_id": "client-123",
            "retain": True,
        }

        message = parser.parse_dict(message_dict)

        assert message.topic == "test/topic"
        assert message.payload == "test data"
        assert message.qos == 2
        assert message.retain is True

    def test_parse_dict_missing_topic(self, parser):
        """Test that missing topic raises error."""
        with pytest.raises(MQTTParserError) as exc_info:
            parser.parse_dict({"payload": "data"})
        assert "topic" in str(exc_info.value)

    def test_parse_dict_missing_payload(self, parser):
        """Test that missing payload raises error."""
        with pytest.raises(MQTTParserError) as exc_info:
            parser.parse_dict({"topic": "test"})
        assert "payload" in str(exc_info.value)


# =============================================================================
# MODELS TESTS
# =============================================================================

class TestMQTTMessage:
    """Tests for MQTTMessage model."""

    def test_to_dict(self):
        """Test MQTTMessage serialization."""
        message = MQTTMessage(
            topic="test/topic",
            payload="data",
            qos=1,
        )

        msg_dict = message.to_dict()
        assert msg_dict["topic"] == "test/topic"
        assert msg_dict["payload"] == "data"
        assert msg_dict["qos"] == 1

    def test_has_metadata(self):
        """Test has_metadata property."""
        msg_no_meta = MQTTMessage(topic="t", payload="d")
        assert msg_no_meta.has_metadata is False

        msg_with_meta = MQTTMessage(topic="t", payload="d", client_id="c1")
        assert msg_with_meta.has_metadata is True


class TestMQTTEvent:
    """Tests for MQTTEvent model."""

    def test_from_mqtt_message(self, parser):
        """Test creating MQTTEvent from MQTTMessage."""
        message = parser.parse(
            topic="tactical/sensors",
            payload="sensor data",
            qos=1,
        )
        event = MQTTEvent.from_mqtt_message(message)

        assert event.event_type == "mqtt.message"
        assert event.topic == "tactical/sensors"
        assert event.payload == "sensor data"
        assert event.qos == 1
        assert event.source == "mqtt_connector"

    def test_to_dict(self, parser):
        """Test MQTTEvent serialization."""
        message = parser.parse(topic="t", payload="d")
        event = MQTTEvent.from_mqtt_message(message)
        event_dict = event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == "mqtt.message"
        assert event_dict["topic"] == "t"
        assert "timestamp" in event_dict

    def test_event_has_unique_id(self, parser):
        """Test that each event has a unique ID."""
        message = parser.parse(topic="t", payload="d")
        event1 = MQTTEvent.from_mqtt_message(message)
        event2 = MQTTEvent.from_mqtt_message(message)

        assert event1.event_id != event2.event_id


# =============================================================================
# CONNECTOR TESTS
# =============================================================================

class TestMQTTConnector:
    """Tests for MQTTConnector."""

    def test_initialization(self, event_bus, parser):
        """Test connector initialization."""
        connector = MQTTConnector(event_bus=event_bus, parser=parser)

        assert connector.is_enabled is True
        assert connector.message_count == 0
        assert connector.error_count == 0

    def test_initialization_with_default_parser(self, event_bus):
        """Test connector creates default parser if none provided."""
        connector = MQTTConnector(event_bus=event_bus)

        assert connector._parser is not None
        assert isinstance(connector._parser, MQTTParser)

    def test_enable_disable(self, connector):
        """Test enable/disable connector."""
        connector.disable()
        assert connector.is_enabled is False

        connector.enable()
        assert connector.is_enabled is True

    def test_receive_message_returns_event(self, connector):
        """Test receiving a valid message returns MQTTEvent."""
        event = connector.receive_message(
            topic="tactical/sensors",
            payload="test data",
        )

        assert event is not None
        assert isinstance(event, MQTTEvent)
        assert event.topic == "tactical/sensors"

    def test_receive_message_increments_count(self, connector):
        """Test message count is incremented on success."""
        connector.receive_message(topic="t1", payload="d1")
        connector.receive_message(topic="t2", payload="d2")

        assert connector.message_count == 2

    def test_receive_message_skips_when_disabled(self, connector):
        """Test messages are skipped when connector is disabled."""
        connector.disable()
        event = connector.receive_message(topic="t", payload="d")

        assert event is None
        assert connector.message_count == 0

    def test_receive_message_publishes_to_event_bus(self, connector, event_bus):
        """Test message is published to Event Bus."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="test-capture",
            handler=capture_handler,
            event_types=["mqtt.message"],
        )

        connector.receive_message(topic="t", payload="d")

        assert len(published_events) == 1
        assert published_events[0]["topic"] == "t"

    def test_receive_message_normalizes_to_mqtt_event(self, connector):
        """Test message is normalized to MQTTEvent format."""
        event = connector.receive_message(
            topic="tactical/sensors",
            payload="sensor data",
            qos=1,
        )

        assert event.event_type == "mqtt.message"
        assert event.source == "mqtt_connector"
        assert event.payload == "sensor data"

    def test_receive_message_with_malformed_payload(self, connector):
        """Test malformed message is handled gracefully."""
        event = connector.receive_message(topic="", payload="data")

        assert event is None
        assert connector.error_count == 1

    def test_receive_batch(self, connector):
        """Test batch message processing."""
        messages = [
            {"topic": "t1", "payload": "d1"},
            {"topic": "t2", "payload": "d2"},
        ]

        events = connector.receive_batch(messages)

        assert len(events) == 2
        assert connector.message_count == 2

    def test_health_check(self, connector):
        """Test health check returns correct status."""
        connector.receive_message(topic="t", payload="d")

        health = connector.health_check()

        assert health["connector"] == "mqtt"
        assert health["messages_processed"] == 1
        assert health["status"] == "healthy"


# =============================================================================
# SERVICE TESTS
# =============================================================================

class TestMQTTService:
    """Tests for MQTTService."""

    def test_service_creates_connector(self, event_bus):
        """Test service initializes with a connector."""
        service = MQTTService(event_bus=event_bus)

        assert service.connector is not None
        assert isinstance(service.connector, MQTTConnector)

    def test_service_receives_message(self, event_bus):
        """Test service receive_message method."""
        service = MQTTService(event_bus=event_bus)
        result = service.receive_message(topic="t", payload="d")

        assert result is True

    def test_service_receives_message_returns_false_on_failure(self, event_bus):
        """Test service returns False on malformed message."""
        service = MQTTService(event_bus=event_bus)
        result = service.receive_message(topic="", payload="d")

        assert result is False

    def test_service_singleton(self, event_bus):
        """Test service singleton behavior."""
        MQTTService.reset_instance()

        service1 = MQTTService.get_instance(event_bus)
        service2 = MQTTService.get_instance(event_bus)

        assert service1 is service2

        MQTTService.reset_instance()

    def test_service_uses_supplied_event_bus(self, event_bus):
        """Test service uses the supplied EventBus."""
        service = MQTTService(event_bus=event_bus)

        assert service.event_bus is event_bus
        assert service.connector._bus is event_bus


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestMQTTConnectorIntegration:
    """Integration tests for MQTTConnector with EventBus."""

    def test_full_pipeline_valid_message(self, event_bus):
        """Test complete pipeline from MQTT message to Event Bus."""
        connector = MQTTConnector(event_bus=event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe(
            subscriber_id="integration-test",
            handler=handler,
            event_types=["mqtt.message"],
        )

        event = connector.receive_message(
            topic="tactical/sensors/temperature",
            payload="Temperature: 25.5C",
            qos=1,
        )

        assert event is not None
        assert len(received) == 1
        assert received[0]["topic"] == "tactical/sensors/temperature"
        assert received[0]["payload"] == "Temperature: 25.5C"
        assert received[0]["event_type"] == "mqtt.message"

    def test_event_type_is_mqtt_message(self, event_bus):
        """Test that event_type is correctly set to mqtt.message."""
        connector = MQTTConnector(event_bus=event_bus)

        event = connector.receive_message(topic="test", payload="data")

        assert event.event_type == "mqtt.message"

    def test_no_direct_repository_access(self, connector):
        """Test connector does not access Repository directly."""
        event = connector.receive_message(topic="test", payload="data")

        assert event is not None
        # Verify no Repository import exists
        import app.connectors.mqtt.connector as connector_module
        source = dir(connector_module)
        assert "Repository" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
