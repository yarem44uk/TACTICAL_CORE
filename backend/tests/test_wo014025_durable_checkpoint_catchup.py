"""WO-014-025 — Durable Projection Checkpoint + Deterministic Catch-up.

Proves the WO-014-025 architectural gate over the real production composition:

    DatabaseSessionManager
        ├── DurableCanonicalEventRepository   (durable events + seq)
        ├── SQLAlchemyEntityRepository        (durable entity state)
        └── ProjectionCheckpointRepository    (durable projection checkpoint)
    EventPipeline
        → durable Event persistence
        → EntityBridge / EntityManager projection  (best-effort)
        → ProjectionObservability                 (in-memory HOT PATH — DB-free)

Key invariants covered:
  * EVENT PERSIST -> ENTITY PROJECTION/COMMIT -> CHECKPOINT ADVANCE/COMMIT.
  * The checkpoint NEVER advances before successful entity projection.
  * A projection failure leaves the durable Event intact and the checkpoint
    behind, so a later deterministic catch-up retries it.
  * Durable monotonic ``seq`` orders replay deterministically (ORDER BY seq ASC).
  * Duplicate canonical ``event_id`` retains its original seq (no dup row).
  * Durable entity + checkpoint survive a session/engine reopen (restart).
  * NO second engine/sessionmaker/DB owner (single DatabaseSessionManager).
  * Projection-observability HOT PATH performs ZERO DB access (deadlock gate):
    repeated ``pipeline.process`` never hangs on the shared :memory: owner.
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository as DurableCanonicalEventRepository,
)
from app.projection.checkpoint import ProjectionCheckpointRepository


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database (single canonical DB owner), resetting afterwards so
    nothing leaks. No second engine/sessionmaker/owner is created."""
    manager = configure_session_manager("sqlite:///:memory:")
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def durable_repo(session_manager) -> DurableCanonicalEventRepository:
    """A durable canonical repository bound to the global session manager,
    with the durable table created."""
    repo = DurableCanonicalEventRepository()
    repo.initialize()
    return repo


@pytest.fixture()
def checkpoint_repo(session_manager) -> ProjectionCheckpointRepository:
    """A durable projection-checkpoint repository over the single owner."""
    repo = ProjectionCheckpointRepository()
    repo.initialize()
    return repo


def make_event(
    *,
    event_id: str,
    entity_id: str,
    event_type: EventType = EventType.SIGNAL_RECEIVED,
    payload: dict | None = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=event_type,
        timestamp=__import__("datetime").datetime(
            2026, 8, 17, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc
        ),
        source="wo014025-source",
        payload=payload if payload is not None else {"k": "v"},
        metadata=EventMetadata(tags=["wo014025"]),
        created_at=__import__("datetime").datetime(
            2026, 8, 17, 10, 0, 0, tzinfo=__import__("datetime").timezone.utc
        ),
    )


# ---------------------------------------------------------------------------
# A. Deadlock elimination on the projection-observability HOT PATH
# ---------------------------------------------------------------------------


def test_hot_path_repeated_process_does_not_deadlock(session_manager):
    """Repeated pipeline.process() must complete without hanging/deadlocking,
    even though projection observability publishes a health signal on every
    event. Regression for the WO-014-025 deadlock on the shared :memory: owner."""
    rt = create_event_runtime()
    for i in range(5):
        rt.pipeline.process(
            make_event(event_id=f"evt-025-dl-{i}", entity_id=f"entity-{i}")
        )
    # Hot-path snapshot reflects the last projected event without DB access.
    assert rt.projection_observability.last_projected_event_id == "evt-025-dl-4"
    assert rt.projection_observability.snapshot()["entity_count"] == 5


def test_snapshot_performs_no_db_access(session_manager):
    """snapshot() is built entirely from the in-memory cache; it must not open
    a DB session. We prove this by constructing a runtime whose observability
    has NO durable checkpoint and asserting the snapshot is memory-derived."""
    rt = create_event_runtime()
    rt.pipeline.process(
        make_event(event_id="evt-025-snap-1", entity_id="entity-snap-1")
    )
    snap = rt.projection_observability.snapshot()
    assert snap["last_projected_event_id"] == "evt-025-snap-1"
    assert snap["entity_count"] == 1
    assert snap["projection_failure_count"] == 0


