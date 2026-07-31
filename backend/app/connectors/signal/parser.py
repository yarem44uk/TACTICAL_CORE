"""
Signal message parser.

Parses incoming Signal payloads into SignalMessage objects.
Handles various payload formats and validates data.
"""

import logging
from typing import Optional, Dict, Any, List

from app.connectors.signal.models import SignalMessage, Attachment


logger = logging.getLogger(__name__)


class SignalParserError(Exception):
    """Raised when Signal message parsing fails."""
    pass


class SignalParser:
    """
    Parses Signal message payloads into SignalMessage objects.

    Supports multiple payload formats from Signal-cli and similar sources.
    """

    def __init__(self):
        """Initialize the parser."""
        self._required_fields = ["message_id", "sender", "chat_id", "timestamp"]

    def parse(self, payload: Dict[str, Any]) -> SignalMessage:
        """
        Parse a Signal payload into a SignalMessage.

        Args:
            payload: Raw Signal message payload.

        Returns:
            Parsed SignalMessage object.

        Raises:
            SignalParserError: If parsing fails.
        """
        if not payload:
            raise SignalParserError("Empty payload")

        # Validate required fields
        self._validate_payload(payload)

        # Parse attachments
        attachments = self._parse_attachments(payload.get("attachments", []))

        # Create message
        message = SignalMessage(
            message_id=str(payload["message_id"]),
            sender=str(payload["sender"]),
            chat_id=str(payload["chat_id"]),
            timestamp=self._parse_timestamp(payload["timestamp"]),
            message_text=str(payload.get("message_text", payload.get("body", ""))),
            attachments=attachments,
            raw_payload=payload,
        )

        logger.debug(
            f"Parsed Signal message: id={message.message_id}, "
            f"sender={message.sender}"
        )

        return message

    def _validate_payload(self, payload: Dict[str, Any]) -> None:
        """
        Validate that payload contains required fields.

        Args:
            payload: Payload to validate.

        Raises:
            SignalParserError: If validation fails.
        """
        missing = []
        for field in self._required_fields:
            if field not in payload:
                missing.append(field)

        if missing:
            raise SignalParserError(f"Missing required fields: {missing}")

    def _parse_timestamp(self, timestamp: Any) -> Any:
        """
        Parse timestamp to UTC datetime.

        Args:
            timestamp: Timestamp in various formats.

        Returns:
            Parsed timestamp.
        """
        from datetime import datetime, timezone

        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                return timestamp.replace(tzinfo=timezone.utc)
            return timestamp

        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)

        if isinstance(timestamp, str):
            # Handle ISO format
            ts = timestamp.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                # Try parsing as Unix timestamp
                try:
                    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    pass

        # Default to current time
        return datetime.now(timezone.utc)

    def _parse_attachments(self, attachments: List[Any]) -> List[Attachment]:
        """
        Parse attachment list.

        Args:
            attachments: Raw attachment data.

        Returns:
            List of Attachment objects.
        """
        result = []
        for att in attachments:
            if not isinstance(att, dict):
                continue

            result.append(Attachment(
                content_type=att.get("contentType", att.get("content_type", "application/octet-stream")),
                filename=att.get("filename"),
                size=att.get("size"),
                url=att.get("url"),
            ))

        return result

    def parse_batch(self, payloads: List[Dict[str, Any]]) -> List[SignalMessage]:
        """
        Parse multiple payloads.

        Args:
            payloads: List of raw Signal payloads.

        Returns:
            List of parsed SignalMessage objects.
        """
        messages = []
        errors = []

        for i, payload in enumerate(payloads):
            try:
                messages.append(self.parse(payload))
            except SignalParserError as e:
                errors.append(f"Payload {i}: {e}")
                logger.warning(f"Failed to parse payload {i}: {e}")

        if errors:
            logger.warning(f"Batch parse errors: {errors}")

        return messages
