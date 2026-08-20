"""WO-014-025 — SQLite Entity Repository refactored onto the single DB owner.

Refactor of the legacy raw-``sqlite3`` ``SQLiteEntityRepository`` so it no
longer creates its own engine / sessionmaker / SQLite database / transaction
lifecycle. It now persists through the single canonical
:class:`DatabaseSessionManager` (the same owner used by the durable canonical
Event repository), registering the ``entities`` table on the shared
``Base.metadata``.

The public :class:`ISQLRepository` method surface (``save``, ``update``,
``get``, ``delete``, ``soft_delete``, ``hard_delete``, ``list``,
``list_by_type``, ``list_deleted``, ``close``) is preserved for backward
compatibility, so existing consumers/tests of ``SQLiteEntityRepository`` keep
working. This class is the durable-persistence analogue of the newer
``SQLAlchemyEntityRepository`` (which implements the Entity ``IRepository``
contract used by :class:`EntityManager`).

NO second ``create_engine``, NO second ``sessionmaker``, NO independent DB
owner is introduced (WO-014-025 single-owner invariant).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database.base import Base
from app.database.session import DatabaseSessionManager, get_session_manager
from app.entity_repository.sqlalchemy_entity_repository import EntityRecord
from .interfaces.i_sql_repository import ISQLRepository

_LOCK = threading.RLock()

# The durable ``entities`` SQLAlchemy model is shared with
# ``SQLAlchemyEntityRepository`` so the table is defined ONCE on the shared
# ``Base.metadata`` (no duplicate-table collision). ``EntityRecord`` is
# re-exported here for the refactored ``SQLiteEntityRepository`` to reuse.
EntityTable = EntityRecord


class SQLiteEntityRepository(ISQLRepository):
    """SQLAlchemy-backed Entity repository using the single DatabaseSessionManager."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        session_manager: Optional[DatabaseSessionManager] = None,
    ) -> None:
        """Initialize the repository.

        Args:
            db_path: Ignored for backward compatibility (kept for callers that
                historically passed a path). Durability is owned by the shared
                DatabaseSessionManager, not by a repository-local file.
            session_manager: Optional session manager. Defaults to the global
                session manager (``get_session_manager``).
        """
        self._session_manager = session_manager
        self._lock = _LOCK
        # Backward-compatible alias (some callers relied on the path).
        self._db_path = db_path

    @property
    def session_manager(self) -> DatabaseSessionManager:
        if self._session_manager is None:
            return get_session_manager()
        return self._session_manager

    def initialize(self) -> None:
        """Ensure the durable entities table exists via the shared metadata."""
        Base.metadata.create_all(bind=self.session_manager.engine)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _row_to_dict(self, row: EntityTable) -> Dict[str, Any]:
        d = {
            "id": row.id,
            "entity_id": row.id,
            "entity_type": row.entity_type,
            "status": row.status,
            "attributes": dict(row.attributes or {}),
            "metadata": dict(row.entity_metadata or {}),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "version": row.version,
        }
        if row.deleted_at is not None:
            d["deleted_at"] = row.deleted_at.isoformat()
        return d

    # -- ISQLRepository -----------------------------------------------------

    def save(self, data: Dict[str, Any]) -> None:
        entity_id = str(data["entity_id"])
        now = self._now()
        with self.session_manager.session(commit=True) as session:
            existing = session.get(EntityTable, entity_id)
            if existing is not None:
                existing.entity_type = data.get("entity_type", existing.entity_type)
                existing.status = data.get("status", existing.status)
                existing.attributes = dict(data.get("attributes", {}))
                existing.entity_metadata = dict(data.get("metadata", {}))
                existing.updated_at = now
                existing.version = data.get("version", existing.version + 1)
            else:
                session.add(
                    EntityTable(
                        id=entity_id,
                        entity_type=data.get("entity_type", ""),
                        status=data.get("status", "UNKNOWN"),
                        attributes=dict(data.get("attributes", {})),
                        entity_metadata=dict(data.get("metadata", {})),
                        created_at=now,
                        updated_at=now,
                        version=data.get("version", 1),
                    )
                )

    def update(self, entity_id: UUID | str, updates: Dict[str, Any]) -> bool:
        eid = str(entity_id)
        with self.session_manager.session(commit=True) as session:
            row = session.get(EntityTable, eid)
            if row is None:
                return False
            attrs = dict(row.attributes or {})
            attrs.update(updates)
            row.attributes = attrs
            row.updated_at = self._now()
            row.version += 1
            return True

    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        eid = str(entity_id)
        with self.session_manager.session(commit=False) as session:
            row = session.get(EntityTable, eid)
            if row is None or row.deleted_at is not None:
                return None
            return self._row_to_dict(row)

    def delete(self, entity_id: UUID | str) -> bool:
        """Soft delete by default (CV2)."""
        return self.soft_delete(entity_id)

    def soft_delete(self, entity_id: UUID | str) -> bool:
        eid = str(entity_id)
        with self.session_manager.session(commit=True) as session:
            row = session.get(EntityTable, eid)
            if row is None or row.deleted_at is not None:
                return False
            row.deleted_at = self._now()
            row.status = "DELETED"
            return True

    def hard_delete(self, entity_id: UUID | str) -> bool:
        eid = str(entity_id)
        with self.session_manager.session(commit=True) as session:
            row = session.get(EntityTable, eid)
            if row is None:
                return False
            session.delete(row)
            return True

    def list(self) -> List[Dict[str, Any]]:
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(EntityTable)
                .where(EntityTable.deleted_at.is_(None))
                .order_by(EntityTable.id.asc())
            )
            return [self._row_to_dict(r) for r in session.execute(stmt).scalars().all()]

    def list_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(EntityTable)
                .where(
                    EntityTable.entity_type == entity_type,
                    EntityTable.deleted_at.is_(None),
                )
                .order_by(EntityTable.id.asc())
            )
            return [self._row_to_dict(r) for r in session.execute(stmt).scalars().all()]

    def list_deleted(self) -> List[Dict[str, Any]]:
        from sqlalchemy import select

        with self.session_manager.session(commit=False) as session:
            stmt = (
                select(EntityTable)
                .where(EntityTable.deleted_at.is_not(None))
                .order_by(EntityTable.id.asc())
            )
            return [self._row_to_dict(r) for r in session.execute(stmt).scalars().all()]

    def close(self) -> None:
        # The shared DatabaseSessionManager owns engine/session lifecycle.
        pass
