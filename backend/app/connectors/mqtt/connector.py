"""MQTT Connector.

Main connector class that receives MQTT messages and publishes to Event Bus.
Does NOT write directly to Repository.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.core.event_bus import EventBus
from app.connectors.mqtt.models import MQTTMessage, MQTTEvent
from app.connectors.mqtt.parser import MQTTParser, MQTTParserError


logger = logging.getLogger(__name__)


class MQTTConnectorError(Exception):
    """Raised when MQTT connector operations fail."""

    pass


class MQTTConnector:
    """MQTT message connector.

    Receives MQTT messages, parses them, normalizes to canonical Event format,
    and publishes to the Event Bus.

    Does NOT access Repository directly. Uses Event Bus only.

    Usage:
        >>> event_bus = EventBus()
        >>> connector = MQTTConnector(event_bus)
        >>> connector.receive_message(topic, payload)
    """

    def __init__(
        self,
        event_bus: EventBus,
        parser: Optional[MQTTParser] = None,
    ):
        """Initialize the MQTT Connector.

        Args:
            event_bus: Event Bus instance for publishing.
            parser: Optional MQTT parser instance.
        """
        self._bus = event_bus
        self._parser = parser or MQTTParser()
        self._enabled = True
        self._message_count = 0
        self._error_count = 0

        logger.info("MQTTConnector initialized")

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
        logger.info("MQTTConnector enabled")

    def disable(self) -> None:
        """Disable the connector."""
        self._enabled = False
        logger.info("MQTTConnector disabled")

    def receive_message(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        client_id: Optional[str] = None,
        retain: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> Optional[MQTTEvent]:
        """Receive and process an MQTT message.

        Parses the message, normalizes to MQTTEvent, and publishes to Event Bus.

        Args:
            topic: The MQTT topic.
            payload: The message payload.
            qos: Quality of Service level.
            client_id: Client that published the message.
            retain: Whether message was retained.
            timestamp: Optional message timestamp.

        Returns:
            Created MQTTEvent if successful, None if failed.
        """
        if not self._enabled:
            logger.debug("MQTTConnector disabled, skipping message")
            return None

        try:
            # Parse the message
            message = self._parser.parse(
                topic=topic,
                payload=payload,
                qos=qos,
                client_id=client_id,
                retain=retain,
                timestamp=timestamp,
            )

            # Normalize to canonical Event
            event = MQTTEvent.from_mqtt_message(message)

            # Publish to Event Bus
            self._bus.publish(event.event_type, event.to_dict())

            self._message_count += 1
            logger.info(
                f"MQTT message published: topic={event.topic}, "
                f"payload_len={len(event.payload)}"
            )

            return event

        except MQTTParserError as e:
            self._error_count += 1
            logger.error(f"Failed to parse MQTT message: {e}")
            return None

        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to process MQTT message: {e}")
            return None

    def receive_batch(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[MQTTEvent]:
        """Receive and process multiple MQTT messages.

        Args:
            messages: List of message dictionaries with topic/payload.

        Returns:
            List of successfully created MQTTEvents.
        """
        events = []

        for msg in messages:
            event = self.receive_message(
                topic=msg.get("topic", ""),
                payload=msg.get("payload", ""),
                qos=msg.get("qos", 0),
                client_id=msg.get("client_id"),
                retain=msg.get("retain", False),
            )
            if event:
                events.append(event)

        logger.info(f"Batch processed: {len(events)}/{len(messages)} successful")
        return events

    def health_check(self) -> Dict[str, Any]:
        """Get connector health status.

        Returns:
            Health status dictionary.
        """
        return {
            "connector": "mqtt",
            "enabled": self._enabled,
            "messages_processed": self._message_count,
            "errors": self._error_count,
            "status": "healthy" if self._error_count == 0 else "degraded",
        }
