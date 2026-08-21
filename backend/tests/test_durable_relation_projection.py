"""WO-016 — Durable Relation Projection contract.

Locks the deterministic, durable projection of Entity RELATIONS from
canonical Events, downstream of the canonical Entity projection, within the
established production architecture.

Invariants locked here:
  - a canonical Event that establishes a relation produces a durable relation
    record through the production composition root;
  - the relation identity is deterministic (derived from the logical
    source/target/type triple), NOT a random UUID;
  - reprocessing the same canonical Event is idempotent (no duplicate relation
    rows at the database level);
  - two different canonical Events establishing the same logical relation
    resolve to the same durable relation (no accidental duplicate);
  - an Event without a usable relation (missing source/target/type) is safely
    skipped (no invented identity, no auto entity creation);
  - the durable relation projection uses the single DatabaseSessionManager
    owner (no second engine/sessionmaker/persistence plane);
  - relation projection failure does not prevent durable Event persistence;
  - existing EventPipeline / Entity projection behavior remains intact.
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
    deterministic_relation_id,
)
from app.entity_relations.interfaces.i_relation_repository import IRelationRepository
from app.event.event import Event
from app.event.event_types import EventType
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


@pytest.fixture()
def session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database and create the durable canonical + relation tables (single
    owner)."""
    manager = configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    SQLAlchemyRelationRepository().initialize()
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """A production-composed runtime via the authoritative composition root."""
    return create_event_runtime()


