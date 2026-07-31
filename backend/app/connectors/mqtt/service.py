"""MQTT Service.

Service wrapper for MQTT Connector integration with dependency injection.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.mqtt.connector import MQTTConnector, MQTTConnectorError
from app.connectors.mqtt.parser import MQTTParser


logger = logging.getLogger(__name__)


class MQTTService:
    """MQTT Service for dependency injection.

    Provides a configured MQTTConnector instance.
    Can be registered with the application lifecycle.
    """

    _instance: Optional["MQTTService"] = None

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize MQTT Service.

        Args:
            event_bus: Event Bus instance. Required - raises if None.
        """
        if event_bus is None:
            raise ValueError("event_bus is required for MQTTService")

        self._bus = event_bus
        self._parser = MQTTParser()
        self._connector = MQTTConnector(
            event_bus=self._bus,
            parser=self._parser,
        )

        logger.info("MQTTService initialized")

    @classmethod
    def get_instance(cls, event_bus: EventBus) -> "MQTTService":
        """Get singleton instance with required EventBus.

        Args:
            event_bus: Required Event Bus instance.

        Returns:
            MQTTService instance.
        """
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
    def connector(self) -> MQTTConnector:
        """Get the MQTT Connector."""
        return self._connector

    @property
    def event_bus(self) -> EventBus:
        """Get the Event Bus."""
        return self._bus

    def receive_message(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        **kwargs
    ) -> bool:
        """Receive an MQTT message.

        Args:
            topic: The MQTT topic.
            payload: The message payload.
            qos: Quality of Service level.
            **kwargs: Additional message parameters.

        Returns:
            True if successful, False otherwise.
        """
        event = self._connector.receive_message(
            topic=topic,
            payload=payload,
            qos=qos,
            **kwargs
        )
        return event is not None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status."""
        return self._connector.health_check()


def get_mqtt_service(event_bus: EventBus) -> MQTTService:
    """Get MQTT Service instance with the provided EventBus.

    Args:
        event_bus: Event Bus instance to use.

    Returns:
        MQTTService instance.
    """
    return MQTTService.get_instance(event_bus=event_bus)
