"""
WO-023 — Migration Atomicity, Failure Rollback & Concurrency.

Locks the ratified WO-023 verification contract for the WO-021 schema-migration
engine:

  * A versioned migration executes atomically: the migration's schema/data
    operation and its revision record commit together in ONE transaction.
  * On failure, BOTH the schema/data mutation AND the revision record roll
    back — no partially-applied migration, no falsely-recorded revision.
  * Retry after a failed migration recovers deterministically: the database
    reopens at the OLD valid revision, re-running ``upgrade_schema`` succeeds,
    produces exactly one migration record, and a further run is a no-op.
  * Concurrent ``upgrade_schema`` attempts against the same (file) database
    converge to one valid target schema without duplicate migration records,
    duplicate schema objects, or corrupted rows — transient SQLite
    ``database is locked`` is handled deterministically (bounded retry), never
    suppressed.
  * The engine operates through the single existing ``DatabaseSessionManager``
    owner — NO second engine, NO second sessionmaker, NO second DB owner.
  * Migration registry invariants hold after success, failure, rollback,
    retry, repeated upgrade and concurrent upgrade.

Scope: migration-engine atomicity / recovery / concurrency only.  No change to
Event, EventType, Entity, Relation, lifecycle, severance, replay, deterministic
``relation_id``, or projection semantics.
"""

from __future__ import annotations

import os
import tempfile
import threading

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
    _FAIL_INJECT_REVISION,
    get_migration_state,
    get_schema_version,
    upgrade_schema,
)
from app.database.session import configure_session_manager, get_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
    deterministic_relation_id,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)

EVENT_TYPE_INDEX = "ix_durable_canonical_events_event_type"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _reset():
    session_mod._session_manager = None


def _compose(db_url: str) -> "object":
    configure_session_manager(db_url)
    SQLAlchemyEventRepository().initialize()
    return create_event_runtime()


def _index_names(table: str) -> list:
    insp = sa_inspect(get_session_manager().engine)
    return [i["name"] for i in insp.get_indexes(table)]


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


def _capture(rt: "object") -> dict:
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


def _seed(db_path: str) -> dict:
    """Populate a file DB with realistic canonical state and close it."""
    rt = _compose(_url(db_path))
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


# A real schema/data migration used for failure-injection.  It performs a
# genuine DML mutation — INSERTING a marker row into the existing durable
# ``durable_canonical_events`` table — INSIDE the active migration session, the
# same transaction that records the revision.  SQLite DML is transactional, so
# on rollback the inserted row is removed, proving atomic data rollback.
#
# (Note: raw SQLite DDL — CREATE TABLE / CREATE INDEX — is implicitly committed
# by SQLite and is NOT rollback-safe via the ORM session; the WO-021 revision-2
# index migration is therefore idempotent ``IF NOT EXISTS`` rather than relying
# on rollback.  This DML-based probe exercises the transactional path.)
def _migrate_creates_probe_data(manager, session) -> None:
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
            "id": "probe-row",
            "seq": 999001,
            "event_id": "probe-event",
            "entity_id": "probe-entity",
            "event_type": "ENTITY_CREATED",
            "ts": datetime.now(timezone.utc),
            "source": "wo023-probe",
            "payload": "{}",
            "metadata": "{}",
        },
    )


# A synthetic migration appended to the registry for atomicity/rollback tests.
PROBE_MIGRATION = schema_mod.Migration(
    revision=9999,
    name="wo023_probe_data",
    migrate=_migrate_creates_probe_data,
)


@pytest.fixture()
def memory_rt():
    rt = _compose("sqlite:///:memory:")
    yield rt
    _reset()


@pytest.fixture(autouse=True)
def _no_fail_inject():
    """Ensure failure injection is never left on between tests."""
    schema_mod._FAIL_INJECT_REVISION = None
    yield
    schema_mod._FAIL_INJECT_REVISION = None


