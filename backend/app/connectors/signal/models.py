"""
Signal data models.

Canonical models for Signal messages and internal Events.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4


@dataclass
class Attachment:
    """Signal message attachment metadata."""

    content_type: str
    filename: Optional[str] = None
    size: Optional[int] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content_type": self.content_type,
            "filename": self.filename,
            "size": self.size,
            "url": self.url,
        }


@dataclass
class SignalMessage:
    """
    Incoming Signal message model.

    Attributes:
        message_id: Unique message identifier.
        sender: Sender phone number or identifier.
        chat_id: Chat/channel identifier.
        timestamp: Message timestamp (UTC normalized).
        message_text: Message content.
        attachments: List of attachment metadata.
        raw_payload: Original payload for debugging.
    """

    message_id: str
    sender: str
    chat_id: str
    timestamp: datetime
    message_text: str
    attachments: List[Attachment] = field(default_factory=list)
    raw_payload: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalMessage":
        """Create from dictionary payload."""
        # Parse timestamp
        ts = data.get("timestamp")
        if isinstance(ts, str):
            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Parse attachments
        attachments = []
        for att in data.get("attachments", []):
            attachments.append(Attachment(
                content_type=att.get("contentType", "application/octet-stream"),
                filename=att.get("filename"),
                size=att.get("size"),
                url=att.get("url"),
            ))

        return cls(
            message_id=str(data.get("message_id", data.get("id", uuid4()))),
            sender=str(data.get("sender", data.get("source", ""))),
            chat_id=str(data.get("chat_id", data.get("conversationId", ""))),
            timestamp=timestamp,
            message_text=data.get("message_text", data.get("body", "")),
            attachments=attachments,
            raw_payload=data,
        )


@dataclass
class SignalEvent:
    """
    Normalized internal Event for the Event Bus.

    This is the canonical format that all connectors produce.
    """

    event_type: str = "signal.message"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "signal_connector"

    # Message fields
    message_id: str = ""
    sender: str = ""
    chat_id: str = ""
    message_text: str = ""
    attachments: List[Dict[str, Any]] = field(default_factory=list)

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
            "sender": self.sender,
            "chat_id": self.chat_id,
            "message_text": self.message_text,
            "attachments": self.attachments,
            "metadata": self.metadata,
        }

    @classmethod
    def from_signal_message(cls, message: SignalMessage) -> "SignalEvent":
        """Create from SignalMessage."""
        return cls(
            message_id=message.message_id,
            sender=message.sender,
            chat_id=message.chat_id,
            message_text=message.message_text,
            attachments=[att.to_dict() for att in message.attachments],
            metadata={
                "raw_payload_available": message.raw_payload is not None,
            },
        )
