"""WO-039-B — Per-source radio transmission recording configuration.

:class:`RecordingConfig` holds the VAD / segmentation / WAV / MP3 settings for a
single multicast radio source (W-039-B §8).  It is built from the opaque
``SourceDefinition.config`` dict (matching the existing ``AudioConfig``
convention), so no operational path or address is hardcoded.  Unknown keys are
ignored; missing keys fall back to the documented defaults.

The values below are configurable defaults, not immutable protocol facts
(W-039-B §9).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class RecordingConfig:
    """Configuration for one source's recording / VAD / segmentation pipeline."""

    # Master switch: when False the recorder is not engaged for the source.
    enabled: bool = False
    vad_enabled: bool = True
    # VAD tuning.
    vad_adaptive: bool = True
    vad_threshold_ratio: float = 2.5
    vad_fixed_threshold: float | None = None
    vad_noise_alpha: float = 0.05
    # Segmentation (configurable defaults, W-039-B §9).
    pre_roll_ms: int = 400
    post_roll_ms: int = 800
    min_speech_ms: int = 250
    silence_timeout_ms: int = 1000
    max_segment_ms: int = 60000
    # Storage.
    audio_archive_root: str = "audio"
    # MP3 derivative.
    mp3_enabled: bool = True
    mp3_bitrate: str = "64k"
    mp3_queue_max: int = 100
    mp3_ffmpeg_path: str = "ffmpeg"

    def with_options(self, **kwargs: Any) -> RecordingConfig:
        """Return a copy with selected fields overridden (immutable config)."""
        return replace(self, **kwargs)

    @classmethod
    def from_source_definition(cls, config: dict[str, Any] | None) -> RecordingConfig:
        """Build a ``RecordingConfig`` from an opaque source config dict.

        ``vad_enabled`` is the master switch: when the source config sets it,
        the recording pipeline is engaged for that source.
        """
        if config is None:
            config = {}

        def _opt_float(key: str) -> float | None:
            value = config.get(key)
            if value is None or value == "":
                return None
            return float(value)

        vad_enabled = bool(config.get("vad_enabled", False))
        return cls(
            enabled=vad_enabled,
            vad_enabled=vad_enabled,
            vad_adaptive=bool(config.get("vad_adaptive", True)),
            vad_threshold_ratio=float(config.get("vad_threshold_ratio", 2.5)),
            vad_fixed_threshold=_opt_float("vad_fixed_threshold"),
            vad_noise_alpha=float(config.get("vad_noise_alpha", 0.05)),
            pre_roll_ms=int(config.get("pre_roll_ms", 400)),
            post_roll_ms=int(config.get("post_roll_ms", 800)),
            min_speech_ms=int(config.get("min_speech_ms", 250)),
            silence_timeout_ms=int(config.get("silence_timeout_ms", 1000)),
            max_segment_ms=int(config.get("max_segment_ms", 60000)),
            audio_archive_root=str(config.get("audio_archive_root", "audio")),
            mp3_enabled=bool(config.get("mp3_enabled", True)),
            mp3_bitrate=str(config.get("mp3_bitrate", "64k")),
            mp3_queue_max=int(config.get("mp3_queue_max", 100)),
            mp3_ffmpeg_path=str(config.get("mp3_ffmpeg_path", "ffmpeg")),
        )
