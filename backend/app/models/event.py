"""
Event SQLAlchemy Model.

Canonical Event model for the Unified Event Database.
All connectors normalize to this format before persistence.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    String,
    Text,
    Boolean,
    Integer,
    Index,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class Event(BaseModel):
    """
    Canonical Event model for the Unified Event Database.

    Every connector normalizes its data to this format before persistence.
    Provides soft delete, audit trail, and full-text search indexes.

    Attributes:
        id: Unique event identifier (UUID4).
        event_type: Classification of the event (e.g., signal.message, mqtt.alert).
        source: Originating system or connector identifier.
        title: Human-readable event title.
        description: Detailed event description.
        payload: JSON payload with raw/normalized event data.
        status: Current event lifecycle status.
        priority: Event priority level.
        created_at: When the event was first recorded (UTC).
        updated_at: When the event was last modified (UTC).
        version: Optimistic locking version number.
        is_deleted: Soft delete flag.

    Usage:
        >>> event = Event(
        ...     event_type="signal.message",
        ...     source="signal_connector",
        ...     title="Incoming Signal Message",
        ... )
    """

    __tablename__ = "events"

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    """Event classification type."""

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    """Originating system or connector identifier."""

    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    """Human-readable event title."""

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    """Detailed event description."""

    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    """JSON payload with raw/normalized event data."""

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="new",
        index=True,
    )
    """Current event lifecycle status."""

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        index=True,
    )
    """Event priority level: low, medium, high, critical."""

    __table_args__ = (
        Index("ix_events_source_type", "source", "event_type"),
        Index("ix_events_status_created", "status", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "source": self.source,
            "title": self.title,
            "description": self.description,
            "payload": self.payload,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "version": self.version,
            "is_deleted": self.is_deleted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create Event from dictionary."""
        event = cls(
            event_type=data.get("event_type", "unknown"),
            source=data.get("source", "unknown"),
            title=data.get("title"),
            description=data.get("description"),
            payload=data.get("payload"),
            status=data.get("status", "new"),
            priority=data.get("priority", "medium"),
        )

        if "id" in data:
            event.id = data["id"] if isinstance(data["id"], uuid.UUID) else uuid.UUID(data["id"])

        return event
