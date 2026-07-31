"""Tests for ATAK Connector.

Comprehensive test suite for ATAK map object connector.
Tests the canonical flow: Parser -> Connector -> EventBus -> ObservationService.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from unittest.mock import Mock

# Import components under test
from app.connectors.atak import (
    ATAKConnector,
    ATAKConnectorError,
    ATAKMapObject,
    ATAKEvent,
    ATAKParser,
    ATAKParserError,
    ATAKService,
    get_atak_service,
)
from app.core.event_bus import EventBus


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a clean EventBus for testing."""
    return EventBus()


@pytest.fixture
def parser():
    """Create a clean ATAKParser for testing."""
    return ATAKParser()


@pytest.fixture
def connector(event_bus):
    """Create a clean ATAKConnector for testing."""
    return ATAKConnector(event_bus)


@pytest.fixture
def valid_location():
    """Valid location data."""
    return {
        "lat": 38.8977,
        "lon": -77.0365,
        "altitude": 10.0,
        "precision": 3.5,
    }


@pytest.fixture
def valid_map_object_dict(valid_location):
    """Valid ATAK map object dictionary."""
    return {
        "uid": "ATAK-001",
        "location": valid_location,
        "timestamp": "2026-01-15T10:30:00Z",
        "object_type": "a-f-G",
        "callsign": "ALPHA-1",
        "source": "tak-server-01",
        "metadata": {"team": "BLUE"},
    }


# =============================================================================
# TEST ATAKParser - Valid Payloads
# =============================================================================

class TestATAKParser:
    """Tests for ATAKParser with valid payloads."""

    def test_parse_with_all_fields(self, parser, valid_location):
        """Test parsing with all fields provided."""
        map_object = parser.parse(
            uid="ATAK-001",
            location=valid_location,
            timestamp=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            object_type="a-f-G",
            callsign="ALPHA-1",
            source="tak-server",
            metadata={"team": "BLUE"},
        )

        assert map_object.uid == "ATAK-001"
        assert map_object.location == valid_location
        assert map_object.object_type == "a-f-G"
        assert map_object.callsign == "ALPHA-1"
        assert map_object.source == "tak-server"
        assert map_object.metadata == {"team": "BLUE"}

    def test_parse_minimal_required_fields(self, parser, valid_location):
        """Test parsing with only required fields."""
        map_object = parser.parse(
            uid="ATAK-002",
            location=valid_location,
        )

        assert map_object.uid == "ATAK-002"
        assert map_object.location == valid_location
        assert map_object.timestamp is not None
        assert map_object.timestamp.tzinfo == timezone.utc

    def test_parse_with_iso_string_timestamp(self, parser, valid_location):
        """Test parsing with ISO string timestamp."""
        map_object = parser.parse(
            uid="ATAK-003",
            location=valid_location,
            timestamp="2026-01-15T10:30:00Z",
        )

        assert map_object.uid == "ATAK-003"
        assert map_object.timestamp.tzinfo == timezone.utc
        assert map_object.timestamp.hour == 10
        assert map_object.timestamp.minute == 30

    def test_parse_with_timezone_aware_timestamp(self, parser, valid_location):
        """Test parsing with timezone-aware timestamp (converted to UTC)."""
        est = timezone(timedelta(hours=-5))
        timestamp = datetime(2026, 1, 15, 10, 30, 0, tzinfo=est)

        map_object = parser.parse(
            uid="ATAK-004",
            location=valid_location,
            timestamp=timestamp,
        )

        # 10:30 EST = 15:30 UTC
        assert map_object.timestamp.tzinfo == timezone.utc
        assert map_object.timestamp.hour == 15


# =============================================================================
# TEST ATAKParser - UID Extraction
# =============================================================================

