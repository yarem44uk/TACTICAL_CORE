"""Test suite for Signal Connector.

Tests verify:
- Valid Signal message parsing
- Malformed payload handling
- Normalization
- Event creation
- Event Bus publication
- Connector initialization
- Error handling

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.connectors.signal.connector import (
    SignalConnector,
    SignalConnectorError,
)
from app.connectors.signal.parser import (
    SignalParser,
    SignalParserError,
)
from app.connectors.signal.models import (
    Attachment,
    SignalMessage,
    SignalEvent,
)
from app.connectors.signal.service import SignalService
from app.core.event_bus import EventBus
from app.core.event_context import EventContext


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a clean EventBus instance for testing."""
    bus = EventBus()
    return bus


@pytest.fixture
def parser():
    """Create a SignalParser instance for testing."""
    return SignalParser()


@pytest.fixture
def connector(event_bus, parser):
    """Create a SignalConnector with injected dependencies."""
    return SignalConnector(event_bus=event_bus, parser=parser)


@pytest.fixture
def valid_payload():
    """Create a valid Signal message payload."""
    return {
        "message_id": "msg-001",
        "sender": "+1234567890",
        "chat_id": "chat-001",
        "timestamp": 1700000000,  # Unix timestamp
        "message_text": "Test message content",
        "attachments": [
            {
                "contentType": "image/png",
                "filename": "test.png",
                "size": 1024,
                "url": "https://example.com/test.png",
            }
        ],
    }


@pytest.fixture
def valid_payload_iso_timestamp():
    """Create a valid Signal message payload with ISO timestamp."""
    return {
        "message_id": "msg-002",
        "sender": "+9876543210",
        "chat_id": "chat-002",
        "timestamp": "2024-01-15T10:30:00Z",
        "message_text": "Another test message",
        "body": "Body field instead of message_text",
    }


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestSignalParser:
    """Tests for SignalParser."""

    def test_parse_valid_payload(self, parser, valid_payload):
        """Test parsing a valid Signal payload."""
        message = parser.parse(valid_payload)

        assert isinstance(message, SignalMessage)
        assert message.message_id == "msg-001"
        assert message.sender == "+1234567890"
        assert message.chat_id == "chat-001"
        assert message.message_text == "Test message content"
        assert len(message.attachments) == 1
        assert message.attachments[0].content_type == "image/png"

    def test_parse_with_iso_timestamp(self, parser, valid_payload_iso_timestamp):
        """Test parsing with ISO format timestamp."""
        message = parser.parse(valid_payload_iso_timestamp)

        assert isinstance(message.timestamp, datetime)
        assert message.message_text == "Another test message"

    def test_parse_with_body_field(self, parser):
        """Test parsing uses 'body' as fallback for message_text."""
        payload = {
            "message_id": "msg-003",
            "sender": "+111",
            "chat_id": "chat-003",
            "timestamp": 1700000000,
            "body": "Message from body field",
        }

        message = parser.parse(payload)
        assert message.message_text == "Message from body field"

    def test_parse_empty_attachments(self, parser):
        """Test parsing with no attachments."""
        payload = {
            "message_id": "msg-004",
            "sender": "+222",
            "chat_id": "chat-004",
            "timestamp": 1700000000,
            "message_text": "No attachments",
        }

        message = parser.parse(payload)
        assert message.attachments == []

    def test_parse_empty_payload_raises_error(self, parser):
        """Test that empty payload raises SignalParserError."""
        with pytest.raises(SignalParserError) as exc_info:
            parser.parse({})
        assert "Empty payload" in str(exc_info.value)

    def test_parse_missing_required_field_raises_error(self, parser):
        """Test that missing required field raises SignalParserError."""
        payload = {
            "message_id": "msg-005",
            "sender": "+333",
            # Missing chat_id and timestamp
        }

        with pytest.raises(SignalParserError) as exc_info:
            parser.parse(payload)
        assert "Missing required fields" in str(exc_info.value)

    def test_parse_missing_message_id(self, parser):
        """Test that missing message_id is detected."""
        payload = {
            "sender": "+444",
            "chat_id": "chat-005",
            "timestamp": 1700000000,
        }

        with pytest.raises(SignalParserError) as exc_info:
            parser.parse(payload)
        assert "message_id" in str(exc_info.value)

    def test_parse_missing_sender(self, parser):
        """Test that missing sender is detected."""
        payload = {
            "message_id": "msg-006",
            "chat_id": "chat-006",
            "timestamp": 1700000000,
        }

        with pytest.raises(SignalParserError) as exc_info:
            parser.parse(payload)
        assert "sender" in str(exc_info.value)

    def test_parse_stores_raw_payload(self, parser, valid_payload):
        """Test that raw payload is preserved."""
        message = parser.parse(valid_payload)
        assert message.raw_payload == valid_payload

    def test_parse_batch(self, parser, valid_payload):
        """Test parsing multiple payloads."""
        payloads = [valid_payload, valid_payload.copy(), valid_payload.copy()]
        payloads[2]["message_id"] = "msg-batched"

        messages = parser.parse_batch(payloads)
        assert len(messages) == 3
        assert messages[2].message_id == "msg-batched"

    def test_parse_batch_with_errors(self, parser):
        """Test batch parsing handles partial failures."""
        payloads = [
            {"message_id": "ok", "sender": "+1", "chat_id": "c1", "timestamp": 1700000000},
            {"message_id": "bad"},  # Missing fields
            {"message_id": "also-ok", "sender": "+2", "chat_id": "c2", "timestamp": 1700000000},
        ]

        messages = parser.parse_batch(payloads)
        assert len(messages) == 2

    def test_parse_timestamp_as_float(self, parser):
        """Test parsing timestamp as float."""
        payload = {
            "message_id": "msg-float",
            "sender": "+555",
            "chat_id": "chat-float",
            "timestamp": 1700000000.5,
            "message_text": "Float timestamp",
        }

        message = parser.parse(payload)
        assert isinstance(message.timestamp, datetime)


