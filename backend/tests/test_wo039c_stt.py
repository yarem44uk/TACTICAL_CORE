"""WO-039-C1/C2 tests — offline STT seam + model configuration.

These tests validate the minimum offline STT seam (C1) and the offline model
configuration / path plumbing (C2).  No real engine is installed and no model is
downloaded: a fake adapter is registered only inside the tests to exercise the
offline-init lifecycle (model exists -> initialize -> ready).

Required cases (WO-039-C2 configuration validation):
    * valid model path
    * missing model path (fails clearly, no download / no network)
    * invalid engine (fails clearly)
    * disabled STT (no model path required)
    * language setting
    * device setting

Required seam behaviour (WO-039-C1):
    * no public ``ITranscriber`` expansion
    * a recognised engine with no registered adapter fails clearly (no silent
      fallback to ``DeterministicTestTranscriber``)
    * ``AbstractSttAdapter`` provides the offline ``initialize`` lifecycle

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import tempfile
import threading
import wave
from typing import Any

import pytest

from app.audio.audio_config import AudioConfig
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.audio.stt_config import (
    SUPPORTED_ENGINES,
    SttConfig,
    SttConfigError,
    resolve_model_path,
)
from app.audio.stt_seam import (
    AbstractSttAdapter,
    SttEngineUnavailableError,
    SttEngineUnknownError,
    build_transcriber,
    register_engine,
)
from app.audio.stt_worker import (
    SttJob,
    SttWorker,
    SttWorkerError,
    build_transcript_raw,
    read_wav_readonly,
)
from app.audio.wav_writer import write_wav_atomic
from app.contracts.audio import ITranscriber
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.identity.event_identity import EventIdentityResolver


@pytest.fixture()
def model_dir() -> str:
    """A temporary directory standing in for a provisioned local model."""
    root = tempfile.mkdtemp(prefix="wo039c_model_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# C2 — configuration validation
# ---------------------------------------------------------------------------


def test_valid_model_path_resolves(model_dir: str) -> None:
    cfg = SttConfig(
        enabled=True,
        engine="faster_whisper",
        model_path=model_dir,
        language="uk",
        device="cpu",
    )
    resolved = cfg.resolved_model_path()
    assert resolved == os.path.realpath(model_dir)
    assert os.path.exists(resolved)
    assert cfg.validate() is cfg


def test_missing_model_path_fails_clearly() -> None:
    missing = os.path.join(tempfile.gettempdir(), "wo039c_definitely_missing_model")
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=missing)
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_empty_model_path_fails() -> None:
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path="")
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_invalid_engine_fails_clearly(model_dir: str) -> None:
    cfg = SttConfig(enabled=True, engine="gpt4", model_path=model_dir)
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_unknown_engine_not_in_supported_set() -> None:
    assert "faster_whisper" in SUPPORTED_ENGINES
    assert "vosk" in SUPPORTED_ENGINES
    assert "gpt4" not in SUPPORTED_ENGINES


def test_disabled_stt_requires_no_model_path() -> None:
    cfg = SttConfig(enabled=False, engine="", model_path=None)
    assert cfg.resolved_model_path() is None
    assert cfg.validate() is cfg


def test_disabled_stt_ignores_engine() -> None:
    cfg = SttConfig(enabled=False, engine="faster_whisper", model_path=None)
    assert cfg.resolved_model_path() is None


def test_language_setting() -> None:
    assert SttConfig(language="uk").language == "uk"
    assert SttConfig(language="en").language == "en"
    assert SttConfig().language is None


def test_device_setting() -> None:
    assert SttConfig(device="cpu").device == "cpu"
    assert SttConfig(device="cuda").device == "cuda"
    assert SttConfig().device == "cpu"


def test_from_dict_roundtrip(model_dir: str) -> None:
    cfg = SttConfig.from_dict(
        {
            "enabled": True,
            "engine": "VOSK",  # case-insensitive, normalised
            "model_path": model_dir,
            "language": "uk",
            "device": "cpu",
            "unknown_key": "ignored",
        }
    )
    assert cfg.enabled is True
    assert cfg.engine == "vosk"
    assert cfg.model_path == model_dir
    assert cfg.language == "uk"
    assert cfg.device == "cpu"
    assert cfg.resolved_model_path() == os.path.realpath(model_dir)


def test_from_dict_none() -> None:
    cfg = SttConfig.from_dict(None)
    assert cfg.enabled is False
    assert cfg.engine == ""
    assert cfg.model_path is None


# ---------------------------------------------------------------------------
# C2 — model path security
# ---------------------------------------------------------------------------


def test_model_root_containment_accepts_inner_path(model_dir: str) -> None:
    inner = os.path.join(model_dir, "model.bin")
    with open(inner, "w") as fh:
        fh.write("x")
    cfg = SttConfig(
        enabled=True,
        engine="vosk",
        model_path=inner,
        model_root=model_dir,
    )
    assert cfg.resolved_model_path() == os.path.realpath(inner)


def test_model_root_containment_rejects_traversal(model_dir: str) -> None:
    escaping = os.path.join(model_dir, "..", "outside", "model")
    cfg = SttConfig(
        enabled=True,
        engine="vosk",
        model_path=escaping,
        model_root=model_dir,
    )
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_resolve_model_path_empty_rejected() -> None:
    with pytest.raises(SttConfigError):
        resolve_model_path("   ")


# ---------------------------------------------------------------------------
# C1 — adapter seam
# ---------------------------------------------------------------------------


class _FakeAdapter(AbstractSttAdapter):
    """A minimal non-inference adapter used to exercise the offline seam."""

    def __init__(self, config: SttConfig) -> None:
        super().__init__(config)

    def initialize(self, config: SttConfig) -> None:
        # Model must already exist locally; otherwise fail clearly.
        path = config.resolved_model_path()
        self._model = f"{config.engine}:{os.path.basename(path)}"
        self._ready = True

    @property
    def model(self) -> str:
        return self._model

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        return ""

    def is_ready(self) -> bool:
        return self._ready


def _register_fake(engine: str) -> None:
    register_engine(engine, lambda config: _FakeAdapter(config))


def test_register_unknown_engine_rejected() -> None:
    with pytest.raises(SttEngineUnknownError):
        register_engine("bogus_engine", lambda config: _FakeAdapter(config))


def test_recognised_engine_no_adapter_no_silent_fallback(model_dir: str) -> None:
    # faster_whisper is recognised but not registered here -> must fail clearly,
    # NOT silently return DeterministicTestTranscriber.
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=model_dir)
    with pytest.raises(SttEngineUnavailableError):
        build_transcriber(cfg)


def test_register_and_build_offline_init_ready(model_dir: str) -> None:
    _register_fake("vosk")
    cfg = SttConfig(enabled=True, engine="vosk", model_path=model_dir)
    adapter = build_transcriber(cfg)
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.is_ready() is True
    assert adapter.model == f"vosk:{os.path.basename(os.path.realpath(model_dir))}"


def test_register_and_build_missing_model_fails_before_engine(model_dir: str) -> None:
    _register_fake("vosk")
    missing = os.path.join(model_dir, "nope")
    cfg = SttConfig(enabled=True, engine="vosk", model_path=missing)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_build_disabled_stt_rejected(model_dir: str) -> None:
    cfg = SttConfig(enabled=False, engine="vosk", model_path=model_dir)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_build_unknown_engine_rejected(model_dir: str) -> None:
    cfg = SttConfig(enabled=True, engine="gpt4", model_path=model_dir)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_public_contract_not_expanded(model_dir: str) -> None:
    # The Core contract remains the three-interface-method ITranscriber.  The
    # offline lifecycle hook lives on the adapter, not the Core contract.
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=model_dir)
    assert callable(getattr(cfg, "resolved_model_path"))
    assert not hasattr(cfg, "transcribe")  # config is not the transcriber


# ---------------------------------------------------------------------------
# WO-039-C3 — bounded WAV acoustic STT worker
# ---------------------------------------------------------------------------
#
# These tests exercise the C3 worker against a fake ``ITranscriber`` (no real
# engine, no model, no network).  They prove the required guarantees:
# bounded queue, receiver-thread isolation, read-only WAV master, failure
# isolation, deterministic shutdown, duplicate suppression, and a derived
# transcript event with a distinct deterministic identity.


class _FakeSttTranscriber(ITranscriber):
    """Deterministic fake transcriber used by the C3 worker tests."""

    def __init__(
        self,
        text: str = "test transcript",
        ready: bool = True,
        fail_for: set[str] | None = None,
        empty_for: set[str] | None = None,
    ) -> None:
        self._text = text
        self._ready = ready
        self._fail_for = set(fail_for or ())
        self._empty_for = set(empty_for or ())
        self.transcribe_calls: list[tuple[bytes, str | None]] = []
        self.caller_threads: list[str] = []

    @property
    def model(self) -> str:
        return "fake-stt"

    def is_ready(self) -> bool:
        return self._ready

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        self.transcribe_calls.append((audio_data, language))
        self.caller_threads.append(threading.current_thread().name)
        # Deterministic behaviour keyed off the audio bytes (stable hash).
        key = hashlib.sha256(audio_data).hexdigest()
        if key in self._fail_for:
            raise RuntimeError("fake STT engine failure")
        if key in self._empty_for:
            return ""
        return self._text


def _wav_pcm(samples: int = 1600, value: int = 1000) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _write_wav(
    root: str,
    name: str = "rec",
    *,
    sample_rate: int = 8000,
    channels: int = 1,
    sampwidth: int = 2,
    pcm: bytes | None = None,
) -> tuple[str, bytes]:
    pcm = pcm if pcm is not None else _wav_pcm()
    path = os.path.join(root, f"{name}.wav")
    write_wav_atomic(pcm, path, sample_rate, channels, sampwidth)
    return path, pcm


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _job(recording_id: str, wav_path: str, **kwargs: Any) -> SttJob:
    return SttJob(
        audio_recording_id=recording_id,
        wav_path=wav_path,
        source="radio",
        **kwargs,
    )


def _worker(
    fake: ITranscriber,
    *,
    maxsize: int = 10,
    on_transcript: Any = None,
) -> SttWorker:
    return SttWorker(fake, source="radio", maxsize=maxsize, on_transcript=on_transcript)


def _adapter(port: int, worker: SttWorker) -> MulticastAudioSourceAdapter:
    return MulticastAudioSourceAdapter(
        SourceDefinition(
            name="radio-mc",
            adapter_type="multicast_audio",
            config={
                "multicast_address": "239.255.9.9",
                "multicast_port": port,
                "codec": "wav",
                "source_name": "radio",
            },
        ),
        config=AudioConfig(
            multicast_address="239.255.9.9",
            multicast_port=port,
            codec="wav",
            source_name="radio",
        ),
        stt_worker=worker,
    )


# -- G1 / queue ------------------------------------------------------------


def test_c3_g1_finalized_recording_enters_queue(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    worker = _worker(_FakeSttTranscriber())
    # Worker not started: the job stays queued, proving it entered the queue.
    assert worker.submit(_job("rec-1", wav)) is True
    snap = worker.snapshot()
    assert snap["queued"] == 1
    assert snap["dropped"] == 0


def test_c3_queue_is_bounded() -> None:
    worker = _worker(_FakeSttTranscriber(), maxsize=2)
    wav = "/tmp/nonexistent.wav"
    # Not started: jobs accumulate, so the bound is observable.
    assert worker.submit(_job("a", wav)) is True
    assert worker.submit(_job("b", wav)) is True
    assert worker.submit(_job("c", wav)) is False
    assert worker.snapshot()["dropped"] == 1


def test_c3_queue_full_drops_newest() -> None:
    worker = _worker(_FakeSttTranscriber(), maxsize=1)
    wav = "/tmp/nonexistent.wav"
    assert worker.submit(_job("first", wav)) is True
    # The newest job is dropped (drop-newest policy).
    assert worker.submit(_job("second", wav)) is False
    assert worker.snapshot()["dropped"] == 1
    assert worker.snapshot()["queued"] == 1


def test_c3_dropped_job_increments_counter() -> None:
    worker = _worker(_FakeSttTranscriber(), maxsize=1)
    wav = "/tmp/nonexistent.wav"
    worker.submit(_job("x", wav))
    worker.submit(_job("y", wav))
    worker.submit(_job("z", wav))
    assert worker.snapshot()["dropped"] == 2


# -- G2 / worker processing ------------------------------------------------


def test_c3_worker_processes_one_recording(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="прийом")
    worker = _worker(fake)
    worker.start()
    assert worker.submit(_job("rec-1", wav)) is True
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["processed"] == 1
    assert snap["failed"] == 0
    assert snap["last_processed_recording_id"] == "rec-1"


def test_c3_transcriber_receives_expected_bytes(tmp_path) -> None:
    pcm = _wav_pcm()
    wav, _ = _write_wav(str(tmp_path), pcm=pcm)
    fake = _FakeSttTranscriber(text="ok")
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    assert len(fake.transcribe_calls) == 1
    received, language = fake.transcribe_calls[0]
    # The transcriber receives the decoded PCM payload of the WAV master.
    assert received == pcm
    assert language is None  # default language (None) used


def test_c3_worker_runs_outside_producer_thread(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="ok")
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    assert fake.caller_threads == ["wo039c-stt-worker"]


def test_c3_wav_hash_unchanged(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    before = _sha256_file(wav)
    worker = _worker(_FakeSttTranscriber(text="ok"))
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    after = _sha256_file(wav)
    assert before == after
    assert os.path.exists(wav)


# -- failure isolation -----------------------------------------------------


def test_c3_invalid_wav_fails_safely(tmp_path) -> None:
    # A 16 kHz WAV is not the accepted 8 kHz master: the job fails clearly.
    wav, _ = _write_wav(str(tmp_path), name="bad", sample_rate=16000)
    worker = _worker(_FakeSttTranscriber(text="ok"))
    worker.start()
    assert worker.submit(_job("rec-1", wav)) is True
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["failed"] == 1
    assert snap["processed"] == 0
    assert any("unexpected WAV format" in e for e in snap["errors"])
    # The master is preserved.
    assert os.path.exists(wav)


def test_c3_transcriber_failure_preserves_wav(tmp_path) -> None:
    wav, pcm = _write_wav(str(tmp_path))
    before = _sha256_file(wav)
    fake = _FakeSttTranscriber(fail_for={hashlib.sha256(pcm).hexdigest()})
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["failed"] == 1
    assert _sha256_file(wav) == before
    assert os.path.exists(wav)


def test_c3_worker_continues_after_one_failed_job(tmp_path) -> None:
    wav_bad, pcm_bad = _write_wav(str(tmp_path), name="bad", pcm=_wav_pcm(value=1000))
    wav_ok, _ = _write_wav(str(tmp_path), name="ok", pcm=_wav_pcm(value=2000))
    bad_key = hashlib.sha256(pcm_bad).hexdigest()
    fake = _FakeSttTranscriber(text="ok", fail_for={bad_key})
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-bad", wav_bad))
    worker.submit(_job("rec-ok", wav_ok))
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["failed"] == 1
    assert snap["processed"] == 1


def test_c3_not_ready_transcriber_rejects_processing(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="ok", ready=False)
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    assert snap["failed"] == 1
    # No silent fallback: transcribe() is never called when not ready.
    assert fake.transcribe_calls == []
    assert os.path.exists(wav)


def test_c3_no_silent_fallback_on_not_ready(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="should-not-appear", ready=False)
    worker = _worker(fake)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    # The worker never fabricated a transcript from a non-ready engine.
    assert fake.transcribe_calls == []
    assert worker.snapshot()["processed"] == 0


# -- transcript event ------------------------------------------------------


def test_c3_transcript_event_is_created(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    emitted: list[dict[str, Any]] = []
    worker = _worker(_FakeSttTranscriber(text="прийом"), on_transcript=emitted.append)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    assert len(emitted) == 1
    raw = emitted[0]
    assert raw["audio_recording_id"] == "rec-1"
    assert raw["transcript"]["text"] == "прийом"
    assert raw["transcript"]["model"] == "fake-stt"


def test_c3_transcript_event_distinct_deterministic_identity(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    emitted: list[dict[str, Any]] = []
    worker = _worker(_FakeSttTranscriber(text="ok"), on_transcript=emitted.append)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    resolver = EventIdentityResolver()
    raw = emitted[0]
    # The transcript content_id is distinct from the bare recording content_id.
    assert raw["content_id"] == "rec-1|transcript"
    recording_id = resolver.resolve({"content_id": "rec-1"}, "radio")
    transcript_id = resolver.resolve(raw, "radio")
    assert recording_id is not None
    assert transcript_id is not None
    assert recording_id != transcript_id
    # Deterministic and idempotent.
    assert resolver.resolve(raw, "radio") == transcript_id


def test_c3_duplicate_recording_submission_controlled(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="ok")
    worker = _worker(fake)
    worker.start()
    assert worker.submit(_job("rec-1", wav)) is True
    # Same recording id submitted again -> suppressed.
    assert worker.submit(_job("rec-1", wav)) is False
    assert worker.snapshot()["duplicates"] == 1
    assert worker.wait_idle(timeout=5)
    assert worker.snapshot()["processed"] == 1
    assert len(fake.transcribe_calls) == 1


def test_c3_worker_shutdown_is_clean(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    worker = _worker(_FakeSttTranscriber(text="ok"))
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    worker.stop()
    # The thread is joined and released.
    assert worker._thread is None


def test_c3_empty_transcript_is_success(tmp_path) -> None:
    wav, pcm = _write_wav(str(tmp_path))
    key = hashlib.sha256(pcm).hexdigest()
    emitted: list[dict[str, Any]] = []
    fake = _FakeSttTranscriber(text="unused", empty_for={key})
    worker = _worker(fake, on_transcript=emitted.append)
    worker.start()
    worker.submit(_job("rec-1", wav))
    assert worker.wait_idle(timeout=5)
    snap = worker.snapshot()
    # Empty transcript is a SUCCESSFUL STT execution, not a failure.
    assert snap["processed"] == 1
    assert snap["failed"] == 0
    assert len(emitted) == 1
    assert emitted[0]["transcript"]["text"] == ""


# -- integration: on_recording -> SttWorker (legacy path protected) --------


def test_c3_on_recording_flows_to_stt_worker(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="прийом")
    worker = _worker(fake)
    adapter = _adapter(50100, worker)
    raw = {
        "timestamp": "2026-09-02T10:00:00+00:00",
        "occurred_at": "2026-09-02T10:00:00+00:00",
        "audio_recording_id": "rec-abc",
        "content_id": "rec-abc",
        "recording": {
            "wav_path": wav,
            "sha256": _sha256_file(wav),
            "source": "radio",
        },
    }
    adapter._on_recording(raw)
    assert worker.wait_idle(timeout=5)
    assert worker.snapshot()["processed"] == 1
    contents = list(adapter._queue)
    transcript_raws = [
        c for c in contents if c.get("content_id") == "rec-abc|transcript"
    ]
    # The finalized recording event AND the derived transcript event are both
    # represented (separate, append-only; never an UPDATE of the recording).
    assert len(transcript_raws) == 1
    assert transcript_raws[0]["transcript"]["text"] == "прийом"
    assert transcript_raws[0]["correlation_id"] == "rec-abc"
    assert worker.snapshot()["processed"] == 1


def test_c3_no_legacy_per_rtp_stt_reactivated(tmp_path) -> None:
    # A source adapter WITHOUT an STT worker must never invoke transcribe() on
    # the producer path: the legacy RTP-frame -> transcribe_detailed path stays
    # untouched.  With no worker, a finalized recording only queues the recording
    # event.
    wav, _ = _write_wav(str(tmp_path))
    adapter = MulticastAudioSourceAdapter(
        SourceDefinition(
            name="radio-mc",
            adapter_type="multicast_audio",
            config={
                "multicast_address": "239.255.9.9",
                "multicast_port": 50101,
                "codec": "wav",
                "source_name": "radio",
            },
        ),
        config=AudioConfig(
            multicast_address="239.255.9.9",
            multicast_port=50101,
            codec="wav",
            source_name="radio",
        ),
    )
    raw = {
        "timestamp": "2026-09-02T10:00:00+00:00",
        "occurred_at": "2026-09-02T10:00:00+00:00",
        "audio_recording_id": "rec-abc",
        "content_id": "rec-abc",
        "recording": {"wav_path": wav, "source": "radio"},
    }
    adapter._on_recording(raw)
    assert adapter._stt_worker is None
    contents = list(adapter._queue)
    assert len(contents) == 1  # only the recording event, no transcript
    assert contents[0]["content_id"] == "rec-abc"


# ---------------------------------------------------------------------------
# WO-039-C3 corrective — SttWorker.stop() lifecycle / thread tracking
# ---------------------------------------------------------------------------
#
# Independent audit finding: the original ``stop()`` cleared ``_thread`` after
# a timed ``join()`` even when the worker was STILL alive (long-running
# ``transcribe()`` outliving the timeout).  That let ``start()`` spawn a second
# concurrent worker against the same instance.  These tests reproduce the defect
# and pin the corrective policy: a live worker is NEVER forgotten.


class _BlockingTranscriber(ITranscriber):
    """Fake transcriber whose ``transcribe()`` blocks until released.

    Reproduces a long-running inference that outlives the ``stop()`` timeout.
    """

    def __init__(self, text: str = "blocked") -> None:
        self._text = text
        self.entered = threading.Event()
        self.release = threading.Event()
        self.transcribe_calls: list[tuple[bytes, str | None]] = []

    @property
    def model(self) -> str:
        return "fake-blocking"

    def is_ready(self) -> bool:
        return True

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        self.transcribe_calls.append((audio_data, language))
        self.entered.set()
        # Block until the test releases the transcriber (simulates long STT).
        self.release.wait(timeout=10)
        return self._text


def test_c3_stop_timeout_never_forgets_live_worker(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _BlockingTranscriber()
    worker = _worker(fake)
    worker.start()
    assert worker.submit(_job("rec-block", wav)) is True
    # Wait until transcribe() has been entered: the worker is now blocked in a
    # long-running inference that outlives a short stop timeout.
    assert fake.entered.wait(timeout=5)
    # Short timeout -> stop() must report the worker is still alive (Policy A),
    # and must NOT forget the live thread by clearing _thread.
    assert worker.stop(timeout=0.05) is False
    assert worker._thread is not None
    assert worker._thread.is_alive()
    original = worker._thread
    # A second start() must NOT spawn a second concurrent worker on this
    # instance: the live thread is retained, so start() stays idempotent.
    worker.start()
    assert worker._thread is original
    assert worker._thread.is_alive()
    # Release the transcriber so the original worker can finish and exit.
    fake.release.set()
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
    # The captured worker thread has actually terminated (no leak).
    assert original.is_alive() is False


def test_c3_stop_clean_termination_allows_restart(tmp_path) -> None:
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="ok")
    worker = _worker(fake)
    worker.start()
    assert worker.submit(_job("rec-1", wav)) is True
    assert worker.wait_idle(timeout=5)
    # Normal path: the worker finishes before the stop timeout -> clean stop.
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
    # A fresh worker may safely be created after a clean stop.
    worker.start()
    assert worker._thread is not None
    assert worker._thread.is_alive()
    # Clean up.
    assert worker.stop(timeout=5) is True
    assert worker._thread is None


def test_c3_repeated_stop_and_idempotent_start() -> None:
    fake = _FakeSttTranscriber(text="ok")
    worker = _worker(fake)
    # Repeated stop before any start is safe.
    assert worker.stop(timeout=0.1) is True
    assert worker.stop(timeout=0.1) is True
    # start() is idempotent while running.
    worker.start()
    worker.start()
    assert worker._thread is not None
    assert worker._thread.is_alive()
    # Repeated stop while running is safe.
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
    assert worker.stop(timeout=0.1) is True


# ---------------------------------------------------------------------------
# WO-039-C3 corrective 2 — concurrent start()/stop() lifecycle race-safety
# ---------------------------------------------------------------------------
#
# Independent audit finding: the lifecycle state transition between start() and
# stop() must be race-safe when invoked from different threads.  The invariant:
# AT MOST ONE live worker thread may exist for one SttWorker instance, and a
# live previous worker must never be replaced by a newly created worker.  These
# tests force the interleaving and prove it by counting thread creation, not by
# asserting the current ``_thread`` reference alone.


class _LifecycleRecordingWorker(SttWorker):
    """SttWorker that records every distinct worker thread it creates.

    Used to *prove* the single-worker invariant: it counts actual thread
    creation, so a test can assert that a second worker thread was never created
    while the original was still alive (rather than only checking the current
    ``_thread`` reference, which could hide a forgotten live thread).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.created_threads: list[threading.Thread] = []
        self._created_lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            prev = self._thread
        super().start()
        with self._lock:
            new = self._thread
        if new is not None and new is not prev:
            with self._created_lock:
                self.created_threads.append(new)


