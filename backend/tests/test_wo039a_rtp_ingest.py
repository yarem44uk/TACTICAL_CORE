"""WO-039-A tests — Real RTP / UDP multicast radio ingest.

These tests exercise the real radio transport (WO-039-A §15 TEST 1-10):

    UDP multicast -> RTP v2 parser -> RTP validation -> G.711 A-law decode
    -> PCM S16LE / 8000 Hz / mono -> existing source boundary

The production path is exercised at the real network/socket boundary (loopback
multicast), and the parser/decoder are validated against REAL packets captured
in ``test.pcapng``.  The WO-038 ``TCA1`` test-frame format is NOT used here —
this is the real RTP path (WO-039-A §3/§16).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import socket
import struct
import time

import pytest
from app.audio.alaw import alaw_decode_byte, alaw_to_pcm
from app.audio.audio_config import AudioConfig
from app.audio.rtp import RtpPacket, parse_rtp_packet, validate_rtp_packet
from app.audio.rtp_receiver import RtpPcmFrame, RtpReceiver
from app.audio.rtp_simulator import RtpSimulator, build_rtp_packet
from app.audio.rtp_stream import RtpDisposition, RtpStreamTracker
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.event_sources.config.source_definition import SourceDefinition

# ---------------------------------------------------------------------------
# Real RTP packets extracted from test.pcapng (main flow
# 172.19.4.118 -> 239.233.18.30:5033, PT=8, SSRC=536816391).
# ---------------------------------------------------------------------------
REAL_RTP_0 = bytes.fromhex(
    "800836d10002f1c01fff2b07d5d5d5d5d5d5d5d555d555d5d555d555d554d555d5d554d456d150d053d056d5d17f969d95ebfc94909b91eb9c94e2190e01149c80828eb581043519df0c330fe68c5a1f7a84b5ff6d19e49b7798b5b06709003588a4b1c235efbd9b0f0a06003634e183101d868a8cf613630e3d081310c685808eb3b9b78682941c0403021b1310046a9f85929695999c6d131d15671b49e913708685919a869f94919ed215"
)
REAL_RTP_1 = bytes.fromhex(
    "800836d20002f2601fff2b079c961f5885f51e1c151f78ff15051917071b171d197b951105db929d84808fb5b7b1b4b5b0b2b6b0b2b18098eb06343509323825232c2c282a282b2a2a2204a6aaaaaaa9a3a1a4b8beb9bc8c9681859a9f621d060d0a303d3c3e3f393b383e320db5a6a3afada3a1b8b1b58e849a80b6bebbbabeb680e0706271c14d10040f0809313c3c3d320eb4a3acaeafa3a7b08799858689b6bda5a6a6be8d92909c9896"
)
REAL_SSRC = 536816391
REAL_SEQ0 = 14033
REAL_TS0 = 192960

# A reserved loopback multicast group + per-test ports (no operational address).
GROUP = "239.255.2.0"
_PORT_COUNTER = {"n": 0}


def _unique_port() -> int:
    _PORT_COUNTER["n"] += 1
    return 41000 + _PORT_COUNTER["n"] * 2


def _rtp_config(port: int, **overrides) -> AudioConfig:
    """Build an RTP AudioConfig for the test loopback group."""
    defaults = {
        "multicast_address": GROUP,
        "multicast_port": port,
        "protocol": "rtp",
        "codec": "pcm_alaw",
        "payload_type": 8,
        "sample_rate": 8000,
        "channels": 1,
        "packetization_ms": 20,
        "source_name": "radio",
        "join_interface": "127.0.0.1",
        "network_interface": "AUTO",
        "frame_timeout": 0.2,
    }
    defaults.update(overrides)
    return AudioConfig(**defaults)


# ---------------------------------------------------------------------------
# TEST 1 / TEST 2 — RTP header parse + PT=8
# ---------------------------------------------------------------------------


def test_rtp_header_real_packet_parses() -> None:
    packet = parse_rtp_packet(REAL_RTP_0)
    assert packet.version == 2
    assert packet.padding is False
    assert packet.extension is False
    assert packet.csrc_count == 0
    assert packet.marker is False
    assert packet.payload_type == 8
    assert packet.sequence_number == REAL_SEQ0
    assert packet.timestamp == REAL_TS0
    assert packet.ssrc == REAL_SSRC
    assert packet.header_length == 12
    assert packet.payload_len == 160


def test_rtp_payload_type_8_accepted() -> None:
    validate_rtp_packet(parse_rtp_packet(REAL_RTP_0), expected_payload_type=8)


def test_rtp_wrong_payload_type_rejected() -> None:
    packet = parse_rtp_packet(REAL_RTP_0)
    with pytest.raises(ValueError):
        validate_rtp_packet(packet, expected_payload_type=7)


def test_rtp_header_length_with_csrc_extension_padding() -> None:
    # A packet with 2 CSRC entries (12 + 8 = 20-byte header).
    header = struct.pack(">BBHII", (2 << 6) | 2, 8, 1, 160, REAL_SSRC)
    csrcs = struct.pack(">II", 0x11111111, 0x22222222)
    raw = header + csrcs + b"\x55" * 160
    pkt = parse_rtp_packet(raw)
    assert pkt.csrc_count == 2
    assert pkt.csrcs == (0x11111111, 0x22222222)
    assert pkt.header_length == 20
    assert pkt.payload_len == 160

    # A packet with a header extension (1 32-bit word).
    ext_header = struct.pack(">BBHII", (2 << 6) | (1 << 4), 8, 1, 160, REAL_SSRC)
    ext = struct.pack(">HH", 0xBEDE, 1) + b"\x00" * 4
    raw_ext = ext_header + ext + b"\x55" * 160
    pkt_ext = parse_rtp_packet(raw_ext)
    assert pkt_ext.extension is True
    assert pkt_ext.header_length == 20
    assert pkt_ext.payload_len == 160

    # A packet with padding (P bit set, last byte is the pad length).
    # 160 real payload bytes + 3 filler + 1 pad-length byte (4 padding bytes).
    pad_payload = b"\x55" * 160 + b"\x00" * 3 + b"\x04"
    pad_header = struct.pack(">BBHII", (2 << 6) | (1 << 5), 8, 1, 160, REAL_SSRC)
    raw_pad = pad_header + pad_payload
    pkt_pad = parse_rtp_packet(raw_pad)
    assert pkt_pad.padding is True
    assert pkt_pad.payload_len == 160
    assert pkt_pad.payload == b"\x55" * 160


def test_rtp_malformed_raises() -> None:
    for bad in [b"", b"\x80", b"\x80\x08", b"\x80\x08\x00\x00", bytes(11)]:
        with pytest.raises(ValueError):
            parse_rtp_packet(bad)
    # Bad version.
    with pytest.raises(ValueError):
        parse_rtp_packet(bytes([0x40, 8]) + bytes(10))
    # Padding length exceeding payload.
    with pytest.raises(ValueError):
        parse_rtp_packet(
            struct.pack(">BBHII", (2 << 6) | (1 << 5), 8, 1, 160, REAL_SSRC)
            + b"\x55" * 3
            + b"\xFF"
        )


# ---------------------------------------------------------------------------
# TEST 3 — PCMA / G.711 A-law decode
# ---------------------------------------------------------------------------


def test_alaw_decode_known_values() -> None:
    # Reference values (validated against ffmpeg's alaw decoder).
    assert alaw_decode_byte(0x55) == -8
    assert alaw_decode_byte(0xD5) == 8
    assert alaw_decode_byte(0x00) == -5504
    assert alaw_decode_byte(0x7F) == -848
    assert alaw_decode_byte(0x80) == 5504
    assert alaw_decode_byte(0xFF) == 848


def test_alaw_to_pcm_deterministic() -> None:
    payload = bytes([0x55, 0xD5, 0x00, 0x7F, 0x80, 0xFF])
    pcm = alaw_to_pcm(payload)
    assert len(pcm) == len(payload) * 2
    # Same input -> same output.
    assert pcm == alaw_to_pcm(payload)
    samples = struct.unpack("<" + "h" * len(payload), pcm)
    assert list(samples) == [-8, 8, -5504, -848, 5504, 848]


def test_alaw_real_payload_decodes_to_pcm() -> None:
    packet = parse_rtp_packet(REAL_RTP_0)
    pcm = alaw_to_pcm(packet.payload)
    # 160 A-law bytes -> 160 samples -> 320 PCM bytes.
    assert len(pcm) == 160 * 2
    samples = struct.unpack("<160h", pcm)
    assert len(samples) == 160
    assert len(set(samples)) > 1  # non-silent content decodes to varied PCM


# ---------------------------------------------------------------------------
# TEST 4 — Sequence tracking: normal / duplicate / gap / out-of-order
# ---------------------------------------------------------------------------


def _pkt(seq: int, ts: int = 0, ssrc: int = REAL_SSRC) -> RtpPacket:
    raw = build_rtp_packet(
        payload_type=8, sequence_number=seq, timestamp=ts, ssrc=ssrc,
        payload=b"\x55" * 160,
    )
    return parse_rtp_packet(raw)


def test_sequence_normal_duplicate_gap_out_of_order() -> None:
    tracker = RtpStreamTracker(expected_payload_type=8)
    # Initial.
    assert tracker.on_packet(_pkt(100, 0)).disposition == RtpDisposition.INITIAL
    # Normal in-order.
    assert tracker.on_packet(_pkt(101, 160)).disposition == RtpDisposition.IN_ORDER
    # Duplicate (same seq as last).
    assert tracker.on_packet(_pkt(101, 160)).disposition == RtpDisposition.DUPLICATE
    # Gap (skip 102,103,104 -> land on 105): 3 lost.
    result = tracker.on_packet(_pkt(105, 160 * 5))
    assert result.disposition == RtpDisposition.GAP
    assert result.dropped == 3
    # Out-of-order (late packet, seq 103 < last 105).
    assert tracker.on_packet(_pkt(103, 160 * 3)).disposition == RtpDisposition.OUT_OF_ORDER

    stats = tracker.stats
    assert stats.packets_received == 3  # initial + in-order + gap (out-of-order not accepted)
    assert stats.duplicates == 1
    assert stats.sequence_gaps == 1
    assert stats.out_of_order == 1
    assert stats.packets_dropped == 3
    assert stats.current_ssrc == REAL_SSRC
    assert stats.last_sequence == 105


def test_sequence_16bit_wraparound() -> None:
    tracker = RtpStreamTracker()
    assert tracker.on_packet(_pkt(65535, 0)).disposition == RtpDisposition.INITIAL
    # Wrap to 0.
    assert tracker.on_packet(_pkt(0, 160)).disposition == RtpDisposition.IN_ORDER


# ---------------------------------------------------------------------------
# TEST 5 — Timestamp progression
# ---------------------------------------------------------------------------


def test_simulator_timestamp_progression() -> None:
    cfg = _rtp_config(1)
    sim = RtpSimulator(cfg, ssrc=REAL_SSRC)
    p0 = sim.build(payload=b"\x55" * 160)
    p1 = sim.build(payload=b"\x55" * 160)
    sim.close()
    assert p0.timestamp == 0
    assert p1.timestamp == 160  # +160 samples per packet
    assert p0.sequence_number == 0
    assert p1.sequence_number == 1


def test_rtp_timestamp_preserved_through_tracker() -> None:
    tracker = RtpStreamTracker()
    tracker.on_packet(_pkt(1, ts=192960))
    tracker.on_packet(_pkt(2, ts=193120))
    assert tracker.stats.last_timestamp == 193120


# ---------------------------------------------------------------------------
# TEST 6 — SSRC tracking + safe transition
# ---------------------------------------------------------------------------


def test_ssrc_tracking_and_transition() -> None:
    tracker = RtpStreamTracker()
    assert tracker.on_packet(_pkt(1, 0, ssrc=0xAAAA)).disposition == RtpDisposition.INITIAL
    assert tracker.on_packet(_pkt(2, 160, ssrc=0xAAAA)).disposition == RtpDisposition.IN_ORDER
    # SSRC change -> transition, state reset, stats preserved.
    result = tracker.on_packet(_pkt(1, 0, ssrc=0xBBBB))
    assert result.disposition == RtpDisposition.SSRC_CHANGE
    assert tracker.stats.current_ssrc == 0xBBBB
    assert tracker.stats.ssrc_transitions == 1
    assert tracker.stats.packets_received == 3
    # New stream baseline resets so seq 1 is now IN_ORDER on the new SSRC.
    assert tracker.on_packet(_pkt(2, 160, ssrc=0xBBBB)).disposition == RtpDisposition.IN_ORDER


# ---------------------------------------------------------------------------
# TEST 7 — Malformed RTP does not crash the receiver
# ---------------------------------------------------------------------------


def test_malformed_packets_do_not_crash_receiver() -> None:
    port = _unique_port()
    cfg = _rtp_config(port)
    frames: list[RtpPcmFrame] = []
    receiver = RtpReceiver(cfg, on_pcm=frames.append)
    receiver.start()
    try:
        _wait_for_bind(receiver)
        # Send malformed / non-RTP datagrams directly to the port.
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Send on the loopback interface so the datagrams reach the receiver's
        # 127.0.0.1 multicast membership.
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sender.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1")
        )
        for bad in [b"", b"NOT-A-PACKET", b"\x80\x08", bytes(10)]:
            sender.sendto(bad, (GROUP, port))
        # Send a valid RTP packet too.
        sim = RtpSimulator(cfg, ssrc=REAL_SSRC)
        sim.send(payload=b"\x55" * 160)
        sim.close()
        sender.close()
        time.sleep(0.5)
        assert receiver.is_active() is True
        assert len(frames) >= 1
        snap = receiver.snapshot()
        assert snap["malformed"] >= 3
        assert snap["packets_received"] >= 1
    finally:
        receiver.stop()


# ---------------------------------------------------------------------------
# TEST 8 — Real PCAP payload processed by the parser/decoder
# ---------------------------------------------------------------------------


def _find_pcap() -> str | None:
    candidates = [
        os.environ.get("WO039_PCAP"),
        "/opt/data/uploads/1788366527-b0f355db/test.pcapng",
        os.path.join(os.path.dirname(__file__), "..", "..", "test.pcapng"),
        "test.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _iter_pcap_rtp(path: str):
    """Parse a pcapng and yield RTP packets from the real radio flow."""
    with open(path, "rb") as fh:
        data = fh.read()
    i = 0
    iface_tsresol: list[int] = []
    while i + 12 <= len(data):
        btype, blen = struct.unpack_from("<II", data, i)
        if btype == 0x0A0D0D0A:
            i += blen
            continue
        if btype == 0x00000001:
            tsresol = 6
            j = i + 16
            end = i + blen - 4
            while j + 4 <= end:
                oc, ol = struct.unpack_from("<HH", data, j)
                if oc == 0:
                    break
                v = data[j + 4 : j + 4 + ol]
                if oc == 9 and ol >= 1:
                    b = v[0]
                    tsresol = 2 ** (b & 0x7F) if (b & 0x80) else 10 ** b
                j += 4 + ol + ((4 - (ol % 4)) % 4)
            iface_tsresol.append(tsresol)
            i += blen
            continue
        if btype == 0x00000006:
            ifid, _th, _tl, caplen, _origlen = struct.unpack_from("<IIIII", data, i + 8)
            pkt = data[i + 28 : i + 28 + caplen]
            if ifid < len(iface_tsresol):
                # Extract UDP -> RTP (the radio flow: sport/dport 5033).
                rtp = _extract_udp_rtp(pkt)
                if rtp is not None:
                    yield rtp
            i += blen
            continue
        if blen < 12:
            break
        i += blen


def _extract_udp_rtp(pkt: bytes) -> bytes | None:
    if len(pkt) < 14:
        return None
    eth_type = struct.unpack_from(">H", pkt, 12)[0]
    off = 14
    if eth_type == 0x8100:
        eth_type = struct.unpack_from(">H", pkt, 16)[0]
        off = 18
    if eth_type != 0x0800:
        return None
    ihl = (pkt[off] & 0x0F) * 4
    if pkt[off + 9] != 17:
        return None
    sport, dport = struct.unpack_from(">HH", pkt, off + ihl)
    if sport != 5033 or dport != 5033:
        return None
    return pkt[off + ihl + 8 :]


@pytest.mark.skipif(
    _find_pcap() is None,
    reason="test.pcapng not found (real PCAP fixture is not committed)",
)
def test_real_pcap_payload_parsed_and_decoded() -> None:
    path = _find_pcap()
    assert path is not None
    count = 0
    for rtp in _iter_pcap_rtp(path):
        packet = parse_rtp_packet(rtp)
        validate_rtp_packet(packet, expected_payload_type=8)
        assert packet.payload_len == 160
        pcm = alaw_to_pcm(packet.payload)
        assert len(pcm) == 320
        count += 1
        if count >= 100:
            break
    assert count >= 1, "no radio RTP packets found in pcap"


# ---------------------------------------------------------------------------
# TEST 9 — Real multicast loopback (UDP -> RTP -> A-law -> PCM)
# ---------------------------------------------------------------------------


def _wait_for_frames(frames: list, n: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(frames) >= n:
            return True
        time.sleep(0.05)
    return False


def _wait_for_bind(receiver: RtpReceiver, timeout: float = 2.0) -> None:
    """Wait for the receiver thread to bind its socket before sending.

    Avoids a startup race where multicast datagrams are emitted before the
    receiver has joined the group and would be dropped by the kernel.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if receiver.is_bound():
            return
        time.sleep(0.02)
    time.sleep(0.05)


