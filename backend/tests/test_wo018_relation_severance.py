"""WO-018 — Explicit Relation Severance (RELATION_SEVERED -> ACTIVE -> INACTIVE).

Locks the ratified WO-018 architecture (Architecture Authority Directive):

  * ``RELATION_SEVERED`` is a NEW canonical EventType representing explicit,
    operator/system-level severance of a SINGLE existing relation.
  * It is architecturally DISTINCT from ``ENTITY_REMOVED`` (WO-017): it affects
    ONLY the identified relation (ACTIVE -> INACTIVE, durable terminal), and
    NEVER mutates either endpoint entity lifecycle state and NEVER cascades to
    other relations.
  * Deterministic identity: the relation is identified by the WO-016
    deterministic ``relation_id``; identity is never changed.
  * Idempotent: reprocessing the same severance event is a safe no-op.
  * No physical deletion; no reactivation; no SUPERSEDED; no temporal fields.
  * Single DatabaseSessionManager owner; independent EVENT/RELATION
    transactions; no second DB/engine/sessionmaker.
  * Strict Event.seq replay remains deterministic (idempotent, not
    commutative).
  * Flows through the canonical EventPipeline production composition root.

Invariants locked here (WO-018 AC-01..AC-14):
  AC-01 RELATION_SEVERED exists and is processed through the canonical path.
  AC-02 explicit severance -> ACTIVE -> INACTIVE.
  AC-03 neither endpoint entity changes lifecycle state.
  AC-04 no cascade to other relations.
  AC-05 deterministic relation_id unchanged.
  AC-06 durable INACTIVE state.
  AC-07 idempotent repeated processing (no duplicates / no corruption).
  AC-08 strict seq replay deterministic.
  AC-09 WO-017 ENTITY_REMOVED lifecycle behavior preserved.
  AC-10 no physical deletion.
  AC-11 no reactivation.
  AC-12 no second DB owner.
  AC-13 WO-015/016/017 regression preserved.
  AC-14 only necessary files changed.
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
    """Establish a durable ACTIVE relation via the canonical pipeline (WO-016)."""
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


def _severed_event(
    event_id: str,
    source: str,
    target: str,
    rel_type: str,
) -> Event:
    """A canonical RELATION_SEVERED event identifying a single relation."""
    return Event(
        event_id=event_id,
        entity_id=source,
        event_type=EventType.RELATION_SEVERED,
        payload={
            "source_entity_id": source,
            "target_entity_id": target,
            "relation_type": rel_type,
        },
    )


# ---------------------------------------------------------------------------
# AC-01 / AC-02 — RELATION_SEVERED exists and severs a single relation
# ---------------------------------------------------------------------------


def test_event_type_relation_severed_exists():
    assert EventType.RELATION_SEVERED == "relation.severed"


def test_explicit_severance_terminates_relation(runtime, relation_repo):
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    assert relation_repo.get(rid)["status"] == "ACTIVE"

    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))

    rel = relation_repo.get(rid)
    assert rel["status"] == "INACTIVE"  # AC-02
    assert rel["terminated_at"] is not None  # AC-06 durable terminal
    assert rel["relation_id"] == rid  # AC-05 identity unchanged


# ---------------------------------------------------------------------------
# AC-03 — no entity mutation; AC-04 — no cascade
# ---------------------------------------------------------------------------


def test_severance_does_not_mutate_entities(runtime, relation_repo, entity_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_entity_created_event("e2", "B"))
    runtime.pipeline.process(_relation_event("e3", "A", "B", "reports_to"))

    runtime.pipeline.process(_severed_event("e4", "A", "B", "reports_to"))

    # AC-03: neither endpoint entity is tombstoned / deactivated.
    assert entity_repo.is_tombstoned("A") is False
    assert entity_repo.is_tombstoned("B") is False


def test_severance_does_not_cascade_to_other_relations(runtime, relation_repo):
    # Establish two relations sharing source A.
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    runtime.pipeline.process(_relation_event("e2", "A", "C", "commands"))

    rid1 = deterministic_relation_id("A", "B", "reports_to")
    rid2 = deterministic_relation_id("A", "C", "commands")

    # Sever only the A->B relation.
    runtime.pipeline.process(_severed_event("e3", "A", "B", "reports_to"))

    # AC-04: only the identified relation is INACTIVE; A->C remains ACTIVE.
    assert relation_repo.get(rid1)["status"] == "INACTIVE"
    assert relation_repo.get(rid2)["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# AC-07 — idempotency
# ---------------------------------------------------------------------------


def test_repeated_severance_is_idempotent(runtime, relation_repo):
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")

    # Replay the severance event twice.
    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))
    runtime.pipeline.process(_severed_event("e3", "A", "B", "reports_to"))

    rel = relation_repo.get(rid)
    assert rel["status"] == "INACTIVE"
    assert rel["terminated_at"] is not None
    # Idempotent: exactly one durable relation row, no duplicates.
    assert len(relation_repo.list_all()) == 1


def test_sever_nonexistent_relation_is_safe_noop(runtime, relation_repo):
    # No relation exists; severance must not error and must not create rows.
    runtime.pipeline.process(_severed_event("e1", "A", "B", "reports_to"))
    assert relation_repo.get(deterministic_relation_id("A", "B", "reports_to")) is None
    assert len(relation_repo.list_all()) == 0


# ---------------------------------------------------------------------------
# AC-10 — no physical deletion
# ---------------------------------------------------------------------------


def test_severance_preserves_row_and_identity(runtime, relation_repo):
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))

    rel = relation_repo.get(rid)
    assert rel is not None  # AC-10: row retained (durable tombstone, not DELETE)
    assert rel["status"] == "INACTIVE"
    assert rel["relation_id"] == rid


# ---------------------------------------------------------------------------
# AC-09 — WO-017 ENTITY_REMOVED lifecycle preserved (severance is distinct)
# ---------------------------------------------------------------------------


def test_entity_removed_still_tombstones_and_cascades(runtime, relation_repo, entity_repo):
    runtime.pipeline.process(_entity_created_event("e1", "A"))
    runtime.pipeline.process(_relation_event("e2", "A", "B", "reports_to"))
    runtime.pipeline.process(_relation_event("e3", "C", "A", "commands"))

    rid1 = deterministic_relation_id("A", "B", "reports_to")
    rid2 = deterministic_relation_id("C", "A", "commands")

    # ENTITY_REMOVED must STILL tombstone the entity and cascade BOTH relations.
    runtime.pipeline.process(
        Event(
            event_id="e4",
            entity_id="A",
            event_type=EventType.ENTITY_REMOVED,
            payload={},
        )
    )

    assert entity_repo.is_tombstoned("A") is True
    assert relation_repo.get(rid1)["status"] == "INACTIVE"
    assert relation_repo.get(rid2)["status"] == "INACTIVE"


# ---------------------------------------------------------------------------
# AC-12 — no second DB owner
# ---------------------------------------------------------------------------


def test_severance_uses_single_database_owner(runtime, relation_repo):
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))

    assert relation_repo.get(rid)["status"] == "INACTIVE"
    # The single DatabaseSessionManager is the only engine/session owner.
    assert session_mod._session_manager is not None
    # No stray in-memory/second engines created during severance.
    assert relation_repo.session_manager is session_mod.get_session_manager()


# ---------------------------------------------------------------------------
# AC-08 — strict seq replay deterministic (idempotent, not commutative)
# ---------------------------------------------------------------------------


def test_replay_in_any_dup_is_idempotent(runtime, relation_repo):
    # Reprocessing identical canonical events yields the same durable state.
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))

    # Full replay of the same events again.
    runtime.pipeline.process(_relation_event("e1", "A", "B", "reports_to"))
    runtime.pipeline.process(_severed_event("e2", "A", "B", "reports_to"))

    rid = deterministic_relation_id("A", "B", "reports_to")
    rel = relation_repo.get(rid)
    assert rel["status"] == "INACTIVE"
    assert len(relation_repo.list_all()) == 1
