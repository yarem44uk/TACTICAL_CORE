"""WO-014-025 — Durable SQLAlchemy Entity Repository (single DB owner).

Implements the ``entity_manager.interfaces.i_repository.IRepository`` contract
(the repository abstraction used by the authoritative :class:`EntityManager`)
against the single existing :class:`DatabaseSessionManager` SQLAlchemy owner.

Architectural contract (WO-014-025, OPTION A — durable entity state):
  * Entity state becomes durable as part of production projection.
  * The ``entities`` table is registered on the shared ``Base.metadata`` so it
    is created by the same ``Base.metadata.create_all`` call that brings up the
    durable canonical events table — NO second ``create_engine``, NO second
    ``sessionmaker``, NO second database/session/transaction owner.
  * ``EntityManager`` remains the authoritative owner of Entity state mutation;
    this repository is the durable persistence implementation behind it.
  * ``Entity.id`` (``entity_id``) is the Entity identity. This is DISTINCT from
    the canonical Event identity (``Event.event_id``) and from any SQL surrogate
    key.
  * ``lock()`` returns a module-level :class:`threading.RLock` guarding
    read-modify-write cycles; actual transaction isolation is provided by the
    shared DatabaseSessionManager.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.session import DatabaseSessionManager, get_session_manager
from app.entity_manager.interfaces.i_repository import IRepository

# A single process-wide lock serialising read-modify-write entity cycles.
# Actual durability/transaction isolation is owned by DatabaseSessionManager.
_ENTITY_LOCK = threading.RLock()


class EntityRecord(Base):
    """Durable SQLAlchemy model for the derived Entity state."""

    __tablename__ = "entities"

    # Entity.id is the authoritative Entity identity (string UUID).
    id: Mapped[str] = mapped_column(String(128), primary_key=True)

    entity_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN", index=True
    )
    attributes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Stored under DB column "metadata"; attribute renamed because "metadata"
    # is reserved by the SQLAlchemy Declarative API.
    entity_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SQLAlchemyEntityRepository(IRepository):
    """Durable SQLAlchemy implementation of the Entity ``IRepository``."""

    def __init__(
        self, session_manager: Optional[DatabaseSessionManager] = None
    ) -> None:
        self._session_manager = session_manager

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """Ensure the durable entities table exists via the shared metadata."""
        Base.metadata.create_all(bind=self.session_manager.engine)

    # -- mapping -----------------------------------------------------------

    def _row_to_dict(self, row: EntityRecord) -> Dict[str, Any]:
        return {
            "entity_id": row.id,
            "entity_type": row.entity_type,
            "status": row.status,
            "attributes": dict(row.attributes or {}),
            "metadata": dict(row.entity_metadata or {}),
            "created_at": (
                row.created_at.isoformat() if row.created_at else None
            ),
            "updated_at": (
                row.updated_at.isoformat() if row.updated_at else None
            ),
            "version": row.version,
        }

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # -- IRepository -------------------------------------------------------

    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        with self.session_manager.session(commit=False) as session:
            row = session.get(EntityRecord, str(entity_id))
            if row is None or row.deleted_at is not None:
                return None
            return self._row_to_dict(row)

    def save(self, data: Dict[str, Any]) -> None:
        entity_id = str(data["entity_id"])
        now = self._now()
        with self.session_manager.session(commit=True) as session:
            existing = session.get(EntityRecord, entity_id)
            if existing is not None:
                existing.entity_type = data.get("entity_type", existing.entity_type)
                existing.status = data.get("status", existing.status)
                existing.attributes = dict(data.get("attributes", {}))
                existing.metadata = dict(data.get("metadata", {}))
                existing.updated_at = now
                existing.version = data.get("version", existing.version + 1)
            else:
                session.add(
                    EntityRecord(
                        id=entity_id,
                        entity_type=data.get("entity_type", ""),
                        status=data.get("status", "UNKNOWN"),
                        attributes=dict(data.get("attributes", {})),
                        metadata=dict(data.get("metadata", {})),
                        created_at=now,
                        updated_at=now,
                        version=data.get("version", 1),
                    )
                )

    def delete(self, entity_id: UUID | str) -> bool:
        """Soft delete by default (CV2)."""
        with self.session_manager.session(commit=True) as session:
            row = session.get(EntityRecord, str(entity_id))
            if row is None or row.deleted_at is not None:
                return False
            row.deleted_at = self._now()
            row.status = "DELETED"
            return True

    def tombstone(self, entity_id: UUID | str) -> bool:
        """WO-017 / ADR-ENTITY-RELATION-LIFECYCLE — durable entity TOMBSTONE transition.

        Transitions the entity ACTIVE -> TOMBSTONED.  This is a terminal,
        DURABLE lifecycle transition (NOT physical deletion): the row is
        retained with ``status = TOMBSTONED`` and ``deleted_at`` set, so it
        remains reconstructable from the durable event log but is excluded
        from active reads.

        Idempotent: an already-tombstoned (or already-deleted) entity is a
        no-op (returns False).  Non-reactivating in v1.
        """
        with self.session_manager.session(commit=True) as session:
            row = session.get(EntityRecord, str(entity_id))
            if row is None or row.deleted_at is not None:
                return False
            row.deleted_at = self._now()
            row.status = "TOMBSTONED"
            return True

    def is_tombstoned(self, entity_id: UUID | str) -> bool:
        """Return True if the entity is durably tombstoned (or deleted)."""
        with self.session_manager.session(commit=False) as session:
            row = session.get(EntityRecord, str(entity_id))
            if row is None:
                return False
            return row.deleted_at is not None

    def list_all(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = select(EntityRecord).where(EntityRecord.deleted_at.is_(None))
            if entity_type is not None:
                stmt = stmt.where(EntityRecord.entity_type == str(entity_type))
            stmt = stmt.order_by(EntityRecord.id.asc())
            rows = list(session.execute(stmt).scalars().all())
        return [self._row_to_dict(r) for r in rows]

    def lock(self) -> threading.RLock:
        """Expose a process-wide lock for atomic read-modify-write cycles."""
        return _ENTITY_LOCK

    # -- ISQLRepository-compatible extras (read-only / maintenance) ---------

    def list_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        return self.list_all(entity_type)

    def count(self) -> int:
        from sqlalchemy import func, select

        with self.session_manager.session(commit=False) as session:
            stmt = select(func.count()).select_from(EntityRecord).where(
                EntityRecord.deleted_at.is_(None)
            )
            return int(session.execute(stmt).scalar_one())

    def clear(self) -> None:
        """Delete all entity rows (maintenance/test helper)."""
        from sqlalchemy import delete

        with self.session_manager.session(commit=True) as session:
            session.execute(delete(EntityRecord))
