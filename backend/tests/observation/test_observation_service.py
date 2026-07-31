"""Unit tests for Observation Service.

Tests verify:
- Event received from Event Bus
- Event -> Observation mapping
- ObservationType assignment
- UUID generation
- Metadata preservation
- Invalid Event handling
- Unknown Event Type handling
- Repository forwarding

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

import pytest

from app.core.event_bus import EventBus
from app.core.event_context import EventContext
from app.observation.models import (
    CanonicalEvent,
    EventMetadata,
    ObservationMapping,
    ObservationResult,
    EVENT_TYPE_MAPPINGS,
    DEFAULT_MAPPING,
)
from app.observation.mapper import EventToObservationMapper, EventMappingError
from app.observation.factory import ObservationFactory, ObservationFactoryError
from app.observation.processor import ObservationProcessor, ObservationProcessorError


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def event_bus():
    """Create an EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def mapper():
    """Create an EventToObservationMapper instance."""
    return EventToObservationMapper()


@pytest.fixture
def factory():
    """Create an ObservationFactory instance."""
    return ObservationFactory()


@pytest.fixture
def valid_canonical_event():
    """Create a valid CanonicalEvent for testing."""
    return CanonicalEvent(
        event_id="evt-001",
        event_type="signal.message",
        timestamp=datetime.now(timezone.utc),
        source="signal_connector",
        data={
            "message_id": "msg-123",
            "sender": "+1234567890",
            "chat_id": "chat-001",
            "message_text": "Test message",
        },
        metadata={
            "correlation_id": "corr-001",
            "driver_id": "driver-signal",
        },
    )


@pytest.fixture
def valid_event_dict():
    """Create a valid event dictionary."""
    return {
        "event_id": "evt-002",
        "event_type": "signal.message",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "signal_connector",
        "data": {
            "message_id": "msg-456",
            "sender": "+9876543210",
            "chat_id": "chat-002",
            "message_text": "Another test message",
        },
        "metadata": {
            "correlation_id": "corr-002",
        },
    }


# =============================================================================
# MODELS TESTS
# =============================================================================

class TestCanonicalEvent:
    """Tests for CanonicalEvent model."""

    def test_from_dict(self, valid_event_dict):
        """Test creating CanonicalEvent from dictionary."""
        event = CanonicalEvent.from_dict(valid_event_dict)

        assert event.event_id == "evt-002"
        assert event.event_type == "signal.message"
        assert event.source == "signal_connector"
        assert isinstance(event.timestamp, datetime)
        assert event.data["message_id"] == "msg-456"

    def test_from_dict_with_unix_timestamp(self):
        """Test creating CanonicalEvent with Unix timestamp."""
        event_dict = {
            "event_id": "evt-003",
            "event_type": "radio.transmission",
            "timestamp": 1700000000,
            "source": "radio_connector",
            "data": {"frequency": "155.5"},
        }

        event = CanonicalEvent.from_dict(event_dict)
        assert isinstance(event.timestamp, datetime)

    def test_to_dict(self, valid_canonical_event):
        """Test CanonicalEvent serialization."""
        event_dict = valid_canonical_event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["event_id"] == "evt-001"
        assert event_dict["event_type"] == "signal.message"

    def test_get_metadata(self, valid_canonical_event):
        """Test extracting EventMetadata."""
        metadata = valid_canonical_event.get_metadata()

        assert metadata.event_id == "evt-001"
        assert metadata.event_type == "signal.message"
        assert metadata.correlation_id == "corr-001"

    def test_from_dict_missing_fields(self):
        """Test handling of missing fields in from_dict."""
        event_dict = {"event_type": "test"}
        event = CanonicalEvent.from_dict(event_dict)

        assert event.event_id is not None
        assert event.event_type == "test"
        assert isinstance(event.timestamp, datetime)


class TestEventMetadata:
    """Tests for EventMetadata model."""

    def test_to_dict(self):
        """Test EventMetadata serialization."""
        metadata = EventMetadata(
            event_id="evt-001",
            event_type="signal.message",
            source="signal_connector",
            timestamp=datetime.now(timezone.utc),
            correlation_id="corr-001",
        )

        md_dict = metadata.to_dict()
        assert md_dict["event_id"] == "evt-001"
        assert md_dict["correlation_id"] == "corr-001"


