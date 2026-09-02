"""WO-038 — Audio decode (reuse existing ffmpeg).

:class:`AudioDecoder` decodes an arbitrary input audio stream into raw PCM
(S16LE, mono, target sample rate) suitable for STT input.  It shells out to the
already-installed ``ffmpeg`` binary — the WO-038 directive explicitly says to
reuse ffmpeg when present rather than introduce a second audio stack.

Every decode is a short-lived subprocess (``ffmpeg`` reads the audio bytes from
stdin and writes PCM to stdout), so a malformed/unsupported input is isolated to
one call and can never crash the Core.  A decode failure returns ``b""`` rather
than raising, so the pipeline degrades gracefully.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class AudioDecoder:
    """Decodes audio bytes to PCM using the system ffmpeg.

    Args:
        sample_rate: Target PCM sample rate (Hz). Default 16000.
        channels: Target PCM channel count. Default 1 (mono).
        ffmpeg_path: Path to the ffmpeg binary. Defaults to ``ffmpeg`` on PATH.
        timeout: Subprocess timeout in seconds (guards against a hung decoder).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        ffmpeg_path: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._ffmpeg_path = ffmpeg_path or "ffmpeg"
        self._timeout = timeout
        self._available: bool | None = None

    @property
    def available(self) -> bool:
        """Whether the ffmpeg binary is usable on this host."""
        if self._available is None:
            self._available = shutil.which(self._ffmpeg_path) is not None
        return self._available

    def decode(self, audio_bytes: bytes) -> bytes:
        """Decode raw audio bytes to PCM (S16LE, mono, target sample rate).

        Args:
            audio_bytes: Input audio stream (any format ffmpeg understands,
                e.g. WAV, MP3, raw PCM).

        Returns:
            PCM bytes.  Returns ``b""`` on decode failure (never raises).

        Raises:
            RuntimeError: If ffmpeg is unavailable.  The caller decides whether
                this is fatal; the pipeline treats it as a degraded source.
        """
        if not audio_bytes:
            return b""
        if not self.available:
            raise RuntimeError("ffmpeg is not available for audio decode")
        cmd = [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le",
            "-ac", str(self._channels),
            "-ar", str(self._sample_rate),
            "pipe:1",
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=audio_bytes,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("WO-038 audio decode failed (process error): %s", exc)
            return b""
        if proc.returncode != 0:
            logger.warning(
                "WO-038 audio decode failed (rc=%d): %s",
                proc.returncode,
                proc.stderr[-400:],
            )
            return b""
        return proc.stdout

    def decode_segment(self, audio_bytes: bytes, codec: str | None = None) -> bytes:
        """Decode an audio segment with an explicit codec hint.

        When ``codec`` is provided (e.g. ``wav``, ``pcm_s16le``, ``mp3``), the
        input demuxer is forced, which makes decode deterministic for known
        formats.  Falls back to auto-detection when ``codec`` is ``None``.
        """
        if not audio_bytes:
            return b""
        if not self.available:
            raise RuntimeError("ffmpeg is not available for audio decode")
        cmd = [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
        ]
        if codec:
            cmd += ["-f", codec]
        cmd += [
            "-i", "pipe:0",
            "-f", "s16le",
            "-ac", str(self._channels),
            "-ar", str(self._sample_rate),
            "pipe:1",
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=audio_bytes,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("WO-038 audio decode failed (process error): %s", exc)
            return b""
        if proc.returncode != 0:
            logger.warning(
                "WO-038 audio decode failed (rc=%d): %s",
                proc.returncode,
                proc.stderr[-400:],
            )
            return b""
        return proc.stdout