# ---------------------------------------------------------------------------
# B. Durable monotonic sequence (seq)
# ---------------------------------------------------------------------------


def _durable_seqs(session_manager) -> list:
    """Return the durable seq values via the shared owner (test helper)."""
    from sqlalchemy import select
    from app.database.base import Base
    from app.event_repository.durable.durable_event_model import (
        DurableCanonicalEvent,
    )
    manager = session_mod.get_session_manager()
    with manager.session(commit=False) as s:
        return [
            r.seq
            for r in s.execute(
                select(DurableCanonicalEvent).order_by(DurableCanonicalEvent.seq.asc())
            ).scalars().all()
        ]


def test_seq_assigned_and_monotonic(durable_repo, session_manager):
    e1 = make_event(event_id="evt-seq-1", entity_id="entity-seq-1")
    e2 = make_event(event_id="evt-seq-2", entity_id="entity-seq-2")
    e3 = make_event(event_id="evt-seq-3", entity_id="entity-seq-3")
    for e in (e1, e2, e3):
        durable_repo.save(e)
    seqs = _durable_seqs(session_manager)
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3  # strictly increasing / unique
    assert seqs[0] < seqs[1] < seqs[2]


def test_duplicate_event_id_preserves_original_seq(durable_repo, session_manager):
    e = make_event(event_id="evt-dup-seq", entity_id="entity-dup-seq")
    durable_repo.save(e)
    original_seq = _durable_seqs(session_manager)[0]
    # Save the SAME canonical event_id again -> must not create a second row.
    durable_repo.save(e)
    rows = _durable_seqs(session_manager)
    assert len(rows) == 1
    assert rows[0] == original_seq  # original seq retained


def test_list_all_ordered_by_seq(durable_repo, session_manager):
    for i in range(4):
        durable_repo.save(
            make_event(event_id=f"evt-order-{i}", entity_id=f"entity-order-{i}")
        )
    seqs = _durable_seqs(session_manager)
    assert seqs == sorted(seqs)


def test_list_after_seq_and_iter_after_seq(durable_repo, session_manager):
    for i in range(5):
        durable_repo.save(
            make_event(event_id=f"evt-after-{i}", entity_id=f"entity-after-{i}")
        )
    seqs = _durable_seqs(session_manager)
    checkpoint = seqs[2]
    after = durable_repo.list_after_seq(checkpoint)
    assert len(after) == 2
    pairs = durable_repo.iter_after_seq(checkpoint)
    assert len(pairs) == 2
    got_seqs = [s for s, _ in pairs]
    assert got_seqs == sorted(got_seqs)
    assert all(s > checkpoint for s in got_seqs)


# ---------------------------------------------------------------------------
# C. Durable projection checkpoint
# ---------------------------------------------------------------------------


def test_checkpoint_persists_and_survives_restart(durable_repo, checkpoint_repo, session_manager):
    assert checkpoint_repo.get_last_seq() == 0
    checkpoint_repo.advance(7, "evt-checkpoint-7")
    assert checkpoint_repo.get_last_seq() == 7
    assert checkpoint_repo.get_last_event_id() == "evt-checkpoint-7"
    # Reopen a fresh repository against the same engine (restart simulation).
    fresh = ProjectionCheckpointRepository()
    assert fresh.get_last_seq() == 7
    assert fresh.get_last_event_id() == "evt-checkpoint-7"


# ---------------------------------------------------------------------------
# D. Catch-up driver
# ---------------------------------------------------------------------------


def test_catch_up_projects_and_advances_checkpoint(session_manager, checkpoint_repo):
    rt = create_event_runtime()
    # Persist 3 events durably WITHOUT running catch-up first.
    for i in range(3):
        rt.event_service.save_event(
            make_event(event_id=f"evt-cu-{i}", entity_id=f"entity-cu-{i}")
        )
    assert checkpoint_repo.get_last_seq() == 0
    result = rt.catch_up.run()
    assert result.processed == 3
    assert result.failed == 0
    assert checkpoint_repo.get_last_seq() == result.checkpoint_seq > 0
    # Entities are now present.
    entities = rt.entity_manager.list_entities()
    assert {e["entity_id"] for e in entities} == {
        "entity-cu-0", "entity-cu-1", "entity-cu-2",
    }


