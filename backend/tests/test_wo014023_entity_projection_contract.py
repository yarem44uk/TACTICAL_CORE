"""WO-014-023 — Entity projection contract / deterministic state update.

Locks the deterministic production contract for canonical Event -> Entity
state projection established by WO-014-022.  The projection is:

    canonical Event
        -> durable Event persistence (source of truth)
        -> EntityBridge -> EntityManager -> Entity state  (best-effort)

This WO-014-023 suite focuses on the deterministic contract invariants that
WO-014-022's suite does NOT already cover, in particular the "event without a
usable Entity identity" case (must be safely and deterministically skipped,
never invented), plus confirmation that the projection contract is
source-agnostic and deterministic across the authoritative composition root.

Invariants locked here:
  - deterministic Event -> Entity projection through production composition
  - repeated processing of the same Event produces identical, non-duplicated
    Entity state
  - two different Events sharing the same Entity.id update the SAME Entity
  - an Event with NO usable Entity identity is safely skipped (no projection,
    no invented Entity), and does not error or interrupt the pipeline
  - projection is source-agnostic (not coupled to a specific source adapter)
  - projection failure does not prevent durable Event persistence
  - Entity identity stays distinct from canonical Event identity
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_types import EventType
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


@pytest.fixture()
def session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database and create the durable canonical table (single owner)."""
    manager = configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """A production-composed runtime via the authoritative composition root."""
    return create_event_runtime()


# ---------------------------------------------------------------------------
# Contract 1 — deterministic Event -> Entity projection (production composition)
# ---------------------------------------------------------------------------


def test_projection_is_deterministic_and_wired(runtime):
    # The authoritative composition root wires the projection seam.
    assert isinstance(runtime.pipeline, EventPipeline)
    assert runtime.pipeline._projection is not None
    assert runtime.entity_manager is not None


def test_deterministic_projection_repeated_processing_is_idempotent(runtime):
    event = Event(
        event_id="evt-023-0001",
        entity_id="entity-023-0001",
        source="atak",
        event_type=EventType.ENTITY_CREATED,
        payload={"callsign": "NOVEMBER-1", "status": "active"},
    )

    runtime.pipeline.process(event)
    runtime.pipeline.process(event)  # reprocess same canonical Event

    entities = runtime.entity_manager.list_entities("entity.created")
    ids = [e["entity_id"] for e in entities]
    assert ids.count("entity-023-0001") == 1  # exactly one Entity record

    # Deterministic resulting state: same attributes after reprocessing.
    state = runtime.entity_manager.get_entity("entity.created", "entity-023-0001")
    assert state is not None
    assert state["attributes"]["callsign"] == "NOVEMBER-1"
    assert state["attributes"]["status"] == "active"


# ---------------------------------------------------------------------------
# Contract 2 — two Events, same Entity.id, update the SAME Entity
# ---------------------------------------------------------------------------


def test_same_entity_id_across_events_updates_single_entity(runtime):
    e1 = Event(
        event_id="evt-023-0002",
        entity_id="entity-023-0002",
        source="atak",
        event_type=EventType.ENTITY_UPDATED,
        payload={"callsign": "OSCAR-1", "seq": 1},
    )
    e2 = Event(
        event_id="evt-023-0003",
        entity_id="entity-023-0002",  # same Entity, different Event
        source="atak",
        event_type=EventType.ENTITY_UPDATED,
        payload={"callsign": "OSCAR-1", "seq": 2},
    )

    runtime.pipeline.process(e1)
    runtime.pipeline.process(e2)

    matches = [
        e for e in runtime.entity_manager.list_entities("entity.updated")
        if e["entity_id"] == "entity-023-0002"
    ]
    assert len(matches) == 1  # SAME Entity updated, not duplicated
    assert matches[0]["attributes"]["seq"] == 2  # latest update applied


# ---------------------------------------------------------------------------
# Contract 3 — Event with NO usable Entity identity is safely skipped
# ---------------------------------------------------------------------------


def test_event_without_entity_identity_is_safely_skipped(runtime):
    # entity_id is None -> the bridge must deterministically skip projection
    # and must NOT invent an Entity identity.
    event = Event(
        event_id="evt-023-0004",
        entity_id=None,  # no usable Entity identity
        source="atak",
        event_type=EventType.OBSERVATION_CREATED,
        payload={"text": "no entity here"},
    )

    # Must not raise; pipeline reports success.
    result = runtime.pipeline.process(event)
    assert result is True

    # The canonical Event is still durably persisted (source of truth).
    persisted = runtime.event_service.get_event("evt-023-0004")
    assert persisted is not None
    assert persisted.event_id == "evt-023-0004"

    # No Entity state was created (no invented identity).
    entities = runtime.entity_manager.list_entities()
    assert entities == []


def test_event_with_blank_entity_identity_is_safely_skipped(runtime):
    # entity_id is an empty string -> treated as no usable identity.
    event = Event(
        event_id="evt-023-0005",
        entity_id="",
        source="atak",
        event_type=EventType.SIGNAL_RECEIVED,
        payload={"freq": "123.45"},
    )

    result = runtime.pipeline.process(event)
    assert result is True

    persisted = runtime.event_service.get_event("evt-023-0005")
    assert persisted is not None

    # No Entity projection occurred.
    assert runtime.entity_manager.list_entities() == []


# ---------------------------------------------------------------------------
# Contract 4 — projection is source-agnostic (not source-coupled)
# ---------------------------------------------------------------------------


def test_projection_is_source_agnostic(runtime):
    # Identical projection behavior across different source adapters.
    for source, eid in [("atak", "entity-023-0006"), ("signal", "entity-023-0007")]:
        event = Event(
            event_id=f"evt-023-src-{source}",
            entity_id=eid,
            source=source,
            event_type=EventType.ENTITY_CREATED,
            payload={"source": source},
        )
        runtime.pipeline.process(event)
        state = runtime.entity_manager.get_entity("entity.created", eid)
        assert state is not None
        assert state["attributes"]["source"] == source


# ---------------------------------------------------------------------------
# Contract 5 — projection failure does not prevent durable Event persistence
# ---------------------------------------------------------------------------


def test_projection_failure_does_not_erase_durable_event(session_manager):
    runtime = create_event_runtime()

    def _exploding_projection(event):
        raise RuntimeError("projection exploded")

    runtime.pipeline.set_projection(_exploding_projection)

    event = Event(
        event_id="evt-023-0008",
        entity_id="entity-023-0008",
        source="atak",
        event_type=EventType.ENTITY_CREATED,
        payload={"callsign": "PAPA-1"},
    )

    # Must not raise; pipeline reports success despite projection failure.
    result = runtime.pipeline.process(event)
    assert result is True

    # The canonical Event is STILL durably persisted.
    persisted = runtime.event_service.get_event("evt-023-0008")
    assert persisted is not None
    assert persisted.event_id == "evt-023-0008"


# ---------------------------------------------------------------------------
# Contract 6 — Entity identity is distinct from canonical Event identity
# ---------------------------------------------------------------------------


def test_entity_identity_distinct_from_event_identity(runtime):
    event = Event(
        event_id="evt-023-0009",
        entity_id="entity-023-0009",
        source="atak",
        event_type=EventType.ENTITY_CREATED,
        payload={"name": "QUEBEC"},
    )
    runtime.pipeline.process(event)

    persisted = runtime.event_service.get_event("evt-023-0009")
    state = runtime.entity_manager.get_entity("entity.created", "entity-023-0009")

    assert persisted is not None
    assert state is not None
    assert state["entity_id"] == "entity-023-0009"
    assert state["entity_id"] != persisted.event_id  # distinct identities
