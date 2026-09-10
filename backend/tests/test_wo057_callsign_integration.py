"""WO-057 — Integrated callsign detection into the production STT-derived transcript path.

WO-057 closes the confirmed production code seam:

    STT transcript -> CallsignDetector -> enriched transcript raw dict
        -> AdapterRuntime -> EventFactory -> EventPipeline -> Durable Journal

The derived transcript raw dict is enriched with the established WO-038 callsign
contract (``detected_callsigns``, ``confidence``, ``detection_method`` and the
primary ``callsign``) WITHOUT modifying the original transcript text.  The
canonical boundary (``EventFactory.create_event``), the Event model,
EventPipeline, the durable journal, and WO-055 flow isolation are all
preserved.  The STT boundary remains fail-closed when no production engine is
registered — a deterministic test transcriber is TEST-ONLY and never becomes a
production fallback.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import struct
import tempfile
from typing import Any

import pytest

import app.database.session as session_mod
from app.audio.callsign import CallsignDetector
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.audio.stt_config import SttConfig
from app.audio.stt_seam import AbstractSttAdapter, register_engine
from app.audio.stt_worker import SttJob, SttWorker
from app.audio.wav_writer import write_wav_atomic
from app.bootstrap import create_production_runtime
from app.contracts.audio import ITranscriber
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory

CALLSIGN = "Буревій-2"
PHRASE = f"{CALLSIGN}, підтверджую. Прийом."
NO_CALLSIGN_PHRASE = "Прийом. Підтверджую. Чекаю."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSttTranscriber(ITranscriber):
    """Deterministic TEST-ONLY transcriber (never a production fallback)."""

    def __init__(self, text: str, ready: bool = True) -> None:
        self._text = text
        self._ready = ready
        self.transcribe_calls: list[tuple[bytes, str | None]] = []

    @property
    def model(self) -> str:
        return "fake-stt"

    def is_ready(self) -> bool:
        return self._ready

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        self.transcribe_calls.append((audio_data, language))
        return self._text


def _write_wav(root: str, name: str = "rec") -> str:
    pcm = struct.pack("<1600h", *([1000] * 1600))
    path = os.path.join(root, f"{name}.wav")
    write_wav_atomic(pcm, path, 8000, 1, 2)
    return path


def _job(recording_id: str, wav_path: str, **kwargs: Any) -> SttJob:
    return SttJob(
        audio_recording_id=recording_id,
        wav_path=wav_path,
        source="radio",
        **kwargs,
    )


def _definition(port: int, **config_extra: Any) -> SourceDefinition:
    config: dict[str, Any] = {
        "multicast_address": "239.255.1.30",
        "multicast_port": port,
        "codec": "wav",
        "source_name": "radio",
    }
    config.update(config_extra)
    return SourceDefinition(
        name="radio-mc", adapter_type="multicast_audio", config=config
    )


def _recording_raw(wav_path: str, recording_id: str) -> dict[str, Any]:
    return {
        "timestamp": "2026-09-02T10:00:00+00:00",
        "occurred_at": "2026-09-02T10:00:00+00:00",
        "audio_recording_id": recording_id,
        "content_id": recording_id,
        "recording": {"wav_path": wav_path, "sha256": "x", "source": "radio"},
    }


# ---------------------------------------------------------------------------
# WO057-01 — integrated positive detection through the real SttWorker boundary
# ---------------------------------------------------------------------------


def test_wo057_01_integrated_positive_detection(tmp_path) -> None:
    """A transcript with a known callsign is enriched; the canonical boundary
    (EventFactory) receives the callsign fields and the original text verbatim."""
    wav = _write_wav(str(tmp_path))
    emitted: list[dict[str, Any]] = []
    fake = _FakeSttTranscriber(text=PHRASE)
    detector = CallsignDetector(callsigns=[CALLSIGN], confidence=1.0)
    worker = SttWorker(
        fake,
        source="radio",
        callsign_detector=detector,
        on_transcript=emitted.append,
    )
    worker.start()
    assert worker.submit(_job("rec-057-01", wav)) is True
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["processed"] == 1
    assert snap["failed"] == 0
    assert len(emitted) == 1

    raw = emitted[0]
    # Distinct deterministic identity for the derived transcript event.
    assert raw["content_id"] == "rec-057-01|transcript"
    # The ORIGINAL transcript text is preserved verbatim (never modified).
    assert raw["transcript"]["text"] == PHRASE
    # Existing WO-038 callsign contract.
    assert raw["detected_callsigns"] == [CALLSIGN]
    assert raw["confidence"] == 1.0
    assert raw["detection_method"] == "configured-callsigns"
    assert raw["callsign"] == CALLSIGN

    # The enriched raw dict crosses the ONE canonical boundary
    # (EventFactory.create_event) and the callsign fields land in Event.payload.
    ev = EventFactory().create_event(raw, "radio")
    assert isinstance(ev, Event)
    assert ev.payload["detected_callsigns"] == [CALLSIGN]
    assert ev.payload["confidence"] == 1.0
    assert ev.payload["detection_method"] == "configured-callsigns"
    assert ev.payload["callsign"] == CALLSIGN
    assert ev.payload["transcript"]["text"] == PHRASE

    assert worker.stop(timeout=5) is True


# ---------------------------------------------------------------------------
# WO057-02 — no callsign in the transcript: no fabrication
# ---------------------------------------------------------------------------


def test_wo057_02_no_callsign_no_fabrication(tmp_path) -> None:
    """A transcript without a callsign yields an empty/no-result representation
    and never fabricates a primary ``callsign``."""
    wav = _write_wav(str(tmp_path))
    emitted: list[dict[str, Any]] = []
    fake = _FakeSttTranscriber(text=NO_CALLSIGN_PHRASE)
    detector = CallsignDetector(callsigns=[CALLSIGN], confidence=1.0)
    worker = SttWorker(
        fake,
        source="radio",
        callsign_detector=detector,
        on_transcript=emitted.append,
    )
    worker.start()
    assert worker.submit(_job("rec-057-02", wav)) is True
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["processed"] == 1
    assert snap["failed"] == 0
    assert len(emitted) == 1

    raw = emitted[0]
    assert raw["transcript"]["text"] == NO_CALLSIGN_PHRASE  # unchanged
    assert raw["detected_callsigns"] == []
    assert raw["confidence"] == 0.0
    assert raw["detection_method"] == "none"
    # No primary callsign is fabricated for a no-callsign transcript.
    assert "callsign" not in raw

    assert worker.stop(timeout=5) is True


# ---------------------------------------------------------------------------
# WO057-03 — durable preservation through the real canonical path
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_wo057_03_durable_preservation(db_path, tmp_path) -> None:
    """STT -> transcript raw -> AdapterRuntime -> EventFactory -> EventPipeline
    -> durable repository: the callsign information survives into the persisted
    canonical event payload (no parallel persistence path)."""
    configure_session_manager(f"sqlite:///{db_path}")
    rt = create_production_runtime()
    repo = rt.event_runtime.pipeline._repository

    wav = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text=PHRASE)
    detector = CallsignDetector(callsigns=[CALLSIGN], confidence=1.0)
    worker = SttWorker(fake, source="radio", callsign_detector=detector)
    adapter = MulticastAudioSourceAdapter(_definition(52001), stt_worker=worker)
    aruntime = rt.add_source(adapter)
    adapter._running = True

    # A finalized recording is handed to the worker (off the receiver thread).
    adapter._on_recording(_recording_raw(wav, "rec-057-03"))
    assert worker.wait_idle(timeout=5)
    assert worker.snapshot()["processed"] == 1

    # Drain both the recording and the derived transcript raw events through the
    # canonical boundary and the real durable pipeline.
    for r in adapter.read_events():
        aruntime._process_raw(r)

    events = repo.list_all()
    transcript_events = [
        e for e in events if e.payload.get("content_id") == "rec-057-03|transcript"
    ]
    assert len(transcript_events) == 1, "the transcript event must be durably persisted"
    ev = transcript_events[0]
    assert isinstance(ev, Event)
    # Callsign information survives into the persisted canonical event payload.
    assert ev.payload["detected_callsigns"] == [CALLSIGN]
    assert ev.payload["confidence"] == 1.0
    assert ev.payload["detection_method"] == "configured-callsigns"
    assert ev.payload["callsign"] == CALLSIGN
    # The original transcript text is preserved verbatim.
    assert ev.payload["transcript"]["text"] == PHRASE

    session_mod._session_manager = None


# ---------------------------------------------------------------------------
# WO057-04 — STT remains fail-closed when no production engine is available
# ---------------------------------------------------------------------------


def test_wo057_04_fail_closed_no_production_fallback(tmp_path) -> None:
    """STT enabled but no authorized engine registered -> explicit UNAVAILABLE.
    The deterministic test transcriber is TEST-ONLY and never becomes a
    production fallback; no fake transcript/callsign is produced."""
    definition = _definition(
        52004,
        stt={"enabled": True, "engine": "faster_whisper", "model_path": str(tmp_path)},
    )
    adapter = MulticastAudioSourceAdapter(definition)
    assert adapter.stt_state == "UNAVAILABLE"
    assert adapter._stt_worker is not None
    assert adapter._stt_worker.available is False

    wav = _write_wav(str(tmp_path))
    adapter._on_recording(_recording_raw(wav, "rec-057-04"))
    snap = adapter._stt_worker.snapshot()
    assert snap["unavailable"] == 1
    assert snap["processed"] == 0
    # No transcript event is queued; only the recording event.
    contents = list(adapter._queue)
    assert all(
        c.get("content_id") != "rec-057-04|transcript" for c in contents
    )


# ---------------------------------------------------------------------------
# WO057-05 — production composition wires the callsign detector into the worker
# ---------------------------------------------------------------------------


class _FakeEngineAdapter(AbstractSttAdapter):
    """Minimal non-inference engine adapter used only to exercise the seam."""

    def __init__(self, config: SttConfig) -> None:
        super().__init__(config)
        self._ready = False

    def initialize(self, config: SttConfig) -> None:
        self._ready = True

    @property
    def model(self) -> str:
        return f"fake:{self._config.engine}"

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        return PHRASE

    def is_ready(self) -> bool:
        return self._ready


def test_wo057_05_production_composition_wires_callsign_detector(tmp_path) -> None:
    """The PRODUCTION composition path (``_build_production_stt_worker``) passes
    the adapter's configured callsign detector into the worker, so a derived
    transcript event carries the callsign fields (G1)."""
    register_engine("vosk", lambda config: _FakeEngineAdapter(config))
    detector = CallsignDetector(callsigns=[CALLSIGN], confidence=1.0)
    definition = _definition(
        52005,
        stt={"enabled": True, "engine": "vosk", "model_path": str(tmp_path)},
    )
    # No explicit stt_worker: the production composition builder runs.
    adapter = MulticastAudioSourceAdapter(definition, callsign_detector=detector)
    assert adapter.stt_state == "AVAILABLE"
    assert adapter._stt_worker is not None
    assert adapter._stt_worker.available is True
    # The worker uses the SAME detector the adapter was configured with.
    assert adapter._stt_worker._callsign_detector is detector

    wav = _write_wav(str(tmp_path))
    adapter._on_recording(_recording_raw(wav, "rec-057-05"))
    assert adapter._stt_worker.wait_idle(timeout=5)
    contents = list(adapter._queue)
    transcript_raws = [
        c for c in contents if c.get("content_id") == "rec-057-05|transcript"
    ]
    assert len(transcript_raws) == 1
    raw = transcript_raws[0]
    assert raw["transcript"]["text"] == PHRASE  # original text preserved
    assert raw["detected_callsigns"] == [CALLSIGN]
    assert raw["confidence"] == 1.0
    assert raw["detection_method"] == "configured-callsigns"
    assert raw["callsign"] == CALLSIGN
