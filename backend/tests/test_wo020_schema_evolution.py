"""
WO-020 — Populated-Database Schema Evolution / Upgrade Safety.

Locks the ratified WO-020 verification contract:

  * The current production schema is fully additive and is brought up with
    ``Base.metadata.create_all(bind=engine)`` under the single
    ``DatabaseSessionManager`` (no second engine / sessionmaker / owner).
  * ``create_all`` is non-destructive for existing tables: it does not alter,
    drop, or rewrite tables that already exist.
  * Therefore a POPULATED database (one already holding durable canonical
    events, entities, relations, lifecycle state and severed-relation state)
    can be safely REOPENED by the current production runtime and continue
    operating: no data loss, no duplication, no identity / lifecycle /
    severance corruption, no replay incompatibility.
  * A FRESH database is also fully supported: the same schema initializes a
    brand-new database and processes canonical events correctly.
  * Repeated schema initialization (create_all) is idempotent — it does not
    duplicate rows, indexes, or constraints.

Architectural posture: WO-020 is a verification-gate WO.  The existing
production architecture already satisfies the populated-DB upgrade safety
contract (additive ``create_all`` under a single DB owner; an Alembic
``MigrationManager`` scaffolding exists but is NOT wired into production and
has no migration scripts / alembic.ini, so it is not the active mechanism).
Therefore this suite is tests-only.  NO production code is modified, and NO
migration framework is introduced or wired.
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    deterministic_relation_id,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from sqlalchemy import inspect as sa_inspect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    """Turn a raw filesystem path into a SQLAlchemy sqlite:/// URL."""
    return f"sqlite:///{db_path}"


def _compose(db_url: str) -> "object":
    """Compose a production runtime against the given URL (fresh or an
    already-populated file DB).  A new DatabaseSessionManager engine is created
    for the URL; on a file DB this genuinely reopens the same file."""
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
    """Capture the full durable projected state from the runtime's own
    production-wired repositories."""
    er = SQLAlchemyEventRepository()
    rr = rt.relation_repository
    ent = rt.entity_repository
    events = er.list_all()  # seq-ordered
    return {
        "event_ids": sorted(e.event_id for e in events),
        "seq_order": [e.event_id for e in events],
        "event_count": len(events),
        "entity_status": {
            str(e["entity_id"]): e["status"] for e in ent.list_all()
        },
        "entity_count": len(ent.list_all()),
        "relation_status": {r["relation_id"]: r["status"] for r in rr.list_all()},
        "relation_ids": sorted(r["relation_id"] for r in rr.list_all()),
        "relation_count": len(rr.list_all()),
    }


