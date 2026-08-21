"""
WO-021 — Schema Migration Infrastructure.

Locks the ratified WO-021 verification contract:

  * A single authoritative schema revision is durably tracked in the
    ``schema_migration_version`` table (``version``, ``applied_at``).
  * Migrations live in an explicitly-ordered, deterministic registry
    (ascending revision).  Ordering never depends on filesystem layout,
    dictionary iteration, timestamps, or random ids.
  * ``upgrade_schema`` applies only missing migrations in ascending order and
    records each revision only after its operation succeeds.
  * Repeated ``upgrade_schema`` is idempotent: no duplicate migration records,
    no duplicate schema objects, no data duplication.
  * Migration state is inspectable via ``get_schema_version`` /
    ``get_migration_state``.
  * The mechanism operates through the single existing database owner —
    ``DatabaseSessionManager`` — with NO second engine / sessionmaker /
    connection manager / DB lifecycle (INVARIANT: exactly one owner).
  * A failed migration is NOT falsely recorded as successful; retry recovers
    deterministically.
  * Populated databases (events, entities, relations, lifecycle, severance)
    survive upgrade untouched.
  * The production runtime can reopen the upgraded database and continue
    normal Event/Entity/Relation processing.

WO-021 is infrastructure-only.  No semantic change to Event, EventType,
Entity, Relation, ENTITY_REMOVED, RELATION_SEVERED, replay, deterministic
``relation_id``, lifecycle, or projection behaviour.
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.schema_migration import (
    MIGRATIONS,
    TARGET_VERSION,
    SchemaMigrationVersion,
    get_migration_state,
    get_schema_version,
    upgrade_schema,
)
from app.database.session import configure_session_manager, get_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    deterministic_relation_id,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _compose(db_url: str) -> "object":
    """Configure a fresh single-owner session manager and compose a production
    runtime against the URL (fresh or already-populated file DB)."""
    configure_session_manager(db_url)
    SQLAlchemyEventRepository().initialize()
    return create_event_runtime()


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
        payload={
            "target_entity_id": target,
            "relation_type": rel_type,
            "confidence": 1.0,
        },
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
        payload={
            "source_entity_id": source,
            "target_entity_id": target,
            "relation_type": rel_type,
        },
    )


def _capture(rt: "object") -> dict:
    er = SQLAlchemyEventRepository()
    rr = rt.relation_repository
    ent = rt.entity_repository
    events = er.list_all()
    return {
        "event_ids": sorted(e.event_id for e in events),
        "seq_order": [e.event_id for e in events],
        "event_count": len(events),
        "entity_status": {str(e["entity_id"]): e["status"] for e in ent.list_all()},
        "entity_count": len(ent.list_all()),
        "relation_status": {r["relation_id"]: r["status"] for r in rr.list_all()},
        "relation_ids": sorted(r["relation_id"] for r in rr.list_all()),
        "relation_count": len(rr.list_all()),
    }


def _seed(db_path: str) -> dict:
    """Populate a file DB with realistic canonical state and close it.

    Entities A, B ACTIVE; C created then ENTITY_REMOVED -> TOMBSTONED;
    Relations A->B ACTIVE, C->A INACTIVE (cascade), A->B2 then SEVERED INACTIVE.
    """
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


@pytest.fixture()
def memory_rt():
    rt = _compose("sqlite:///:memory:")
    yield rt
    _reset()


# ---------------------------------------------------------------------------
# 1-3. Version identity / inspection
# ---------------------------------------------------------------------------


def test_migration_version_table_exists(memory_rt):
    mgr = get_session_manager()
    insp = sa_inspect(mgr.engine)
    assert "schema_migration_version" in set(insp.get_table_names())


def test_initial_version_is_deterministic(memory_rt):
    upgrade_schema()
    assert get_schema_version() == 1
    assert TARGET_VERSION == 1


def test_migration_state_inspectable(memory_rt):
    upgrade_schema()
    state = get_migration_state()
    assert state["current_revision"] == 1
    assert state["target_revision"] == TARGET_VERSION
    assert state["upgrade_required"] is False


def test_migration_registry_is_deterministically_ordered():
    revs = [m.revision for m in MIGRATIONS]
    assert revs == sorted(revs)
    assert revs == sorted(set(revs)), "migration revisions must be unique"
    assert revs[0] == 1


# ---------------------------------------------------------------------------
# 4-8. Ordered execution + idempotency
# ---------------------------------------------------------------------------


def test_upgrade_applies_missing_migrations_in_order(memory_rt):
    # Fresh DB starts at version 0; upgrade applies all missing in order.
    assert get_schema_version() == 0
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    # No duplicate migration records.
    mgr = get_session_manager()
    with mgr.session(commit=False) as session:
        rows = session.execute(
            __import__("sqlalchemy").select(SchemaMigrationVersion.version)
        ).scalars().all()
    assert sorted(rows) == [1]


def test_repeated_upgrade_is_idempotent_noop(memory_rt):
    upgrade_schema()
    mgr = get_session_manager()
    with mgr.session(commit=False) as session:
        before = session.execute(
            __import__("sqlalchemy").select(SchemaMigrationVersion.version)
        ).scalars().all()
    # Run again twice.
    upgrade_schema()
    upgrade_schema()
    with mgr.session(commit=False) as session:
        after = session.execute(
            __import__("sqlalchemy").select(SchemaMigrationVersion.version)
        ).scalars().all()
    assert before == after == [1]
    assert get_schema_version() == 1


def test_upgrade_does_not_duplicate_schema_objects(memory_rt):
    upgrade_schema()
    insp = sa_inspect(get_session_manager().engine)
    tables_before = set(insp.get_table_names())
    upgrade_schema()
    upgrade_schema()
    insp2 = sa_inspect(get_session_manager().engine)
    tables_after = set(insp2.get_table_names())
    assert tables_before == tables_after
    # No duplicate durable schema objects.
    assert tables_before == {
        "schema_migration_version",
        "durable_canonical_events",
        "entities",
        "entity_relations",
        "projection_checkpoint",
        "observations",
    }


# ---------------------------------------------------------------------------
# Ownership — single DatabaseSessionManager, no second engine/sessionmaker
# ---------------------------------------------------------------------------


def test_single_database_owner_no_second_engine(memory_rt):
    upgrade_schema()
    # The mechanism resolves to the global single owner.
    mgr = get_session_manager()
    assert isinstance(mgr.engine, Engine)
    assert isinstance(mgr.session_factory, sessionmaker)
    # Repositories and migration all use the same manager.
    from app.database.schema_migration import get_schema_version as _gsv

    er = SQLAlchemyEventRepository()
    assert er.session_manager is mgr
    # Confirm the manager identity is singular and shared.
    assert er.session_manager is get_session_manager()


def test_migration_uses_existing_database_owner(memory_rt):
    mgr_before = get_session_manager()
    # Upgrading through the manager produces the version table on its engine.
    upgrade_schema(session_manager=mgr_before)
    insp = sa_inspect(mgr_before.engine)
    assert "schema_migration_version" in set(insp.get_table_names())
    # No new engine/sessionmaker were created.
    assert get_session_manager() is mgr_before


# ---------------------------------------------------------------------------
# 9-14. Populated database survives upgrade
# ---------------------------------------------------------------------------


def test_populated_db_upgrade_preserves_all_state(tmp_path):
    db = str(tmp_path / "wo021.sqlite")
    fp1 = _seed(db)
    # Reopen + upgrade on the populated DB.
    _compose(_url(db))
    upgrade_schema()
    fp2 = _capture(create_event_runtime())
    _reset()
    assert fp1["event_ids"] == fp2["event_ids"]
    assert fp1["entity_status"] == fp2["entity_status"]
    assert fp1["relation_status"] == fp2["relation_status"]
    assert fp1["relation_ids"] == fp2["relation_ids"]
    assert fp1["event_count"] == fp2["event_count"] == 8
    assert fp1["relation_count"] == fp2["relation_count"] == 3
    assert fp1["seq_order"] == fp2["seq_order"]


def test_populated_db_upgrade_preserves_identity(tmp_path):
    db = str(tmp_path / "wo021.sqlite")
    fp1 = _seed(db)
    _compose(_url(db))
    upgrade_schema()
    fp2 = _capture(create_event_runtime())
    _reset()
    assert fp1["event_ids"] == fp2["event_ids"]
    assert fp1["relation_ids"] == fp2["relation_ids"]
    assert fp1["seq_order"] == fp2["seq_order"]


def test_populated_db_upgrade_preserves_lifecycle_and_severance(tmp_path):
    db = str(tmp_path / "wo021.sqlite")
    _seed(db)
    rt = _compose(_url(db))
    upgrade_schema()
    # Lifecycle (tombstone) state preserved.
    assert rt.entity_repository.is_tombstoned("C") is True
    assert rt.entity_repository.is_tombstoned("A") is False
    # Relation lifecycle + severance state preserved.
    rr = rt.relation_repository
    assert rr.get(deterministic_relation_id("C", "A", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B2", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B", "relates_to"))["status"] == "ACTIVE"
    _reset()


def test_populated_db_upgrade_then_continue_operating(tmp_path):
    db = str(tmp_path / "wo021.sqlite")
    _seed(db)
    rt = _compose(_url(db))
    upgrade_schema()
    rt.pipeline.process(_entity_created("NEW1", "D"))
    rt.pipeline.process(_relation_event("NEW2", "D", "A", "relates_to"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    er = SQLAlchemyEventRepository()
    assert str(ent.get("D")["entity_id"]) == "D"
    assert rr.get(deterministic_relation_id("D", "A", "relates_to"))["status"] == "ACTIVE"
    assert str(ent.get("A")["entity_id"]) == "A"  # old data preserved
    assert er.count() == 10  # 8 seeded + 2 new
    _reset()


# ---------------------------------------------------------------------------
# 15-16. Failure safety + deterministic retry
# ---------------------------------------------------------------------------


def test_failed_migration_not_recorded(memory_rt, monkeypatch):
    from app.database import schema_migration as sm

    def _boom(_manager):
        raise RuntimeError("simulated migration failure")

    # Inject a failing migration at revision 99 (never in the real registry).
    fake = sm.Migration(revision=99, name="boom", migrate=_boom)
    monkeypatch.setattr(sm, "MIGRATIONS", sm.MIGRATIONS + (fake,))
    monkeypatch.setattr(sm, "TARGET_VERSION", 99)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        upgrade_schema()

    # The failed revision must NOT be recorded; only revision 1 succeeded.
    assert get_schema_version() == 1
    mgr = get_session_manager()
    with mgr.session(commit=False) as session:
        rows = session.execute(
            __import__("sqlalchemy").select(SchemaMigrationVersion.version)
        ).scalars().all()
    assert rows == [1]


def test_failed_migration_can_retry_deterministically(memory_rt, monkeypatch):
    from app.database import schema_migration as sm

    calls = {"n": 0}

    def _flaky(_manager):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")

    fake = sm.Migration(revision=99, name="flaky", migrate=_flaky)
    monkeypatch.setattr(sm, "MIGRATIONS", sm.MIGRATIONS + (fake,))
    monkeypatch.setattr(sm, "TARGET_VERSION", 99)

    with pytest.raises(RuntimeError, match="transient failure"):
        upgrade_schema()
    assert get_schema_version() == 1

    # Retry completes deterministically and records the higher revision.
    upgrade_schema()
    assert get_schema_version() == 99
    mgr = get_session_manager()
    with mgr.session(commit=False) as session:
        rows = session.execute(
            __import__("sqlalchemy").select(SchemaMigrationVersion.version)
        ).scalars().all()
    assert rows == [1, 99]


# ---------------------------------------------------------------------------
# 19-20. Runtime reopen + normal processing
# ---------------------------------------------------------------------------


def test_production_runtime_reopens_upgraded_db(tmp_path):
    db = str(tmp_path / "wo021.sqlite")
    _seed(db)
    rt = _compose(_url(db))
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    # Normal processing still works.
    rt.pipeline.process(_entity_created("R1", "Z"))
    rt.pipeline.process(_relation_event("R2", "Z", "A", "relates_to"))
    rt.pipeline.process(_entity_removed("R3", "Z"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    assert ent.is_tombstoned("Z") is True
    assert rr.get(deterministic_relation_id("Z", "A", "relates_to"))["status"] == "INACTIVE"
    # Reprocessing duplicate is an idempotent no-op.
    rt.pipeline.process(_entity_removed("R3", "Z"))
    assert len(rr.list_all()) == 4
    _reset()


def test_fresh_db_upgrade_then_normal_processing(memory_rt):
    upgrade_schema()
    rt = memory_rt
    rt.pipeline.process(_entity_created("F1", "A"))
    rt.pipeline.process(_relation_event("F2", "A", "B", "relates_to"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    assert str(ent.get("A")["entity_id"]) == "A"
    assert rr.get(deterministic_relation_id("A", "B", "relates_to"))["status"] == "ACTIVE"
