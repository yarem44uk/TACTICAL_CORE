"""WO-039-B — Atomic WAV master writer + SHA-256.

:func:`write_wav_atomic` writes a lossless ``WAV / PCM S16LE`` file using only
the Python standard library ``wave`` module.  It follows the W-039-B §16
integrity pattern:

    recording.wav.tmp -> complete write/close -> os.replace -> recording.wav

so a ``.wav`` file is never presented as complete while it is still being
written.  ``os.replace`` is atomic on POSIX and on Windows, so a completed file
is always a complete file, and an interrupted write leaves only a ``.tmp`` file
that is never mistaken for a valid recording.

SHA-256 is computed over the FINAL WAV bytes (W-039-B §19), not over the PCM
before wrapping.

The WAV is the authoritative master.  It is written losslessly and is never
recompressed or overwritten by MP3 generation.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import os
import wave
from dataclasses import dataclass


class WavWriteError(Exception):
    """Raised when a WAV master cannot be written or finalised."""


@dataclass(frozen=True)
class WavResult:
    """Result of a successful WAV master write.

    Attributes:
        path: The final ``.wav`` path (after atomic rename).
        sha256: SHA-256 of the exact stored WAV bytes.
        sample_rate: Sample rate (Hz).
        channels: Channel count.
        sampwidth: Sample width in bytes.
        sample_count: Number of PCM sample frames written.
        duration_ms: Duration in milliseconds (derived from sample count).
        data_bytes: Number of PCM data bytes.
    """

    path: str
    sha256: str
    sample_rate: int
    channels: int
    sampwidth: int
    sample_count: int
    duration_ms: float
    data_bytes: int


def write_wav_atomic(
    pcm: bytes,
    path: str,
    sample_rate: int,
    channels: int,
    sampwidth: int = 2,
) -> WavResult:
    """Write PCM to a lossless WAV master atomically and hash the final file.

    Args:
        pcm: PCM ``S16LE`` bytes (must be a whole number of sample frames).
        path: Destination ``.wav`` path.  A sibling ``.tmp`` file is written and
            then atomically renamed over ``path``.
        sample_rate: Sample rate in Hz.
        channels: Channel count.
        sampwidth: Sample width in bytes (default 2 = 16-bit).

    Returns:
        A :class:`WavResult`.

    Raises:
        WavWriteError: If the file cannot be created/written/renamed or hashed
            (e.g. disk full, permission denied, invalid PCM length).
    """
    frame_size = sampwidth * channels
    if frame_size <= 0 or sample_rate <= 0:
        raise WavWriteError("invalid WAV parameters (sample_rate/channels/sampwidth)")
    if len(pcm) % frame_size != 0:
        raise WavWriteError(
            f"PCM length {len(pcm)} is not a whole number of sample frames "
            f"(frame_size={frame_size})"
        )

    directory = os.path.dirname(path)
    tmp_path = path + ".tmp"
    try:
        if directory:
            os.makedirs(directory, exist_ok=True)
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        # Atomic rename: the .wav path only ever appears as a complete file.
        os.replace(tmp_path, path)
    except (OSError, wave.Error) as exc:
        # Best-effort cleanup of the partial temp file.
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise WavWriteError(f"WAV write failed: {exc}") from exc

    try:
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    except OSError as exc:
        raise WavWriteError(f"WAV hash failed: {exc}") from exc

    sample_count = len(pcm) // frame_size
    return WavResult(
        path=path,
        sha256=digest,
        sample_rate=sample_rate,
        channels=channels,
        sampwidth=sampwidth,
        sample_count=sample_count,
        duration_ms=sample_count / sample_rate * 1000.0,
        data_bytes=len(pcm),
    )
