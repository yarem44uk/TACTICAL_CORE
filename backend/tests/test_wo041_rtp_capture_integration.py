"""WO-041 tests — Real RTP capture integration (radio_rtp.pcapng -> PCM -> WAV).

These tests prove that TACTICAL_CORE can consume the REAL captured RTP radio
stream (``radio_rtp.pcapng``) through the EXISTING WO-039 path:

    REAL RTP CAPTURE
        -> RTP PACKET INPUT
        -> RTP VALIDATION          (app.audio.rtp.parse/validate_rtp_packet)
        -> G.711 A-law PAYLOAD      (app.audio.alaw.alaw_to_pcm)
        -> PCM AUDIO                (S16LE / 8000 Hz / mono)
        -> WAV MASTER               (app.audio.wav_writer.write_wav_atomic)

The WO-041 objective is NOT STT.  It proves the real captured radio stream can
enter TACTICAL_CORE and become a valid PCM/WAV audio master through the intended
architecture.  No STT engine is selected, installed, or invoked here.

Golden values below were derived from the supplied capture and independently
verified against the reference ffmpeg A-law decoder and the production
``write_wav_atomic`` boundary (see docs/benchmarks/rtp/WO-041-REAL-RTP-CAPTURE-INTEGRATION.md).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import datetime
import hashlib
import os
import socket
import struct
import subprocess
import wave

import pytest

from app.audio.alaw import alaw_to_pcm
from app.audio.audio_config import AudioConfig
from app.audio.recording_config import RecordingConfig
from app.audio.recorder import TransmissionRecorder
from app.audio.rtp import parse_rtp_packet
from app.audio.rtp_capture import RtpCaptureReader
from app.audio.rtp_stream import RtpDisposition, RtpStreamTracker
from app.audio.wav_writer import write_wav_atomic

# ---------------------------------------------------------------------------
# Verified capture facts (independently derived from radio_rtp.pcapng).
# ---------------------------------------------------------------------------
GOLDEN = {
    "source_ip": "172.19.4.118",
    "dest_ip": "239.233.18.30",
    "port": 5033,
    "payload_type": 8,
    "ssrc": 536816391,
    "version": 2,
    "seq_start": 14033,
    "seq_end": 16253,
    "packet_count": 1772,
    "sequence_gaps": 3,
    "dropped": 449,
    "duplicates": 0,
    "payload_bytes": 283520,
    "sample_count": 283520,
    "duration_s": 35.44,
    "sample_rate": 8000,
    "channels": 1,
    "sampwidth": 2,
    "pcm_sha256": "f3d973f3ed51394c94104c41f6e9ff6671e0210dd82a6bae62faab1530e8450c",
    "wav_sha256": "bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1",
}


def _find_capture() -> str | None:
    """Locate the real capture fixture (not committed to the repo)."""
    candidates = [
        os.environ.get("WO041_PCAP"),
        "/opt/data/wo041_evidence/radio_rtp.pcapng",
        "/opt/data/uploads/1788382671-3d155d40/test.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    # Fall back to any uploads/*/test.pcapng (the real capture fixture).
    if os.path.isdir("/opt/data/uploads"):
        for name in os.listdir("/opt/data/uploads"):
            p = os.path.join("/opt/data/uploads", name, "test.pcapng")
            if os.path.exists(p):
                return p
    return None


def _reader() -> RtpCaptureReader:
    path = _find_capture()
    assert path is not None, "radio_rtp.pcapng not found (real capture unavailable)"
    return RtpCaptureReader(
        path,
        source_ip=GOLDEN["source_ip"],
        dest_ip=GOLDEN["dest_ip"],
        udp_port=GOLDEN["port"],
        payload_type=GOLDEN["payload_type"],
    )


# ---------------------------------------------------------------------------
# Capture validation
# ---------------------------------------------------------------------------


def test_capture_available() -> None:
    """The real capture must be present.  Fails when the capture is unavailable."""
    assert _find_capture() is not None, "radio_rtp.pcapng not found"


def test_capture_stream_independently_verified() -> None:
    stream = _reader().read()
    assert stream.source_ip == GOLDEN["source_ip"]
    assert stream.dest_ip == GOLDEN["dest_ip"]
    assert stream.source_port == GOLDEN["port"]
    assert stream.dest_port == GOLDEN["port"]
    assert stream.payload_type == GOLDEN["payload_type"]
    assert stream.ssrc == GOLDEN["ssrc"]
    # Single consistent SSRC stream.
    assert len({p.ssrc for p in stream.packets}) == 1
    # Every accepted packet is RTP v2 with the expected PT.
    for packet in stream.packets:
        assert packet.version == GOLDEN["version"]
        assert packet.payload_type == GOLDEN["payload_type"]


def test_capture_stream_malformed_none() -> None:
    stream = _reader().read()
    assert stream.malformed == 0
    assert stream.udp_datagrams == GOLDEN["packet_count"]


# ---------------------------------------------------------------------------
# RTP reconstruction
# ---------------------------------------------------------------------------


def test_rtp_packets_preserve_order() -> None:
    stream = _reader().read()
    seqs = [p.sequence_number for p in stream.packets]
    assert seqs == sorted(seqs), "packets are not in sequence order"
    assert seqs[0] == GOLDEN["seq_start"]
    assert seqs[-1] == GOLDEN["seq_end"]


def test_rtp_packet_count_and_payload_length() -> None:
    stream = _reader().read()
    assert len(stream.packets) == GOLDEN["packet_count"]
    for packet in stream.packets:
        assert packet.payload_len == 160  # 160 samples @ 8 kHz = 20 ms


def test_rtp_gaps_and_duplicates_detected() -> None:
    stream = _reader().read()
    stats = stream.stats
    assert stats["sequence_gaps"] == GOLDEN["sequence_gaps"]
    assert stats["duplicates"] == GOLDEN["duplicates"]
    assert stats["packets_dropped"] == GOLDEN["dropped"]
    assert stats["packets_received"] == GOLDEN["packet_count"]
    assert stats["bytes_received"] == GOLDEN["payload_bytes"]


def test_rtp_timestamp_progression() -> None:
    stream = _reader().read()
    ts = [p.timestamp for p in stream.packets]
    # Every adjacent accepted packet advances by 160 samples (20 ms) except at
    # the known gap bursts (which jump by 160 * (dropped+1)).
    for i in range(1, len(ts)):
        delta = ts[i] - ts[i - 1]
        assert delta == 160 or delta in (160 * 184, 160 * 148, 160 * 120)


# ---------------------------------------------------------------------------
# Codec — G.711 A-law -> PCM
# ---------------------------------------------------------------------------


def test_alaw_decode_produces_valid_pcm() -> None:
    reader = _reader()
    stream = reader.read()
    pcm = reader.decode_pcm(stream)
    assert len(pcm) == GOLDEN["sample_count"] * GOLDEN["sampwidth"]
    assert len(pcm) % 2 == 0
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert len(set(samples)) > 1, "decoded PCM is not varied (not real content)"


def test_alaw_decode_deterministic() -> None:
    reader = _reader()
    stream = reader.read()
    assert reader.decode_pcm(stream) == reader.decode_pcm(stream)


def test_alaw_pcm_sha256_matches_golden() -> None:
    reader = _reader()
    stream = reader.read()
    pcm = reader.decode_pcm(stream)
    assert hashlib.sha256(pcm).hexdigest() == GOLDEN["pcm_sha256"]


@pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg not available for reference decode",
)
def test_alaw_decode_matches_ffmpeg_reference(tmp_path) -> None:
    """The A-law decoder must match the reference ffmpeg ``alaw`` decoder."""
    reader = _reader()
    stream = reader.read()
    payload = b"".join(p.payload for p in stream.packets)
    alaw_path = tmp_path / "stream.alaw"
    alaw_path.write_bytes(payload)
    ref = tmp_path / "ref.s16le"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "alaw", "-ar", "8000", "-ac", "1",
            "-i", str(alaw_path), "-f", "s16le", "-acodec", "pcm_s16le", str(ref),
        ],
        capture_output=True,
    )
    assert result.returncode == 0
    ref_pcm = ref.read_bytes()
    pcm = reader.decode_pcm(stream)
    assert pcm == ref_pcm, "A-law decode does not match ffmpeg reference"


# ---------------------------------------------------------------------------
# WAV master
# ---------------------------------------------------------------------------


def test_wav_master_valid_and_deterministic(tmp_path) -> None:
    reader = _reader()
    stream = reader.read()
    wav_path = str(tmp_path / "radio_rtp_master.wav")
    wav = reader.write_wav(stream, wav_path)
    assert wav.sample_rate == GOLDEN["sample_rate"]
    assert wav.channels == GOLDEN["channels"]
    assert wav.sampwidth == GOLDEN["sampwidth"]
    assert wav.sample_count == GOLDEN["sample_count"]
    assert wav.duration_ms == pytest.approx(GOLDEN["duration_s"] * 1000.0)
    assert wav.sha256 == GOLDEN["wav_sha256"]


def test_wav_master_readable(tmp_path) -> None:
    reader = _reader()
    stream = reader.read()
    wav_path = str(tmp_path / "radio_rtp_master.wav")
    reader.write_wav(stream, wav_path)
    with wave.open(wav_path, "rb") as wf:
        assert wf.getnchannels() == GOLDEN["channels"]
        assert wf.getsampwidth() == GOLDEN["sampwidth"]
        assert wf.getframerate() == GOLDEN["sample_rate"]
        assert wf.getnframes() == GOLDEN["sample_count"]
        assert wf.getnframes() / wf.getframerate() > 0.0


# ---------------------------------------------------------------------------
# Integration — the real capture through the existing TACTICAL_CORE boundary
# ---------------------------------------------------------------------------


def _audio_config() -> AudioConfig:
    return AudioConfig(
        multicast_address=GOLDEN["dest_ip"],
        multicast_port=GOLDEN["port"],
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=GOLDEN["payload_type"],
        sample_rate=GOLDEN["sample_rate"],
        channels=GOLDEN["channels"],
        packetization_ms=20,
        source_name="radio",
        join_interface="127.0.0.1",
        network_interface="AUTO",
        frame_timeout=0.2,
    )


def test_real_capture_through_recording_boundary(tmp_path) -> None:
    """The real capture frames flow through the production VAD/recording boundary.

    This is the WO-041 integration assertion: the real captured RTP radio stream
    is consumed by the existing ``TransmissionRecorder`` (VAD -> WAV master via
    ``write_wav_atomic``) and produces a valid WAV master.  No synthetic audio
    and no STT engine are involved.
    """
    reader = _reader()
    stream = reader.read()
    start = datetime.datetime(2026, 9, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)
    frames = reader.iter_frames(stream, start=start)
    assert len(frames) == GOLDEN["packet_count"]
    for frame in frames:
        assert frame.ssrc == GOLDEN["ssrc"]
        assert frame.payload_type == GOLDEN["payload_type"]
        assert frame.sample_rate == GOLDEN["sample_rate"]
        assert frame.channels == GOLDEN["channels"]
        assert len(frame.pcm) == 320  # 160 samples * 2 bytes

    recordings: list[dict] = []
    rec = TransmissionRecorder(
        _audio_config(),
        RecordingConfig(
            enabled=True,
            vad_enabled=True,
            audio_archive_root=str(tmp_path / "archive"),
            mp3_enabled=False,
        ),
        on_recording=recordings.append,
    )
    for frame in frames:
        rec.on_pcm(frame)
    rec.on_shutdown()

    assert len(recordings) >= 1, "the real capture did not produce a recording"
    for raw in recordings:
        rec_meta = raw["recording"]
        wav_path = rec_meta["wav_path"]
        assert os.path.exists(wav_path)
        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == GOLDEN["channels"]
            assert wf.getsampwidth() == GOLDEN["sampwidth"]
            assert wf.getframerate() == GOLDEN["sample_rate"]
            assert wf.getnframes() > 0
        # WAV master hash is present and the WAV is complete/valid.
        assert len(rec_meta["sha256"]) == 64


def test_no_stt_engine_involved() -> None:
    """WO-041 must not select, install, or invoke any STT engine."""
    # The reader and recorder are pure decode/record; no transcriber exists.
    assert not hasattr(_reader(), "transcriber")
    rec = TransmissionRecorder(_audio_config(), RecordingConfig(enabled=True, vad_enabled=True))
    assert not hasattr(rec, "transcriber")


# ---------------------------------------------------------------------------
# WO-041-CORR-01 — RTP edge-case hardening (F-01 / F-02 regression tests)
# ---------------------------------------------------------------------------
#
# Deterministic synthetic captures below exercise the exact edge-case policy:
#   INITIAL / IN_ORDER / GAP  -> accepted (emitted once)
#   DUPLICATE                 -> rejected (never emitted twice)
#   OUT_OF_ORDER              -> rejected (never merged into the payload)
#   multiple SSRC             -> FAIL CLOSED (explicit ValueError, no merge)


def _rtp_packet(seq: int, ssrc: int, payload_type: int = 8, ts: int | None = None) -> bytes:
    """Build a minimal RFC 3550 RTP v2 datagram (PT=8, 160-byte payload)."""
    if ts is None:
        ts = seq * 160
    payload = bytes([seq % 256]) * 160
    return struct.pack(">BBHII", 0x80, payload_type, seq & 0xFFFF, ts, ssrc) + payload


def _eth_frame(src_ip: str, dst_ip: str, sport: int, dport: int, rtp: bytes) -> bytes:
    """Wrap an RTP datagram in Ethernet / IPv4 / UDP (as _filter_target expects)."""
    eth = b"\x00" * 12 + struct.pack(">H", 0x0800)
    total_len = 20 + 8 + len(rtp)
    ip = struct.pack(
        ">BBHHHBBH4s4s", 0x45, 0, total_len, 0, 0, 64, 17, 0,
        socket.inet_aton(src_ip), socket.inet_aton(dst_ip),
    )
    udp = struct.pack(">HHHH", sport, dport, 8 + len(rtp), 0) + rtp
    return eth + ip + udp


def _pcapng_block(btype: int, body: bytes) -> bytes:
    total = 12 + len(body)
    return struct.pack("<II", btype, total) + body + struct.pack("<I", total)


def _pcapng_shb() -> bytes:
    return _pcapng_block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))


def _pcapng_idb() -> bytes:
    return _pcapng_block(0x00000001, struct.pack("<HHI", 1, 0, 65535))


def _pcapng_epb(frame: bytes, ts: int) -> bytes:
    caplen = len(frame)
    body = struct.pack(
        "<IIIII", 0, (ts >> 32) & 0xFFFFFFFF, ts & 0xFFFFFFFF, caplen, caplen
    )
    body += frame
    body += b"\x00" * ((4 - (len(body) % 4)) % 4)
    return _pcapng_block(0x00000006, body)


def _write_synthetic_capture(
    tmp_path,
    rtp_packets: list[bytes],
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    sport: int = 5033,
    dport: int = 5033,
) -> str:
    """Write a minimal pcapng carrying one target-flow RTP stream."""
    frames = [_eth_frame(src_ip, dst_ip, sport, dport, p) for p in rtp_packets]
    pcapng = _pcapng_shb() + _pcapng_idb()
    pcapng += b"".join(_pcapng_epb(f, i) for i, f in enumerate(frames))
    path = str(tmp_path / "synthetic_rtp.pcapng")
    with open(path, "wb") as fh:
        fh.write(pcapng)
    return path


def _synthetic_reader(pcap: str) -> RtpCaptureReader:
    return RtpCaptureReader(pcap, udp_port=5033, payload_type=8)


def test_out_of_order_packet_excluded_from_output(tmp_path) -> None:
    """F-01: a late/out-of-order packet must not leak into the accepted payload."""
    packets = [
        _rtp_packet(100, ssrc=0x1111),
        _rtp_packet(101, ssrc=0x1111),
        _rtp_packet(99, ssrc=0x1111),
        _rtp_packet(102, ssrc=0x1111),
    ]
    # Direct disposition proof: seq 99 is classified OUT_OF_ORDER (not a gap).
    tracker = RtpStreamTracker(expected_payload_type=8)
    results = [tracker.on_packet(parse_rtp_packet(p)) for p in packets]
    assert results[2].disposition == RtpDisposition.OUT_OF_ORDER
    assert results[2].disposition != RtpDisposition.DUPLICATE
    assert tracker.stats.out_of_order == 1

    pcap = _write_synthetic_capture(tmp_path, packets)
    reader = _synthetic_reader(pcap)
    stream = reader.read()

    seqs = [p.sequence_number for p in stream.packets]
    assert seqs == [100, 101, 102]
    assert 99 not in seqs
    assert stream.stats["out_of_order"] == 1

    # 99 must not be decoded to PCM.
    accepted_payload = b"".join(p.payload for p in stream.packets)
    assert (bytes([99]) * 160) not in accepted_payload
    pcm = reader.decode_pcm(stream)
    assert len(pcm) == 3 * 160 * 2  # exactly 3 packets, no invented PCM

    # 99 must not be emitted through the recording boundary (PCM frames).
    frames = reader.iter_frames(stream)
    assert all(f.sequence_number != 99 for f in frames)
    assert len(frames) == 3


def test_duplicate_packet_excluded_from_output(tmp_path) -> None:
    """F-01/regression: a duplicate packet is never emitted twice."""
    packets = [
        _rtp_packet(100, ssrc=0x1111),
        _rtp_packet(101, ssrc=0x1111),
        _rtp_packet(101, ssrc=0x1111),
        _rtp_packet(102, ssrc=0x1111),
    ]
    pcap = _write_synthetic_capture(tmp_path, packets)
    reader = _synthetic_reader(pcap)
    stream = reader.read()
    seqs = [p.sequence_number for p in stream.packets]
    assert seqs == [100, 101, 102]
    assert seqs.count(101) == 1
    assert stream.stats["duplicates"] == 1
    pcm = reader.decode_pcm(stream)
    assert len(pcm) == 3 * 160 * 2


def test_gap_packet_accepted_missing_not_invented(tmp_path) -> None:
    """F-01/regression: a gap emits the arriving packet, never invented samples."""
    packets = [
        _rtp_packet(100, ssrc=0x1111),
        _rtp_packet(101, ssrc=0x1111),
        _rtp_packet(105, ssrc=0x1111),
    ]
    pcap = _write_synthetic_capture(tmp_path, packets)
    reader = _synthetic_reader(pcap)
    stream = reader.read()
    seqs = [p.sequence_number for p in stream.packets]
    assert seqs == [100, 101, 105]
    assert stream.stats["sequence_gaps"] == 1
    assert stream.stats["packets_dropped"] == 3
    # No invented PCM for the 3 missing packets (102, 103, 104).
    pcm = reader.decode_pcm(stream)
    assert len(pcm) == 3 * 160 * 2


def test_multiple_ssrc_fails_closed(tmp_path) -> None:
    """F-02: a capture reader must fail closed rather than merge SSRCs."""
    packets = [
        _rtp_packet(100, ssrc=0xAAAA),
        _rtp_packet(101, ssrc=0xAAAA),
        _rtp_packet(102, ssrc=0xBBBB),
    ]
    pcap = _write_synthetic_capture(tmp_path, packets)
    reader = _synthetic_reader(pcap)
    with pytest.raises(ValueError) as excinfo:
        reader.read()
    msg = str(excinfo.value)
    assert "multiple SSRC" in msg
    assert str(0xAAAA) in msg and str(0xBBBB) in msg


def test_real_capture_single_ssrc_regression() -> None:
    """F-02 regression: the real capture is a single-SSRC stream and must pass."""
    reader = _reader()
    stream = reader.read()
    assert len({p.ssrc for p in stream.packets}) == 1
    assert stream.ssrc == GOLDEN["ssrc"]
    assert len(stream.packets) == GOLDEN["packet_count"]
    for packet in stream.packets:
        assert packet.payload_type == GOLDEN["payload_type"]
