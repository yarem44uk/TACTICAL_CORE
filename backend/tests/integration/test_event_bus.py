"""Integration Test: EventBus Publish/Subscribe

Tests the core event bus functionality that forms the foundation
of the connector-to-service communication pipeline.

Author: WO-008-009 Implementation
Version: 1.0
"""

import pytest
import asyncio
from typing import List, Dict, Any
from uuid import uuid4

from app.core.event_bus import EventBus, BusMessage, Subscription


class TestEventBusBasics:
    """Test EventBus publish/subscribe functionality."""

    def test_event_bus_instantiation(self):
        """Test EventBus can be instantiated."""
        bus = EventBus()
        assert bus is not None
        assert isinstance(bus, EventBus)

    def test_subscribe_returns_subscription_id(self):
        """Test subscribing returns a subscription ID."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        sub_id = bus.subscribe(
            subscriber_id="test-handler",
            event_types=["test.event"],
            handler=handler,
        )
        assert sub_id is not None

    def test_publish_reaches_subscriber(self):
        """Test that published events reach subscribers."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(
            subscriber_id="test-handler",
            event_types=["test.event"],
            handler=handler,
        )

        test_event = {"event_id": "test-001", "data": "test"}
        bus.publish(
            event_type="test.event",
            event=test_event,
            context={"source": "test"},
        )

        assert len(received) == 1
        assert received[0]["event_id"] == "test-001"

    def test_multiple_subscribers_same_event(self):
        """Test multiple subscribers can receive same event."""
        bus = EventBus()
        received1 = []
        received2 = []

        def handler1(event: Any, context: Dict[str, Any]) -> None:
            received1.append(event)

        def handler2(event: Any, context: Dict[str, Any]) -> None:
            received2.append(event)

        bus.subscribe(subscriber_id="handler1", event_types=["multi.event"], handler=handler1)
        bus.subscribe(subscriber_id="handler2", event_types=["multi.event"], handler=handler2)

        bus.publish(
            event_type="multi.event",
            event={"message": "broadcast"},
            context={},
        )

        assert len(received1) == 1
        assert len(received2) == 1

    def test_unsubscribe_stops_events(self):
        """Test unsubscribing stops event delivery."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        sub_id = bus.subscribe(subscriber_id="handler", event_types=["unsub.event"], handler=handler)
        bus.publish("unsub.event", {"msg": "1"}, {})
        assert len(received) == 1

        bus.unsubscribe("handler")
        bus.publish("unsub.event", {"msg": "2"}, {})
        assert len(received) == 1  # No new events received

    def test_wildcard_subscription(self):
        """Test wildcard (*) subscription receives all events."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(subscriber_id="wildcard", event_types=["*"], handler=handler)

        bus.publish("radio.transmission", {"freq": "155.5"}, {})
        bus.publish("signal.message", {"text": "hello"}, {})

        assert len(received) >= 2


class TestConnectorEvents:
    """Test connector-specific event types."""

    def test_signal_message_event(self):
        """Test Signal message event format."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(subscriber_id="signal-test", event_types=["signal.message"], handler=handler)

        signal_event = {
            "event_type": "signal.message",
            "event_id": "sig-001",
            "timestamp": "2026-01-15T10:30:00Z",
            "source": "signal_connector",
            "data": {
                "message_id": "msg-123",
                "sender": "+1234567890",
                "chat_id": "chat-456",
                "message_text": "Test message",
            },
            "metadata": {},
        }

        bus.publish("signal.message", signal_event, {"connector": "signal"})

        assert len(received) == 1
        assert received[0]["event_type"] == "signal.message"

    def test_radio_transmission_event(self):
        """Test Radio transmission event format."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(subscriber_id="radio-test", event_types=["radio.transmission"], handler=handler)

        radio_event = {
            "event_type": "radio.transmission",
            "event_id": "radio-001",
            "timestamp": "2026-01-15T10:30:00Z",
            "source": "radio_connector",
            "data": {
                "frequency": "155.5",
                "callsign": "ALPHA-1",
            },
            "metadata": {},
        }

        bus.publish("radio.transmission", radio_event, {"connector": "radio"})

        assert len(received) == 1
        assert received[0]["event_type"] == "radio.transmission"
        assert received[0]["data"]["frequency"] == "155.5"

    def test_mqtt_message_event(self):
        """Test MQTT message event format."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(subscriber_id="mqtt-test", event_types=["mqtt.message"], handler=handler)

        mqtt_event = {
            "event_type": "mqtt.message",
            "event_id": "mqtt-001",
            "topic": "tactical/updates",
            "payload": {"status": "online"},
        }

        bus.publish("mqtt.message", mqtt_event, {"connector": "mqtt"})

        assert len(received) == 1

    def test_telegram_message_event(self):
        """Test Telegram message event format."""
        bus = EventBus()
        received = []

        def handler(event: Any, context: Dict[str, Any]) -> None:
            received.append(event)

        bus.subscribe(subscriber_id="telegram-test", event_types=["telegram.message"], handler=handler)

        telegram_event = {
            "event_type": "telegram.message",
            "event_id": "tg-001",
            "data": {
                "message_id": 12345,
                "chat_id": -98765,
                "from_user": {"id": 111, "username": "testuser"},
                "text": "Telegram test message",
            },
        }

        bus.publish("telegram.message", telegram_event, {"connector": "telegram"})

        assert len(received) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
