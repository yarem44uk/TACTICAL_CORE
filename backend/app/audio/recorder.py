"""WO-039-B — Per-transmission radio recording orchestrator.

:class:`TransmissionRecorder` turns a continuous PCM stream (from the WO-039-A
``RtpReceiver.on_pcm`` boundary) into discrete master WAV recordings plus MP3
derivatives, and links each recording to the existing Canonical Event path.

Pipeline (W-039-B §1/§23):

    PCM -> VAD -> segment state machine -> pre-roll/record/post-roll
        -> WAV master (atomic) -> SHA-256 -> MP3 async -> recording metadata
        -> canonical event raw dict

Design principles honoured here:
  * AUDIO = SOURCE OF TRUTH (W-039-B §3).  The WAV is lossless and is never
    recompressed or overwritten by MP3 generation.  An MP3 failure never
    invalidates the WAV master.
  * The recorder is per-source (W-039-B §23/§27).  Each instance owns its VAD
    state, pre-roll buffer, segment state machine, WAV writer, and statistics.
    No state leaks between multicast sources.
  * Recording failure is observable and never crashes the Core (W-039-B §30).
  * Paths are confined to the configured archive root and are sanitised
    (W-039-B §17/§18/§39).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.audio.audio_config import AudioConfig
from app.audio.mp3_derivative import Mp3Job, Mp3Worker
from app.audio.recording_config import RecordingConfig
from app.audio.segmenter import (
    FinalizeReason,
    SegmentConfig,
    SegmentResult,
    TransmissionSegmenter,
)
from app.audio.vad import EnergyVad, VadConfig
from app.audio.wav_writer import WavWriteError, write_wav_atomic

logger = logging.getLogger(__name__)

# Characters allowed in filesystem components (Windows-safe, no path traversal).
_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_source(name: str) -> str:
    """Sanitise a source name into a safe, Windows-compatible component.

    Replaces any character outside ``[A-Za-z0-9_-]`` with ``_`` and prevents
    path traversal / reserved-name issues.  Falls back to ``"source"`` when the
    result is empty or contains only separators.
    """
    safe = _SAFE_RE.sub("_", str(name))
    safe = safe.strip("._-")
    if not safe or set(safe) <= {"-", "_"}:
        safe = "source"
    return safe


def _safe_join(root: str, *parts: str) -> str:
    """Join path components and verify the result stays inside ``root``.

    Raises:
        ValueError: If the resolved path escapes the archive root.
    """
    root_real = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_real, *parts))
    if target != root_real and not target.startswith(root_real + os.sep):
        raise ValueError("recording path escapes the archive root")
    return target


def build_recording_id(source: str, started_at: datetime, duration_ms: float) -> str:
    """Deterministic, unique, stable ``audio_recording_id``.

    Derived from source + exact start time + duration, so the same capture
    replayed deterministically yields the same id (W-039-B §20).  It does not
    depend solely on the filename and is safe for replay / forensic processing.
    """
    material = f"{source}|{started_at.isoformat()}|{duration_ms:.3f}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_recording_paths(
    root: str,
    source: str,
    started_at: datetime,
    recording_id: str,
) -> tuple[str, str]:
    """Build the (WAV, MP3) paths inside the ``YYYY/MM/DD/SOURCE`` hierarchy.

    Returns ``(wav_path, mp3_path)``.  Both share a deterministic base name:
    ``<TIMESTAMP>_<SOURCE>_<ID>.wav`` (W-039-B §17/§18).
    """
    source_safe = sanitize_source(source)
    date_dir = started_at.strftime("%Y/%m/%d")
    stamp = started_at.strftime("%Y%m%d_%H%M%S_%f")
    base = f"{stamp}_{source_safe}_{recording_id[:12]}"
    rel_dir = os.path.join(date_dir, source_safe)
    wav_path = _safe_join(root, rel_dir, base + ".wav")
    mp3_path = _safe_join(root, rel_dir, base + ".mp3")
    return wav_path, mp3_path


@dataclass(frozen=True)
class RecordingMetadata:
    """Metadata for one finalized transmission (W-039-B §18/§19/§20)."""

    audio_recording_id: str
    wav_path: str
    mp3_path: str | None
    started_at: datetime
    ended_at: datetime
    duration_ms: float
    source: str
    multicast_address: str
    udp_port: int
    codec: str
    sample_rate: int
    channels: int
    sha256: str
    complete: bool
    finalize_reason: str
    format: str = "wav"

    def to_event_raw(self) -> dict[str, Any]:
        """Return an EventFactory-compatible raw dict (W-039-B §21)."""
        started = self.started_at
        return {
            "timestamp": started.isoformat(),
            "occurred_at": started.isoformat(),
            "audio_recording_id": self.audio_recording_id,
            "content_id": self.audio_recording_id,
            "recording": {
                "wav_path": self.wav_path,
                "mp3_path": self.mp3_path,
                "format": self.format,
                "started_at": self.started_at.isoformat(),
                "ended_at": self.ended_at.isoformat(),
                "duration_ms": round(self.duration_ms, 3),
                "duration": round(self.duration_ms / 1000.0, 3),
                "source": self.source,
                "multicast_address": self.multicast_address,
                "udp_port": self.udp_port,
                "codec": self.codec,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "sha256": self.sha256,
                "complete": self.complete,
                "finalize_reason": self.finalize_reason,
            },
        }


class TransmissionRecorder:
    """Per-source recording orchestrator (VAD -> segment -> WAV -> MP3 -> event).

    Args:
        audio_config: The source :class:`AudioConfig` (PCM format + identity).
        recording_config: The :class:`RecordingConfig`.
        on_recording: Callable ``(raw_dict) -> None`` invoked for each finalized
            transmission with an EventFactory-compatible raw dict.  Defaults to
            a no-op.
    """

    def __init__(
        self,
        audio_config: AudioConfig,
        recording_config: RecordingConfig,
        on_recording: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._audio = audio_config
        self._rc = recording_config
        self._on_recording = on_recording or (lambda raw: None)
        self._vad = EnergyVad(
            VadConfig(
                enabled=recording_config.vad_enabled,
                adaptive=recording_config.vad_adaptive,
                threshold_ratio=recording_config.vad_threshold_ratio,
                fixed_threshold=recording_config.vad_fixed_threshold,
            )
        )
        self._segmenter = TransmissionSegmenter(
            SegmentConfig(
                pre_roll_ms=recording_config.pre_roll_ms,
                post_roll_ms=recording_config.post_roll_ms,
                min_speech_ms=recording_config.min_speech_ms,
                silence_timeout_ms=recording_config.silence_timeout_ms,
                max_segment_ms=recording_config.max_segment_ms,
                sample_rate=audio_config.sample_rate,
                channels=audio_config.channels,
            )
        )
        self._archive_root = recording_config.audio_archive_root
        self._mp3_worker: Mp3Worker | None = None
        if recording_config.mp3_enabled:
            self._mp3_worker = Mp3Worker(
                maxsize=recording_config.mp3_queue_max,
                ffmpeg_path=recording_config.mp3_ffmpeg_path,
            )
            self._mp3_worker.start()
        # Per-source statistics (W-039-B §38).
        self._segments_completed = 0
        self._segments_failed = 0
        self._mp3_queued = 0
        self._last_error: str | None = None
        self._active = False

    # -- public interface ---------------------------------------------------

    @property
    def source_name(self) -> str:
        return self._audio.source_name

    @property
    def enabled(self) -> bool:
        return self._rc.enabled and self._rc.vad_enabled

    def on_pcm(self, frame: Any) -> None:
        """Feed one decoded PCM frame (from the WO-039-A ``on_pcm`` hook)."""
        if not self.enabled:
            return
        self._active = True
        try:
            vad_active = self._vad.detect(frame.pcm)
            result = self._segmenter.process(
                frame.pcm, vad_active, now=frame.received_at
            )
            if result is not None:
                self._finalize(result, complete=True)
        except Exception as exc:  # noqa: BLE001 - isolate per-frame failure
            self._segments_failed += 1
            self._last_error = str(exc)
            logger.exception("WO-039-B recorder on_pcm failed")

    def on_shutdown(self, reason: str = "source_shutdown") -> None:
        """Finalize any in-progress transmission and stop the MP3 worker.

        An interrupted transmission is written to disk but marked
        ``complete=False`` so it is never mistaken for a clean recording
        (W-039-B §28).  The Core stays alive.
        """
        result = self._segmenter.force_finalize(
            FinalizeReason.SOURCE_SHUTDOWN
        )
        if result is not None:
            self._finalize(result, complete=False, reason_override=reason)
        if self._mp3_worker is not None:
            self._mp3_worker.stop()
        self._active = False

    def wait_for_mp3(self, timeout: float = 10.0) -> bool:
        """Block until queued MP3 jobs drain.  Returns ``True`` when idle."""
        if self._mp3_worker is None:
            return True
        return self._mp3_worker.wait_idle(timeout=timeout)

    # -- observability (W-039-B §38) ---------------------------------------

    def snapshot(self) -> dict:
        seg = self._segmenter.snapshot()
        current_started = self._segmenter.current_started_at
        current_id = None
        if self._segmenter.is_recording and current_started is not None:
            current_id = build_recording_id(
                self._audio.source_name,
                current_started,
                self._segmenter.current_recording_ms,
            )
        seg.update(
            {
                "source": self._audio.source_name,
                "vad_state": "active" if self._vad.is_speech else "inactive",
                "vad_noise_floor": round(self._vad.noise_floor, 3),
                "vad_threshold": round(self._vad.last_threshold, 3),
                "recording_active": self._segmenter.is_recording,
                "current_recording_id": current_id,
                "recording_started_at": (
                    current_started.isoformat() if current_started else None
                ),
                "segments_completed": self._segments_completed,
                "segments_failed": self._segments_failed,
                "mp3_queued": self._mp3_queued,
                "last_error": self._last_error,
            }
        )
        if self._mp3_worker is not None:
            seg["mp3_worker"] = self._mp3_worker.snapshot()
        return seg

    # -- internals ----------------------------------------------------------

    def _finalize(self, result: SegmentResult, complete: bool, reason_override: str | None = None) -> None:
        """Write the WAV master, hash it, enqueue MP3, and emit the event raw dict."""
        if not result.pcm:
            # Nothing meaningful recorded; do not create an empty file.
            return
        reason = (reason_override or result.reason.value)
        started_at = result.started_at
        duration_ms = result.duration_ms
        recording_id = build_recording_id(
            self._audio.source_name, started_at, duration_ms
        )
        try:
            wav_path, mp3_path = build_recording_paths(
                self._archive_root, self._audio.source_name, started_at, recording_id
            )
            wav = write_wav_atomic(
                result.pcm,
                wav_path,
                self._audio.sample_rate,
                self._audio.channels,
            )
        except (WavWriteError, ValueError) as exc:
            self._segments_failed += 1
            self._last_error = str(exc)
            logger.error("WO-039-B WAV finalize failed: %s", exc)
            return

        self._segments_completed += 1

        # MP3 is a derivative: enqueue only after the WAV is safely finalized.
        actual_mp3_path: str | None = None
        if self._mp3_worker is not None and self._rc.mp3_enabled:
            actual_mp3_path = mp3_path
            job = Mp3Job(
                wav_path=wav.path,
                mp3_path=mp3_path,
                bitrate=self._rc.mp3_bitrate,
                sample_rate=self._audio.sample_rate,
                channels=self._audio.channels,
            )
            if self._mp3_worker.submit(job):
                self._mp3_queued += 1
            else:
                # Queue full: WAV remains authoritative; MP3 is dropped visibly.
                logger.warning(
                    "WO-039-B MP3 queue full; WAV master retained for %s", wav.path
                )

        metadata = RecordingMetadata(
            audio_recording_id=recording_id,
            wav_path=wav.path,
            mp3_path=actual_mp3_path,
            started_at=started_at,
            ended_at=result.ended_at,
            duration_ms=duration_ms,
            source=self._audio.source_name,
            multicast_address=self._audio.multicast_address,
            udp_port=self._audio.multicast_port,
            codec=self._audio.codec or "pcm_alaw",
            sample_rate=wav.sample_rate,
            channels=wav.channels,
            sha256=wav.sha256,
            complete=complete,
            finalize_reason=reason,
        )
        try:
            self._on_recording(metadata.to_event_raw())
        except Exception as exc:  # noqa: BLE001 - never let linkage crash the Core
            self._last_error = f"on_recording failed: {exc}"
            logger.exception("WO-039-B on_recording callback failed")
