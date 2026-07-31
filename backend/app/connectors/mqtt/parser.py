"""MQTT message parser.

Parses incoming MQTT payloads into MQTTMessage objects.
Handles various payload formats and validates data.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.connectors.mqtt.models import MQTTMessage


logger = logging.getLogger(__name__)


class MQTTParserError(Exception):
    """Raised when MQTT message parsing fails."""

    pass


class MQTTParser:
    """Parses MQTT message payloads into MQTTMessage objects.

    MQTT payload contract requires:
    - topic: The MQTT topic
    - payload: The message payload
    """

    def __init__(self):
        """Initialize the parser."""
        pass

    def parse(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        client_id: Optional[str] = None,
        retain: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> MQTTMessage:
        """Parse MQTT message components into an MQTTMessage.

        Args:
            topic: The MQTT topic the message was published to.
            payload: The message payload (str, bytes, or dict).
            qos: Quality of Service level (0, 1, or 2).
            client_id: Client that published the message.
            retain: Whether message was retained.
            timestamp: Optional message timestamp.

        Returns:
            MQTTMessage object.

        Raises:
            MQTTParserError: If parsing fails.
        """
        # Validate required fields
        if not topic:
            raise MQTTParserError("Empty topic")

        if payload is None:
            raise MQTTParserError("Empty payload")

        # Parse timestamp
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
        elif isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, str):
            ts = timestamp.replace("Z", "+00:00")
            try:
                timestamp = datetime.fromisoformat(ts)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    timestamp = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    timestamp = datetime.now(timezone.utc)

        # Parse payload
        parsed_payload = self._parse_payload(payload)

        # Create message
        message = MQTTMessage(
            topic=topic,
            payload=parsed_payload,
            qos=qos,
            timestamp=timestamp,
            client_id=client_id,
            retain=retain,
            raw_payload={"original": payload},
        )

        logger.debug(
            f"Parsed MQTT message: topic={message.topic}, "
            f"payload_len={len(message.payload)}"
        )

        return message

    def _parse_payload(self, payload: Any) -> str:
        """Parse payload to string.

        Args:
            payload: Raw payload.

        Returns:
            Payload as string.
        """
        if isinstance(payload, str):
            return payload

        if isinstance(payload, bytes):
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError:
                return payload.decode("utf-8", errors="replace")

        if isinstance(payload, dict):
            import json
            try:
                return json.dumps(payload)
            except (TypeError, ValueError):
                return str(payload)

        return str(payload)

    def parse_dict(self, message_dict: Dict[str, Any]) -> MQTTMessage:
        """Parse MQTT message from dictionary.

        Args:
            message_dict: Dictionary containing MQTT message data.

        Returns:
            MQTTMessage object.

        Raises:
            MQTTParserError: If required fields are missing.
        """
        # Validate required fields
        if "topic" not in message_dict:
            raise MQTTParserError("Missing required field: topic")
        if "payload" not in message_dict:
            raise MQTTParserError("Missing required field: payload")

        return self.parse(
            topic=message_dict["topic"],
            payload=message_dict["payload"],
            qos=message_dict.get("qos", 0),
            client_id=message_dict.get("client_id"),
            retain=message_dict.get("retain", False),
            timestamp=message_dict.get("timestamp"),
        )