def test_real_multicast_loopback_rtp_to_pcm() -> None:
    port = _unique_port()
    cfg = _rtp_config(port, join_interface="127.0.0.1", network_interface="AUTO")
    frames: list[RtpPcmFrame] = []
    receiver = RtpReceiver(cfg, on_pcm=frames.append)
    receiver.start()
    sim: RtpSimulator | None = None
    try:
        _wait_for_bind(receiver)
        sim = RtpSimulator(cfg, ssrc=REAL_SSRC)
        # Send 5 real A-law packets (160 samples each).
        for _ in range(5):
            sim.send(payload=b"\x55" * 160)
        assert _wait_for_frames(frames, 5), f"got {len(frames)} frames"
        assert len(frames) >= 5
        for frame in frames:
            assert frame.ssrc == REAL_SSRC
            assert frame.payload_type == 8
            assert frame.sample_rate == 8000
            assert frame.channels == 1
            assert len(frame.pcm) == 320  # 160 samples * 2 bytes
        snap = receiver.snapshot()
        assert snap["running"] is True
        assert snap["packets_received"] >= 5
        assert snap["current_ssrc"] == REAL_SSRC
        assert snap["codec"] == "pcm_alaw"
        assert snap["sample_rate"] == 8000
        assert snap["multicast_address"] == GROUP
        assert snap["udp_port"] == port
    finally:
        receiver.stop()
        if sim is not None:
            sim.close()