# ---------------------------------------------------------------------------
# 1. Baseline / registry invariants
# ---------------------------------------------------------------------------


def test_registry_is_ordered_unique_deterministic(memory_rt):
    revisions = [m.revision for m in MIGRATIONS]
    assert revisions == sorted(revisions)
    assert len(set(revisions)) == len(revisions)
    assert TARGET_VERSION == max(revisions)


def test_fresh_db_starts_at_zero_and_upgrades_to_target(memory_rt):
    assert get_schema_version() == 0
    v = upgrade_schema()
    assert v == TARGET_VERSION
    assert get_schema_version() == TARGET_VERSION
    st = get_migration_state()
    assert st["current_revision"] == TARGET_VERSION
    assert st["upgrade_required"] is False


# ---------------------------------------------------------------------------
# 2. Atomicity — success
# ---------------------------------------------------------------------------


def test_successful_migration_commits_mutation_and_record_atomically(memory_rt):
    # Register a probe migration that performs a real mutation + record.
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (PROBE_MIGRATION,)
    try:
        v = upgrade_schema()
        assert v == 9999
        assert 9999 in _migration_records()
        mgr = get_session_manager()
        with mgr.session(commit=False) as s:
            rows = s.execute(
                sa.text("SELECT COUNT(*) FROM durable_canonical_events WHERE id = :i"),
                {"i": "probe-row"},
            ).scalar()
        assert rows == 1  # mutation committed alongside the record
    finally:
        schema_mod.MIGRATIONS = original
        schema_mod._FAIL_INJECT_REVISION = None


# ---------------------------------------------------------------------------
# 3. Atomicity — forced failure / rollback
# ---------------------------------------------------------------------------


def test_failed_migration_rolls_back_mutation_and_record(memory_rt):
    """A forced failure AFTER a real mutation but BEFORE the revision commit
    must roll back BOTH the mutation and the revision record — the database
    remains at the OLD valid revision with no partial schema/data."""
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (PROBE_MIGRATION,)
    schema_mod._FAIL_INJECT_REVISION = 9999  # raise after mutation, before record
    try:
        with pytest.raises(RuntimeError, match="WO-023 injected failure"):
            upgrade_schema()
    finally:
        schema_mod.MIGRATIONS = original
        schema_mod._FAIL_INJECT_REVISION = None

    # Revision NOT recorded — database is still at the pre-migration revision
    # (revision 2 = the WO-021/022 target; the probe rev 9999 is NOT applied).
    assert get_schema_version() == 2
    assert 9999 not in _migration_records()
    # Mutation rolled back: the probe DATA row is absent (DML is transactional).
    mgr = get_session_manager()
    with mgr.session(commit=False) as s:
        n = s.execute(
            sa.text("SELECT COUNT(*) FROM durable_canonical_events WHERE id = :i"),
            {"i": "probe-row"},
        ).scalar()
    assert n == 0


def test_failed_migration_preserves_prior_schema_and_data(tmp_path):
    """On a populated OLD database, a forced migration failure leaves the
    pre-existing schema, data, identities and lifecycle fully intact."""
    db = tmp_path / "fail.db"
    before = _seed(str(db))
    configure_session_manager(_url(str(db)))
    # Ensure the WO-022 baseline migration (rev 1 -> 2) is already applied.
    upgrade_schema()
    assert get_schema_version() == 2
    # Register a failing migration and inject failure after its real mutation.
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (PROBE_MIGRATION,)
    schema_mod._FAIL_INJECT_REVISION = 9999
    try:
        with pytest.raises(RuntimeError, match="WO-023 injected failure"):
            upgrade_schema()
    finally:
        schema_mod.MIGRATIONS = original
        schema_mod._FAIL_INJECT_REVISION = None

    # Old valid revision retained; no partial migration record; probe row absent.
    assert get_schema_version() == 2
    assert 9999 not in _migration_records()
    with get_session_manager().session(commit=False) as s:
        n = s.execute(
            sa.text("SELECT COUNT(*) FROM durable_canonical_events WHERE id = :i"),
            {"i": "probe-row"},
        ).scalar()
    assert n == 0

    # Production data/identity/lifecycle preserved through the failed migration.
    rt = _compose(_url(str(db)))
    after = _capture(rt)
    assert after["event_ids"] == before["event_ids"]
    assert after["event_count"] == before["event_count"]
    assert after["entity_count"] == before["entity_count"]
    assert after["relation_count"] == before["relation_count"]
    assert after["relation_ids"] == before["relation_ids"]
    assert after["relation_status"] == before["relation_status"]
    _reset()


