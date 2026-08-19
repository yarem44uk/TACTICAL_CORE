"""WO-014-024 — Canonical Entity Read-Side + Projection Observability.

Verifies the two WO-014-024 gaps against the real production composition:

  G2 — a thin, canonical, read-only read surface over the authoritative
       EntityManager (EntityReadService), exposed by create_event_runtime().

  G3 — projection observability/health signal (ProjectionObservability):
       last projected event_id, current Entity count, projection failure
       count.  Strictly diagnostic; never gates durable Event persistence.

Invariants locked here:
  - get(entity_id) returns the correct Entity
  - get_by_type(entity_type) returns deterministic results
  - list() returns persisted Entities
  - read operations do NOT mutate state and do NOT create Entities
  - the read surface delegates to the canonical EntityManager
  - production composition exposes the read surface
  - successful projection updates last_projected_event_id
  - Entity count is reported correctly
  - projection failure increments the failure count
  - projection failure does NOT mark Event persistence as failed
  - repeated/idempotent processing does not corrupt counters
  - observability introduces NO second DB owner
  - production runtime constructs successfully
  - existing Event -> Entity projection still works (WO-014-022/023)
  - WO-014-023 failure isolation remains intact
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.entity_read.entity_read_service import EntityReadService
from app.entity_read.projection_observability import (
    ProjectionObservability,
    HEALTH_COMPONENT,
)
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


def _entity_event(event_id, entity_id, entity_type=EventType.ENTITY_CREATED,
                  payload=None):
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        source="atak",
        event_type=entity_type,
        payload=payload or {"callsign": event_id},
    )


# ---------------------------------------------------------------------------
# READ SIDE — surface exposed by production composition
# ---------------------------------------------------------------------------


def test_production_composition_exposes_read_surface(runtime):
    assert isinstance(runtime.entity_read, EntityReadService)
    # The read surface is backed by the authoritative EntityManager.
    assert runtime.entity_read._entity_manager is runtime.entity_manager


def test_get_returns_correct_entity(runtime):
    runtime.pipeline.process(_entity_event("evt-024-0001", "entity-024-0001"))

    state = runtime.entity_read.get("entity-024-0001")
    assert state is not None
    assert state["entity_id"] == "entity-024-0001"
    assert state["attributes"]["callsign"] == "evt-024-0001"


def test_get_with_entity_type_filter(runtime):
    runtime.pipeline.process(
        _entity_event("evt-024-0002", "entity-024-0002")
    )
    state = runtime.entity_read.get(
        "entity-024-0002", entity_type="entity.created"
    )
    assert state is not None
    assert state["entity_id"] == "entity-024-0002"
    # Wrong type -> no match.
    assert (
        runtime.entity_read.get("entity-024-0002", entity_type="entity.updated")
        is None
    )


def test_get_by_type_returns_deterministic_results(runtime):
    runtime.pipeline.process(
        _entity_event("evt-024-0003", "entity-024-0003")
    )
    runtime.pipeline.process(
        _entity_event("evt-024-0004", "entity-024-0004")
    )
    runtime.pipeline.process(
        _entity_event(
            "evt-024-0005", "entity-024-0005",
            entity_type=EventType.ENTITY_UPDATED,
            payload={"seq": 1},
        )
    )

    created = runtime.entity_read.get_by_type("entity.created")
    updated = runtime.entity_read.get_by_type("entity.updated")

    assert {e["entity_id"] for e in created} == {
        "entity-024-0003", "entity-024-0004"
    }
    assert {e["entity_id"] for e in updated} == {"entity-024-0005"}


def test_list_returns_persisted_entities(runtime):
    runtime.pipeline.process(_entity_event("evt-024-0006", "entity-024-0006"))
    runtime.pipeline.process(_entity_event("evt-024-0007", "entity-024-0007"))

    entities = runtime.entity_read.list()
    ids = {e["entity_id"] for e in entities}
    assert {"entity-024-0006", "entity-024-0007"} <= ids


def test_read_operations_do_not_mutate_state(runtime):
    runtime.pipeline.process(_entity_event("evt-024-0008", "entity-024-0008"))
    before = runtime.entity_manager.get_entity("entity.created", "entity-024-0008")

    # Perform only read operations.
    runtime.entity_read.get("entity-024-0008")
    runtime.entity_read.get_by_type("entity.created")
    runtime.entity_read.list()

    after = runtime.entity_manager.get_entity("entity.created", "entity-024-0008")
    assert before == after
    # No new Entities were created by reads.
    assert len(runtime.entity_read.list()) == 1


# ---------------------------------------------------------------------------
# OBSERVABILITY
# ---------------------------------------------------------------------------


def test_successful_projection_updates_last_projected_event_id(runtime):
    assert runtime.projection_observability.last_projected_event_id is None

    runtime.pipeline.process(_entity_event("evt-024-0010", "entity-024-0010"))

    assert runtime.projection_observability.last_projected_event_id == "evt-024-0010"


def test_entity_count_is_reported_correctly(runtime):
    runtime.pipeline.process(_entity_event("evt-024-0011", "entity-024-0011"))
    runtime.pipeline.process(_entity_event("evt-024-0012", "entity-024-0012"))
    runtime.pipeline.process(_entity_event("evt-024-0013", "entity-024-0013"))

    assert runtime.projection_observability.entity_count() == 3
    assert runtime.projection_observability.snapshot()["entity_count"] == 3


def test_projection_failure_increments_failure_count(runtime):
    def _exploding_projection(event):
        raise RuntimeError("projection exploded")

    runtime.pipeline.set_projection(
        runtime.projection_observability.wrap(_exploding_projection)
    )

    event = _entity_event("evt-024-0014", "entity-024-0014")
    # Pipeline swallows the projection exception (best-effort, WO-014-023).
    result = runtime.pipeline.process(event)
    assert result is True

    assert runtime.projection_observability.projection_failure_count == 1
    # last_projected_event_id must NOT have advanced on failure.
    assert runtime.projection_observability.last_projected_event_id is None


def test_projection_failure_does_not_mark_event_persistence_failed(runtime):
    def _exploding_projection(event):
        raise RuntimeError("projection exploded")

    runtime.pipeline.set_projection(
        runtime.projection_observability.wrap(_exploding_projection)
    )

    event = _entity_event("evt-024-0015", "entity-024-0015")
    result = runtime.pipeline.process(event)
    assert result is True

    # The canonical Event is STILL durably persisted (source of truth).
    persisted = runtime.event_service.get_event("evt-024-0015")
    assert persisted is not None
    assert persisted.event_id == "evt-024-0015"


def test_repeated_processing_does_not_corrupt_counters(runtime):
    event = _entity_event("evt-024-0016", "entity-024-0016")

    runtime.pipeline.process(event)
    runtime.pipeline.process(event)  # idempotent reprocess
    runtime.pipeline.process(event)

    snap = runtime.projection_observability.snapshot()
    # Idempotent reprocessing of the same Event -> exactly one Entity.
    assert snap["entity_count"] == 1
    assert snap["projection_failure_count"] == 0
    assert snap["last_projected_event_id"] == "evt-024-0016"


def test_observability_introduces_no_second_db_owner(runtime):
    # The observability recorder holds no engine/session of its own; it only
    # reports on the EntityManager and the existing global HealthManager.
    assert not hasattr(runtime.projection_observability, "engine")
    assert not hasattr(runtime.projection_observability, "sessionmaker")
    assert runtime.projection_observability.snapshot() is not None


def test_observability_surfaces_health_component(runtime):
    from app.core.health.health import get_health_manager

    runtime.pipeline.process(_entity_event("evt-024-0017", "entity-024-0017"))

    health = get_health_manager().get_component_health(HEALTH_COMPONENT)
    assert health is not None
    assert health.details.get("last_projected_event_id") == "evt-024-0017"


# ---------------------------------------------------------------------------
# INTEGRATION
# ---------------------------------------------------------------------------


def test_production_runtime_constructs_with_read_side_and_observability(runtime):
    assert isinstance(runtime.pipeline, EventPipeline)
    assert runtime.entity_read is not None
    assert runtime.projection_observability is not None
    # Projection seam is wired (through the observability wrapper).
    assert runtime.pipeline._projection is not None


def test_existing_event_to_entity_projection_still_works(runtime):
    runtime.pipeline.process(_entity_event("evt-024-0018", "entity-024-0018"))
    state = runtime.entity_manager.get_entity("entity.created", "entity-024-0018")
    assert state is not None
    assert state["attributes"]["callsign"] == "evt-024-0018"


def test_wo014023_failure_isolation_remains_intact(runtime):
    def _exploding_projection(event):
        raise RuntimeError("projection exploded")

    runtime.pipeline.set_projection(
        runtime.projection_observability.wrap(_exploding_projection)
    )
    event = _entity_event("evt-024-0019", "entity-024-0019")

    # Pipeline reports success and does not raise (best-effort isolation).
    assert runtime.pipeline.process(event) is True
    # Durable persistence intact, projection failure observable.
    assert runtime.event_service.get_event("evt-024-0019") is not None
    assert runtime.projection_observability.projection_failure_count == 1
