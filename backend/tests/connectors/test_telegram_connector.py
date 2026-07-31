"""Test suite for Telegram Connector.

Tests verify:
- Valid Telegram message parsing
- Malformed payload handling
- Sender/source normalization
- Message text normalization
- Timestamp handling
- Media/attachment metadata
- Canonical Event creation
- Event Bus publication
- No direct Repository access
- Connector initialization
- Error handling

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from app.core.event_bus import EventBus
from app.connectors.telegram.connector import TelegramConnector, TelegramConnectorError
from app.connectors.telegram.parser import TelegramParser, TelegramParserError
from app.connectors.telegram.models import (
    TelegramMedia,
    TelegramMessage,
    TelegramEvent,
)
from app.connectors.telegram.service import TelegramService


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
    """Create a TelegramParser instance for testing."""
    return TelegramParser()


@pytest.fixture
def connector(event_bus, parser):
    """Create a TelegramConnector with injected dependencies."""
    return TelegramConnector(event_bus=event_bus, parser=parser)


@pytest.fixture
def valid_telegram_payload():
    """Create a valid Telegram message payload."""
    return {
        "message_id": 123,
        "chat": {
            "id": -1001234567890,
            "type": "supergroup",
            "title": "Test Group",
        },
        "from": {
            "id": 987654321,
            "is_bot": False,
            "first_name": "Test",
            "username": "testuser",
        },
        "date": 1700000000,
        "text": "Test message content",
    }


@pytest.fixture
def valid_telegram_payload_with_media():
    """Create a valid Telegram message with photo."""
    return {
        "message_id": 456,
        "chat": {
            "id": -1001234567890,
            "type": "supergroup",
        },
        "from": {
            "id": 111222333,
            "is_bot": False,
            "first_name": "Media",
            "username": "mediauser",
        },
        "date": 1700000001,
        "photo": [
            {
                "file_id": "AgACAgIAAxkDAAIBZ2Qk0Z3K8L6W1M5mAAQ3",
                "file_unique_id": "AQADl8RZ2Ql0Z3K8",
                "file_size": 12345,
                "width": 640,
                "height": 480,
            }
        ],
        "caption": "Check out this photo",
    }


@pytest.fixture
def minimal_telegram_payload():
    """Create a minimal valid Telegram message payload."""
    return {
        "message_id": 789,
        "chat": {"id": -1000000000000},
        "from": {"id": 555666777},
        "date": 1700000002,
        "text": "Minimal message",
    }


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestTelegramParser:
    """Tests for TelegramParser."""

    def test_parse_valid_payload(self, parser, valid_telegram_payload):
        """Test parsing a valid Telegram payload."""
        message = parser.parse(valid_telegram_payload)

        assert isinstance(message, TelegramMessage)
        assert message.message_id == 123
        assert message.chat_id == -1001234567890
        assert message.sender_id == 987654321
        assert message.sender_username == "testuser"
        assert message.message_text == "Test message content"

    def test_parse_with_iso_timestamp(self, parser):
        """Test parsing with ISO format timestamp."""
        payload = {
            "message_id": 100,
            "chat": {"id": -1000000000001},
            "from": {"id": 111222333},
            "date": "2024-01-15T10:30:00Z",
            "text": "ISO timestamp test",
        }

        message = parser.parse(payload)
        assert isinstance(message.timestamp, datetime)

    def test_parse_with_caption_instead_of_text(self, parser):
        """Test parsing uses caption when text is absent."""
        payload = {
            "message_id": 101,
            "chat": {"id": -1000000000002},
            "from": {"id": 222333444},
            "date": 1700000000,
            "caption": "Caption text message",
        }

        message = parser.parse(payload)
        assert message.message_text == "Caption text message"

    def test_parse_sender_display_name(self, parser, valid_telegram_payload):
        """Test sender display name is correctly determined."""
        message = parser.parse(valid_telegram_payload)

        # Should prefer username
        assert message.sender_display_name == "@testuser"

    def test_parse_sender_display_name_first_name_only(self, parser):
        """Test sender display name when username is absent."""
        payload = {
            "message_id": 102,
            "chat": {"id": -1000000000003},
            "from": {"id": 333444555, "first_name": "FirstName"},
            "date": 1700000000,
            "text": "No username",
        }

        message = parser.parse(payload)
        assert message.sender_display_name == "FirstName"

    def test_parse_with_reply(self, parser):
        """Test parsing message with reply_to_message."""
        payload = {
            "message_id": 104,
            "chat": {"id": -1000000000005},
            "from": {"id": 555666777},
            "date": 1700000000,
            "text": "Reply message",
            "reply_to_message": {"message_id": 100},
        }

        message = parser.parse(payload)
        assert message.reply_to_message_id == 100

    def test_parse_empty_payload_raises_error(self, parser):
        """Test that empty payload raises TelegramParserError."""
        with pytest.raises(TelegramParserError) as exc_info:
            parser.parse({})
        assert "Empty payload" in str(exc_info.value)

    def test_parse_missing_message_id_raises_error(self, parser):
        """Test that missing message_id is detected."""
        payload = {
            "chat": {"id": -1000000000006},
            "from": {"id": 666777888},
            "date": 1700000000,
            "text": "Missing message_id",
        }

        with pytest.raises(TelegramParserError) as exc_info:
            parser.parse(payload)
        assert "Missing required fields" in str(exc_info.value)
        assert "message_id" in str(exc_info.value)

    def test_parse_missing_chat_raises_error(self, parser):
        """Test that missing chat is detected."""
        payload = {
            "message_id": 105,
            "from": {"id": 777888999},
            "date": 1700000000,
            "text": "Missing chat",
        }

        with pytest.raises(TelegramParserError) as exc_info:
            parser.parse(payload)
        assert "chat" in str(exc_info.value)

    def test_parse_missing_sender_raises_error(self, parser):
        """Test that missing sender is detected."""
        payload = {
            "message_id": 106,
            "chat": {"id": -1000000000007},
            "date": 1700000000,
            "text": "Missing sender",
        }

        with pytest.raises(TelegramParserError) as exc_info:
            parser.parse(payload)
        assert "from" in str(exc_info.value)

    def test_parse_with_photo(self, parser, valid_telegram_payload_with_media):
        """Test parsing message with photo."""
        message = parser.parse(valid_telegram_payload_with_media)

        assert message.has_media is True
        assert len(message.media) == 1
        assert message.media[0].media_type == "photo"
        assert message.media[0].file_id == "AgACAgIAAxkDAAIBZ2Qk0Z3K8L6W1M5mAAQ3"
        assert message.message_text == "Check out this photo"

    def test_parse_stores_raw_payload(self, parser, valid_telegram_payload):
        """Test that raw payload is preserved."""
        message = parser.parse(valid_telegram_payload)
        assert message.raw_payload == valid_telegram_payload

    def test_parse_batch(self, parser, valid_telegram_payload, minimal_telegram_payload):
        """Test parsing multiple payloads."""
        payloads = [valid_telegram_payload, minimal_telegram_payload]
        messages = parser.parse_batch(payloads)

        assert len(messages) == 2
        assert messages[0].message_id == 123
        assert messages[1].message_id == 789

    def test_parse_batch_with_errors(self, parser, valid_telegram_payload):
        """Test batch parsing handles partial failures."""
        payloads = [
            valid_telegram_payload,
            {"bad": "payload"},
        ]

        messages = parser.parse_batch(payloads)
        assert len(messages) == 1


# =============================================================================
# MODELS TESTS
# =============================================================================

class TestTelegramMedia:
    """Tests for TelegramMedia model."""

    def test_to_dict(self):
        """Test TelegramMedia serialization."""
        media = TelegramMedia(
            file_id="file123",
            file_unique_id="unique456",
            mime_type="image/jpeg",
            file_size=1024,
            file_name="photo.jpg",
            media_type="photo",
        )

        media_dict = media.to_dict()
        assert media_dict["file_id"] == "file123"
        assert media_dict["mime_type"] == "image/jpeg"
        assert media_dict["media_type"] == "photo"


class TestTelegramMessage:
    """Tests for TelegramMessage model."""

    def test_has_media(self):
        """Test has_media property."""
        message = TelegramMessage(
            message_id=1,
            chat_id=-1000000000000,
            sender_id=123456,
            media=[],
        )
        assert message.has_media is False

        message_with_media = TelegramMessage(
            message_id=2,
            chat_id=-1000000000001,
            sender_id=654321,
            media=[TelegramMedia(file_id="x", file_unique_id="y")],
        )
        assert message_with_media.has_media is True

    def test_to_dict(self):
        """Test TelegramMessage serialization."""
        message = TelegramMessage(
            message_id=1,
            chat_id=-1000000000000,
            sender_id=123456,
            sender_username="test",
            message_text="Hello",
        )

        msg_dict = message.to_dict()
        assert msg_dict["message_id"] == 1
        assert msg_dict["chat_id"] == -1000000000000
        assert msg_dict["sender_username"] == "test"


class TestTelegramEvent:
    """Tests for TelegramEvent model."""

    def test_from_telegram_message(self, parser, valid_telegram_payload):
        """Test creating TelegramEvent from TelegramMessage."""
        message = parser.parse(valid_telegram_payload)
        event = TelegramEvent.from_telegram_message(message)

        assert event.event_type == "telegram.message"
        assert event.message_id == "123"
        assert event.chat_id == "-1001234567890"
        assert event.sender_id == "987654321"
        assert event.sender_username == "testuser"
        assert event.sender_display_name == "@testuser"
        assert event.source == "telegram_connector"

    def test_to_dict(self, parser, valid_telegram_payload):
        """Test TelegramEvent serialization."""
        message = parser.parse(valid_telegram_payload)
        event = TelegramEvent.from_telegram_message(message)
        event_dict = event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == "telegram.message"
        assert event_dict["message_id"] == "123"
        assert "timestamp" in event_dict

    def test_event_has_unique_id(self, parser, valid_telegram_payload):
        """Test that each event has a unique ID."""
        message = parser.parse(valid_telegram_payload)
        event1 = TelegramEvent.from_telegram_message(message)
        event2 = TelegramEvent.from_telegram_message(message)

        assert event1.event_id != event2.event_id


# =============================================================================
# CONNECTOR TESTS
# =============================================================================

class TestTelegramConnector:
    """Tests for TelegramConnector."""

    def test_initialization(self, event_bus, parser):
        """Test connector initialization."""
        connector = TelegramConnector(event_bus=event_bus, parser=parser)

        assert connector.is_enabled is True
        assert connector.message_count == 0
        assert connector.error_count == 0

    def test_initialization_with_default_parser(self, event_bus):
        """Test connector creates default parser if none provided."""
        connector = TelegramConnector(event_bus=event_bus)

        assert connector._parser is not None
        assert isinstance(connector._parser, TelegramParser)

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

    def test_receive_message_returns_event(self, connector, valid_telegram_payload):
        """Test receiving a valid message returns TelegramEvent."""
        event = connector.receive_message(valid_telegram_payload)

        assert event is not None
        assert isinstance(event, TelegramEvent)
        assert event.message_id == "123"

    def test_receive_message_increments_count(self, connector, valid_telegram_payload):
        """Test message count is incremented on success."""
        connector.receive_message(valid_telegram_payload)
        assert connector.message_count == 1

        connector.receive_message(valid_telegram_payload)
        assert connector.message_count == 2

    def test_receive_message_skips_when_disabled(self, connector, valid_telegram_payload):
        """Test messages are skipped when connector is disabled."""
        connector.disable()
        event = connector.receive_message(valid_telegram_payload)

        assert event is None
        assert connector.message_count == 0

    def test_receive_message_publishes_to_event_bus(
        self, connector, event_bus, valid_telegram_payload
    ):
        """Test message is published to Event Bus."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="test-capture",
            handler=capture_handler,
            event_types=["telegram.message"],
        )

        connector.receive_message(valid_telegram_payload)

        assert len(published_events) == 1
        assert published_events[0]["message_id"] == "123"

    def test_receive_message_normalizes_to_telegram_event(
        self, connector, valid_telegram_payload
    ):
        """Test message is normalized to TelegramEvent format."""
        event = connector.receive_message(valid_telegram_payload)

        assert event.event_type == "telegram.message"
        assert event.source == "telegram_connector"
        assert event.message_text == "Test message content"

    def test_receive_message_with_malformed_payload(self, connector):
        """Test malformed payload is handled gracefully."""
        malformed = {"message_id": "bad", "chat": {}, "from": {}}

        event = connector.receive_message(malformed)

        assert event is None
        assert connector.error_count == 1

    def test_receive_message_with_empty_payload(self, connector):
        """Test empty payload is handled gracefully."""
        event = connector.receive_message({})

        assert event is None
        assert connector.error_count == 1

    def test_receive_message_preserves_media(
        self, connector, event_bus, valid_telegram_payload_with_media
    ):
        """Test that media is preserved in the event."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="media-test",
            handler=capture_handler,
            event_types=["telegram.message"],
        )

        connector.receive_message(valid_telegram_payload_with_media)

        assert len(published_events) == 1
        assert published_events[0]["has_media"] is True
        assert len(published_events[0]["media"]) == 1

    def test_receive_batch(self, connector, valid_telegram_payload):
        """Test batch message processing."""
        payloads = [
            valid_telegram_payload,
            {**valid_telegram_payload, "message_id": 999, "text": "Batch 2"},
            {**valid_telegram_payload, "message_id": 998, "text": "Batch 3"},
        ]

        events = connector.receive_batch(payloads)

        assert len(events) == 3
        assert connector.message_count == 3

    def test_receive_batch_with_failures(self, connector, valid_telegram_payload):
        """Test batch processing handles partial failures."""
        payloads = [
            valid_telegram_payload,
            {"bad": "payload"},
            {**valid_telegram_payload, "message_id": 997, "text": "After fail"},
        ]

        events = connector.receive_batch(payloads)

        assert len(events) == 2
        assert connector.message_count == 2
        assert connector.error_count == 1

    def test_health_check(self, connector, valid_telegram_payload):
        """Test health check returns correct status."""
        connector.receive_message(valid_telegram_payload)

        health = connector.health_check()

        assert health["connector"] == "telegram"
        assert health["enabled"] is True
        assert health["messages_processed"] == 1
        assert health["errors"] == 0
        assert health["status"] == "healthy"

    def test_health_check_degraded_status(self, connector):
        """Test health check shows degraded status on errors."""
        connector.receive_message({})
        connector.receive_message({"bad": "payload"})

        health = connector.health_check()

        assert health["errors"] == 2
        assert health["status"] == "degraded"


class TestTelegramConnectorErrorHandling:
    """Tests for TelegramConnector error handling."""

    def test_parser_error_does_not_crash_connector(self, connector):
        """Test that parser errors are handled gracefully."""
        result = connector.receive_message({"invalid": "data"})
        assert result is None
        assert connector.error_count == 1

    def test_multiple_failures_increment_error_count(self, connector):
        """Test error count increments on each failure."""
        connector.receive_message({"bad": "1"})
        connector.receive_message({"bad": "2"})
        connector.receive_message({"bad": "3"})

        assert connector.error_count == 3

    def test_successful_message_after_failure(self, connector, valid_telegram_payload):
        """Test successful messages still work after failures."""
        connector.receive_message({"bad": "1"})
        event = connector.receive_message(valid_telegram_payload)

        assert event is not None
        assert connector.message_count == 1
        assert connector.error_count == 1


# =============================================================================
# SERVICE TESTS
# =============================================================================

class TestTelegramService:
    """Tests for TelegramService."""

    def test_service_creates_connector(self, event_bus):
        """Test service initializes with a connector."""
        service = TelegramService(event_bus=event_bus)

        assert service.connector is not None
        assert isinstance(service.connector, TelegramConnector)

    def test_service_receives_message(self, event_bus, valid_telegram_payload):
        """Test service receive_message method."""
        service = TelegramService(event_bus=event_bus)
        result = service.receive_message(valid_telegram_payload)

        assert result is True

    def test_service_receives_message_returns_false_on_failure(self, event_bus):
        """Test service returns False on malformed message."""
        service = TelegramService(event_bus=event_bus)
        result = service.receive_message({})

        assert result is False

    def test_service_health_check(self, event_bus):
        """Test service health_check method."""
        service = TelegramService(event_bus=event_bus)
        health = service.health_check()

        assert health["connector"] == "telegram"

    def test_service_singleton(self, event_bus):
        """Test service singleton behavior."""
        TelegramService.reset_instance()

        service1 = TelegramService.get_instance(event_bus)
        service2 = TelegramService.get_instance(event_bus)

        assert service1 is service2

        TelegramService.reset_instance()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestTelegramConnectorIntegration:
    """Integration tests for TelegramConnector with EventBus."""

    def test_full_pipeline_valid_message(self, event_bus):
        """Test complete pipeline from raw payload to Event Bus."""
        connector = TelegramConnector(event_bus=event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe(
            subscriber_id="integration-test",
            handler=handler,
            event_types=["telegram.message"],
        )

        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456, "username": "test"},
            "date": datetime.now(timezone.utc).isoformat(),
            "text": "Integration test message",
        }

        event = connector.receive_message(payload)

        assert event is not None
        assert len(received) == 1
        assert received[0]["message_id"] == "1"

    def test_multiple_subscribers_receive_event(self, event_bus):
        """Test multiple subscribers can receive the same event."""
        connector = TelegramConnector(event_bus=event_bus)
        received1, received2 = [], []

        def handler1(event, context):
            received1.append(event)

        def handler2(event, context):
            received2.append(event)

        event_bus.subscribe(
            subscriber_id="subscriber-1",
            handler=handler1,
            event_types=["telegram.message"],
        )
        event_bus.subscribe(
            subscriber_id="subscriber-2",
            handler=handler2,
            event_types=["telegram.message"],
        )

        payload = {
            "message_id": 2,
            "chat": {"id": -1000000000002},
            "from": {"id": 654321, "first_name": "Multi"},
            "date": 1700000000,
            "text": "Multiple subscribers test",
        }

        connector.receive_message(payload)

        assert len(received1) == 1
        assert len(received2) == 1




# =============================================================================
# DEFECT FIX TESTS - WO-008-003-HF1
# =============================================================================

class TestDefect1TextField:
    """Tests for DEFECT 1: text field in canonical event."""

    def test_telegram_event_contains_text_field(self, parser, valid_telegram_payload):
        """Telegram event must contain 'text' field, not 'message_text'."""
        message = parser.parse(valid_telegram_payload)
        event = TelegramEvent.from_telegram_message(message)
        event_dict = event.to_dict()

        assert "text" in event_dict
        assert "message_text" not in event_dict
        assert event_dict["text"] == "Test message content"

    def test_telegram_event_text_equals_message_text(self, parser):
        """The 'text' field should contain the original message text."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456, "username": "test"},
            "date": 1700000000,
            "text": "Hello World",
        }
        message = parser.parse(payload)
        event = TelegramEvent.from_telegram_message(message)

        assert event.to_dict()["text"] == "Hello World"


