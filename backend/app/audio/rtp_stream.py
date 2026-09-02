"""WO-039-A — Per-source RTP stream state and statistics tracking.

:class:`RtpStreamTracker` maintains the per-SSRC receive state needed to detect
and observe packet loss / duplication / reordering without inventing audio
samples:

  * duplicates are never emitted twice (WO-039-A §5);
  * sequence gaps are detected and counted, and are observable — the tracker
    never silently pretends there was no loss;
  * out-of-order (late) packets are detected separately from gaps;
  * an SSRC change is treated as a stream transition: the per-stream RTP state
    (sequence/timestamp baseline) is reset, while cumulative statistics are
    preserved.

The tracker is pure Python, thread-free, and used by the receiver thread.  It
emits a :class:`RtpStreamResult` describing the disposition of each packet so
the caller can decide whether to emit PCM.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

from app.audio.rtp import RtpPacket


class RtpDisposition(enum.Enum):
    """Disposition of one received RTP packet relative to its stream."""

    INITIAL = "initial"
    IN_ORDER = "in_order"
    DUPLICATE = "duplicate"
    GAP = "gap"
    OUT_OF_ORDER = "out_of_order"
    SSRC_CHANGE = "ssrc_change"


@dataclass(frozen=True)
class RtpStreamResult:
    """Result of feeding one RTP packet to a stream tracker."""

    disposition: RtpDisposition
    dropped: int = 0  # number of packets inferred lost by a forward gap


@dataclass
class RtpStreamStats:
    """Cumulative per-source RTP statistics (observability contract).

    Attributes:
        packets_received: Total RTP packets accepted (post-validation).
        packets_dropped: Total packets inferred lost (forward-sequence gaps).
        duplicates: Total duplicate packets observed (not emitted twice).
        sequence_gaps: Total forward-sequence gap events.
        out_of_order: Total late/out-of-order packets observed.
        bytes_received: Total RTP payload bytes accepted.
        current_ssrc: The current synchronization source identifier (or None).
        ssrc_transitions: Number of observed SSRC changes.
        last_sequence: The last accepted in-order sequence number (or None).
        last_timestamp: The last accepted RTP timestamp (or None).
        last_packet_at: UTC datetime of the last accepted packet (or None).
    """

    packets_received: int = 0
    packets_dropped: int = 0
    duplicates: int = 0
    sequence_gaps: int = 0
    out_of_order: int = 0
    bytes_received: int = 0
    current_ssrc: int | None = None
    ssrc_transitions: int = 0
    last_sequence: int | None = None
    last_timestamp: int | None = None
    last_packet_at: datetime | None = None

    def as_dict(self) -> dict:
        """Serialisable statistics snapshot."""
        return {
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
            "duplicates": self.duplicates,
            "sequence_gaps": self.sequence_gaps,
            "out_of_order": self.out_of_order,
            "bytes_received": self.bytes_received,
            "current_ssrc": self.current_ssrc,
            "ssrc_transitions": self.ssrc_transitions,
            "last_sequence": self.last_sequence,
            "last_timestamp": self.last_timestamp,
            "last_packet_at": (
                self.last_packet_at.isoformat() if self.last_packet_at else None
            ),
        }


def _sequence_delta(new: int, previous: int) -> int:
    """Signed 16-bit modular difference ``new - previous`` in ``[0, 65535)``."""
    return (new - previous) & 0xFFFF


class RtpStreamTracker:
    """Tracks RTP sequence/timestamp state for one source stream.

    Args:
        expected_payload_type: Optional payload type the tracker expects (the
            receiver validates before feeding; kept for completeness).
    """

    def __init__(self, expected_payload_type: int | None = None) -> None:
        self._expected_payload_type = expected_payload_type
        self._stats = RtpStreamStats()

    # -- public accessors --------------------------------------------------

    @property
    def stats(self) -> RtpStreamStats:
        """Live cumulative statistics for the stream."""
        return self._stats

    def snapshot(self) -> dict:
        """Return a serialisable statistics snapshot."""
        return self._stats.as_dict()

    # -- packet handling ---------------------------------------------------

    def on_packet(self, packet: RtpPacket) -> RtpStreamResult:
        """Record one received RTP packet and classify it.

        Args:
            packet: A parsed, validated :class:`RtpPacket`.

        Returns:
            An :class:`RtpStreamResult` describing the disposition.  The caller
            should emit PCM only for ``IN_ORDER``, ``INITIAL`` and ``GAP``
            dispositions (a gap emits the arriving packet, not invented
            samples) and must NOT emit twice for ``DUPLICATE``.
        """
        stats = self._stats

        # SSRC transition: reset per-stream baseline, preserve cumulative stats.
        if (
            stats.current_ssrc is not None
            and packet.ssrc != stats.current_ssrc
        ):
            stats.current_ssrc = packet.ssrc
            stats.ssrc_transitions += 1
            stats.last_sequence = None
            stats.last_timestamp = None
            result = RtpStreamResult(RtpDisposition.SSRC_CHANGE)
            self._accept(packet, stats, dropped=0)
            return result

        if stats.current_ssrc is None:
            stats.current_ssrc = packet.ssrc
            self._accept(packet, stats, dropped=0)
            return RtpStreamResult(RtpDisposition.INITIAL)

        if stats.last_sequence is None:
            self._accept(packet, stats, dropped=0)
            return RtpStreamResult(RtpDisposition.INITIAL)

        delta = _sequence_delta(packet.sequence_number, stats.last_sequence)
        if delta == 0:
            # Same sequence number again: duplicate, do not emit twice.
            stats.duplicates += 1
            return RtpStreamResult(RtpDisposition.DUPLICATE)
        if delta == 1:
            # The exact next expected sequence number: normal in-order.
            self._accept(packet, stats, dropped=0)
            return RtpStreamResult(RtpDisposition.IN_ORDER)
        if delta < 0x8000:
            # Forward jump: inferred packet loss (delta-1 missing packets).
            dropped = delta - 1
            stats.sequence_gaps += 1
            self._accept(packet, stats, dropped=dropped)
            return RtpStreamResult(RtpDisposition.GAP, dropped=dropped)
        # Backward jump (late packet): out-of-order, do not reset baseline.
        stats.out_of_order += 1
        return RtpStreamResult(RtpDisposition.OUT_OF_ORDER)

    # -- internals ---------------------------------------------------------

    def _accept(self, packet: RtpPacket, stats: RtpStreamStats, dropped: int) -> None:
        """Update counters for an accepted (in-order/initial/gap) packet."""
        stats.packets_received += 1
        stats.packets_dropped += dropped
        stats.bytes_received += len(packet.payload)
        stats.last_sequence = packet.sequence_number
        stats.last_timestamp = packet.timestamp
        stats.last_packet_at = datetime.now(timezone.utc)
