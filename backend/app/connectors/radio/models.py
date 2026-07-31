"""Radio data models.

Radio-specific models for transmissions and internal events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4


@dataclass
class RadioTransmission:
    """Incoming radio transmission model.

    Attributes:
        frequency: Radio frequency (e.g., "155.5 MHz").
        callsign: Radio callsign identifier.
        timestamp: Transmission timestamp (UTC normalized).
        source: Source device or channel.
        signal_strength: Optional signal strength indicator.
        modulation: Optional modulation type.
        raw_payload: Original payload for debugging.
    """

    frequency: str
    callsign: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: Optional[str] = None
    signal_strength: Optional[int] = None
    modulation: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "frequency": self.frequency,
            "callsign": self.callsign,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "signal_strength": self.signal_strength,
            "modulation": self.modulation,
        }


@dataclass
class RadioEvent:
    """Canonical event for the Event Bus.

    Normalized radio event format that all connectors produce.
    """

    event_type: str = "radio.transmission"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "radio_connector"

    # Transmission fields
    frequency: str = ""
    callsign: str = ""
    radio_source: Optional[str] = None
    signal_strength: Optional[int] = None
    modulation: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Event Bus dictionary format."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "frequency": self.frequency,
            "callsign": self.callsign,
            "radio_source": self.radio_source,
            "signal_strength": self.signal_strength,
            "modulation": self.modulation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_radio_transmission(cls, transmission: RadioTransmission) -> "RadioEvent":
        """Create from RadioTransmission."""
        return cls(
            frequency=transmission.frequency,
            callsign=transmission.callsign,
            timestamp=transmission.timestamp,  # FIX: Copy timestamp from transmission
            radio_source=transmission.source,
            signal_strength=transmission.signal_strength,
            modulation=transmission.modulation,
            metadata={
                "raw_payload_available": transmission.raw_payload is not None,
            },
        )
