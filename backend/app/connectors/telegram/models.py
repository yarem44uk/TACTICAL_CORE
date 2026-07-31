"""Telegram data models.

Telegram-specific models for messages and internal events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4


@dataclass
class TelegramMedia:
    """Telegram message media/attachment metadata.

    Attributes:
        file_id: Telegram file identifier.
        file_unique_id: Unique file identifier.
        mime_type: MIME type of the file.
        file_size: Size of the file in bytes.
        file_name: Original file name if present.
        media_type: Type of media (photo, video, document, audio, voice, sticker).
    """

    file_id: str
    file_unique_id: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    file_name: Optional[str] = None
    media_type: str = "document"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_id": self.file_id,
            "file_unique_id": self.file_unique_id,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_name": self.file_name,
            "media_type": self.media_type,
        }


@dataclass
class TelegramMessage:
    """Incoming Telegram message model.

    Attributes:
        message_id: Telegram message ID.
        chat_id: Chat/channel identifier.
        sender_id: Sender user ID.
        sender_username: Sender username (if available).
        sender_first_name: Sender first name.
        message_text: Message content.
        timestamp: Message timestamp (UTC normalized).
        reply_to_message_id: ID of message being replied to.
        media: List of media attachments.
        raw_payload: Original payload for debugging.
    """

    message_id: int
    chat_id: int
    sender_id: int
    sender_username: Optional[str] = None
    sender_first_name: Optional[str] = None
    message_text: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to_message_id: Optional[int] = None
    media: List[TelegramMedia] = field(default_factory=list)
    raw_payload: Optional[Dict[str, Any]] = None

    @property
    def sender_display_name(self) -> str:
        """Get the best available sender display name."""
        if self.sender_username:
            return f"@{self.sender_username}"
        if self.sender_first_name:
            return self.sender_first_name
        return str(self.sender_id)

    @property
    def has_media(self) -> bool:
        """Check if message has media attachments."""
        return len(self.media) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "sender_id": self.sender_id,
            "sender_username": self.sender_username,
            "sender_first_name": self.sender_first_name,
            "sender_display_name": self.sender_display_name,
            "message_text": self.message_text,
            "timestamp": self.timestamp.isoformat(),
            "reply_to_message_id": self.reply_to_message_id,
            "media": [m.to_dict() for m in self.media],
            "has_media": self.has_media,
        }


@dataclass
class TelegramEvent:
    """Canonical event for the Event Bus.

    Normalized Telegram event format that all connectors produce.
    """

    event_type: str = "telegram.message"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "telegram_connector"

    # Message fields
    message_id: str = ""
    chat_id: str = ""
    sender_id: str = ""
    sender_username: Optional[str] = None
    sender_display_name: str = ""
    message_text: str = ""
    has_media: bool = False
    media: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Event Bus dictionary format."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "sender_id": self.sender_id,
            "sender_username": self.sender_username,
            "sender_display_name": self.sender_display_name,
            "text": self.message_text,
            "has_media": self.has_media,
            "media": self.media,
            "metadata": self.metadata,
        }

    @classmethod
    def from_telegram_message(cls, message: TelegramMessage) -> "TelegramEvent":
        """Create from TelegramMessage."""
        return cls(
            message_id=str(message.message_id),
            chat_id=str(message.chat_id),
            sender_id=str(message.sender_id),
            sender_username=message.sender_username,
            sender_display_name=message.sender_display_name,
            message_text=message.message_text,
            has_media=message.has_media,
            media=[media.to_dict() for media in message.media],
            metadata={
                "reply_to_message_id": message.reply_to_message_id,
                "raw_payload_available": message.raw_payload is not None,
            },
        )
