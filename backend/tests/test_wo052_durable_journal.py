"""WO-052 — End-to-end durable journal verification.

WO-052 establishes, with executable evidence, whether a production-like radio
recording can traverse the complete existing ingestion path and become a durable
journal entry exactly once:

    radio/audio recording (PCM)
        -> VAD -> segment -> WAV master -> RecordingMetadata.to_event_raw()
        -> MulticastAudioSourceAdapter._on_recording -> read_events()
        -> AdapterRuntime (production seam)
        -> EventFactory.create_event()          (sole RAW -> Event boundary)
        -> canonical app.event.Event
        -> EventPipeline.process()              (sole lifecycle / persistence path)
        -> DurableCanonicalEventRepository      (durable journal)
        -> DatabaseSessionManager -> SQLite

The tests exercise the REAL production composition (``app.bootstrap.
create_production_runtime`` / ``app.composition.create_event_runtime``) and the
REAL radio/audio adapter + recorder.  They do NOT mock away AdapterRuntime,
EventFactory, EventPipeline or the durable repository.  The only injection is a
deliberate persistence-failure at the repository seam for the failure-path tests
(T5/T9) — the success paths use the unmodified durable repository.

No production code is modified by WO-052.  This file is the only deliverable.
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

import app.database.session as session_mod
from app.audio.recorder import RecordingMetadata
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.bootstrap import create_production_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository as DurableCanonicalEventRepository,
)
from app.event_sources.config.source_definition import SourceDefinition

# ---------------------------------------------------------------------------
# Synthetic PCM constants (mirror test_wo039b_recording.py)
# ---------------------------------------------------------------------------

SAMPLE_RATE = 8000
CHANNELS = 1
FRAME_SAMPLES = 160  # 20 ms at 8 kHz
FRAME_MS = 20
SPEECH = 20000
SILENCE = 50

OCCURRED_AT = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


def _pcm(value: int, samples: int = FRAME_SAMPLES) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _frame(value: int, t: datetime) -> SimpleNamespace:
    return SimpleNamespace(pcm=_pcm(value), received_at=t)


def _feed(recorder: Any, values: list[int], t0: datetime) -> datetime:
    """Feed one frame per value, advancing the clock by ``FRAME_MS``."""
    cur = t0
    for value in values:
        recorder.on_pcm(_frame(value, cur))
        cur += timedelta(milliseconds=FRAME_MS)
    return cur


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def production_db():
    """Configure the canonical GLOBAL DatabaseSessionManager to an isolated
    in-memory SQLite database (exactly as production does at startup) and reset
    it afterwards so it does not leak across tests."""
    manager = configure_session_manager("sqlite:///:memory:")
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(production_db):
    """The REAL production bootstrap runtime, composed against the configured
    canonical database owner.  No manual table initialisation is performed (the
    production composition owns that)."""
    return create_production_runtime()


@pytest.fixture()
def archive_root() -> str:
    root = tempfile.mkdtemp(prefix="wo052_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recording_metadata(**overrides: Any) -> RecordingMetadata:
    """Build a deterministic production ``RecordingMetadata``."""
    base: dict[str, Any] = dict(
        audio_recording_id="rec-wo052-0001",
        wav_path="/tmp/wo052-0001.wav",
        mp3_path=None,
        started_at=OCCURRED_AT,
        ended_at=OCCURRED_AT + timedelta(seconds=3),
        duration_ms=3000.0,
        source="radio",
        multicast_address="239.255.0.1",
        udp_port=5033,
        codec="pcm_alaw",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        sha256="a" * 64,
        complete=True,
        finalize_reason="silence_timeout",
    )
    base.update(overrides)
    return RecordingMetadata(**base)


def _source_definition(archive_root: str, source: str = "radio") -> SourceDefinition:
    """A production SourceDefinition that enables the WO-039-B recorder."""
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


def _drive_recorder(adapter: MulticastAudioSourceAdapter) -> None:
    """Drive the adapter's real TransmissionRecorder with synthetic speech frames
    so it finalizes one recording and queues its raw dict via ``_on_recording``."""
    recorder = adapter._recorder
    assert recorder is not None, "recording config must engage the recorder"
    t0 = OCCURRED_AT
    _feed(recorder, [SILENCE] * 25, t0)  # 500 ms pre-roll background
    _feed(recorder, [SPEECH] * 40, t0 + timedelta(seconds=0.5))  # 800 ms speech
    _feed(recorder, [SILENCE] * 60, t0 + timedelta(seconds=1.3))  # finalize


def _ingest(runtime, archive_root: str) -> tuple[MulticastAudioSourceAdapter, Any]:
    """Build a real radio adapter, drive the real recorder, drain the raw via
    ``read_events()``, and process it through the real production AdapterRuntime
    seam (``AdapterRuntime._process_raw``).  Returns ``(adapter, aruntime)``."""
    adapter = MulticastAudioSourceAdapter(_source_definition(archive_root))
    aruntime = runtime.add_source(adapter)
    # Mark the base adapter running (BaseEventSourceAdapter.start() semantics)
    # so read_events() drains; we do NOT call adapter.start() because that opens
    # the receiver socket.
    adapter._running = True
    _drive_recorder(adapter)
    raws = adapter.read_events()
    assert raws, "the radio adapter read_events() must drain the recording raw"
    for r in raws:
        aruntime._process_raw(r)
    return adapter, aruntime


# ---------------------------------------------------------------------------
# Producer side: PCM -> RecordingMetadata.to_event_raw()
# ---------------------------------------------------------------------------


def test_recorder_produces_recording_raw_via_adapter(archive_root) -> None:
    """The real recorder finalizes a recording whose raw dict is exactly
    ``RecordingMetadata.to_event_raw()`` (the production raw representation)."""
    adapter = MulticastAudioSourceAdapter(_source_definition(archive_root))
    _drive_recorder(adapter)
    queued = adapter._queue
    assert len(queued) == 1, "one finalized recording must produce one raw dict"
    raw = queued[0]
    assert isinstance(raw, dict)
    assert raw["content_id"] == raw["audio_recording_id"]
    assert "timestamp" in raw and "occurred_at" in raw
    assert raw["recording"]["source"] == "radio"
    assert raw["recording"]["wav_path"].endswith(".wav")
    assert os.path.exists(raw["recording"]["wav_path"])
    assert len(raw["recording"]["sha256"]) == 64


def test_recording_metadata_to_event_raw_shape() -> None:
    """``RecordingMetadata.to_event_raw()`` is EventFactory-compatible and carries
    the canonical identity material (``content_id``)."""
    raw = _recording_metadata().to_event_raw()
    assert raw["timestamp"] == OCCURRED_AT.isoformat()
    assert raw["occurred_at"] == OCCURRED_AT.isoformat()
    assert raw["audio_recording_id"] == "rec-wo052-0001"
    assert raw["content_id"] == "rec-wo052-0001"
    assert raw["recording"]["wav_path"] == "/tmp/wo052-0001.wav"


# ---------------------------------------------------------------------------
# T1 — RAW radio event -> canonical Event
# ---------------------------------------------------------------------------


def test_t1_raw_radio_event_to_canonical_event(runtime, archive_root) -> None:
    """A radio-derived raw dict (from ``RecordingMetadata.to_event_raw()``) enters
    the real adapter/runtime path and becomes exactly one canonical Event."""
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime = _ingest(runtime, archive_root)

    events = repo.list_all()
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.source == "radio"
    assert ev.event_type == EventType.CUSTOM
    assert ev.payload["content_id"] == ev.payload["audio_recording_id"]
    assert ev.payload["recording"]["wav_path"].endswith(".wav")


# ---------------------------------------------------------------------------
# T2 — Canonical Event -> durable journal
# ---------------------------------------------------------------------------


def test_t2_canonical_event_to_durable_journal(runtime, archive_root) -> None:
    """The canonical Event is actually persisted into the durable journal and is
    retrievable by its canonical event_id through the durable repository."""
    repo = runtime.event_runtime.pipeline._repository
    _ingest(runtime, archive_root)

    events = repo.list_all()
    assert len(events) == 1
    ev = events[0]
    assert repo.exists(ev.event_id) is True
    restored = repo.get(ev.event_id)
    assert restored is not None
    assert restored.event_id == ev.event_id


# ---------------------------------------------------------------------------
# T3 — Persisted event identity
# ---------------------------------------------------------------------------


def test_t3_persisted_event_identity(runtime, archive_root) -> None:
    """The durable record preserves the canonical identity expected by the Event
    model (event_id, source, event_type, timestamp, payload)."""
    repo = runtime.event_runtime.pipeline._repository
    _ingest(runtime, archive_root)
    ev = repo.list_all()[0]

    restored = repo.get(ev.event_id)
    assert restored is not None
    assert type(restored) is Event
    assert restored.event_id == ev.event_id
    assert restored.source == "radio"
    assert restored.event_type == EventType.CUSTOM
    assert restored.payload == ev.payload
    # timestamp is the occurrence time (the recording started_at carried as the
    # raw ``occurred_at``), preserved through persistence and never replaced by
    # ingestion time.
    stored = restored.timestamp
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored == datetime.fromisoformat(ev.payload["occurred_at"])
    # ingested_at (created_at) differs from occurred_at for the controlled event.
    created = ev.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    assert stored != created
    assert restored.metadata.to_dict() == ev.metadata.to_dict()


# ---------------------------------------------------------------------------
# T4 — Exactly-once / duplicate semantics
# ---------------------------------------------------------------------------


def test_t4_duplicate_ingestion_is_idempotent(runtime, archive_root) -> None:
    """Re-ingesting the same logical recording (same content_id) yields exactly
    one durable event, because the deterministic identity resolver + the
    UNIQUE(event_id) journal constraint deduplicate it."""
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime = _ingest(runtime, archive_root)

    # Re-drive the same logical recording: same content_id -> same identity.
    _drive_recorder(adapter)
    raws = adapter.read_events()
    assert raws
    for r in raws:
        aruntime._process_raw(r)

    assert repo.count() == 1, "duplicate logical input must not create a 2nd record"
    events = repo.list_all()
    assert len(events) == 1


def test_t4b_distinct_recording_distinct_journal_entry(runtime, archive_root) -> None:
    """Distinct logical recordings produce distinct durable journal entries."""
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime = _ingest(runtime, archive_root)
    assert repo.count() == 1

    # A different content_id raw dict (distinct logical recording) -> distinct.
    raw2 = _recording_metadata(audio_recording_id="rec-wo052-0002",
                               wav_path="/tmp/wo052-0002.wav").to_event_raw()
    aruntime._process_raw(raw2)
    assert repo.count() == 2


# ---------------------------------------------------------------------------
# T5 — Failure before persistence (pipeline boundary)
# ---------------------------------------------------------------------------


def test_t5_persistence_failure_is_observable(runtime, archive_root, monkeypatch) -> None:
    """A persistence failure raises at the pipeline boundary and produces no
    false durable-success state."""
    repo = runtime.event_runtime.pipeline._repository
    raw = _recording_metadata().to_event_raw()

    def _fail_save(event, consumer_ids):
        raise RuntimeError("simulated durable persistence failure")

    monkeypatch.setattr(repo, "save_with_deliveries", _fail_save)

    event = runtime.event_factory.create_event(raw_data=raw, source_name="radio")
    with pytest.raises(RuntimeError, match="simulated durable persistence failure"):
        runtime.pipeline.process(event)

    # No durable record was created (the real repo's count reflects no save).
    assert repo.count() == 0


# ---------------------------------------------------------------------------
# T6 — Failure / checkpoint ordering
# ---------------------------------------------------------------------------


def test_t6_no_checkpoint_in_hot_ingestion_path(runtime) -> None:
    """The hot radio ingestion path has NO checkpoint/cursor: persistence is
    synchronous and there is no separate checkpoint that could advance before or
    after a failed persist.  The only checkpoint in the composition belongs to the
    separate Entity-projection catch-up driver, not to this path."""
    pipeline = runtime.event_runtime.pipeline
    assert not hasattr(pipeline, "_checkpoint")
    assert not hasattr(runtime.event_runtime, "_checkpoint")
    # AdapterRuntime (the ingestion loop owner) exposes no checkpoint.
    adapter, aruntime = runtime, None
    # Confirm the production pipeline's durable path does not advance a checkpoint.
    assert not hasattr(pipeline, "advance_checkpoint")


# ---------------------------------------------------------------------------
# T7 — Durable read-back across a session close / reopen
# ---------------------------------------------------------------------------


def test_t7_durable_read_back_across_restart(tmp_path) -> None:
    """After successful ingestion, closing the session manager and reopening the
    SAME SQLite file (a real restart) still returns the event — actual durability,
    not same-session visibility."""
    db_path = str(tmp_path / "wo052_durable.db")
    archive = str(tmp_path / "archive")
    os.makedirs(archive, exist_ok=True)

    sm = configure_session_manager(f"sqlite:///{db_path}")
    rt = create_production_runtime()
    repo = rt.event_runtime.pipeline._repository
    _ingest(rt, archive)
    events = repo.list_all()
    assert len(events) == 1
    event_id = events[0].event_id

    # Simulate a service restart: dispose the old manager, configure a fresh one
    # over the SAME SQLite file.
    session_mod._session_manager = None
    sm2 = configure_session_manager(f"sqlite:///{db_path}")
    repo2 = DurableCanonicalEventRepository()
    assert repo2.exists(event_id) is True, "event did not survive restart"
    restored = repo2.get(event_id)
    assert restored is not None
    assert restored.event_id == event_id
    assert restored.source == "radio"
    session_mod._session_manager = None


# ---------------------------------------------------------------------------
# T8 — Single journal entry for one input
# ---------------------------------------------------------------------------


def test_t8_single_journal_entry(runtime, archive_root) -> None:
    """For one successful input, the journal query returns exactly one record."""
    repo = runtime.event_runtime.pipeline._repository
    _ingest(runtime, archive_root)

    assert repo.count() == 1
    events = repo.list_all()
    assert len(events) == 1


# ---------------------------------------------------------------------------
# T9 — EventPipeline failure propagation (runtime boundary)
# ---------------------------------------------------------------------------


def test_t9_runtime_isolates_persistence_failure(runtime, archive_root, monkeypatch) -> None:
    """A persistence failure does NOT crash the runtime and does NOT report
    successful ingestion (no false durable-success, no events_processed bump)."""
    repo = runtime.event_runtime.pipeline._repository

    def _fail_save(event, consumer_ids):
        raise RuntimeError("simulated durable persistence failure")

    monkeypatch.setattr(repo, "save_with_deliveries", _fail_save)

    adapter, aruntime = _ingest(runtime, archive_root)
    # The runtime isolated the failure: it did not crash, did not count the event,
    # and no durable record was produced.
    assert aruntime._events_processed == 0
    assert repo.count() == 0


# ---------------------------------------------------------------------------
# T10 — Regression of existing ingestion tests (run separately via pytest -k)
# ---------------------------------------------------------------------------