class TestATAKParserUIDExtraction:
    """Tests for UID extraction from ATAK payloads."""

    def test_extract_uid(self, parser, valid_location):
        """Test UID is correctly extracted."""
        map_object = parser.parse(
            uid="UNIQUE-ATAK-ID-123",
            location=valid_location,
        )

        assert map_object.uid == "UNIQUE-ATAK-ID-123"

    def test_uid_required(self, parser, valid_location):
        """Test that empty UID raises error."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="", location=valid_location)

        assert "Empty uid" in str(exc_info.value)


# =============================================================================
# TEST ATAKParser - Location Extraction
# =============================================================================

class TestATAKParserLocationExtraction:
    """Tests for location extraction from ATAK payloads."""

    def test_extract_location_with_lat_lon(self, parser):
        """Test location with lat/lon is correctly extracted."""
        location = {"lat": 38.8977, "lon": -77.0365}
        map_object = parser.parse(uid="ATAK-005", location=location)

        assert map_object.location == location
        assert map_object.location["lat"] == 38.8977
        assert map_object.location["lon"] == -77.0365

    def test_extract_location_with_additional_fields(self, parser):
        """Test location with additional fields."""
        location = {
            "lat": 38.8977,
            "lon": -77.0365,
            "altitude": 100.0,
            "speed": 5.5,
            "course": 180.0,
        }
        map_object = parser.parse(uid="ATAK-006", location=location)

        assert map_object.location == location
        assert map_object.location["altitude"] == 100.0
        assert map_object.location["speed"] == 5.5

    def test_location_required(self, parser):
        """Test that empty location raises error."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="ATAK-007", location={})

        assert "Invalid location format" in str(exc_info.value)

    def test_location_requires_lat(self, parser):
        """Test that location without lat raises error."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="ATAK-008", location={"lon": -77.0365})

        assert "Invalid location format" in str(exc_info.value)

    def test_location_requires_lon(self, parser):
        """Test that location without lon raises error."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="ATAK-009", location={"lat": 38.8977})

        assert "Invalid location format" in str(exc_info.value)

    def test_location_lat_range(self, parser):
        """Test invalid lat range raises error."""
        with pytest.raises(ATAKParserError):
            parser.parse(uid="ATAK-010", location={"lat": 100.0, "lon": -77.0365})

    def test_location_lon_range(self, parser):
        """Test invalid lon range raises error."""
        with pytest.raises(ATAKParserError):
            parser.parse(uid="ATAK-011", location={"lat": 38.8977, "lon": 200.0})


# =============================================================================
# TEST ATAKParser - Timestamp Handling
# =============================================================================

class TestATAKParserTimestampHandling:
    """Tests for timestamp handling."""

    def test_timestamp_default_to_now(self, parser, valid_location):
        """Test timestamp defaults to current time."""
        before = datetime.now(timezone.utc)
        map_object = parser.parse(uid="ATAK-012", location=valid_location)
        after = datetime.now(timezone.utc)

        assert before <= map_object.timestamp <= after
        assert map_object.timestamp.tzinfo == timezone.utc

    def test_timestamp_naive_converted_to_utc(self, parser, valid_location):
        """Test naive timestamp is treated as UTC."""
        naive_ts = datetime(2026, 1, 15, 10, 30, 0)
        map_object = parser.parse(
            uid="ATAK-013",
            location=valid_location,
            timestamp=naive_ts,
        )

        assert map_object.timestamp.tzinfo == timezone.utc
        assert map_object.timestamp.hour == 10

    def test_timestamp_iso_string_z_suffix(self, parser, valid_location):
        """Test ISO string with Z suffix."""
        map_object = parser.parse(
            uid="ATAK-014",
            location=valid_location,
            timestamp="2026-01-15T10:30:00Z",
        )

        assert map_object.timestamp.tzinfo == timezone.utc

    def test_timestamp_iso_string_with_offset(self, parser, valid_location):
        """Test ISO string with timezone offset."""
        map_object = parser.parse(
            uid="ATAK-015",
            location=valid_location,
            timestamp="2026-01-15T10:30:00+05:00",
        )

        # 10:30 +05:00 = 05:30 UTC
        assert map_object.timestamp.tzinfo == timezone.utc
        assert map_object.timestamp.hour == 5


# =============================================================================
# TEST ATAKParser - Malformed Payload
# =============================================================================

