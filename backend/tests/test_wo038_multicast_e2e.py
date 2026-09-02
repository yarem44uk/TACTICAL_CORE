"""WO-038 tests — Multicast audio -> STT -> callsign -> durable event -> operator.

PRIMARY ACCEPTANCE TEST (WO-038 §16): the integrated vertical slice must produce
an operator-visible, durably-stored canonical event from controlled multicast
audio.  These tests exercise the REAL path:

    controlled multicast simulator
        -> real UDP multicast receive
        -> real ffmpeg decode
        -> ITranscriber (DeterministicTestTranscriber)
        -> CallsignDetector
        -> EventFactory
        -> SQLAlchemyEventRepository (durable)
        -> operator REST / SSE
        -> operator-visible result

Scenarios covered (WO-038 §17):
  A  normal flow            B  restart recovery
  C  duplicate handling     D  source interruption
  E  source recovery        F  chronology
  G  callsign extraction    H  >=100 events

The deterministic test transcriber is NOT production acoustic STT; it is the
explicit test implementation of the STT seam (WO-038 authorization).  The full
transcript is always preserved, and the vertical path is never mocked away.
"""

from __future__ import annotations

import os
import tempfile
import time

import httpx
import pytest
from app.audio.audio_config import AudioConfig
from app.audio.callsign import CallsignDetector
from app.audio.simulator import MulticastAudioSimulator
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.audio.transcriber import DeterministicTestTranscriber
from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor

# A stable, reserved multicast group + per-test ports (no operational address).
GROUP = "239.255.1.0"
_PORT_COUNTER = {"n": 0}

# Known test phrase (WO-038 §15 example).
PHRASE = "Буревій-2, прийом. Виходжу на позицію."
CONTENT_ID = "bureviy-2"
CALLSIGN = "Буревій-2"


def _unique_port() -> int:
    """Return a per-test port so parallel/serial runs never collide."""
    _PORT_COUNTER["n"] += 1
    return 40000 + _PORT_COUNTER["n"] * 2


def _make_config(port: int, **overrides) -> AudioConfig:
    return AudioConfig(
        multicast_address=GROUP,
        multicast_port=port,
        codec="wav",
        source_name="radio",
        join_interface="127.0.0.1",
        **overrides,
    )


def _make_transcriber() -> DeterministicTestTranscriber:
    return DeterministicTestTranscriber(
        phrase_map={CONTENT_ID: PHRASE},
        default_text="",
        language="uk",
    )


def _make_detector() -> CallsignDetector:
    return CallsignDetector(callsigns=[CALLSIGN])


def _make_definition(port: int) -> SourceDefinition:
    return SourceDefinition(
        name="radio-mc",
        adapter_type="multicast_audio",
        config={
            "multicast_address": GROUP,
            "multicast_port": port,
            "codec": "wav",
            "source_name": "radio",
            "join_interface": "127.0.0.1",
        },
    )


def _make_db(port: int) -> tuple[str, DatabaseSessionManager]:
    fd, path = tempfile.mkstemp(suffix=f"-{port}.db")
    os.close(fd)
    sm = DatabaseSessionManager(database_url=f"sqlite:///{path}", echo=False)
    sm.initialize()
    return path, sm


def _make_runtime(
    path: str, sm: DatabaseSessionManager, port: int
) -> tuple[SQLAlchemyEventRepository, AdapterSupervisor, MulticastAudioSourceAdapter]:
    repo = SQLAlchemyEventRepository(session_manager=sm)
    repo.initialize()
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    pipeline = EventPipeline()
    pipeline.set_repository(repo)
    supervisor = AdapterSupervisor(factory, pipeline)
    adapter = MulticastAudioSourceAdapter(
        _make_definition(port),
        config=_make_config(port),
        transcriber=_make_transcriber(),
        callsign_detector=_make_detector(),
    )
    runtime = supervisor.add_adapter(adapter)
    runtime.start()
    return repo, supervisor, adapter


def _wait_for_event(repo: SQLAlchemyEventRepository, timeout: float = 8.0) -> Event | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = repo.list_all()
        if events:
            return events[-1]
        time.sleep(0.1)
    return None


