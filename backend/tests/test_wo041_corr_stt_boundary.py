"""WO-041-CORR tests — production STT fail-closed boundary & legacy path elimination.

These tests pin the corrected production STT boundary (WO-041-CORR):

  * F-01: ``DeterministicTestTranscriber`` is NOT a production default.
  * F-02: real RTP packets do NOT generate packet-level transcript events.
  * F-03: ``SttWorker`` is the only intended production transcription boundary,
    driven by the finalized WAV master (not per-packet audio).
  * No authorized acoustic engine -> explicit fail-closed (UNAVAILABLE), never a
    fake transcript.
  * No engine is selected here; the boundary is engine-neutral and offline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Any

import pytest

from app.audio.audio_config import AudioConfig
from app.audio.callsign import CallsignDetector
from app.audio.rtp_receiver import RtpPcmFrame
from app.audio.source_adapter import (
    MulticastAudioSourceAdapter,
    make_multicast_audio_adapter,
)
from app.audio.stt_config import SttConfig
from app.audio.stt_seam import (
    AbstractSttAdapter,
    SttEngineUnavailableError,
    build_transcriber,
    register_engine,
)
from app.audio.stt_worker import SttJob, SttWorker, SttWorkerError
from app.audio.transcriber import DeterministicTestTranscriber
from app.audio.wav_writer import write_wav_atomic
from app.contracts.audio import ITranscriber
from app.event_sources.config.source_definition import SourceDefinition

GROUP = "239.255.1.20"
PHRASE = "Буревій-2, прийом. Виходжу на позицію."
CALLSIGN = "Буревій-2"


def _definition(port: int, **config_extra: Any) -> SourceDefinition:
    config: dict[str, Any] = {
        "multicast_address": GROUP,
        "multicast_port": port,
        "codec": "wav",
        "source_name": "radio",
        "join_interface": "127.0.0.1",
    }
    config.update(config_extra)
    return SourceDefinition(
        name="radio-mc", adapter_type="multicast_audio", config=config
    )


def _rtp_definition(port: int, **config_extra: Any) -> SourceDefinition:
    config: dict[str, Any] = {
        "protocol": "rtp",
        "multicast_address": GROUP,
        "multicast_port": port,
        "codec": "pcm_alaw",
        "payload_type": 8,
        "sample_rate": 8000,
        "channels": 1,
        "source_name": "radio",
        "join_interface": "127.0.0.1",
    }
    config.update(config_extra)
    return SourceDefinition(
        name="radio-rtp", adapter_type="multicast_audio", config=config
    )


def _pcm_frame(seq: int = 1, ts: int = 0, ssrc: int = 100) -> RtpPcmFrame:
    return RtpPcmFrame(
        pcm=b"\x55" * 160,
        sequence_number=seq,
        timestamp=ts,
        ssrc=ssrc,
        payload_type=8,
        sample_rate=8000,
        channels=1,
        received_at=datetime.now(timezone.utc),
    )


def _write_wav(root: str, name: str = "rec") -> str:
    pcm = struct.pack("<1600h", *([1000] * 1600))
    path = f"{root}/{name}.wav"
    write_wav_atomic(pcm, path, 8000, 1, 2)
    return path


class _FakeSttTranscriber(ITranscriber):
    """Deterministic test transcriber for the C3 worker seam (test-only)."""

    def __init__(self, text: str = "прийом", ready: bool = True) -> None:
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


class _FakeEngineAdapter(AbstractSttAdapter):
    """A minimal non-inference engine adapter used only to exercise the seam."""

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


def _recording_raw(wav_path: str, recording_id: str = "rec-abc") -> dict[str, Any]:
    return {
        "timestamp": "2026-09-02T10:00:00+00:00",
        "occurred_at": "2026-09-02T10:00:00+00:00",
        "audio_recording_id": recording_id,
        "content_id": recording_id,
        "recording": {"wav_path": wav_path, "sha256": "x", "source": "radio"},
    }


# ---------------------------------------------------------------------------
# F-01 — DeterministicTestTranscriber is NOT a production default
# ---------------------------------------------------------------------------


def test_production_construction_no_deterministic_default() -> None:
    """Building an adapter without an explicit transcriber must NOT instantiate
    ``DeterministicTestTranscriber`` (WO-041-CORR F-01)."""
    adapter = make_multicast_audio_adapter(_definition(51001))
    assert adapter._transcriber is None
    assert not isinstance(adapter._transcriber, DeterministicTestTranscriber)
    # STT disabled (no stt config) -> no worker, explicit DISABLED state.
    assert adapter.stt_state == "DISABLED"


def test_explicit_test_transcriber_still_accepted() -> None:
    """An explicitly injected test transcriber (test-only path) still works."""
    adapter = MulticastAudioSourceAdapter(
        _definition(51002),
        transcriber=DeterministicTestTranscriber(phrase_map={"bureviy-2": PHRASE}),
        callsign_detector=CallsignDetector(callsigns=[CALLSIGN]),
    )
    assert isinstance(adapter._transcriber, DeterministicTestTranscriber)
    # The TCA1 (non-RTP) path with an explicit transcriber still transcribes.
    from app.audio.audio_segment import AudioSegment

    segment = AudioSegment(
        content_id="bureviy-2",
        audio_bytes=b"pcm",
        occurred_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        is_pcm=True,
    )
    adapter._on_segment(segment)
    contents = list(adapter._queue)
    assert len(contents) == 1
    assert contents[0]["transcript"] == PHRASE


# ---------------------------------------------------------------------------
# F-02 — RTP packets MUST NOT generate packet-level transcript events
# ---------------------------------------------------------------------------


def test_rtp_packet_callback_no_transcript_event() -> None:
    """The RTP packet callback (``_on_pcm``) must NOT produce a transcript event
    through the deterministic STT path (WO-041-CORR F-02)."""
    adapter = MulticastAudioSourceAdapter(_rtp_definition(51003))
    # No recorder / no worker: packets accumulate nothing.
    adapter._on_pcm(_pcm_frame(seq=1, ts=0))
    adapter._on_pcm(_pcm_frame(seq=2, ts=160))
    assert adapter.read_events() == []
    assert adapter.stt_state == "DISABLED"


def test_rtp_packet_callback_no_deterministic_transcriber_used() -> None:
    """Feeding RTP packets must never invoke the deterministic transcriber."""
    calls: list[str] = []

    class _SpyTranscriber(DeterministicTestTranscriber):
        def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
            calls.append("transcribe")
            return super().transcribe(audio_data, language)

        def transcribe_detailed(self, *a: Any, **k: Any) -> Any:
            calls.append("transcribe_detailed")
            return super().transcribe_detailed(*a, **k)

    adapter = MulticastAudioSourceAdapter(
        _rtp_definition(51004),
        transcriber=_SpyTranscriber(phrase_map={"x": "y"}),
    )
    adapter._on_pcm(_pcm_frame(seq=1, ts=0))
    assert calls == [], "RTP packet callback must not invoke the transcriber"
    assert adapter.read_events() == []


# ---------------------------------------------------------------------------
# F-03 — finalized WAV -> SttWorker is the STT boundary
# ---------------------------------------------------------------------------


def test_recording_finalization_submits_stt_job(tmp_path) -> None:
    """A finalized recording (``_on_recording``) submits an ``SttJob`` to the
    worker with the WAV path as the STT input."""
    wav = _write_wav(str(tmp_path))
    worker = SttWorker(_FakeSttTranscriber(), source="radio")
    adapter = MulticastAudioSourceAdapter(
        _definition(51005), stt_worker=worker
    )
    adapter._on_recording(_recording_raw(wav))
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["processed"] == 1
    assert snap["failed"] == 0


def test_wav_path_is_stt_input(tmp_path) -> None:
    """The SttJob carries the finalized WAV path (the authoritative STT input)."""
    wav = _write_wav(str(tmp_path))
    submitted: list[SttJob] = []

    class _RecordingWorker(SttWorker):
        def submit(self, job: SttJob) -> bool:
            submitted.append(job)
            return True

    worker = _RecordingWorker(_FakeSttTranscriber(), source="radio")
    adapter = MulticastAudioSourceAdapter(
        _definition(51006), stt_worker=worker
    )
    adapter._on_recording(_recording_raw(wav))
    assert len(submitted) == 1
    assert submitted[0].wav_path == wav
    assert submitted[0].audio_recording_id == "rec-abc"


def test_one_transmission_one_transcript_event(tmp_path) -> None:
    """One finalized transmission yields exactly ONE derived transcript event
    (multiple RTP packets belonging to one transmission do NOT multiply it)."""
    wav = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="прийом")
    worker = SttWorker(fake, source="radio")
    adapter = MulticastAudioSourceAdapter(
        _definition(51007), stt_worker=worker
    )
    # Simulate many RTP packets feeding the recorder (none produce events).
    for i in range(10):
        adapter._on_pcm(_pcm_frame(seq=i, ts=i * 160))
    assert adapter.read_events() == []
    # The single finalized recording produces exactly one transcript event.
    adapter._on_recording(_recording_raw(wav))
    assert worker.wait_idle(timeout=5)
    contents = list(adapter._queue)
    transcript_raws = [
        c for c in contents if c.get("content_id") == "rec-abc|transcript"
    ]
    assert len(transcript_raws) == 1
    assert transcript_raws[0]["transcript"]["text"] == "прийом"


# ---------------------------------------------------------------------------
# No authorized engine -> explicit fail-closed (UNAVAILABLE)
# ---------------------------------------------------------------------------


def test_no_engine_fail_closed(tmp_path) -> None:
    """STT enabled but no authorized engine registered -> explicit UNAVAILABLE,
    no fake transcript (WO-041-CORR F-01/F-03)."""
    definition = _definition(
        51008,
        stt={"enabled": True, "engine": "faster_whisper", "model_path": str(tmp_path)},
    )
    adapter = MulticastAudioSourceAdapter(definition)
    # Recognized engine but no adapter registered -> fail-closed UNAVAILABLE.
    assert adapter.stt_state == "UNAVAILABLE"
    assert adapter._stt_worker is not None
    assert adapter._stt_worker.available is False
    wav = _write_wav(str(tmp_path))
    adapter._on_recording(_recording_raw(wav))
    snap = adapter._stt_worker.snapshot()
    assert snap["unavailable"] == 1
    assert snap["processed"] == 0
    # No transcript event is queued; only the recording event.
    contents = list(adapter._queue)
    assert all(c.get("content_id") != "rec-abc|transcript" for c in contents)


def test_no_engine_worker_rejects_job(tmp_path) -> None:
    """A fail-closed worker rejects jobs and never fabricates a transcript."""
    worker = SttWorker(None, source="radio")
    assert worker.available is False
    assert worker.state == "UNAVAILABLE"
    assert worker.submit(SttJob("r1", "/tmp/nonexistent.wav", source="radio")) is False
    assert worker.snapshot()["unavailable"] == 1
    assert worker.snapshot()["processed"] == 0
    # The worker never starts a thread in the fail-closed state.
    assert worker._thread is None


def test_worker_process_guards_none_transcriber() -> None:
    """A direct ``_process`` call on a fail-closed worker raises (no transcript)."""
    worker = SttWorker(None, source="radio")
    with pytest.raises(SttWorkerError):
        worker._process(SttJob("r1", "/tmp/nonexistent.wav", source="radio"))


# ---------------------------------------------------------------------------
# A registered fake/test adapter can still exercise the seam (test-only)
# ---------------------------------------------------------------------------


def test_registered_fake_engine_exercises_seam(tmp_path) -> None:
    """A test-registered engine adapter (test-only) reaches AVAILABLE and
    produces a derived transcript event through the WAV boundary."""
    register_engine("vosk", lambda config: _FakeEngineAdapter(config))
    definition = _definition(
        51009,
        stt={"enabled": True, "engine": "vosk", "model_path": str(tmp_path)},
    )
    adapter = MulticastAudioSourceAdapter(definition)
    assert adapter.stt_state == "AVAILABLE"
    assert adapter._stt_worker.available is True
    wav = _write_wav(str(tmp_path))
    adapter._on_recording(_recording_raw(wav))
    assert adapter._stt_worker.wait_idle(timeout=5)
    contents = list(adapter._queue)
    transcript_raws = [
        c for c in contents if c.get("content_id") == "rec-abc|transcript"
    ]
    assert len(transcript_raws) == 1
    assert transcript_raws[0]["transcript"]["text"] == PHRASE


# ---------------------------------------------------------------------------
# build_transcriber seam remains fail-closed (no silent fallback)
# ---------------------------------------------------------------------------


def test_build_transcriber_no_silent_fallback(tmp_path) -> None:
    """A recognized engine with no registered adapter raises (no fallback)."""
    cfg = SttConfig(
        enabled=True, engine="faster_whisper", model_path=str(tmp_path)
    )
    with pytest.raises(SttEngineUnavailableError):
        build_transcriber(cfg)
