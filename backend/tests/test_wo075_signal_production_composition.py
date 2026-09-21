"""WO-075 — Signal production composition + injectable transport seam.

Acceptance tests proving that Signal is no longer merely a registered +
unit-tested adapter but is composed into the production source path:

    PRODUCTION_SOURCE_CATALOG
        -> build_production_source_provider()
        -> ProductionSourceRegistrar            (backend.main.register_sources)
        -> AdapterFactory.create()              (build_production_adapter_factory)
        -> SignalSourceAdapter                  (transport injected)
        -> AdapterSupervisor / AdapterRuntime   (production runtime)
        -> synthetic injectable transport
        -> SignalSourceAdapter.ingest()         (adapter unchanged raw dict)
        -> AdapterRuntime._process_raw()
        -> EventFactory.create_event()          (production composition factory)
        -> EventPipeline.process()              (production pipeline)
        -> durable canonical event journal
        -> canonical Observation (``signal.message`` mapping)
        -> operator observation read model (``/api/v1/operator/observations``)

These tests deliberately do NOT construct ``SignalSourceAdapter`` /
``AdapterRuntime`` / a fake pipeline by hand: the adapters come from the
production factory, the runtimes come from the production supervisor, and the
canonical runtime (EventFactory, EventPipeline, durable journal, Observation)
is the production one produced by ``create_production_runtime()``.

No live Signal connectivity is exercised: ``signal-cli`` is not provisioned,
no account is authenticated, no network connection is opened and no message is
sent or received.  A SYNTHETIC, in-memory transport implementation
(``SyntheticSignalTransport``) is used exclusively for acceptance testing — it
exists only to feed a payload into ``SignalSourceAdapter.ingest``.

Scope note (WO-075): restart/replay/cursor semantics and the attachment /
evidence seam are explicitly OUT OF SCOPE and remain as documented by WO-074
(the adapter's queue is in-memory; it is cleared on stop).
"""

from __future__ import annotations

import copy
import time

import pytest
from sqlalchemy import func, select

import app.database.session as session_mod
import backend.main as main
from app.bootstrap import create_production_runtime
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.adapters.signal_parser import SignalPayloadNormalizer
from app.event_sources.adapters.signal_source_adapter import SignalSourceAdapter
from app.event_sources.adapters.signal_transport import SignalTransport
from app.event_sources.config.production_source_config import (
    PRODUCTION_SOURCE_CATALOG,
    build_production_adapter_factory,
    build_production_source_provider,
)
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.intelligence.observation.model import Observation
from app.intelligence.observation.repository import ObservationRepository

# Pseudonymous, non-personal test identifiers (no real account / phone number).
MESSAGE = {
    "message_id": "sig-wo075-1",
    "sender": "sender-alpha",
    "chat_id": "group-wo075",
    "message_text": "Буревій-2 на зв'язку",
    "timestamp": "2026-09-03T12:00:00+00:00",
}

WAIT_TIMEOUT_S = 10.0
WAIT_STEP_S = 0.05


# --------------------------------------------------------------------------- #
# Synthetic injectable transport (acceptance-test only — never production).
# --------------------------------------------------------------------------- #
class SyntheticSignalTransport(SignalTransport):
    """In-memory Signal transport used EXCLUSIVELY for acceptance testing.

    Implements the WO-075 transport contract and nothing else: on ``start`` it
    hands the pre-loaded payloads to the injected sink (the adapter's
    ``ingest`` callable); ``deliver`` feeds one more payload at any time.

    It performs no authentication, opens no socket, and never reaches the
    canonical event path directly.
    """

    def __init__(self, payloads: list[dict] | None = None) -> None:
        self._pending = list(payloads or [])
        self._sink = None
        self.started = False
        self.stopped = False
        self.accepted = 0
        self.rejected = 0

    def start(self, sink) -> None:  # type: ignore[override]
        self._sink = sink
        self.started = True
        for payload in self._pending:
            self._feed(payload)
        self._pending = []

    def stop(self) -> None:
        self.stopped = True
        self._sink = None

    def deliver(self, payload: dict) -> bool:
        assert self._sink is not None, "transport must be started before deliver()"
        return self._feed(payload)

    def _feed(self, payload: dict) -> bool:
        accepted = bool(self._sink(payload))
        if accepted:
            self.accepted += 1
        else:
            self.rejected += 1
        return accepted


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _reset() -> None:
    session_mod._session_manager = None