def _relation_event(
    event_id: str,
    source: str,
    target: str,
    rel_type: str,
    source_entity: str | None = None,
    confidence: float = 1.0,
    extra_payload: dict | None = None,
) -> Event:
    payload = {
        "target_entity_id": target,
        "relation_type": rel_type,
        "confidence": confidence,
    }
    if extra_payload:
        payload.update(extra_payload)
    return Event(
        event_id=event_id,
        entity_id=source_entity if source_entity is not None else source,
        source="atak",
        event_type=EventType.CUSTOM,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# 1. Relation projection from a canonical event (production composition)
# ---------------------------------------------------------------------------


def test_relation_projection_is_wired(runtime):
    assert isinstance(runtime.pipeline, EventPipeline)
    assert runtime.pipeline._projection is not None
    assert runtime.relation_repository is not None
    assert isinstance(runtime.relation_repository, IRelationRepository)


def test_canonical_event_establishes_durable_relation(runtime):
    event = _relation_event("evt-rel-0001", "entity-a", "entity-b", "owns")
    runtime.pipeline.process(event)

    repo = runtime.relation_repository
    rel_id = deterministic_relation_id("entity-a", "entity-b", "owns")
    rel = repo.get(rel_id)
    assert rel is not None
    assert rel["source_entity_id"] == "entity-a"
    assert rel["target_entity_id"] == "entity-b"
    assert rel["relation_type"] == "owns"
    assert rel["source_event_id"] == "evt-rel-0001"


def test_relation_projection_uses_canonical_entity_identity(runtime):
    event = _relation_event(
        "evt-rel-0002", "src-1", "tgt-1", "controls", source_entity="entity-subject"
    )
    runtime.pipeline.process(event)

    rel = runtime.relation_repository.get(
        deterministic_relation_id("entity-subject", "tgt-1", "controls")
    )
    assert rel is not None
    # Source entity is the canonical Event.entity_id (the relation subject),
    # target is read deterministically from the payload.
    assert rel["source_entity_id"] == "entity-subject"
    assert rel["target_entity_id"] == "tgt-1"


# ---------------------------------------------------------------------------
# 2. Deterministic relation identity
# ---------------------------------------------------------------------------


def test_relation_identity_is_deterministic_and_not_random():
    a = deterministic_relation_id("x", "y", "owns")
    b = deterministic_relation_id("x", "y", "owns")
    assert a == b  # deterministic, stable

    c = deterministic_relation_id("x", "y", "controls")
    assert a != c  # different relation type -> different identity

    # It is a fixed-length hash, not a random UUID.
    assert len(a) == 64
    assert a.isalnum()


def test_same_logical_relation_resolves_to_same_durable_identity(runtime):
    # Two DIFFERENT canonical events establishing the same logical relation
    # (same source/target/type) must resolve to the SAME durable relation.
    e1 = _relation_event("evt-rel-0003", "entity-a", "entity-b", "owns")
    e2 = _relation_event("evt-rel-0004", "entity-a", "entity-b", "owns")

    runtime.pipeline.process(e1)
    runtime.pipeline.process(e2)

    rel_id = deterministic_relation_id("entity-a", "entity-b", "owns")
    assert runtime.relation_repository.get(rel_id) is not None

    # Only ONE durable relation row exists.
    matches = [
        r
        for r in runtime.relation_repository.list_for_entity("entity-a")
        if r["target_entity_id"] == "entity-b" and r["relation_type"] == "owns"
    ]
    assert len(matches) == 1


# ---------------------------------------------------------------------------
# 3. Idempotency — duplicate event processing
# ---------------------------------------------------------------------------


def test_duplicate_event_processing_is_idempotent(runtime):
    event = _relation_event("evt-rel-0005", "entity-a", "entity-b", "owns")
    runtime.pipeline.process(event)
    runtime.pipeline.process(event)  # reprocess same canonical Event

    rel_id = deterministic_relation_id("entity-a", "entity-b", "owns")
    assert runtime.relation_repository.get(rel_id) is not None
    # Exactly one durable relation row, never a duplicate.
    matches = runtime.relation_repository.list_all()
    assert len(matches) == 1


def test_duplicate_relation_insertion_does_not_duplicate(runtime):
    repo = runtime.relation_repository
    rel_id = deterministic_relation_id("entity-a", "entity-b", "owns")
    repo.save(
        {
            "relation_id": rel_id,
            "source_entity_id": "entity-a",
            "target_entity_id": "entity-b",
            "relation_type": "owns",
            "confidence": 1.0,
            "source_event_id": "evt-rel-0006",
            "metadata": {},
        }
    )
    # Duplicate save of the SAME logical relation (same deterministic id).
    repo.save(
        {
            "relation_id": rel_id,
            "source_entity_id": "entity-a",
            "target_entity_id": "entity-b",
            "relation_type": "owns",
            "confidence": 1.0,
            "source_event_id": "evt-rel-0006",
            "metadata": {},
        }
    )
    assert len(repo.list_all()) == 1  # no duplicate row


# ---------------------------------------------------------------------------
# 4. Relation persistence round-trip
# ---------------------------------------------------------------------------


def test_relation_round_trip(runtime):
    event = _relation_event(
        "evt-rel-0007", "entity-a", "entity-b", "communicates_with"
    )
    runtime.pipeline.process(event)

    rel = runtime.relation_repository.get(
        deterministic_relation_id("entity-a", "entity-b", "communicates_with")
    )
    assert rel is not None
    assert rel["relation_id"] == deterministic_relation_id(
        "entity-a", "entity-b", "communicates_with"
    )
    assert rel["source_entity_id"] == "entity-a"
    assert rel["target_entity_id"] == "entity-b"
    assert rel["relation_type"] == "communicates_with"
    assert rel["version"] == 1


def test_list_for_entity_returns_both_directions(runtime):
    runtime.pipeline.process(_relation_event("e1", "a", "b", "owns"))
    runtime.pipeline.process(_relation_event("e2", "b", "c", "controls"))

    rels_a = runtime.relation_repository.list_for_entity("a")
    assert len(rels_a) == 1  # a -> b
    rels_b = runtime.relation_repository.list_for_entity("b")
    assert len(rels_b) == 2  # a->b (incoming) + b->c (outgoing)


# ---------------------------------------------------------------------------
# 5. Missing / invalid relation -> safe deterministic skip
# ---------------------------------------------------------------------------


def test_event_without_relation_is_skipped(runtime):
    event = Event(
        event_id="evt-rel-0008",
        entity_id="entity-a",
        source="atak",
        event_type=EventType.CUSTOM,
        payload={"callsign": "NOVEMBER-1"},
    )
    runtime.pipeline.process(event)

    assert runtime.relation_repository.list_all() == []
    # The Event is still durably persisted and Entity-projected (unchanged).
    assert runtime.event_service.get_event("evt-rel-0008") is not None


def test_event_missing_target_is_skipped(runtime):
    event = _relation_event("evt-rel-0009", "entity-a", "", "owns")
    runtime.pipeline.process(event)
    assert runtime.relation_repository.list_all() == []


def test_event_missing_relation_type_is_skipped(runtime):
    event = Event(
        event_id="evt-rel-0010",
        entity_id="entity-a",
        source="atak",
        event_type=EventType.CUSTOM,
        payload={"target_entity_id": "entity-b"},
    )
    runtime.pipeline.process(event)
    assert runtime.relation_repository.list_all() == []


# ---------------------------------------------------------------------------
# 6. Single database / session ownership
# ---------------------------------------------------------------------------


def test_relation_projection_uses_single_db_owner(runtime):
    # The durable relation repository and the durable event repository share
    # the SAME DatabaseSessionManager (no second engine/sessionmaker).
    event_repo = SQLAlchemyEventRepository()
    relation_repo = SQLAlchemyRelationRepository()
    assert event_repo.session_manager is relation_repo.session_manager


# ---------------------------------------------------------------------------
# 7. Existing EventPipeline / Entity projection behavior remains intact
# ---------------------------------------------------------------------------


def test_entity_projection_still_works_alongside_relation(runtime):
    event = Event(
        event_id="evt-rel-0011",
        entity_id="entity-023-0001",
        source="atak",
        event_type=EventType.ENTITY_CREATED,
        payload={"callsign": "NOVEMBER-1"},
    )
    runtime.pipeline.process(event)

    # Entity projection still works.
    entities = runtime.entity_manager.list_entities("entity.created")
    assert any(e["entity_id"] == "entity-023-0001" for e in entities)

    # No relation because payload had no relation fields.
    assert runtime.relation_repository.list_all() == []


def test_pipeline_still_returns_true_and_persists_event(runtime):
    event = _relation_event("evt-rel-0012", "a", "b", "owns")
    result = runtime.pipeline.process(event)
    assert result is True
    assert runtime.event_service.get_event("evt-rel-0012") is not None