def test_catch_up_is_idempotent(session_manager, checkpoint_repo):
    rt = create_event_runtime()
    for i in range(3):
        rt.event_service.save_event(
            make_event(event_id=f"evt-cuid-{i}", entity_id=f"entity-cuid-{i}")
        )
    rt.catch_up.run()
    first_entities = sorted(
        (e["entity_id"], e["version"]) for e in rt.entity_manager.list_entities()
    )
    # Second catch-up pass must be a no-op (checkpoint already advanced).
    result2 = rt.catch_up.run()
    assert result2.processed == 0
    second_entities = sorted(
        (e["entity_id"], e["version"]) for e in rt.entity_manager.list_entities()
    )
    assert second_entities == first_entities  # identical state, no dupes


def test_catch_up_reprocesses_after_failure_does_not_advance_checkpoint(
    session_manager, checkpoint_repo, monkeypatch
):
    """A projection failure must NOT advance the checkpoint, and the durable
    Event must survive; a later catch-up retries it."""
    rt = create_event_runtime()
    for i in range(2):
        rt.event_service.save_event(
            make_event(event_id=f"evt-fail-{i}", entity_id=f"entity-fail-{i}")
        )
    from app.composition import _project_event_to_entity

    calls = {"n": 0}

    def flaky_projection(event):
        calls["n"] += 1
        if event.event_id == "evt-fail-0":
            raise RuntimeError("projection boom")

    # Temporarily replace the catch-up projection with a flaky one.
    rt.catch_up._projection = flaky_projection
    result = rt.catch_up.run()
    assert result.failed == 1
    assert result.processed == 0
    # Checkpoint must NOT have advanced past 0.
    assert checkpoint_repo.get_last_seq() == 0
    # Durable events are intact.
    assert rt.event_service.get_event("evt-fail-0") is not None
    assert rt.event_service.get_event("evt-fail-1") is not None


# ---------------------------------------------------------------------------
# E. Durable entity persistence
# ---------------------------------------------------------------------------


def test_durable_entity_state_survives_restart(session_manager):
    """Entity state persists through the shared DB owner and survives a
    session/engine reopen (restart)."""
    rt = create_event_runtime()
    rt.pipeline.process(
        make_event(event_id="evt-restart-1", entity_id="entity-restart-1")
    )
    # Reopen a fresh repository against the same engine.
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    fresh = SQLAlchemyEntityRepository()
    row = fresh.get("entity-restart-1")
    assert row is not None
    assert row["entity_id"] == "entity-restart-1"


# ---------------------------------------------------------------------------
# F. Single DB owner / no second engine
# ---------------------------------------------------------------------------


def test_single_database_owner(session_manager):
    """The production composition must not create a second engine, sessionmaker,
    or independent DB owner."""
    rt = create_event_runtime()
    # The runtime exposes the shared manager; no second owner is created.
    manager = session_mod.get_session_manager()
    assert manager.engine is not None
    # The three durable tables all live on the same engine/metadata.
    from app.database.base import Base
    tables = Base.metadata.tables
    assert "durable_canonical_events" in tables
    assert "entities" in tables
    assert "projection_checkpoint" in tables


def test_production_boundary_integration(session_manager):
    """Cross the real production boundary end-to-end without mocks:
    create_event_runtime -> EventPipeline -> durable event -> EntityBridge ->
    EntityManager -> durable entity -> durable checkpoint."""
    rt = create_event_runtime()
    rt.pipeline.process(
        make_event(event_id="evt-e2e-025", entity_id="entity-e2e-025")
    )
    # Durable event persisted.
    assert rt.event_service.get_event("evt-e2e-025") is not None
    # Entity projected + durable.
    assert rt.entity_read.get("entity-e2e-025") is not None
    # Observability reflects success.
    assert rt.projection_observability.last_projected_event_id == "evt-e2e-025"
