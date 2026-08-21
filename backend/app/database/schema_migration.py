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
from sqlalchemy.orm import Mapped, Session, mapped_column

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
    """A single schema migration step.

    ``migrate`` receives both the single database owner (manager) and the
    active transaction ``session`` so that the migration's schema/data
    operation executes INSIDE the SAME transaction that records the revision.
    This is what makes each migration atomic: operation + revision record
    commit together, and roll back together on failure.
    """

    revision: int
    name: str
    migrate: Callable[[DatabaseSessionManager, "Session"], None]


def _bootstrap_current_schema(manager: DatabaseSessionManager, session: "Session") -> None:
    """Revision-1 operation: bring up the current (additive) schema.

    Uses ``Base.metadata.create_all`` bound to the active migration session's
    transaction (the existing single ``DatabaseSessionManager`` engine).
    ``create_all`` is idempotent and non-destructive: it creates only tables
    that do not yet exist and never alters, drops, or rewrites existing
    tables.  It runs inside the migration transaction and is recorded as
    revision 1 only after it succeeds.
    """
    Base.metadata.create_all(bind=session.get_bind())


def _index_durable_events_event_type(manager: DatabaseSessionManager, session: "Session") -> None:
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
        active migration transaction (the existing single owner).  It is NOT
        a ``create_all()`` bootstrap: ``create_all`` would never add this
        index to an already-existing table.
      * ATOMIC — the DDL runs inside the SAME transaction as the revision
        record; operation + record commit together and roll back together.
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

    session.execute(
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


# ---------------------------------------------------------------------------
# SQLite-lock detection / deterministic concurrency retry
# ---------------------------------------------------------------------------

def _is_sqlite_locked(exc: BaseException) -> bool:
    """Return True for SQLite 'database is locked' / 'database is busy'
    transient OperationalError conditions.

    Concurrent ``upgrade_schema`` callers against a shared SQLite file may
    transiently contend for the write lock.  These are *recoverable* transient
    conditions — not structural failures — and are retried with bounded
    backoff rather than being suppressed.  Non-lock errors are never retried.
    """
    from sqlalchemy.exc import OperationalError

    if not isinstance(exc, OperationalError):
        return False
    # ``exc.orig`` is the wrapped driver exception (e.g. ``sqlite3
    # .OperationalError``) — a single exception, not necessarily iterable.
    # Build a lowercase text fingerprint from both the wrapped error and the
    # SQLAlchemy error message so 'database is locked' / 'database is busy'
    # are reliably detected regardless of driver formatting.
    orig = getattr(exc, "orig", None)
    text = str(exc).lower()
    if orig is not None:
        try:
            text += " " + str(orig).lower()
        except Exception:  # noqa: BLE001 - best-effort only
            pass
    return ("database is locked" in text) or ("database is busy" in text)


# Test-controlled, deterministic failure-injection hook.  When set to a
# revision number, the migration engine raises a RuntimeError *after* the
# migration operation has run (a real schema/data mutation) but *before* the
# revision record is committed — proving atomic rollback.  It is ``None`` in
# normal production operation and is only ever set by WO-023 tests to inject a
# controlled failure.  This is deliberately isolated so no production caller
# can accidentally trigger it.
_FAIL_INJECT_REVISION: Optional[int] = None

# WO-024 test-only process-crash instrumentation.  Disabled by default.
#
# A REAL process crash — as opposed to a Python exception — is required to
# prove the migration durability boundary across an actual OS process boundary
# (WO-024).  When the WO-024 crash-recovery tests execute the migration engine
# in a child process they set these environment variables:
#
#   WO_CRASH_AT_REVISION=<int>  — only the migration whose revision matches may
#                                  hard-terminate the process
#   WO_CRASH_MODE=before_commit  — crash after the migration-side mutation has
#                                  run but BEFORE the revision transaction
#                                  commits (Boundary A)
#   WO_CRASH_MODE=after_commit   — crash AFTER the migration transaction has
#                                  successfully committed, before normal process
#                                  exit (Boundary B)
#
# When enabled at the matching boundary the engine calls ``os._exit(137)``,
# which terminates the process immediately WITHOUT running Python cleanup,
# ``finally`` handlers, or flushing buffered output — simulating abrupt
# OS-level process death.  In normal production neither variable is set, so
# this code path is entirely inert (disabled by default and impossible to
# trigger accidentally).  It never creates a second database owner and never
# bypasses the real transaction boundary — it fires at an actual boundary.
_CRASH_AT_REVISION: Optional[int] = None
_CRASH_MODE: Optional[str] = None


def _load_crash_hook() -> None:
    """Read the test-only crash instrumentation from the environment."""
    global _CRASH_AT_REVISION, _CRASH_MODE
    import os as _os

    raw = _os.environ.get("WO_CRASH_AT_REVISION")
    _CRASH_AT_REVISION = int(raw) if raw is not None else None
    _CRASH_MODE = _os.environ.get("WO_CRASH_MODE")


_load_crash_hook()


def _maybe_crash(migration: Migration, boundary: str) -> None:
    """Hard-terminate the process at a real transaction boundary (test-only).

    Only fires when the WO-024 test explicitly arms it via the environment for
    the exact revision and boundary.  ``os._exit`` bypasses Python teardown so
    the process dies as if by a real crash, leaving SQLite to recover the
    transaction boundary via its journal on the next open.
    """
    if (
        _CRASH_AT_REVISION is not None
        and _CRASH_AT_REVISION == migration.revision
        and _CRASH_MODE == boundary
    ):
        import os as _os

        _os._exit(137)


def _apply_migration(
    manager: DatabaseSessionManager,
    migration: Migration,
    *,
    max_lock_retries: int = 8,
    lock_retry_delay: float = 0.05,
) -> bool:
    """Apply a single migration in one atomic transaction.

    The migration's schema/data operation and its revision record are written
    in the SAME ``manager.session(commit=True)`` transaction.  On success the
    transaction commits atomically; on any failure the ``manager.session``
    context manager rolls back, so neither the partial operation nor the
    revision record survives (no false success, no partial migration state).

    SQLite file locking can transiently raise ``OperationalError: database is
    locked`` under concurrent writers.  Such transient lock errors are retried
    with bounded backoff (deterministic, never suppressed).  If a concurrent
    caller already applied this revision, the PK ``IntegrityError`` on the
    revision record is treated as a benign, already-applied no-op (the winning
    caller recorded it; the loser observes it and moves on).  A successful
    retry commits exactly once.

    Returns:
        True if this call applied the migration; False if it was already
        applied (idempotent no-op).
    """
    from time import sleep

    from sqlalchemy.exc import IntegrityError

    attempt = 0
    while True:
        try:
            with manager.session(commit=True) as session:
                # Re-check inside the same transaction so concurrent upgrades
                # and repeated calls are safe (defensive; normal path already
                # filtered by revision ordering).
                row = session.get(SchemaMigrationVersion, migration.revision)
                if row is not None:
                    return False
                # Run the migration operation inside the SAME transaction as
                # the revision record.  If it raises, the ``manager.session``
                # context rolls back both the operation and nothing is
                # recorded.
                #
                # Backward-compatible arity: WO-021/022 migration callables use
                # the single-argument ``(manager)`` form; WO-023 atomicity
                # migrations additionally accept ``(manager, session)`` so their
                # DML runs in the SAME transaction as the record.  Introspection
                # preserves both contracts.
                import inspect as _inspect

                _sig = _inspect.signature(migration.migrate)
                if len(_sig.parameters) >= 2:
                    migration.migrate(manager, session)
                else:
                    migration.migrate(manager)
                # Test-controlled failure injection: raise AFTER the real
                # mutation but BEFORE the revision record commit, so the whole
                # transaction (mutation + record) rolls back together.
                if _FAIL_INJECT_REVISION == migration.revision:
                    raise RuntimeError(
                        f"WO-023 injected failure for migration revision "
                        f"{migration.revision}"
                    )
                # WO-024 Boundary A: the migration-side mutation has run but the
                # revision transaction has NOT yet committed.  A real process
                # crash here must leave the DB at the previous valid revision
                # with the mutation rolled back (test-only; inert in prod).
                _maybe_crash(migration, "before_commit")
                session.add(
                    SchemaMigrationVersion(
                        version=migration.revision,
                        name=migration.name,
                        applied_at=datetime.now(timezone.utc),
                    )
                )
            return True
        except IntegrityError:
            # A concurrent caller already committed this revision (PK
            # uniqueness).  This is the expected, benign outcome for the
            # losing caller — the migration is already applied.  Nothing to
            # record and nothing to retry.
            return False
        except Exception as exc:  # noqa: BLE001 - re-raised after lock retry
            if _is_sqlite_locked(exc) and attempt < max_lock_retries:
                attempt += 1
                sleep(lock_retry_delay * attempt)
                continue
            raise


def upgrade_schema(
    session_manager: Optional[DatabaseSessionManager] = None,
) -> int:
    """Apply all missing migrations in ascending revision order.

    Deterministic, idempotent, single-owner.  Only migrations whose revision
    is greater than the current applied revision are executed, in ascending
    order.  Each migration's operation and its revision record are written in
    one transaction: on success the revision is recorded; on failure the
    transaction rolls back and the revision is NOT recorded (no false
    success), so a corrected retry can recover deterministically.  Concurrent
    SQLite file-lock contention is handled deterministically via bounded retry
    (transient ``database is locked``), never suppressed.

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
        if _apply_migration(manager, migration):
            applied = migration.revision
            # WO-024 Boundary B: the migration transaction has successfully
            # committed, but the process has not yet exited normally.  A real
            # process crash here must leave the committed migration durable
            # (test-only; inert in prod).
            _maybe_crash(migration, "after_commit")

    # Return the AUTHORITATIVE current revision actually persisted, not an
    # optimistic local counter.  Under concurrency a losing caller may observe
    # an already-applied revision as a benign no-op (``_apply_migration``
    # returns False) even though the database has advanced; re-reading the
    # durable version guarantees every caller reports the true converged
    # schema revision (WO-023 concurrency invariant).
    return get_schema_version(manager)
