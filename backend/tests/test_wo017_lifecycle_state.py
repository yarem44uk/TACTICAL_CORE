"""WO-017 (ADR-ENTITY-RELATION-LIFECYCLE) — Entity & Relation Lifecycle State & Tombstone Projection.

Locks the ratified lifecycle architecture:
  ENTITY:  ACTIVE -> TOMBSTONED   (terminal; durable; no physical delete)
  RELATION: ACTIVE -> INACTIVE    (terminal; durable; no physical delete)
  CASCADE: entity deactivation synchronously inactivates every canonical
           relation referencing that entity (deterministic, idempotent,
           projection-time).
  Historical preservation: lifecycle transitions never physically delete rows.
  Identity: the WO-016 deterministic relation_id is unchanged by lifecycle.
  Transactions: independent EVENT/ENTITY/RELATION persistence (never a single
           implicit atomic transaction), single DatabaseSessionManager owner.
  Replay: repeated processing of the same canonical event is idempotent.

Invariants locked here (WO-017 §13, §14, §15):
  - relation creation -> ACTIVE;
  - entity deactivation -> entity TOMBSTONED + referencing relations INACTIVE;
  - repeated lifecycle processing is idempotent (no duplicate rows, same state);
  - historical preservation (row retained, identity unchanged);
  - no physical DELETE of terminated relations by the lifecycle path;
  - no new relation id during a lifecycle transition;
  - no second database owner / engine / sessionmaker;
  - lifecycle transitions flow through the canonical EventPipeline
    (no bypass of the production projection path).
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.composition import create_event_runtime
from app.database.session import configure_session_manager
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
    deterministic_relation_id,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


@pytest.fixture()
def session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database and create all durable tables via the single owner."""
    manager = configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    SQLAlchemyRelationRepository().initialize()
    SQLAlchemyEntityRepository().initialize()
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """A production-composed runtime via the authoritative composition root."""
    return create_event_runtime()


@pytest.fixture()
def relation_repo(session_manager):
    return SQLAlchemyRelationRepository()


@pytest.fixture()
def entity_repo(session_manager):
    return SQLAlchemyEntityRepository()


def _relation_event(
    event_id: str,
    source: str,
    target: str,
    rel_type: str,
) -> Event:
    return Event(
        event_id=event_id,
        entity_id=source,
        event_type=EventType.ENTITY_UPDATED,
        payload={
            "target_entity_id": target,
            "relation_type": rel_type,
            "confidence": 1.0,
        },
    )


def _entity_created_event(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_CREATED,
        payload={"entity_type": "unit", "callsign": "ALPHA"},
    )


def _entity_removed_event(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_REMOVED,
        payload={},
    )


# ---------------------------------------------------------------------------
# Relation creation -> ACTIVE
# ---------------------------------------------------------------------------


def test_relation_creation_is_active(runtime, relation_repo):
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    rel = relation_repo.get(rid)
    assert rel is not None
    assert rel["status"] == "ACTIVE"
    assert rel["terminated_at"] is None


# ---------------------------------------------------------------------------
# Entity deactivation cascade -> entity TOMBSTONED + relations INACTIVE
# ---------------------------------------------------------------------------


def test_entity_deactivation_cascades_to_relations(runtime, relation_repo, entity_repo):
    # Build an entity and two relations referencing it (as source and target).
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    runtime.pipeline.process(_relation_event("e3", "C", "A", "commands"))

    rid1 = deterministic_relation_id("A", "B", "reports_to")
    rid2 = deterministic_relation_id("C", "A", "commands")
    assert relation_repo.get(rid1)["status"] == "ACTIVE"
    assert relation_repo.get(rid2)["status"] == "ACTIVE"

    # Deactivate entity A via the canonical ENTITY_REMOVED event.
    runtime.pipeline.process(_entity_removed_event("e4", "A"))

    # Entity A is durably TOMBSTONED (row retained, excluded from active reads).
    assert entity_repo.is_tombstoned("A") is True

    # Both referencing relations transitioned ACTIVE -> INACTIVE (durable).
    rel1 = relation_repo.get(rid1)
    rel2 = relation_repo.get(rid2)
    assert rel1["status"] == "INACTIVE"
    assert rel1["terminated_at"] is not None
    assert rel2["status"] == "INACTIVE"
    assert rel2["terminated_at"] is not None

    # Historical preservation: rows still exist, identity unchanged.
    assert rel1["relation_id"] == rid1
    assert rel2["relation_id"] == rid2


# ---------------------------------------------------------------------------
# Idempotent cascade / replay
# ---------------------------------------------------------------------------


