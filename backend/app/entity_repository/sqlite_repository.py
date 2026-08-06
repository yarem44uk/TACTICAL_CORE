from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from .interfaces.i_sql_repository import ISQLRepository
from .migration import apply_migrations


class SQLiteEntityRepository(ISQLRepository):
    """SQLite-backed Entity Repository with thread safety and soft delete support."""

    def __init__(self, db_path: str = "data/entities.db") -> None:
        """Initialize repository and apply migrations.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        apply_migrations(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["attributes"] = json.loads(d["attributes"])
        d["metadata"] = json.loads(d["metadata"])
        return d

    # -- ISQLRepository --

    def save(self, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        entity_id = str(data["entity_id"])
        entity_type = data.get("entity_type", "")
        status = data.get("status", "UNKNOWN")
        attributes = json.dumps(data.get("attributes", {}))
        metadata = json.dumps(data.get("metadata", {}))
        version = data.get("version", 1)

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO entities
                    (id, entity_type, status, attributes, metadata, created_at, updated_at, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    status=excluded.status,
                    attributes=excluded.attributes,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at,
                    version=excluded.version
                    """,
                    (entity_id, entity_type, status, attributes, metadata, now, now, version),
                )
                conn.commit()
            finally:
                conn.close()

    def update(self, entity_id: UUID | str, updates: Dict[str, Any]) -> bool:
        eid = str(entity_id)
        with self._lock:
            conn = self._connect()
            try:
                now = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute(
                    "SELECT attributes, metadata, version FROM entities WHERE id = ?",
                    (eid,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                attrs = json.loads(row["attributes"])
                meta = json.loads(row["metadata"])
                attrs.update(updates)
                new_version = row["version"] + 1
                conn.execute(
                    "UPDATE entities SET attributes=?, metadata=?, updated_at=?, version=? WHERE id=?",
                    (json.dumps(attrs), json.dumps(meta), now, new_version, eid),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def get(self, entity_id: UUID | str) -> Optional[Dict[str, Any]]:
        eid = str(entity_id)
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT * FROM entities WHERE id = ? AND deleted_at IS NULL",
                    (eid,),
                )
                row = cursor.fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def delete(self, entity_id: UUID | str) -> bool:
        """Soft delete by default (CV2)."""
        return self.soft_delete(entity_id)

    def soft_delete(self, entity_id: UUID | str) -> bool:
        eid = str(entity_id)
        with self._lock:
            conn = self._connect()
            try:
                now = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute(
                    "UPDATE entities SET deleted_at=?, status='DELETED' WHERE id=? AND deleted_at IS NULL",
                    (now, eid),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def hard_delete(self, entity_id: UUID | str) -> bool:
        eid = str(entity_id)
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute("DELETE FROM entities WHERE id=?", (eid,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute("SELECT * FROM entities WHERE deleted_at IS NULL")
                return [self._row_to_dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()

    def list_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT * FROM entities WHERE entity_type=? AND deleted_at IS NULL",
                    (entity_type,),
                )
                return [self._row_to_dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()

    def list_deleted(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute("SELECT * FROM entities WHERE deleted_at IS NOT NULL")
                return [self._row_to_dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()

    def close(self) -> None:
        pass