# =============================================================================
# MODELS TESTS
# =============================================================================

class TestSignalMessage:
    """Tests for SignalMessage model."""

    def test_from_dict(self, valid_payload):
        """Test creating SignalMessage from dict."""
        message = SignalMessage.from_dict(valid_payload)

        assert message.message_id == "msg-001"
        assert message.sender == "+1234567890"
        assert message.chat_id == "chat-001"
        assert len(message.attachments) == 1

    def test_from_dict_with_iso_timestamp(self):
        """Test from_dict with ISO timestamp."""
        payload = {
            "message_id": "msg-iso",
            "sender": "+666",
            "chat_id": "chat-iso",
            "timestamp": "2024-01-15T12:00:00Z",
            "body": "ISO timestamp test",
        }

        message = SignalMessage.from_dict(payload)
        assert isinstance(message.timestamp, datetime)

    def test_from_dict_with_int_timestamp(self):
        """Test from_dict with integer timestamp."""
        payload = {
            "message_id": "msg-int",
            "sender": "+777",
            "chat_id": "chat-int",
            "timestamp": 1700000000,
            "body": "Int timestamp test",
        }

        message = SignalMessage.from_dict(payload)
        assert isinstance(message.timestamp, datetime)

    def test_from_dict_alternate_field_names(self):
        """Test from_dict handles alternate field names."""
        payload = {
            "id": "alt-id",
            "source": "alt-sender",
            "conversationId": "alt-chat",
            "timestamp": 1700000000,
            "body": "Alternate field names",
        }

        message = SignalMessage.from_dict(payload)
        assert message.message_id == "alt-id"
        assert message.sender == "alt-sender"
        assert message.chat_id == "alt-chat"


