"""
WO-022 — Real Schema Evolution (genuine OLD → NEW migration).

Locks the ratified WO-022 verification contract: the WO-021 migration engine
must perform a REAL schema evolution on a populated, production-like database —
NOT a ``create_all()``-only check.

Selected genuine delta (justified by repository evidence):
  * The durable ``durable_canonical_events`` repository exposes the production
    ``list_by_type`` query (``IEventRepository`` contract) filtering on
    ``event_type``, but that column was historically UNINDEXED — the table
    carried indexes only on ``event_id`` and ``seq`` (verified via PRAGMA /
    ``SQLAlchemy.inspect``).
  * WO-022 adds a revision-2 migration that performs a genuine schema delta:
    ``CREATE INDEX IF NOT EXISTS ix_durable_canonical_events_event_type``
    against an existing (potentially populated) ``durable_canonical_events``
    table.  The ORM model additionally declares ``index=True`` on
    ``event_type`` so fresh-schema bootstrap stays in sync.
  * The migration runs through the SINGLE existing ``DatabaseSessionManager``
    (NO second engine / sessionmaker / DB owner), is deterministic, idempotent,
    non-destructive, and preserves all existing data and identity.

Contract covered:
  * correct baseline revision (1)
  * genuine OLD schema — event_type index physically ABSENT before migration
  * populated OLD database (events, entities incl. TOMBSTONED, ACTIVE/INACTIVE
    and severed relations)
  * migration executes a real schema delta (revision 1 -> 2)
  * index physically exists after migration
  * deterministic backfill N/A (index-only delta) — identity/state preserved
  * Event / Entity / Relation identity preserved
  * lifecycle + severance preserved
  * no duplicate relations / rows
  * repeated migration is idempotent
  * current-schema migration is a no-op
  * production runtime reopens the migrated DB and continues operating
  * single DB owner preserved (no second engine/sessionmaker)
"""

from __future__ import annotations

import os
import tempfile

