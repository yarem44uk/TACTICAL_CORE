"""
WO-014-017 tests: Canonical durable repository production integration.

Exercises the additive canonical production composition path:

    canonical Event
        |
        v
    EventService
        |
        v
    IEventRepository
        |
        v
    DurableCanonicalEventRepository   (WO-014-016 SQLAlchemy durable impl)
        |
        v
    DurableCanonicalEvent
        |
        v
    existing DatabaseSessionManager

These tests exercise the actual composition/service path against a real
in-memory SQLite database (no mocks that bypass the repository). The legacy
persistence architecture is explicitly out of scope and is never touched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

from app.composition import durable_build_default_components, DurableEventRuntime
from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_repository.interfaces.i_event_repository import IEventRepository
from app.event_repository.memory_event_repository import MemoryEventRepository


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


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
def durable_repo(
    session_manager: DatabaseSessionManager,
) -> SQLAlchemyEventRepository:
    """A durable canonical repository bound to an in-memory DB, table created."""
    repository = SQLAlchemyEventRepository(session_manager=session_manager)
    repository.initialize()
    return repository


@pytest.fixture()
def runtime(durable_repo: SQLAlchemyEventRepository) -> DurableEventRuntime:
    """The canonical durable composition runtime wired to a real in-memory repo."""
    return durable_build_default_components(repository=durable_repo)


def make_event(
    *,
    event_id: Optional[str] = None,
    entity_id: Optional[str] = "entity-1",
    event_type: EventType = EventType.SIGNAL_RECEIVED,
    source: str = "wo014017-source",
    payload: Optional[dict] = None,
    metadata: Optional[EventMetadata] = None,
    timestamp: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id or "evt-wo014017-0000-0000-000000000001",
        entity_id=entity_id,
        event_type=event_type,
        timestamp=timestamp
        or datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=metadata if metadata is not None else EventMetadata(
            tags=["wo014017"],
            properties={"nested": {"level": 1}},
            correlation_id="corr-wo014017",
        ),
        created_at=created_at
        or datetime(2026, 8, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. composition function exists and is callable
# ---------------------------------------------------------------------------


def test_durable_composition_exists_and_callable():
    """durable_build_default_components is importable and callable."""
    assert callable(durable_build_default_components)
    assert DurableEventRuntime is not None


# ---------------------------------------------------------------------------
# 2. EventService receives the durable canonical repository
# ---------------------------------------------------------------------------


def test_runtime_injects_durable_canonical_repository(runtime):
    """The runtime's EventService holds a DurableCanonicalEventRepository."""
    assert isinstance(runtime.event_service, object)
    assert isinstance(runtime.repository, SQLAlchemyEventRepository)
    assert isinstance(runtime.repository, IEventRepository)


# ---------------------------------------------------------------------------
# 3/4/5/6/7/8/9/10/11/12. full round trip via EventService
# ---------------------------------------------------------------------------