def test_multicast_sequence_gap_detected_live() -> None:
    port = _unique_port()
    cfg = _rtp_config(port, join_interface="127.0.0.1")
    frames: list[RtpPcmFrame] = []
    receiver = RtpReceiver(cfg, on_pcm=frames.append)
    receiver.start()
    sim: RtpSimulator | None = None
    try:
        _wait_for_bind(receiver)
        sim = RtpSimulator(cfg, ssrc=REAL_SSRC)
        # Send seq 0,1 then skip to seq 10 (gap of 8).
        sim.send(payload=b"\x55" * 160, seq=0, ts=0)
        sim.send(payload=b"\x55" * 160, seq=1, ts=160)
        sim.send(payload=b"\x55" * 160, seq=10, ts=1600)
        assert _wait_for_frames(frames, 3)
        snap = receiver.snapshot()
        assert snap["sequence_gaps"] >= 1
        assert snap["packets_dropped"] >= 8
    finally:
        receiver.stop()
        if sim is not None:
            sim.close()


# ---------------------------------------------------------------------------
# TEST 10 — Multiple independent multicast sources
# ---------------------------------------------------------------------------


def test_multiple_sources_independent_state() -> None:
    port_a = _unique_port()
    port_b = _unique_port()
    group_a = "239.255.2.1"
    group_b = "239.255.2.2"
    cfg_a = _rtp_config(port_a, multicast_address=group_a, join_interface="127.0.0.1")
    cfg_b = _rtp_config(port_b, multicast_address=group_b, join_interface="127.0.0.1")
    frames_a: list[RtpPcmFrame] = []
    frames_b: list[RtpPcmFrame] = []
    rx_a = RtpReceiver(cfg_a, on_pcm=frames_a.append)
    rx_b = RtpReceiver(cfg_b, on_pcm=frames_b.append)
    rx_a.start()
    rx_b.start()
    sim_a: RtpSimulator | None = None
    sim_b: RtpSimulator | None = None
    try:
        _wait_for_bind(rx_a)
        _wait_for_bind(rx_b)
        sim_a = RtpSimulator(cfg_a, ssrc=0xAAAA)
        sim_b = RtpSimulator(cfg_b, ssrc=0xBBBB)
        # Independent sources, independent SSRC/sequence state.
        sim_a.send(payload=b"\x55" * 160, seq=1, ts=0)
        sim_a.send(payload=b"\x55" * 160, seq=2, ts=160)
        sim_b.send(payload=b"\x55" * 160, seq=100, ts=0)
        sim_b.send(payload=b"\x55" * 160, seq=101, ts=160)

        assert _wait_for_frames(frames_a, 2)
        assert _wait_for_frames(frames_b, 2)

        snap_a = rx_a.snapshot()
        snap_b = rx_b.snapshot()
        assert snap_a["current_ssrc"] == 0xAAAA
        assert snap_b["current_ssrc"] == 0xBBBB
        assert snap_a["packets_received"] == 2
        assert snap_b["packets_received"] == 2
        assert snap_a["last_sequence"] == 2
        assert snap_b["last_sequence"] == 101
        # Each source keeps its own sequence/SSRC state (no cross-talk).
        assert snap_a["current_ssrc"] != snap_b["current_ssrc"]
    finally:
        rx_a.stop()
        rx_b.stop()
        if sim_a is not None:
            sim_a.close()
        if sim_b is not None:
            sim_b.close()