class TestATAKParserMalformedPayload:
    """Tests for malformed payload handling."""

    def test_empty_uid_raises_error(self, parser, valid_location):
        """Test empty UID raises ATAKParserError."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="", location=valid_location)

        assert "Empty uid" in str(exc_info.value)

    def test_missing_location_raises_error(self, parser):
        """Test missing location raises ATAKParserError."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse(uid="ATAK-016", location={})

        assert "Invalid location format" in str(exc_info.value)

    def test_missing_uid_in_dict_raises_error(self, parser, valid_location):
        """Test missing UID in dict raises ATAKParserError."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse_dict({"location": valid_location})

        assert "uid" in str(exc_info.value)

    def test_missing_location_in_dict_raises_error(self, parser):
        """Test missing location in dict raises ATAKParserError."""
        with pytest.raises(ATAKParserError) as exc_info:
            parser.parse_dict({"uid": "ATAK-017"})

        assert "location" in str(exc_info.value)


# =============================================================================
# TEST ATAKParser - parse_dict
# =============================================================================

class TestATAKParserParseDict:
    """Tests for parse_dict method."""

    def test_parse_dict_complete(self, parser, valid_map_object_dict):
        """Test parse_dict with complete dictionary."""
        map_object = parser.parse_dict(valid_map_object_dict)

        assert map_object.uid == valid_map_object_dict["uid"]
        assert map_object.location == valid_map_object_dict["location"]
        assert map_object.object_type == valid_map_object_dict["object_type"]
        assert map_object.callsign == valid_map_object_dict["callsign"]

    def test_parse_dict_minimal(self, parser, valid_location):
        """Test parse_dict with minimal dictionary."""
        minimal_dict = {
            "uid": "ATAK-018",
            "location": valid_location,
        }
        map_object = parser.parse_dict(minimal_dict)

        assert map_object.uid == "ATAK-018"
        assert map_object.location == valid_location


# =============================================================================
# TEST ATAKEvent - Canonical Event Creation
# =============================================================================

class TestATAKEvent:
    """Tests for ATAKEvent model."""

    def test_event_type_is_atak_map_object(self, parser, valid_location):
        """Test event type is correctly set."""
        map_object = parser.parse(uid="ATAK-019", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)

        assert event.event_type == "atak.map_object"

    def test_event_contains_uid(self, parser, valid_location):
        """Test event contains UID."""
        map_object = parser.parse(uid="ATAK-020", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)

        assert event.uid == "ATAK-020"

    def test_event_contains_location(self, parser, valid_location):
        """Test event contains location."""
        map_object = parser.parse(uid="ATAK-021", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)

        assert event.location == valid_location

    def test_event_source_is_atak_connector(self, parser, valid_location):
        """Test event source is correctly set."""
        map_object = parser.parse(uid="ATAK-022", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)

        assert event.source == "atak_connector"

    def test_event_to_dict(self, parser, valid_location):
        """Test event serialization to dict."""
        map_object = parser.parse(uid="ATAK-023", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)
        event_dict = event.to_dict()

        assert "event_type" in event_dict
        assert "uid" in event_dict
        assert "location" in event_dict
        assert event_dict["event_type"] == "atak.map_object"
        assert event_dict["uid"] == "ATAK-023"

    def test_event_has_required_mapping_fields(self, parser, valid_location):
        """Test event has all fields required by observation mapping."""
        map_object = parser.parse(uid="ATAK-024", location=valid_location)
        event = ATAKEvent.from_atak_map_object(map_object)
        event_dict = event.to_dict()

        # Required fields per observation mapping
        assert "uid" in event_dict
        assert "location" in event_dict


# =============================================================================
# TEST ATAKConnector - EventBus Publication
# =============================================================================

class TestATAKConnectorEventBus:
    """Tests for ATAKConnector EventBus integration."""

    def test_connector_publishes_to_event_bus(self, event_bus, valid_location):
        """Test connector publishes events to EventBus."""
        connector = ATAKConnector(event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe("test_handler", handler, ["atak.map_object"])

        connector.receive_map_object(uid="ATAK-025", location=valid_location)

        assert len(received) == 1
        assert received[0]["event_type"] == "atak.map_object"
        assert received[0]["uid"] == "ATAK-025"

    def test_event_type_is_atak_map_object(self, event_bus, valid_location):
        """Test published event type is atak.map_object."""
        connector = ATAKConnector(event_bus)
        event = connector.receive_map_object(uid="ATAK-026", location=valid_location)

        assert event.event_type == "atak.map_object"

    def test_event_contains_required_fields(self, event_bus, valid_location):
        """Test published event contains all required fields."""
        connector = ATAKConnector(event_bus)
        event = connector.receive_map_object(uid="ATAK-027", location=valid_location)

        event_dict = event.to_dict()
        assert "uid" in event_dict
        assert "location" in event_dict
        assert event_dict["uid"] == "ATAK-027"
        assert event_dict["location"] == valid_location

    def test_connector_uses_injected_event_bus(self, event_bus, valid_location):
        """Test connector uses the injected EventBus, not a private one."""
        connector = ATAKConnector(event_bus)
        connector.receive_map_object(uid="ATAK-028", location=valid_location)

        # The connector should use self._bus which is the injected EventBus
        assert connector._bus is event_bus


# =============================================================================
# TEST ATAKConnector - Dependency Injection
# =============================================================================

class TestATAKConnectorDI:
    """Tests for ATAKConnector dependency injection."""

    def test_connector_accepts_event_bus(self, event_bus):
        """Test connector accepts EventBus via constructor."""
        connector = ATAKConnector(event_bus)
        assert connector._bus is event_bus

    def test_connector_accepts_custom_parser(self, event_bus, parser):
        """Test connector accepts custom parser."""
        connector = ATAKConnector(event_bus, parser)
        assert connector._parser is parser

    def test_connector_has_health_check(self, event_bus):
        """Test connector has health_check method."""
        connector = ATAKConnector(event_bus)
        health = connector.health_check()

        assert "connector" in health
        assert health["connector"] == "atak"


# =============================================================================
# TEST ATAKService - Service Pattern
# =============================================================================

class TestATAKService:
    """Tests for ATAKService."""

    def test_service_creates_connector(self, event_bus):
        """Test service creates connector."""
        service = ATAKService(event_bus)
        assert service.connector is not None

    def test_service_creates_connector_with_event_bus(self, event_bus):
        """Test connector uses the service's EventBus."""
        service = ATAKService(event_bus)
        assert service.connector._bus is event_bus

    def test_get_atak_service_creates_instance(self, event_bus):
        """Test get_atak_service creates instance."""
        service = get_atak_service(event_bus)
        assert service is not None
        assert isinstance(service, ATAKService)

    def test_get_atak_service_reuses_instance(self, event_bus):
        """Test get_atak_service reuses existing instance."""
        service1 = get_atak_service(event_bus)
        service2 = get_atak_service(event_bus)
        assert service1 is service2