class TestSignalEvent:
    """Tests for SignalEvent model."""

    def test_from_signal_message(self, parser, valid_payload):
        """Test creating SignalEvent from SignalMessage."""
        message = parser.parse(valid_payload)
        event = SignalEvent.from_signal_message(message)

        assert event.event_type == "signal.message"
        assert event.message_id == "msg-001"
        assert event.sender == "+1234567890"
        assert event.chat_id == "chat-001"
        assert event.source == "signal_connector"
        assert event.message_text == "Test message content"

    def test_to_dict(self, parser, valid_payload):
        """Test SignalEvent serialization to dict."""
        message = parser.parse(valid_payload)
        event = SignalEvent.from_signal_message(message)
        event_dict = event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == "signal.message"
        assert event_dict["message_id"] == "msg-001"
        assert event_dict["sender"] == "+1234567890"
        assert "timestamp" in event_dict
        assert "attachments" in event_dict

    def test_event_has_unique_id(self, parser, valid_payload):
        """Test that each event has a unique ID."""
        message = parser.parse(valid_payload)
        event1 = SignalEvent.from_signal_message(message)
        event2 = SignalEvent.from_signal_message(message)

        assert event1.event_id != event2.event_id

    def test_event_has_timestamp(self, parser, valid_payload):
        """Test that event has a timestamp."""
        message = parser.parse(valid_payload)
        event = SignalEvent.from_signal_message(message)

        assert isinstance(event.timestamp, datetime)


class TestAttachment:
    """Tests for Attachment model."""

    def test_attachment_to_dict(self):
        """Test Attachment serialization."""
        attachment = Attachment(
            content_type="image/jpeg",
            filename="photo.jpg",
            size=2048,
            url="https://example.com/photo.jpg",
        )

        att_dict = attachment.to_dict()
        assert att_dict["content_type"] == "image/jpeg"
        assert att_dict["filename"] == "photo.jpg"
        assert att_dict["size"] == 2048

    def test_attachment_default_content_type(self):
        """Test default content type."""
        attachment = Attachment(content_type="application/octet-stream")
        att_dict = attachment.to_dict()
        assert att_dict["content_type"] == "application/octet-stream"


# =============================================================================
# CONNECTOR TESTS
# =============================================================================