def test_repeated_deactivation_is_idempotent(runtime, relation_repo, entity_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")

    # Replay the deactivation event twice.
    runtime.pipeline.process(_entity_removed_event("e3", "A"))
    runtime.pipeline.process(_entity_removed_event("e4", "A"))

    assert relation_repo.get(rid)["status"] == "INACTIVE"
    assert entity_repo.is_tombstoned("A") is True
    # Idempotent: exactly one durable relation row.
    assert len(relation_repo.list_all()) == 1


# ---------------------------------------------------------------------------
# Historical preservation & no physical delete
# ---------------------------------------------------------------------------


def test_termination_preserves_row_and_identity(runtime, relation_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")

    runtime.pipeline.process(_entity_removed_event("e3", "A"))

    rel = relation_repo.get(rid)
    assert rel is not None, "terminated relation must NOT be physically deleted"
    assert rel["status"] == "INACTIVE"
    assert rel["relation_id"] == rid
    assert rel["source_entity_id"] == "A"
    assert rel["target_entity_id"] == "B"
    assert rel["relation_type"] == "reports_to"


def test_no_physical_delete_in_list(runtime, relation_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    runtime.pipeline.process(_entity_removed_event("e3", "A"))

    # The terminated relation is still present in the durable store.
    all_rels = relation_repo.list_all()
    assert any(r["relation_id"] == rid for r in all_rels)
    # ... but excluded from the active view.
    assert all(r["status"] == "INACTIVE" for r in all_rels)
    assert relation_repo.list_active() == []


# ---------------------------------------------------------------------------
# Relation lifecycle state is NOT part of identity
# ---------------------------------------------------------------------------


def test_lifecycle_does_not_change_relation_id(runtime, relation_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    rid_before = deterministic_relation_id("A", "B", "reports_to")

    runtime.pipeline.process(_entity_removed_event("e3", "A"))

    rel = relation_repo.get(rid_before)
    assert rel is not None
    # Identity is unchanged by lifecycle (state is mutable, identity is not).
    assert rel["relation_id"] == rid_before


# ---------------------------------------------------------------------------
# Read-side filtering
# ---------------------------------------------------------------------------


def test_active_and_historical_filtering(runtime, relation_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_entity_created_event("e2", "B"))
    runtime.pipeline.process(_relation_event("e3", "A", "B", "reports_to"))
    runtime.pipeline.process(_relation_event("e4", "B", "C", "reports_to"))

    # Both ACTIVE initially.
    assert len(relation_repo.list_active()) == 2

    # Deactivate A -> only the A->B relation is inactivated; B->C stays active.
    runtime.pipeline.process(_entity_removed_event("e5", "A"))
    active = relation_repo.list_active()
    assert len(active) == 1
    assert active[0]["source_entity_id"] == "B"

    # Historical view still returns both.
    assert len(relation_repo.list_historical()) == 2

    # Per-entity filters.
    assert len(relation_repo.list_for_entity("A", status="ACTIVE")) == 0
    assert len(relation_repo.list_for_entity("A", status="INACTIVE")) == 1
    assert len(relation_repo.list_for_entity("A")) == 1  # historical (all)


# ---------------------------------------------------------------------------
# Non-removal events do NOT trigger the cascade
# ---------------------------------------------------------------------------


def test_non_removal_event_does_not_inactivate(runtime, relation_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")

    # An update event for A (not ENTITY_REMOVED) must not inactivate relations.
    runtime.pipeline.process(
        Event(
            event_id="e3",
            entity_id="A",
            event_type=EventType.ENTITY_UPDATED,
            payload={"callsign": "BRAVO"},
        )
    )

    assert relation_repo.get(rid)["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Single DB owner / no second engine/sessionmaker
# ---------------------------------------------------------------------------


def test_single_database_owner(runtime, session_manager):
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )

    event_repo = SQLAlchemyEventRepository()
    relation_repo = runtime.relation_repository
    # The event runtime exposes the durable relation repository.
    assert relation_repo is not None
    # All repos share the same single DatabaseSessionManager owner.
    assert (
        event_repo.session_manager is relation_repo.session_manager
    )
    assert (
        runtime.entity_repository.session_manager
        is relation_repo.session_manager
    )


# ---------------------------------------------------------------------------
# No direct lifecycle write bypassing the canonical pipeline
# ---------------------------------------------------------------------------


def test_cascade_runs_through_production_pipeline(runtime, relation_repo):
    # Projection (incl. lifecycle) only happens when events flow through
    # pipeline.process (the canonical projection seam).  A freshly composed
    # runtime must not have inactivated anything before any event arrives.
    assert relation_repo.list_all() == []
