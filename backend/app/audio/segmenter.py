"""WO-039-B — Radio transmission segmentation state machine.

:class:`TransmissionSegmenter` turns a continuous PCM stream into discrete radio
transmissions.  It implements the explicit state machine from W-039-B §7:

    IDLE -> PREBUFFER -> RECORDING -> TAIL/POST-ROLL -> FINALIZE -> IDLE

and correctly handles: silence, speech start, speech continue, a short pause
(speech resumes before the timeout → one transmission), speech end, maximum
duration, source interruption, and forced finalization.

The segmenter is pure Python and thread-confined: one instance per source
(W-039-B §23).  It does NOT touch the filesystem or the event model — it only
accumulates PCM and reports the completed segment boundaries to the caller
(``TransmissionRecorder``), which is responsible for the WAV / MP3 / event
linkage.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class SegmentState(enum.Enum):
    """Lifecycle state of the segmentation state machine."""

    IDLE = "idle"
    RECORDING = "recording"
    TAIL = "tail"


class FinalizeReason(enum.Enum):
    """Why a segment was finalized."""

    SILENCE_TIMEOUT = "silence_timeout"
    MAX_SEGMENT = "max_segment"
    SOURCE_SHUTDOWN = "source_shutdown"
    FORCE = "force"


@dataclass(frozen=True)
class SegmentConfig:
    """Tunable segmentation parameters (W-039-B §9).

    These are configurable defaults, not immutable protocol facts.
    """

    pre_roll_ms: int = 400
    post_roll_ms: int = 800
    min_speech_ms: int = 250
    silence_timeout_ms: int = 1000
    max_segment_ms: int = 60000
    sample_rate: int = 8000
    channels: int = 1
    sampwidth: int = 2

    @property
    def bytes_per_sample(self) -> int:
        return self.sampwidth * self.channels

    @property
    def prebuffer_bytes(self) -> int:
        """Maximum prebuffer size in bytes (bounded pre-roll)."""
        samples = int(self.pre_roll_ms / 1000.0 * self.sample_rate)
        return samples * self.bytes_per_sample


@dataclass(frozen=True)
class SegmentResult:
    """A finalized transmission ready to be written as a master WAV.

    Attributes:
        pcm: The complete PCM ``S16LE`` bytes of the transmission (pre-roll +
            speech + post-roll).
        started_at: UTC time the transmission began (pre-roll included).
        ended_at: UTC time the transmission was finalized.
        duration_ms: Total recorded duration in milliseconds.
        reason: The :class:`FinalizeReason`.
        pre_roll_ms: Configured pre-roll (informational).
        speech_ms: Approximate duration classified as speech.
    """

    pcm: bytes
    started_at: datetime
    ended_at: datetime
    duration_ms: float
    reason: FinalizeReason
    pre_roll_ms: float
    speech_ms: float


class TransmissionSegmenter:
    """Segments a continuous PCM stream into individual transmissions.

    Args:
        config: The :class:`SegmentConfig`.
    """

    def __init__(self, config: SegmentConfig | None = None) -> None:
        self._config = config or SegmentConfig()
        self._state = SegmentState.IDLE
        self._prebuffer: deque[bytes] = deque()
        self._prebuffer_ms = 0.0
        self._pending = bytearray()
        self._pending_ms = 0.0
        self._recording = bytearray()
        self._recording_ms = 0.0
        self._silence_ms = 0.0
        self._recording_started_at: datetime | None = None
        self._last_speech_at: datetime | None = None

    # -- accessors ----------------------------------------------------------

    @property
    def state(self) -> SegmentState:
        return self._state

    @property
    def current_started_at(self) -> datetime | None:
        """UTC start time of the in-progress recording (or ``None``)."""
        return self._recording_started_at

    @property
    def current_recording_ms(self) -> float:
        """Elapsed duration (ms) of the in-progress recording."""
        return self._recording_ms

    @property
    def is_recording(self) -> bool:
        return self._state in (SegmentState.RECORDING, SegmentState.TAIL)

    def snapshot(self) -> dict:
        """Per-source observability snapshot (W-039-B §38)."""
        return {
            "state": self._state.value,
            "recording_active": self.is_recording,
            "prebuffer_ms": round(self._prebuffer_ms, 3),
            "pending_ms": round(self._pending_ms, 3),
            "recording_ms": round(self._recording_ms, 3),
            "silence_ms": round(self._silence_ms, 3),
        }

    # -- frame processing ---------------------------------------------------

    def process(
        self,
        pcm: bytes,
        vad_active: bool,
        now: datetime | None = None,
    ) -> SegmentResult | None:
        """Process one PCM frame.

        Args:
            pcm: PCM ``S16LE`` bytes for the frame.
            vad_active: Whether the VAD classifies this frame as speech.
            now: Optional wall-clock timestamp for the frame (defaults to now).

        Returns:
            A :class:`SegmentResult` when a transmission is finalized by this
            frame, otherwise ``None``.
        """
        now = now or datetime.now(timezone.utc)
        frame_ms = self._frame_ms(len(pcm))

        if self._state == SegmentState.IDLE:
            if vad_active:
                # The pre-roll buffer already holds the background audio that
                # preceded this speech frame (non-speech frames only).  Do NOT
                # push the speech frame into the pre-roll buffer.
                self._pending.extend(pcm)
                self._pending_ms += frame_ms
                if self._pending_ms >= self._config.min_speech_ms:
                    self._start_recording(now)
            else:
                self._push_prebuffer(pcm, frame_ms)
                self._pending = bytearray()
                self._pending_ms = 0.0
            return None

        if self._state == SegmentState.RECORDING:
            self._recording.extend(pcm)
            self._recording_ms += frame_ms
            if vad_active:
                self._silence_ms = 0.0
                self._last_speech_at = now
            else:
                # Speech ended -> enter post-roll (TAIL).
                self._state = SegmentState.TAIL
                self._silence_ms = frame_ms
            if self._recording_ms >= self._config.max_segment_ms:
                return self._finalize(FinalizeReason.MAX_SEGMENT, now)
            return None

        # TAIL / post-roll
        self._recording.extend(pcm)
        self._recording_ms += frame_ms
        if vad_active:
            # Speech resumed before finalization -> continue same transmission.
            self._state = SegmentState.RECORDING
            self._silence_ms = 0.0
            self._last_speech_at = now
            if self._recording_ms >= self._config.max_segment_ms:
                return self._finalize(FinalizeReason.MAX_SEGMENT, now)
            return None
        self._silence_ms += frame_ms
        if self._silence_ms >= self._finalize_silence_ms():
            return self._finalize(FinalizeReason.SILENCE_TIMEOUT, now)
        if self._recording_ms >= self._config.max_segment_ms:
            return self._finalize(FinalizeReason.MAX_SEGMENT, now)
        return None

    def force_finalize(
        self,
        reason: FinalizeReason = FinalizeReason.SOURCE_SHUTDOWN,
        now: datetime | None = None,
    ) -> SegmentResult | None:
        """Finalize an in-progress transmission (e.g. on source interruption).

        Returns the finalized segment when a transmission was active, otherwise
        ``None``.  The caller decides whether the segment is marked complete.
        """
        now = now or datetime.now(timezone.utc)
        if self._state in (SegmentState.RECORDING, SegmentState.TAIL):
            return self._finalize(reason, now)
        return None

    # -- internals ----------------------------------------------------------

    def _frame_ms(self, pcm_len: int) -> float:
        if pcm_len <= 0:
            return 0.0
        samples = pcm_len // self._config.bytes_per_sample
        return samples / self._config.sample_rate * 1000.0

    def _finalize_silence_ms(self) -> float:
        """Silence required before finalization.

        Guarantees at least ``post_roll_ms`` of trailing audio is preserved even
        when ``silence_timeout_ms`` is configured below it, while honoring the
        timeout when it is the larger value.
        """
        return float(max(self._config.post_roll_ms, self._config.silence_timeout_ms))

    def _start_recording(self, now: datetime) -> None:
        """Transition IDLE -> RECORDING, seeding with pre-roll + confirmed speech."""
        start_pcm = b"".join(self._prebuffer) + bytes(self._pending)
        pre_ms = self._prebuffer_ms
        pend_ms = self._pending_ms
        self._state = SegmentState.RECORDING
        self._recording = bytearray(start_pcm)
        self._recording_ms = pre_ms + pend_ms
        self._recording_started_at = now - timedelta(milliseconds=pre_ms + pend_ms)
        self._last_speech_at = now
        self._silence_ms = 0.0
        # Reset the pre-buffers; the recording owns the pre-roll now.
        self._pending = bytearray()
        self._pending_ms = 0.0
        self._prebuffer.clear()
        self._prebuffer_ms = 0.0

    def _push_prebuffer(self, pcm: bytes, frame_ms: float) -> None:
        """Append a frame to the bounded pre-roll buffer (IDLE only)."""
        self._prebuffer.append(pcm)
        self._prebuffer_ms += frame_ms
        max_bytes = self._config.prebuffer_bytes
        total = sum(len(b) for b in self._prebuffer)
        # Trim from the oldest until the buffer fits the pre-roll budget.
        while total > max_bytes and len(self._prebuffer) > 1:
            old = self._prebuffer.popleft()
            total -= len(old)
            self._prebuffer_ms -= self._frame_ms(len(old))

    def _finalize(self, reason: FinalizeReason, now: datetime) -> SegmentResult:
        result = SegmentResult(
            pcm=bytes(self._recording),
            started_at=self._recording_started_at or now,
            ended_at=now,
            duration_ms=self._recording_ms,
            reason=reason,
            pre_roll_ms=float(self._config.pre_roll_ms),
            speech_ms=max(0.0, self._recording_ms - self._silence_ms),
        )
        self._reset()
        return result

    def _reset(self) -> None:
        self._state = SegmentState.IDLE
        self._recording = bytearray()
        self._recording_ms = 0.0
        self._silence_ms = 0.0
        self._recording_started_at = None
        self._last_speech_at = None
        self._pending = bytearray()
        self._pending_ms = 0.0
        self._prebuffer.clear()
        self._prebuffer_ms = 0.0
