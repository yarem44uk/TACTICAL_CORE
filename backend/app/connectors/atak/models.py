"""ATAK data models.

ATAK-specific models for map objects and internal events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4


@dataclass
class ATAKMapObject:
    """Incoming ATAK map object model.

    Represents a map object received from ATAK/CoT system.
    Conforms to the atak.map_object event type mapping.

    Attributes:
        uid: Unique identifier for the map object.
        location: Location data (dict with lat, lon, etc.).
        timestamp: Object timestamp (UTC normalized).
        object_type: Type of map object (cotType).
        callsign: Optional callsign identifier.
        source: Source device or channel.
        metadata: Additional object metadata.
    """

    uid: str
    location: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    object_type: Optional[str] = None
    callsign: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uid": self.uid,
            "location": self.location,
            "timestamp": self.timestamp.isoformat(),
            "object_type": self.object_type,
            "callsign": self.callsign,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class ATAKEvent:
    """Canonical event for the Event Bus.

    Normalized ATAK event format that all connectors produce.
    Conforms to EVENT_TYPE_MAPPINGS["atak.map_object"].
    """

    event_type: str = "atak.map_object"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "atak_connector"

    # Map object fields (required by mapping)
    uid: str = ""
    location: Dict[str, Any] = field(default_factory=dict)

    # Optional fields
    object_type: Optional[str] = None
    callsign: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Event Bus dictionary format."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "uid": self.uid,
            "location": self.location,
            "object_type": self.object_type,
            "callsign": self.callsign,
            "metadata": self.metadata,
        }

    @classmethod
    def from_atak_map_object(cls, map_object: ATAKMapObject) -> "ATAKEvent":
        """Create from ATAKMapObject.

        Args:
            map_object: The parsed ATAK map object.

        Returns:
            ATAKEvent instance.
        """
        return cls(
            uid=map_object.uid,
            location=map_object.location,
            timestamp=map_object.timestamp,
            object_type=map_object.object_type,
            callsign=map_object.callsign,
            metadata={
                "source": map_object.source,
                "metadata_available": bool(map_object.metadata),
            },
        )