class TestSignalConnector:
    """Tests for SignalConnector."""

    def test_initialization(self, event_bus, parser):
        """Test connector initialization."""
        connector = SignalConnector(event_bus=event_bus, parser=parser)

        assert connector.is_enabled is True
        assert connector.message_count == 0
        assert connector.error_count == 0

    def test_initialization_with_default_parser(self, event_bus):
        """Test connector creates default parser if none provided."""
        connector = SignalConnector(event_bus=event_bus)

        assert connector._parser is not None
        assert isinstance(connector._parser, SignalParser)

    def test_enable_connector(self, connector):
        """Test enabling the connector."""
        connector.disable()
        assert connector.is_enabled is False

        connector.enable()
        assert connector.is_enabled is True

    def test_disable_connector(self, connector):
        """Test disabling the connector."""
        connector.disable()
        assert connector.is_enabled is False

    def test_receive_message_returns_event(self, connector, valid_payload):
        """Test receiving a valid message returns SignalEvent."""
        event = connector.receive_message(valid_payload)

        assert event is not None
        assert isinstance(event, SignalEvent)
        assert event.message_id == "msg-001"

    def test_receive_message_increments_count(self, connector, valid_payload):
        """Test message count is incremented on success."""
        connector.receive_message(valid_payload)
        assert connector.message_count == 1

        connector.receive_message(valid_payload)
        assert connector.message_count == 2

    def test_receive_message_skips_when_disabled(self, connector, valid_payload):
        """Test messages are skipped when connector is disabled."""
        connector.disable()
        event = connector.receive_message(valid_payload)

        assert event is None
        assert connector.message_count == 0

    def test_receive_message_publishes_to_event_bus(self, connector, event_bus, valid_payload):
        """Test message is published to Event Bus."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="test-capture",
            handler=capture_handler,
            event_types=["signal.message"],
        )

        connector.receive_message(valid_payload)

        assert len(published_events) == 1
        assert published_events[0]["message_id"] == "msg-001"

    def test_receive_message_normalizes_to_signal_event(self, connector, valid_payload):
        """Test message is normalized to SignalEvent format."""
        event = connector.receive_message(valid_payload)

        assert event.event_type == "signal.message"
        assert event.source == "signal_connector"
        assert event.message_text == "Test message content"

    def test_receive_message_with_malformed_payload(self, connector):
        """Test malformed payload is handled gracefully."""
        malformed = {"message_id": "bad", "sender": "+1"}  # Missing required fields

        event = connector.receive_message(malformed)

        assert event is None
        assert connector.error_count == 1

    def test_receive_message_with_empty_payload(self, connector):
        """Test empty payload is handled gracefully."""
        event = connector.receive_message({})

        assert event is None
        assert connector.error_count == 1

    def test_receive_message_preserves_attachments(self, connector, event_bus, valid_payload):
        """Test that attachments are preserved in the event."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="attachment-test",
            handler=capture_handler,
            event_types=["signal.message"],
        )

        connector.receive_message(valid_payload)

        assert len(published_events) == 1
        assert len(published_events[0]["attachments"]) == 1
        assert published_events[0]["attachments"][0]["content_type"] == "image/png"

    def test_receive_batch(self, connector, valid_payload):
        """Test batch message processing."""
        payloads = [
            valid_payload,
            valid_payload.copy(),
            valid_payload.copy(),
        ]
        payloads[1]["message_id"] = "msg-batch-2"
        payloads[2]["message_id"] = "msg-batch-3"

        events = connector.receive_batch(payloads)

        assert len(events) == 3
        assert connector.message_count == 3

    def test_receive_batch_with_failures(self, connector):
        """Test batch processing handles partial failures."""
        payloads = [
            {"message_id": "ok1", "sender": "+1", "chat_id": "c1", "timestamp": 1700000000},
            {"message_id": "bad"},  # Missing fields
            {"message_id": "ok2", "sender": "+2", "chat_id": "c2", "timestamp": 1700000000},
        ]

        events = connector.receive_batch(payloads)

        assert len(events) == 2
        assert connector.message_count == 2
        assert connector.error_count == 1

    def test_health_check(self, connector, valid_payload):
        """Test health check returns correct status."""
        connector.receive_message(valid_payload)

        health = connector.health_check()

        assert health["connector"] == "signal"
        assert health["enabled"] is True
        assert health["messages_processed"] == 1
        assert health["errors"] == 0
        assert health["status"] == "healthy"

    def test_health_check_degraded_status(self, connector):
        """Test health check shows degraded status on errors."""
        connector.receive_message({})  # Will fail
        connector.receive_message({"bad": "payload"})  # Will fail

        health = connector.health_check()

        assert health["errors"] == 2
        assert health["status"] == "degraded"


class TestSignalConnectorErrorHandling:
    """Tests for SignalConnector error handling."""

    def test_parser_error_does_not_crash_connector(self, connector):
        """Test that parser errors are handled gracefully."""
        # No exception should propagate
        result = connector.receive_message({"invalid": "data"})
        assert result is None
        assert connector.error_count == 1

    def test_multiple_failures_increment_error_count(self, connector):
        """Test error count increments on each failure."""
        connector.receive_message({"bad": "1"})
        connector.receive_message({"bad": "2"})
        connector.receive_message({"bad": "3"})

        assert connector.error_count == 3

    def test_successful_message_after_failure(self, connector, valid_payload):
        """Test successful messages still work after failures."""
        connector.receive_message({"bad": "1"})
        event = connector.receive_message(valid_payload)

        assert event is not None
        assert connector.message_count == 1
        assert connector.error_count == 1


# =============================================================================
# SERVICE TESTS
# =============================================================================

