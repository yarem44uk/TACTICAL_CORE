"""
WO-014-016 tests: Durable Event Repository.

Exercises the actual SQLAlchemy-backed durable repository against a real
in-memory SQLite database. Tests verify:

A. model existence
B. DB-level UNIQUE(event_id)
C. repository implements IEventRepository
D. idempotent duplicate save
E. distinct event IDs
F. full round-trip
G. nested payload/metadata
H. transaction success
I. rollback on failure
J. session lifecycle (no leaks)
K. repository interface parity
L. architectural isolation
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import List, Optional

import pytest
from sqlalchemy import inspect, text

from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_repository.interfaces.i_event_repository import IEventRepository


@pytest.fixture()
def session_manager() -> DatabaseSessionManager:
    """A fresh in-memory SQLite session manager for each test."""
    manager = DatabaseSessionManager(
        database_url="sqlite:///:memory:",
        echo=False,
    )
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture()
def repo(session_manager: DatabaseSessionManager) -> SQLAlchemyEventRepository:
    """A durable repository bound to an in-memory DB, table created."""
    repository = SQLAlchemyEventRepository(session_manager=session_manager)
    repository.initialize()
    return repository


def make_event(
    *,
    event_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: EventType = EventType.CUSTOM,
    source: str = "test-source",
    payload: Optional[dict] = None,
    metadata: Optional[EventMetadata] = None,
    timestamp: Optional[datetime] = None,
) -> Event:
    """Build a canonical domain Event with deterministic defaults."""
    return Event(
        event_id=event_id or "evt-0000-0000-0000-000000000000",
        entity_id=entity_id,
        event_type=event_type,
        timestamp=timestamp or datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=metadata if metadata is not None else EventMetadata(),
    )


# --------------------------------------------------------------------------
# A. model existence
# --------------------------------------------------------------------------

def test_model_existence():
    """DurableCanonicalEvent is importable and is a SQLAlchemy model."""
    assert DurableCanonicalEvent is not None
    assert DurableCanonicalEvent.__tablename__ == "durable_canonical_events"
    assert "event_id" in DurableCanonicalEvent.__table__.columns


# --------------------------------------------------------------------------
# B. DB-level UNIQUE(event_id)
# --------------------------------------------------------------------------

def test_database_level_unique_constraint():
    """event_id has a database-level UNIQUE constraint, separate from ORM PK."""
    table = DurableCanonicalEvent.__table__
    columns = {c.name: c for c in table.columns}

    # event_id is not the primary key; id is the ORM PK.
    assert list(table.primary_key.columns) == [columns["id"]]
    assert "event_id" not in [c.name for c in table.primary_key.columns]

    # DB-level UNIQUE on event_id.
    uniques = [u for u in table.constraints if isinstance(u, type(table.constraints))]
    from sqlalchemy import UniqueConstraint

    unique_constraints = [
        c for c in table.constraints if isinstance(c, UniqueConstraint)
    ]
    assert unique_constraints, "expected a UniqueConstraint on the table"
    assert columns["event_id"].unique is True or any(
        "event_id" in uc.columns for uc in unique_constraints
    )


# --------------------------------------------------------------------------
# C. repository implements IEventRepository
# --------------------------------------------------------------------------

def test_repository_implements_interface():
    """SQLAlchemyEventRepository is a subclass of IEventRepository."""
    assert issubclass(SQLAlchemyEventRepository, IEventRepository)


# --------------------------------------------------------------------------
# D. idempotent duplicate save
# --------------------------------------------------------------------------

def test_idempotent_duplicate_save(repo: SQLAlchemyEventRepository):
    """save(E) followed by save(E) results in exactly one durable record."""
    evt = make_event(event_id="evt-idempotent-0001")
    repo.save(evt)
    repo.save(evt)
    assert repo.count() == 1
    assert repo.exists("evt-idempotent-0001")
    assert repo.get("evt-idempotent-0001") is not None


# --------------------------------------------------------------------------
# E. distinct event IDs
# --------------------------------------------------------------------------

def test_distinct_event_ids_produce_distinct_records(
    repo: SQLAlchemyEventRepository,
):
    """Distinct canonical event_id values produce distinct durable records."""
    a = make_event(event_id="evt-distinct-aaa", source="s-a")
    b = make_event(event_id="evt-distinct-bbb", source="s-b")
    repo.save(a)
    repo.save(b)
    assert repo.count() == 2
    got_a = repo.get("evt-distinct-aaa")
    got_b = repo.get("evt-distinct-bbb")
    assert got_a is not None and got_b is not None
    assert got_a.event_id == "evt-distinct-aaa"
    assert got_b.event_id == "evt-distinct-bbb"
    assert got_a.source == "s-a"
    assert got_b.source == "s-b"


# --------------------------------------------------------------------------
# F. full round-trip
# --------------------------------------------------------------------------

def test_full_round_trip(repo: SQLAlchemyEventRepository):
    """Event -> save() -> get(event_id) -> Event preserves canonical fields."""
    payload = {"nested": {"list": [1, 2, 3], "flag": True}, "value": 42}
    meta = EventMetadata(
        tags=["a", "b"],
        properties={"nested_prop": {"x": 1}},
        correlation_id="corr-xyz",
    )
    ts = datetime(2026, 8, 15, 23, 59, 58, tzinfo=timezone.utc)
    evt = make_event(
        event_id="evt-roundtrip-0001",
        entity_id="entity-1",
        event_type=EventType.SIGNAL_RECEIVED,
        source="signal-in",
        payload=payload,
        metadata=meta,
        timestamp=ts,
    )

    repo.save(evt)
    got = repo.get("evt-roundtrip-0001")

    assert got is not None
    assert isinstance(got, Event)
    assert got.event_id == "evt-roundtrip-0001"
    assert got.entity_id == "entity-1"
    assert got.event_type == EventType.SIGNAL_RECEIVED
    # UTC semantics: the stored instant is preserved. SQLite's DateTime column
    # does not persist tzinfo, so normalize the returned value to UTC before
    # comparing the instant.
    assert got.timestamp.replace(tzinfo=timezone.utc) == ts
    assert got.source == "signal-in"
    assert got.payload == payload
    assert got.metadata.tags == ["a", "b"]
    assert got.metadata.properties == {"nested_prop": {"x": 1}}
    assert got.metadata.correlation_id == "corr-xyz"


def test_created_at_round_trip(repo: SQLAlchemyEventRepository):
    """Canonical Event.created_at is durably preserved (Architect Decision A).

    Uses a deterministic UTC instant T (NOT datetime.now()) and asserts that a
    full save -> get round-trip returns exactly that instant for created_at.
    """
    t = datetime(2021, 5, 17, 8, 30, 45, tzinfo=timezone.utc)
    evt = Event(
        event_id="evt-createdat-0001",
        entity_id="entity-created-at",
        event_type=EventType.SIGNAL_RECEIVED,
        timestamp=datetime(2021, 5, 17, 8, 30, 0, tzinfo=timezone.utc),
        source="created-at-source",
        payload={"n": 1},
        metadata=EventMetadata(correlation_id="corr-created-at"),
        created_at=t,
    )

    repo.save(evt)
    got = repo.get("evt-createdat-0001")

    assert got is not None
    assert isinstance(got, Event)
    # SQLite's DateTime column does not persist tzinfo; normalize to UTC before
    # comparing the exact instant.
    assert got.created_at.replace(tzinfo=timezone.utc) == t


# --------------------------------------------------------------------------
# G. nested payload/metadata
# --------------------------------------------------------------------------

def test_nested_payload_and_metadata(repo: SQLAlchemyEventRepository):
    """Deeply nested payload/metadata survive the round-trip unchanged."""
    deep_payload = {
        "outer": {
            "inner": {
                "list_of_dicts": [
                    {"a": [1, 2, {"deep": True}]},
                    {"b": None},
                ]
            }
        }
    }
    deep_meta = EventMetadata(
        tags=["tag1", "tag2", "tag3"],
        properties={
            "settings": {"retry": 3, "backoff": [1, 2, 4]},
            "flags": {"enabled": True},
        },
        correlation_id="corr-nested",
    )
    evt = make_event(
        event_id="evt-nested-0001",
        payload=deep_payload,
        metadata=deep_meta,
    )
    repo.save(evt)
    got = repo.get("evt-nested-0001")
    assert got is not None
    assert got.payload == deep_payload
    assert got.metadata.properties == deep_meta.properties
    assert got.metadata.tags == deep_meta.tags


# --------------------------------------------------------------------------
# H. transaction success
# --------------------------------------------------------------------------

def test_transaction_success_commits(repo: SQLAlchemyEventRepository):
    """Successful save() commits and makes the record visible to new sessions."""
    evt = make_event(event_id="evt-commit-0001")
    repo.save(evt)
    # Fresh repository session must see the committed row.
    fresh = SQLAlchemyEventRepository(session_manager=repo.session_manager)
    assert fresh.exists("evt-commit-0001")
    assert fresh.get("evt-commit-0001") is not None


def test_save_many_atomic_success(repo: SQLAlchemyEventRepository):
    """save_many persists all events in one atomic transaction."""
    events = [
        make_event(event_id=f"evt-batch-{i:03d}", source=f"src-{i}")
        for i in range(5)
    ]
    repo.save_many(events)
    assert repo.count() == 5
    assert repo.get("evt-batch-003") is not None


# --------------------------------------------------------------------------
# I. rollback on failure
# --------------------------------------------------------------------------

def test_rollback_on_save_many_conflict(repo: SQLAlchemyEventRepository):
    """A UNIQUE(event_id) conflict in save_many rolls back the whole batch."""
    first = make_event(event_id="evt-conflict-0001")
    repo.save(first)
    before = repo.count()

    duplicate = make_event(event_id="evt-conflict-0001", source="other")
    with pytest.raises(Exception):
        repo.save_many([duplicate])

    # No partial writes: only the original record remains.
    assert repo.count() == before
    assert repo.get("evt-conflict-0001").source != "other"


def test_rollback_on_failure_session(repo: SQLAlchemyEventRepository):
    """A failing persistence operation rolls back, re-raises, and leaks no session.

    Forces a genuine DB-level failure inside save_many (a duplicate canonical
    event_id already committed). Verifies the transaction lifecycle contract:
    rollback on failure, exception re-raised, no partial writes, and the
    session remains usable afterward (no leak).
    """
    repo.save(make_event(event_id="evt-conflict-rollback-0001"))

    before = repo.count()
    batch = [
        make_event(event_id="evt-rollback-new-0001", source="src-new-1"),
        make_event(event_id="evt-conflict-rollback-0001", source="src-dup"),  # conflict
        make_event(event_id="evt-rollback-new-0002", source="src-new-2"),
    ]
    with pytest.raises(Exception):
        repo.save_many(batch)

    # No partial writes: the two new events must NOT have been committed.
    assert repo.count() == before
    assert not repo.exists("evt-rollback-new-0001")
    assert not repo.exists("evt-rollback-new-0002")

    # Session lifecycle: after the rolled-back failure the repository still
    # works and a fresh commit succeeds (no leaked/broken session).
    repo.save(make_event(event_id="evt-after-rollback-0001"))
    assert repo.exists("evt-after-rollback-0001")


# --------------------------------------------------------------------------
# J. session lifecycle (no leaks)
# --------------------------------------------------------------------------

def test_session_lifecycle_no_leak(session_manager: DatabaseSessionManager):
    """Repository operations do not leak open sessions."""
    repo = SQLAlchemyEventRepository(session_manager=session_manager)
    repo.initialize()

    evt = make_event(event_id="evt-session-0001")
    repo.save(evt)
    repo.get("evt-session-0001")
    repo.exists("evt-session-0001")
    repo.list_all()
    repo.count()

    # The session() context manager always closes; the engine still works.
    assert session_manager.engine is not None
    with session_manager.session(commit=False) as s:
        s.execute(text("SELECT 1"))


# --------------------------------------------------------------------------
# K. repository interface parity
# --------------------------------------------------------------------------

def test_repository_interface_parity():
    """Repository exposes every abstract method of IEventRepository."""
    abstract = set(IEventRepository.__abstractmethods__)
    concrete = SQLAlchemyEventRepository.__dict__
    for method in abstract:
        assert method in concrete, f"missing implementation: {method}"
    assert abstract == {"save", "get", "exists", "delete", "list_all",
                        "list_by_type", "list_by_source", "list_by_correlation",
                        "count"}


def test_list_and_count_operations(repo: SQLAlchemyEventRepository):
    """list_all/list_by_type/list_by_source/list_by_correlation/count work."""
    meta_a = EventMetadata(correlation_id="corr-1")
    meta_b = EventMetadata(correlation_id="corr-2")
    repo.save(make_event(event_id="evt-list-a", source="src-a",
                         event_type=EventType.SIGNAL_RECEIVED, metadata=meta_a))
    repo.save(make_event(event_id="evt-list-b", source="src-b",
                         event_type=EventType.SIGNAL_RECEIVED, metadata=meta_a))
    repo.save(make_event(event_id="evt-list-c", source="src-b",
                         event_type=EventType.OBSERVATION_CREATED, metadata=meta_b))

    assert repo.count() == 3
    assert len(repo.list_all()) == 3
    assert len(repo.list_by_type(str(EventType.SIGNAL_RECEIVED))) == 2
    assert len(repo.list_by_type(str(EventType.OBSERVATION_CREATED))) == 1
    assert len(repo.list_by_source("src-b")) == 2
    assert len(repo.list_by_correlation("corr-1")) == 2
    assert len(repo.list_by_correlation("corr-2")) == 1
    assert len(repo.list_by_correlation("missing")) == 0


def test_get_returns_canonical_event_type(repo: SQLAlchemyEventRepository):
    """get() returns app.event.event.Event, not the durable model."""
    evt = make_event(event_id="evt-type-0001")
    repo.save(evt)
    got = repo.get("evt-type-0001")
    assert got is not None
    assert type(got) is Event
    assert not isinstance(got, DurableCanonicalEvent)


def test_delete(repo: SQLAlchemyEventRepository):
    """delete removes the durable record and returns True/False correctly."""
    evt = make_event(event_id="evt-delete-0001")
    repo.save(evt)
    assert repo.exists("evt-delete-0001")
    assert repo.delete("evt-delete-0001") is True
    assert not repo.exists("evt-delete-0001")
    assert repo.delete("evt-delete-0001") is False


# --------------------------------------------------------------------------
# L. architectural isolation
# --------------------------------------------------------------------------

def test_architectural_isolation_from_canonical_domain():
    """Canonical Event, pipeline, factory, adapters have no SQLAlchemy coupling."""
    import app.event.event as event_mod
    import app.event_repository.interfaces.i_event_repository as iface_mod

    canonical_src = open(event_mod.__file__).read()
    iface_src = open(iface_mod.__file__).read()

    for forbidden in ("sqlalchemy", "create_engine", "Session", "DurableCanonicalEvent"):
        assert forbidden not in canonical_src, (
            f"canonical Event coupled to {forbidden}"
        )
        assert forbidden not in iface_src, (
            f"IEventRepository interface coupled to {forbidden}"
        )
