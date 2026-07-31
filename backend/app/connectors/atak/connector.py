"""ATAK Connector.

Main connector class that receives ATAK map objects and publishes to Event Bus.
Does NOT write directly to Repository.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.atak.models import ATAKMapObject, ATAKEvent
from app.connectors.atak.parser import ATAKParser, ATAKParserError


logger = logging.getLogger(__name__)


class ATAKConnectorError(Exception):
    """Raised when ATAK connector operations fail."""

    pass


class ATAKConnector:
    """ATAK map object connector.

    Receives ATAK map objects, parses them, normalizes to canonical Event format,
    and publishes to the Event Bus.

    Does NOT access Repository directly. Uses Event Bus only.

    Usage:
        >>> event_bus = EventBus()
        >>> connector = ATAKConnector(event_bus)
        >>> connector.receive_map_object(uid, location)
    """

    def __init__(
        self,
        event_bus: EventBus,
        parser: Optional[ATAKParser] = None,
    ):
        """Initialize the ATAK Connector.

        Args:
            event_bus: Event Bus instance for publishing.
            parser: Optional ATAK parser instance.
        """
        self._bus = event_bus
        self._parser = parser or ATAKParser()
        self._enabled = True
        self._object_count = 0
        self._error_count = 0

        logger.info("ATAKConnector initialized")

    @property
    def is_enabled(self) -> bool:
        """Check if connector is enabled."""
        return self._enabled

    @property
    def object_count(self) -> int:
        """Get number of map objects processed."""
        return self._object_count

    @property
    def error_count(self) -> int:
        """Get number of errors encountered."""
        return self._error_count

    def enable(self) -> None:
        """Enable the connector."""
        self._enabled = True
        logger.info("ATAKConnector enabled")

    def disable(self) -> None:
        """Disable the connector."""
        self._enabled = False
        logger.info("ATAKConnector disabled")

    def receive_map_object(
        self,
        uid: str,
        location: Dict[str, Any],
        timestamp: Optional[datetime] = None,
        object_type: Optional[str] = None,
        callsign: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ATAKEvent]:
        """Receive and process an ATAK map object.

        Args:
            uid: Unique identifier for the map object.
            location: Location data (must contain lat, lon).
            timestamp: Optional object timestamp.
            object_type: Optional type of map object.
            callsign: Optional callsign identifier.
            source: Optional source device or channel.
            metadata: Optional additional metadata.

        Returns:
            Created ATAKEvent if successful, None if failed.
        """
        if not self._enabled:
            logger.debug("ATAKConnector disabled, skipping map object")
            return None

        try:
            # Parse the map object
            map_object = self._parser.parse(
                uid=uid,
                location=location,
                timestamp=timestamp,
                object_type=object_type,
                callsign=callsign,
                source=source,
                metadata=metadata,
            )

            # Normalize to canonical Event
            event = ATAKEvent.from_atak_map_object(map_object)

            # Publish to Event Bus
            self._bus.publish(event.event_type, event.to_dict())

            self._object_count += 1
            logger.info(
                f"ATAK map object published: uid={event.uid}, "
                f"location={event.location}"
            )

            return event

        except ATAKParserError as e:
            self._error_count += 1
            logger.error(f"Failed to parse ATAK map object: {e}")
            return None

        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process ATAK map object: {e}")
            return None

    def receive_batch(
        self,
        map_objects: List[Dict[str, Any]],
    ) -> List[ATAKEvent]:
        """Receive and process multiple ATAK map objects.

        Args:
            map_objects: List of map object dictionaries.

        Returns:
            List of successfully created ATAKEvents.
        """
        events = []

        for obj in map_objects:
            event = self.receive_map_object(
                uid=obj.get("uid", ""),
                location=obj.get("location", {}),
                timestamp=obj.get("timestamp"),
                object_type=obj.get("object_type"),
                callsign=obj.get("callsign"),
                source=obj.get("source"),
                metadata=obj.get("metadata"),
            )
            if event:
                events.append(event)

        logger.info(f"Batch processed: {len(events)}/{len(map_objects)} successful")
        return events

    def health_check(self) -> Dict[str, Any]:
        """Get connector health status.

        Returns:
            Health status dictionary.
        """
        return {
            "connector": "atak",
            "enabled": self._enabled,
            "objects_processed": self._object_count,
            "errors": self._error_count,
            "status": "healthy" if self._error_count == 0 else "degraded",
        }
