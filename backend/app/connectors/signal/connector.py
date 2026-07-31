"""
Signal Connector.

Main connector class that receives Signal messages and publishes to Event Bus.
Does NOT write directly to Repository.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.signal.models import SignalMessage, SignalEvent
from app.connectors.signal.parser import SignalParser, SignalParserError


logger = logging.getLogger(__name__)


class SignalConnectorError(Exception):
    """Raised when Signal connector operations fail."""
    pass


class SignalConnector:
    """
    Signal message connector.

    Receives Signal messages, parses them, normalizes to canonical Event format,
    and publishes to the Event Bus.

    Does NOT access Repository directly. Uses Event Bus only.

    Usage:
        >>> event_bus = EventBus()
        >>> connector = SignalConnector(event_bus)
        >>> connector.receive_message(raw_payload)
    """

    def __init__(
        self,
        event_bus: EventBus,
        parser: Optional[SignalParser] = None,
    ):
        """
        Initialize the Signal Connector.

        Args:
            event_bus: Event Bus instance for publishing.
            parser: Optional Signal parser instance.
        """
        self._bus = event_bus
        self._parser = parser or SignalParser()
        self._enabled = True
        self._message_count = 0
        self._error_count = 0

        logger.info("SignalConnector initialized")

    @property
    def is_enabled(self) -> bool:
        """Check if connector is enabled."""
        return self._enabled

    @property
    def message_count(self) -> int:
        """Get number of messages processed."""
        return self._message_count

    @property
    def error_count(self) -> int:
        """Get number of errors encountered."""
        return self._error_count

    def enable(self) -> None:
        """Enable the connector."""
        self._enabled = True
        logger.info("SignalConnector enabled")

    def disable(self) -> None:
        """Disable the connector."""
        self._enabled = False
        logger.info("SignalConnector disabled")

    def receive_message(self, payload: Dict[str, Any]) -> Optional[SignalEvent]:
        """
        Receive and process a Signal message.

        Parses the payload, normalizes to SignalEvent, and publishes to Event Bus.

        Args:
            payload: Raw Signal message payload.

        Returns:
            Created SignalEvent if successful, None if failed.
        """
        if not self._enabled:
            logger.debug("SignalConnector disabled, skipping message")
            return None

        try:
            # Parse the payload
            message = self._parser.parse(payload)

            # Normalize to canonical Event
            event = SignalEvent.from_signal_message(message)

            # Publish to Event Bus
            self._bus.publish(event.event_type, event.to_dict())

            self._message_count += 1
            logger.info(
                f"Signal message published: id={event.message_id}, "
                f"sender={event.sender}"
            )

            return event

        except SignalParserError as e:
            self._error_count += 1
            logger.error(f"Failed to parse Signal message: {e}")
            return None

        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process Signal message: {e}")
            return None

    def receive_batch(self, payloads: List[Dict[str, Any]]) -> List[SignalEvent]:
        """
        Receive and process multiple Signal messages.

        Args:
            payloads: List of raw Signal payloads.

        Returns:
            List of successfully created SignalEvents.
        """
        events = []

        for payload in payloads:
            event = self.receive_message(payload)
            if event:
                events.append(event)

        logger.info(f"Batch processed: {len(events)}/{len(payloads)} successful")
        return events

    def health_check(self) -> Dict[str, Any]:
        """
        Get connector health status.

        Returns:
            Health status dictionary.
        """
        return {
            "connector": "signal",
            "enabled": self._enabled,
            "messages_processed": self._message_count,
            "errors": self._error_count,
            "status": "healthy" if self._error_count == 0 else "degraded",
        }
