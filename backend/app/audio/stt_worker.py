"""WO-039-C3 — Bounded WAV acoustic STT worker.

The finalized WAV master is the authoritative audio (``AUDIO = SOURCE OF
TRUTH``); the transcript is *derived* data.  This module runs transcription on a
bounded background queue so STT inference can never block RTP reception, VAD, or
the recorder (the RTP receiver returns immediately after handing the finalized
recording reference to the queue).

Pipeline (WO-039-C3):

    TransmissionRecorder.on_recording -> SttWorker.submit(job)
        -> bounded queue.Queue(maxsize=N)
        -> dedicated daemon thread ("wo039c-stt-worker")
        -> ITranscriber.transcribe(bytes, language)
        -> derived transcript event raw dict -> on_transcript callback

Guarantees honoured here:
  * WAV master is opened read-only; it is never modified or deleted.
  * The queue is bounded; when full the newest job is dropped (the WAV remains
    authoritative) and the drop is observable.
  * The producer path never calls ``transcribe()`` synchronously.
  * Per-job failure is isolated (a failed STT never loses the recording and
    never crashes the Core / receiver).
  * Processing is gated on ``ITranscriber.is_ready()``: a not-ready transcriber
    does not silently fall back, it records an observable failure.
  * No network access, no model download, no engine selection (the engine stays
    ``NOT_YET_JUSTIFIED``; C3 consumes the abstract adapter).
  * Duplicate ``audio_recording_id`` submission is suppressed deterministically.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import io
import logging
import queue
import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.contracts.audio import ITranscriber

logger = logging.getLogger(__name__)


class SttWorkerError(Exception):
    """Raised when a queued STT job cannot be processed safely."""


@dataclass(frozen=True)
class SttJob:
    """One finalized-recording transcription request (a recording reference).

    The job carries the recording reference, never the PCM payload, so no large
    audio buffer is copied through the queue (WO-039-C3 §3/§5).
    """

    audio_recording_id: str
    wav_path: str
    source: str
    language: str | None = None
    started_at: str | None = None
    sha256: str | None = None


def build_transcript_raw(
    job: SttJob,
    text: str,
    *,
    engine: str,
    model: str,
    language: str | None,
    processed_at: datetime,
    processing_ms: float,
    wav_sha256: str | None = None,
) -> dict[str, Any]:
    """Build an EventFactory-compatible raw dict for a derived transcript event.

    The ``content_id`` is ``<audio_recording_id>|transcript`` so the canonical
    event identity (``radio|content|<audio_recording_id>|transcript``) is
    deterministic and DISTINCT from the source recording event
    (``radio|content|<audio_recording_id>``) — it never collides with the
    recording event's ``UNIQUE(event_id)`` (WO-039-C3 §15).

    No database columns are introduced; the transcript lives in ``Event.payload``.
    """
    return {
        "timestamp": processed_at.isoformat(),
        "occurred_at": processed_at.isoformat(),
        "audio_recording_id": job.audio_recording_id,
        # Distinct deterministic identity discriminator (never equals the
        # recording event's content_id, which is the bare audio_recording_id).
        "content_id": f"{job.audio_recording_id}|transcript",
        "correlation_id": job.audio_recording_id,
        "source": job.source,
        "transcript": {
            "text": text,
            "language": language,
            "engine": engine,
            "model": model,
            "audio_recording_id": job.audio_recording_id,
            "processed_at": processed_at.isoformat(),
            "processing_ms": round(processing_ms, 3),
            "wav_sha256": wav_sha256,
        },
    }


def read_wav_readonly(path: str) -> tuple[bytes, dict[str, Any]]:
    """Read a WAV master read-only.

    Returns ``(pcm_bytes, metadata)`` where ``metadata`` carries ``channels``,
    ``sampwidth``, ``sample_rate`` and ``sha256``.  The file is opened in ``rb``
    and never written; the SHA-256 is computed over the exact stored bytes so a
    caller can prove the master is unchanged.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    digest = hashlib.sha256(data).hexdigest()
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, {
        "channels": channels,
        "sampwidth": sampwidth,
        "sample_rate": sample_rate,
        "sha256": digest,
    }


