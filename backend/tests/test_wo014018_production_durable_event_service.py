"""
WO-014-018 tests: Canonical durable repository promoted to the authoritative
production EventService composition path.

Proves that the REAL authoritative production path:

    create_production_runtime()
        |-> create_event_runtime()
              |-> EventRuntime.event_service
                    |-> DurableCanonicalEventRepository
                          |-> WO-014-016 SQLAlchemy durable impl
                          |-> existing DatabaseSessionManager

now exposes a canonical ``EventService`` backed by the durable canonical
repository (``DurableCanonicalEventRepository``) — NOT the in-memory
repository — and that this authoritative path can persist and retrieve
canonical ``Event`` objects durably.

WO-014-018 is strictly additive and confined to the canonical composition
root. The legacy persistence domain and the WO-014-016 durable
implementation are never modified.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

import app.database.session as session_mod
from app.bootstrap import ProductionRuntime, create_production_runtime
from app.composition import EventRuntime, create_event_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
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


def make_event(
    *,
    event_id: str,
    entity_id: str = "entity-018",
    event_type: EventType = EventType.SIGNAL_RECEIVED,
    source: str = "wo014018-source",
    payload: Optional[dict] = None,
    metadata: Optional[EventMetadata] = None,
    timestamp: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=event_type,
        timestamp=timestamp
        or datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload if payload is not None else {"k": "v"},
        metadata=metadata if metadata is not None else EventMetadata(
            tags=["wo014018"],
            properties={"nested": {"level": 2}},
            correlation_id="corr-wo014018",
        ),
        created_at=created_at
        or datetime(2026, 8, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. authoritative runtime wiring (create_event_runtime)
# ---------------------------------------------------------------------------


def test_create_event_runtime_wires_durable_event_service():
    """create_event_runtime() now returns an EventRuntime whose event_service
    is backed by the durable canonical repository (not the in-memory one)."""
    runtime = create_event_runtime()
    assert isinstance(runtime, EventRuntime)
    assert hasattr(runtime, "event_service")
    assert isinstance(runtime.event_service._repository, DurableCanonicalEventRepository)
    assert not isinstance(runtime.event_service._repository, MemoryEventRepository)


def test_create_event_runtime_preserves_existing_fields():
    """The existing EventRuntime fields (pipeline, manager, dispatcher) remain
    intact after the additive event_service wiring."""
    runtime = create_event_runtime()
    assert runtime.pipeline is not None
    assert runtime.plugin_manager is not None
    assert runtime.plugin_dispatcher is not None
    assert runtime.pipeline._dispatcher is runtime.plugin_dispatcher


def test_create_event_runtime_accepts_injected_repository():
    """Callers may inject an alternative IEventRepository for testing; the
    EventService then uses that injected repository."""
    mem = MemoryEventRepository()
    runtime = create_event_runtime(repository=mem)
    assert runtime.event_service._repository is mem
    assert isinstance(runtime.event_service._repository, MemoryEventRepository)


# ---------------------------------------------------------------------------
# 2. production bootstrap wiring (acceptance) — real authoritative path
# ---------------------------------------------------------------------------


def test_production_bootstrap_exposes_durable_event_service(global_session_manager):
    """The REAL authoritative path create_production_runtime() ->
    create_event_runtime() -> EventRuntime now exposes an EventService backed
    by the durable canonical repository."""
    rt = create_production_runtime()
    assert isinstance(rt, ProductionRuntime)
    event_service = rt.event_runtime.event_service
    assert isinstance(event_service._repository, DurableCanonicalEventRepository)
    assert not isinstance(event_service._repository, MemoryEventRepository)


def test_production_round_trip_through_authoritative_path(global_session_manager):
    """A canonical Event persisted through the authoritative production
    EventService can be retrieved as a canonical Event, with all fields
    preserved. Proves real durable persistence via the existing global
    DatabaseSessionManager."""
    rt = create_production_runtime()
    repo = rt.event_runtime.event_service._repository
    # Ensure the durable table exists on the configured global manager.
    repo.initialize()

    created = make_event(
        event_id="evt-wo014018-prod-1",
        entity_id="entity-018",
        event_type=EventType.OBSERVATION_CREATED,
        source="sensor-018",
        payload={"coords": {"lat": 49.0, "lon": 28.0}, "values": [4, 5, 6]},
        metadata=EventMetadata(
            tags=["a", "b"],
            properties={"nested": {"deep": {"y": 2}}},
            correlation_id="corr-prod-1",
        ),
        timestamp=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 15, 10, 30, 0, tzinfo=timezone.utc),
    )

    rt.event_runtime.event_service.save_event(created)
    restored = rt.event_runtime.event_service.get_event("evt-wo014018-prod-1")

    # canonical Event returned, not an ORM object.
    assert type(restored) is Event
    assert not isinstance(restored, type(repo))

    # event_id / entity_id preserved.
    assert restored.event_id == created.event_id
    assert restored.entity_id == created.entity_id
    # event_type preserved (canonical enum).
    assert restored.event_type == EventType.OBSERVATION_CREATED
    assert isinstance(restored.event_type, EventType)
    # timestamp preserved (SQLite tzinfo normalization, documented WO-014-016).
    assert restored.timestamp.replace(tzinfo=timezone.utc) == created.timestamp
    # source preserved.
    assert restored.source == created.source
    # payload preserved (incl. nested).
    assert restored.payload == created.payload
    assert restored.payload["coords"] == {"lat": 49.0, "lon": 28.0}
    # metadata preserved (incl. nested + correlation_id).
    assert restored.metadata.to_dict() == created.metadata.to_dict()
    assert restored.metadata.correlation_id == "corr-prod-1"
    # created_at preserved exactly (deterministic instant).
    assert restored.created_at.replace(tzinfo=timezone.utc) == created.created_at


def test_production_duplicate_save_idempotent(global_session_manager):
    """The authoritative durable path remains idempotent: saving the same
    event_id twice yields exactly one record."""
    rt = create_production_runtime()
    repo = rt.event_runtime.event_service._repository
    repo.initialize()

    event = make_event(event_id="evt-wo014018-idem")
    rt.event_runtime.event_service.save_event(event)
    rt.event_runtime.event_service.save_event(event)
    assert repo.count() == 1
    assert rt.event_runtime.event_service.get_event("evt-wo014018-idem") is not None


# ---------------------------------------------------------------------------
# 3. session manager reuse
# ---------------------------------------------------------------------------


def test_durable_repo_uses_existing_database_session_manager(global_session_manager):
    """The durable repository on the authoritative path binds the existing
    (configured) DatabaseSessionManager — no second engine/session owner."""
    rt = create_production_runtime()
    repo = rt.event_runtime.event_service._repository
    from app.database.session import DatabaseSessionManager

    assert isinstance(repo.session_manager, DatabaseSessionManager)
    # The configured global manager IS the one the repo uses.
    assert repo.session_manager is session_mod.get_session_manager()
