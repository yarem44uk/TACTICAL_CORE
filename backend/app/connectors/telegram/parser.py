"""Telegram message parser.

Parses incoming Telegram payloads into TelegramMessage objects.
Handles various payload formats and validates data.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.connectors.telegram.models import TelegramMessage, TelegramMedia


logger = logging.getLogger(__name__)


class TelegramParserError(Exception):
    """Raised when Telegram message parsing fails."""

    pass


class TelegramParser:
    """Parses Telegram message payloads into TelegramMessage objects.

    Supports the standard Telegram Bot API message format.
    """

    # Required fields for a valid message
    _required_fields = ["message_id", "chat", "from"]

    # Media types in Telegram
    _media_fields = [
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "sticker",
    ]

    def __init__(self):
        """Initialize the parser."""
        pass

    def parse(self, payload: Dict[str, Any]) -> TelegramMessage:
        """Parse a Telegram payload into a TelegramMessage.

        Args:
            payload: Raw Telegram message payload.

        Returns:
            Parsed TelegramMessage object.

        Raises:
            TelegramParserError: If parsing fails.
        """
        if not payload:
            raise TelegramParserError("Empty payload")

        # Validate required fields
        self._validate_payload(payload)

        # Parse sender
        sender = payload.get("from", {})
        sender_id = sender.get("id")
        sender_username = sender.get("username")
        sender_first_name = sender.get("first_name")

        if not sender_id:
            raise TelegramParserError("Missing required field: from.id")

        # Parse chat
        chat = payload.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            raise TelegramParserError("Missing required field: chat.id")

        # Parse message text
        message_text = payload.get("text") or payload.get("caption") or ""

        # Parse timestamp
        timestamp = self._parse_timestamp(payload.get("date"))

        # Parse reply
        reply_to_message_id = None
        if "reply_to_message" in payload:
            reply_to_message_id = payload["reply_to_message"].get("message_id")

        # Parse media/attachments
        media = self._parse_media(payload)

        # Create message
        message = TelegramMessage(
            message_id=payload["message_id"],
            chat_id=chat_id,
            sender_id=sender_id,
            sender_username=sender_username,
            sender_first_name=sender_first_name,
            message_text=message_text,
            timestamp=timestamp,
            reply_to_message_id=reply_to_message_id,
            media=media,
            raw_payload=payload,
        )

        logger.debug(
            f"Parsed Telegram message: id={message.message_id}, "
            f"sender={message.sender_display_name}"
        )

        return message

    def _validate_payload(self, payload: Dict[str, Any]) -> None:
        """Validate that payload contains required fields.

        Args:
            payload: Payload to validate.

        Raises:
            TelegramParserError: If validation fails.
        """
        missing = []
        for field in self._required_fields:
            if field not in payload:
                missing.append(field)

        if missing:
            raise TelegramParserError(f"Missing required fields: {missing}")

    def _parse_timestamp(self, timestamp: Any) -> datetime:
        """Parse timestamp to UTC datetime.

        Args:
            timestamp: Timestamp in various formats.

        Returns:
            Parsed timestamp in UTC.
        """
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                # Naive datetime - assume UTC
                return timestamp.replace(tzinfo=timezone.utc)
            else:
                # Timezone-aware - convert to UTC
                return timestamp.astimezone(timezone.utc)

        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)

        if isinstance(timestamp, str):
            # Handle ISO format or Unix timestamp
            ts = timestamp.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                try:
                    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    pass

        # Default to current time
        return datetime.now(timezone.utc)

    def _parse_media(self, payload: Dict[str, Any]) -> List[TelegramMedia]:
        """Parse media/attachments from payload.

        Args:
            payload: Raw Telegram payload.

        Returns:
            List of TelegramMedia objects.
            For arrays (like photo), selects ONE representative entry.
        """
        result = []

        for media_field in self._media_fields:
            if media_field in payload:
                media_data = payload[media_field]

                # Handle arrays - select ONE representative
                if isinstance(media_data, list):
                    # For photo, select largest by file_size
                    if media_field == "photo" and media_data:
                        representative = self._select_representative_photosize(media_data)
                        if representative:
                            media = self._parse_single_media(representative, media_field)
                            if media:
                                result.append(media)
                    else:
                        # For other arrays, take first valid item
                        for item in media_data:
                            if isinstance(item, dict):
                                media = self._parse_single_media(item, media_field)
                                if media:
                                    result.append(media)
                                    break  # Only one
                elif isinstance(media_data, dict):
                    media = self._parse_single_media(media_data, media_field)
                    if media:
                        result.append(media)

        return result

    def _parse_single_media(
        self, media_data: Dict[str, Any], media_type: str
    ) -> Optional[TelegramMedia]:
        """Parse a single media item.

        Args:
            media_data: Media data dictionary.
            media_type: Type of media (photo, video, etc.).

        Returns:
            TelegramMedia object or None.
        """
        file_id = media_data.get("file_id")
        file_unique_id = media_data.get("file_unique_id")

        if not file_id or not file_unique_id:
            return None

        # Get file name from different possible fields
        file_name = (
            media_data.get("file_name")
            or media_data.get("filename")
            or media_data.get("title")
        )

        return TelegramMedia(
            file_id=file_id,
            file_unique_id=file_unique_id,
            mime_type=media_data.get("mime_type"),
            file_size=media_data.get("file_size"),
            file_name=file_name,
            media_type=media_type,
        )
    def _select_representative_photosize(
        self, photosizes: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Select one representative PhotoSize from an array.

        Prefers largest file_size. Falls back to last in array (Telegram 
        API orders largest first).

        Args:
            photosizes: List of PhotoSize objects.

        Returns:
            Best representative PhotoSize dict, or None.
        """
        if not photosizes:
            return None

        # Filter out entries without file_id
        valid = [ps for ps in photosizes if ps.get("file_id") and ps.get("file_unique_id")]
        if not valid:
            return None

        # Find one with largest file_size
        with_size = [ps for ps in valid if ps.get("file_size")]
        if with_size:
            return max(with_size, key=lambda ps: ps.get("file_size", 0))

        # Fallback: last in array (Telegram orders largest first)
        return valid[-1]


    def parse_batch(self, payloads: List[Dict[str, Any]]) -> List[TelegramMessage]:
        """Parse multiple payloads.

        Args:
            payloads: List of raw Telegram payloads.

        Returns:
            List of parsed TelegramMessage objects.
        """
        messages = []
        errors = []

        for i, payload in enumerate(payloads):
            try:
                messages.append(self.parse(payload))
            except TelegramParserError as e:
                errors.append(f"Payload {i}: {e}")
                logger.warning(f"Failed to parse payload {i}: {e}")

        if errors:
            logger.warning(f"Batch parse errors: {errors}")

        return messages
