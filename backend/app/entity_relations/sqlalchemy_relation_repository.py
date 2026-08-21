"""WO-016 — Durable SQLAlchemy Relation Repository (single DB owner).

Implements the authoritative ``IRelationRepository`` contract against the
single existing :class:`DatabaseSessionManager` SQLAlchemy owner, following
the established durable-persistence pattern of
``SQLAlchemyEntityRepository``.

Architectural contract (Durable Relation Projection):
  * The ``entity_relations`` table is registered on the shared
    ``Base.metadata`` so it is created by the same
    ``Base.metadata.create_all`` call that brings up the durable canonical
    events / entities / checkpoint tables — NO second ``create_engine``, NO
    second ``sessionmaker``, NO second database/session/transaction owner.
  * ``relation_id`` is a DETERMINISTIC durable identity derived from the
    logical relation ``(source_entity_id, target_entity_id, relation_type)``,
    NOT a random UUID.  The same logical relation derived from the same
    canonical Event therefore resolves to the same durable identity, making
    duplicate canonical-Event processing idempotent at the database level.
  * ``save()`` is an idempotent upsert keyed on ``relation_id``: reprocessing
    the same canonical Event never creates a duplicate relation row.
  * WO-017 (ADR-ENTITY-RELATION-LIFECYCLE) durable relation lifecycle: ``status`` is ACTIVE (default)
    or INACTIVE (terminal).  Lifecycle is MUTABLE state on the SAME
    deterministic ``relation_id`` — it is never part of identity, and
    transitions never physically delete the row (historical preservation).
    ``inactivate_for_entity()`` implements the synchronous, deterministic,
    idempotent entity-deactivation cascade.
  * ``lock()`` returns a module-level :class:`threading.RLock` guarding
    read-modify-write cycles; actual transaction isolation is provided by the
    shared DatabaseSessionManager.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.session import DatabaseSessionManager, get_session_manager
from app.entity_relations.interfaces.i_relation_repository import IRelationRepository

# A single process-wide lock serialising read-modify-write relation cycles.
# Actual durability/transaction isolation is owned by DatabaseSessionManager.
_RELATION_LOCK = threading.RLock()


def deterministic_relation_id(
    source_entity_id: str | UUID,
    target_entity_id: str | UUID,
    relation_type: str,
) -> str:
    """Return a deterministic, stable durable identity for a logical relation.

    The identity is a SHA-256 digest (hex) of the canonical
    ``(source_entity_id, target_entity_id, relation_type)`` triple.  It is:

      * deterministic — the same logical relation always maps to the same id;
      * stable across repeated processing of the same canonical Event;
      * independent of the (random) canonical ``Event.event_id``, so two
        Events that establish the same logical relation resolve to the same
        durable relation, preventing accidental duplicates.
    """
    canonical = "|".join(
        [str(source_entity_id), str(target_entity_id), str(relation_type)]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RelationRecord(Base):
    """Durable SQLAlchemy model for the derived Entity relation state."""

    __tablename__ = "entity_relations"

    # relation_id is the deterministic durable identity (sha-256 hex string).
    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    source_entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    # The canonical Event.event_id that established this relation (provenance).
    source_event_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    relation_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True
    )
    # WO-017 (ADR-ENTITY-RELATION-LIFECYCLE) — durable lifecycle state.  ``status`` is the terminal
    # relation lifecycle: ACTIVE (default) or INACTIVE (terminal).  ``status``
    # is MUTABLE state on the SAME deterministic ``relation_id`` — it is NOT
    # part of relation identity.  Lifecycle transitions never physically delete
    # the row (historical preservation).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", index=True
    )
    terminated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"



class SQLAlchemyRelationRepository(IRelationRepository):
    """Durable SQLAlchemy implementation of the Relation ``IRelationRepository``."""

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
        """Ensure the durable entity_relations table exists via shared metadata."""
        Base.metadata.create_all(bind=self.session_manager.engine)

    # -- mapping -----------------------------------------------------------

    def _row_to_dict(self, row: RelationRecord) -> Dict[str, Any]:
        return {
            "relation_id": row.relation_id,
            "source_entity_id": row.source_entity_id,
            "target_entity_id": row.target_entity_id,
            "relation_type": row.relation_type,
            "confidence": row.confidence,
            "source_event_id": row.source_event_id,
            "metadata": dict(row.relation_metadata or {}),
            "status": row.status,
            "terminated_at": (
                row.terminated_at.isoformat() if row.terminated_at else None
            ),
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

    # -- IRelationRepository -----------------------------------------------

    def save(self, data: Dict[str, Any]) -> None:
        """Idempotent upsert keyed on the deterministic ``relation_id``.

        If the logical relation already exists (same deterministic identity,
        e.g. the same canonical Event was reprocessed), the existing row is
        updated in place — it is never duplicated and never silently changes
        identity.
        """
        relation_id = str(data["relation_id"])
        now = self._now()
        with self.session_manager.session(commit=True) as session:
            existing = session.get(RelationRecord, relation_id)
            if existing is not None:
                existing.source_entity_id = str(data["source_entity_id"])
                existing.target_entity_id = str(data["target_entity_id"])
                existing.relation_type = str(data["relation_type"])
                existing.confidence = float(data.get("confidence", 1.0))
                existing.source_event_id = (
                    str(data["source_event_id"])
                    if data.get("source_event_id") is not None
                    else existing.source_event_id
                )
                existing.relation_metadata = dict(data.get("metadata", {}))
                # Lifecycle state is MUTABLE on the deterministic identity: an
                # existing relation keeps its current status (e.g. INACTIVE is
                # never silently resurrected by a re-projected creation event).
                existing.status = existing.status or RelationRecord.ACTIVE
                existing.updated_at = now
                existing.version = int(data.get("version", existing.version + 1))
            else:
                session.add(
                    RelationRecord(
                        relation_id=relation_id,
                        source_entity_id=str(data["source_entity_id"]),
                        target_entity_id=str(data["target_entity_id"]),
                        relation_type=str(data["relation_type"]),
                        confidence=float(data.get("confidence", 1.0)),
                        source_event_id=(
                            str(data["source_event_id"])
                            if data.get("source_event_id") is not None
                            else None
                        ),
                        relation_metadata=dict(data.get("metadata", {})),
                        status=RelationRecord.ACTIVE,
                        created_at=now,
                        updated_at=now,
                        version=int(data.get("version", 1)),
                    )
                )

    def get(self, relation_id: str | UUID) -> Optional[Dict[str, Any]]:
        with self.session_manager.session(commit=False) as session:
            row = session.get(RelationRecord, str(relation_id))
            if row is None:
                return None
            return self._row_to_dict(row)

    def delete(self, relation_id: str | UUID) -> bool:
        """Explicit-administrative PURGE only.

        WO-017 / ADR-ENTITY-RELATION-LIFECYCLE: lifecycle transitions (ACTIVE -> INACTIVE) are durable
        state changes and MUST NOT use physical deletion.  ``delete()`` is
        retained solely for explicit administrative purge and is never invoked
        by the lifecycle/cascade path.
        """
        with self.session_manager.session(commit=True) as session:
            row = session.get(RelationRecord, str(relation_id))
            if row is None:
                return False
            session.delete(row)
            return True

    def inactivate_for_entity(self, entity_id: str | UUID) -> int:
        """Deterministic entity-deactivation CASCADE (WO-017 / ADR-ENTITY-RELATION-LIFECYCLE).

        When an entity transitions to a terminal (TOMBSTONED) state, all
        canonical relations referencing that entity (as source OR target)
        transition ACTIVE -> INACTIVE.  This is:

          * synchronous / projection-time;
          * deterministic and idempotent — only ACTIVE rows are touched;
          * durable — the rows are updated in place, never physically deleted;
          * non-reactivating — INACTIVE is terminal in v1.

        Uses the single DatabaseSessionManager owner (independent transaction,
        consistent with the verified EVENT/ENTITY/RELATION independent-TX
        architecture).  Returns the number of relations inactivated.
        """
        from sqlalchemy import or_, select

        eid = str(entity_id)
        now = self._now()
        count = 0
        with self.session_manager.session(commit=True) as session:
            stmt = (
                select(RelationRecord)
                .where(
                    or_(
                        RelationRecord.source_entity_id == eid,
                        RelationRecord.target_entity_id == eid,
                    )
                )
                .where(RelationRecord.status == RelationRecord.ACTIVE)
            )
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                row.status = RelationRecord.INACTIVE
                row.terminated_at = now
                row.updated_at = now
                row.version = row.version + 1
                count += 1
        return count

    def list_all(self) -> List[Dict[str, Any]]:
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = select(RelationRecord).order_by(
                RelationRecord.source_entity_id.asc(),
                RelationRecord.target_entity_id.asc(),
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._row_to_dict(r) for r in rows]

    def list_for_entity(
        self,
        entity_id: str | UUID,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List relations involving a specific entity.

        Args:
            entity_id: The entity identity.
            status: Optional lifecycle filter (``ACTIVE`` / ``INACTIVE``).  When
                ``None``, ALL relations (active + inactive) for the entity are
                returned (historical view).  When ``ACTIVE``, only currently
                active relations are returned (read-side active view).
        """
        from sqlalchemy import or_, select

        eid = str(entity_id)
        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(RelationRecord)
                .where(
                    or_(
                        RelationRecord.source_entity_id == eid,
                        RelationRecord.target_entity_id == eid,
                    )
                )
            )
            if status is not None:
                stmt = stmt.where(RelationRecord.status == str(status))
            stmt = stmt.order_by(RelationRecord.relation_type.asc())
            rows = list(session.execute(stmt).scalars().all())
        return [self._row_to_dict(r) for r in rows]

    def list_active(self) -> List[Dict[str, Any]]:
        """List only currently-ACTIVE relations (read-side active view)."""
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(RelationRecord)
                .where(RelationRecord.status == RelationRecord.ACTIVE)
                .order_by(
                    RelationRecord.source_entity_id.asc(),
                    RelationRecord.target_entity_id.asc(),
                )
            )
            rows = list(session.execute(stmt).scalars().all())
        return [self._row_to_dict(r) for r in rows]

    def list_historical(self) -> List[Dict[str, Any]]:
        """List ALL relations (active + inactive) — historical view."""
        return self.list_all()

    def lock(self) -> threading.RLock:
        """Expose a process-wide lock for atomic read-modify-write cycles."""
        return _RELATION_LOCK
