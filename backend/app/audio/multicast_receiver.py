"""WO-038 — Multicast UDP audio receiver.

:class:`MulticastAudioReceiver` binds a UDP socket to a multicast group,
joins the group on a configurable interface, and receives audio datagrams on a
dedicated background thread.

Failure model (WO-038 §7): a failure of the audio source must NOT crash the
Core.  The receiver therefore isolates every receive error:

  * malformed datagram       -> logged + skipped (no crash)
  * transient receive timeout -> treated as a no-op (no crash)
  * socket interruption       -> degraded state, thread exits; may be restarted

It exposes a callback ``on_segment(AudioSegment)`` invoked for each successfully
decoded frame, so the caller (adapter/orchestrator) owns STT/callsign/persistence
and is never crash-coupled to the transport.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
from collections.abc import Callable

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment, decode_frame

logger = logging.getLogger(__name__)


class MulticastAudioReceiver:
    """Receives WO-038 multicast audio frames on a background thread.

    Args:
        config: The :class:`AudioConfig` (multicast address, port, interface...).
        on_segment: Callable ``(AudioSegment) -> None`` invoked for each decoded
            frame.  Called on the receiver thread; it must be fast and must not
            raise (exceptions are logged and isolated by the caller).
    """

    def __init__(
        self,
        config: AudioConfig,
        on_segment: Callable[[AudioSegment], None],
    ) -> None:
        self._config = config
        self._on_segment = on_segment
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._last_error: str | None = None

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
                name="wo038-multicast-receiver",
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

    @property
    def last_error(self) -> str | None:
        """The last recorded receive error (or None)."""
        with self._lock:
            return self._last_error

    # -- internals ----------------------------------------------------------

    def _bind(self) -> socket.socket:
        """Create and bind the UDP socket, joining the multicast group."""
        config = self._config
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        # SO_REUSEADDR so the test simulator and receiver can coexist on the same
        # host without port conflicts.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to the group address (or the wildcard) on the configured port.
        sock.bind(("", config.multicast_port))
        # Join the multicast group on the configured interface.
        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(config.multicast_address),
            socket.inet_aton(config.join_interface),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(config.frame_timeout)
        return sock

    def _run(self) -> None:
        """Receiver thread body.  Never raises out of the loop."""
        try:
            sock = self._bind()
        except OSError as exc:
            self._record_error(f"bind failed: {exc}")
            logger.error("WO-038 receiver bind failed: %s", exc)
            return

        with self._lock:
            self._socket = sock

        try:
            while not self._stop_event.is_set():
                try:
                    payload, _addr = sock.recvfrom(self._config.receive_buffer)
                except TimeoutError:
                    # Transient timeout: no datagram in this window.  Not a
                    # failure; keep listening.
                    continue
                except OSError as exc:
                    # Socket interruption (e.g. closed): degrade, do not crash.
                    self._record_error(f"recv failed: {exc}")
                    logger.warning("WO-038 receiver recv failed: %s", exc)
                    break

                self._handle_payload(payload)
        finally:
            try:
                sock.close()
            except OSError:  # pragma: no cover - defensive
                pass
            with self._lock:
                self._socket = None

    def _handle_payload(self, payload: bytes) -> None:
        """Decode one datagram and dispatch it.  Isolates malformed frames."""
        try:
            segment = decode_frame(payload)
        except ValueError as exc:
            # Malformed frame: isolate, log, continue (no crash).
            self._record_error(f"malformed frame: {exc}")
            logger.warning("WO-038 receiver dropped malformed frame: %s", exc)
            return
        try:
            self._on_segment(segment)
        except Exception as exc:
            self._record_error(f"on_segment failed: {exc}")
            logger.exception("WO-038 receiver on_segment hook failed")

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