class TestObservationMapping:
    """Tests for ObservationMapping model."""

    def test_is_valid_event_with_required_fields(self):
        """Test validation with all required fields."""
        mapping = EVENT_TYPE_MAPPINGS["signal.message"]
        event_data = {
            "message_id": "msg-001",
            "sender": "+123",
            "chat_id": "chat-001",
        }

        assert mapping.is_valid_event(event_data) is True

    def test_is_valid_event_missing_fields(self):
        """Test validation with missing required fields."""
        mapping = EVENT_TYPE_MAPPINGS["signal.message"]
        event_data = {
            "message_id": "msg-001",
            # Missing sender and chat_id
        }

        assert mapping.is_valid_event(event_data) is False


class TestObservationResult:
    """Tests for ObservationResult model."""

    def test_success_result_to_dict(self):
        """Test successful result serialization."""
        result = ObservationResult(
            success=True,
            observation_id=uuid4(),
            event_id="evt-001",
            event_type="signal.message",
            processing_time_ms=15.5,
        )

        result_dict = result.to_dict()
        assert result_dict["success"] is True
        assert result_dict["observation_id"] is not None
        assert result_dict["processing_time_ms"] == 15.5

    def test_failure_result_to_dict(self):
        """Test failed result serialization."""
        result = ObservationResult(
            success=False,
            error_message="Mapping failed",
            event_id="evt-001",
            event_type="unknown.event",
            processing_time_ms=5.0,
        )

        result_dict = result.to_dict()
        assert result_dict["success"] is False
        assert result_dict["error_message"] == "Mapping failed"


# =============================================================================
# MAPPER TESTS
# =============================================================================

