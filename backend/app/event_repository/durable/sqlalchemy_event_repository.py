"""
SQLAlchemy-backed durable implementation of ``IEventRepository`` (WO-014-016).

``SQLAlchemyEventRepository`` persists the canonical domain Event
(``app.event.event.Event``) behind the authoritative repository seam
(``app.event_repository.interfaces.i_event_repository.IEventRepository``).

Design decisions (WO-014-016):
- canonical ``event_id`` is the authoritative durable identity, enforced by a
  DB-level UNIQUE constraint;
- an internal surrogate ORM primary key on ``DurableCanonicalEvent`` is kept
  separate from ``event_id``;
- explicit deterministic mapping methods ``_to_persistent`` / ``_from_persistent``;
- reuses the existing approved database session infrastructure
  (``app.database.session.DatabaseSessionManager``) — no second engine or
  session architecture is introduced;
- SQLAlchemy remains confined to this package plus the existing DB infrastructure;
- transaction lifecycle: commit on success, rollback + re-raise on failure,
  session always closed (no leaks).

``save`` is idempotent and conflict-safe: saving the same canonical ``event_id``
twice results in exactly one durable record (no duplicate, no overwrite, no new
identity). Distinct ``event_id`` values produce distinct records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.session import DatabaseSessionManager, get_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.interfaces.i_event_repository import IEventRepository


class SQLAlchemyEventRepository(IEventRepository):
    """
    Durable SQLAlchemy implementation of the authoritative IEventRepository.

    Args:
        session_manager: Optional session manager. Defaults to the global
            session manager (``get_session_manager``).
    """

    def __init__(self, session_manager: Optional[DatabaseSessionManager] = None) -> None:
        self._session_manager = session_manager

    # -- session/ownership ---------------------------------------------------

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """
        Ensure the durable table exists using the existing engine/metadata.

        Uses ``Base.metadata.create_all`` bound to the existing engine so no
        second database owner, engine, or configuration is introduced.
        """
        from app.database.base import Base

        Base.metadata.create_all(bind=self.session_manager.engine)

    # -- explicit mapping ----------------------------------------------------

    def _to_persistent(self, event: Event) -> DurableCanonicalEvent:
        """Map a canonical domain Event to a DurableCanonicalEvent."""
        return DurableCanonicalEvent(
            event_id=event.event_id,
            entity_id=event.entity_id,
            event_type=str(event.event_type),
            timestamp=event.timestamp,
            source=event.source,
            payload=dict(event.payload),
            event_metadata=event.metadata.to_dict(),
            created_at=event.created_at,
        )

    def _from_persistent(self, row: DurableCanonicalEvent) -> Event:
        """Map a DurableCanonicalEvent back to a canonical domain Event."""
        metadata_data: Dict[str, Any] = dict(row.event_metadata or {})
        payload: Dict[str, Any] = dict(row.payload or {})
        return Event(
            event_id=row.event_id,
            entity_id=row.entity_id,
            event_type=self._resolve_event_type(row.event_type),
            timestamp=row.timestamp,
            source=row.source,
            payload=payload,
            metadata=EventMetadata.from_dict(metadata_data),
            created_at=row.created_at,
        )

    def _next_seq(self, session: Any) -> int:
        """Return the next durable monotonic sequence value.

        Derived from the durable log state (``MAX(seq)+1``) within the same
        transaction/session, so it is monotonic, survives restart, and is
        rolled back together with any failed duplicate insertion (preserving
        the original sequence of an already-persisted canonical event_id).
        """
        stmt = select(func.max(DurableCanonicalEvent.seq))
        current_max = session.execute(stmt).scalar_one_or_none()
        return int(current_max) + 1 if current_max is not None else 1

    @staticmethod
    def _resolve_event_type(raw: str) -> EventType:
        """Resolve a stored event-type string back to the canonical enum."""
        try:
            return EventType(raw)
        except ValueError:
            return EventType.CUSTOM

    # -- IEventRepository implementation -------------------------------------

    def save(self, event: Event) -> None:
        """Persist one canonical Event. Idempotent and conflict-safe."""
        row = self._to_persistent(event)
        with self.session_manager.session(commit=True) as session:
            row.seq = self._next_seq(session)
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                # Duplicate canonical event_id: idempotent no-op. Rollback the
                # failed flush so the session is clean, and return without error.
                session.rollback()
                return

    def save_with_deliveries(self, event: Event, consumer_ids: List[str]) -> None:
        """WO-027 — Persist a canonical Event and its outbox delivery records
        ATOMICALLY in one transaction (transactional outbox).

        The canonical event row AND a PENDING delivery record for every
        ``consumer_id`` are written and committed together, so there is no
        valid production state where the event is durable but a contractually
        required consumer has no durable delivery record.  Delivery itself is
        performed later by the post-commit ``DurableDeliveryDispatcher``; no
        consumer side effect runs here.

        Idempotent and conflict-safe:
          * re-saving an existing ``event_id`` is a no-op (event already
            durable; any already-created delivery records are preserved by the
            ``UNIQUE(event_id, consumer_id)`` outbox constraint);
          * if any enqueued consumer already has a delivery record for this
            event, that record is preserved (no duplicate delivery state).

        Args:
            event: canonical ``app.event.event.Event`` to persist.
            consumer_ids: consumers that contractually receive this event.
        """
        from app.event_delivery.outbox_model import DurableDeliveryRecord
        import uuid as _uuid
        from datetime import datetime as _datetime, timezone as _timezone

        row = self._to_persistent(event)
        with self.session_manager.session(commit=True) as session:
            row.seq = self._next_seq(session)
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                # Duplicate canonical event_id: the event is already durable.
                # Preserve the already-created outbox records and treat this as
                # an idempotent no-op (roll back the failed flush).
                session.rollback()
                # Reopen a session to reconcile outbox records (below).
                with self.session_manager.session(commit=True) as s2:
                    self._reconcile_deliveries(s2, event.event_id, consumer_ids)
                return
            # Fresh event: create PENDING delivery records in the same
            # transaction.  UNIQUE(event_id, consumer_id) makes accidental
            # duplicates impossible even if a record already exists.
            now = _datetime.now(_timezone.utc)
            for cid in consumer_ids:
                existing = session.execute(
                    select(DurableDeliveryRecord).where(
                        DurableDeliveryRecord.event_id == event.event_id,
                        DurableDeliveryRecord.consumer_id == cid,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        DurableDeliveryRecord(
                            id=_uuid.uuid4().hex,
                            event_id=event.event_id,
                            consumer_id=cid,
                            state=DurableDeliveryRecord.PENDING,
                            attempts=0,
                            created_at=now,
                            updated_at=now,
                        )
                    )

    @staticmethod
    def _reconcile_deliveries(session: Any, event_id: str, consumer_ids: List[str]) -> None:
        """Ensure PENDING delivery records exist for every consumer.

        Called on the idempotent re-save path (event already durable) so a
        consumer added after the original commit still gets a delivery record,
        while never duplicating existing records (UNIQUE constraint).
        """
        from app.event_delivery.outbox_model import DurableDeliveryRecord
        import uuid as _uuid
        from datetime import datetime as _datetime, timezone as _timezone

        now = _datetime.now(_timezone.utc)
        for cid in consumer_ids:
            existing = session.execute(
                select(DurableDeliveryRecord).where(
                    DurableDeliveryRecord.event_id == event_id,
                    DurableDeliveryRecord.consumer_id == cid,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    DurableDeliveryRecord(
                        id=_uuid.uuid4().hex,
                        event_id=event_id,
                        consumer_id=cid,
                        state=DurableDeliveryRecord.PENDING,
                        attempts=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

    def save_many(self, events: List[Event]) -> None:
        """
        Persist several canonical Events atomically in one transaction.

        If any event violates the UNIQUE(event_id) constraint, the entire batch
        is rolled back and the IntegrityError is re-raised (no partial writes,
        no false success).
        """
        rows = [self._to_persistent(e) for e in events]
        with self.session_manager.session(commit=True) as session:
            # Assign distinct monotonic seq values within the batch. Because the
            # rows are not flushed until add_all, a naive per-row MAX(seq)+1 read
            # would return the same value for every row. Track a running counter
            # so each row in the batch gets a unique, strictly-increasing seq
            # (satisfying the UNIQUE(seq) invariant and deterministic replay order).
            next_seq = self._next_seq(session)
            for row in rows:
                row.seq = next_seq
                next_seq += 1
            session.add_all(rows)
            session.flush()

    def get(self, event_id: str) -> Optional[Event]:
        """Retrieve a canonical Event by its canonical event_id."""
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.event_id == event_id)
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        return self._from_persistent(row)

    def exists(self, event_id: str) -> bool:
        """Return True if a canonical event_id is durably persisted."""
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent.event_id)
                .where(DurableCanonicalEvent.event_id == event_id)
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none() is not None

    def delete(self, event_id: str) -> bool:
        """Delete a durable record by canonical event_id. Returns True if deleted."""
        with self.session_manager.session(commit=True) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.event_id == event_id)
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return False
            session.delete(row)
            return True

    def list_all(self) -> List[Event]:
        """Return all durable canonical Events in deterministic seq order."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(DurableCanonicalEvent).order_by(
                DurableCanonicalEvent.seq.asc(),
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._from_persistent(r) for r in rows]

    def list_after_seq(self, seq: int) -> List[Event]:
        """Return durable canonical Events with seq strictly greater than a
        checkpoint, ordered deterministically by seq ASC (WO-014-025).

        This is the additive sequential-retrieval API used by deterministic
        catch-up. It does not alter any existing repository contract.
        """
        return [event for _, event in self.iter_after_seq(seq)]

    def iter_after_seq(self, seq: int) -> List[tuple]:
        """Return ``(seq, Event)`` pairs with seq strictly greater than a
        checkpoint, ordered deterministically by seq ASC (WO-014-025).

        The catch-up driver needs the durable ``seq`` to advance the projection
        checkpoint. The canonical ``Event`` domain object does not carry
        ``seq`` (a durable persistence attribute), so this additive API returns
        the seq alongside each canonical Event. It does not modify the canonical
        ``Event`` model.
        """
        from app.event_repository.durable.durable_event_model import (
            DurableCanonicalEvent,
        )

        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.seq > int(seq))
                .order_by(DurableCanonicalEvent.seq.asc())
            )
            rows = list(session.execute(stmt).scalars().all())
        return [(r.seq, self._from_persistent(r)) for r in rows]

    def max_seq(self) -> int:
        """Return the highest durable seq, or 0 if the log is empty."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(func.max(DurableCanonicalEvent.seq))
            current_max = session.execute(stmt).scalar_one_or_none()
        return int(current_max) if current_max is not None else 0

    def list_by_type(self, event_type: str) -> List[Event]:
        """Return canonical Events filtered by event type string."""
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.event_type == event_type)
                .order_by(DurableCanonicalEvent.created_at, DurableCanonicalEvent.id)
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._from_persistent(r) for r in rows]

    def list_by_source(self, source: str) -> List[Event]:
        """Return canonical Events filtered by source."""
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.source == source)
                .order_by(DurableCanonicalEvent.created_at, DurableCanonicalEvent.id)
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._from_persistent(r) for r in rows]

    def list_by_correlation(self, correlation_id: str) -> List[Event]:
        """Return canonical Events whose metadata correlation_id matches."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(DurableCanonicalEvent).order_by(
                DurableCanonicalEvent.created_at,
                DurableCanonicalEvent.id,
            )
            rows = list(session.execute(stmt).scalars().all())
        return [
            self._from_persistent(r)
            for r in rows
            if (r.event_metadata or {}).get("correlation_id") == correlation_id
        ]

    # -- WO-037-01: additive read-only operator event feed -------------------

    def query_events(
        self,
        *,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        from_time: Optional[Any] = None,
        to_time: Optional[Any] = None,
        limit: int = 50,
        cursor: Optional[int] = None,
    ) -> "tuple[List[Event], Optional[int]]":
        """Return ``(events, next_cursor)`` for the operator event feed.

        Deterministic keyset/cursor pagination over the authoritative durable
        ``seq`` column (monotonic, ``ORDER BY seq ASC``). The cursor is the last
        ``seq`` returned; ``next_cursor`` is ``None`` on the final page.

        This method is ADDITIVE and READ-ONLY:
          * no offset pagination against the durable event table;
          * filtering/pagination applied at the database query layer;
          * ``limit`` is clamped to a bounded maximum;
          * no persistence side effects, no dispatch, no retry, no reconstruction;
          * does not modify the durable event schema or canonical event model.

        Args:
            source: optional authoritative source filter.
            event_type: optional authoritative event-type string filter.
            from_time: optional inclusive lower timestamp bound (naive treated
                as UTC).
            to_time: optional exclusive upper timestamp bound.
            limit: requested page size, clamped to ``[1, 200]``.
            cursor: opaque continuation cursor — the last durable ``seq``.
                Only an integer (or ``None``) is accepted; malformed values are
                rejected by raising ``ValueError``.

        Returns:
            ``(events, next_cursor)``. ``next_cursor`` is the ``seq`` of the
            last returned event, or ``None`` when there are no further rows.

        Raises:
            ValueError: if ``cursor`` is provided but not an int, or ``limit``
                is not a positive int, or ``from_time`` > ``to_time``.
        """
        if cursor is not None and not isinstance(cursor, int):
            raise ValueError("cursor must be an integer seq or None")
        if isinstance(cursor, bool):
            raise ValueError("cursor must be an integer seq or None")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be a positive integer")
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        limit = min(limit, 200)
        if from_time is not None and to_time is not None:
            if from_time > to_time:
                raise ValueError("from_time must not be after to_time")

        stmt = select(DurableCanonicalEvent)
        if cursor is not None:
            stmt = stmt.where(DurableCanonicalEvent.seq > int(cursor))
        if source is not None:
            stmt = stmt.where(DurableCanonicalEvent.source == source)
        if event_type is not None:
            stmt = stmt.where(DurableCanonicalEvent.event_type == event_type)
        if from_time is not None:
            stmt = stmt.where(DurableCanonicalEvent.timestamp >= from_time)
        if to_time is not None:
            stmt = stmt.where(DurableCanonicalEvent.timestamp < to_time)
        # Fetch limit+1 to detect whether another page exists.
        stmt = stmt.order_by(DurableCanonicalEvent.seq.asc()).limit(limit + 1)

        with self.session_manager.session(commit=False) as session:
            rows = list(session.execute(stmt).scalars().all())

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        events = [self._from_persistent(r) for r in page_rows]
        next_cursor = None
        if has_more:
            next_cursor = page_rows[-1].seq
        return events, next_cursor

    def get_durable_event(self, event_id: str) -> "Optional[tuple[int, Event]]":
        """Return ``(seq, Event)`` for one authoritative durable event.

        Additive, read-only helper that surfaces the authoritative durable
        ``seq`` alongside the canonical event for operator event-detail display.
        Returns ``None`` when the event_id is not durably persisted.

        Does not dispatch, retry, reconstruct, or mutate any state.
        """
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(DurableCanonicalEvent)
                .where(DurableCanonicalEvent.event_id == event_id)
                .limit(1)
            )
            row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        return row.seq, self._from_persistent(row)

    def count(self) -> int:
        """Return the number of durably persisted canonical events."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(func.count()).select_from(DurableCanonicalEvent)
            return int(session.execute(stmt).scalar_one())
