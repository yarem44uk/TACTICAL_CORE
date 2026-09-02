"""WO-039-A — Real RTP / G.711 A-law multicast test simulator.

:class:`RtpSimulator` emits real RFC 3550 RTP packets carrying G.711 A-law
(PCMA) payloads to a configured multicast group.  It is the controlled test
source required by WO-039-A §15 TEST 9 / TEST 10:

    real RTP/G.711 A-law multicast -> real UDP -> real RTP parser
    -> real A-law decode -> PCM

It is distinct from the WO-038 ``MulticastAudioSimulator`` (which emits the
proprietary ``TCA1`` test-frame format).  The RTP simulator builds genuine RTP
headers (version 2, configurable payload type / sequence / timestamp / SSRC)
and does NOT wrap traffic in TCA1.

No operational address is hardcoded: the multicast group / port / interface
come from the :class:`AudioConfig`.  The simulator can inject controlled
sequence gaps, duplicates and out-of-order packets for deterministic tests.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import dataclass

from app.audio.alaw import alaw_encode_byte
from app.audio.audio_config import AudioConfig
from app.audio.rtp_receiver import resolve_interface_address

logger = logging.getLogger(__name__)

# Default SSRC used by the simulator when none is configured.
_DEFAULT_SSRC = 0x536816391 & 0xFFFFFFFF


@dataclass(frozen=True)
class RtpSendPacket:
    """A configured RTP packet ready to be sent by :class:`RtpSimulator`."""

    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    marker: bool
    payload: bytes


def build_rtp_packet(
    *,
    payload_type: int,
    sequence_number: int,
    timestamp: int,
    ssrc: int,
    payload: bytes,
    marker: bool = False,
    version: int = 2,
) -> bytes:
    """Build a raw RFC 3550 RTP packet.

    Args:
        payload_type: RTP payload type (7-bit).
        sequence_number: RTP sequence number (16-bit, truncated).
        timestamp: RTP timestamp (32-bit, truncated).
        ssrc: Synchronization source identifier (32-bit, truncated).
        payload: RTP payload bytes.
        marker: Whether to set the M (marker) bit.
        version: RTP version (default 2).

    Returns:
        The raw RTP packet bytes (header + payload), with no padding or
        extension and no CSRC entries.
    """
    byte0 = (version << 6) | 0x00  # no padding, no extension, no CSRC
    byte1 = (0x80 if marker else 0x00) | (payload_type & 0x7F)
    header = struct.pack(
        ">BBHII",
        byte0,
        byte1,
        sequence_number & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF,
    )
    return header + payload


class RtpSimulator:
    """Sends real RTP / G.711 A-law packets to a multicast group.

    Args:
        config: The :class:`AudioConfig` (multicast group, port, interface).
        ssrc: Optional SSRC (defaults to a stable value).  Change it to test
            SSRC transition handling.
        payload_type: Optional payload type (defaults to ``config.payload_type``).
    """

    def __init__(
        self,
        config: AudioConfig,
        ssrc: int | None = None,
        payload_type: int | None = None,
    ) -> None:
        self._config = config
        self._ssrc = (ssrc if ssrc is not None else _DEFAULT_SSRC) & 0xFFFFFFFF
        self._payload_type = (
            payload_type if payload_type is not None else config.payload_type
        )
        self._socket: socket.socket | None = None
        self._seq = 0
        self._timestamp = 0

    # -- lifecycle ----------------------------------------------------------

    def _get_socket(self) -> socket.socket:
        """Create a UDP socket configured for multicast loopback on the host."""
        if self._socket is None:
            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            interface_ip = resolve_interface_address(self._config.network_interface)
            if interface_ip is None:
                interface_ip = self._config.join_interface
            if interface_ip:
                try:
                    sock.setsockopt(
                        socket.IPPROTO_IP,
                        socket.IP_MULTICAST_IF,
                        socket.inet_aton(interface_ip),
                    )
                except OSError:
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

    # -- packet building ----------------------------------------------------

    def build(
        self,
        payload: bytes | None = None,
        *,
        seq: int | None = None,
        ts: int | None = None,
        ssrc: int | None = None,
        marker: bool = False,
        payload_type: int | None = None,
    ) -> RtpSendPacket:
        """Build a packet using explicit or auto-advancing sequence/timestamp.

        When ``seq``/``ts`` are omitted they auto-advance by +1 / +160 per call
        (matching the verified stream: 160 samples per packet at 8000 Hz).
        """
        sequence_number = self._seq if seq is None else seq
        timestamp = self._timestamp if ts is None else ts
        self._seq = (sequence_number + 1) & 0xFFFF
        self._timestamp = timestamp + 160
        return RtpSendPacket(
            payload_type=(
                payload_type if payload_type is not None else self._payload_type
            ),
            sequence_number=sequence_number,
            timestamp=timestamp,
            ssrc=(ssrc if ssrc is not None else self._ssrc) & 0xFFFFFFFF,
            marker=marker,
            payload=payload if payload is not None else b"",
        )

    # -- sending ------------------------------------------------------------

    def send(
        self,
        payload: bytes | None = None,
        *,
        seq: int | None = None,
        ts: int | None = None,
        ssrc: int | None = None,
        marker: bool = False,
        payload_type: int | None = None,
    ) -> int:
        """Send one RTP packet to the multicast group.  Returns bytes sent."""
        packet = self.build(
            payload,
            seq=seq,
            ts=ts,
            ssrc=ssrc,
            marker=marker,
            payload_type=payload_type,
        )
        raw = build_rtp_packet(
            payload_type=packet.payload_type,
            sequence_number=packet.sequence_number,
            timestamp=packet.timestamp,
            ssrc=packet.ssrc,
            payload=packet.payload,
            marker=packet.marker,
        )
        sock = self._get_socket()
        return sock.sendto(raw, (self._config.multicast_address, self._config.multicast_port))

    def send_silence(self, n: int = 1, samples: int = 160, *, value: int = 0x55) -> int:
        """Send ``n`` A-law silence packets (default 160 samples each).

        Returns the total bytes sent.  ``value`` is the A-law byte repeated to
        form each payload (0x55 is the standard near-zero A-law code).
        """
        payload = bytes([value & 0xFF]) * samples
        total = 0
        for _ in range(n):
            total += self.send(payload)
        return total

    def send_pcm(self, pcm: bytes, *, seq: int | None = None, ts: int | None = None) -> int:
        """Encode 16-bit LE PCM to A-law and send it as one RTP packet."""
        count = len(pcm) // 2
        samples = struct.unpack(f"<{count}h", pcm[: count * 2])
        payload = bytes(alaw_encode_byte(s) for s in samples)
        return self.send(payload, seq=seq, ts=ts)