def _seed(db_path: str) -> dict:
    """Populate a file DB with realistic canonical state, close it, and return
    the durable-state fingerprint to compare after reopen.

    State created:
      * Entities A, B (ACTIVE); C created then ENTITY_REMOVED -> TOMBSTONED.
      * Relations A->B (ACTIVE), C->A (INACTIVE via cascade).
      * Relation A->B2 (ACTIVE) then RELATION_SEVERED -> INACTIVE (targeted).
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


def _reopen(db_path: str) -> dict:
    """Reopen the same file DB with a brand-new runtime/engine and return the
    durable-state fingerprint."""
    rt = _compose(_url(db_path))
    fp = _capture(rt)
    _reset()
    return fp


@pytest.fixture()
def memory_rt():
    rt = _compose("sqlite:///:memory:")
    yield rt
    _reset()


# ---------------------------------------------------------------------------
# 1-4. Schema presence / fresh database
# ---------------------------------------------------------------------------


def test_fresh_db_creates_required_tables(memory_rt):
    insp = sa_inspect(memory_rt.entity_repository.session_manager.engine)
    tables = set(insp.get_table_names())
    for required in (
        "durable_canonical_events",
        "entities",
        "entity_relations",
        "projection_checkpoint",
    ):
        assert required in tables, f"missing table {required}"


def test_fresh_db_required_columns_exist(memory_rt):
    mgr = memory_rt.entity_repository.session_manager
    insp = sa_inspect(mgr.engine)
    event_cols = {c["name"] for c in insp.get_columns("durable_canonical_events")}
    assert {"event_id", "seq", "event_type", "source"}.issubset(event_cols)
    rel_cols = {c["name"] for c in insp.get_columns("entity_relations")}
    assert {"relation_id", "source_entity_id", "target_entity_id",
            "relation_type", "status", "source_event_id"}.issubset(rel_cols)
    ent_cols = {c["name"] for c in insp.get_columns("entities")}
    assert {"id", "status"}.issubset(ent_cols)


def test_fresh_db_unique_constraints_and_indexes(memory_rt):
    mgr = memory_rt.entity_repository.session_manager
    insp = sa_inspect(mgr.engine)
    unique_cols = set()
    for ix in insp.get_indexes("durable_canonical_events"):
        if ix.get("unique"):
            unique_cols.update(ix["column_names"])
    assert "event_id" in unique_cols
    assert "seq" in unique_cols
    pk = set(insp.get_pk_constraint("entity_relations")["constrained_columns"])
    assert "relation_id" in pk


def test_fresh_db_production_runtime_opens_and_processes(memory_rt):
    rt = memory_rt
    rt.pipeline.process(_entity_created("F1", "A"))
    rt.pipeline.process(_relation_event("F2", "A", "B", "relates_to"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    assert str(ent.get("A")["entity_id"]) == "A"
    assert rr.get(deterministic_relation_id("A", "B", "relates_to"))["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# 5+. Populated database reopen safety
# ---------------------------------------------------------------------------


def test_populated_db_reopen_preserves_all_state(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    fp1 = _seed(db)
    fp2 = _reopen(db)
    assert fp1["event_ids"] == fp2["event_ids"]
    assert fp1["entity_status"] == fp2["entity_status"]
    assert fp1["relation_status"] == fp2["relation_status"]
    assert fp1["relation_ids"] == fp2["relation_ids"]
    assert fp1["event_count"] == fp2["event_count"]
    assert fp1["entity_count"] == fp2["entity_count"]
    assert fp1["relation_count"] == fp2["relation_count"]
    assert fp1["seq_order"] == fp2["seq_order"]


def test_populated_db_reopen_identity_and_seq_preserved(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    fp1 = _seed(db)
    fp2 = _reopen(db)
    assert fp1["event_ids"] == fp2["event_ids"]
    assert fp1["relation_ids"] == fp2["relation_ids"]
    assert fp1["seq_order"] == fp2["seq_order"]


def test_populated_db_reopen_lifecycle_and_severance_preserved(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    _seed(db)
    # The durable TOMBSTONED entity row is preserved across reopen (excluded
    # from active reads, but durably present and reconstructable).
    rt = _compose(_url(db))
    assert rt.entity_repository.is_tombstoned("C") is True
    assert rt.entity_repository.is_tombstoned("A") is False
    # Relation lifecycle + severance state preserved.
    rr = rt.relation_repository
    assert rr.get(deterministic_relation_id("C", "A", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B2", "relates_to"))["status"] == "INACTIVE"
    assert rr.get(deterministic_relation_id("A", "B", "relates_to"))["status"] == "ACTIVE"
    _reset()


def test_populated_db_reopen_then_continue_operating(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    _seed(db)
    rt = _compose(_url(db))
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


def test_populated_db_reopen_no_duplicate_rows(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    fp1 = _seed(db)
    fp2 = _reopen(db)
    # No duplication on reopen: counts identical before/after.
    assert fp1["event_count"] == fp2["event_count"] == 8
    assert fp1["relation_count"] == fp2["relation_count"] == 3
    assert fp1["entity_count"] == fp2["entity_count"] == 2  # A, B active; C tombstoned (excluded from active reads)


def test_repeated_create_all_is_idempotent(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    _seed(db)
    # Re-initialize schema repeatedly on the same populated DB.
    for _ in range(3):
        rt = _compose(_url(db))
        _reset()
    fp = _reopen(db)
    assert fp["event_count"] == 8
    assert fp["relation_count"] == 3
    assert fp["entity_count"] == 2  # A, B active; C tombstoned (durable, excluded from active reads)


def test_populated_db_reopen_continued_replay_compatible(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    _seed(db)
    rt = _compose(_url(db))
    rt.pipeline.process(_entity_created("R1", "Z"))
    rt.pipeline.process(_relation_event("R2", "Z", "A", "relates_to"))
    rt.pipeline.process(_entity_removed("R3", "Z"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    assert ent.is_tombstoned("Z") is True
    assert rr.get(deterministic_relation_id("Z", "A", "relates_to"))["status"] == "INACTIVE"
    # Reprocessing a duplicate after reopen is a safe idempotent no-op.
    rt.pipeline.process(_entity_removed("R3", "Z"))
    assert len(rr.list_all()) == 4
    _reset()


def test_reopen_is_idempotent_processing(tmp_path):
    db = str(tmp_path / "wo020.sqlite")
    _seed(db)
    rt = _compose(_url(db))
    # Reprocess ENTITY_REMOVED for an already-tombstoned entity: no-op.
    rt.pipeline.process(_entity_removed("E7", "C"))
    ent = rt.entity_repository
    rr = rt.relation_repository
    assert ent.is_tombstoned("C") is True
    assert len(rr.list_all()) == 3
    _reset()