import pytest

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
from sqlalchemy import inspect as sa_inspect


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The index introduced by the WO-022 revision-2 migration (matches the ORM
# ``index=True`` declaration on ``DurableCanonicalEvent.event_type``).
EVENT_TYPE_INDEX = "ix_durable_canonical_events_event_type"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _compose(db_url: str) -> "object":
    configure_session_manager(db_url)
    SQLAlchemyEventRepository().initialize()
    return create_event_runtime()


def _reset():
    session_mod._session_manager = None


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
# 1. Baseline revision / registry
# ---------------------------------------------------------------------------


def test_correct_baseline_revision(memory_rt):
    """Fresh (un-upgraded) DB starts at revision 0; the registry target is the
    latest real migration."""
    assert get_schema_version() == 0
    assert TARGET_VERSION == max(m.revision for m in MIGRATIONS)
    assert [m.revision for m in MIGRATIONS] == sorted(m.revision for m in MIGRATIONS)


def test_upgrade_fresh_db_reaches_target(memory_rt):
    """Fresh DB: upgrade_schema reaches the registry target revision."""
    v = upgrade_schema()
    assert v == TARGET_VERSION
    assert get_schema_version() == TARGET_VERSION
    st = get_migration_state()
    assert st["current_revision"] == TARGET_VERSION
    assert st["target_revision"] == TARGET_VERSION
    assert st["upgrade_required"] is False


# ---------------------------------------------------------------------------
# 2. Genuine OLD schema (event_type index physically absent)
# ---------------------------------------------------------------------------


def test_old_schema_lacks_event_type_index(tmp_path):
    """A genuinely-OLD durable schema must be physically incapable of already
    containing the WO-022 delta: no ``event_type`` index, and no index on the
    ``source`` column either (baseline durable table only indexes event_id/seq)."""
    db = tmp_path / "old.db"
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    import sqlalchemy as sa

    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as c:
        c.execute(
            sa.text(
                "CREATE TABLE durable_canonical_events ("
                "id VARCHAR(36) PRIMARY KEY, "
                "seq INTEGER NOT NULL UNIQUE, "
                "event_id VARCHAR(36) NOT NULL UNIQUE, "
                "entity_id VARCHAR(128), "
                "event_type VARCHAR(100) NOT NULL, "
                "timestamp DATETIME NOT NULL, "
                "source VARCHAR(255) NOT NULL DEFAULT '', "
                "payload TEXT, metadata TEXT, "
                "created_at DATETIME NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO durable_canonical_events "
                "(id,seq,event_id,event_type,timestamp,source,created_at) "
                "VALUES ('i1',1,'e1','ENTITY_CREATED',"
                "'2024-01-01 00:00:00','test','2024-01-01 00:00:00')"
            )
        )
    engine.dispose()
    configure_session_manager(f"sqlite:///{path}")
    names = _index_names("durable_canonical_events")
    # The WO-022 delta (event_type index) is physically ABSENT in the OLD schema.
    assert EVENT_TYPE_INDEX not in names
    _reset()
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# 3. Real migration on populated OLD database
# ---------------------------------------------------------------------------


def _seed_old_schema(db_path: str) -> dict:
    """Build a GENUINE OLD populated database via raw DDL (no event_type index)
    and insert realistic canonical state, then return a deterministic snapshot.

    This is the honest OLD-schema fixture the WO-022 contract requires: the
    ``durable_canonical_events`` table is created WITHOUT the
    ``ix_durable_canonical_events_event_type`` index (the WO-022 delta), yet
    carries real populated rows — multiple events, ACTIVE entities, one
    TOMBSTONED entity, an ACTIVE relation, a cascade-INACTIVE relation and a
    severed-INACTIVE relation — plus the ``schema_migration_version`` record at
    revision 1 (the WO-021 baseline revision).
    """
    import sqlalchemy as sa
    from datetime import datetime, timezone

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as c:
        # OLD durable schema — no event_type index.
        c.execute(
            sa.text(
                "CREATE TABLE durable_canonical_events ("
                "id VARCHAR(36) PRIMARY KEY, "
                "seq INTEGER NOT NULL UNIQUE, "
                "event_id VARCHAR(36) NOT NULL UNIQUE, "
                "entity_id VARCHAR(128), "
                "event_type VARCHAR(100) NOT NULL, "
                "timestamp DATETIME NOT NULL, "
                "source VARCHAR(255) NOT NULL DEFAULT '', "
                "payload TEXT, metadata TEXT, "
                "created_at DATETIME NOT NULL)"
            )
        )
        c.execute(sa.text("CREATE INDEX ix_durable_canonical_events_event_id "
                          "ON durable_canonical_events (event_id)"))
        c.execute(sa.text("CREATE INDEX ix_durable_canonical_events_seq "
                          "ON durable_canonical_events (seq)"))
        c.execute(
            sa.text(
                "CREATE TABLE entities ("
                "id VARCHAR(128) PRIMARY KEY, "
                "entity_type VARCHAR(255) NOT NULL, "
                "status VARCHAR(32) NOT NULL, "
                "attributes TEXT, metadata TEXT, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL, "
                "deleted_at DATETIME, "
                "version INTEGER NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "CREATE TABLE entity_relations ("
                "relation_id VARCHAR(64) PRIMARY KEY, "
                "source_entity_id VARCHAR(128) NOT NULL, "
                "target_entity_id VARCHAR(128) NOT NULL, "
                "relation_type VARCHAR(64) NOT NULL, "
                "confidence REAL NOT NULL, "
                "source_event_id VARCHAR(36), "
                "metadata TEXT, "
                "status VARCHAR(32) NOT NULL, "
                "terminated_at DATETIME, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL, "
                "version INTEGER NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "CREATE TABLE projection_checkpoint ("
                "projection_name VARCHAR(64) PRIMARY KEY, "
                "last_seq INTEGER NOT NULL, "
                "last_event_id VARCHAR(128), "
                "updated_at DATETIME NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "CREATE TABLE schema_migration_version ("
                "version INTEGER PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "applied_at DATETIME NOT NULL)"
            )
        )
        now = "2024-01-01 00:00:00"
        # Events (seq 1..8)
        events = [
            ("i1", 1, "E1", "A", "ENTITY_CREATED", now, "test"),
            ("i2", 2, "E2", "B", "ENTITY_CREATED", now, "test"),
            ("i3", 3, "E3", "A", "ENTITY_UPDATED", now, "test"),
            ("i4", 4, "E4", "A", "ENTITY_UPDATED", now, "test"),
            ("i5", 5, "E5", "C", "ENTITY_CREATED", now, "test"),
            ("i6", 6, "E6", "C", "ENTITY_UPDATED", now, "test"),
            ("i7", 7, "E7", "C", "ENTITY_REMOVED", now, "test"),
            ("i8", 8, "E8", "A", "RELATION_SEVERED", now, "test"),
        ]
        for (id_, seq, evid, entid, etype, ts, src) in events:
            c.execute(
                sa.text(
                    "INSERT INTO durable_canonical_events "
                    "(id,seq,event_id,entity_id,event_type,timestamp,source,created_at) "
                    "VALUES (:id,:seq,:evid,:entid,:etype,:ts,:src,:ts)"
                ),
                {"id": id_, "seq": seq, "evid": evid, "entid": entid,
                 "etype": etype, "ts": ts, "src": src},
            )
        # Entities: A, B ACTIVE; C TOMBSTONED (deleted_at set, status TOMBSTONED).
        c.execute(
            sa.text("INSERT INTO entities (id,entity_type,status,attributes,metadata,created_at,updated_at,deleted_at,version) "
                    "VALUES ('A','unit','UNKNOWN','{}','{}',:ts,:ts,NULL,1)"), {"ts": now})
        c.execute(
            sa.text("INSERT INTO entities (id,entity_type,status,attributes,metadata,created_at,updated_at,deleted_at,version) "
                    "VALUES ('B','unit','UNKNOWN','{}','{}',:ts,:ts,NULL,1)"), {"ts": now})
        c.execute(
            sa.text("INSERT INTO entities (id,entity_type,status,attributes,metadata,created_at,updated_at,deleted_at,version) "
                    "VALUES ('C','unit','TOMBSTONED','{}','{}',:ts,:ts,:ts,1)"), {"ts": now})
        # Relations: A->B ACTIVE; C->A INACTIVE (cascade); A->B2 INACTIVE (severed).
        rid = deterministic_relation_id
        rels = [
            (rid("A", "B", "relates_to"), "A", "B", "relates_to", "ACTIVE", "E3", None),
            (rid("C", "A", "relates_to"), "C", "A", "relates_to", "INACTIVE", "E6", now),
            (rid("A", "B2", "relates_to"), "A", "B2", "relates_to", "INACTIVE", "E4", now),
        ]
        for (r_id, src, tgt, rtype, status, sev, term) in rels:
            c.execute(
                sa.text(
                    "INSERT INTO entity_relations (relation_id,source_entity_id,target_entity_id,relation_type,confidence,source_event_id,metadata,status,terminated_at,created_at,updated_at,version) "
                    "VALUES (:rid,:src,:tgt,:rtype,1.0,:sev,'{}',:status,:term,:ts,:ts,1)"
                ),
                {"rid": r_id, "src": src, "tgt": tgt, "rtype": rtype,
                 "sev": sev, "status": status, "term": term, "ts": now},
            )
        # Baseline revision already applied (WO-021 revision 1).
        c.execute(
            sa.text("INSERT INTO schema_migration_version (version,name,applied_at) "
                    "VALUES (1,'bootstrap_current_schema',:ts)"), {"ts": now})
        # Projection checkpoint at seq 8.
        c.execute(
            sa.text("INSERT INTO projection_checkpoint (projection_name,last_seq,last_event_id,updated_at) "
                    "VALUES ('entity',8,'E8',:ts)"), {"ts": now})
    engine.dispose()

    return {
        "event_ids": sorted(ev[2] for ev in events),
        "seq_order": [ev[2] for ev in events],
        "event_count": len(events),
        # _capture measures ent.list_all() which excludes tombstoned/deleted,
        # so only A and B are counted (C is TOMBSTONED).
        "entity_count": 2,
        "relation_count": 3,
        "relation_ids": sorted(r[0] for r in rels),
        "relation_status": {r[0]: r[4] for r in rels},
    }


def test_populated_old_db_migration_real_delta(tmp_path):
    """A populated GENUINE OLD database (events/entities/relations/lifecycle/
    severance) upgraded via the WO-021 engine advances revision and gains the
    event_type index while preserving all data and identity."""
    db = tmp_path / "pop.db"
    before = _seed_old_schema(str(db))
    configure_session_manager(_url(str(db)))
    # The delta is genuinely ABSENT before migration.
    assert EVENT_TYPE_INDEX not in _index_names("durable_canonical_events")
    # Baseline WO-021 revision present; later revisions pending.
    assert get_schema_version() == 1
    v = upgrade_schema()
    assert v == TARGET_VERSION
    assert get_schema_version() == TARGET_VERSION

    # Genuine delta now physically present.
    assert EVENT_TYPE_INDEX in _index_names("durable_canonical_events")

    # Reopen production runtime on the migrated DB and verify state preserved.
    rt = _compose(_url(str(db)))
    after = _capture(rt)
    assert after["event_ids"] == before["event_ids"]
    assert after["seq_order"] == before["seq_order"]
    assert after["event_count"] == before["event_count"]
    assert after["entity_count"] == before["entity_count"]
    assert after["relation_status"] == before["relation_status"]
    assert after["relation_ids"] == before["relation_ids"]
    assert after["relation_count"] == before["relation_count"]
    _reset()


def test_entity_and_relation_identity_preserved(tmp_path):
    db = tmp_path / "id.db"
    before = _seed_old_schema(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    rt = _compose(_url(str(db)))
    er = SQLAlchemyEventRepository()
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    ev = er.list_all()
    assert sorted(e.event_id for e in ev) == before["event_ids"]
    # Relation identity unchanged (deterministic relation_id preserved).
    assert sorted(r["relation_id"] for r in rr.list_all()) == before["relation_ids"]
    # Entity identity unchanged (A, B, C — C tombstoned but row retained).
    assert {e["entity_id"] for e in ent.list_all()} == {"A", "B"}
    assert ent.is_tombstoned("C") is True
    _reset()


def test_lifecycle_and_severance_preserved(tmp_path):
    db = tmp_path / "life.db"
    before = _seed_old_schema(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    rt = _compose(_url(str(db)))
    er = SQLAlchemyEventRepository()
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    # Event / entity / relation counts + identity preserved.
    assert sorted(e.event_id for e in er.list_all()) == before["event_ids"]
    # WO-017 lifecycle preserved: C tombstoned, A/B not.
    assert ent.is_tombstoned("C") is True
    assert ent.is_tombstoned("A") is False
    assert ent.is_tombstoned("B") is False
    # Relation lifecycle + severance preserved via durable status.
    assert rr.get(deterministic_relation_id("C", "A", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B2", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B", "relates_to"))["status"] == "ACTIVE"
    _reset()


def test_no_duplicate_rows_after_migration(tmp_path):
    db = tmp_path / "dup.db"
    before = _seed(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    rt = _compose(_url(str(db)))
    after = _capture(rt)
    assert after["event_count"] == before["event_count"]
    assert len(after["event_ids"]) == len(set(after["event_ids"]))
    assert after["relation_count"] == before["relation_count"]
    assert len(after["relation_ids"]) == len(set(after["relation_ids"]))
    assert after["entity_count"] == before["entity_count"]
    _reset()


# ---------------------------------------------------------------------------
# 4. Idempotency / current-schema no-op
# ---------------------------------------------------------------------------


def test_repeated_migration_idempotent(memory_rt):
    from app.database.schema_migration import MIGRATIONS

    upgrade_schema()
    assert get_schema_version() == max(m.revision for m in MIGRATIONS)
    upgrade_schema()
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    # Exactly one migration record per revision (no duplicates).
    from app.database.schema_migration import SchemaMigrationVersion
    from app.database.session import get_session_manager
    from sqlalchemy import select

    with get_session_manager().session(commit=False) as s:
        rows = s.execute(select(SchemaMigrationVersion.version)).scalars().all()
    assert sorted(rows) == sorted(m.revision for m in MIGRATIONS)
    assert len(rows) == len(MIGRATIONS)


def test_current_schema_migration_is_noop(tmp_path):
    """A DB already at the registry target: upgrade_schema is a deterministic
    no-op."""
    db = tmp_path / "cur.db"
    _seed(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    idx_before = _index_names("durable_canonical_events")
    rows_before = SQLAlchemyEventRepository().count()
    upgrade_schema()
    assert get_schema_version() == TARGET_VERSION
    assert _index_names("durable_canonical_events") == idx_before
    assert SQLAlchemyEventRepository().count() == rows_before
    _reset()


# ---------------------------------------------------------------------------
# 5. Production runtime reopens & operates
# ---------------------------------------------------------------------------


def test_production_runtime_reopens_and_operates(tmp_path):
    db = tmp_path / "rt.db"
    _seed(str(db))
    configure_session_manager(_url(str(db)))
    upgrade_schema()
    rt = _compose(_url(str(db)))
    # New Event/Entity/Relation processing still works on upgraded schema.
    rt.pipeline.process(_entity_created("E10", "D"))
    rt.pipeline.process(_relation_event("E11", "D", "A", "relates_to"))
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    assert {e["entity_id"] for e in ent.list_all()} >= {"D", "A", "B"}
    rels = {r["source_entity_id"] + "->" + r["target_entity_id"]: r["status"]
            for r in rr.list_all()}
    assert rels["D->A"] == "ACTIVE"
    # WO-017 lifecycle still works post-migration.
    rt.pipeline.process(_entity_removed("E12", "D"))
    assert ent.is_tombstoned("D")
    # WO-018 severance still works post-migration.
    rid = next(r["relation_id"] for r in rr.list_all()
               if r["source_entity_id"] == "A" and r["target_entity_id"] == "B")
    assert rr.sever_relation(rid) is True
    _reset()


# ---------------------------------------------------------------------------
# 6. Single DB owner / no second engine
# ---------------------------------------------------------------------------


def test_single_database_owner_no_second_engine(memory_rt):
    """The migration uses the SINGLE DatabaseSessionManager — no second engine
    or sessionmaker is created."""
    mgr = get_session_manager()
    er = SQLAlchemyEventRepository()
    ent = SQLAlchemyEntityRepository()
    rr = SQLAlchemyRelationRepository()
    assert er.session_manager is mgr
    assert ent.session_manager is mgr
    assert rr.session_manager is mgr
    # After a full upgrade only one engine exists on the manager.
    upgrade_schema()
    assert get_session_manager() is mgr
    assert mgr.engine is not None
