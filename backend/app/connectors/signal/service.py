"""
Signal Service.

Service wrapper for Signal Connector integration with dependency injection.
"""

import logging
from typing import Optional, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.signal.connector import SignalConnector, SignalConnectorError
from app.connectors.signal.parser import SignalParser


logger = logging.getLogger(__name__)


class SignalService:
    """
    Signal Service for dependency injection.

    Provides a configured SignalConnector instance.
    Can be registered with the application lifecycle.
    """

    _instance: Optional["SignalService"] = None

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize Signal Service.

        Args:
            event_bus: Event Bus instance. Creates new if not provided.
        """
        self._bus = event_bus or EventBus()
        self._parser = SignalParser()
        self._connector = SignalConnector(
            event_bus=self._bus,
            parser=self._parser,
        )

        logger.info("SignalService initialized")

    @classmethod
    def get_instance(cls) -> "SignalService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @property
    def connector(self) -> SignalConnector:
        """Get the Signal Connector."""
        return self._connector

    @property
    def event_bus(self) -> EventBus:
        """Get the Event Bus."""
        return self._bus

    def receive_message(self, payload: Dict[str, Any]) -> bool:
        """
        Receive a Signal message.

        Args:
            payload: Raw Signal payload.

        Returns:
            True if successful, False otherwise.
        """
        event = self._connector.receive_message(payload)
        return event is not None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status."""
        return self._connector.health_check()


def get_signal_service(event_bus: Optional[EventBus] = None) -> SignalService:
    """
    Get Signal Service instance.

    Args:
        event_bus: Optional Event Bus instance.

    Returns:
        SignalService instance.
    """
    return SignalService.get_instance()
