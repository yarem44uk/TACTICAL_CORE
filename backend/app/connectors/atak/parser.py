"""ATAK map object parser.

Parses incoming ATAK map object data into ATAKMapObject instances.
Handles various formats and validates required fields.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.connectors.atak.models import ATAKMapObject


logger = logging.getLogger(__name__)


class ATAKParserError(Exception):
    """Raised when ATAK map object parsing fails."""

    pass


class ATAKParser:
    """Parses ATAK map object data into ATAKMapObject instances.

    ATAK map object contract requires:
    - uid: Unique identifier
    - location: Location data (dict with lat, lon, etc.)
    """

    def __init__(self):
        """Initialize the parser."""
        pass

    def parse(
        self,
        uid: str,
        location: Dict[str, Any],
        timestamp: Optional[datetime] = None,
        object_type: Optional[str] = None,
        callsign: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ATAKMapObject:
        """Parse ATAK map object components into an ATAKMapObject.

        Args:
            uid: Unique identifier for the map object.
            location: Location data (must contain lat, lon at minimum).
            timestamp: Optional object timestamp.
            object_type: Optional type of map object.
            callsign: Optional callsign identifier.
            source: Optional source device or channel.
            metadata: Optional additional metadata.

        Returns:
            ATAKMapObject instance.

        Raises:
            ATAKParserError: If parsing fails.
        """
        # Validate required fields
        if not uid:
            raise ATAKParserError("Empty uid")

        if not location:
            raise ATAKParserError("Invalid location format")

        # Validate location contains required coordinates
        if not self._is_valid_location(location):
            raise ATAKParserError("Invalid location format")

        # Parse timestamp
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                # Convert timezone-aware datetime to UTC
                timestamp = timestamp.astimezone(timezone.utc)
        elif isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, str):
            ts = timestamp.replace("Z", "+00:00")
            try:
                timestamp = datetime.fromisoformat(ts)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                else:
                    timestamp = timestamp.astimezone(timezone.utc)
            except ValueError:
                try:
                    timestamp = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    timestamp = datetime.now(timezone.utc)

        # Create map object
        map_object = ATAKMapObject(
            uid=uid,
            location=location,
            timestamp=timestamp,
            object_type=object_type,
            callsign=callsign,
            source=source,
            metadata=metadata or {},
        )

        logger.debug(
            f"Parsed ATAK map object: uid={map_object.uid}, "
            f"location={map_object.location}"
        )

        return map_object

    def _is_valid_location(self, location: Dict[str, Any]) -> bool:
        """Validate location format.

        Args:
            location: Location dictionary to validate.

        Returns:
            True if valid format.
        """
        if not isinstance(location, dict):
            return False

        # Must have lat and lon at minimum
        if "lat" not in location or "lon" not in location:
            return False

        lat = location.get("lat")
        lon = location.get("lon")

        # Validate coordinate ranges
        if not isinstance(lat, (int, float)):
            return False
        if not isinstance(lon, (int, float)):
            return False
        if lat < -90 or lat > 90:
            return False
        if lon < -180 or lon > 180:
            return False

        return True

    def parse_dict(self, map_object_dict: Dict[str, Any]) -> ATAKMapObject:
        """Parse ATAK map object from dictionary.

        Args:
            map_object_dict: Dictionary containing map object data.

        Returns:
            ATAKMapObject instance.

        Raises:
            ATAKParserError: If required fields are missing.
        """
        # Validate required fields
        if "uid" not in map_object_dict:
            raise ATAKParserError("Missing required field: uid")
        if "location" not in map_object_dict:
            raise ATAKParserError("Missing required field: location")

        return self.parse(
            uid=map_object_dict["uid"],
            location=map_object_dict["location"],
            timestamp=map_object_dict.get("timestamp"),
            object_type=map_object_dict.get("object_type"),
            callsign=map_object_dict.get("callsign"),
            source=map_object_dict.get("source"),
            metadata=map_object_dict.get("metadata"),
        )
