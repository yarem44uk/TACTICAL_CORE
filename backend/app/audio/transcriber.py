"""WO-038 — STT seam + deterministic test transcriber.

This module provides the *explicit STT seam* required by WO-038 §8:

    AudioInput -> ITranscriber -> Transcript

:class:`DeterministicTestTranscriber` implements the existing
``app.contracts.audio.ITranscriber`` interface.  Per the WO-038 authorization it
is a *deliberately non-acoustic* test transcriber: it maps a controlled
``content_id`` (carried on the audio segment) to a known transcript via a
configurable phrase table.  It is NOT production speech recognition.

The seam is explicit so a real Vosk/Whisper/faster-whisper engine can replace
``DeterministicTestTranscriber`` later *without touching the Core event
architecture*.  A real engine would implement the same ``ITranscriber``
interface (and the richer :meth:`transcribe_detailed` hook used by the
orchestrator) and derive the transcript from the acoustic content instead of a
content identifier.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.contracts.audio import ITranscriber


@dataclass(frozen=True)
class TranscriptResult:
    """Structured STT output for one audio segment.

    Attributes:
        text: The full transcript text (never truncated).
        occurred_at: The occurrence time of the audio (event time, not ingestion).
        confidence: STT confidence in ``[0.0, 1.0]`` (1.0 for the deterministic
            test transcriber).
        metadata: STT/audio metadata (engine, model, sample_rate, channels,
            pcm length, content_id...).
        language: Language hint.
    """

    text: str
    occurred_at: datetime
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    language: str | None = None


def _default_content_resolver(audio_data: bytes) -> str:
    """Deterministic content id from audio bytes (interface-compliant fallback).

    A real STT engine ignores this and uses the acoustic content; the
    deterministic test transcriber uses a stable hash so ``transcribe(bytes)``
    is reproducible without an external content id.
    """
    if not audio_data:
        return "empty"
    return hashlib.sha256(audio_data).hexdigest()[:16]


class DeterministicTestTranscriber(ITranscriber):
    """Deterministic, configurable test implementation of the STT seam.

    Args:
        phrase_map: Mapping ``content_id -> transcript text``.  When the
            ``content_id`` is absent, the default ``transcribe(bytes)`` path
            resolves a stable hash of the audio bytes and looks it up here.
        default_text: Transcript returned when no phrase matches.
        language: Default language hint.
        confidence: Confidence reported for deterministic transcripts.
        content_resolver: Optional callable ``(audio_data: bytes) -> str`` used
            by the interface ``transcribe(bytes)`` path.  Defaults to a stable
            SHA-256 based resolver.
    """

    def __init__(
        self,
        phrase_map: dict[str, str] | None = None,
        default_text: str = "",
        language: str = "uk",
        confidence: float = 1.0,
        content_resolver: Callable[[bytes], str] | None = None,
    ) -> None:
        self._phrase_map: dict[str, str] = dict(phrase_map or {})
        self._default_text = default_text
        self._language = language
        self._confidence = confidence
        self._content_resolver = content_resolver or _default_content_resolver

    # -- ITranscriber interface --------------------------------------------

    @property
    def model(self) -> str:
        """Transcription model name (explicitly a test model)."""
        return "deterministic-test"

    def is_ready(self) -> bool:
        """The deterministic test transcriber is always ready."""
        return True

    def transcribe(
        self,
        audio_data: bytes,
        language: str | None = None,
    ) -> str:
        """Transcribe audio bytes to text (interface-compliant).

        Resolves a deterministic content id from the audio bytes and looks it up
        in the phrase table.  Returns the transcript, or the configured default.
        """
        content_id = self._content_resolver(audio_data)
        return self._phrase_map.get(content_id, self._default_text)

    # -- richer seam used by the WO-038 orchestrator -------------------------

    def transcribe_detailed(
        self,
        content_id: str,
        audio_data: bytes,
        occurred_at: datetime | None = None,
        language: str | None = None,
        *,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> TranscriptResult:
        """Transcribe a segment using its explicit content id (deterministic).

        This is the seam a real engine replaces: a real STT engine would derive
        the transcript from ``audio_data`` (the acoustic content) and ignore
        ``content_id``.  Here ``content_id`` selects the known transcript.

        Args:
            content_id: The deterministic content identifier from the segment.
            audio_data: The PCM/raw audio bytes (passed through the seam).
            occurred_at: Occurrence time; defaults to now.
            language: Optional language hint.
            sample_rate: Optional sample rate recorded in STT metadata.
            channels: Optional channel count recorded in STT metadata.

        Returns:
            A :class:`TranscriptResult` preserving the full transcript.
        """
        occurred_at = occurred_at or datetime.now(timezone.utc)
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        lang = language or self._language
        text = self._phrase_map.get(content_id, self._default_text)
        metadata: dict[str, Any] = {
            "engine": "deterministic-test",
            "model": self.model,
            "content_id": content_id,
            "audio_bytes_len": len(audio_data),
        }
        if sample_rate is not None:
            metadata["sample_rate"] = sample_rate
        if channels is not None:
            metadata["channels"] = channels
        return TranscriptResult(
            text=text,
            occurred_at=occurred_at,
            confidence=self._confidence,
            metadata=metadata,
            language=lang,
        )
