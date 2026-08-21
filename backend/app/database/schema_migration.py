"""
WO-021 — Schema Migration Infrastructure.

Establishes the first real, minimal, durable schema revision / migration
mechanism for TACTICAL_CORE, without introducing Alembic or any external
migration framework.

Architectural contract (WO-021):

* A single authoritative schema revision is tracked in a durable
  ``schema_migration_version`` table (``version``, ``applied_at``).
* Migrations live in an explicitly-ordered, deterministic registry (a
  module-level sequence ordered by ascending revision).  Ordering never
  depends on filesystem layout, dictionary iteration, timestamps, or random
  ids.
* ``upgrade_schema(...)`` determines the current revision, applies only the
  missing migrations in ascending order, and records each revision only after
  its operation succeeds.
* Repeated ``upgrade_schema`` is idempotent: no duplicate migration records,
  no duplicate schema objects, no data duplication.
* Migration-state inspection is available via ``get_schema_version`` and
  ``get_migration_state``.
* The mechanism operates through the existing single database owner —
  ``DatabaseSessionManager``.  It creates NO second engine, NO second
  sessionmaker, NO second connection manager, and NO independent database
  lifecycle (INVARIANT: exactly one database ownership mechanism).
* A migration is recorded as applied only after its schema/data operation
  succeeds.  On failure the revision is NOT recorded (transaction rollback);
  retry is deterministic.

Scope: infrastructure only.  No semantic change to Event, EventType, Entity,
Relation, ENTITY_REMOVED, RELATION_SEVERED, replay, deterministic
``relation_id``, lifecycle, or projection behaviour.

``Base.metadata.create_all`` remains available for current-schema bootstrap,
but it is NOT itself the migration engine — WO-021 adds explicit revision
tracking and ordered migration execution on top of it.  Revision 1's
operation is the (idempotent, additive, non-destructive) current-schema
bootstrap, executed under version control.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.session import DatabaseSessionManager, get_session_manager

# ---------------------------------------------------------------------------
# Durable schema-revision table
# ---------------------------------------------------------------------------


class SchemaMigrationVersion(Base):
    """One durable record per successfully applied schema revision.

    ``version`` is the authoritative, monotonically increasing schema
    revision.  It is recorded only after the corresponding migration
    operation has completed successfully.
    """

    __tablename__ = "schema_migration_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<SchemaMigrationVersion(version={self.version}, "
            f"name={self.name!r})>"
        )


# ---------------------------------------------------------------------------
# Ordered, deterministic migration registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Migration:
    """A single schema migration step."""

    revision: int
    name: str
    migrate: Callable[[DatabaseSessionManager], None]


def _bootstrap_current_schema(manager: DatabaseSessionManager) -> None:
    """Revision-1 operation: bring up the current (additive) schema.

    Uses ``Base.metadata.create_all`` bound to the existing single
    ``DatabaseSessionManager`` engine.  ``create_all`` is idempotent and
    non-destructive: it creates only tables that do not yet exist and never
    alters, drops, or rewrites existing tables.  It runs inside the migration
    transaction and is recorded as revision 1 only after it succeeds.
    """
    Base.metadata.create_all(bind=manager.engine)


def _index_durable_events_event_type(manager: DatabaseSessionManager) -> None:
    """Revision-2 operation: add a durable index on ``event_type``.

    WO-022 — REAL schema evolution on top of the WO-021 engine.

    The durable canonical-events repository exposes the production
    ``list_by_type`` query (``IEventRepository`` contract) which filters on
    ``DurableCanonicalEvent.event_type``.  Historically that column was
    UNINDEXED (the table carried indexes only on ``event_id`` and ``seq``).
    This migration performs a genuine OLD → NEW schema delta: it creates the
    ``ix_durable_canonical_events_event_type`` index on an existing,
    potentially populated ``durable_canonical_events`` table.

    Properties:
      * REAL DDL — executed with ``CREATE INDEX IF NOT EXISTS`` against the
        existing single ``DatabaseSessionManager`` engine.  It is NOT a
        ``create_all()`` bootstrap: ``create_all`` would never add this index
        to an already-existing table.
      * Deterministic / idempotent — ``IF NOT EXISTS`` makes a repeated run a
        safe no-op; no duplicate index can be created.
      * Non-destructive — it adds an index only; no column, table, row,
        identity, lifecycle, relation, or replay behaviour is altered.
      * Single owner — it runs through the SAME ``DatabaseSessionManager``
        that owns every other durable table (INVARIANT: no second engine,
        sessionmaker, or DB lifecycle).

    The ORM model declares ``index=True`` on ``event_type`` so fresh-schema
    bootstrap (``create_all``) stays in sync with the migrated schema; this
    migration guarantees the index is present on pre-existing databases.
    """
    from sqlalchemy import text

    with manager.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_durable_canonical_events_event_type "
                "ON durable_canonical_events (event_type)"
            )
        )


# Ordered ascending by revision — the ONLY ordering authority.
# To add a future revision, append a new Migration with a higher revision
# number here.  Do not renumber or reorder existing entries.
MIGRATIONS: Tuple[Migration, ...] = (
    Migration(revision=1, name="bootstrap_current_schema", migrate=_bootstrap_current_schema),
    Migration(
        revision=2,
        name="index_durable_events_event_type",
        migrate=_index_durable_events_event_type,
    ),
)

# The highest revision the registry knows how to apply.
TARGET_VERSION: int = MIGRATIONS[-1].revision


# ---------------------------------------------------------------------------
# Schema-revision table management (single owner)
# ---------------------------------------------------------------------------


def _ensure_version_table(manager: DatabaseSessionManager) -> None:
    """Ensure the ``schema_migration_version`` table exists on the shared
    metadata / engine.  Idempotent; uses the single existing owner."""
    Base.metadata.create_all(bind=manager.engine, tables=[SchemaMigrationVersion.__table__])


def _current_version(manager: DatabaseSessionManager) -> int:
    """Return the highest successfully applied revision (0 if none)."""
    with manager.session(commit=False) as session:
        rows = session.execute(select(SchemaMigrationVersion.version)).scalars().all()
    return max(rows) if rows else 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_schema_version(
    session_manager: Optional[DatabaseSessionManager] = None,
) -> int:
    """Return the current applied schema revision.

    Args:
        session_manager: Optional.  Defaults to the global single owner
            (``get_session_manager``).

    Returns:
        int: the highest applied revision (0 if none applied yet).
    """
    manager = session_manager or get_session_manager()
    _ensure_version_table(manager)
    return _current_version(manager)


def get_migration_state(
    session_manager: Optional[DatabaseSessionManager] = None,
) -> Dict[str, object]:
    """Return an inspection snapshot of the schema-migration state.

    Args:
        session_manager: Optional.  Defaults to the global single owner.

    Returns:
        dict with:
          * ``current_revision`` — applied revision (0 if none);
          * ``target_revision`` — the registry's latest revision;
          * ``upgrade_required`` — True iff current < target.
    """
    manager = session_manager or get_session_manager()
    current = get_schema_version(manager)
    return {
        "current_revision": current,
        "target_revision": TARGET_VERSION,
        "upgrade_required": current < TARGET_VERSION,
    }


def upgrade_schema(
    session_manager: Optional[DatabaseSessionManager] = None,
) -> int:
    """Apply all missing migrations in ascending revision order.

    Deterministic, idempotent, single-owner.  Only migrations whose revision
    is greater than the current applied revision are executed, in ascending
    order.  Each migration's operation and its revision record are written in
    one transaction: on success the revision is recorded; on failure the
    transaction rolls back and the revision is NOT recorded (no false
    success), so a corrected retry can recover deterministically.

    Args:
        session_manager: Optional.  Defaults to the global single owner.

    Returns:
        int: the resulting applied schema revision (== TARGET_VERSION on a
            fully-upgraded database).
    """
    manager = session_manager or get_session_manager()
    _ensure_version_table(manager)

    applied: int = _current_version(manager)
    pending: Sequence[Migration] = tuple(
        m for m in MIGRATIONS if m.revision > applied
    )

    for migration in pending:
        with manager.session(commit=True) as session:
            # Re-check inside the same transaction so concurrent upgrades and
            # repeated calls are safe (defensive; normal path already filtered).
            row = session.get(SchemaMigrationVersion, migration.revision)
            if row is not None:
                continue
            # Run the migration operation.  If it raises, the ``manager.session``
            # context rolls back and nothing is recorded.
            migration.migrate(manager)
            session.add(
                SchemaMigrationVersion(
                    version=migration.revision,
                    name=migration.name,
                    applied_at=datetime.now(timezone.utc),
                )
            )
        applied = migration.revision

    return applied