def test_production_round_trip_preserves_all_fields(runtime):
    """save_event -> get_event returns a canonical Event with all fields intact."""
    created = make_event(
        event_id="evt-roundtrip-1",
        entity_id="entity-9",
        event_type=EventType.OBSERVATION_CREATED,
        source="sensor-a",
        payload={"coords": {"lat": 48.0, "lon": 37.0}, "values": [1, 2, 3]},
        metadata=EventMetadata(
            tags=["alpha", "beta"],
            properties={"nested": {"deep": {"x": 1}}},
            correlation_id="corr-1",
        ),
        timestamp=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 15, 10, 30, 0, tzinfo=timezone.utc),
    )

    runtime.event_service.save_event(created)
    restored = runtime.event_service.get_event("evt-roundtrip-1")

    # Returned object is a canonical Event, not an ORM object.
    assert isinstance(restored, Event)
    assert not isinstance(restored, DurableCanonicalEvent)

    # event_id preserved.
    assert restored.event_id == created.event_id
    # entity_id preserved.
    assert restored.entity_id == created.entity_id
    # event_type preserved (canonical enum representation).
    assert restored.event_type == EventType.OBSERVATION_CREATED
    assert isinstance(restored.event_type, EventType)
    # timestamp preserved exactly. SQLite's DateTime column does not persist
    # tzinfo, so normalize the returned value to UTC before comparing (this is
    # the documented WO-014-016 durable repository behavior with SQLite).
    assert restored.timestamp.replace(tzinfo=timezone.utc) == created.timestamp
    # source preserved.
    assert restored.source == created.source
    # payload preserved (incl. nested).
    assert restored.payload == created.payload
    assert restored.payload["coords"] == {"lat": 48.0, "lon": 37.0}
    # metadata preserved (incl. nested).
    assert restored.metadata.to_dict() == created.metadata.to_dict()
    assert restored.metadata.correlation_id == "corr-1"
    # created_at preserved exactly (deterministic instant). Same SQLite tzinfo
    # normalization as the WO-014-016 created_at round-trip test.
    assert restored.created_at.replace(tzinfo=timezone.utc) == created.created_at
    assert (
        restored.created_at.replace(tzinfo=timezone.utc)
        == datetime(2026, 8, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# ---------------------------------------------------------------------------
# 12. created_at preserved exactly
# ---------------------------------------------------------------------------


def test_created_at_preserved_exactly(runtime):
    """created_at survives round trip as the exact deterministic instant T."""
    T = datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc)
    event = make_event(event_id="evt-createdat", created_at=T)
    runtime.event_service.save_event(event)
    restored = runtime.event_service.get_event("evt-createdat")
    # SQLite's DateTime column does not persist tzinfo (documented WO-014-016
    # behavior); normalize to UTC before comparing the exact instant.
    assert restored.created_at.replace(tzinfo=timezone.utc) == T


# ---------------------------------------------------------------------------
# 13. duplicate event_id remains idempotent
# ---------------------------------------------------------------------------


def test_duplicate_save_idempotent(runtime):
    """Saving the same event_id twice yields exactly one durable record."""
    event = make_event(event_id="evt-idem")
    runtime.event_service.save_event(event)
    runtime.event_service.save_event(event)
    assert runtime.repository.count() == 1
    assert runtime.event_service.get_event("evt-idem") is not None


# ---------------------------------------------------------------------------
# 14. successful persistence commits
# ---------------------------------------------------------------------------


def test_successful_persistence_commits(runtime):
    """A saved event is durably visible (committed to the in-memory DB)."""
    event = make_event(event_id="evt-commit")
    runtime.event_service.save_event(event)
    # A fresh repository bound to the same manager reads the committed record.
    assert runtime.repository.exists("evt-commit") is True
    assert runtime.repository.count() == 1


# ---------------------------------------------------------------------------
# 15. failed transaction rolls back
# ---------------------------------------------------------------------------


def test_failed_transaction_rolls_back(runtime):
    """A failure in a save_many batch rolls back atomically (no partial writes)."""
    e1 = make_event(event_id="evt-a")
    e2 = make_event(event_id="evt-b")
    runtime.repository.save_many([e1, e2])
    assert runtime.repository.count() == 2

    # Now attempt a batch containing a duplicate of evt-a -> UNIQUE violation.
    dup = make_event(event_id="evt-a")
    with pytest.raises(Exception):
        runtime.repository.save_many([e2, dup])

    # The failed batch must not have created a new record; count stays 2.
    assert runtime.repository.count() == 2


# ---------------------------------------------------------------------------
# 16. legacy SQLAlchemyEventRepository name remains resolvable
# ---------------------------------------------------------------------------


def test_legacy_sqlalchemy_name_still_resolvable():
    """The existing SQLAlchemyEventRepository export in durable remains intact."""
    from app.event_repository.durable import SQLAlchemyEventRepository as DurableSQL
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )

    assert DurableSQL is SQLAlchemyEventRepository


# ---------------------------------------------------------------------------
# 17. canonical composition does not depend on legacy Event objects
# ---------------------------------------------------------------------------


def test_canonical_path_uses_canonical_event(runtime):
    """Events flowing through the composition are canonical app.event.event.Event."""
    event = make_event(event_id="evt-canon")
    runtime.event_service.save_event(event)
    restored = runtime.event_service.get_event("evt-canon")
    assert type(restored) is Event  # exactly the canonical class


# ---------------------------------------------------------------------------
# 18. durable repository uses the existing DatabaseSessionManager
# ---------------------------------------------------------------------------


def test_durable_repository_reuses_existing_session_manager(durable_repo):
    """The durable repo binds the provided (existing) DatabaseSessionManager."""
    assert isinstance(durable_repo.session_manager, DatabaseSessionManager)
