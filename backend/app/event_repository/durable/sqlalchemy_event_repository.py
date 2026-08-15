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
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                # Duplicate canonical event_id: idempotent no-op. Rollback the
                # failed flush so the session is clean, and return without error.
                session.rollback()
                return

    def save_many(self, events: List[Event]) -> None:
        """
        Persist several canonical Events atomically in one transaction.

        If any event violates the UNIQUE(event_id) constraint, the entire batch
        is rolled back and the IntegrityError is re-raised (no partial writes,
        no false success).
        """
        rows = [self._to_persistent(e) for e in events]
        with self.session_manager.session(commit=True) as session:
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
        """Return all durable canonical Events in insertion order."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(DurableCanonicalEvent).order_by(
                DurableCanonicalEvent.created_at,
                DurableCanonicalEvent.id,
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._from_persistent(r) for r in rows]

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

    def count(self) -> int:
        """Return the number of durably persisted canonical events."""
        with self.session_manager.session(commit=False) as session:
            stmt = select(func.count()).select_from(DurableCanonicalEvent)
            return int(session.execute(stmt).scalar_one())