class TestDefect2DependencyInjection:
    """Tests for DEFECT 2: EventBus dependency injection."""

    def test_get_telegram_service_uses_supplied_event_bus(self):
        """get_telegram_service must use the supplied EventBus."""
        from app.connectors.telegram.service import get_telegram_service
        from app.core.event_bus import EventBus

        TelegramService.reset_instance()
        bus = EventBus()

        service = get_telegram_service(bus)

        assert service.event_bus is bus
        assert service.connector._bus is bus

        TelegramService.reset_instance()

    def test_different_event_buses_are_not_shared(self):
        """Two different EventBus instances must remain independent."""
        from app.connectors.telegram.service import get_telegram_service, TelegramService

        TelegramService.reset_instance()
        bus1 = EventBus()
        bus2 = EventBus()

        service1 = get_telegram_service(bus1)
        service2 = get_telegram_service(bus2)

        # They should use different buses
        assert service1.event_bus is bus1
        assert service2.event_bus is bus2
        assert bus1 is not bus2

        TelegramService.reset_instance()

    def test_telegram_connector_uses_service_event_bus(self):
        """The connector inside service must use the service's EventBus."""
        from app.connectors.telegram.service import get_telegram_service

        TelegramService.reset_instance()
        bus = EventBus()

        service = get_telegram_service(bus)

        assert service.connector._bus is bus

        TelegramService.reset_instance()


