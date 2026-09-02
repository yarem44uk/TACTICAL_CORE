"""WO-039-A — RFC 3550 RTP packet parser and validator.

:class:`RtpPacket` is the parsed, validated representation of a single Real-Time
Transport Protocol packet.  The parser implements the RFC 3550 fixed header and
correctly advances the header length when CSRC entries, a header extension, or
padding are present.

Production rationale (WO-039-A §4/§5): the real radio stream is

    UDP -> RTP v2 -> PT=8 (G.711 A-law / PCMA) -> 160-byte payload

This module is a pure, dependency-free parser.  It never opens sockets, never
decodes audio, and never touches the Core event architecture.  Malformed
packets raise :class:`ValueError` so the receiver can drop them safely without
crashing the source.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# RFC 3550 fixed header length (12 bytes).
RTP_FIXED_HEADER_LENGTH = 12


@dataclass(frozen=True)
class RtpPacket:
    """One parsed, validated RTP packet.

    Attributes:
        version: RTP version (must be 2 per RFC 3550).
        padding: Whether the P (padding) bit is set.
        extension: Whether the X (extension) bit is set.
        csrc_count: Number of CSRC identifiers (C bit field).
        marker: Whether the M (marker) bit is set.
        payload_type: Payload type (PT field, 7-bit).
        sequence_number: Sequence number (16-bit).
        timestamp: RTP timestamp (32-bit, in the codec clock domain).
        ssrc: Synchronization source identifier (32-bit).
        csrcs: Tuple of contributing-source identifiers (when present).
        header_length: The computed RTP header length in bytes (fixed + CSRC
            + extension).  This is what the parser must calculate correctly.
        payload: The RTP payload bytes (padding stripped when present).
    """

    version: int
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    csrcs: tuple[int, ...]
    header_length: int
    payload: bytes

    @property
    def payload_len(self) -> int:
        """Number of payload bytes (post padding-strip)."""
        return len(self.payload)


def parse_rtp_packet(data: bytes) -> RtpPacket:
    """Parse and validate one RTP packet (RFC 3550).

    Args:
        data: The RTP datagram payload (starting at the RTP fixed header).

    Returns:
        A fully-populated :class:`RtpPacket`.

    Raises:
        ValueError: If the packet is malformed (too short, bad version,
            truncated header, invalid padding, or an extension/CSRC region
            that overruns the datagram).  The caller is expected to drop
            malformed packets safely.
    """
    if not data:
        raise ValueError("empty RTP packet")
    if len(data) < RTP_FIXED_HEADER_LENGTH:
        raise ValueError(
            f"RTP packet too short: {len(data)} < {RTP_FIXED_HEADER_LENGTH}"
        )

    byte0 = data[0]
    byte1 = data[1]
    version = (byte0 >> 6) & 0x03
    padding = bool((byte0 >> 5) & 0x01)
    extension = bool((byte0 >> 4) & 0x01)
    csrc_count = byte0 & 0x0F
    marker = bool((byte1 >> 7) & 0x01)
    payload_type = byte1 & 0x7F

    if version != 2:
        raise ValueError(f"unsupported RTP version {version} (expected 2)")

    sequence_number, timestamp, ssrc = struct.unpack_from(">HII", data, 2)

    header_length = RTP_FIXED_HEADER_LENGTH + 4 * csrc_count
    if header_length > len(data):
        raise ValueError("RTP header overruns datagram (CSRC region)")

    csrcs: tuple[int, ...] = ()
    if csrc_count:
        csrcs = struct.unpack_from(f">{csrc_count}I", data, RTP_FIXED_HEADER_LENGTH)

    if extension:
        # Extension header: 16-bit profile + 16-bit length, then 4*length bytes.
        if header_length + 4 > len(data):
            raise ValueError("RTP header overruns datagram (extension length)")
        ext_length = struct.unpack_from(">H", data, header_length + 2)[0]
        header_length += 4 + 4 * ext_length
        if header_length > len(data):
            raise ValueError("RTP header overruns datagram (extension region)")

    payload = data[header_length:]
    if padding:
        if not payload:
            raise ValueError("RTP padding set but no payload bytes")
        pad_length = payload[-1]
        if pad_length > len(payload):
            raise ValueError(
                f"RTP padding length {pad_length} exceeds payload {len(payload)}"
            )
        payload = payload[:-pad_length]

    return RtpPacket(
        version=version,
        padding=padding,
        extension=extension,
        csrc_count=csrc_count,
        marker=marker,
        payload_type=payload_type,
        sequence_number=sequence_number,
        timestamp=timestamp,
        ssrc=ssrc,
        csrcs=csrcs,
        header_length=header_length,
        payload=payload,
    )


def validate_rtp_packet(
    packet: RtpPacket,
    *,
    expected_payload_type: int | None = None,
    expected_version: int = 2,
) -> None:
    """Validate a parsed RTP packet against configuration-derived expectations.

    Args:
        packet: The parsed :class:`RtpPacket`.
        expected_payload_type: When set, the packet's payload type must match
            (e.g. ``8`` for G.711 A-law / PCMA).
        expected_version: The only supported version (default 2).

    Raises:
        ValueError: If any validation rule is violated.
    """
    if packet.version != expected_version:
        raise ValueError(
            f"RTP version {packet.version} != expected {expected_version}"
        )
    if expected_payload_type is not None and packet.payload_type != expected_payload_type:
        raise ValueError(
            f"RTP payload type {packet.payload_type} != expected "
            f"{expected_payload_type}"
        )


def is_valid_rtp_packet(
    data: bytes,
    *,
    expected_payload_type: int | None = None,
) -> bool:
    """Return whether ``data`` parses and validates as an RTP packet.

    Never raises.  Convenience for safe receive loops.
    """
    try:
        packet = parse_rtp_packet(data)
        validate_rtp_packet(packet, expected_payload_type=expected_payload_type)
        return True
    except ValueError:
        return False
