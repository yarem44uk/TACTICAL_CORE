"""Telegram Connector.

Main connector class that receives Telegram messages and publishes to Event Bus.
Does NOT write directly to Repository.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.telegram.models import TelegramMessage, TelegramEvent
from app.connectors.telegram.parser import TelegramParser, TelegramParserError


logger = logging.getLogger(__name__)


class TelegramConnectorError(Exception):
    """Raised when Telegram connector operations fail."""

    pass


class TelegramConnector:
    """Telegram message connector.

    Receives Telegram messages, parses them, normalizes to canonical Event format,
    and publishes to the Event Bus.

    Does NOT access Repository directly. Uses Event Bus only.

    Usage:
        >>> event_bus = EventBus()
        >>> connector = TelegramConnector(event_bus)
        >>> connector.receive_message(raw_payload)
    """

    def __init__(
        self,
        event_bus: EventBus,
        parser: Optional[TelegramParser] = None,
    ):
        """Initialize the Telegram Connector.

        Args:
            event_bus: Event Bus instance for publishing.
            parser: Optional Telegram parser instance.
        """
        self._bus = event_bus
        self._parser = parser or TelegramParser()
        self._enabled = True
        self._message_count = 0
        self._error_count = 0

        logger.info("TelegramConnector initialized")

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
        logger.info("TelegramConnector enabled")

    def disable(self) -> None:
        """Disable the connector."""
        self._enabled = False
        logger.info("TelegramConnector disabled")

    def receive_message(self, payload: Dict[str, Any]) -> Optional[TelegramEvent]:
        """Receive and process a Telegram message.

        Parses the payload, normalizes to TelegramEvent, and publishes to Event Bus.

        Args:
            payload: Raw Telegram message payload.

        Returns:
            Created TelegramEvent if successful, None if failed.
        """
        if not self._enabled:
            logger.debug("TelegramConnector disabled, skipping message")
            return None

        try:
            # Parse the payload
            message = self._parser.parse(payload)

            # Normalize to canonical Event
            event = TelegramEvent.from_telegram_message(message)

            # Publish to Event Bus
            self._bus.publish(event.event_type, event.to_dict())

            self._message_count += 1
            logger.info(
                f"Telegram message published: id={event.message_id}, "
                f"sender={event.sender_display_name}"
            )

            return event

        except TelegramParserError as e:
            self._error_count += 1
            logger.error(f"Failed to parse Telegram message: {e}")
            return None

        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process Telegram message: {e}")
            return None

    def receive_batch(self, payloads: List[Dict[str, Any]]) -> List[TelegramEvent]:
        """Receive and process multiple Telegram messages.

        Args:
            payloads: List of raw Telegram payloads.

        Returns:
            List of successfully created TelegramEvents.
        """
        events = []

        for payload in payloads:
            event = self.receive_message(payload)
            if event:
                events.append(event)

        logger.info(f"Batch processed: {len(events)}/{len(payloads)} successful")
        return events

    def health_check(self) -> Dict[str, Any]:
        """Get connector health status.

        Returns:
            Health status dictionary.
        """
        return {
            "connector": "telegram",
            "enabled": self._enabled,
            "messages_processed": self._message_count,
            "errors": self._error_count,
            "status": "healthy" if self._error_count == 0 else "degraded",
        }
