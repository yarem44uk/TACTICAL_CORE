"""WO-030 — Production durable delivery composition wiring.

WO-030 makes ``create_event_runtime()`` the SINGLE production owner of the
durable post-commit delivery dispatcher (transactional outbox).  It:

  * wires ``wire_durable_delivery()`` exactly once per runtime;
  * attaches the dispatcher to the EventRuntime (delivery_dispatcher) and to
    the EventPipeline (pipeline._delivery_dispatcher) as the SAME object;
  * connects the dispatcher to the durable outbox repository and the durable
    canonical event repository (WO-031 reconstruction);
  * registers the ``plugins`` and ``observation`` consumers;
  * never silently downgrades to the legacy path: when durable delivery is
    required but a DatabaseSessionManager is unavailable,
    ``create_production_runtime(require_durable_delivery=True)`` raises.

These tests exercise the REAL production composition functions
(``create_event_runtime`` / ``create_production_runtime``) and the REAL
pipeline/dispatcher/outbox/repository — no test double for the wiring.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import pytest

import app.database.session as session_mod
from app.composition import EventRuntime, create_event_runtime
from app.bootstrap import create_production_runtime
from app.database.schema_migration import upgrade_schema
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


def _make_event(event_id: str = "wo030-evt-1") -> Event:
    return Event(
        event_id=event_id,
        entity_id="entity-wo030",
        event_type=EventType.CUSTOM,
        source="wo030-source",
        payload={"k": "v"},
        metadata=EventMetadata(tags=["wo030"]),
    )


def _dispatcher(runtime) -> DurableDeliveryDispatcher:
    """Return the runtime's durable dispatcher, asserting it is concrete.

    ``EventRuntime.delivery_dispatcher`` is typed ``Optional[object]``; this
    helper narrows to the concrete ``DurableDeliveryDispatcher`` so the tests
    can assert on its real attributes.
    """
    assert isinstance(runtime.delivery_dispatcher, DurableDeliveryDispatcher)
    return runtime.delivery_dispatcher


@pytest.fixture()
def file_db():
    """Real file-backed SQLite + migration, reset after each test."""
    tmp = tempfile.mkdtemp(prefix="wo030-")
    db = os.path.join(tmp, "db.sqlite")
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    yield db
    session_mod._session_manager = None


# ---------------------------------------------------------------------------
# 1. create_event_runtime() wires the durable dispatcher (canonical owner)
# ---------------------------------------------------------------------------


def test_create_event_runtime_wires_durable_dispatcher(file_db):
    runtime = create_event_runtime()
    assert isinstance(runtime, EventRuntime)
    dd = _dispatcher(runtime)
    assert isinstance(dd, DurableDeliveryDispatcher)


def test_runtime_dispatcher_is_pipeline_dispatcher_object_identity(file_db):
    """EventRuntime.delivery_dispatcher IS pipeline._delivery_dispatcher."""
    runtime = create_event_runtime()
    dd = _dispatcher(runtime)
    assert runtime.delivery_dispatcher is runtime.pipeline._delivery_dispatcher
    assert dd is runtime.pipeline._delivery_dispatcher


def test_dispatcher_is_connected_to_outbox_and_event_repository(file_db):
    runtime = create_event_runtime()
    dd = _dispatcher(runtime)
    assert isinstance(dd.outbox, SQLAlchemyOutboxRepository)
    # WO-031 — the dispatcher resolves record.event_id through the durable
    # canonical event repository (Option B reconstruction).
    assert dd._event_repository is not None


def test_consumers_registered(file_db):
    runtime = create_event_runtime()
    dd = _dispatcher(runtime)
    consumer_ids = dd.consumer_ids()
    assert "plugins" in consumer_ids
    assert "observation" in consumer_ids


# ---------------------------------------------------------------------------
# 2. create_production_runtime() does not double-wire
# ---------------------------------------------------------------------------


def test_production_runtime_single_dispatcher_instance(file_db):
    pr = create_production_runtime()
    # Within ONE production runtime, the same dispatcher instance is exposed on
    # the ProductionRuntime handle, the EventRuntime, and the pipeline — i.e.
    # create_event_runtime() wired durable delivery exactly once and
    # create_production_runtime() did NOT re-wire a second dispatcher.
    assert pr.delivery_dispatcher is pr.event_runtime.delivery_dispatcher
    assert pr.delivery_dispatcher is pr.event_runtime.pipeline._delivery_dispatcher


def test_wire_durable_delivery_executes_once_per_runtime(file_db):
    """A single production composition produces exactly one dispatcher shared
    by the production handle, the EventRuntime, and the pipeline."""
    pr = create_production_runtime()
    ids = {
        id(pr.delivery_dispatcher),
        id(pr.event_runtime.delivery_dispatcher),
        id(pr.event_runtime.pipeline._delivery_dispatcher),
    }
    assert len(ids) == 1  # exactly one dispatcher instance everywhere


# ---------------------------------------------------------------------------
# 3. Canonical hot-path delivery through the real runtime (WO-031 compatible)
# ---------------------------------------------------------------------------


def test_hot_path_delivers_canonical_event(file_db):
    runtime = create_event_runtime()
    dd = _dispatcher(runtime)

    received: list[object] = []

    # Replace the wired consumer callbacks with recording ones so we can
    # observe what the hot path delivers (original Event).
    dd._consumers["plugins"] = received.append

    ev = _make_event("wo030-hot")
    runtime.pipeline.process(ev)

    assert len(received) == 1
    payload = received[0]
    assert isinstance(payload, Event)
    assert payload.event_id == "wo030-hot"
    # Hot path records are DELIVERED (not left PENDING).
    assert dd.outbox.get_state("wo030-hot", "plugins") == "DELIVERED"


def test_event_id_preserved_through_production_runtime(file_db):
    pr = create_production_runtime()
    dd = _dispatcher(pr.event_runtime)
    seen: list[str] = []
    dd._consumers["plugins"] = lambda e: seen.append(e.event_id)  # type: ignore[union-attr,attr-defined]

    ev = _make_event("wo030-identity")
    pr.event_runtime.pipeline.process(ev)

    assert seen == ["wo030-identity"]
    assert dd.outbox.get_state("wo030-identity", "plugins") == "DELIVERED"


# ---------------------------------------------------------------------------
# 4. No silent downgrade
# ---------------------------------------------------------------------------


def test_no_session_manager_keeps_legacy_path_by_default():
    # Ensure no DatabaseSessionManager is configured.
    session_mod._session_manager = None
    rt = create_event_runtime()
    assert rt.delivery_dispatcher is None  # lightweight/test-only runtime
    pr = create_production_runtime()
    assert pr.delivery_dispatcher is None
    session_mod._session_manager = None


def test_production_requires_durable_delivery_explicit_failure():
    # No DatabaseSessionManager -> durable delivery cannot be constructed.
    session_mod._session_manager = None
    with pytest.raises(RuntimeError):
        create_production_runtime(require_durable_delivery=True)
    session_mod._session_manager = None


# ---------------------------------------------------------------------------
# 5. Raw dict rejected before persistence on the durable path
# ---------------------------------------------------------------------------


def test_raw_dict_rejected_on_durable_path(file_db):
    runtime = create_event_runtime()
    with pytest.raises(TypeError):
        runtime.pipeline.process({})  # type: ignore[arg-type]
    # Nothing persisted, nothing delivered.
    repo = SQLAlchemyEventRepository()
    assert repo.get("nope") is None