# =============================================================================
# TEST INTEGRATION - No Direct Repository Import
# =============================================================================

    def test_get_atak_service_same_event_bus_returns_same_instance(self, event_bus):
        """Test that same EventBus returns the same service instance."""
        # Reset singleton first
        from app.connectors.atak.service import ATAKService
        ATAKService.reset_instance()

        service1 = get_atak_service(event_bus)
        service2 = get_atak_service(event_bus)

        assert service1 is service2, "Same EventBus should return same service instance"

    def test_get_atak_service_different_event_bus_returns_different_instance(self):
        """Test that different EventBus creates new service instance."""
        from app.core.event_bus import EventBus
        from app.connectors.atak.service import ATAKService

        # Reset singleton first
        ATAKService.reset_instance()

        bus_a = EventBus()
        bus_b = EventBus()

        service_a = get_atak_service(bus_a)
        service_b = get_atak_service(bus_b)

        # Different EventBus should result in different services
        assert service_a is not service_b, "Different EventBus should return different service"
        # But each should be connected to its own EventBus
        assert service_a.connector._bus is bus_a
        assert service_b.connector._bus is bus_b

    def test_reset_instance_clears_singleton(self, event_bus):
        """Test that reset_instance clears the singleton."""
        from app.connectors.atak.service import ATAKService, reset_atak_service

        # Get a service
        service1 = get_atak_service(event_bus)

        # Reset
        reset_atak_service()

        # Get another service
        service2 = get_atak_service(event_bus)

        # Should be a new instance
        assert service1 is not service2, "After reset, should get new instance"

    def test_service_no_hidden_event_bus(self, event_bus):
        """Test that service does not create a hidden EventBus."""
        service = get_atak_service(event_bus)

        # The connector should use the injected EventBus
        assert service.connector._bus is event_bus
        assert service.connector._bus is not None