# ---------------------------------------------------------------------------
# Existing source-adapter boundary (RTP mode reaches read_events)
# ---------------------------------------------------------------------------


def test_rtp_adapter_no_packet_level_stt() -> None:
    """WO-041-CORR F-02 — RTP packets MUST NOT produce packet-level STT events.

    Without a recorder / STT worker the RTP adapter accumulates no audio and
    produces NO event from an individual RTP packet (fail-closed, no fake
    transcript).  The production STT boundary is the finalized WAV master, never
    a per-packet deterministic transcriber.
    """
    port = _unique_port()
    definition = SourceDefinition(
        name="radio-rtp",
        adapter_type="multicast_audio",
        config={
            "protocol": "rtp",
            "multicast_address": GROUP,
            "multicast_port": port,
            "codec": "pcm_alaw",
            "payload_type": 8,
            "sample_rate": 8000,
            "channels": 1,
            "source_name": "radio",
            "join_interface": "127.0.0.1",
        },
    )
    adapter = MulticastAudioSourceAdapter(definition)
    adapter.start()
    sim: RtpSimulator | None = None
    try:
        # Wait for the RTP receiver to bind before emitting packets.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            receiver = getattr(adapter, "_receiver", None)
            if receiver is not None and receiver.is_bound():
                break
            time.sleep(0.02)
        sim = RtpSimulator(adapter._config, ssrc=REAL_SSRC)
        sim.send(payload=b"\x55" * 160)
        sim.send(payload=b"\x55" * 160)
        # Give the receiver time to process the packets.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            time.sleep(0.05)
        raw_events = adapter.read_events()
        # No packet-level transcript/STT event is produced from RTP packets.
        assert raw_events == [], (
            "RTP packets must not produce per-packet STT events (WO-041-CORR F-02)"
        )
        # The adapter stays alive and healthy.
        assert adapter.health() is True
        assert adapter.is_running is True
    finally:
        adapter.stop()
        if sim is not None:
            sim.close()


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_audio_config_rtp_defaults() -> None:
    cfg = AudioConfig.from_source_definition(
        {"protocol": "rtp", "multicast_address": "239.233.18.30", "multicast_port": 5033}
    )
    assert cfg.is_rtp is True
    assert cfg.codec == "pcm_alaw"
    assert cfg.payload_type == 8
    assert cfg.sample_rate == 8000
    assert cfg.channels == 1
    assert cfg.packetization_ms == 20
    assert cfg.network_interface == "AUTO"


