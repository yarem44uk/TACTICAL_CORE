"""WO-027 — Durable outbox repository (single database owner).

``SQLAlchemyOutboxRepository`` manages the durable delivery records behind the
canonical transactional outbox.  It operates exclusively through the existing
``DatabaseSessionManager`` — no second engine, sessionmaker, or database owner.

The repository provides the operations the post-commit delivery dispatcher
needs:

  * ``enqueue`` — create a PENDING delivery record for an event/consumer pair
    (idempotent via ``UNIQUE(event_id, consumer_id)``);
  * ``claim_pending`` — select PENDING records (plus stale IN_FLIGHT records
    whose lease has expired after a process crash) and mark them IN_FLIGHT so
    no two workers deliver the same record concurrently;
  * ``mark_delivered`` / ``mark_failed`` — record the terminal/retryable
    outcome of a delivery attempt.

Delivery state is durable: a crash mid-delivery leaves the record IN_FLIGHT,
which the recovery pass later makes eligible again (AT-LEAST-ONCE).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.database.session import DatabaseSessionManager, get_session_manager
from app.event_delivery.outbox_model import DurableDeliveryRecord


class SQLAlchemyOutboxRepository:
    """Durable delivery-record repository over the single DB owner."""

    def __init__(
        self,
        session_manager: Optional[DatabaseSessionManager] = None,
        *,
        stale_lease_seconds: int = 60,
    ) -> None:
        self._session_manager = session_manager
        # A delivery left IN_FLIGHT for longer than this lease is assumed to
        # belong to a crashed worker and is reclaimed for retry.
        self._stale_lease_seconds = stale_lease_seconds

    # -- ownership -----------------------------------------------------------

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """Ensure the outbox table exists on the shared metadata/engine."""
        from app.database.base import Base

        Base.metadata.create_all(bind=self.session_manager.engine)

    # -- lifecycle -----------------------------------------------------------

    def enqueue(self, event_id: str, consumer_id: str) -> bool:
        """Create a PENDING delivery record for ``(event_id, consumer_id)``.

        Idempotent: if a record already exists for the pair (UNIQUE constraint),
        this is a benign no-op returning False.  Returns True if a new record
        was created.
        """
        with self.session_manager.session(commit=True) as session:
            existing = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False
            session.add(
                DurableDeliveryRecord(
                    id=uuid.uuid4().hex,
                    event_id=event_id,
                    consumer_id=consumer_id,
                    state=DurableDeliveryRecord.PENDING,
                    attempts=0,
                )
            )
            return True

    def enqueue_many(self, event_id: str, consumer_ids: List[str]) -> int:
        """Enqueue delivery records for one event to several consumers.

        Returns the number of NEW records created (existing pairs are no-ops).
        """
        created = 0
        for consumer_id in consumer_ids:
            if self.enqueue(event_id, consumer_id):
                created += 1
        return created

    def claim_pending(
        self,
        limit: int = 100,
        *,
        consumer_ids: Optional[List[str]] = None,
    ) -> List[DurableDeliveryRecord]:
        """Claim up to ``limit`` eligible delivery records.

        Eligible = PENDING, FAILED (retryable), or IN_FLIGHT whose lease has
        expired (a crashed worker).  Claimed records are transitioned to
        IN_FLIGHT (with an incremented attempt counter) so a concurrent
        dispatcher will not pick them up.  Recovery of stale IN_FLIGHT is what
        makes AT-LEAST-ONCE delivery lossless after a process crash, and the
        inclusion of FAILED is what keeps a failed consumer retryable
        (delivery guarantee: a failed consumer must not be permanently lost).
        """
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self._stale_lease_seconds)
        with self.session_manager.session(commit=True) as session:
            stmt = (
                select(DurableDeliveryRecord)
                .where(
                    (DurableDeliveryRecord.state == DurableDeliveryRecord.PENDING)
                    | (DurableDeliveryRecord.state == DurableDeliveryRecord.FAILED)
                    | (
                        (DurableDeliveryRecord.state == DurableDeliveryRecord.IN_FLIGHT)
                        & (DurableDeliveryRecord.updated_at < stale_before)
                    )
                )
                .order_by(DurableDeliveryRecord.created_at.asc())
                .limit(limit)
            )
            if consumer_ids:
                stmt = stmt.where(DurableDeliveryRecord.consumer_id.in_(consumer_ids))
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                row.state = DurableDeliveryRecord.IN_FLIGHT
                row.attempts += 1
                row.updated_at = now
            return rows

    def mark_delivered(self, event_id: str, consumer_id: str) -> None:
        """Mark an event/consumer delivery as successfully delivered."""
        with self.session_manager.session(commit=True) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.state = DurableDeliveryRecord.DELIVERED
            row.last_error = None
            row.updated_at = datetime.now(timezone.utc)

    def mark_pending(self, event_id: str, consumer_id: str) -> None:
        """Return an unclaimed delivery record to PENDING (not lost).

        Used when a delivery was claimed but its consumer is not (yet)
        registered — the record is put back so it remains discoverable rather
        than being stranded or permanently failed.
        """
        with self.session_manager.session(commit=True) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.state = DurableDeliveryRecord.PENDING
            row.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, event_id: str, consumer_id: str, error: str) -> None:
        """Record a failed delivery attempt (leaves the record retryable)."""
        with self.session_manager.session(commit=True) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.state = DurableDeliveryRecord.FAILED
            row.last_error = (error or "")[:500]
            row.updated_at = datetime.now(timezone.utc)

    # -- inspection ----------------------------------------------------------

    def get_state(self, event_id: str, consumer_id: str) -> Optional[str]:
        """Return the delivery state for an event/consumer pair, or None."""
        with self.session_manager.session(commit=False) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
        return row.state if row is not None else None

    def count(self) -> int:
        """Return the total number of durable delivery records."""
        with self.session_manager.session(commit=False) as session:
            return int(
                session.execute(
                    select(DurableDeliveryRecord.id)
                ).scalars().all().__len__()
            )

    def count_by_state(self, state: str) -> int:
        """Return the number of durable delivery records in ``state``."""
        with self.session_manager.session(commit=False) as session:
            return int(
                session.execute(
                    select(DurableDeliveryRecord.id).where(
                        DurableDeliveryRecord.state == state
                    )
                ).scalars().all().__len__()
            )
