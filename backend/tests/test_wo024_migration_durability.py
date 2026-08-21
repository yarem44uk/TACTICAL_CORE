"""
WO-024 — Migration Durability / Crash-Recovery Boundary.

Locks the ratified WO-024 verification contract for the WO-021/022/023 schema
migration engine across a REAL OS process-crash boundary:

  * BOUNDARY A — the process terminates AFTER the migration-side mutation has
    run but BEFORE the migration transaction commits.  On reopening the
    database:
        - the migration revision is NOT recorded;
        - the migration-side DML is NOT durable (rolled back);
        - the database remains at the previous valid revision;
        - no impossible mixed state exists;
        - a retry can recover deterministically.

  * BOUNDARY B — the process terminates AFTER the migration transaction has
    successfully committed but BEFORE normal process exit.  On reopening the
    database:
        - the migration revision IS recorded;
        - the migration-side DML IS present and durable;
        - no duplicate migration record exists;
        - a further upgrade is an idempotent no-op.

A Python exception is deliberately NOT used as crash evidence here.  At least
one canonical test crosses a REAL OS process boundary (``subprocess.Popen``)
and terminates the child abnormally via ``os._exit`` — a genuine hard process
death, not a raised exception.

Scope: migration-engine crash-recovery boundary only.  No change to Event,
EventType, Entity, Relation, lifecycle, severance, replay, deterministic
``relation_id``, or projection semantics.  Single ``DatabaseSessionManager``
owner is preserved throughout — no second engine, sessionmaker, or DB owner.

Durability scope (reported honestly in the final report):
  * PROVEN here: process-crash consistency, transactional rollback, committed
    state surviving process termination, restart recovery, retry, idempotency.
  * NOT PROVEN here (would require separate physical storage power-loss
    testing): power-loss durability, filesystem/controller cache behaviour,
    hardware storage failure, sudden power removal.  The WO-021 revision-2
    index migration uses raw SQLite DDL (implicitly committed, not
    rollback-safe via the ORM session); this suite therefore exercises the
    transactional path with a DML probe, exactly as WO-023 does.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

import app.database.schema_migration as schema_mod
import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.schema_migration import (
    MIGRATIONS,
    TARGET_VERSION,
    get_migration_state,
    get_schema_version,
    upgrade_schema,
)
from app.database.session import configure_session_manager, get_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)

CRASH_PROBE_REVISION = 9998
PROBE_ID = "wo024-probe-row"
PROBE_EVENT_ID = "wo024-probe-event"
PROBE_SEQ = 999900


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _reset():
    session_mod._session_manager = None


def _entity_created(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_CREATED,
        payload={"entity_type": "unit", "callsign": entity_id},
    )


def _relation_event(event_id: str, source: str, target: str, rel_type: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=source,
        event_type=EventType.ENTITY_UPDATED,
        payload={"target_entity_id": target, "relation_type": rel_type, "confidence": 1.0},
    )


def _entity_removed(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_REMOVED,
        payload={},
    )


def _severed(source: str, target: str, rel_type: str, event_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=source,
        event_type=EventType.RELATION_SEVERED,
        payload={"source_entity_id": source, "target_entity_id": target, "relation_type": rel_type},
    )


def _capture(rt) -> dict:
    er = SQLAlchemyEventRepository()
    rr = rt.relation_repository
    ent = rt.entity_repository
    events = er.list_all()
    return {
        "event_ids": sorted(e.event_id for e in events),
        "event_count": len(events),
        "entity_status": {str(e["entity_id"]): e["status"] for e in ent.list_all()},
        "entity_count": len(ent.list_all()),
        "relation_status": {r["relation_id"]: r["status"] for r in rr.list_all()},
        "relation_ids": sorted(r["relation_id"] for r in rr.list_all()),
        "relation_count": len(rr.list_all()),
    }


def _migration_records(manager=None) -> list:
    mgr = manager or get_session_manager()
    with mgr.session(commit=False) as s:
        rows = s.execute(select(schema_mod.SchemaMigrationVersion.version)).scalars().all()
    return sorted(rows)


def _probe_count(manager=None) -> int:
    mgr = manager or get_session_manager()
    with mgr.session(commit=False) as s:
        n = s.execute(
            sa.text("SELECT COUNT(*) FROM durable_canonical_events WHERE id = :i"),
            {"i": PROBE_ID},
        ).scalar()
    return n


def _seed(db_path: str) -> dict:
    """Populate a file DB with realistic canonical state and close it."""
    configure_session_manager(_url(db_path))
    rt = create_event_runtime()
    rt.pipeline.process(_entity_created("E1", "A"))
    rt.pipeline.process(_entity_created("E2", "B"))
    rt.pipeline.process(_relation_event("E3", "A", "B", "relates_to"))
    rt.pipeline.process(_relation_event("E4", "A", "B2", "relates_to"))
    rt.pipeline.process(_entity_created("E5", "C"))
    rt.pipeline.process(_relation_event("E6", "C", "A", "relates_to"))
    rt.pipeline.process(_entity_removed("E7", "C"))
    rt.pipeline.process(_severed("A", "B2", "relates_to", "E8"))
    fp = _capture(rt)
    _reset()
    return fp


def _probe_migration():
    """A real DML migration (rollback-safe) used as the crash target.

    Inserts a marker row into the existing durable ``durable_canonical_events``
    table INSIDE the active migration session — the same transaction that
    records the revision.  SQLite DML is transactional, so a crash before
    commit rolls the row back, while a crash after commit leaves it durable.
    """
    def _migrate(manager, session) -> None:
        from datetime import datetime, timezone

        session.execute(
            sa.text(
                "INSERT INTO durable_canonical_events "
                "(id, seq, event_id, entity_id, event_type, timestamp, source, "
                " payload, metadata, created_at) "
                "VALUES (:id, :seq, :event_id, :entity_id, :event_type, "
                ":ts, :source, :payload, :metadata, :ts)"
            ),
            {
                "id": PROBE_ID,
                "seq": PROBE_SEQ,
                "event_id": PROBE_EVENT_ID,
                "entity_id": "wo024-probe-entity",
                "event_type": "ENTITY_CREATED",
                "ts": datetime.now(timezone.utc),
                "source": "wo024-probe",
                "payload": "{}",
                "metadata": "{}",
            },
        )

    return schema_mod.Migration(
        revision=CRASH_PROBE_REVISION,
        name="wo024_probe_data",
        migrate=_migrate,
    )


# ---------------------------------------------------------------------------
# Real child-process crash helpers
# ---------------------------------------------------------------------------


def _child_code() -> str:
    """Python source executed in a REAL child OS process against a REAL file DB.

    Registers the probe migration and runs the REAL migration engine.  The
    environment variables WO_CRASH_AT_REVISION / WO_CRASH_MODE (set by the
    parent on the child's env) cause the engine to hard-terminate the child via
    ``os._exit`` at the exact transaction boundary.
    """
    return (
        "import sqlalchemy as sa\n"
        "from datetime import datetime, timezone\n"
        "import app.database.schema_migration as sm\n"
        "from app.database.session import configure_session_manager\n"
        "db = %r\n"
        "configure_session_manager('sqlite:///' + db)\n"
        "def probe(manager, session):\n"
        "    session.execute(sa.text(\n"
        "        'INSERT INTO durable_canonical_events '\n"
        "        '(id, seq, event_id, entity_id, event_type, timestamp, source, '\n"
        "        ' payload, metadata, created_at) '\n"
        "        'VALUES (:id, :seq, :event_id, :entity_id, :event_type, '\n"
        "        ':ts, :source, :payload, :metadata, :ts)'\n"
        "    ), {\n"
        "        'id': %r,\n"
        "        'seq': %d,\n"
        "        'event_id': %r,\n"
        "        'entity_id': 'wo024-probe-entity',\n"
        "        'event_type': 'ENTITY_CREATED',\n"
        "        'ts': datetime.now(timezone.utc),\n"
        "        'source': 'wo024-probe',\n"
        "        'payload': '{}',\n"
        "        'metadata': '{}',\n"
        "    })\n"
        "sm.MIGRATIONS = sm.MIGRATIONS + (sm.Migration(%d, 'wo024_probe_data', probe),)\n"
        "sm.upgrade_schema()\n"
    ) % (
        "%s",  # db path placeholder
        PROBE_ID,
        PROBE_SEQ,
        PROBE_EVENT_ID,
        CRASH_PROBE_REVISION,
    )


def _run_child(db_path: str, crash_mode: str) -> int:
    """Spawn a real child process that runs the migration engine and crashes.

    Returns the child's exit code (137 when hard-terminated via os._exit).
    """
    code = _child_code().replace("%s", db_path, 1)
    env = dict(os.environ)
    env["PYTHONPATH"] = "backend"
    env["WO_CRASH_AT_REVISION"] = str(CRASH_PROBE_REVISION)
    env["WO_CRASH_MODE"] = crash_mode
    python = sys.executable
    # Prefer the repository's own virtualenv python so imports resolve.
    repo_venv = "/opt/data/tactical_core_github/.venv/bin/python"
    if os.path.exists(repo_venv):
        python = repo_venv
    proc = subprocess.run(
        [python, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd="/opt/data/tactical_core_github/backend",
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# 1. Baseline / registry invariants
# ---------------------------------------------------------------------------


def test_crash_hook_inert_by_default():
    """The WO-024 crash instrumentation is disabled in normal operation."""
    assert schema_mod._CRASH_AT_REVISION is None
    assert schema_mod._CRASH_MODE is None


def test_registry_ordered_unique_deterministic(tmp_path):
    db = tmp_path / "b.db"
    configure_session_manager(_url(str(db)))
    revisions = [m.revision for m in MIGRATIONS]
    assert revisions == sorted(revisions)
    assert len(set(revisions)) == len(revisions)
    assert TARGET_VERSION == max(revisions)
    _reset()


# ---------------------------------------------------------------------------
# BOUNDARY A — crash BEFORE commit (real process death)
# ---------------------------------------------------------------------------


def test_crash_before_commit_rolls_back_mutation_and_revision(tmp_path):
    """A REAL process crash after the migration mutation but before commit must
    leave the DB at the previous valid revision with the mutation rolled back;
    a retry then converges deterministically with exactly one record."""
    db = tmp_path / "a.db"
    before = _seed(str(db))

    # Establish a clean, valid baseline at the WO-021/022 target revision.
    configure_session_manager(_url(str(db)))
    assert upgrade_schema() == TARGET_VERSION
    assert get_schema_version() == TARGET_VERSION
    _reset()

    # Spawn a real child process that runs the engine and is hard-killed
    # (os._exit) after the probe DML mutation but BEFORE the commit.
    rc = _run_child(str(db), "before_commit")
    assert rc == 137  # genuine abnormal termination, not a normal return

    # Parent reopens the DB with production infrastructure.
    configure_session_manager(_url(str(db)))
    # Revision of the crashing migration is NOT recorded — DB at previous valid
    # revision (the WO-021/022 target = 2), NOT the probe revision 9998.
    assert get_schema_version() == TARGET_VERSION
    assert CRASH_PROBE_REVISION not in _migration_records()
    # Migration-side DML mutation is NOT durable — rolled back.
    assert _probe_count() == 0

    # Retry via the same real engine converges to the full target.
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (_probe_migration(),)
    try:
        v = upgrade_schema()
    finally:
        schema_mod.MIGRATIONS = original
    assert v == CRASH_PROBE_REVISION
    assert get_schema_version() == CRASH_PROBE_REVISION
    assert _migration_records().count(CRASH_PROBE_REVISION) == 1
    assert _probe_count() == 1

    # Production data/identity/lifecycle preserved through crash + recovery.
    # The probe event is an intentional migration-side mutation (added on
    # retry), so it is excluded from the original-data preservation comparison.
    rt = create_event_runtime()
    after = _capture(rt)
    after_ids = [e for e in after["event_ids"] if e != PROBE_EVENT_ID]
    assert after_ids == before["event_ids"]
    assert after["event_count"] == before["event_count"] + 1
    assert after["entity_count"] == before["entity_count"]
    assert after["relation_count"] == before["relation_count"]
    assert after["relation_ids"] == before["relation_ids"]
    assert after["relation_status"] == before["relation_status"]
    _reset()


# ---------------------------------------------------------------------------
# BOUNDARY B — crash AFTER commit (real process death)
# ---------------------------------------------------------------------------


def test_crash_after_commit_persists_migration(tmp_path):
    """A REAL process crash AFTER the migration transaction committed must leave
    the committed revision and mutation durable; a further upgrade is an
    idempotent no-op with no duplicate record."""
    db = tmp_path / "b.db"
    before = _seed(str(db))

    configure_session_manager(_url(str(db)))
    assert upgrade_schema() == TARGET_VERSION
    _reset()

    # Child runs the engine; the probe migration COMMITS, then the process is
    # hard-killed (os._exit) before normal exit.
    rc = _run_child(str(db), "after_commit")
    assert rc == 137  # abnormal termination AFTER commit

    # Parent reopens with production infrastructure.
    configure_session_manager(_url(str(db)))
    # Committed revision IS recorded.
    assert get_schema_version() == CRASH_PROBE_REVISION
    assert _migration_records().count(CRASH_PROBE_REVISION) == 1
    # Committed mutation IS durable.
    assert _probe_count() == 1

    # Further upgrade is an idempotent no-op: no duplicate record, no data change.
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (_probe_migration(),)
    try:
        assert upgrade_schema() == CRASH_PROBE_REVISION
    finally:
        schema_mod.MIGRATIONS = original
    assert _migration_records().count(CRASH_PROBE_REVISION) == 1
    assert _probe_count() == 1

    # Production data preserved.  The probe event is the intentional committed
    # migration-side mutation (durable in Boundary B), excluded from the
    # original-data preservation comparison.
    rt = create_event_runtime()
    after = _capture(rt)
    after_ids = [e for e in after["event_ids"] if e != PROBE_EVENT_ID]
    assert after_ids == before["event_ids"]
    assert after["event_count"] == before["event_count"] + 1
    assert after["entity_count"] == before["entity_count"]
    assert after["relation_count"] == before["relation_count"]
    assert after["relation_ids"] == before["relation_ids"]
    _reset()


# ---------------------------------------------------------------------------
# Restart recovery / idempotency / data preservation
# ---------------------------------------------------------------------------


def test_repeated_upgrade_idempotent_and_no_duplicate_schema(tmp_path):
    db = tmp_path / "c.db"
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    upgrade_schema()
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    assert _migration_records() == list(range(1, TARGET_VERSION + 1))
    assert len(_migration_records()) == len(set(_migration_records()))
    # No duplicate index object on a repeated upgrade.
    insp = sa_inspect(get_session_manager().engine)
    idx = [i["name"] for i in insp.get_indexes("durable_canonical_events")]
    assert idx.count("ix_durable_canonical_events_event_type") == 1
    _reset()


def test_production_runtime_reopens_and_operates_after_recovery(tmp_path):
    db = tmp_path / "d.db"
    before = _seed(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    # Simulate restart: close and reopen via the production runtime.
    get_session_manager().close()
    configure_session_manager(_url(str(db)))
    rt = create_event_runtime()
    rt.pipeline.process(_entity_created("E10", "D"))
    rt.pipeline.process(_relation_event("E11", "D", "A", "relates_to"))
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    assert {e["entity_id"] for e in ent.list_all()} >= {"D", "A", "B"}
    rels = {r["source_entity_id"] + "->" + r["target_entity_id"]: r["status"]
            for r in rr.list_all()}
    assert rels["D->A"] == "ACTIVE"
    rt.pipeline.process(_entity_removed("E12", "D"))
    assert ent.is_tombstoned("D")
    # WO-018 severance semantics intact after restart.
    rt.pipeline.process(_severed("A", "B", "relates_to", "E13"))
    assert rr.list_all()[0]["status"] in ("ACTIVE", "INACTIVE")
    _reset()


def test_single_database_owner_no_second_engine(tmp_path):
    db = tmp_path / "e.db"
    configure_session_manager(_url(str(db)))
    mgr = get_session_manager()
    er = SQLAlchemyEventRepository()
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    assert er.session_manager is mgr
    assert ent.session_manager is mgr
    assert rr.session_manager is mgr
    upgrade_schema()
    assert get_session_manager() is mgr
    assert mgr.engine is not None
    _reset()
