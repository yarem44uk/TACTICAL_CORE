"""WO-063 — STT processing worker against an accepted durable recording.

The accepted durable radio recording is the authoritative input
(``AUDIO = SOURCE OF TRUTH``); the transcript is *derived* evidence.  This
worker consumes a recording by its **canonical identity** (``audio_recording_id``)
and resolves the actual media exclusively through the authoritative
recording/evidence mechanism (``RecordingAccess``) — it NEVER trusts an arbitrary
filesystem path supplied by a caller.

Flow (WO-063):

    audio_recording_id
        |
        v
    resolve accepted recording (RecordingAccess)
        |       identity lookup + path confinement + existence
        v
    verify recording integrity (mandatory stored SHA-256, WO-062-C1)
        |
        v
    obtain authoritative media (read-only)
        |
        v
    STT (ITranscriber seam)
        |
        v
    deterministic transcript evidence
        |
        v
    enrichment seam (on_transcript) -> canonical event path -> observation

Guarantees honoured here:
  * identity-only: the caller supplies the canonical recording identity, never a
    path.  The verified media path comes from the trusted resolver.
  * WO-062-C1 mandatory integrity gate: NO verified stored SHA-256 -> NO media
    bytes consumed.  A missing / null / empty / malformed / wrong stored hash
    fails closed before any byte is read.
  * read-only source: the authoritative WAV is opened in ``rb`` and never
    modified, truncated, transcoded, renamed or deleted.
  * engine-neutral: the worker consumes the existing ``ITranscriber`` seam; it
    selects no engine, downloads no model, and makes no network call.
  * deterministic: the derived transcript raw dict carries the canonical
    ``content_id = <audio_recording_id>|transcript`` (distinct from the recording
    event), so the same recording + the same STT contract/version yields the same
    logical transcript result and event identity.
  * idempotent: re-processing a recording that has already been transcribed under
    the same (engine, model) contract returns the cached result and does not run
    STT again.
  * safe, typed failures: every failure is an explicit, non-leaking
    :class:`RecordingSttError` subclass.  No filesystem path, archive root, OS
    error, internal exception, or credential is exposed through the result.

Callsign / speaker / confidence-meaning / frequency / location / operational
classification enrichment is deliberately OUT OF SCOPE here (it belongs to
WO-064).  The transcript is pure derived evidence.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.audio.stt_worker import (
    SttJob,
    build_transcript_raw,
    read_wav_readonly,
)
from app.contracts.audio import ITranscriber
from app.operator.recording_access import (
    RecordingArtifact,
    RecordingIntegrityError as AccessIntegrityError,
    RecordingNotFoundError as AccessNotFoundError,
    RecordingPathEscapeError as AccessPathEscapeError,
    RecordingUnavailableError as AccessUnavailableError,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Safe, typed failure hierarchy (no path / internal detail is leaked)
# --------------------------------------------------------------------------- #


class RecordingSttError(Exception):
    """Base error for the identity-based STT worker.

    Subclasses carry a safe, human-readable message that never exposes a
    filesystem path, archive root, OS error, credential, or stack trace.
    """


class RecordingIdentityInvalidError(RecordingSttError):
    """The canonical recording identity is invalid (empty / non-string)."""


class RecordingMissingError(RecordingSttError):
    """The canonical recording identity does not resolve to a recording."""


class RecordingIntegrityViolationError(RecordingSttError):
    """The recording fails the mandatory SHA-256 integrity gate (WO-062-C1).

    Covers a missing, null, empty, malformed, or wrong stored digest, and a
    mismatch between the stored digest and the actual media bytes.
    """


class RecordingMediaUnavailableError(RecordingSttError):
    """The recording metadata exists but its media artifact is unavailable.

    Also covers a path that escapes the archive root (confinement violation) —
    reported generically so the underlying path is never revealed.
    """


class RecordingMediaUnreadableError(RecordingSttError):
    """The media artifact exists but cannot be read / is not a usable WAV."""


class SttExecutionFailedError(RecordingSttError):
    """STT execution failed (engine not ready, inference error, no engine)."""


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RecordingTranscriptResult:
    """Deterministic transcript evidence derived from an accepted recording.

    Attributes:
        audio_recording_id: the canonical recording identity consumed.
        content_id: deterministic derived-evidence identity
            (``<audio_recording_id>|transcript``), distinct from the recording.
        text: the transcript text (``""`` for a valid recording with no speech —
            a successful STT execution, not a failure).
        engine: STT engine identifier.
        model: STT model identifier.
        language: language hint used.
        wav_sha256: the verified SHA-256 of the authoritative media.
        processed_at: UTC time the transcript was produced.
        processing_ms: STT processing time in milliseconds.
        raw: the EventFactory-compatible raw dict (transcript evidence) that flows
            through the enrichment seam -> canonical event path -> observation.
    """

    audio_recording_id: str
    content_id: str
    text: str
    engine: str
    model: str
    language: str | None
    wav_sha256: str
    processed_at: datetime
    processing_ms: float
    raw: dict[str, Any]


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #


class RecordingSttWorker:
    """Resolve an accepted recording by identity and transcribe it (read-only).

    The worker is a *downstream consumer* of the accepted recording.  It never
    touches the recording pipeline, never moves STT into the live capture path,
    and never rewrites the canonical event model.  It resolves the recording
    exclusively through the injected ``resolver`` (the authoritative
    ``RecordingAccess`` mechanism), verifies integrity, reads the media
    read-only, runs STT through the existing ``ITranscriber`` seam, and emits a
    deterministic transcript-evidence raw dict via ``on_transcript``.

    Args:
        transcriber: the existing :class:`app.contracts.audio.ITranscriber` seam.
            May be ``None`` (fail-closed): the worker is ``UNAVAILABLE`` and
            ``transcribe`` rejects every request — it never fabricates a
            transcript and never falls back to ``DeterministicTestTranscriber``.
        resolver: callable ``(audio_recording_id) -> RecordingArtifact`` that
            resolves the canonical identity to a confined, integrity-verified
            artifact.  This is the authoritative recording/evidence mechanism
            (e.g. ``RecordingAccess.resolve``).  The worker never accepts a path.
        source: the source name used for the derived transcript event.
        language: default language hint (a per-call value overrides it).
        engine: optional engine identifier for the transcript payload.  When
            ``None`` it falls back to ``transcriber.model``.
        on_transcript: callable ``(raw_dict) -> None`` invoked with the derived
            transcript-evidence raw dict after a successful transcription (the
            enrichment seam).
        on_error: optional callable ``(message) -> None`` for observable runtime
            errors.
    """

    def __init__(
        self,
        transcriber: ITranscriber | None,
        resolver: Callable[[str], RecordingArtifact],
        *,
        source: str,
        language: str | None = None,
        engine: str | None = None,
        on_transcript: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._resolver = resolver
        self._source = source
        self._language = language
        self._engine = engine
        self.on_transcript: Callable[[dict[str, Any]], None] = on_transcript or (
            lambda raw: None
        )
        self._on_error = on_error or (lambda msg: None)
        # Idempotency cache keyed by (recording_id, engine, model).  Same
        # recording + same STT contract/version -> same logical result, and STT
        # is not re-run for an already-processed contract.
        self._results: dict[tuple[str, str, str], RecordingTranscriptResult] = {}
        self._failures: int = 0

    # -- production STT state ------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether an authorized acoustic engine is registered."""
        return self._transcriber is not None

    @property
    def state(self) -> str:
        """Explicit production STT state (``AVAILABLE`` / ``UNAVAILABLE``)."""
        return "AVAILABLE" if self.available else "UNAVAILABLE"

    @property
    def failures(self) -> int:
        """Number of failed transcription attempts (observable)."""
        return self._failures

    # -- main seam -----------------------------------------------------------

    def transcribe(self, audio_recording_id: str) -> RecordingTranscriptResult:
        """Transcribe one accepted recording by its canonical identity.

        Returns a deterministic :class:`RecordingTranscriptResult`.  A valid
        recording with no speech yields a successful result with ``text == ""``
        (it is NOT a failure).

        Raises:
            RecordingIdentityInvalidError: the identity is empty / non-string.
            RecordingMissingError: the identity does not resolve to a recording.
            RecordingIntegrityViolationError: mandatory SHA-256 gate failed.
            RecordingMediaUnavailableError: the media artifact is unavailable.
            RecordingMediaUnreadableError: the media cannot be read.
            SttExecutionFailedError: STT failed (no engine / not ready / error).
        """
        self._validate_identity(audio_recording_id)

        artifact = self._resolve(audio_recording_id)
        return self._transcribe_artifact(audio_recording_id, artifact)

    def has_result(self, audio_recording_id: str) -> bool:
        """Whether a transcript already exists for the recording under the
        current STT contract (used by callers to avoid re-processing)."""
        return self._cache_key(audio_recording_id) in self._results

    # -- internals -----------------------------------------------------------

    def _cache_key(self, audio_recording_id: str) -> tuple[str, str, str]:
        engine = self._engine or (self._transcriber.model if self._transcriber else "")
        model = self._transcriber.model if self._transcriber else ""
        return (audio_recording_id, engine, model)

    @staticmethod
    def _validate_identity(audio_recording_id: str) -> None:
        if not isinstance(audio_recording_id, str) or not audio_recording_id.strip():
            raise RecordingIdentityInvalidError("invalid recording identity")

    def _resolve(self, audio_recording_id: str) -> RecordingArtifact:
        """Resolve the recording via the authoritative mechanism.

        Translates the resolver's safe domain errors into the worker's typed
        error hierarchy.  No filesystem path or internal detail is propagated.
        """
        try:
            return self._resolver(audio_recording_id)
        except AccessNotFoundError as exc:
            raise RecordingMissingError("recording not found") from exc
        except AccessIntegrityError as exc:
            raise RecordingIntegrityViolationError(
                "recording integrity verification failed"
            ) from exc
        except (AccessUnavailableError, AccessPathEscapeError) as exc:
            raise RecordingMediaUnavailableError(
                "recording media unavailable"
            ) from exc
        except RecordingSttError:
            raise
        except Exception as exc:  # noqa: BLE001 - safe boundary
            logger.warning(
                "WO-063 resolver failure for %s: %s",
                audio_recording_id,
                exc,
            )
            raise RecordingMediaUnavailableError(
                "recording media unavailable"
            ) from exc

    def _transcribe_artifact(
        self,
        audio_recording_id: str,
        artifact: RecordingArtifact,
    ) -> RecordingTranscriptResult:
        # Idempotency: if this recording was already transcribed under the same
        # STT contract, return the cached result without re-running STT.
        key = self._cache_key(audio_recording_id)
        cached = self._results.get(key)
        if cached is not None:
            return cached

        if self._transcriber is None:
            self._failures += 1
            raise SttExecutionFailedError(
                "STT engine unavailable (fail closed)"
            )

        # Read the media read-only and re-verify the SHA-256 at read time
        # (WO-062-C1: NO verified stored SHA-256 -> NO media bytes consumed).
        pcm, meta = self._read_media(audio_recording_id, artifact)

        if not self._transcriber.is_ready():
            self._failures += 1
            raise SttExecutionFailedError("transcriber is not ready")

        started = _now()
        try:
            text = self._transcriber.transcribe(pcm, self._language)
        except Exception as exc:  # noqa: BLE001 - STT failure is isolated
            self._failures += 1
            logger.warning(
                "WO-063 STT failure for %s: %s", audio_recording_id, exc
            )
            raise SttExecutionFailedError("STT execution failed") from exc

        processing_ms = (_now() - started) * 1000.0
        processed_at = datetime.now(timezone.utc)
        engine = self._engine or self._transcriber.model
        model = self._transcriber.model

        job = SttJob(
            audio_recording_id=audio_recording_id,
            wav_path=artifact.path,
            source=self._source,
            language=self._language,
            sha256=meta["sha256"],
        )
        # WO-063 scope: pure derived transcript evidence.  Callsign / speaker /
        # confidence-meaning enrichment is deferred to WO-064, so the detector is
        # deliberately NOT applied here.
        raw = build_transcript_raw(
            job,
            text,
            engine=engine,
            model=model,
            language=self._language,
            processed_at=processed_at,
            processing_ms=processing_ms,
            wav_sha256=meta["sha256"],
        )
        result = RecordingTranscriptResult(
            audio_recording_id=audio_recording_id,
            content_id=raw["content_id"],
            text=text,
            engine=engine,
            model=model,
            language=self._language,
            wav_sha256=meta["sha256"],
            processed_at=processed_at,
            processing_ms=processing_ms,
            raw=raw,
        )
        self._results[key] = result
        # Enrichment seam: emit the transcript evidence into the canonical event
        # path (caller wires this to EventFactory -> EventPipeline -> observation).
        self.on_transcript(raw)
        return result

    @staticmethod
    def _read_media(
        audio_recording_id: str,
        artifact: RecordingArtifact,
    ) -> tuple[bytes, dict[str, Any]]:
        """Read the verified media read-only and re-verify its SHA-256.

        The artifact was already confined and verified by ``RecordingAccess``;
        this re-hashes the exact bytes at read time so a TOCTOU change between
        resolution and consumption is caught before any byte is transcribed.

        Raises:
            RecordingMediaUnreadableError: the file cannot be read or is not a
                usable WAV.
            RecordingIntegrityViolationError: the read bytes do not match the
                verified artifact SHA-256.
        """
        try:
            pcm, meta = read_wav_readonly(artifact.path)
        except (OSError, ValueError, wave.Error, EOFError) as exc:
            logger.warning("WO-063 media unreadable for %s: %s", audio_recording_id, exc)
            raise RecordingMediaUnreadableError(
                "recording media unreadable"
            ) from exc
        actual = meta["sha256"]
        # Length-safe comparison; any mismatch (including a corrupt/truncated
        # artifact) fails closed before any byte is transcribed.
        if not _safe_hex_equal(actual, artifact.sha256):
            logger.warning(
                "WO-063 integrity mismatch at read time for %s", audio_recording_id
            )
            raise RecordingIntegrityViolationError(
                "recording integrity verification failed"
            )
        return pcm, meta


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _now() -> float:
    import time

    return time.monotonic()


def _safe_hex_equal(expected: str, actual: str) -> bool:
    """Length-safe hex digest comparison (no partial match ever reported)."""
    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    e = expected.strip().lower()
    a = actual.strip().lower()
    if len(e) != len(a):
        return False
    return e == a
