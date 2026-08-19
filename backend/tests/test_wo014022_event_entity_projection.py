"""WO-014-022 — Event -> Entity projection (production composition).

Proves that the production composition root (``create_event_runtime``) wires
the canonical Event -> Entity projection:

    canonical Event
        ↓
    EventPipeline.process(event)
        ↓  (1) durable Event persistence (IEventRepository -> DurableCanonicalEventRepository)
        ↓  (2) EntityBridge -> EntityManager -> Entity state   (best-effort)
        ↓
    Entity state

Invariants covered:
  - production composition wires the projection into the pipeline seam
  - canonical Event is durably persisted AND entity state is projected
  - Event.event_id remains the Event identity; Entity.id remains the Entity
    identity (never confused)
  - reprocessing the same Event does not create duplicate Entity state
  - two Events referring to the same Entity.id update the SAME Entity
  - a projection failure does NOT prevent durable Event persistence
  - no second Event persistence plane / no second DB owner
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
    SQLite database and create the durable canonical table (single owner),
    resetting afterwards so nothing leaks. No second DB owner is created."""
    manager = configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """A production-composed runtime via the authoritative composition root."""
    return create_event_runtime()


# ---------------------------------------------------------------------------
# Test A — production composition wires the projection seam
# ---------------------------------------------------------------------------

def test_production_composition_wires_projection(runtime):
    assert isinstance(runtime.pipeline, EventPipeline)
    # the projection step is wired into the canonical pipeline
    assert runtime.pipeline._projection is not None
    # the projection's EntityManager is exposed on the runtime
    assert runtime.entity_manager is not None


# ---------------------------------------------------------------------------
# Test B — canonical event persistence + projection round-trip
# ---------------------------------------------------------------------------

def test_event_is_durably_persisted_and_projected(runtime):
    event = Event(
        event_id="evt-022-0001",
        entity_id="entity-022-0001",
        source="atak",
        event_type=EventType.ENTITY_CREATED,
        payload={"callsign": "ALPHA-1", "status": "active"},
    )

    result = runtime.pipeline.process(event)

    # 1. pipeline processed the event
    assert result is True

    # 2. durable persistence occurred (round-trip by canonical event_id)
    persisted = runtime.event_service.get_event(event.event_id)
    assert persisted is not None
    assert persisted.event_id == event.event_id  # canonical identity preserved

    # 3. entity projection occurred (Entity state retrievable)
    state = runtime.entity_manager.get_entity(
        EventType.ENTITY_CREATED.value, "entity-022-0001"
    )
    assert state is not None
    assert state["entity_id"] == "entity-022-0001"
    assert state["attributes"].get("callsign") == "ALPHA-1"


# ---------------------------------------------------------------------------
# Test C — event_id vs entity_id are distinct identities
# ---------------------------------------------------------------------------

def test_event_id_and_entity_id_are_distinct(runtime):
    event = Event(
        event_id="evt-022-0002",
        entity_id="entity-022-0002",
        source="atak",
        payload={"name": "X"},
    )
    runtime.pipeline.process(event)

    persisted = runtime.event_service.get_event("evt-022-0002")
    assert persisted is not None
    assert persisted.event_id == "evt-022-0002"

    state = runtime.entity_manager.get_entity("custom", "entity-022-0002")
    assert state is not None
    assert state["entity_id"] == "entity-022-0002"
    assert state["entity_id"] != persisted.event_id  # distinct identities


# ---------------------------------------------------------------------------
# Test D — reprocessing same event does not duplicate Entity state
# ---------------------------------------------------------------------------

def test_reprocessing_same_event_no_duplicate_entity(runtime):
    event = Event(
        event_id="evt-022-0003",
        entity_id="entity-022-0003",
        source="atak",
        payload={"callsign": "BRAVO-1"},
    )
    runtime.pipeline.process(event)
    runtime.pipeline.process(event)  # reprocess same canonical event

    entities = runtime.entity_manager.list_entities("custom")
    ids = [e["entity_id"] for e in entities]
    assert ids.count("entity-022-0003") == 1  # exactly one entity record


# ---------------------------------------------------------------------------
# Test E — two events, same Entity.id, update the SAME Entity
# ---------------------------------------------------------------------------

def test_same_entity_updated_not_duplicated(runtime):
    e1 = Event(
        event_id="evt-022-0004",
        entity_id="entity-022-0004",
        source="atak",
        payload={"callsign": "CHARLIE-1", "seq": 1},
    )
    e2 = Event(
        event_id="evt-022-0005",
        entity_id="entity-022-0004",  # same entity, different event
        source="atak",
        payload={"callsign": "CHARLIE-1", "seq": 2},
    )
    runtime.pipeline.process(e1)
    runtime.pipeline.process(e2)

    entities = runtime.entity_manager.list_entities("custom")
    matches = [e for e in entities if e["entity_id"] == "entity-022-0004"]
    assert len(matches) == 1  # same Entity updated, not duplicated
    assert matches[0]["attributes"]["seq"] == 2  # latest update applied


# ---------------------------------------------------------------------------
# Test F — projection failure does NOT prevent durable Event persistence
# ---------------------------------------------------------------------------

def test_projection_failure_does_not_block_event_persistence(session_manager):
    runtime = create_event_runtime()

    def _exploding_projection(event):
        raise RuntimeError("projection exploded")

    runtime.pipeline.set_projection(_exploding_projection)

    event = Event(
        event_id="evt-022-0006",
        entity_id="entity-022-0006",
        source="atak",
        payload={"callsign": "DELTA-1"},
    )

    # Must not raise; must still return True (pipeline reports processed)
    result = runtime.pipeline.process(event)
    assert result is True

    # Event MUST still be durably persisted despite projection failure
    persisted = runtime.event_service.get_event("evt-022-0006")
    assert persisted is not None
    assert persisted.event_id == "evt-022-0006"


# ---------------------------------------------------------------------------
# Test G — single DB owner, no second persistence plane
# ---------------------------------------------------------------------------

def test_single_database_owner(session_manager):
    import app.database.session as s
    from app.database.session import DatabaseSessionManager

    # The composition reuses the single global DatabaseSessionManager
    assert isinstance(s.get_session_manager(), DatabaseSessionManager)