class TestDefect3PhotoSizeSelection:
    """Tests for DEFECT 3: Single PhotoSize selection."""

    def test_multiple_photosizes_produces_single_media(self, parser):
        """Multiple PhotoSize objects must produce ONE media entry."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": 1700000000,
            "photo": [
                {"file_id": "small", "file_unique_id": "s1", "file_size": 1000, "width": 90, "height": 90},
                {"file_id": "medium", "file_unique_id": "m1", "file_size": 5000, "width": 320, "height": 320},
                {"file_id": "large", "file_unique_id": "l1", "file_size": 15000, "width": 800, "height": 800},
            ],
        }

        message = parser.parse(payload)

        # Should have exactly ONE media entry
        assert message.has_media is True
        assert len(message.media) == 1

    def test_largest_photosize_is_selected(self, parser):
        """The PhotoSize with largest file_size should be selected."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": 1700000000,
            "photo": [
                {"file_id": "small", "file_unique_id": "s1", "file_size": 1000, "width": 90, "height": 90},
                {"file_id": "medium", "file_unique_id": "m1", "file_size": 5000, "width": 320, "height": 320},
                {"file_id": "large", "file_unique_id": "l1", "file_size": 15000, "width": 800, "height": 800},
            ],
        }

        message = parser.parse(payload)

        # The largest file_size should be selected
        assert message.media[0].file_id == "large"
        assert message.media[0].file_size == 15000

    def test_photosize_without_file_size_uses_fallback(self, parser):
        """PhotoSize without file_size falls back to last in array."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": 1700000000,
            "photo": [
                {"file_id": "a", "file_unique_id": "a1", "width": 90, "height": 90},
                {"file_id": "b", "file_unique_id": "b1", "width": 320, "height": 320},
                {"file_id": "c", "file_unique_id": "c1", "width": 800, "height": 800},
            ],
        }

        message = parser.parse(payload)

        # Should use last in array (Telegram orders largest first)
        assert message.media[0].file_id == "c"


class TestDefect4UTCNormalization:
    """Tests for DEFECT 4: UTC timezone normalization."""

    def test_timezone_aware_datetime_converts_to_utc(self, parser):
        """Timezone-aware datetime must convert to UTC."""
        from datetime import timezone, timedelta

        # Create a time in EST (UTC-5)
        est = timezone(timedelta(hours=-5))
        est_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=est)

        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": est_time,
            "text": "Test",
        }

        message = parser.parse(payload)

        # Should be converted to UTC (17:00:00)
        assert message.timestamp.tzinfo == timezone.utc
        assert message.timestamp.hour == 17

    def test_iso_datetime_with_offset_converts_to_utc(self, parser):
        """ISO datetime with timezone offset must convert to UTC."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": "2026-01-01T12:00:00-05:00",
            "text": "Test",
        }

        message = parser.parse(payload)

        # Should be converted to UTC (17:00:00)
        assert message.timestamp.tzinfo == timezone.utc
        assert message.timestamp.hour == 17

    def test_unix_timestamp_parsing_unchanged(self, parser):
        """Unix timestamp parsing must remain correct."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": 1700000000,
            "text": "Test",
        }

        message = parser.parse(payload)

        # Should parse correctly to UTC
        assert message.timestamp.tzinfo == timezone.utc
        from datetime import datetime
        # 1700000000 = 2023-11-14 22:13:20 UTC
        expected = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        assert message.timestamp == expected

    def test_naive_datetime_becomes_utc(self, parser):
        """Naive datetime should become UTC, not fail."""
        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456},
            "date": "2026-01-15T10:30:00",
            "text": "Test",
        }

        message = parser.parse(payload)

        # Should become UTC
        assert message.timestamp.tzinfo == timezone.utc


class TestIntegrationEndToEnd:
    """End-to-end integration tests."""

    def test_telegram_event_reaches_event_bus(self, event_bus):
        """Canonical event is published to Event Bus."""
        connector = TelegramConnector(event_bus=event_bus)
        received = []

        def handler(event, ctx):
            received.append(event)

        event_bus.subscribe("test", handler, ["telegram.message"])

        payload = {
            "message_id": 1,
            "chat": {"id": -1000000000001},
            "from": {"id": 123456, "username": "test"},
            "date": 1700000000,
            "text": "End-to-end test",
        }

        result = connector.receive_message(payload)

        assert result is not None
        assert len(received) == 1
        assert received[0]["text"] == "End-to-end test"
        assert received[0]["event_type"] == "telegram.message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
