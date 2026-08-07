from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.event.event_metadata import EventMetadata
from app.event.event_status import EventStatus
from app.event.event_types import EventType


@dataclass(frozen=True)
class Event:
    """
    Immutable event representation.
    
    An event is a fact. It is created once and never modified.
    No UPDATE. No DELETE. Append Only.
    Thread-safe by design (frozen dataclass).
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    entity_id: Optional[str] = None
    event_type: EventType = EventType.CUSTOM
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: EventMetadata = field(default_factory=EventMetadata)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        hash=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise TypeError(
                f"payload must be a dict, got {type(self.payload).__name__}"
            )
        if not isinstance(self.event_type, EventType):
            raise TypeError(
                f"event_type must be EventType, got {type(self.event_type).__name__}"
            )
        if not isinstance(self.source, str):
            raise TypeError(
                f"source must be a str, got {type(self.source).__name__}"
            )

    @property
    def event_status(self) -> EventStatus:
        return EventStatus.REGISTERED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "event_type": str(self.event_type),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "payload": dict(self.payload),
            "metadata": self.metadata.to_dict(),
            "created_at": self.created_at.isoformat(),
            "event_status": str(self.event_status),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        event_type_str = data["event_type"]
        event_type = (
            EventType(event_type_str)
            if event_type_str in [e.value for e in EventType]
            else EventType.CUSTOM
        )
        metadata_data = data.get("metadata", {})
        event_metadata = EventMetadata.from_dict(metadata_data)
        return cls(
            event_id=data["event_id"],
            entity_id=data.get("entity_id"),
            event_type=event_type,
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data["source"],
            payload=data.get("payload", {}),
            metadata=event_metadata,
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def equals(self, other: "Event") -> bool:
        """Compare events by event_id (identity comparison)."""
        if not isinstance(other, Event):
            return False
        return self.event_id == other.event_id

    def get_lock(self) -> threading.RLock:
        """Expose lock for atomic read operations."""
        return self._lock