def test_audio_config_tca1_preserved() -> None:
    cfg = AudioConfig.from_source_definition({})
    assert cfg.is_rtp is False
    assert cfg.codec is None
    assert cfg.sample_rate == 16000


# ---------------------------------------------------------------------------
# TEST 11 — Receiver lifecycle: a terminal failure must clear the running
# state (WO-039-A reliability fix).  A failed source must NOT report
# is_active()/snapshot()['running'] == True, and start() must be able to
# restart it.  Regression for the defect where _running stayed True after a
# bind failure / recv error, so is_active() lied and start() became a no-op.
# ---------------------------------------------------------------------------


def test_receiver_bind_failure_clears_running_state_and_restarts() -> None:
    """A multicast bind failure must terminate the thread and clear _running.

    The port is occupied WITHOUT SO_REUSEADDR so the receiver's ``bind()`` is
    rejected (EADDRINUSE) — a real, deterministic terminal receiver failure.
    """
    port = _unique_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    receiver: RtpReceiver | None = None
    try:
        blocker.bind(("", port))
        cfg = _rtp_config(port)
        receiver = RtpReceiver(cfg, on_pcm=lambda frame: None)
        receiver.start()

        deadline = time.time() + 3.0
        while time.time() < deadline and receiver.is_active():
            time.sleep(0.02)

        # The thread terminated and the running state must reflect it.
        assert receiver.is_active() is False
        snap = receiver.snapshot()
        assert snap["running"] is False
        assert "bind failed" in (snap["last_error"] or "")
        assert receiver.is_bound() is False
        # No receiver thread is leaked.
        thread = getattr(receiver, "_thread", None)
        assert thread is not None and thread.is_alive() is False

        # Release the port: the receiver must be restartable.
        blocker.close()
        time.sleep(0.05)
        receiver.start()
        deadline = time.time() + 3.0
        while time.time() < deadline and not receiver.is_bound():
            time.sleep(0.02)
        assert receiver.is_bound() is True
        assert receiver.is_active() is True
    finally:
        blocker.close()
        if receiver is not None:
            receiver.stop()