# ---------------------------------------------------------------------------
# 4. Retry after failure
# ---------------------------------------------------------------------------


def test_retry_after_failure_recovers_deterministically(memory_rt):
    """After a forced failure, the DB reopens at the OLD revision; retrying
    succeeds, produces exactly one record, and a further run is idempotent."""
    original = schema_mod.MIGRATIONS
    schema_mod.MIGRATIONS = original + (PROBE_MIGRATION,)
    schema_mod._FAIL_INJECT_REVISION = 9999
    try:
        with pytest.raises(RuntimeError):
            upgrade_schema()
        # rev 1 and 2 applied; the failing probe rev 9999 is NOT recorded.
        assert get_schema_version() == 2
        assert 9999 not in _migration_records()

        # Retry — failure injection now disabled for this migration.
        schema_mod._FAIL_INJECT_REVISION = None
        v = upgrade_schema()
        assert v == 9999
        assert get_schema_version() == 9999
        assert _migration_records()[-1] == 9999
        # Exactly one record for revision 9999.
        assert _migration_records().count(9999) == 1

        # Idempotent third run.
        assert upgrade_schema() == 9999
        assert _migration_records().count(9999) == 1
    finally:
        schema_mod.MIGRATIONS = original
        schema_mod._FAIL_INJECT_REVISION = None


def test_repeated_upgrade_idempotent(memory_rt):
    upgrade_schema()
    upgrade_schema()
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    assert _migration_records() == list(range(1, TARGET_VERSION + 1))
    assert len(_migration_records()) == len(set(_migration_records()))


# ---------------------------------------------------------------------------
# 5. Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_upgrades_converge(tmp_path):
    """Concurrent upgrade_schema calls against the SAME file DB converge to the
    target revision with exactly one record per revision and no duplicate
    schema objects or corrupted data."""
    db = tmp_path / "conc.db"
    _seed(str(db))
    configure_session_manager(_url(str(db)))

    barrier = threading.Barrier(3)
    results = []
    errors = []

    def _worker():
        try:
            barrier.wait()
            v = upgrade_schema()
            results.append(v)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All callers converge to the target revision.
    assert all(v == TARGET_VERSION for v in results), results
    assert not errors, errors
    # Exactly one record per revision (no duplicates from races).
    assert _migration_records() == list(range(1, TARGET_VERSION + 1))
    # No duplicate schema object (index exists exactly once).
    assert _index_names("durable_canonical_events").count(EVENT_TYPE_INDEX) == 1
    # Data preserved.
    rt = _compose(_url(str(db)))
    after = _capture(rt)
    assert after["event_count"] >= 1
    assert len(after["event_ids"]) == len(set(after["event_ids"]))
    assert after["relation_count"] >= 1
    _reset()


# ---------------------------------------------------------------------------
# 6. Production runtime compatibility + single DB owner
# ---------------------------------------------------------------------------


def test_production_runtime_works_after_migration(tmp_path):
    db = tmp_path / "rt.db"
    _seed(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    rt = _compose(_url(str(db)))
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
    _reset()


def test_single_database_owner_no_second_engine(memory_rt):
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


def test_failure_injection_disabled_in_normal_operation():
    """The test-controlled failure hook is None by default (production)."""
    assert _FAIL_INJECT_REVISION is None