class SttWorker:
    """Bounded async queue that runs STT on a dedicated background thread.

    Mirrors the approved :class:`app.audio.mp3_derivative.Mp3Worker` lifecycle so
    the two derivatives behave consistently.  The worker never writes the WAV and
    never calls the transcriber on the producer (RTP receiver) thread.

    Args:
        transcriber: The :class:`app.contracts.audio.ITranscriber` to run jobs on.
        source: The source name used for the derived transcript event.
        language: Default language hint (a job's ``language`` overrides it).
        engine: Optional engine identifier for the transcript payload.  When
            ``None`` it falls back to ``transcriber.model``.
        maxsize: Maximum queued jobs (backpressure bound).
        on_transcript: Callable ``(raw_dict) -> None`` invoked with the derived
            transcript raw event dict after a successful transcription.
        on_error: Optional callable ``(message) -> None`` for observable runtime
            errors (mirrors the recorder's ``last_error`` pattern).
    """

    def __init__(
        self,
        transcriber: ITranscriber,
        *,
        source: str,
        language: str | None = None,
        engine: str | None = None,
        maxsize: int = 100,
        on_transcript: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._source = source
        self._language = language
        self._engine = engine
        self._queue: queue.Queue[SttJob] = queue.Queue(maxsize=maxsize)
        # Public, reassignable callback: the owning source adapter wires this to
        # route the derived transcript event into its read_events() queue.
        self.on_transcript: Callable[[dict[str, Any]], None] = on_transcript or (
            lambda raw: None
        )
        self._on_error = on_error or (lambda msg: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._processed = 0
        self._failed = 0
        self._dropped = 0
        self._duplicates = 0
        self._inflight = 0
        self._errors: list[str] = []
        self._seen: set[str] = set()
        self._last_processed_recording_id: str | None = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def language(self) -> str | None:
        """The worker's default language hint (used by the source adapter)."""
        return self._language

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="wo039c-stt-worker", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self._thread = None

    # -- submission ---------------------------------------------------------

    def submit(self, job: SttJob) -> bool:
        """Queue a transcription job.  Returns ``False`` when dropped.

        The ``audio_recording_id`` is deduplicated deterministically: a second
        submission of the same recording is suppressed (WO-039-C3 §20).  When the
        queue is full the newest job is dropped; the WAV master is unaffected.
        """
        with self._lock:
            if job.audio_recording_id in self._seen:
                self._duplicates += 1
                logger.warning(
                    "WO-039-C duplicate recording %s suppressed", job.audio_recording_id
                )
                return False
            try:
                self._queue.put_nowait(job)
            except queue.Full:
                self._dropped += 1
                logger.warning(
                    "WO-039-C STT queue full; dropping job for %s", job.wav_path
                )
                return False
            self._seen.add(job.audio_recording_id)
            return True

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Block until the queue drains and no job is in flight.

        Returns ``True`` when idle, ``False`` on timeout.
        """
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                if self._queue.qsize() == 0 and self._inflight == 0:
                    return True
            time.sleep(0.02)
        with self._lock:
            return self._queue.qsize() == 0 and self._inflight == 0

    # -- observability ------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queued": self._queue.qsize(),
                "inflight": self._inflight,
                "processed": self._processed,
                "failed": self._failed,
                "dropped": self._dropped,
                "duplicates": self._duplicates,
                "errors": list(self._errors[-5:]),
                "last_processed_recording_id": self._last_processed_recording_id,
            }

    # -- worker loop --------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            with self._lock:
                self._inflight += 1
            try:
                self._process(job)
                with self._lock:
                    self._processed += 1
                    self._last_processed_recording_id = job.audio_recording_id
            except Exception as exc:  # noqa: BLE001 - isolate a failed job
                with self._lock:
                    self._failed += 1
                    self._errors.append(f"{job.audio_recording_id}: {exc}")
                logger.warning(
                    "WO-039-C STT failed for %s: %s", job.audio_recording_id, exc
                )
                self._on_error(f"{job.audio_recording_id}: {exc}")
            finally:
                with self._lock:
                    self._inflight -= 1
                self._queue.task_done()

    # -- per-job processing -------------------------------------------------

    def _process(self, job: SttJob) -> None:
        """Transcribe one finalized recording and emit a derived transcript event.

        The WAV master is opened read-only and never written.  If the transcriber
        is not ready the job fails clearly (no silent fallback); the WAV is
        preserved.
        """
        if not self._transcriber.is_ready():
            raise SttWorkerError(
                f"transcriber is not ready; refusing to transcribe {job.audio_recording_id}"
            )

        pcm, meta = read_wav_readonly(job.wav_path)
        if meta["channels"] != 1 or meta["sampwidth"] != 2 or meta["sample_rate"] != 8000:
            raise SttWorkerError(
                f"unexpected WAV format for {job.audio_recording_id}: {meta}"
            )

        started = time.monotonic()
        text = self._transcriber.transcribe(pcm, job.language or self._language)
        processing_ms = (time.monotonic() - started) * 1000.0
        processed_at = datetime.now(timezone.utc)
        raw = build_transcript_raw(
            job,
            text,
            engine=self._engine or self._transcriber.model,
            model=self._transcriber.model,
            language=job.language or self._language,
            processed_at=processed_at,
            processing_ms=processing_ms,
            wav_sha256=meta["sha256"],
        )
        self.on_transcript(raw)
