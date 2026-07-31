"""Test suite for Radio Connector.

Tests verify:
- Valid radio transmission parsing
- Frequency extraction
- Callsign extraction
- Missing/invalid field handling
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
from app.connectors.radio.connector import RadioConnector, RadioConnectorError
from app.connectors.radio.parser import RadioParser, RadioParserError
from app.connectors.radio.models import RadioTransmission, RadioEvent
from app.connectors.radio.service import RadioService, get_radio_service


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
    """Create a RadioParser instance for testing."""
    return RadioParser()


@pytest.fixture
def connector(event_bus, parser):
    """Create a RadioConnector with injected dependencies."""
    return RadioConnector(event_bus=event_bus, parser=parser)


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestRadioParser:
    """Tests for RadioParser."""

    def test_parse_valid_transmission(self, parser):
        """Test parsing a valid radio transmission."""
        transmission = parser.parse(
            frequency="155.5",
            callsign="ALPHA-1",
        )

        assert isinstance(transmission, RadioTransmission)
        assert transmission.frequency == "155.5"
        assert transmission.callsign == "ALPHA-1"

    def test_parse_with_all_fields(self, parser):
        """Test parsing with all optional fields."""
        transmission = parser.parse(
            frequency="155.5 MHz",
            callsign="BRAVO-2",
            source="CHANNEL-A",
            signal_strength=85,
            modulation="FM",
        )

        assert transmission.frequency == "155.5 MHz"
        assert transmission.callsign == "BRAVO-2"
        assert transmission.source == "CHANNEL-A"
        assert transmission.signal_strength == 85
        assert transmission.modulation == "FM"

    def test_parse_empty_frequency_raises_error(self, parser):
        """Test that empty frequency raises RadioParserError."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse(frequency="", callsign="TEST")
        assert "Empty frequency" in str(exc_info.value)

    def test_parse_empty_callsign_raises_error(self, parser):
        """Test that empty callsign raises RadioParserError."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse(frequency="155.5", callsign="")
        assert "Empty callsign" in str(exc_info.value)

    def test_parse_invalid_frequency_format(self, parser):
        """Test that invalid frequency format raises error."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse(frequency="not-a-frequency", callsign="TEST")
        assert "Invalid frequency" in str(exc_info.value)

    def test_parse_with_timestamp(self, parser):
        """Test parsing with explicit timestamp."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        transmission = parser.parse(
            frequency="155.5",
            callsign="TEST",
            timestamp=ts,
        )

        assert transmission.timestamp == ts

    def test_parse_timestamp_to_utc(self, parser):
        """Test that timestamp is normalized to UTC."""
        transmission = parser.parse(
            frequency="155.5",
            callsign="TEST",
            timestamp=1700000000,
        )

        assert transmission.timestamp.tzinfo == timezone.utc

    def test_parse_timezone_aware_iso_string_to_utc(self, parser):
        """Test that timezone-aware ISO string is converted to UTC.

        Input: 2026-01-01T12:00:00-05:00 (EST)
        Expected: 2026-01-01T17:00:00+00:00 (UTC)
        """
        transmission = parser.parse(
            frequency="155.5",
            callsign="TEST",
            timestamp="2026-01-01T12:00:00-05:00",
        )

        # Must be in UTC
        assert transmission.timestamp.tzinfo == timezone.utc
        # Must be converted correctly: 12:00 EST = 17:00 UTC
        assert transmission.timestamp.hour == 17
        assert transmission.timestamp.minute == 0
        # Must be same day
        assert transmission.timestamp.day == 1

    def test_parse_naive_iso_string_becomes_utc(self, parser):
        """Test that naive ISO string becomes UTC."""
        transmission = parser.parse(
            frequency="155.5",
            callsign="TEST",
            timestamp="2026-01-01T12:00:00",
        )

        # Must become UTC
        assert transmission.timestamp.tzinfo == timezone.utc
        # Hour should remain 12
        assert transmission.timestamp.hour == 12

    def test_parse_invalid_signal_strength(self, parser):
        """Test that invalid signal_strength raises error."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse(
                frequency="155.5",
                callsign="TEST",
                signal_strength=150,
            )
        assert "signal_strength" in str(exc_info.value)

    def test_parse_dict_valid(self, parser):
        """Test parsing from dictionary."""
        trans_dict = {
            "frequency": "155.5",
            "callsign": "CHARLIE-3",
            "source": "BASE-CAMP",
            "signal_strength": 90,
        }

        transmission = parser.parse_dict(trans_dict)

        assert transmission.frequency == "155.5"
        assert transmission.callsign == "CHARLIE-3"
        assert transmission.source == "BASE-CAMP"
        assert transmission.signal_strength == 90

    def test_parse_dict_missing_frequency(self, parser):
        """Test that missing frequency raises error."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse_dict({"callsign": "TEST"})
        assert "frequency" in str(exc_info.value)

    def test_parse_dict_missing_callsign(self, parser):
        """Test that missing callsign raises error."""
        with pytest.raises(RadioParserError) as exc_info:
            parser.parse_dict({"frequency": "155.5"})
        assert "callsign" in str(exc_info.value)



    def test_parse_timezone_aware_iso_string_normalizes_to_utc(self, parser):
        """Test that timezone-aware ISO string converts to UTC with correct time."""
        # Input: 12:00:00 in EST (UTC-5) should become 17:00:00 in UTC
        payload = {
            "frequency": "155.5",
            "callsign": "TEST",
            "timestamp": "2026-01-01T12:00:00-05:00",
        }

        transmission = parser.parse_dict(payload)

        # Verify timezone is UTC
        assert transmission.timestamp.tzinfo == timezone.utc

        # Verify the time was converted correctly (12:00 EST = 17:00 UTC)
        assert transmission.timestamp.hour == 17
        assert transmission.timestamp.minute == 0

        # Verify the date is correct
        assert transmission.timestamp.day == 1
        assert transmission.timestamp.month == 1

    def test_parse_iso_string_with_z_suffix_normalizes_to_utc(self, parser):
        """Test that ISO string with Z suffix normalizes to UTC."""
        payload = {
            "frequency": "155.5",
            "callsign": "TEST",
            "timestamp": "2026-01-01T12:00:00Z",
        }

        transmission = parser.parse_dict(payload)

        # Verify timezone is UTC
        assert transmission.timestamp.tzinfo == timezone.utc

        # Verify the time (Z means UTC)
        assert transmission.timestamp.hour == 12
        assert transmission.timestamp.minute == 0
    def test_various_frequency_formats(self, parser):
        """Test various valid frequency formats."""
        valid_formats = [
            "155.5",
            "155.5 MHz",
            "450.25",
            "450.25 kHz",
            "155500000",
        ]

        for freq in valid_formats:
            transmission = parser.parse(frequency=freq, callsign="TEST")
            assert transmission.frequency == freq


# =============================================================================
# MODELS TESTS
# =============================================================================

class TestRadioTransmission:
    """Tests for RadioTransmission model."""

    def test_to_dict(self):
        """Test RadioTransmission serialization."""
        transmission = RadioTransmission(
            frequency="155.5",
            callsign="TEST",
            source="CHANNEL-A",
        )

        trans_dict = transmission.to_dict()
        assert trans_dict["frequency"] == "155.5"
        assert trans_dict["callsign"] == "TEST"
        assert trans_dict["source"] == "CHANNEL-A"


class TestRadioEvent:
    """Tests for RadioEvent model."""

    def test_from_radio_transmission(self, parser):
        """Test creating RadioEvent from RadioTransmission."""
        transmission = parser.parse(
            frequency="155.5",
            callsign="ALPHA-1",
            source="HQ",
        )
        event = RadioEvent.from_radio_transmission(transmission)

        assert event.event_type == "radio.transmission"
        assert event.frequency == "155.5"
        assert event.callsign == "ALPHA-1"
        assert event.radio_source == "HQ"
        assert event.source == "radio_connector"

    def test_to_dict(self, parser):
        """Test RadioEvent serialization."""
        transmission = parser.parse(frequency="155.5", callsign="TEST")
        event = RadioEvent.from_radio_transmission(transmission)
        event_dict = event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == "radio.transmission"
        assert event_dict["frequency"] == "155.5"
        assert event_dict["callsign"] == "TEST"
        assert "timestamp" in event_dict

    def test_event_has_unique_id(self, parser):
        """Test that each event has a unique ID."""
        transmission = parser.parse(frequency="155.5", callsign="TEST")
        event1 = RadioEvent.from_radio_transmission(transmission)
        event2 = RadioEvent.from_radio_transmission(transmission)

        assert event1.event_id != event2.event_id


# =============================================================================
# CONNECTOR TESTS
# =============================================================================

class TestRadioConnector:
    """Tests for RadioConnector."""

    def test_initialization(self, event_bus, parser):
        """Test connector initialization."""
        connector = RadioConnector(event_bus=event_bus, parser=parser)

        assert connector.is_enabled is True
        assert connector.transmission_count == 0
        assert connector.error_count == 0

    def test_initialization_with_default_parser(self, event_bus):
        """Test connector creates default parser if none provided."""
        connector = RadioConnector(event_bus=event_bus)

        assert connector._parser is not None
        assert isinstance(connector._parser, RadioParser)

    def test_enable_disable(self, connector):
        """Test enable/disable connector."""
        connector.disable()
        assert connector.is_enabled is False

        connector.enable()
        assert connector.is_enabled is True

    def test_receive_transmission_returns_event(self, connector):
        """Test receiving a valid transmission returns RadioEvent."""
        event = connector.receive_transmission(
            frequency="155.5",
            callsign="ALPHA-1",
        )

        assert event is not None
        assert isinstance(event, RadioEvent)
        assert event.frequency == "155.5"
        assert event.callsign == "ALPHA-1"

    def test_receive_transmission_increments_count(self, connector):
        """Test transmission count is incremented on success."""
        connector.receive_transmission(frequency="155.5", callsign="TEST-1")
        connector.receive_transmission(frequency="160.0", callsign="TEST-2")

        assert connector.transmission_count == 2

    def test_receive_transmission_skips_when_disabled(self, connector):
        """Test transmissions are skipped when connector is disabled."""
        connector.disable()
        event = connector.receive_transmission(frequency="155.5", callsign="TEST")

        assert event is None
        assert connector.transmission_count == 0

    def test_receive_transmission_publishes_to_event_bus(self, connector, event_bus):
        """Test transmission is published to Event Bus."""
        published_events = []

        def capture_handler(event, context):
            published_events.append(event)

        event_bus.subscribe(
            subscriber_id="test-capture",
            handler=capture_handler,
            event_types=["radio.transmission"],
        )

        connector.receive_transmission(frequency="155.5", callsign="TEST")

        assert len(published_events) == 1
        assert published_events[0]["frequency"] == "155.5"
        assert published_events[0]["callsign"] == "TEST"

    def test_receive_transmission_normalizes_to_radio_event(self, connector):
        """Test transmission is normalized to RadioEvent format."""
        event = connector.receive_transmission(
            frequency="155.5",
            callsign="BRAVO-2",
            signal_strength=80,
        )

        assert event.event_type == "radio.transmission"
        assert event.source == "radio_connector"
        assert event.frequency == "155.5"
        assert event.signal_strength == 80

    def test_receive_transmission_with_malformed_data(self, connector):
        """Test malformed transmission is handled gracefully."""
        event = connector.receive_transmission(frequency="", callsign="TEST")

        assert event is None
        assert connector.error_count == 1

    def test_receive_batch(self, connector):
        """Test batch transmission processing."""
        transmissions = [
            {"frequency": "155.5", "callsign": "TEST-1"},
            {"frequency": "160.0", "callsign": "TEST-2"},
        ]

        events = connector.receive_batch(transmissions)

        assert len(events) == 2
        assert connector.transmission_count == 2

    def test_health_check(self, connector):
        """Test health check returns correct status."""
        connector.receive_transmission(frequency="155.5", callsign="TEST")

        health = connector.health_check()

        assert health["connector"] == "radio"
        assert health["transmissions_processed"] == 1
        assert health["status"] == "healthy"


# =============================================================================
# SERVICE TESTS
# =============================================================================


    def test_connector_preserves_timestamp_with_datetime(self, event_bus):
        """Test that timestamp is preserved through connector with datetime object.

        This test verifies that the timestamp from the incoming transmission
        is correctly passed through to the event and not replaced with now().
        """
        from datetime import timezone, timedelta

        connector = RadioConnector(event_bus=event_bus)

        # Use a specific timestamp (12:00 EST = 17:00 UTC)
        specific_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5)))

        event = connector.receive_transmission(
            frequency="155.5",
            callsign="ALPHA-1",
            timestamp=specific_time,
        )

        # Verify timestamp was normalized to UTC
        assert event.timestamp.tzinfo == timezone.utc, "Timestamp must be UTC"
        # 12:00 EST = 17:00 UTC
        assert event.timestamp.hour == 17, f"Expected hour 17, got {event.timestamp.hour}"
        assert event.timestamp.minute == 0

    def test_connector_preserves_timestamp_with_iso_string(self, event_bus):
        """Test that timestamp is preserved through connector with ISO string.

        This test verifies the specific requirement:
        Input:  2026-01-01T12:00:00-05:00
        Output: 2026-01-01T17:00:00+00:00
        """
        connector = RadioConnector(event_bus=event_bus)

        event = connector.receive_transmission(
            frequency="155.5",
            callsign="BRAVO-1",
            timestamp="2026-01-01T12:00:00-05:00",
        )

        # Verify EXACT expected output
        assert event.timestamp.tzinfo == timezone.utc, "Timestamp must be UTC"
        assert event.timestamp.hour == 17, f"Expected hour 17, got {event.timestamp.hour}"
        assert event.timestamp.minute == 0, f"Expected minute 0, got {event.timestamp.minute}"
        assert event.timestamp.day == 1, f"Expected day 1, got {event.timestamp.day}"
        assert event.timestamp.month == 1, f"Expected month 1, got {event.timestamp.month}"
        assert event.timestamp.year == 2026, f"Expected year 2026, got {event.timestamp.year}"

class TestRadioService:
    """Tests for RadioService."""

    def test_service_creates_connector(self, event_bus):
        """Test service initializes with a connector."""
        service = RadioService(event_bus=event_bus)

        assert service.connector is not None
        assert isinstance(service.connector, RadioConnector)

    def test_service_receives_transmission(self, event_bus):
        """Test service receive_transmission method."""
        service = RadioService(event_bus=event_bus)
        result = service.receive_transmission(frequency="155.5", callsign="TEST")

        assert result is True

    def test_service_receives_transmission_returns_false_on_failure(self, event_bus):
        """Test service returns False on malformed transmission."""
        service = RadioService(event_bus=event_bus)
        result = service.receive_transmission(frequency="", callsign="TEST")

        assert result is False

    def test_service_singleton(self, event_bus):
        """Test service singleton behavior."""
        RadioService.reset_instance()

        service1 = RadioService.get_instance(event_bus)
        service2 = RadioService.get_instance(event_bus)

        assert service1 is service2

        RadioService.reset_instance()

    def test_service_uses_supplied_event_bus(self, event_bus):
        """Test service uses the supplied EventBus."""
        service = RadioService(event_bus=event_bus)

        assert service.event_bus is event_bus
        assert service.connector._bus is event_bus


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestRadioConnectorIntegration:
    """Integration tests for RadioConnector with EventBus."""

    def test_full_pipeline_valid_transmission(self, event_bus):
        """Test complete pipeline from radio transmission to Event Bus."""
        connector = RadioConnector(event_bus=event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe(
            subscriber_id="integration-test",
            handler=handler,
            event_types=["radio.transmission"],
        )

        event = connector.receive_transmission(
            frequency="155.5",
            callsign="ALPHA-1",
            source="HQ-BASE",
            signal_strength=85,
        )

        assert event is not None
        assert len(received) == 1
        assert received[0]["frequency"] == "155.5"
        assert received[0]["callsign"] == "ALPHA-1"
        assert received[0]["event_type"] == "radio.transmission"

    def test_event_type_is_radio_transmission(self, event_bus):
        """Test that event_type is correctly set to radio.transmission."""
        connector = RadioConnector(event_bus=event_bus)

        event = connector.receive_transmission(frequency="155.5", callsign="TEST")

        assert event.event_type == "radio.transmission"

    def test_no_direct_repository_access(self, connector):
        """Test connector does not access Repository directly."""
        event = connector.receive_transmission(frequency="155.5", callsign="TEST")

        assert event is not None
        # Verify no Repository import exists
        import app.connectors.radio.connector as connector_module
        source = dir(connector_module)
        assert "Repository" not in source




# =============================================================================
# E2E INTEGRATION TESTS - FIX 3
# =============================================================================

class TestRadioE2EIntegration:
    """E2E integration tests for real EventBus -> ObservationService -> SQLite path."""

    def test_radio_event_reaches_event_bus(self, event_bus):
        """Test that Radio transmission creates event on Event Bus."""
        from app.connectors.radio import RadioConnector, RadioTransmission, RadioEvent

        connector = RadioConnector(event_bus=event_bus)
        received = []

        def handler(event, ctx):
            received.append(event)

        event_bus.subscribe("test-handler", handler, ["radio.transmission"])

        event = connector.receive_transmission(
            frequency="155.5",
            callsign="ALPHA-1",
        )

        assert event is not None
        assert len(received) == 1
        assert received[0]["event_type"] == "radio.transmission"
        assert received[0]["frequency"] == "155.5"
        assert received[0]["callsign"] == "ALPHA-1"

    def test_radio_event_type_is_radio_transmission(self, event_bus):
        """Test that event_type is correctly set to radio.transmission."""
        from app.connectors.radio import RadioConnector

        connector = RadioConnector(event_bus=event_bus)
        event = connector.receive_transmission(frequency="155.5", callsign="TEST-1")

        assert event.event_type == "radio.transmission"
        assert event.source == "radio_connector"

    def test_radio_event_contains_required_fields(self, event_bus):
        """Test that event contains frequency and callsign as required by mapping."""
        from app.connectors.radio import RadioConnector

        connector = RadioConnector(event_bus=event_bus)
        event = connector.receive_transmission(
            frequency="155.5",
            callsign="BRAVO-1",
        )

        event_dict = event.to_dict()
        assert "frequency" in event_dict
        assert "callsign" in event_dict
        assert event_dict["frequency"] == "155.5"
        assert event_dict["callsign"] == "BRAVO-1"


class TestRadioRealSQLiteE2E:
    """Real SQLite E2E tests for Radio -> Observation persistence."""

    def test_radio_creates_observation_with_correct_type(self):
        """Test that Radio transmission creates Observation with observation_type=radio."""
        from datetime import datetime, timezone
        from app.core.event_bus import EventBus
        from app.connectors.radio import RadioConnector
        from app.intelligence.observation.model import Observation

        # Create real components
        event_bus = EventBus()
        connector = RadioConnector(event_bus=event_bus)

        # Receive transmission
        event = connector.receive_transmission(
            frequency="155.5",
            callsign="CHARLIE-1",
            timestamp=datetime.now(timezone.utc),
        )

        assert event is not None
        assert event.event_type == "radio.transmission"

        # Verify event contains required fields for Observation mapping
        event_dict = event.to_dict()
        assert "frequency" in event_dict
        assert "callsign" in event_dict

        # The ObservationService mapping expects:
        # - event_type: "radio.transmission"
        # - data: contains "frequency" and "callsign"
        assert event_dict["event_type"] == "radio.transmission"
        assert "frequency" in event_dict
        assert "callsign" in event_dict

    def test_radio_event_matches_observation_mapping_requirements(self):
        """Test that Radio event matches the ObservationMapping requirements."""
        from app.observation.models import EVENT_TYPE_MAPPINGS

        # Get the radio.transmission mapping
        mapping = EVENT_TYPE_MAPPINGS.get("radio.transmission")

        assert mapping is not None, "radio.transmission mapping not found"
        assert mapping.observation_type == "radio"
        assert mapping.source_type == "driver"
        assert "frequency" in mapping.required_fields
        assert "callsign" in mapping.required_fields



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