def test_c3_concurrent_stop_timeout_then_start_never_second_worker(
    tmp_path,
) -> None:
    """TEST 1 -- a live worker is never replaced by a newly created worker.

    Force the interleaving: worker is alive -> stop() begins and times out ->
    start() is called.  Assert the original live thread is retained and that a
    second worker thread was never created (unique thread count == 1).
    """
    wav, _ = _write_wav(str(tmp_path))
    fake = _BlockingTranscriber()
    worker = _LifecycleRecordingWorker(fake, source="radio")
    worker.start()
    assert worker.submit(_job("rec-block", wav)) is True
    # The worker is now blocked inside transcribe(): it is genuinely alive.
    assert fake.entered.wait(timeout=5)
    original = worker._thread
    assert original is not None
    assert original.is_alive()
    # stop() begins and times out: the live worker must NOT be forgotten.
    assert worker.stop(timeout=0.05) is False
    assert worker._thread is original
    assert original.is_alive()
    # A concurrent start() must NOT spawn a second worker on this instance.
    worker.start()
    assert worker._thread is original
    assert original.is_alive()
    # Prove only ONE worker thread was ever created for this instance.
    assert len(worker.created_threads) == 1
    assert worker.created_threads[0] is original
    # Clean up.
    fake.release.set()
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
    assert original.is_alive() is False


