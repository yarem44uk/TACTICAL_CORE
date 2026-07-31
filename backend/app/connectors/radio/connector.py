"""Radio Connector.

Main connector class that receives radio transmissions and publishes to Event Bus.
Does NOT write directly to Repository.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.radio.models import RadioTransmission, RadioEvent
from app.connectors.radio.parser import RadioParser, RadioParserError


logger = logging.getLogger(__name__)


class RadioConnectorError(Exception):
    """Raised when radio connector operations fail."""

    pass


class RadioConnector:
    """Radio transmission connector.

    Receives radio transmissions, parses them, normalizes to canonical Event format,
    and publishes to the Event Bus.

    Does NOT access Repository directly. Uses Event Bus only.

    Usage:
        >>> event_bus = EventBus()
        >>> connector = RadioConnector(event_bus)
        >>> connector.receive_transmission(frequency, callsign)
    """

    def __init__(
        self,
        event_bus: EventBus,
        parser: Optional[RadioParser] = None,
    ):
        """Initialize the Radio Connector.

        Args:
            event_bus: Event Bus instance for publishing.
            parser: Optional Radio parser instance.
        """
        self._bus = event_bus
        self._parser = parser or RadioParser()
        self._enabled = True
        self._transmission_count = 0
        self._error_count = 0

        logger.info("RadioConnector initialized")

    @property
    def is_enabled(self) -> bool:
        """Check if connector is enabled."""
        return self._enabled

    @property
    def transmission_count(self) -> int:
        """Get number of transmissions processed."""
        return self._transmission_count

    @property
    def error_count(self) -> int:
        """Get number of errors encountered."""
        return self._error_count

    def enable(self) -> None:
        """Enable the connector."""
        self._enabled = True
        logger.info("RadioConnector enabled")

    def disable(self) -> None:
        """Disable the connector."""
        self._enabled = False
        logger.info("RadioConnector disabled")

    def receive_transmission(
        self,
        frequency: str,
        callsign: str,
        timestamp: Optional[datetime] = None,
        source: Optional[str] = None,
        signal_strength: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> Optional[RadioEvent]:
        """Receive and process a radio transmission.

        Args:
            frequency: Radio frequency identifier.
            callsign: Radio callsign identifier.
            timestamp: Optional transmission timestamp.
            source: Optional source device or channel.
            signal_strength: Optional signal strength (0-100).
            modulation: Optional modulation type.

        Returns:
            Created RadioEvent if successful, None if failed.
        """
        if not self._enabled:
            logger.debug("RadioConnector disabled, skipping transmission")
            return None

        try:
            # Parse the transmission
            transmission = self._parser.parse(
                frequency=frequency,
                callsign=callsign,
                timestamp=timestamp,
                source=source,
                signal_strength=signal_strength,
                modulation=modulation,
            )

            # Normalize to canonical Event
            event = RadioEvent.from_radio_transmission(transmission)

            # Publish to Event Bus
            self._bus.publish(event.event_type, event.to_dict())

            self._transmission_count += 1
            logger.info(
                f"Radio transmission published: frequency={event.frequency}, "
                f"callsign={event.callsign}"
            )

            return event

        except RadioParserError as e:
            self._error_count += 1
            logger.error(f"Failed to parse radio transmission: {e}")
            return None

        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process radio transmission: {e}")
            return None

    def receive_batch(
        self,
        transmissions: List[Dict[str, Any]],
    ) -> List[RadioEvent]:
        """Receive and process multiple radio transmissions.

        Args:
            transmissions: List of transmission dictionaries.

        Returns:
            List of successfully created RadioEvents.
        """
        events = []

        for trans in transmissions:
            event = self.receive_transmission(
                frequency=trans.get("frequency", ""),
                callsign=trans.get("callsign", ""),
                timestamp=trans.get("timestamp"),
                source=trans.get("source"),
                signal_strength=trans.get("signal_strength"),
                modulation=trans.get("modulation"),
            )
            if event:
                events.append(event)

        logger.info(f"Batch processed: {len(events)}/{len(transmissions)} successful")
        return events

    def health_check(self) -> Dict[str, Any]:
        """Get connector health status.

        Returns:
            Health status dictionary.
        """
        return {
            "connector": "radio",
            "enabled": self._enabled,
            "transmissions_processed": self._transmission_count,
            "errors": self._error_count,
            "status": "healthy" if self._error_count == 0 else "degraded",
        }
