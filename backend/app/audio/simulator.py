"""WO-038 — Controlled multicast audio test simulator.

:class:`MulticastAudioSimulator` produces deterministic, known-content multicast
audio frames and sends them to the configured multicast group.  It is the
controlled test source required by WO-038 §15.

The audio payload is a real WAV stream (generated via ffmpeg) that the receiver
decodes to PCM; the deterministic transcript mapping is driven by the
``content_id`` carried in the frame header.  This keeps the simulator
deterministic and lets the acceptance test verify the complete chain end to end.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import logging
import socket
import subprocess
from datetime import datetime, timezone

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import encode_frame

logger = logging.getLogger(__name__)


class MulticastAudioSimulator:
    """Sends controlled multicast audio frames to a multicast group.

    Args:
        config: The :class:`AudioConfig` (multicast address/port/interface).
        ffmpeg_path: Path to ffmpeg (used to generate the WAV payload).
    """

    def __init__(
        self,
        config: AudioConfig,
        ffmpeg_path: str | None = None,
    ) -> None:
        self._config = config
        self._ffmpeg_path = ffmpeg_path or "ffmpeg"
        self._socket: socket.socket | None = None

    def _get_socket(self) -> socket.socket:
        """Create a UDP socket configured for multicast loopback on the host."""
        if self._socket is None:
            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            # Loop back so same-host simulators and receivers see the packet.
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            try:
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(self._config.join_interface),
                )
            except OSError:
                # Non-loopback interface may not support setting the multicast
                # interface explicitly; leave the OS default.
                pass
            self._socket = sock
        return self._socket

    def close(self) -> None:
        """Close the simulator's socket."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:  # pragma: no cover - defensive
                pass
            self._socket = None

    def generate_audio(self, content_id: str, duration: float = 0.5) -> bytes:
        """Generate a deterministic WAV audio payload for a content id.

        The tone frequency is derived from a stable hash of ``content_id`` so
        the same content always produces the same audio bytes (deterministic).
        """
        freq = 300 + (int(hashlib.sha256(content_id.encode("utf-8")).hexdigest()[:8], 16) % 500)
        cmd = [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={duration}",
            "-ar", str(self._config.sample_rate),
            "-ac", str(self._config.channels),
            "-f", "wav",
            "pipe:1",
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"simulator failed to generate audio: {proc.stderr[-300:]}"
            )
        return proc.stdout

    def send(
        self,
        content_id: str,
        *,
        occurred_at: datetime | None = None,
        audio_bytes: bytes | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Send one controlled multicast audio frame.

        Args:
            content_id: Deterministic content identifier for the segment.
            occurred_at: Optional explicit occurrence time (ISO-8601).  When
                omitted the receiver stamps receive time.
            audio_bytes: Optional audio payload.  When omitted a deterministic
                WAV is generated for ``content_id``.
            metadata: Optional extra per-segment metadata.

        Returns:
            Number of bytes sent.
        """
        if occurred_at is not None and occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        if audio_bytes is None:
            audio_bytes = self.generate_audio(content_id)
        frame = encode_frame(
            audio_bytes,
            content_id=content_id,
            occurred_at=occurred_at,
            metadata=metadata,
        )
        sock = self._get_socket()
        sent = sock.sendto(frame, (self._config.multicast_address, self._config.multicast_port))
        return sent
