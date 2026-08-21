"""
WO-019 — Durable Event Identity / Deterministic Replay / Cross-Projection Consistency.

Locks the ratified WO-019 verification contract:

  * Canonical ``Event.event_id`` is durable and stable.
  * ``event_id`` survives serialization/deserialization (to_dict/from_dict).
  * Reprocessing the same canonical Event is idempotent.
  * No duplicate durable event rows are created by replay.
  * ``Event.seq`` ordering is deterministic (durable log order).
  * Durable event history is the authoritative replay input.
  * Replay in strict ``Event.seq`` order reproduces deterministic state.
  * Normal processing and clean-state replay produce equivalent:
      - Entity state
      - Relation state
      - Lifecycle state
      - ``source_event_id`` relationships
      - Relation cardinality
  * WO-017 ``ENTITY_REMOVED`` semantics remain intact (tombstone + cascade,
    idempotent, non-destructive).
  * WO-018 ``RELATION_SEVERED`` semantics remain intact (single-relation
    severance, non-cascading, idempotent, terminal).
  * No second DatabaseSessionManager / engine / sessionmaker is introduced.
  * ``deterministic_relation_id`` (WO-016) is preserved and stable.

Architectural posture: WO-019 is a verification/replay-consistency gate.  The
existing production architecture already satisfies the contract (durable
canonical event identity, deterministic seq replay, single DB owner), so this
suite is tests-only.  NO production code is modified.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_runtime() -> "object":
    """Configure an isolated in-memory SQLite DB and return a production
    runtime composed via the authoritative composition root.

    Each call creates a NEW DatabaseSessionManager with its own StaticPool
    in-memory engine, so successive runtimes are fully independent.
    """
    configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    SQLAlchemyRelationRepository().initialize()
    SQLAlchemyEntityRepository().initialize()
    return create_event_runtime()


@pytest.fixture()
def runtime() -> "object":
    rt = _fresh_runtime()
    yield rt
    session_mod._session_manager = None


def _fresh_repos():
    return (
        SQLAlchemyEventRepository(),
        SQLAlchemyRelationRepository(),
        SQLAlchemyEntityRepository(),
    )


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------


def _entity_created(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_CREATED,
        payload={"entity_type": "unit", "callsign": entity_id},
    )


def _relation_event(
    event_id: str, source: str, target: str, rel_type: str
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


def _entity_removed(event_id: str, entity_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.ENTITY_REMOVED,
        payload={},
    )


def _severed(source: str, target: str, rel_type: str, event_id: str) -> Event:
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
# State capture helper
# ---------------------------------------------------------------------------


_VOLATILE_KEYS = {
    "created_at",
    "updated_at",
    "terminated_at",
    "version",
}


def _stable_dict(d: dict) -> dict:
    """Return a deterministic, replay-stable projection of a row dict by
    stripping volatile wall-clock/version fields.  Replay equivalence is about
    projected state (identity, lifecycle, provenance, cardinality), not the
    timestamp at which a row was written, so timestamps must not drive the
    equality comparison."""
    return {k: v for k, v in d.items() if k not in _VOLATILE_KEYS}


def _capture_state(runtime) -> dict:
    """Capture the full projected state: entity, relation, lifecycle,
    source_event_id relationships, and relation cardinality."""
    er, rr, _ = (
        SQLAlchemyEventRepository(),
        runtime.relation_repository,
        runtime.entity_repository,
    )
    # Durable event history is the authoritative replay input (seq order).
    events = er.list_all()
    relations = sorted(
        (_stable_dict(r) for r in rr.list_all()),
        key=lambda r: r["relation_id"],
    )
    entities = sorted(
        (_stable_dict(e) for e in runtime.entity_repository.list_all()),
        key=lambda e: str(e["entity_id"]),
    )
    return {
        "event_ids": [e.event_id for e in events],
        "event_seq_order": [e.event_id for e in events],
        "relations": relations,
        "entities": entities,
        "relation_count": len(relations),
        "entity_count": len(entities),
    }


def _replay(runtime, durable_events) -> None:
    """Replay the given durable canonical events (already materialised from
    the source runtime's durable history, in seq order) through a clean-state
    production pipeline.  Each is a distinct event_id, so durable history is
    re-processed exactly once in deterministic order."""
    for ev in durable_events:
        runtime.pipeline.process(ev)


# ---------------------------------------------------------------------------
# 1. Stable event_id
# ---------------------------------------------------------------------------


def test_event_id_is_stable_and_unique(runtime):
    e1 = Event(event_id="evt-1", entity_id="A", event_type=EventType.ENTITY_CREATED)
    e2 = Event(event_id="evt-1", entity_id="A", event_type=EventType.ENTITY_CREATED)
    assert e1.event_id == e2.event_id == "evt-1"
    # Distinct events carry distinct identities.
    e3 = Event(event_id="evt-2", entity_id="B", event_type=EventType.ENTITY_CREATED)
    assert e3.event_id != e1.event_id


# ---------------------------------------------------------------------------
# 2. event_id survives serialization / deserialization
# ---------------------------------------------------------------------------


def test_event_id_survives_serialization_roundtrip(runtime):
    ev = _entity_created("evt-ser-1", "A")
    data = ev.to_dict()
    restored = Event.from_dict(data)
    assert restored.event_id == ev.event_id == "evt-ser-1"
    assert restored.entity_id == ev.entity_id
    assert restored.event_type == ev.event_type
    assert restored.equals(ev)


# ---------------------------------------------------------------------------
# 3/4. Duplicate processing is idempotent, no duplicate durable row
# ---------------------------------------------------------------------------


def test_duplicate_event_processing_is_idempotent_no_dup_row(runtime):
    er, _, _ = _fresh_repos()
    runtime.pipeline.process(_entity_created("evt-dup-1", "A"))
    runtime.pipeline.process(_entity_created("evt-dup-1", "A"))
    assert er.count() == 1  # exactly one durable row
    stored = er.get("evt-dup-1")
    assert stored is not None
    assert stored.event_id == "evt-dup-1"


# ---------------------------------------------------------------------------
# 5. Event.seq ordering is deterministic
# ---------------------------------------------------------------------------


def test_durable_event_seq_ordering_is_deterministic(runtime):
    er, _, _ = _fresh_repos()
    runtime.pipeline.process(_entity_created("evt-seq-1", "A"))
    runtime.pipeline.process(_entity_created("evt-seq-2", "B"))
    runtime.pipeline.process(_entity_created("evt-seq-3", "C"))
    history = er.list_all()  # ordered by seq ASC
    assert [e.event_id for e in history] == ["evt-seq-1", "evt-seq-2", "evt-seq-3"]
    # seq values strictly increasing
    seqs = er.iter_after_seq(0)
    assert [s for s, _ in seqs] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 6/7/8/9/10/11/12. Normal processing == clean-state replay
# ---------------------------------------------------------------------------


def _normal_and_replay_equivalent(runtime):
    """Process a realistic sequence normally (runtime A), capture state, then
    replay the same durable history into a clean-state runtime (runtime B) and
    assert the two states are equivalent across all projection domains."""
    # Normal processing on runtime A.
    runtime.pipeline.process(_entity_created("evt-n-1", "A"))
    runtime.pipeline.process(_entity_created("evt-n-2", "B"))
    runtime.pipeline.process(_relation_event("evt-n-3", "A", "B", "reports_to"))
    runtime.pipeline.process(_entity_created("evt-n-4", "C"))
    runtime.pipeline.process(_relation_event("evt-n-5", "B", "C", "commands"))
    runtime.pipeline.process(_severed("A", "B", "reports_to", "evt-n-6"))

    state_a = _capture_state(runtime)

    # Materialise the durable history objects from runtime A BEFORE the global
    # session manager is switched to the clean-state runtime B (otherwise the
    # repo would read B's empty DB).
    durable_events = SQLAlchemyEventRepository().list_all()  # seq-ordered

    # Clean-state replay: new runtime, new independent in-memory DB.
    rt_b = _fresh_runtime()
    _replay(rt_b, durable_events)
    state_b = _capture_state(rt_b)

    return state_a, state_b


def test_replay_reproduces_entity_state(runtime):
    state_a, state_b = _normal_and_replay_equivalent(runtime)
    assert state_a["entity_count"] == state_b["entity_count"]
    assert state_a["entities"] == state_b["entities"]


def test_replay_reproduces_relation_state(runtime):
    state_a, state_b = _normal_and_replay_equivalent(runtime)
    assert state_a["relation_count"] == state_b["relation_count"]
    assert state_a["relations"] == state_b["relations"]


def test_replay_reproduces_lifecycle_state(runtime):
    state_a, state_b = _normal_and_replay_equivalent(runtime)
    # Lifecycle state is embedded in relation status + entity tombstone state.
    def _lifecycle(state):
        return {
            "rel_status": {
                r["relation_id"]: r["status"] for r in state["relations"]
            },
            "entities": [
                (e["entity_id"], _ent_tombstoned(e)) for e in state["entities"]
            ],
        }

    assert _lifecycle(state_a) == _lifecycle(state_b)


def _ent_tombstoned(e) -> bool:
    return bool(e.get("status") == "TOMBSTONED")


def test_replay_reproduces_source_event_id_relationships(runtime):
    state_a, state_b = _normal_and_replay_equivalent(runtime)
    def _src(state):
        return {
            r["relation_id"]: r.get("source_event_id") for r in state["relations"]
        }
    assert _src(state_a) == _src(state_b)


def test_replay_reproduces_relation_cardinality(runtime):
    state_a, state_b = _normal_and_replay_equivalent(runtime)
    assert state_a["relation_count"] == 2  # A-B severed (inactive) + B-C active
    assert state_a["relation_count"] == state_b["relation_count"]


# ---------------------------------------------------------------------------
# 13. WO-017 ENTITY_REMOVED semantics intact + replay idempotent
# ---------------------------------------------------------------------------


def test_entity_removed_semantics_intact_and_replay_idempotent(runtime):
    rr, _ = SQLAlchemyRelationRepository(), None
    runtime.pipeline.process(_relation_event("evt-r-1", "A", "B", "reports_to"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    runtime.pipeline.process(_entity_removed("evt-r-2", "A"))

    # WO-017 cascade: entity tombstoned + relation inactivated.
    assert runtime.entity_repository.is_tombstoned("A") is True
    assert rr.get(rid)["status"] == "INACTIVE"

    # Reprocess the same events (idempotent): no duplicates, state unchanged.
    runtime.pipeline.process(_relation_event("evt-r-1", "A", "B", "reports_to"))
    runtime.pipeline.process(_entity_removed("evt-r-2", "A"))
    assert len(rr.list_all()) == 1
    assert rr.get(rid)["status"] == "INACTIVE"
    assert runtime.entity_repository.is_tombstoned("A") is True


# ---------------------------------------------------------------------------
# 14/15/16. WO-018 RELATION_SEVERED semantics intact + non-cascading +
#           deterministic relation_id preserved
# ---------------------------------------------------------------------------


def test_relation_severed_semantics_and_deterministic_id(runtime):
    rr = SQLAlchemyRelationRepository()
    runtime.pipeline.process(_relation_event("evt-s-1", "A", "B", "reports_to"))
    runtime.pipeline.process(_relation_event("evt-s-2", "B", "C", "commands"))
    rid = deterministic_relation_id("A", "B", "reports_to")
    rid2 = deterministic_relation_id("B", "C", "commands")
    runtime.pipeline.process(_severed("A", "B", "reports_to", "evt-s-3"))

    # Deterministic relation_id unchanged by severance.
    assert rr.get(rid)["relation_id"] == rid
    # Severance is non-cascading: B->C stays ACTIVE.
    assert rr.get(rid)["status"] == "INACTIVE"
    assert rr.get(rid2)["status"] == "ACTIVE"
    # Endpoint entity lifecycle untouched.
    assert runtime.entity_repository.is_tombstoned("A") is False
    # Idempotent: re-sever is a safe no-op, no duplicate rows.
    runtime.pipeline.process(_severed("A", "B", "reports_to", "evt-s-3"))
    assert len(rr.list_all()) == 2
    assert rr.get(rid)["status"] == "INACTIVE"


# ---------------------------------------------------------------------------
# 17. Shared DB / session ownership remains singular (no second engine)
# ---------------------------------------------------------------------------


def test_single_database_owner(runtime):
    er = SQLAlchemyEventRepository()
    rr = runtime.relation_repository
    ent = runtime.entity_repository
    es_repo = runtime.event_service._repository
    # All four durable repositories resolve to the SAME session manager.
    assert er.session_manager is rr.session_manager
    assert rr.session_manager is ent.session_manager
    assert ent.session_manager is es_repo.session_manager


def test_single_engine_no_second_owner(runtime):
    from app.database.session import get_session_manager

    mgr = get_session_manager()
    es_repo = runtime.event_service._repository
    assert mgr is es_repo.session_manager
    # The durable repos share the single engine; no second engine/sessionmaker.
    assert runtime.entity_repository.session_manager.engine is mgr.engine
    assert runtime.relation_repository.session_manager.engine is mgr.engine
    assert es_repo.session_manager.engine is mgr.engine
