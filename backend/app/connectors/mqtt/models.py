"""MQTT data models.

MQTT-specific models for messages and internal events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4


@dataclass
class MQTTMessage:
    """Incoming MQTT message model.

    Attributes:
        topic: MQTT topic the message was published to.
        payload: Message payload (decoded or raw).
        qos: Quality of Service level (0, 1, or 2).
        timestamp: Message timestamp (UTC normalized).
        client_id: Client that published the message.
        retain: Whether message was retained.
        raw_payload: Original payload for debugging.
    """

    topic: str
    payload: str
    qos: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    client_id: Optional[str] = None
    retain: bool = False
    raw_payload: Optional[Dict[str, Any]] = None

    @property
    def has_metadata(self) -> bool:
        """Check if message has additional metadata."""
        return self.client_id is not None or self.retain

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "payload": self.payload,
            "qos": self.qos,
            "timestamp": self.timestamp.isoformat(),
            "client_id": self.client_id,
            "retain": self.retain,
        }


@dataclass
class MQTTEvent:
    """Canonical event for the Event Bus.

    Normalized MQTT event format that all connectors produce.
    """

    event_type: str = "mqtt.message"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "mqtt_connector"

    # Message fields
    topic: str = ""
    payload: str = ""
    qos: int = 0
    client_id: Optional[str] = None
    retain: bool = False

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Event Bus dictionary format."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "topic": self.topic,
            "payload": self.payload,
            "qos": self.qos,
            "client_id": self.client_id,
            "retain": self.retain,
            "metadata": self.metadata,
        }

    @classmethod
    def from_mqtt_message(cls, message: MQTTMessage) -> "MQTTEvent":
        """Create from MQTTMessage."""
        return cls(
            topic=message.topic,
            payload=message.payload,
            qos=message.qos,
            client_id=message.client_id,
            retain=message.retain,
            metadata={
                "raw_payload_available": message.raw_payload is not None,
            },
        )