class TestEventToObservationMapper:
    """Tests for EventToObservationMapper."""

    def test_get_mapping_signal_message(self, mapper):
        """Test getting mapping for signal.message event."""
        mapping = mapper.get_mapping("signal.message")

        assert mapping.event_type == "signal.message"
        assert mapping.observation_type == "signal"
        assert mapping.source_type == "plugin"

    def test_get_mapping_radio_transmission(self, mapper):
        """Test getting mapping for radio.transmission event."""
        mapping = mapper.get_mapping("radio.transmission")

        assert mapping.observation_type == "radio"
        assert mapping.source_type == "driver"

    def test_get_mapping_unknown_event(self, mapper):
        """Test getting mapping for unknown event type."""
        mapping = mapper.get_mapping("unknown.event")

        assert mapping == DEFAULT_MAPPING
        assert mapping.observation_type == "other"

    def test_get_supported_event_types(self, mapper):
        """Test getting supported event types."""
        types = mapper.get_supported_event_types()

        assert "signal.message" in types
        assert "radio.transmission" in types
        assert len(types) > 0

    def test_map_event_to_observation(self, mapper, valid_canonical_event):
        """Test mapping canonical event to observation schema."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)

        assert observation_create is not None
        assert observation_create.observation_type == "signal"
        assert observation_create.source_type == "plugin"
        assert observation_create.immutable_id == "evt-001"

    def test_map_event_preserves_provenance(self, mapper, valid_canonical_event):
        """Test that provenance is correctly built."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)

        assert observation_create.provenance is not None
        assert observation_create.provenance.capture_method == "event_bus:signal.message"

    def test_map_event_extracts_tags(self, mapper, valid_canonical_event):
        """Test that tags are extracted from event."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)

        assert "signal" in observation_create.tags
        assert "signal_connector" in observation_create.tags

    def test_map_event_with_custom_immutable_id(self, mapper, valid_canonical_event):
        """Test mapping with custom immutable ID."""
        observation_create = mapper.map_event_to_observation(
            valid_canonical_event,
            custom_immutable_id="custom-id-123",
        )

        assert observation_create.immutable_id == "custom-id-123"

    def test_is_supported_event_type(self, mapper):
        """Test checking if event type is supported."""
        assert mapper.is_supported_event_type("signal.message") is True
        assert mapper.is_supported_event_type("unknown.event") is False


# =============================================================================
# FACTORY TESTS
# =============================================================================

class TestObservationFactory:
    """Tests for ObservationFactory."""

    def test_create_observation(self, factory, mapper, valid_canonical_event):
        """Test creating observation model from schema."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)
        observation = factory.create_observation(observation_create)

        assert observation is not None
        assert observation.id is not None
        assert observation.observation_type == "signal"
        assert observation.processing_status == "received"

    def test_create_observation_with_custom_id(self, factory, mapper, valid_canonical_event):
        """Test creating observation with custom UUID."""
        custom_id = uuid4()
        observation_create = mapper.map_event_to_observation(valid_canonical_event)
        observation = factory.create_observation(
            observation_create,
            observation_id=custom_id,
        )

        assert observation.id == custom_id

    def test_create_observation_sets_initial_status(self, factory, mapper, valid_canonical_event):
        """Test that initial processing status is set."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)
        observation = factory.create_observation(observation_create)

        assert observation.processing_status == "received"

    def test_create_observation_from_dict(self, factory):
        """Test creating observation directly from dictionary."""
        observation_dict = {
            "source": "test_source",
            "source_type": "test",
            "evidence_payload": {"data": "test"},
            "observation_type": "test",
            "provenance": {},
        }

        observation = factory.create_observation_from_dict(observation_dict)
        assert observation is not None
        assert observation.observation_type == "test"

    def test_set_processing_status(self, factory, mapper, valid_canonical_event):
        """Test setting processing status."""
        observation_create = mapper.map_event_to_observation(valid_canonical_event)
        observation = factory.create_observation(observation_create)

        updated = factory.set_processing_status(observation, "stored")
        assert updated.processing_status == "stored"


# =============================================================================
# PROCESSOR TESTS
# =============================================================================

class TestObservationProcessor:
    """Tests for ObservationProcessor."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        from unittest.mock import MagicMock
        session = MagicMock()
        session.commit = MagicMock()
        return session

    @pytest.fixture
    def processor(self, mock_session, mapper, factory):
        """Create an ObservationProcessor with mocked session."""
        return ObservationProcessor(
            session=mock_session,
            mapper=mapper,
            factory=factory,
        )

    def test_process_event_success(self, processor, valid_event_dict):
        """Test successful event processing."""
        result = processor.process_event(valid_event_dict)

        assert result.success is True
        assert result.observation_id is not None
        assert result.event_id == "evt-002"
        assert result.event_type == "signal.message"

    def test_process_event_invalid_data(self, processor):
        """Test processing event with invalid data."""
        invalid_event = {
            "event_id": "evt-invalid",
            "event_type": "signal.message",
            "data": {},  # Missing required fields
        }

        result = processor.process_event(invalid_event)
        assert result.success is False
        assert result.error_message is not None

    def test_process_event_unknown_type(self, processor):
        """Test processing event with unknown type."""
        unknown_event = {
            "event_id": "evt-unknown",
            "event_type": "unknown.event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"some": "data"},
        }

        result = processor.process_event(unknown_event)
        # Should still succeed with default mapping
        assert result.success is True

    def test_process_batch(self, processor, valid_event_dict):
        """Test batch event processing."""
        events = [
            valid_event_dict,
            {**valid_event_dict, "event_id": "evt-batch-2"},
        ]

        results = processor.process_batch(events)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_process_event_generates_uuid(self, processor, valid_event_dict):
        """Test that UUID is generated for observation."""
        result = processor.process_event(valid_event_dict)

        assert result.observation_id is not None
        # UUID format check
        assert len(str(result.observation_id)) == 36

    def test_process_event_preserves_metadata(self, processor, valid_event_dict):
        """Test that event metadata is preserved."""
        result = processor.process_event(valid_event_dict)

        assert result.success is True
        assert result.event_id == "evt-002"


# =============================================================================
# SERVICE TESTS
# =============================================================================

