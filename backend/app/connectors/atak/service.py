"""ATAK Service.

Service layer for ATAK Connector with dependency injection support.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.atak.connector import ATAKConnector, ATAKConnectorError
from app.connectors.atak.parser import ATAKParser


logger = logging.getLogger(__name__)


class ATAKService:
    """ATAK service with DI support.

    Provides access to ATAKConnector with proper dependency injection.
    """

    _instance: Optional["ATAKService"] = None

    def __init__(self, event_bus: EventBus):
        """Initialize ATAK service.

        Args:
            event_bus: Event Bus instance for publishing.
        """
        if event_bus is None:
            raise ValueError("event_bus is required for ATAKService")

        self._event_bus = event_bus
        self._connector: Optional[ATAKConnector] = None
        self._parser: Optional[ATAKParser] = None

        logger.info("ATAKService initialized")

    @classmethod
    def get_instance(cls, event_bus: EventBus) -> "ATAKService":
        """Get singleton instance with required EventBus.

        Args:
            event_bus: Required Event Bus instance.

        Returns:
            ATAKService instance.
        """
        if cls._instance is None:
            cls._instance = cls(event_bus=event_bus)
        elif cls._instance._event_bus is not event_bus:
            # Different EventBus provided, recreate
            cls._instance = None
            cls._instance = cls(event_bus=event_bus)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @property
    def connector(self) -> ATAKConnector:
        """Get or create ATAK connector.

        Returns:
            ATAKConnector instance.
        """
        if self._connector is None:
            self._connector = ATAKConnector(self._event_bus, self._parser)
        return self._connector

    @property
    def parser(self) -> ATAKParser:
        """Get or create ATAK parser.

        Returns:
            ATAKParser instance.
        """
        if self._parser is None:
            self._parser = ATAKParser()
        return self._parser

    def set_parser(self, parser: ATAKParser) -> None:
        """Set custom parser.

        Args:
            parser: ATAKParser instance to use.
        """
        self._parser = parser
        # Reset connector to use new parser
        self._connector = None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status.

        Returns:
            Health status dictionary.
        """
        result = {
            "service": "atak",
            "connector_initialized": self._connector is not None,
        }
        if self._connector is not None:
            connector_health = self._connector.health_check()
            result.update(connector_health)
        return result


def get_atak_service(event_bus: EventBus) -> ATAKService:
    """Get ATAK service instance with the provided EventBus.

    Args:
        event_bus: Event Bus instance to use.

    Returns:
        ATAKService instance.

    Raises:
        ValueError: If event_bus is None.
    """
    if event_bus is None:
        raise ValueError("ATAKService requires an EventBus instance")
    return ATAKService.get_instance(event_bus=event_bus)


def reset_atak_service() -> None:
    """Reset the module-level ATAK service instance.

    For testing purposes.
    """
    ATAKService.reset_instance()