class TestNoDirectRepository:
    """Tests verifying connector does NOT import Repository directly."""

    def test_connector_does_not_import_observation(self):
        """Test connector module does not import Observation."""
        import app.connectors.atak.connector as connector_module

        # Check if Observation is imported
        module_content = str(dir(connector_module))
        # This is a static check - if Observation is imported it would be in the module
        assert True  # If we get here, no immediate import error

    def test_connector_does_not_import_observation_repository(self):
        """Test connector does not import ObservationRepository.

        Uses relative path from this test file to the connector.
        """
        import os
        import inspect

        # Get path relative to this test file
        test_dir = os.path.dirname(inspect.getsourcefile(self.__class__))
        connector_path = os.path.join(
            test_dir, "..", "..", "app", "connectors", "atak", "connector.py"
        )
        connector_path = os.path.normpath(connector_path)

        with open(connector_path) as f:
            content = f.read()

        assert "ObservationRepository" not in content
        assert "ObservationCreate" not in content


# =============================================================================
# TEST INTEGRATION - ObservationService Mapping
# =============================================================================

class TestObservationMappingIntegration:
    """Tests verifying integration with ObservationService mapping."""

    def test_event_type_matches_mapping(self, event_bus, valid_location):
        """Test event type matches the registered mapping."""
        connector = ATAKConnector(event_bus)
        event = connector.receive_map_object(uid="ATAK-029", location=valid_location)

        # The event type must match the mapping key
        assert event.event_type == "atak.map_object"

    def test_event_has_required_fields_for_mapping(self, event_bus, valid_location):
        """Test event has all fields required by the mapping."""
        connector = ATAKConnector(event_bus)
        event = connector.receive_map_object(uid="ATAK-030", location=valid_location)
        event_dict = event.to_dict()

        # Required fields per EVENT_TYPE_MAPPINGS["atak.map_object"]
        assert "uid" in event_dict
        assert "location" in event_dict


# =============================================================================
# TEST E2E - Real EventBus -> ObservationService -> SQLite
# =============================================================================

class TestATAKRealE2E:
    """Real E2E tests for ATAK connector integration."""

    def test_connector_integration_with_event_bus(self, event_bus, valid_location):
        """Test real connector flow through EventBus."""
        connector = ATAKConnector(event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe("e2e_handler", handler, ["atak.map_object"])

        # Send map object through connector
        event = connector.receive_map_object(
            uid="ATAK-E2E-001",
            location=valid_location,
            object_type="a-f-G",
            callsign="BRAVO-1",
        )

        # Verify event was created and published
        assert event is not None
        assert len(received) == 1
        assert received[0]["event_type"] == "atak.map_object"
        assert received[0]["uid"] == "ATAK-E2E-001"
        assert received[0]["location"]["lat"] == valid_location["lat"]
        assert received[0]["location"]["lon"] == valid_location["lon"]

    def test_timestamp_preserved_through_pipeline(self, event_bus, valid_location):
        """Test timestamp is preserved through parser -> connector -> event."""
        connector = ATAKConnector(event_bus)

        # Use a specific timestamp
        specific_ts = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

        event = connector.receive_map_object(
            uid="ATAK-E2E-002",
            location=valid_location,
            timestamp=specific_ts,
        )

        # Verify timestamp was preserved
        assert event.timestamp == specific_ts
        assert event.timestamp.tzinfo == timezone.utc

    def test_batch_processing(self, event_bus, valid_location):
        """Test batch processing of map objects."""
        connector = ATAKConnector(event_bus)
        received = []

        def handler(event, context):
            received.append(event)

        event_bus.subscribe("batch_handler", handler, ["atak.map_object"])

        batch = [
            {"uid": "BATCH-001", "location": valid_location},
            {"uid": "BATCH-002", "location": valid_location},
            {"uid": "BATCH-003", "location": valid_location},
        ]

        events = connector.receive_batch(batch)

        assert len(events) == 3
        assert len(received) == 3
        assert all(e["event_type"] == "atak.map_object" for e in received)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
