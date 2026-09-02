"""WO-039-A — Real RTP / UDP multicast radio ingest receiver.

:class:`RtpReceiver` is the production radio ingest component.  It binds a UDP
socket to a multicast group, joins the group on a configurable interface, and
on a dedicated background thread:

    UDP multicast -> RTP v2 parser -> RTP validation -> G.711 A-law decode
    -> PCM S16LE / 8000 Hz / mono -> on_pcm(PcmFrame)

It is the real radio transport (WO-039-A §3): it does NOT use the WO-038
``TCA1`` test-frame format and does NOT wrap real RTP traffic in TCA1.  The
test-frame implementation lives in ``MulticastAudioReceiver`` and is kept for
backward compatibility / the deterministic test simulator.

Failure model (WO-039-A §18):
  * a single malformed RTP packet is dropped and recorded (never crashes);
  * a sequence gap or duplicate is recorded (never crashes);
  * a socket interruption degrades the affected source only;
  * shutdown closes the socket, thread and multicast membership, and no
    background thread is leaked.

Interface selection (WO-039-A §11):
  ``network_interface`` accepts ``AUTO`` (OS default), an explicit IPv4
  address, or a named interface (best-effort resolution to a local IPv4).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.audio.alaw import alaw_to_pcm
from app.audio.audio_config import AudioConfig
from app.audio.rtp import parse_rtp_packet, validate_rtp_packet
from app.audio.rtp_stream import RtpDisposition, RtpStreamTracker

logger = logging.getLogger(__name__)

# Interface selection presets (WO-039-A §11).  AUTO lets the OS choose the
# default multicast interface; the rest are best-effort resolution targets.
_INTERFACE_AUTO = ("AUTO", "AUTO_DEFAULT", "DEFAULT", "")


@dataclass(frozen=True)
class RtpPcmFrame:
    """One decoded PCM frame emitted by :class:`RtpReceiver`.

    Attributes:
        pcm: Decoded PCM ``S16LE`` bytes (mono, ``sample_rate`` Hz).
        sequence_number: The RTP sequence number of the source packet.
        timestamp: The RTP timestamp of the source packet (codec clock).
        ssrc: The RTP synchronization source identifier.
        payload_type: The RTP payload type (e.g. 8 for G.711 A-law).
        sample_rate: PCM sample rate (Hz) carried on the frame.
        channels: PCM channel count carried on the frame.
        received_at: UTC time the datagram was received.
    """

    pcm: bytes
    sequence_number: int
    timestamp: int
    ssrc: int
    payload_type: int
    sample_rate: int
    channels: int
    received_at: datetime


def resolve_interface_address(network_interface: str) -> str | None:
    """Resolve a configured ``network_interface`` to a local IPv4 address.

    Returns:
        * ``None`` for ``AUTO``/empty (let the OS choose the default
          multicast interface);
        * the literal address for an explicit IPv4;
        * a best-effort host IPv4 for a named interface (e.g. ``eth0``).

    Note:
        Precise per-interface address resolution by name is best-effort on this
        platform without adding a dependency; for deterministic behaviour use
        ``AUTO`` or an explicit IPv4 address.
    """
    if network_interface is None:
        return None
    value = str(network_interface).strip()
    if value.upper() in _INTERFACE_AUTO:
        return None
    try:
        parsed = ipaddress.ip_address(value)
        if parsed.version == 4:
            return str(parsed)
    except ValueError:
        pass
    # Named interface: best-effort resolution to the host's IPv4.
    try:
        addresses = {
            str(info[4][0])
            for info in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM
            )
        }
        if addresses:
            resolved = min(addresses)
            logger.warning(
                "WO-039-A: named interface %r resolved best-effort to %s",
                value,
                resolved,
            )
            return resolved
    except OSError:
        pass
    logger.warning("WO-039-A: could not resolve interface %r; using OS default", value)
    return None


class RtpReceiver:
    """Real RTP/UDP multicast receiver producing PCM frames.

    Args:
        config: The :class:`AudioConfig` (protocol must be ``"rtp"``).
        on_pcm: Callable ``(RtpPcmFrame) -> None`` invoked for each accepted,
            decoded frame.  Called on the receiver thread; it must be fast and
            must not raise (exceptions are logged and isolated).
    """

    def __init__(
        self,
        config: AudioConfig,
        on_pcm: Callable[[RtpPcmFrame], None],
    ) -> None:
        if not config.is_rtp:
            raise ValueError(
                f"RtpReceiver requires protocol='rtp', got {config.protocol!r}"
            )
        self._config = config
        self._on_pcm = on_pcm
        self._tracker = RtpStreamTracker(expected_payload_type=config.payload_type)
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._last_error: str | None = None
        self._malformed: int = 0

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start receiving.  Idempotent and thread-safe."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="wo039a-rtp-receiver",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop receiving.  Idempotent and thread-safe.  Joins the thread."""
        thread: threading.Thread | None = None
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def is_active(self) -> bool:
        """Whether the receiver is currently running."""
        with self._lock:
            return self._running

    def is_bound(self) -> bool:
        """Whether the receiver socket has been bound (ready to receive)."""
        with self._lock:
            return self._socket is not None

    # -- observability ------------------------------------------------------

    def snapshot(self) -> dict:
        """Return per-source observability state (WO-039-A §19)."""
        with self._lock:
            running = self._running
            last_error = self._last_error
            malformed = self._malformed
        snapshot = self._tracker.snapshot()
        snapshot.update(
            {
                "running": running,
                "codec": self._config.codec,
                "sample_rate": self._config.sample_rate,
                "channels": self._config.channels,
                "multicast_address": self._config.multicast_address,
                "udp_port": self._config.multicast_port,
                "network_interface": self._config.network_interface,
                "payload_type": self._config.payload_type,
                "malformed": malformed,
                "last_error": last_error,
            }
        )
        return snapshot

    # -- internals ----------------------------------------------------------

    def _interface_ip(self) -> str:
        """Resolve the multicast join interface address.

        ``network_interface`` is authoritative (AUTO -> OS default).  When it
        does not resolve to a concrete address, fall back to ``join_interface``
        (the loopback 127.0.0.1 used by same-host tests/simulators).
        """
        addr = resolve_interface_address(self._config.network_interface)
        if addr is None:
            addr = self._config.join_interface or "0.0.0.0"
        return addr

    def _bind(self) -> socket.socket:
        """Create and bind the UDP socket, joining the multicast group."""
        config = self._config
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # SO_REUSEADDR so a same-host simulator and receiver can coexist.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((config.bind_address or "", config.multicast_port))
        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(config.multicast_address),
            socket.inet_aton(self._interface_ip()),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(config.frame_timeout)
        return sock

    def _drop_membership(self, sock: socket.socket) -> None:
        """Leave the multicast group (best-effort on shutdown)."""
        try:
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(self._config.multicast_address),
                socket.inet_aton(self._interface_ip()),
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except OSError:
            pass

    def _run(self) -> None:
        """Receiver thread body.  Never raises out of the loop."""
        try:
            sock = self._bind()
        except OSError as exc:
            self._record_error(f"bind failed: {exc}")
            logger.error("WO-039-A RTP receiver bind failed: %s", exc)
            return

        with self._lock:
            self._socket = sock

        try:
            while not self._stop_event.is_set():
                try:
                    payload, _addr = sock.recvfrom(self._config.receive_buffer)
                except TimeoutError:
                    continue
                except OSError as exc:
                    self._record_error(f"recv failed: {exc}")
                    logger.warning("WO-039-A RTP receiver recv failed: %s", exc)
                    break
                self._handle_payload(payload)
        finally:
            self._drop_membership(sock)
            try:
                sock.close()
            except OSError:  # pragma: no cover - defensive
                pass
            with self._lock:
                self._socket = None

    def _handle_payload(self, payload: bytes) -> None:
        """Parse/validate one datagram, decode, and dispatch a PCM frame."""
        try:
            packet = parse_rtp_packet(payload)
            validate_rtp_packet(packet, expected_payload_type=self._config.payload_type)
        except ValueError as exc:
            self._record_error(f"malformed rtp: {exc}")
            with self._lock:
                self._malformed += 1
            logger.warning("WO-039-A RTP receiver dropped malformed packet: %s", exc)
            return

        result = self._tracker.on_packet(packet)
        # Duplicates are never emitted twice (WO-039-A §5).  A late /
        # out-of-order packet is still real audio, so it is emitted.
        if result.disposition == RtpDisposition.DUPLICATE:
            return

        if self._config.codec == "pcm_alaw":
            pcm = alaw_to_pcm(packet.payload)
        else:
            # Unknown codec: pass the payload through unchanged (the verified
            # PT=8 path is A-law; anything else is not decoded here).
            pcm = packet.payload

        frame = RtpPcmFrame(
            pcm=pcm,
            sequence_number=packet.sequence_number,
            timestamp=packet.timestamp,
            ssrc=packet.ssrc,
            payload_type=packet.payload_type,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
            received_at=datetime.now(timezone.utc),
        )
        try:
            self._on_pcm(frame)
        except Exception as exc:
            self._record_error(f"on_pcm failed: {exc}")
            logger.exception("WO-039-A RTP receiver on_pcm hook failed")

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