class TestSignalService:
    """Tests for SignalService."""

    def test_service_creates_connector(self, event_bus):
        """Test service initializes with a connector."""
        service = SignalService(event_bus=event_bus)

        assert service.connector is not None
        assert isinstance(service.connector, SignalConnector)

    def test_service_receives_message(self, event_bus, valid_payload):
        """Test service receive_message method."""
        service = SignalService(event_bus=event_bus)
        result = service.receive_message(valid_payload)

        assert result is True

    def test_service_receives_message_returns_false_on_failure(self, event_bus):
        """Test service returns False on malformed message."""
        service = SignalService(event_bus=event_bus)
        result = service.receive_message({})

        assert result is False

    def test_service_health_check(self, event_bus):
        """Test service health_check method."""
        service = SignalService(event_bus=event_bus)
        health = service.health_check()

        assert health["connector"] == "signal"

    def test_service_singleton(self, event_bus):
        """Test service singleton behavior."""
        SignalService.reset_instance()

        service1 = SignalService.get_instance()
        service2 = SignalService.get_instance()

        assert service1 is service2

        SignalService.reset_instance()

    def test_get_signal_service_function(self, event_bus):
        """Test get_signal_service factory function."""
        SignalService.reset_instance()

        from app.connectors.signal.service import get_signal_service

        service = get_signal_service(event_bus=event_bus)
        assert service is not None
        assert isinstance(service, SignalService)

        SignalService.reset_instance()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestSignalConnectorIntegration:
    """Integration tests for SignalConnector with EventBus."""

    def test_full_pipeline_valid_message(self, event_bus):
        """Test complete pipeline from raw payload to Event Bus."""
        connector = SignalConnector(event_bus=event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe(
            subscriber_id="integration-test",
            handler=handler,
            event_types=["signal.message"],
        )

        payload = {
            "message_id": "integration-001",
            "sender": "+1234567890",
            "chat_id": "integration-chat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_text": "Integration test message",
        }

        event = connector.receive_message(payload)

        assert event is not None
        assert len(received) == 1
        assert received[0]["message_id"] == "integration-001"
        assert received[0]["sender"] == "+1234567890"

    def test_connector_publishes_to_correct_event_type(self, event_bus):
        """Test connector publishes to signal.message event type."""
        connector = SignalConnector(event_bus=event_bus)

        def handler(event, context):
            pass

        event_bus.subscribe(
            subscriber_id="type-test",
            handler=handler,
            event_types=["signal.message"],
        )

        payload = {
            "message_id": "type-001",
            "sender": "+111",
            "chat_id": "chat-type",
            "timestamp": 1700000000,
            "message_text": "Type test",
        }

        connector.receive_message(payload)

        # Verify the connector published with correct type
        stats = event_bus.statistics
        assert stats["total_messages_published"] >= 1

    def test_multiple_subscribers_receive_event(self, event_bus):
        """Test multiple subscribers can receive the same event."""
        connector = SignalConnector(event_bus=event_bus)
        received_by_sub1 = []
        received_by_sub2 = []

        def handler1(event, context):
            received_by_sub1.append(event)

        def handler2(event, context):
            received_by_sub2.append(event)

        event_bus.subscribe(
            subscriber_id="subscriber-1",
            handler=handler1,
            event_types=["signal.message"],
        )
        event_bus.subscribe(
            subscriber_id="subscriber-2",
            handler=handler2,
            event_types=["signal.message"],
        )

        payload = {
            "message_id": "multi-sub-001",
            "sender": "+222",
            "chat_id": "chat-multi",
            "timestamp": 1700000000,
            "message_text": "Multiple subscribers test",
        }

        connector.receive_message(payload)

        assert len(received_by_sub1) == 1
        assert len(received_by_sub2) == 1
        assert received_by_sub1[0]["message_id"] == "multi-sub-001"
        assert received_by_sub2[0]["message_id"] == "multi-sub-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