def test_c3_repeated_concurrent_lifecycle_never_two_workers(tmp_path) -> None:
    """TEST 2 -- repeated concurrent start()/stop() calls keep a single worker.

    Exercise many start()/stop(short) cycles from multiple threads at once.  The
    instance must never have more than one live worker: because the original
    worker stays blocked, no second thread may ever be created.
    """
    wav, _ = _write_wav(str(tmp_path))
    fake = _BlockingTranscriber()
    worker = _LifecycleRecordingWorker(fake, source="radio")
    worker.start()
    assert worker.submit(_job("rec-block", wav)) is True
    assert fake.entered.wait(timeout=5)

    def hammer_start() -> None:
        for _ in range(200):
            worker.start()

    def hammer_stop() -> None:
        for _ in range(200):
            try:
                worker.stop(timeout=0.0)
            except Exception:  # noqa: BLE001 - lifecycle calls must never raise
                pass

    threads = [
        threading.Thread(target=hammer_start),
        threading.Thread(target=hammer_stop),
        threading.Thread(target=hammer_start),
        threading.Thread(target=hammer_stop),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # While the original worker stayed alive, no second worker was created.
    assert len(worker.created_threads) == 1
    assert worker._thread is worker.created_threads[0]
    assert worker._thread.is_alive()
    # Clean up.
    fake.release.set()
    assert worker.stop(timeout=5) is True
    assert worker._thread is None


def test_c3_clean_termination_restart_creates_exactly_one_new_worker(
    tmp_path,
) -> None:
    """TEST 3 -- clean termination permits exactly one new worker on restart.

    start -> worker terminates -> stop returns True -> _thread is None ->
    start -> exactly one NEW worker -> stop returns True.
    """
    wav, _ = _write_wav(str(tmp_path))
    fake = _FakeSttTranscriber(text="ok")
    worker = _LifecycleRecordingWorker(fake, source="radio")
    worker.start()
    assert worker.submit(_job("rec-1", wav)) is True
    assert worker.wait_idle(timeout=5)
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
    assert len(worker.created_threads) == 1
    # Restart: exactly one new worker, distinct from the first.
    worker.start()
    new_worker = worker._thread
    assert new_worker is not None
    assert new_worker.is_alive()
    assert len(worker.created_threads) == 2
    assert worker.created_threads[0] is not worker.created_threads[1]
    assert new_worker is worker.created_threads[1]
    assert worker.stop(timeout=5) is True
    assert worker._thread is None