def _wait_for_count(repo: SQLAlchemyEventRepository, n: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if repo.count() >= n:
            return True
        time.sleep(0.1)
    return False


@pytest.fixture()
def e2e():
    """Yields a wired runtime + durable repo for one test."""
    port = _unique_port()
    path, sm = _make_db(port)
    repo, supervisor, adapter = _make_runtime(path, sm, port)
    yield {
        "port": port,
        "path": path,
        "sm": sm,
        "repo": repo,
        "supervisor": supervisor,
        "adapter": adapter,
        "config": _make_config(port),
    }
    supervisor.shutdown()
    sm.close()
    if os.path.exists(path):
        os.remove(path)


# -- A. Normal flow ----------------------------------------------------------


def test_a_normal_flow_durable_event_operator_visible(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    sim.close()

    event = _wait_for_event(e2e["repo"])
    assert event is not None, "no durable event produced from multicast audio"
    assert event.source == "radio"
    assert event.payload["transcript"] == PHRASE
    assert event.payload["detected_callsigns"] == [CALLSIGN]
    assert event.payload["content_id"] == CONTENT_ID
    # Canonical event identity is deterministic (UUID5, 36 chars).
    assert len(event.event_id) == 36


# -- Operator REST visibility (same test's durable store) --------------------


def test_a2_operator_rest_returns_radio_transcript_event(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    sim.close()
    event = _wait_for_event(e2e["repo"])
    assert event is not None

    # Build a fresh operator app over the same repo (the e2e fixture's app
    # wiring above uses the default global session manager; construct it here
    # explicitly over the test repo).
    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.operator.app import create_operator_app
    sm = e2e["sm"]
    app = create_operator_app(
        event_repository=e2e["repo"],
        entity_repository=SQLAlchemyEntityRepository(session_manager=sm),
        relation_repository=SQLAlchemyRelationRepository(session_manager=sm),
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/api/v1/operator/events", params={"source": "radio"})
    assert r.status_code == 200
    body = r.json()
    assert body["events"], "operator feed empty for radio source"
    ev = body["events"][-1]
    assert ev["source"] == "radio"
    assert ev["payload"]["transcript"] == PHRASE
    assert ev["payload"]["detected_callsigns"] == [CALLSIGN]
    assert ev["payload"]["content_id"] == CONTENT_ID
    # Detail endpoint.
    detail = client.get(f"/api/v1/operator/events/{event.event_id}")
    assert detail.status_code == 200
    assert detail.json()["payload"]["transcript"] == PHRASE


# -- B. Restart recovery -----------------------------------------------------


def test_b_restart_recovery_event_survives(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    sim.close()
    event = _wait_for_event(e2e["repo"])
    assert event is not None
    event_id = event.event_id

    # Simulate a service restart: dispose the session manager and create a NEW
    # session manager + repository over the SAME SQLite file.
    e2e["sm"].close()
    sm2 = DatabaseSessionManager(database_url=f"sqlite:///{e2e['path']}", echo=False)
    sm2.initialize()
    repo2 = SQLAlchemyEventRepository(session_manager=sm2)
    repo2.initialize()

    assert repo2.exists(event_id), "event did not survive restart"
    restored = repo2.get(event_id)
    assert restored is not None
    assert restored.payload["transcript"] == PHRASE
    assert restored.payload["detected_callsigns"] == [CALLSIGN]
    sm2.close()


# -- C. Duplicate handling ---------------------------------------------------


def test_c_duplicate_same_content_is_deduplicated(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    # Same content_id sent twice -> same canonical identity -> one durable event.
    sim.send(CONTENT_ID)
    time.sleep(0.3)
    sim.send(CONTENT_ID)
    sim.close()

    assert _wait_for_count(e2e["repo"], 1, timeout=8.0), (
        "duplicate content must be deduplicated to exactly one durable event"
    )
    assert e2e["repo"].count() == 1
    events = e2e["repo"].list_all()
    assert len(events) == 1


# -- D. Source interruption (no crash) ----------------------------------------


def test_d_source_interruption_does_not_crash_core(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    # Send a MALFORMED frame (bad audio, non-frame bytes) directly to the port.
    import socket

    bad = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    bad.sendto(b"NOT-A-FRAME", (GROUP, e2e["port"]))
    bad.close()
    time.sleep(0.3)

    # Core (runtime + adapter) must remain alive after the malformed frame.
    assert e2e["adapter"].health() is True
    assert e2e["adapter"].is_running is True

    # A subsequent valid frame is still processed.
    sim.send(CONTENT_ID)
    sim.close()
    event = _wait_for_event(e2e["repo"])
    assert event is not None, "core did not recover after malformed frame"
    assert event.payload["content_id"] == CONTENT_ID


# -- E. Source recovery ------------------------------------------------------


def test_e_source_recovery_resumes_processing(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    event = _wait_for_event(e2e["repo"])
    assert event is not None
    first_count = e2e["repo"].count()

    # Source "interrupted" (simulator closed), then restored (new send).
    sim.close()
    time.sleep(0.2)
    assert e2e["repo"].count() == first_count

    # A distinct content id -> distinct event; processing resumed.
    sim2 = MulticastAudioSimulator(cfg)
    sim2.send("second-msg")
    sim2.close()
    assert _wait_for_count(e2e["repo"], first_count + 1, timeout=8.0)
    events = e2e["repo"].list_all()
    assert events[-1].payload["content_id"] == "second-msg"


# -- F. Chronology -----------------------------------------------------------


def test_f_chronology_occurred_at_preserved(e2e) -> None:
    from datetime import datetime, timezone

    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    # Send three events with controlled, non-monotonic occurrence times.
    times = [
        datetime(2026, 9, 2, 10, 30, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 2, 10, 32, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 2, 10, 31, 0, tzinfo=timezone.utc),
    ]
    for i, t in enumerate(times):
        sim.send(f"chrono-{i}", occurred_at=t)
    sim.close()

    assert _wait_for_count(e2e["repo"], 3, timeout=8.0)
    events = e2e["repo"].list_all()
    assert len(events) == 3
    # Each durable event's timestamp equals its controlled occurred_at.
    # (occurred_at is never replaced by ingestion time.)
    by_content = {e.payload["content_id"]: e for e in events}
    for i, t in enumerate(times):
        ev = by_content[f"chrono-{i}"]
        # SQLite persists UTC datetimes as naive; normalise both to aware UTC
        # before comparing instants.  The event timestamp must equal the
        # controlled occurred_at (never replaced by ingestion time).
        stored = ev.timestamp
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert stored == t, (
            f"event {i} timestamp {stored} != occurred_at {t}"
        )
        # ingested_at (created_at) differs from occurred_at for at least the
        # controlled events (created_at is the persist time, not event time).
        assert ev.created_at != ev.timestamp
    # The journal (operator feed) orders by durable seq (insertion order).
    seqs = [e2e["repo"].get_durable_event(e.event_id)[0] for e in events]
    assert seqs == sorted(seqs)


# -- G. Callsign extraction --------------------------------------------------


def test_g_callsign_detected_and_transcript_preserved(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    sim.close()
    event = _wait_for_event(e2e["repo"])
    assert event is not None
    payload = event.payload
    # Full transcript preserved.
    assert payload["transcript"] == PHRASE
    # Deterministic callsign extraction.
    assert payload["detected_callsigns"] == [CALLSIGN]
    assert payload["confidence"] == 1.0
    assert payload["detection_method"] == "configured-callsigns"
    # A convenience single callsign field is present.
    assert payload["callsign"] == CALLSIGN


# -- Operator SSE visibility (authoritative log -> SSE stream) ---------------


def test_operator_sse_emits_radio_event(e2e) -> None:
    import asyncio
    import json

    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.operator.app import create_operator_app

    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    sim.send(CONTENT_ID)
    sim.close()
    event = _wait_for_event(e2e["repo"])
    assert event is not None

    sm = e2e["sm"]
    app = create_operator_app(
        event_repository=e2e["repo"],
        entity_repository=SQLAlchemyEntityRepository(session_manager=sm),
        relation_repository=SQLAlchemyRelationRepository(session_manager=sm),
    )

    async def _consume():
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
            client.stream(
                "GET", "/api/v1/operator/events/stream?stream_ticks=0"
            ) as response,
        ):
            body = b"".join([chunk async for chunk in response.aiter_bytes()])
            return response.status_code, body

    status, body = asyncio.run(_consume())
    assert status == 200
    # Parse the SSE data frames and verify the authoritative durable event.
    frames = []
    for block in body.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.split("\n"):
            if line.startswith("data:"):
                frames.append(json.loads(line.split(":", 1)[1].strip()))
    assert frames, "no SSE data frames emitted"
    emitted = frames[-1]["event"]
    assert emitted["event_id"] == event.event_id
    assert emitted["source"] == "radio"
    assert emitted["payload"]["transcript"] == PHRASE
    assert emitted["payload"]["detected_callsigns"] == [CALLSIGN]


# -- Operator UI static assets (append-only) ---------------------------------


def test_operator_ui_exposes_radio_transcript_callsign() -> None:
    """The operator UI static assets render RADIO label + transcript + callsign."""
    import os

    static_dir = os.path.join(
        os.path.dirname(__file__), "..", "app", "operator", "static"
    )
    with open(os.path.join(static_dir, "operator.js"), encoding="utf-8") as fh:
        js = fh.read()
    with open(os.path.join(static_dir, "operator.css"), encoding="utf-8") as fh:
        css = fh.read()
    with open(os.path.join(static_dir, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    # JS renders the RADIO label + transcript + callsign.
    assert "radio-label" in js
    assert "RADIO" in js
    assert "radio-transcript" in js
    assert "radio-callsign" in js
    assert "detected_callsigns" in js
    # CSS defines the new classes (append-only, existing style untouched).
    assert ".radio-label" in css
    assert ".radio-transcript" in css
    assert ".radio-callsign" in css
    # index.html still references the stylesheet + script (unchanged wiring).
    assert "operator.css" in html
    assert "operator.js" in html


def test_h_scale_100_events_no_loss_no_uncontrolled_duplication(e2e) -> None:
    cfg = e2e["config"]
    sim = MulticastAudioSimulator(cfg)
    n = 100
    for i in range(n):
        sim.send(f"bulk-{i}")
    sim.close()

    assert _wait_for_count(e2e["repo"], n, timeout=20.0), (
        f"expected {n} durable events, got {e2e['repo'].count()}"
    )
    events = e2e["repo"].list_all()
    assert len(events) == n, "silent loss or uncontrolled duplication"
    # No duplicate canonical identities.
    ids = [e.event_id for e in events]
    assert len(set(ids)) == n, "duplicate event identities"
    # Ordering: durable seq is strictly ascending and contiguous.
    seqs = [e2e["repo"].get_durable_event(e.event_id)[0] for e in events]
    assert seqs == sorted(seqs)
    assert seqs == list(range(1, n + 1))
    # Every event carries its transcript/callsign fields.
    for e in events:
        assert "transcript" in e.payload
        assert "detected_callsigns" in e.payload
