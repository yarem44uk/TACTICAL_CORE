"""WO-056 — Production radio vertical slice / operator journal acceptance tests.

WO-056 is the first production-like RADIO VERTICAL SLICE: a real radio source
travels through the existing TACTICAL CORE architecture and becomes an
operator-visible durable event.

    REAL MULTICAST RADIO (RTP capture)
        -> RTP flow                 (RtpCaptureReader / FlowRouter)
        -> segmentation             (TransmissionRecorder VAD -> WAV master)
        -> STT                      (fail-closed in production; no engine)
        -> callsign detection       (CallsignDetector, seam)
        -> canonical input          (RecordingMetadata.to_event_raw)
        -> AdapterRuntime._process_raw
        -> EventFactory.create_event      (the ONE canonicalization boundary)
        -> canonical Event
        -> EventPipeline.process
        -> DURABLE EVENT JOURNAL    (DurableCanonicalEvent / SQLAlchemy)
        -> OPERATOR API             (operator service + app /api/v1/operator)
        -> OPERATOR UI              (operator static timeline rendering)

Acceptance tests AT-01 .. AT-09.  The tests drive the REAL production
composition (``app.bootstrap.create_production_runtime``) and the REAL
radio/audio adapter + recorder; they do NOT mock away AdapterRuntime,
EventFactory, EventPipeline or the durable repository.  The real RTP capture
fixture (``/opt/data/wo041_evidence/radio_rtp.pcapng``) is replayed through the
real receiver path where the environment provides it.

Level evidence hierarchy:
  AT-01/AT-02 use the REAL RTP capture -> Level 2 (production-composed replay
  through the real runtime -> durable event -> operator result).
  AT-03/AT-04/AT-05/AT-06/AT-09 use the production-composed raw path -> Level 2.
  AT-07 is a component (callsign detector) test -> Level 4.
  AT-08 is a flow-isolation reproduction -> Level 3.

The STT engine gate is NOT satisfied in this environment (no production STT
engine / acoustic model is provisioned).  The production adapter is fail-closed
(WO-041-CORR F-01): it never fabricates a transcript and never falls back to a
deterministic test transcriber, so the durable radio event carries the audio
metadata and source identity but no transcript/callsign.  That limitation is
reported as an environmental gate, not hidden.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.database.session as session_mod
from app.audio.alaw import alaw_encode_byte
from app.audio.audio_config import AudioConfig
from app.audio.callsign import CallsignDetector
from app.audio.flow_router import FlowKey, FlowRouter
from app.audio.recorder import RecordingMetadata, TransmissionRecorder
from app.audio.recording_config import RecordingConfig
from app.audio.rtp_capture import RtpCaptureReader
from app.audio.rtp_receiver import RtpReceiver
from app.audio.rtp_simulator import build_rtp_packet
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.bootstrap import create_production_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository as DurableCanonicalEventRepository,
)
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event_sources.config.source_definition import SourceDefinition
from app.operator.app import create_operator_app
from app.operator.service import OperatorService

SAMPLE_RATE = 8000
CHANNELS = 1
FRAME_SAMPLES = 160
FRAME_MS = 20
SPEECH = 20000
SILENCE = 50

# Verified real-capture facts (from the WO-041 golden capture).
GOLDEN = {
    "source_ip": "172.19.4.118",
    "dest_ip": "239.233.18.30",
    "port": 5033,
    "payload_type": 8,
    "ssrc": 536816391,
    "packet_count": 1772,
    "sample_rate": 8000,
    "channels": 1,
    "duration_s": 35.44,
}

OCCURRED_AT = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_definition(archive_root: str, source: str = "radio") -> SourceDefinition:
    """A production ``SourceDefinition`` that enables the WO-039-B recorder.

    No ``stt`` block -> STT disabled for the source -> the adapter is fail-closed
    (no transcript event), exactly as production behaves with no engine.
    """
    return SourceDefinition(
        name="radio-mc",
        adapter_type="multicast_audio",
        config={
            "multicast_address": "239.255.0.1",
            "multicast_port": 5033,
            "protocol": "rtp",
            "codec": "pcm_alaw",
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "source_name": source,
            "vad_enabled": True,
            "vad_adaptive": False,
            "vad_fixed_threshold": 2000.0,
            "pre_roll_ms": 400,
            "post_roll_ms": 800,
            "silence_timeout_ms": 1000,
            "min_speech_ms": 250,
            "audio_archive_root": archive_root,
            "mp3_enabled": False,
        },
    )


def _find_capture() -> str | None:
    candidates = [
        os.environ.get("WO041_PCAP"),
        "/opt/data/wo041_evidence/radio_rtp.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _real_frames() -> list[Any]:
    """Return the decoded PCM frames from the REAL radio RTP capture."""
    path = _find_capture()
    if path is None:
        pytest.skip("real radio RTP capture not available")
    reader = RtpCaptureReader(
        path,
        source_ip=GOLDEN["source_ip"],
        dest_ip=GOLDEN["dest_ip"],
        udp_port=GOLDEN["port"],
        payload_type=GOLDEN["payload_type"],
    )
    stream = reader.read()
    start = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    frames = list(reader.iter_frames(stream, start=start))
    assert len(frames) == GOLDEN["packet_count"], "real capture frame count drifted"
    return frames


def _operator_service() -> OperatorService:
    """Build the operator read facade against the global authoritative DB."""
    return OperatorService(
        event_repository=DurableCanonicalEventRepository(),
        entity_repository=SQLAlchemyEntityRepository(),
        relation_repository=SQLAlchemyRelationRepository(),
    )


def _recording_raw(
    content_id: str,
    occurred_at: datetime,
    source: str = "radio",
    duration_ms: float = 3000.0,
) -> dict[str, Any]:
    """Build an EventFactory-compatible recording raw dict (canonical shape)."""
    return RecordingMetadata(
        audio_recording_id=content_id,
        wav_path=f"/tmp/wo056-{content_id}.wav",
        mp3_path=None,
        started_at=occurred_at,
        ended_at=occurred_at + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        source=source,
        multicast_address="239.255.0.1",
        udp_port=5033,
        codec="pcm_alaw",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        sha256="a" * 64,
        complete=True,
        finalize_reason="silence_timeout",
    ).to_event_raw()


def _ingest_real(runtime, archive_root: str) -> tuple[MulticastAudioSourceAdapter, Any, list[dict]]:
    """Drive the REAL RTP capture through the production radio path.

    Returns ``(adapter, aruntime, raws)``.
    """
    adapter = MulticastAudioSourceAdapter(_source_definition(archive_root))
    aruntime = runtime.add_source(adapter)
    adapter._running = True
    rec = adapter._recorder
    assert rec is not None, "recording config must engage the recorder"
    for frame in _real_frames():
        adapter._on_pcm(frame)
    rec.on_shutdown()
    raws = adapter.read_events()
    assert raws, "the real radio capture must produce at least one recording raw"
    for r in raws:
        aruntime._process_raw(r)
    return adapter, aruntime, raws


def _ingest_raw(runtime, raws: list[dict], adapter: MulticastAudioSourceAdapter | None = None):
    """Process raw dicts through the production runtime canonical path."""
    if adapter is None:
        adapter = MulticastAudioSourceAdapter(_source_definition("/tmp/wo056-noop"))
    aruntime = runtime.add_source(adapter)
    adapter._running = True
    for r in raws:
        aruntime._process_raw(r)
    return aruntime


def _pcm(value: int, samples: int = FRAME_SAMPLES) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _rtp_bytes(ssrc: int, seq: int, ts: int, value: int = 0x55, n: int = 160) -> bytes:
    payload = bytes([value & 0xFF]) * n
    return build_rtp_packet(
        payload_type=8, sequence_number=seq, timestamp=ts, ssrc=ssrc, payload=payload
    )


def _rtp_config(port: int, group: str = "239.255.0.1", **overrides: Any) -> AudioConfig:
    return AudioConfig(
        multicast_address=group,
        multicast_port=port,
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=8,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        source_name="radio",
        join_interface="127.0.0.1",
        network_interface="AUTO",
        frame_timeout=0.2,
        **overrides,
    )


class _SpyRecorder:
    """A recorder stand-in that captures frames and records shutdown."""

    def __init__(self) -> None:
        self.frames: list[Any] = []
        self.shutdown_calls = 0

    def on_pcm(self, frame: Any) -> None:
        self.frames.append(frame)

    def on_shutdown(self) -> None:
        self.shutdown_calls += 1

    def snapshot(self) -> dict[str, Any]:
        return {"frames": len(self.frames), "shutdowns": self.shutdown_calls}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str):
    """Configure the canonical GLOBAL session manager to a fresh file SQLite."""
    manager = configure_session_manager(f"sqlite:///{db_path}")
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """The REAL production bootstrap runtime against the configured DB."""
    return create_production_runtime()


@pytest.fixture()
def archive_root() -> str:
    root = tempfile.mkdtemp(prefix="wo056_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# AT-01 — Real radio event -> one canonical event -> one durable event
# ---------------------------------------------------------------------------


def test_at01_real_radio_event_one_canonical_one_durable(runtime, archive_root) -> None:
    """A REAL RTP radio capture becomes exactly one canonical + one durable event."""
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime, raws = _ingest_real(runtime, archive_root)

    assert len(raws) == 1, "one real transmission must produce one recording raw"
    assert repo.count() == 1, "one source event must be one durable event"

    events = repo.list_all()
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.source == "radio"
    assert ev.event_type == EventType.CUSTOM
    assert ev.payload["content_id"] == ev.payload["audio_recording_id"]
    # occurred_at is preserved as the canonical event timestamp (EventFactory
    # normalizes to naive UTC; compare instants, not string formatting).
    raw = raws[0]
    assert datetime.fromisoformat(raw["occurred_at"]) == ev.timestamp.replace(
        tzinfo=timezone.utc
    )
    # Source metadata survives.
    rec = ev.payload["recording"]
    assert rec["source"] == "radio"
    assert rec["multicast_address"] == "239.255.0.1"
    assert rec["udp_port"] == 5033
    assert len(rec["sha256"]) == 64
    assert os.path.exists(rec["wav_path"])
    # The real capture is one 35.44 s continuous stream.
    assert abs(rec["duration_ms"] - GOLDEN["duration_s"] * 1000.0) < 1.0


# ---------------------------------------------------------------------------
# AT-02 — Operator visibility (durable event retrievable + rendered fields)
# ---------------------------------------------------------------------------


def test_at02_operator_visibility(runtime, archive_root, db_path) -> None:
    """The durable radio event is retrievable by the operator API/UI."""
    repo = runtime.event_runtime.pipeline._repository
    _ingest_real(runtime, archive_root)

    # Service-level retrieval (the operator API's query path).
    service = _operator_service()
    page = service.list_events(source="radio", limit=50)
    events = page["events"]
    assert len(events) == 1, "the radio event must be operator-visible"
    ev = events[0]
    # Fields the operator timeline renders.
    assert ev["source"] == "radio"
    assert "timestamp" in ev
    assert "payload" in ev and "recording" in ev["payload"]

    # HTTP operator API surface (real FastAPI app over the same authoritative DB).
    app = create_operator_app()
    with TestClient(app) as client:
        resp = client.get("/api/v1/operator/events", params={"source": "radio"})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["source"] == "radio"


# ---------------------------------------------------------------------------
# AT-03 — Chronology (occurred_at / ingested_at / canonical_seq / ordering)
# ---------------------------------------------------------------------------


def test_at03_chronology_ordering(runtime, archive_root) -> None:
    """10+ events preserve occurred_at, ingested_at and a monotonic canonical_seq."""
    repo = runtime.event_runtime.pipeline._repository
    n = 12
    raws = []
    t0 = OCCURRED_AT
    for i in range(n):
        raws.append(_recording_raw(f"rec-wo056-chrono-{i:03d}", t0 + timedelta(seconds=i * 5)))
    _ingest_raw(runtime, raws)

    assert repo.count() == n
    rows = repo.list_all()  # deterministic seq ASC order
    assert len(rows) == n

    # canonical_seq is strictly increasing and assigned in ingest order.
    seqs = [repo.get_durable_event(e.event_id)[0] for e in rows]
    assert seqs == sorted(seqs), "canonical_seq must be monotonic"
    assert len(set(seqs)) == n

    # occurred_at is preserved per event and ordering follows occurred_at.
    for i, e in enumerate(rows):
        assert e.timestamp.replace(tzinfo=timezone.utc) == t0 + timedelta(seconds=i * 5)
        assert e.payload["content_id"] == f"rec-wo056-chrono-{i:03d}"
        # ingested_at (created_at) is set and distinct from occurred_at.
        assert e.created_at is not None
        assert e.created_at != e.timestamp

    # Operator ordering matches occurred_at (chronology uses occurred_at).
    service = _operator_service()
    page = service.list_events(source="radio", limit=100)
    stamps = [datetime.fromisoformat(e["timestamp"]) for e in page["events"]]
    assert stamps == sorted(stamps), "operator chronology must follow occurred_at"


# ---------------------------------------------------------------------------
# AT-04 — Duplicate delivery -> no uncontrolled duplicate durable event
# ---------------------------------------------------------------------------


def test_at04_duplicate_delivery_idempotent(runtime, archive_root) -> None:
    """Delivering the same logical source event twice yields one durable event."""
    repo = runtime.event_runtime.pipeline._repository
    raw = _recording_raw("rec-wo056-dup", OCCURRED_AT)
    aruntime = _ingest_raw(runtime, [raw, raw])  # same raw delivered twice

    assert repo.count() == 1, "duplicate delivery must not create a second durable event"
    events = repo.list_all()
    assert len(events) == 1
    assert events[0].payload["content_id"] == "rec-wo056-dup"


# ---------------------------------------------------------------------------
# AT-05 — Restart persistence (durable across a session-manager restart)
# ---------------------------------------------------------------------------


def test_at05_restart_persistence(db_path, archive_root) -> None:
    """A durable radio event survives a real session-manager restart."""
    sm = configure_session_manager(f"sqlite:///{db_path}")
    rt = create_production_runtime()
    repo = rt.event_runtime.pipeline._repository
    _ingest_real(rt, archive_root)
    events = repo.list_all()
    assert len(events) == 1
    event_id = events[0].event_id

    # Simulate a service restart: dispose the manager, open the SAME file again.
    session_mod._session_manager = None
    configure_session_manager(f"sqlite:///{db_path}")
    repo2 = DurableCanonicalEventRepository()
    assert repo2.exists(event_id) is True, "event did not survive restart"
    restored = repo2.get(event_id)
    assert restored is not None
    assert restored.event_id == event_id
    assert restored.source == "radio"
    session_mod._session_manager = None


# ---------------------------------------------------------------------------
# AT-06 — Source interruption / recovery (simulated)
# ---------------------------------------------------------------------------


def test_at06_source_interruption_recovery(runtime, archive_root) -> None:
    """Core stays operational through an interruption; recovery resumes.

    NOTE: this is a SIMULATED interruption (no real multicast network is
    available in this environment).  It proves the runtime remains operational,
    prior durable events remain, and resumed ingestion adds new events without a
    duplicate storm.  A real-network interruption cannot be exercised here.
    """
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime, _ = _ingest_real(runtime, archive_root)

    # Interruption: the source stops feeding.  Core must remain operational.
    assert aruntime._events_processed >= 1
    assert repo.count() == 1

    # Recovery: resume ingestion with a distinct logical event through the SAME
    # runtime (no second adapter registration).
    aruntime._process_raw(
        _recording_raw("rec-wo056-recover", OCCURRED_AT + timedelta(minutes=1))
    )
    assert repo.count() == 2
    # No uncontrolled duplicate storm.
    assert len({e.event_id for e in repo.list_all()}) == 2


# ---------------------------------------------------------------------------
# AT-07 — Callsign detection (transcript preserved + callsigns + confidence)
# ---------------------------------------------------------------------------


def test_at07_callsign_detection() -> None:
    """A known callsign in a transcript is detected; transcript is preserved."""
    detector = CallsignDetector(
        callsigns=["Буревій-2"],
        confidence=1.0,
        heuristic_confidence=0.7,
    )
    transcript = "Буревій-2, підтверджую. Прийом."
    result = detector.detect(transcript)

    assert result.text == transcript, "the original transcript must be preserved"
    assert "Буревій-2" in result.detected_callsigns
    assert result.confidence == 1.0
    assert result.detection_method == "configured-callsigns"


def test_at07b_callsign_heuristic_preserves_transcript() -> None:
    """The default heuristic extracts <letters>-<digits> callsigns."""
    detector = CallsignDetector()
    transcript = "Сокіл-1 на зв'язку, чекаю. Говорить Сокіл-1."
    result = detector.detect(transcript)
    assert result.text == transcript
    assert "Сокіл-1" in result.detected_callsigns
    assert result.detection_method == "heuristic"
    assert 0.0 < result.confidence <= 1.0


# ---------------------------------------------------------------------------
# AT-08 — Multi-source UDP flow isolation (A -> B -> A -> B -> A)
# ---------------------------------------------------------------------------


def test_at08_multisource_flow_isolation_ababa() -> None:
    """A -> B -> A -> B -> A keeps independent per-flow RTP state (WO-055)."""
    cfg = _rtp_config(5033)
    router = FlowRouter(recorder_factory=lambda fk: _SpyRecorder(), max_flows=10)
    receiver = RtpReceiver(cfg, on_pcm=lambda f: None, flow_router=router)
    addr_a = ("10.0.0.1", 1000)
    addr_b = ("10.0.0.2", 2000)

    # A1, B1, A2, B2, A3
    receiver._handle_payload(_rtp_bytes(0xAAAA, 1, 0), addr_a)
    receiver._handle_payload(_rtp_bytes(0xBBBB, 100, 0), addr_b)
    receiver._handle_payload(_rtp_bytes(0xAAAA, 2, 160), addr_a)
    receiver._handle_payload(_rtp_bytes(0xBBBB, 101, 160), addr_b)
    receiver._handle_payload(_rtp_bytes(0xAAAA, 3, 320), addr_a)

    snap_a = router.get_or_create(FlowKey("10.0.0.1", 1000, 5033)).tracker.snapshot()
    snap_b = router.get_or_create(FlowKey("10.0.0.2", 2000, 5033)).tracker.snapshot()

    # A's state is never contaminated by B.
    assert snap_a["current_ssrc"] == 0xAAAA
    assert snap_a["packets_received"] == 3
    assert snap_a["last_sequence"] == 3
    assert snap_a["sequence_gaps"] == 0
    assert snap_a["ssrc_transitions"] == 0
    # B's state is independent.
    assert snap_b["packets_received"] == 2
    assert snap_b["last_sequence"] == 101
    assert snap_b["current_ssrc"] == 0xBBBB
    assert snap_b["sequence_gaps"] == 0


# ---------------------------------------------------------------------------
# AT-09 — 100+ event durability (production path, no uncontrolled duplicates)
# ---------------------------------------------------------------------------


def test_at09_100_plus_events_durability(runtime, archive_root) -> None:
    """100+ events through the production path: no loss, no dup, stable order."""
    repo = runtime.event_runtime.pipeline._repository
    n = 120
    raws = []
    t0 = OCCURRED_AT
    for i in range(n):
        raws.append(_recording_raw(f"rec-wo056-bulk-{i:03d}", t0 + timedelta(seconds=i)))
    _ingest_raw(runtime, raws)

    assert repo.count() == n, "no unexplained loss"
    events = repo.list_all()
    assert len(events) == n
    assert len({e.event_id for e in events}) == n, "no uncontrolled duplicates"

    # Stable chronology: seq monotonic and operator retrieval functional.
    seqs = [repo.get_durable_event(e.event_id)[0] for e in events]
    assert seqs == sorted(seqs)
    service = _operator_service()
    page = service.list_events(source="radio", limit=200)
    assert len(page["events"]) == n
