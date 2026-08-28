"""
WO-037-01 tests: Operator event feed — additive read-only repository query layer.

Exercises the actual SQLAlchemy-backed durable repository against a real
in-memory SQLite database. Verifies:

A. keyset/cursor pagination (deterministic, seq-ordered, bounded)
B. first-page / continuation-cursor / final-page behavior
C. source filter
D. event_type filter
E. from_time / to_time filters
F. combined filters
G. bounded limit (clamp)
H. malformed cursor rejection
I. event detail by durable identity (get_durable_event)
J. nonexistent event detail
K. read-only guarantee (no persistent state mutation)
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


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
    event_id: str,
    event_type: EventType = EventType.CUSTOM,
    source: str = "test-source",
    timestamp: datetime,
    payload: dict | None = None,
) -> Event:
    """Build a canonical domain Event with deterministic identity/time."""
    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=EventMetadata(),
    )


def seed_events(repo: SQLAlchemyEventRepository, n: int = 25) -> None:
    """Persist n events with increasing timestamps and deterministic ids."""
    # SQLite stores DateTime(timezone=True) as naive UTC, so we use naive UTC
    # datetimes for deterministic, comparable fixtures.
    base = datetime(2026, 8, 1)
    for i in range(n):
        source = "alpha" if i % 2 == 0 else "beta"
        etype = EventType.ENTITY_CREATED if i % 3 == 0 else EventType.CUSTOM
        ts = base.replace(hour=(i % 24), minute=(i % 60))
        ev = make_event(
            event_id=f"evt-{i:04d}",
            event_type=etype,
            source=source,
            timestamp=ts,
        )
        repo.save(ev)


# -- keyset pagination -------------------------------------------------------


def test_first_page_returns_limit_in_seq_order(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    events, next_cursor = repo.query_events(limit=10)
    assert len(events) == 10
    # seq is assigned 1..25 in save order.
    assert [e.event_id for e in events] == [
        f"evt-{i:04d}" for i in range(10)
    ]
    assert next_cursor == 10


def test_continuation_cursor_advances(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    page1, cursor1 = repo.query_events(limit=10)
    assert cursor1 == 10
    page2, cursor2 = repo.query_events(limit=10, cursor=cursor1)
    assert [e.event_id for e in page2] == [f"evt-{i:04d}" for i in range(10, 20)]
    assert cursor2 == 20
    page3, cursor3 = repo.query_events(limit=10, cursor=cursor2)
    assert [e.event_id for e in page3] == [f"evt-{i:04d}" for i in range(20, 25)]
    assert cursor3 is None  # final page


def test_final_page_has_no_cursor(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 3)
    events, cursor = repo.query_events(limit=10)
    assert len(events) == 3
    assert cursor is None


# -- filters -----------------------------------------------------------------


def test_source_filter(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    events, _ = repo.query_events(source="alpha")
    assert events and all(e.source == "alpha" for e in events)
    # alpha is even index => 13 events (0..24 even).
    assert len(events) == 13


def test_event_type_filter(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    events, _ = repo.query_events(event_type=str(EventType.ENTITY_CREATED))
    assert events and all(e.event_type == EventType.ENTITY_CREATED for e in events)


def test_time_range_filter(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    base = datetime(2026, 8, 1)
    lo = base.replace(hour=4, minute=0)
    hi = base.replace(hour=8, minute=0)
    events, _ = repo.query_events(from_time=lo, to_time=hi)
    assert events
    for e in events:
        assert lo <= e.timestamp < hi


def test_combined_filters(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 25)
    base = datetime(2026, 8, 1)
    lo = base.replace(hour=2, minute=0)
    hi = base.replace(hour=12, minute=0)
    events, _ = repo.query_events(
        source="alpha", event_type=str(EventType.ENTITY_CREATED), from_time=lo, to_time=hi
    )
    for e in events:
        assert e.source == "alpha"
        assert e.event_type == EventType.ENTITY_CREATED
        assert lo <= e.timestamp < hi


# -- limit / validation ------------------------------------------------------


def test_limit_clamped(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 250)
    events, cursor = repo.query_events(limit=10_000)
    assert len(events) == 200  # clamped to max 200
    assert cursor == 200


def test_malformed_cursor_rejected(repo: SQLAlchemyEventRepository) -> None:
    with pytest.raises(ValueError):
        repo.query_events(cursor="not-an-int")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repo.query_events(cursor=1.5)  # type: ignore[arg-type]


def test_bad_limit_rejected(repo: SQLAlchemyEventRepository) -> None:
    with pytest.raises(ValueError):
        repo.query_events(limit=0)
    with pytest.raises(ValueError):
        repo.query_events(limit=-5)


def test_inverted_time_range_rejected(repo: SQLAlchemyEventRepository) -> None:
    base = datetime(2026, 8, 1)
    with pytest.raises(ValueError):
        repo.query_events(
            from_time=base.replace(hour=8),
            to_time=base.replace(hour=4),
        )


# -- event detail ------------------------------------------------------------


def test_get_durable_event(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 5)
    result = repo.get_durable_event("evt-0002")
    assert result is not None
    seq, ev = result
    assert ev.event_id == "evt-0002"
    assert seq == 3  # 1-indexed seq assigned at save


def test_get_durable_event_not_found(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 3)
    assert repo.get_durable_event("evt-9999") is None


# -- read-only guarantee -----------------------------------------------------


def test_queries_do_not_mutate_state(repo: SQLAlchemyEventRepository) -> None:
    seed_events(repo, 10)
    before = repo.count()
    repo.query_events(limit=5)
    repo.query_events(limit=3, cursor=2)
    repo.query_events(source="alpha")
    repo.query_events(from_time=datetime(2026, 8, 1))
    assert repo.get_durable_event("evt-0001") is not None
    assert repo.count() == before  # no insert/delete