def test_receiver_recv_error_clears_running_state_and_restarts() -> None:
    """A socket recv error after a successful bind must terminate the thread,
    clean up the socket, and clear _running so the source can restart."""
    port = _unique_port()
    cfg = _rtp_config(port)
    receiver = RtpReceiver(cfg, on_pcm=lambda frame: None)
    receiver.start()
    try:
        _wait_for_bind(receiver)
        assert receiver.is_active() is True

        # Force a real recv error by closing the bound socket underneath the
        # receiver; the blocked recvfrom then raises EBADF through the actual
        # receiver lifecycle (no _running mutation in the test).
        sock = getattr(receiver, "_socket", None)
        assert sock is not None
        sock.close()

        deadline = time.time() + 3.0
        while time.time() < deadline and receiver.is_active():
            time.sleep(0.02)

        assert receiver.is_active() is False
        snap = receiver.snapshot()
        assert snap["running"] is False
        assert "recv failed" in (snap["last_error"] or "")
        # The receiver's finally block cleared the socket reference.
        assert receiver.is_bound() is False
        thread = getattr(receiver, "_thread", None)
        assert thread is not None and thread.is_alive() is False

        # Restart must be possible after the terminal recv error.
        receiver.start()
        deadline = time.time() + 3.0
        while time.time() < deadline and not receiver.is_bound():
            time.sleep(0.02)
        assert receiver.is_bound() is True
        assert receiver.is_active() is True
    finally:
        receiver.stop()