def _signal_definition():
    """Return the Signal source definition declared in the production catalog."""
    matches = [d for d in PRODUCTION_SOURCE_CATALOG if d.adapter_type == "signal"]
    assert matches, "production catalog must declare a signal source"
    assert len(matches) == 1, "exactly one production signal source is declared"
    return matches[0]


def _expected_event_id(payload: dict) -> str:
    """The canonical event_id the production identity policy must derive."""
    raw = SignalPayloadNormalizer().normalize(payload)
    resolved = EventIdentityResolver().resolve(raw, "signal")
    assert resolved is not None, "signal identity policy must be deduplicable"
    return resolved


def _compose_signal_source(transport):
    """Build the real production composition and register the production sources.

    Returns ``(runtime, signal_aruntime, registered)`` where ``signal_aruntime``
    is the PRODUCTION ``AdapterRuntime`` created by the production supervisor
    (never a hand-built runtime).
    """
    runtime = create_production_runtime()
    provider = build_production_source_provider()  # real static production catalog
    factory = build_production_adapter_factory(signal_transport=transport)
    registered = main.register_sources(runtime, provider, factory)
    signal_aruntime = runtime.supervisor.get_runtime("signal")
    return runtime, signal_aruntime, registered


def _wait_for(predicate, timeout: float = WAIT_TIMEOUT_S):
    """Poll ``predicate`` until it returns a truthy value or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(WAIT_STEP_S)
    return predicate()


@pytest.fixture()
def env(tmp_path):
    """Isolated file database + canonical session manager, reset afterwards."""
    db_path = str(tmp_path / "wo075.db")
    _reset()
    mgr = configure_session_manager(f"sqlite:///{db_path}")
    Base.metadata.create_all(mgr.engine)
    yield {"db_path": db_path, "mgr": mgr}
    _reset()


# --------------------------------------------------------------------------- #
# 1. Production declaration
# --------------------------------------------------------------------------- #
def test_wo075_01_production_catalog_declares_signal() -> None:
    """The static production catalog declares an enabled ``signal`` source."""
    definition = _signal_definition()
    assert definition.name == "signal"
    assert definition.adapter_type == "signal"
    # Explicit enabled state: the production registrar only registers enabled
    # sources, so composition genuinely builds the Signal source.
    assert definition.enabled is True
    # Reference-only credential (never a secret value, never a secret key).
    assert isinstance(definition.credentials_ref, str) and definition.credentials_ref
    for secret_key in ("password", "token", "api_token", "secret", "api_key"):
        assert secret_key not in definition.config

    # The production factory resolves the declared adapter type.
    factory = build_production_adapter_factory()
    assert "signal" in factory.registered_types()


# --------------------------------------------------------------------------- #
# 2. Injectable transport seam
# --------------------------------------------------------------------------- #
def test_wo075_02_production_factory_injects_transport() -> None:
    """The production factory builds a Signal adapter bound to the transport."""
    transport = SyntheticSignalTransport()
    factory = build_production_adapter_factory(signal_transport=transport)
    adapter = factory.create(_signal_definition())

    assert isinstance(adapter, SignalSourceAdapter)
    assert adapter.adapter_type == "signal"
    assert adapter.source_name() == "signal"
    assert adapter.transport is transport


def test_wo075_02b_transport_seam_is_passive_without_injection() -> None:
    """Without injection the adapter keeps its pre-WO-075 passive behaviour."""
    adapter = SignalSourceAdapter(definition=_signal_definition())
    assert adapter.transport is None
    adapter.start()
    try:
        assert adapter.ingest(dict(MESSAGE)) is True
        assert adapter.pending_count() == 1
        assert len(adapter.read_events()) == 1
    finally:
        adapter.stop()
    assert adapter.pending_count() == 0


# --------------------------------------------------------------------------- #
# 3. Production composition builds the Signal source (real registration path)
# --------------------------------------------------------------------------- #
def test_wo075_03_production_composition_builds_signal_source() -> None:
    """catalog -> provider -> registrar -> factory -> Signal source -> runtime."""
    transport = SyntheticSignalTransport()
    runtime, signal_aruntime, registered = _compose_signal_source(transport)

    assert registered == ["radio", "signal"]
    assert runtime.supervisor.list_runtimes() == ["radio", "signal"]

    adapter = signal_aruntime._adapter
    assert isinstance(adapter, SignalSourceAdapter)
    assert adapter.transport is transport
    assert signal_aruntime.name == "signal"


# --------------------------------------------------------------------------- #
# 4. Acceptance: synthetic Signal message traverses the canonical production path
# --------------------------------------------------------------------------- #
def test_wo075_04_signal_message_reaches_durable_journal_and_observation(env) -> None:
    """A synthetic Signal message traverses the REAL canonical production path.

    Proves: production composition -> synthetic transport -> adapter.ingest ->
    AdapterRuntime._process_raw -> EventFactory -> EventPipeline -> durable
    journal -> canonical Observation (``signal.message``).
    """
    transport = SyntheticSignalTransport([dict(MESSAGE)])
    runtime, signal_aruntime, _registered = _compose_signal_source(transport)

    expected_event_id = _expected_event_id(MESSAGE)

    # Drive the PRODUCTION runtime: starting the signal source starts the
    # AdapterRuntime thread, which starts the adapter, which starts the
    # injected transport -> ingest.  The radio source is never started.
    runtime.start_source("signal")
    try:
        obs = _wait_for(
            lambda: ObservationRepository(
                get_session_manager().get_session()
            ).get_by_immutable_id(expected_event_id)
        )
    finally:
        runtime.stop_source("signal")

    assert transport.started is True
    assert transport.stopped is True, "stopping the source must stop the transport"
    assert transport.accepted == 1

    # --- durable canonical event journal -----------------------------------
    event_repo = SQLAlchemyEventRepository(session_manager=env["mgr"])
    assert event_repo.exists(expected_event_id), (
        "the canonical Signal event must be durably persisted"
    )
    durable_event = event_repo.get(expected_event_id)
    assert durable_event is not None
    assert durable_event.source == "signal"
    assert durable_event.payload.get("message_id") == MESSAGE["message_id"]
    assert durable_event.payload.get("sender") == MESSAGE["sender"]
    assert durable_event.payload.get("chat_id") == MESSAGE["chat_id"]

    # --- canonical Observation (signal.message mapping) ---------------------
    assert obs is not None, "the Signal event must reach the Observation read model"
    assert obs.immutable_id == expected_event_id
    assert obs.source == "signal"
    assert obs.observation_type == "signal"
    raw_data = (obs.evidence_payload or {}).get("raw_data", {})
    assert raw_data.get("message_id") == MESSAGE["message_id"]
    assert raw_data.get("sender") == MESSAGE["sender"]
    assert raw_data.get("chat_id") == MESSAGE["chat_id"]
    assert raw_data.get("message_text") == MESSAGE["message_text"]
    # Field mapping (models.EVENT_TYPE_MAPPINGS["signal.message"]).
    assert (obs.evidence_payload or {}).get("source") == MESSAGE["sender"]
    assert (obs.evidence_payload or {}).get("content") == MESSAGE["message_text"]
    assert (obs.evidence_payload or {}).get("channel") == MESSAGE["chat_id"]


def test_wo075_04b_signal_observation_visible_on_operator_wall(env) -> None:
    """The Signal observation is visible through the operator read model."""
    from fastapi.testclient import TestClient

    from app.operator.app import create_operator_app
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )
    from app.intelligence.observation.repository import (
        SessionManagerObservationRepository,
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPERATOR_TOKEN", "wo075-secret")
    try:
        transport = SyntheticSignalTransport([dict(MESSAGE)])
        runtime, _aruntime, _registered = _compose_signal_source(transport)
        expected_event_id = _expected_event_id(MESSAGE)

        runtime.start_source("signal")
        try:
            obs = _wait_for(
                lambda: ObservationRepository(
                    get_session_manager().get_session()
                ).get_by_immutable_id(expected_event_id)
            )
        finally:
            runtime.stop_source("signal")
        assert obs is not None

        app = create_operator_app(
            event_repository=SQLAlchemyEventRepository(session_manager=env["mgr"]),
            entity_repository=SQLAlchemyEntityRepository(session_manager=env["mgr"]),
            relation_repository=SQLAlchemyRelationRepository(
                session_manager=env["mgr"]
            ),
            observation_repository=SessionManagerObservationRepository(env["mgr"]),
        )
        client = TestClient(app)
        resp = client.get(
            "/api/v1/operator/observations",
            headers={"Authorization": "Bearer wo075-secret"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [o["immutable_id"] for o in body.get("observations", [])]
        assert expected_event_id in ids, f"Signal observation missing from wall: {ids}"
        entry = next(o for o in body["observations"] if o["immutable_id"] == expected_event_id)
        assert entry["source"] == "signal"
        assert entry["observation_type"] == "signal"
    finally:
        monkeypatch.undo()


# --------------------------------------------------------------------------- #
# 5. Duplicate safety (existing Signal identity policy: chat_id + message_id)
# --------------------------------------------------------------------------- #
def test_wo075_05_duplicate_delivery_is_idempotent(env) -> None:
    """Re-ingesting the SAME Signal message creates ONE canonical event.

    Uses the existing WO-025 Signal identity policy (``chat_id + message_id``)
    unchanged; no second Signal identity mechanism is introduced.
    """
    duplicate = copy.deepcopy(MESSAGE)
    transport = SyntheticSignalTransport([dict(MESSAGE), duplicate])
    runtime, _aruntime, _registered = _compose_signal_source(transport)
    expected_event_id = _expected_event_id(MESSAGE)

    runtime.start_source("signal")
    try:
        obs = _wait_for(
            lambda: ObservationRepository(
                get_session_manager().get_session()
            ).get_by_immutable_id(expected_event_id)
        )
    finally:
        runtime.stop_source("signal")

    assert transport.accepted == 2, "both deliveries must be accepted by the adapter"
    assert obs is not None

    event_repo = SQLAlchemyEventRepository(session_manager=env["mgr"])
    signal_events = event_repo.list_by_source("signal")
    assert len(signal_events) == 1, (
        f"duplicate delivery must not create a second durable event: {signal_events}"
    )
    assert [e.event_id for e in signal_events] == [expected_event_id]

    session = get_session_manager().get_session()
    count = session.execute(
        select(func.count(Observation.id)).where(
            Observation.immutable_id == expected_event_id
        )
    ).scalar_one()
    assert count == 1, f"duplicate delivery must not create a second observation: {count}"


# --------------------------------------------------------------------------- #
# 6. Transport lifecycle is driven by the adapter (not by the test)
# --------------------------------------------------------------------------- #
def test_wo075_06_transport_lifecycle_idempotent() -> None:
    """Adapter start/stop drive the transport exactly once (idempotent)."""
    transport = SyntheticSignalTransport()
    adapter = build_production_adapter_factory(signal_transport=transport).create(
        _signal_definition()
    )
    assert adapter.transport_started is False

    adapter.start()
    adapter.start()  # idempotent
    assert transport.started is True
    assert adapter.transport_started is True

    adapter.stop()
    adapter.stop()  # idempotent
    assert transport.stopped is True
    assert adapter.transport_started is False
