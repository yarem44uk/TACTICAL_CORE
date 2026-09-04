"""WO-041 — Deterministic real RTP capture reader (pcapng -> RTP -> PCM -> WAV).

This is the benchmark / evidence reader for the REAL captured radio RTP stream
(W-041-REAL-RTP-CAPTURE).  It consumes a ``.pcapng`` packet capture and replays
the real multicast RTP radio stream through the EXISTING WO-039 audio path:

    radio_rtp.pcapng
        -> RTP packet input (Ethernet/IPv4/UDP parse)
        -> RTP validation            (app.audio.rtp.parse/validate_rtp_packet)
        -> RTP reconstruction        (app.audio.rtp_stream.RtpStreamTracker)
        -> G.711 A-law decode        (app.audio.alaw.alaw_to_pcm)
        -> PCM frames                (app.audio.rtp_receiver.RtpPcmFrame)
        -> WAV master                (app.audio.wav_writer.write_wav_atomic)

Design rules honoured here:

* It REUSES the existing WO-039 components.  It does NOT create a parallel
  production audio path, does NOT open sockets, does NOT select an STT engine,
  and does NOT touch the Core event architecture.
* It is deterministic: the same capture always yields the same ordered packets,
  the same PCM bytes, and the same WAV SHA-256.
* It never invents samples for a missing packet.  Sequence gaps and duplicates
  are observed and recorded, never silently filled.
* The master WAV is written through the production ``write_wav_atomic`` boundary
  so the SHA-256 is over the exact stored WAV bytes.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.audio.alaw import alaw_to_pcm
from app.audio.rtp import RtpPacket, parse_rtp_packet, validate_rtp_packet
from app.audio.rtp_receiver import RtpPcmFrame
from app.audio.rtp_stream import RtpDisposition, RtpStreamTracker
from app.audio.wav_writer import WavResult, write_wav_atomic

# ---------------------------------------------------------------------------
# pcapng block types / magic
# ---------------------------------------------------------------------------
_SHB = 0x0A0D0D0A
_IDB = 0x00000001
_EPB = 0x00000006
_SPB = 0x00000003

# Default timestamp resolution when the IDB does not carry an if_tsresol option
# (10^6 ticks/sec = microseconds).
_DEFAULT_TSRESOL = 6


@dataclass(frozen=True)
class CaptureStream:
    """The reconstructed real radio RTP stream from a packet capture.

    Attributes:
        source_ip: The observed UDP source IP.
        dest_ip: The observed UDP destination IP.
        source_port: The observed UDP source port.
        dest_port: The observed UDP destination port.
        payload_type: The observed RTP payload type (8 = G.711 A-law / PCMA).
        ssrc: The single observed synchronization source identifier.
        packets: The accepted RTP packets in sequence order (initial / in-order
            / gap only; duplicates and out-of-order packets are excluded).
        stats: Reconstruction statistics (gaps / duplicates / dropped / order).
        malformed: Number of target-flow datagrams that failed RTP validation.
        udp_datagrams: Total target-flow UDP datagrams inspected.
    """

    source_ip: str
    dest_ip: str
    source_port: int
    dest_port: int
    payload_type: int
    ssrc: int
    packets: tuple[RtpPacket, ...]
    stats: dict
    malformed: int
    udp_datagrams: int


class RtpCaptureReader:
    """Deterministic pcapng capture reader for the real radio RTP stream.

    Args:
        path: Path to the ``.pcapng`` capture.
        source_ip: Optional source IP filter (e.g. ``172.19.4.118``).
        dest_ip: Optional destination IP filter (e.g. ``239.233.18.30``).
        udp_port: Optional UDP port filter (e.g. ``5033``).
        payload_type: Optional expected RTP payload type (e.g. ``8``).
    """

    def __init__(
        self,
        path: str,
        *,
        source_ip: str | None = None,
        dest_ip: str | None = None,
        udp_port: int | None = None,
        payload_type: int | None = None,
    ) -> None:
        self._path = path
        self._source_ip = source_ip
        self._dest_ip = dest_ip
        self._udp_port = udp_port
        self._payload_type = payload_type

    # -- public -------------------------------------------------------------

    def read(self) -> CaptureStream:
        """Parse the capture, reconstruct the target RTP stream, and decode it.

        Returns:
            A :class:`CaptureStream` describing the verified real stream.

        Raises:
            FileNotFoundError: If the capture path does not exist.
            ValueError: If the capture is malformed, the target stream cannot
                be identified, or multiple distinct SSRC values are observed
                (a single capture reader must not silently combine streams).
        """
        with open(self._path, "rb") as fh:
            data = fh.read()
        if not data:
            raise ValueError("capture is empty")

        packets, interfaces = _parse_pcapng(data)
        if not packets:
            raise ValueError("capture contains no packet blocks")

        target_udp, flow_meta = _filter_target(
            packets, self._source_ip, self._dest_ip, self._udp_port
        )
        if not target_udp:
            raise ValueError("no UDP datagrams matched the target flow filter")

        # Reuse the WO-039 RTP parser/validator + stream tracker for
        # reconstruction / gap / duplicate detection.
        tracker = RtpStreamTracker(expected_payload_type=self._payload_type)
        accepted: list[RtpPacket] = []
        seen_ssrcs: set[int] = set()
        malformed = 0
        for raw in target_udp:
            try:
                packet = parse_rtp_packet(raw)
                validate_rtp_packet(
                    packet, expected_payload_type=self._payload_type
                )
                seen_ssrcs.add(packet.ssrc)
                result = tracker.on_packet(packet)
                # Emit PCM only for packets the stream policy accepts: the
                # arriving packet for an initial / in-order / gap packet.
                # Duplicates are never emitted twice (WO-039-A §5) and
                # out-of-order (late) packets are never merged into the
                # decoded payload (WO-041-CORR-01 F-01).
                if result.disposition in (
                    RtpDisposition.INITIAL,
                    RtpDisposition.IN_ORDER,
                    RtpDisposition.GAP,
                ):
                    accepted.append(packet)
            except ValueError:
                malformed += 1

        if not accepted:
            raise ValueError(
                "no valid RTP packets matched the target flow / payload type"
            )

        # A capture reader configured for ONE RTP stream must not silently
        # combine multiple SSRCs: fail closed (WO-041-CORR-01 F-02).
        if len(seen_ssrcs) != 1:
            raise ValueError(
                f"multiple SSRC values observed: {sorted(seen_ssrcs)}"
            )

        # Preserve sequence order (the tracker already recorded gaps/dups).
        accepted.sort(key=lambda p: p.sequence_number)

        src_ip, dst_ip, sport, dport = flow_meta
        return CaptureStream(
            source_ip=src_ip,
            dest_ip=dst_ip,
            source_port=sport,
            dest_port=dport,
            payload_type=accepted[0].payload_type,
            ssrc=accepted[0].ssrc,
            packets=tuple(accepted),
            stats=tracker.stats.as_dict(),
            malformed=malformed,
            udp_datagrams=len(target_udp),
        )

    def decode_pcm(self, stream: CaptureStream) -> bytes:
        """Decode the accepted RTP payloads to PCM ``S16LE`` (G.711 A-law)."""
        payload = b"".join(p.payload for p in stream.packets)
        return alaw_to_pcm(payload)

    def write_wav(
        self,
        stream: CaptureStream,
        path: str,
        *,
        sample_rate: int = 8000,
        channels: int = 1,
    ) -> WavResult:
        """Write the decoded PCM to a lossless WAV master via ``write_wav_atomic``.

        Returns:
            The :class:`WavResult` (with the deterministic SHA-256 of the exact
            stored WAV bytes).
        """
        pcm = self.decode_pcm(stream)
        return write_wav_atomic(pcm, path, sample_rate, channels, sampwidth=2)

    def iter_frames(
        self,
        stream: CaptureStream,
        *,
        sample_rate: int = 8000,
        channels: int = 1,
        start: datetime | None = None,
    ) -> list[RtpPcmFrame]:
        """Build the :class:`RtpPcmFrame` stream for the recording boundary.

        Each frame carries one decoded 20 ms RTP packet (160 samples @ 8000 Hz).
        ``received_at`` is derived deterministically from the authoritative RTP
        timestamp (sample clock), so the same capture always yields the same
        frame timestamps (the arrival-jitter-is-not-silence rule).  This is the
        exact frame shape the WO-039-B ``TransmissionRecorder`` consumes via
        ``on_pcm``.

        Args:
            stream: The reconstructed capture stream.
            sample_rate: PCM sample rate carried on the frames.
            channels: PCM channel count carried on the frames.
            start: Base UTC time for the first frame.  Defaults to ``now``; pass
                a fixed value for deterministic recording timestamps.
        """
        from datetime import timedelta

        frames: list[RtpPcmFrame] = []
        base = start or datetime.now(timezone.utc)
        if not stream.packets:
            return frames
        first_ts = stream.packets[0].timestamp
        for packet in stream.packets:
            pcm = alaw_to_pcm(packet.payload)
            offset_s = (packet.timestamp - first_ts) / sample_rate
            received = base + timedelta(seconds=offset_s)
            frames.append(
                RtpPcmFrame(
                    pcm=pcm,
                    sequence_number=packet.sequence_number,
                    timestamp=packet.timestamp,
                    ssrc=packet.ssrc,
                    payload_type=packet.payload_type,
                    sample_rate=sample_rate,
                    channels=channels,
                    received_at=received,
                )
            )
        return frames


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def find_capture(*candidates: str) -> str | None:
    """Return the first existing capture path among ``candidates``."""
    for path in candidates:
        if path and __import__("os").path.exists(path):
            return path
    return None


def _parse_pcapng(data: bytes) -> tuple[list[tuple[int, int, bytes]], list[dict]]:
    """Parse pcapng into a list of ``(timestamp_ticks, tsresol, packet_bytes)``.

    Returns ``(packets, interfaces)`` where each interface is a dict with
    ``tsresol`` (ticks-per-second) and ``name``.
    """
    if data[:4] == b"\x0a\x0d\x0d\x0a":
        magic = data[8:12]
        endian = "<" if magic == b"\x4d\x3c\x2b\x1a" else (
            ">" if magic == b"\x1a\x2b\x3c\x4d" else None
        )
        if endian is None:
            raise ValueError("unknown pcapng byte-order magic")
    else:
        raise ValueError("not a pcapng file (bad magic)")

    packets: list[tuple[int, int, bytes]] = []
    interfaces: list[dict] = []
    off = 0
    n = len(data)
    while off + 12 <= n:
        btype, blen = struct.unpack_from(endian + "II", data, off)
        if blen < 12 or off + blen > n:
            break
        if btype == _SHB:
            pass
        elif btype == _IDB:
            # linktype(2) reserved(2) snaplen(4) then options.
            tsresol = _DEFAULT_TSRESOL
            name = ""
            j = off + 16
            end = off + blen - 4
            while j + 4 <= end:
                oc, ol = struct.unpack_from(endian + "HH", data, j)
                if oc == 0:
                    break
                v = data[j + 4 : j + 4 + ol]
                if oc == 9 and len(v) >= 1:
                    b = v[0]
                    tsresol = 2 ** (b & 0x7F) if (b & 0x80) else 10 ** b
                elif oc == 2:
                    name = v.decode("utf-8", "replace")
                j += 4 + ol + ((4 - (ol % 4)) % 4)
            interfaces.append({"tsresol": tsresol, "name": name})
        elif btype == _EPB:
            ifid, ts_hi, ts_lo, caplen, _origlen = struct.unpack_from(
                endian + "IIIII", data, off + 8
            )
            pkt = data[off + 28 : off + 28 + caplen]
            ticks = (ts_hi << 32) | ts_lo
            tsresol = (
                interfaces[ifid]["tsresol"]
                if ifid < len(interfaces)
                else _DEFAULT_TSRESOL
            )
            packets.append((ticks, tsresol, pkt))
        elif btype == _SPB:
            caplen = struct.unpack_from(endian + "I", data, off + 8)[0]
            pkt = data[off + 12 : off + 12 + caplen]
            packets.append((0, _DEFAULT_TSRESOL, pkt))
        off += blen
    return packets, interfaces


def _filter_target(
    packets: list[tuple[int, int, bytes]],
    source_ip: str | None,
    dest_ip: str | None,
    udp_port: int | None,
) -> tuple[list[bytes], tuple[str, str, int, int]]:
    """Extract the target-flow UDP payloads (RTP datagrams) and flow metadata.

    Returns ``(rtp_datagrams, (src_ip, dst_ip, sport, dport))``.
    """
    out: list[bytes] = []
    flow_meta: tuple[str, str, int, int] | None = None
    for _, _, pkt in packets:
        if len(pkt) < 14:
            continue
        eth_type = struct.unpack_from(">H", pkt, 12)[0]
        off = 14
        if eth_type == 0x8100:  # VLAN tag
            eth_type = struct.unpack_from(">H", pkt, 16)[0]
            off = 18
        if eth_type != 0x0800:  # IPv4 only
            continue
        if pkt[off + 9] != 17:  # UDP
            continue
        ihl = (pkt[off] & 0x0F) * 4
        total_len = struct.unpack_from(">H", pkt, off + 2)[0]
        udp = pkt[off + ihl : off + total_len]
        if len(udp) < 8:
            continue
        sport, dport = struct.unpack_from(">HH", udp, 0)
        src = socket.inet_ntoa(pkt[off + 12 : off + 16])
        dst = socket.inet_ntoa(pkt[off + 16 : off + 20])
        if source_ip is not None and src != source_ip:
            continue
        if dest_ip is not None and dst != dest_ip:
            continue
        if udp_port is not None and dport != udp_port:
            continue
        if flow_meta is None:
            flow_meta = (src, dst, sport, dport)
        out.append(udp[8:])
    if flow_meta is None:
        raise ValueError("no datagrams matched the target flow filter")
    return out, flow_meta
