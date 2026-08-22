"""WO-027 — Durable outbox delivery-record model.

One durable row per (canonical ``event_id``, ``consumer_id``) pair.  The row is
written in the SAME transaction as the canonical event commit, so there is no
valid production state where an event is committed but a contractually-required
consumer has no durable delivery record (transactional outbox).

The record carries delivery state for recovery: PENDING / IN_FLIGHT /
DELIVERED / FAILED, an attempt counter, timestamps and an optional last-error
string.  ``UNIQUE(event_id, consumer_id)`` is the canonical idempotency
boundary — exactly one delivery record can exist per event/consumer pair, so a
duplicate enqueue is a safe no-op and no duplicate delivery state can be
accidentally created.

Ownership: single ``DatabaseSessionManager`` (no second engine/sessionmaker/
database owner).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DurableDeliveryRecord(Base):
    """One durable, per-consumer delivery record for a canonical event."""

    __tablename__ = "durable_event_delivery"

    # -- delivery state (canonical lifecycle) --------------------------------
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"

    # -- columns --------------------------------------------------------------
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    consumer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Next time a FAILED delivery becomes eligible for retry (backoff schedule).
    # NULL for PENDING / IN_FLIGHT / DELIVERED / DEAD_LETTER.
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Canonical idempotency boundary: exactly one delivery record per
        # event/consumer pair (transactional-outbox uniqueness).
        UniqueConstraint("event_id", "consumer_id", name="uq_durable_event_delivery_event_consumer"),
        Index("ix_durable_event_delivery_state", "state"),
        Index("ix_durable_event_delivery_event", "event_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<DurableDeliveryRecord(event_id={self.event_id!r}, "
            f"consumer_id={self.consumer_id!r}, state={self.state!r}, "
            f"attempts={self.attempts})>"
        )
