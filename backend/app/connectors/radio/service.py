"""Radio Service.

Service wrapper for Radio Connector integration with dependency injection.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.radio.connector import RadioConnector, RadioConnectorError
from app.connectors.radio.parser import RadioParser


logger = logging.getLogger(__name__)


class RadioService:
    """Radio Service for dependency injection.

    Provides a configured RadioConnector instance.
    Can be registered with the application lifecycle.
    """

    _instance: Optional["RadioService"] = None

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize Radio Service.

        Args:
            event_bus: Event Bus instance. Required - raises if None.
        """
        if event_bus is None:
            raise ValueError("event_bus is required for RadioService")

        self._bus = event_bus
        self._parser = RadioParser()
        self._connector = RadioConnector(
            event_bus=self._bus,
            parser=self._parser,
        )

        logger.info("RadioService initialized")

    @classmethod
    def get_instance(cls, event_bus: EventBus) -> "RadioService":
        """Get singleton instance with required EventBus.

        Args:
            event_bus: Required Event Bus instance.

        Returns:
            RadioService instance.
        """
        if cls._instance is None:
            cls._instance = cls(event_bus=event_bus)
        elif cls._instance._bus is not event_bus:
            cls._instance = None
            cls._instance = cls(event_bus=event_bus)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @property
    def connector(self) -> RadioConnector:
        """Get the Radio Connector."""
        return self._connector

    @property
    def event_bus(self) -> EventBus:
        """Get the Event Bus."""
        return self._bus

    def receive_transmission(
        self,
        frequency: str,
        callsign: str,
        **kwargs
    ) -> bool:
        """Receive a radio transmission.

        Args:
            frequency: Radio frequency identifier.
            callsign: Radio callsign identifier.
            **kwargs: Additional transmission parameters.

        Returns:
            True if successful, False otherwise.
        """
        event = self._connector.receive_transmission(
            frequency=frequency,
            callsign=callsign,
            **kwargs
        )
        return event is not None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status."""
        return self._connector.health_check()


def get_radio_service(event_bus: EventBus) -> RadioService:
    """Get Radio Service instance with the provided EventBus.

    Args:
        event_bus: Event Bus instance to use.

    Returns:
        RadioService instance.
    """
    return RadioService.get_instance(event_bus=event_bus)
