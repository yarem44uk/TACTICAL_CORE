"""Observation Service Models.

Data models for the Observation Service.
Defines the structure of Canonical Events and Observation mappings.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


@dataclass
class EventMetadata:
    """Metadata extracted from a Canonical Event.

    Attributes:
        event_id: Unique event identifier.
        event_type: Type of the event.
        source: Source system that created the event.
        timestamp: When the event was created.
        correlation_id: Optional correlation ID for tracing.
    """

    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "metadata": self.metadata,
        }


@dataclass
class CanonicalEvent:
    """Canonical Event received from the Event Bus.

    This is the standardized event format produced by all connectors.
    The Observation Service receives these events and converts them
    to Observations.

    Attributes:
        event_id: Unique event identifier.
        event_type: Type identifier (e.g., "signal.message", "radio.transmission").
        timestamp: When the event occurred.
        source: Connector source (e.g., "signal_connector").
        data: Event-specific payload data.
        metadata: Additional event metadata.
    """

    event_id: str
    event_type: str
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, event_dict: Dict[str, Any]) -> "CanonicalEvent":
        """Create CanonicalEvent from dictionary.

        Args:
            event_dict: Dictionary from Event Bus.

        Returns:
            CanonicalEvent instance.
        """
        # Parse timestamp
        ts = event_dict.get("timestamp")
        if isinstance(ts, str):
            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, datetime):
            timestamp = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        return cls(
            event_id=str(event_dict.get("event_id", uuid4())),
            event_type=str(event_dict.get("event_type", "unknown")),
            timestamp=timestamp,
            source=str(event_dict.get("source", "unknown")),
            data=event_dict.get("data", event_dict),
            metadata=event_dict.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "metadata": self.metadata,
        }

    def get_metadata(self) -> EventMetadata:
        """Extract EventMetadata from event."""
        return EventMetadata(
            event_id=self.event_id,
            event_type=self.event_type,
            source=self.source,
            timestamp=self.timestamp,
            correlation_id=self.metadata.get("correlation_id"),
            trace_id=self.metadata.get("trace_id"),
            span_id=self.metadata.get("span_id"),
            metadata=self.metadata,
        )


@dataclass
class ObservationMapping:
    """Mapping configuration from event type to observation type.

    Defines how each canonical event type should be converted to
    an Observation.

    Attributes:
        event_type: The canonical event type pattern.
        observation_type: The target ObservationType value.
        source_type: The source type for the observation.
        default_confidence: Default confidence if not provided.
        required_fields: List of required fields in event data.
        field_mapping: Mapping of event fields to observation fields.
    """

    event_type: str
    observation_type: str
    source_type: str = "plugin"
    default_confidence: float = 0.5
    required_fields: List[str] = field(default_factory=list)
    field_mapping: Dict[str, str] = field(default_factory=dict)

    def is_valid_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if event data has required fields.

        Args:
            event_data: Event data dictionary.

        Returns:
            True if all required fields are present.
        """
        return all(field in event_data for field in self.required_fields)


# Predefined event type mappings
EVENT_TYPE_MAPPINGS = {
    "signal.message": ObservationMapping(
        event_type="signal.message",
        observation_type="signal",
        source_type="plugin",
        default_confidence=0.7,
        required_fields=["message_id", "sender", "chat_id"],
        field_mapping={
            "sender": "source",
            "message_text": "content",
            "chat_id": "channel",
        },
    ),
    "radio.transmission": ObservationMapping(
        event_type="radio.transmission",
        observation_type="radio",
        source_type="driver",
        default_confidence=0.6,
        required_fields=["frequency", "callsign"],
        field_mapping={
            "frequency": "frequency",
            "callsign": "callsign",
        },
    ),
    "atak.map_object": ObservationMapping(
        event_type="atak.map_object",
        observation_type="atak",
        source_type="plugin",
        default_confidence=0.8,
        required_fields=["uid", "location"],
        field_mapping={},
    ),
    "mqtt.message": ObservationMapping(
        event_type="mqtt.message",
        observation_type="sensor",
        source_type="driver",
        default_confidence=0.7,
        required_fields=["topic", "payload"],
        field_mapping={},
    ),
    "telegram.message": ObservationMapping(
        event_type="telegram.message",
        observation_type="other",
        source_type="plugin",
        default_confidence=0.7,
        required_fields=["chat_id", "text"],
        field_mapping={},
    ),
    "rest.webhook": ObservationMapping(
        event_type="rest.webhook",
        observation_type="rest_api",
        source_type="api",
        default_confidence=0.8,
        required_fields=["endpoint"],
        field_mapping={},
    ),
}

# Default mapping for unknown event types
DEFAULT_MAPPING = ObservationMapping(
    event_type="*",
    observation_type="other",
    source_type="plugin",
    default_confidence=0.5,
    required_fields=[],
    field_mapping={},
)


@dataclass
class ObservationResult:
    """Result of processing a Canonical Event.

    Attributes:
        success: Whether processing succeeded.
        observation_id: UUID of created observation (if success).
        error_message: Error message (if failure).
        event_id: Original event ID.
        event_type: Original event type.
        processing_time_ms: Time taken to process.
    """

    success: bool
    observation_id: Optional[UUID] = None
    error_message: Optional[str] = None
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "observation_id": str(self.observation_id) if self.observation_id else None,
            "error_message": self.error_message,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "processing_time_ms": self.processing_time_ms,
        }
