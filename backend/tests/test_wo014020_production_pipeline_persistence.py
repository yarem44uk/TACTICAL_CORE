"""WO-014-020 tests: Production EventPipeline -> DurableCanonicalEventRepository
persistence wiring.

WO-014-020 closes the production composition gap: ``create_event_runtime()``
now wires the existing durable canonical repository into the
``EventPipeline`` persistence seam via ``pipeline.set_repository(...)``.

Intended canonical production chain (verified here against the REAL
production composition root, not a hand-built wiring):

    canonical Event
        |
        v
    EventPipeline.process(event)
        |
        v    (persistence seam: pipeline.set_repository(repository))
    IEventRepository
        |
        v
    DurableCanonicalEventRepository   (WO-014-016 SQLAlchemy durable impl)
        |
        v
    existing DatabaseSessionManager
        |
        v
    SQLite

These tests call the authoritative production composition function
``create_event_runtime()`` and assert on the resulting wired runtime:
the EventPipeline's own repository seam is the durable canonical repository
(NOT the in-memory or legacy repository), and ``pipeline.process(event)``
actually durably persists the canonical Event (round-trip by event_id).

The single existing ``DatabaseSessionManager`` is reused — no second engine,
session manager, or DB owner is introduced either by the production
composition or by these tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

import app.database.session as session_mod
from app.composition import EventRuntime, create_event_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository as DurableCanonicalEventRepository,
)
from app.event_repository.memory_event_repository import MemoryEventRepository


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def global_session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database (exactly as the production app does at startup) and reset
    it afterwards so it does not leak across tests."""
    manager = configure_session_manager("sqlite:///:memory:")
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def durable_repo(global_session_manager) -> DurableCanonicalEventRepository:
    """A durable canonical repository bound to the global session manager,
    with the durable table created. This is the repository the production
    composition wires into the pipeline by default."""
    repo = DurableCanonicalEventRepository()
    repo.initialize()
    return repo


def make_event(
    *,
    event_id: str,
    entity_id: str = "entity-020",
    event_type: EventType = EventType.SIGNAL_RECEIVED,
    source: str = "wo014020-source",
    payload: Optional[dict] = None,
    metadata: Optional[EventMetadata] = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=event_type,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=metadata if metadata is not None else EventMetadata(
            tags=["wo014020"],
        ),
        created_at=datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Test A — production composition wiring (EventPipeline.repository seam)
# ---------------------------------------------------------------------------


def test_create_event_runtime_wires_durable_repo_into_pipeline(
    durable_repo,
) -> None:
    """create_event_runtime() produces an EventPipeline whose own repository
    seam is the durable canonical repository — NOT the in-memory or legacy
    repository."""
    runtime = create_event_runtime(repository=durable_repo)
    assert isinstance(runtime, EventRuntime)
    assert isinstance(runtime.pipeline, EventPipeline)

    wired = runtime.pipeline._repository
    assert wired is durable_repo
    assert isinstance(wired, DurableCanonicalEventRepository)
    assert not isinstance(wired, MemoryEventRepository)


def test_default_production_runtime_wires_durable_repo(
    global_session_manager,
) -> None:
    """With no repository injected, the production composition itself builds
    and wires a DurableCanonicalEventRepository into the pipeline seam."""
    runtime = create_event_runtime()
    wired = runtime.pipeline._repository
    assert wired is not None
    assert isinstance(wired, DurableCanonicalEventRepository)
    assert not isinstance(wired, MemoryEventRepository)


# ---------------------------------------------------------------------------
# Test B — canonical event persistence through the production-composed pipeline
# ---------------------------------------------------------------------------


def test_pipeline_process_persists_canonical_event(durable_repo) -> None:
    """pipeline.process(event) durably persists the canonical Event through
    the configured durable repository; the event is retrievable by its
    canonical event_id (round-trip)."""
    runtime = create_event_runtime(repository=durable_repo)
    event = make_event(event_id="evt-wo014020-roundtrip-1")

    result = runtime.pipeline.process(event)
    assert result is True

    restored = durable_repo.get(event.event_id)
    assert restored is not None
    assert type(restored) is Event
    assert restored.event_id == event.event_id
    assert restored.entity_id == event.entity_id
    assert restored.source == event.source
    assert restored.payload == event.payload
    assert restored.metadata.to_dict() == event.metadata.to_dict()


def test_pipeline_persistence_round_trip_identity(durable_repo) -> None:
    """The identity stored via pipeline.process() matches the canonical
    event_id exactly (canonical Event.event_id is the durable identity)."""
    runtime = create_event_runtime(repository=durable_repo)
    event = make_event(event_id="evt-wo014020-identity-7")

    runtime.pipeline.process(event)

    assert durable_repo.exists(event.event_id) is True
    got = durable_repo.get("evt-wo014020-identity-7")
    assert got is not None
    assert got.event_id == "evt-wo014020-identity-7"


# ---------------------------------------------------------------------------
# Test C — single repository instance / seam (pipeline and event_service share
# the same durable repository)
# ---------------------------------------------------------------------------


def test_pipeline_and_event_service_share_single_repository(durable_repo) -> None:
    """The production pipeline and the canonical EventService are wired to the
    SAME single durable repository instance — no second repository/database
    path is introduced."""
    runtime = create_event_runtime(repository=durable_repo)
    assert runtime.pipeline._repository is runtime.event_service._repository
    assert runtime.pipeline._repository is durable_repo


# ---------------------------------------------------------------------------
# Test D — database lifecycle: no second DB owner
# ---------------------------------------------------------------------------


def test_pipeline_repo_uses_existing_database_session_manager(durable_repo) -> None:
    """The durable repository wired into the production pipeline binds the
    existing (single) DatabaseSessionManager — no second engine/session
    owner is introduced."""
    from app.database.session import DatabaseSessionManager

    runtime = create_event_runtime(repository=durable_repo)
    wired = runtime.pipeline._repository
    assert isinstance(wired.session_manager, DatabaseSessionManager)
    # The configured global manager IS the one the wired repo uses.
    assert wired.session_manager is session_mod.get_session_manager()


def test_production_composition_reuses_existing_db_infrastructure(
    durable_repo,
) -> None:
    """Composition does not construct a second engine/sessionmaker; it reuses
    the durable repository which itself reuses the global DB owner."""
    runtime = create_event_runtime(repository=durable_repo)
    wired = runtime.pipeline._repository
    # The durable repository's engine IS the global manager's engine.
    assert wired.session_manager.engine is session_mod.get_session_manager().engine
    # No hidden second engine/sessionmaker is created.
    assert wired.session_manager.session_factory is (
        session_mod.get_session_manager().session_factory
    )


# ---------------------------------------------------------------------------
# Test E — idempotency regression through the wired production pipeline
# (schema-level UNIQUE(event_id) holds; duplicate save collapses to one row)
# ---------------------------------------------------------------------------


def test_pipeline_duplicate_process_is_idempotent(durable_repo) -> None:
    """Sending the same canonical event through the wired production pipeline
    twice yields exactly one durable record (WO-014-019 schema idempotency is
    preserved by the production wiring)."""
    runtime = create_event_runtime(repository=durable_repo)
    event = make_event(event_id="evt-wo014020-idem-1")

    runtime.pipeline.process(event)
    runtime.pipeline.process(event)

    assert durable_repo.count() == 1
    assert durable_repo.get(event.event_id) is not None
