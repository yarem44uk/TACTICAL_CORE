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
        max_attempts: int = 5,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        self._session_manager = session_manager
        # A delivery left IN_FLIGHT for longer than this lease is assumed to
        # belong to a crashed worker and is reclaimed for retry.
        self._stale_lease_seconds = stale_lease_seconds
        # WO-029 retry policy: a FAILED delivery is retried with bounded,
        # deterministic backoff and is retired to DEAD_LETTER once it exceeds
        # ``max_attempts`` (no unbounded immediate retry loop).
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds

    def set_retry_policy(
        self,
        *,
        max_attempts: Optional[int] = None,
        backoff_base_seconds: Optional[float] = None,
        stale_lease_seconds: Optional[int] = None,
    ) -> None:
        """Override the delivery retry policy.

        Lets a caller (e.g. ``DurableDeliveryDispatcher``) apply a consistent
        retry policy even when this repository was injected rather than
        constructed by the dispatcher.
        """
        if max_attempts is not None:
            self._max_attempts = max_attempts
        if backoff_base_seconds is not None:
            self._backoff_base_seconds = backoff_base_seconds
        if stale_lease_seconds is not None:
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

        WO-029 eligibility (no unbounded immediate retry):
          * PENDING — never yet delivered;
          * stale IN_FLIGHT below max_attempts — a crashed worker (lease
            expired) whose attempts have not been exhausted;
          * FAILED whose ``next_attempt_at`` has arrived (backoff schedule) and
            whose ``attempts < max_attempts``.

        F2 INVARIANT: ``attempts`` MUST NEVER exceed ``max_attempts`` and no
        consumer is invoked after ``max_attempts`` is exhausted.  A stale
        IN_FLIGHT record at ``attempts >= max_attempts`` is NOT reclaimed for
        delivery; it is retired to DEAD_LETTER (terminal) instead, without
        incrementing attempts.

        DEAD_LETTER records are terminal and are NEVER claimed.

        CONCURRENCY (WO-029): claiming is ATOMIC.  Candidates are first
        selected read-only, then each is claimed with a single conditional
        ``UPDATE ... WHERE id=:id AND state='<eligibility>'``.  Only a claim
        whose UPDATE matched exactly one row (rowcount == 1) is won by this
        caller; a row already transitioned to IN_FLIGHT by a concurrent
        dispatcher no longer matches and returns rowcount 0, so it is NOT
        double-claimed (no duplicate consumer execution).  SQLite serializes
        the writes, making this safe across independent processes.
        """
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self._stale_lease_seconds)
        with self.session_manager.session(commit=True) as session:
            # F2: retire stale IN_FLIGHT records that have exhausted
            # max_attempts directly to DEAD_LETTER (terminal) WITHOUT invoking
            # the consumer again and WITHOUT incrementing attempts.  Atomic
            # conditional UPDATE keeps concurrency safety: only a row that is
            # still IN_FLIGHT and stale and at/over max_attempts matches.
            session.execute(
                update(DurableDeliveryRecord)
                .where(
                    (DurableDeliveryRecord.state == DurableDeliveryRecord.IN_FLIGHT)
                    & (DurableDeliveryRecord.updated_at < stale_before)
                    & (DurableDeliveryRecord.attempts >= self._max_attempts)
                )
                .values(
                    state=DurableDeliveryRecord.DEAD_LETTER,
                    next_attempt_at=None,
                    updated_at=now,
                )
            )
            stmt = (
                select(DurableDeliveryRecord.id)
                .where(
                    (DurableDeliveryRecord.state == DurableDeliveryRecord.PENDING)
                    | (
                        (DurableDeliveryRecord.state == DurableDeliveryRecord.FAILED)
                        & (DurableDeliveryRecord.attempts < self._max_attempts)
                        & (
                            (DurableDeliveryRecord.next_attempt_at.is_(None))
                            | (DurableDeliveryRecord.next_attempt_at <= now)
                        )
                    )
                    | (
                        (DurableDeliveryRecord.state == DurableDeliveryRecord.IN_FLIGHT)
                        & (DurableDeliveryRecord.updated_at < stale_before)
                        & (DurableDeliveryRecord.attempts < self._max_attempts)
                    )
                )
                .order_by(DurableDeliveryRecord.created_at.asc())
                .limit(limit)
            )
            if consumer_ids:
                stmt = stmt.where(DurableDeliveryRecord.consumer_id.in_(consumer_ids))
            candidate_ids = list(session.execute(stmt).scalars().all())

            claimed: List[DurableDeliveryRecord] = []
            for rid in candidate_ids:
                # Atomic conditional claim: only wins if the row is STILL in an
                # eligible state at UPDATE time.  A concurrent claim already
                # transitioned it -> rowcount 0 -> not claimed twice.
                result = session.execute(
                    update(DurableDeliveryRecord)
                    .where(
                        (DurableDeliveryRecord.id == rid)
                        & (
                            (DurableDeliveryRecord.state == DurableDeliveryRecord.PENDING)
                            | (
                                (DurableDeliveryRecord.state == DurableDeliveryRecord.FAILED)
                                & (DurableDeliveryRecord.attempts < self._max_attempts)
                                & (
                                    (DurableDeliveryRecord.next_attempt_at.is_(None))
                                    | (DurableDeliveryRecord.next_attempt_at <= now)
                                )
                            )
                            | (
                                (DurableDeliveryRecord.state == DurableDeliveryRecord.IN_FLIGHT)
                                & (DurableDeliveryRecord.updated_at < stale_before)
                                & (DurableDeliveryRecord.attempts < self._max_attempts)
                            )
                        )
                    )
                    .values(
                        state=DurableDeliveryRecord.IN_FLIGHT,
                        attempts=DurableDeliveryRecord.attempts + 1,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    continue  # another dispatcher claimed it concurrently
                row = session.execute(
                    select(DurableDeliveryRecord).where(
                        DurableDeliveryRecord.id == rid
                    )
                ).scalar_one()
                claimed.append(row)
            return claimed

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
            row.next_attempt_at = None
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

    def _backoff_delay(self, completed_attempts: int) -> float:
        """Deterministic exponential backoff (capped) for a completed attempt.

        ``completed_attempts`` is the 1-based attempt number that just failed.
        Delay grows exponentially from the base and is capped at 60s so the
        schedule stays bounded and deterministic.
        """
        exponent = max(0, completed_attempts - 1)
        delay = self._backoff_base_seconds * (2 ** exponent)
        return min(delay, 60.0)

    def mark_failed(self, event_id: str, consumer_id: str, error: str) -> None:
        """Record a failed delivery attempt.

        WO-029 retry policy: if the delivery has exhausted ``max_attempts`` it
        is retired to DEAD_LETTER (terminal, never auto-claimed).  Otherwise it
        is left FAILED with a deterministic ``next_attempt_at`` backoff so a
        subsequent ``claim_pending`` will not retry it until the schedule
        arrives (no unbounded immediate retry loop).
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
            row.last_error = (error or "")[:500]
            row.updated_at = datetime.now(timezone.utc)
            if row.attempts >= self._max_attempts:
                row.state = DurableDeliveryRecord.DEAD_LETTER
                row.next_attempt_at = None
            else:
                row.state = DurableDeliveryRecord.FAILED
                row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=self._backoff_delay(row.attempts)
                )

    def mark_dead_letter(self, event_id: str, consumer_id: str, error: str) -> None:
        """Force a delivery to DEAD_LETTER (terminal) regardless of attempts."""
        with self.session_manager.session(commit=True) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.state = DurableDeliveryRecord.DEAD_LETTER
            row.last_error = (error or "")[:500]
            row.next_attempt_at = None
            row.updated_at = datetime.now(timezone.utc)

    def requeue_dead_letter(
        self, event_id: str, consumer_id: str
    ) -> bool:
        """Explicit administrative requeue of a DEAD_LETTER delivery.

        Returns the delivery to PENDING with a fresh attempt schedule so it can
        be redelivered.  Returns False if the record does not exist or is not
        in DEAD_LETTER state.
        """
        with self.session_manager.session(commit=True) as session:
            row = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == consumer_id,
                )
            ).scalar_one_or_none()
            if row is None or row.state != DurableDeliveryRecord.DEAD_LETTER:
                return False
            row.state = DurableDeliveryRecord.PENDING
            row.attempts = 0
            row.next_attempt_at = None
            row.last_error = None
            row.updated_at = datetime.now(timezone.utc)
            return True

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
