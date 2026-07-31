"""Telegram Service.

Service wrapper for Telegram Connector integration with dependency injection.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.telegram.connector import TelegramConnector, TelegramConnectorError
from app.connectors.telegram.parser import TelegramParser


logger = logging.getLogger(__name__)


class TelegramService:
    """Telegram Service for dependency injection.

    Provides a configured TelegramConnector instance.
    Can be registered with the application lifecycle.
    """

    _instance: Optional["TelegramService"] = None

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize Telegram Service.

        Args:
            event_bus: Event Bus instance. Required - raises if None.
        """
        if event_bus is None:
            raise ValueError("event_bus is required for TelegramService")

        self._bus = event_bus
        self._parser = TelegramParser()
        self._connector = TelegramConnector(
            event_bus=self._bus,
            parser=self._parser,
        )

        logger.info("TelegramService initialized")

    @classmethod
    def get_instance(cls, event_bus: Optional[EventBus] = None) -> "TelegramService":
        """Get singleton instance with required EventBus.

        Args:
            event_bus: Required Event Bus instance.

        Returns:
            TelegramService instance.

        Raises:
            ValueError: If event_bus is not provided.
        """
        if event_bus is None:
            raise ValueError("event_bus is required for TelegramService.get_instance()")
        if cls._instance is None:
            cls._instance = cls(event_bus=event_bus)
        elif cls._instance._bus is not event_bus:
            # If different bus requested, reset
            cls._instance = None
            cls._instance = cls(event_bus=event_bus)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @property
    def connector(self) -> TelegramConnector:
        """Get the Telegram Connector."""
        return self._connector

    @property
    def event_bus(self) -> EventBus:
        """Get the Event Bus."""
        return self._bus

    def receive_message(self, payload: Dict[str, Any]) -> bool:
        """Receive a Telegram message.

        Args:
            payload: Raw Telegram payload.

        Returns:
            True if successful, False otherwise.
        """
        event = self._connector.receive_message(payload)
        return event is not None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status."""
        return self._connector.health_check()


def get_telegram_service(event_bus: EventBus) -> TelegramService:
    """Get Telegram Service instance with the provided EventBus.

    Args:
        event_bus: Event Bus instance to use.

    Returns:
        TelegramService instance using the provided EventBus.
    """
    # Reset instance to ensure fresh creation with new bus
    TelegramService._instance = None
    service = TelegramService(event_bus=event_bus)
    TelegramService._instance = service
    return service