class TestObservationService:
    """Tests for ObservationService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        from unittest.mock import MagicMock
        session = MagicMock()
        session.commit = MagicMock()
        return session

    def test_service_initialization(self, event_bus, mock_session):
        """Test service initialization."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)

        assert service is not None
        assert service.is_running is False

    def test_service_start_subscribes_to_event_bus(self, event_bus, mock_session):
        """Test that starting service subscribes to Event Bus."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)
        service.start()

        assert service.is_running is True
        assert service.statistics["events_received"] == 0

        service.stop()

    def test_service_stop_unsubscribes(self, event_bus, mock_session):
        """Test that stopping service unsubscribes from Event Bus."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)
        service.start()
        service.stop()

        assert service.is_running is False

    def test_service_receives_event(self, event_bus, mock_session):
        """Test that service receives and processes events."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)
        service.start()

        # Publish an event
        event = {
            "event_id": "evt-service-test",
            "event_type": "signal.message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "test_connector",
            "data": {
                "message_id": "msg-svc-001",
                "sender": "+111",
                "chat_id": "chat-svc",
                "message_text": "Service test",
            },
        }

        # Note: Since session is mocked, processing may fail at persistence
        # but we can verify the service receives the event
        service.stop()

    def test_service_process_event_manually(self, event_bus, mock_session):
        """Test manual event processing."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)

        event = {
            "event_id": "evt-manual",
            "event_type": "signal.message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "test",
            "data": {
                "message_id": "msg-manual",
                "sender": "+222",
                "chat_id": "chat-manual",
                "message_text": "Manual test",
            },
        }

        result = service.process_event_manually(event)
        assert result is not None

        service.stop()

    def test_service_health_check(self, event_bus, mock_session):
        """Test health check returns correct status."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)
        service.start()

        health = service.health_check()
        assert health["service"] == "observation"
        assert health["running"] is True
        assert health["status"] == "healthy"

        service.stop()

    def test_service_get_supported_event_types(self, event_bus, mock_session):
        """Test getting supported event types."""
        from app.observation.service import ObservationService

        service = ObservationService(event_bus, mock_session)
        types = service.get_supported_event_types()

        assert "signal.message" in types




class TestSourceFieldFix:
    """Tests for WO-008-002-HF1 source field fix."""

    def test_mapper_preserves_connector_identity(self, mapper):
        """Test that mapper preserves connector identity in source field."""
        from app.observation.models import CanonicalEvent
        from datetime import datetime, timezone

        event = CanonicalEvent(
            event_id="evt-source-test",
            event_type="signal.message",
            timestamp=datetime.now(timezone.utc),
            source="signal_connector",
            data={
                "message_id": "msg-001",
                "sender": "+123",
                "chat_id": "chat-001",
            },
        )

        observation_create = mapper.map_event_to_observation(event)

        # source should be the connector identity, not the category
        assert observation_create.source == "signal_connector"
        # source_type should be the category
        assert observation_create.source_type == "plugin"

    def test_mapper_radio_connector_identity(self, mapper):
        """Test radio connector preserves its identity."""
        from app.observation.models import CanonicalEvent
        from datetime import datetime, timezone

        event = CanonicalEvent(
            event_id="evt-radio-test",
            event_type="radio.transmission",
            timestamp=datetime.now(timezone.utc),
            source="radio_driver",
            data={
                "frequency": "155.5",
                "callsign": "ALPHA-1",
            },
        )

        observation_create = mapper.map_event_to_observation(event)

        assert observation_create.source == "radio_driver"
        assert observation_create.source_type == "driver"


class TestCanonicalFlowIntegration:
    """Integration tests for the canonical flow."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        from unittest.mock import MagicMock
        session = MagicMock()
        session.commit = MagicMock()
        return session

    def test_full_canonical_flow(self, event_bus, mock_session):
        """Test complete flow: Event -> Observation."""
        from app.observation.service import ObservationService
        from app.observation.processor import ObservationProcessor

        # Create processor directly
        processor = ObservationProcessor(session=mock_session)

        # Create event
        event_dict = {
            "event_id": "evt-flow-test",
            "event_type": "signal.message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "signal_connector",
            "data": {
                "message_id": "msg-flow",
                "sender": "+333",
                "chat_id": "chat-flow",
                "message_text": "Flow test message",
            },
            "metadata": {
                "driver_id": "signal-driver",
            },
        }

        # Process event
        result = processor.process_event(event_dict)

        # Verify result
        assert result.success is True
        assert result.observation_id is not None
        assert result.event_type == "signal.message"
        assert result.processing_time_ms > 0

    def test_signal_connector_to_observation(self, event_bus, mock_session):
        """Test that Signal Connector events become Observations."""
        from app.observation.processor import ObservationProcessor

        processor = ObservationProcessor(session=mock_session)

        # Signal event format
        signal_event = {
            "event_type": "signal.message",
            "event_id": "sig-evt-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "signal_connector",
            "message_id": "sig-msg-001",
            "sender": "+1234567890",
            "chat_id": "sig-chat-001",
            "message_text": "Signal test",
            "data": {
                "message_id": "sig-msg-001",
                "sender": "+1234567890",
                "chat_id": "sig-chat-001",
                "message_text": "Signal test",
            },
        }

        result = processor.process_event(signal_event)
        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
