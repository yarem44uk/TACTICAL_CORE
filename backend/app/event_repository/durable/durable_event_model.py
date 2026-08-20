"""
Durable Canonical Event SQLAlchemy Model (WO-014-016).

``DurableCanonicalEvent`` is the dedicated persistence model used by the durable
event repository. It is intentionally distinct from the legacy
``app.models.event.Event`` model.

The canonical domain identity (``event_id``) is the authoritative durable
identity and is enforced with a database-level UNIQUE constraint. An internal
surrogate ORM primary key (``id``) exists purely for SQLAlchemy mechanics and is
kept separate from the canonical ``event_id``.

Architecture rules honoured here:
- canonical ``event_id`` remains the authoritative durable identity;
- canonical ``event_id`` is NOT mapped onto an auto-generated ORM primary key;
- this model does not reuse ``app.models.event.Event``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DurableCanonicalEvent(Base):
    """
    SQLAlchemy persistence model for the canonical domain Event.

    Attributes:
        id: Internal surrogate ORM primary key (SQLAlchemy mechanics only).
        event_id: Authoritative canonical event identity (DB-level UNIQUE).
        entity_id: Optional entity the event belongs to.
        event_type: Canonical event type, stored as its enum string value.
        timestamp: Event timestamp (UTC).
        source: Originating source.
        payload: Arbitrary JSON-serialisable payload (may be nested).
        metadata: Arbitrary JSON-serialisable metadata (may be nested).
        created_at: When the durable record was created (UTC).
    """

    __tablename__ = "durable_canonical_events"

    # Internal surrogate ORM primary key. Separate from canonical event_id.
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # WO-014-025 — durable deterministic monotonic sequence (replay ordering).
    # A DB-derived, monotonically increasing integer assigned at insert time
    # from the durable log state (MAX(seq)+1 within the same transaction).
    # Used for deterministic replay ordering (ORDER BY seq ASC). Gaps are
    # acceptable. A duplicate canonical event_id insertion is rejected by the
    # UNIQUE(event_id) constraint and rolls back WITHOUT consuming a sequence,
    # so a duplicate retains its original seq. NOT the ORM identity key.
    seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
    )

    # Authoritative canonical durable identity.
    event_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    entity_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Stored under DB column "metadata"; attribute renamed to event_metadata
    # because "metadata" is reserved by the SQLAlchemy Declarative API.
    event_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_durable_canonical_events_event_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<DurableCanonicalEvent event_id={self.event_id!r} "
            f"event_type={self.event_type!r}>"
        )
