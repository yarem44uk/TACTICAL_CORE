#!/usr/bin/env python3
"""Regression test for the WO-043 phantom metadata-SSRC bug.

Background (found in review of the universal ingest tool):
  A G.711/RTP source (`.118`) interleaves control/identity packets on the same
  audio flow. These packets set the RTP header-extension bit (X=1), carry a
  non-audio ASCII identifier (measured: ``Unit02@ATO.local``) in the extension,
  and have a ZERO-length audio payload. They are NOT transmissions.

  The naive payload slice ``rtp[12:]`` (fixed 12-byte header, ignoring CSRC and
  the extension) treated those 48 extension bytes as "audio", so the identity
  SSRC ``0xe181474b`` appeared as a phantom 5-packet transmission and inflated
  the per-source segment count by 1 (WO-043: 38 -> 39).

  The fix (in ``wo043_ingest.rtp_parse``) computes the header length correctly:
  ``hdrlen = 12 + cc*4; if ext: extlen = 4 + 4*ext_words; payload = rtp[hdrlen+extlen:]``.
  With that, the identity packet yields ``payload == b""``, so the P1 filter
  (``pt==8 and ssrc!=0 and len(payload)==160``) discards it.

This test builds those packets from raw bytes (no capture dependency) and asserts:
  1. ``rtp_parse`` computes the extension length and returns a zero-length payload.
  2. The naive slice (the bug) would have produced 48 bytes -- demonstrating the fix.
  3. The P1 filter rejects the identity packet.
  4. Feeding a synthetic pcap through ``collect()`` does NOT let the phantom SSRC
     inflate the per-flow SSRC set or the segment count.
"""

import os
import struct
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo043_ingest as ing  # noqa: E402


# --------------------------------------------------------------------------- #
# RTP packet builders (raw bytes) -- mirror the real identity packet exactly.
# --------------------------------------------------------------------------- #

IDENTITY_EXT_HDR = bytes.fromhex("0778000b")      # profile=0x0778, len_word=11
IDENTITY_EXT_DATA = (
    b"\x00\x02\x05\x0bUnit02@ATO.local"           # readable ASCII prefix
    + bytes.fromhex("e74dd7e544a34404b735c9dba106f5c70e1a22c700000000")
)
IDENTITY_SSRC = 0xE181474B


def _rtp_packet(seq, ts, ssrc, payload, *, ext_data=None, marker=0):
    """Build a single RTP v2 packet (CC=0). Returns raw bytes."""
    if ext_data is not None:
        # header (12) + 4-byte ext header + padded to 4-byte words.
        words = (len(ext_data) + 3) // 4
        ext = IDENTITY_EXT_HDR[:2] + struct.pack(">H", words) + ext_data
        ext = ext + b"\x00" * (words * 4 - len(ext_data))  # pad to word boundary
        b0 = 0x80 | 0x10        # version 2, X=1, CC=0
    else:
        ext = b""
        b0 = 0x80               # version 2, X=0, CC=0
    b1 = (marker << 7) | 8      # PT=8 (G.711 A-law)
    hdr = struct.pack(">BBHII", b0, b1, seq & 0xFFFF, ts & 0xFFFFFFFF,
                      ssrc & 0xFFFFFFFF)
    return hdr + ext + payload


def _audio_packet(seq, ts, ssrc, marker=0, nbytes=160):
    """A real 160-byte audio packet (deterministic non-zero payload)."""
    payload = bytes(((i * 37 + ssrc) & 0xFF) for i in range(nbytes))
    return _rtp_packet(seq, ts, ssrc, payload, marker=marker)


def _identity_packet(seq, ts=513162032, marker=1):
    """The phantom identity packet: X=1, zero-length audio payload."""
    return _rtp_packet(seq, ts, IDENTITY_SSRC, b"", ext_data=IDENTITY_EXT_DATA,
                       marker=marker)


def _eth_ip_udp(rtp, src, dst, sport, dport):
    """Wrap RTP bytes in Ethernet + IPv4 + UDP. Returns a full frame."""
    eth = b"\x01\x00\x5e\x00\x00\x01" + b"\x00\x11\x22\x33\x44\x55" + b"\x08\x00"
    udp_len = 8 + len(rtp)
    ip_len = 20 + udp_len
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, ip_len, 0, 0, 64, 17, 0,
                     bytes(int(x) for x in src.split(".")),
                     bytes(int(x) for x in dst.split(".")))
    udp = struct.pack(">HHHH", sport, dport, udp_len, 0) + rtp
    return eth + ip + udp


def _write_pcap(path, frames):
    """Write a legacy .pcap (linktype 1 = Ethernet, microsecond timestamps)."""
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, fr in enumerate(frames):
            ts_sec, ts_frac = divmod(i * 20000, 1_000_000)  # 20 ms apart
            f.write(struct.pack("<IIII", ts_sec, ts_frac, len(fr), len(fr)))
            f.write(fr)


# --------------------------------------------------------------------------- #
# 1 & 2: rtp_parse computes the extension length; naive slice would be wrong.
# --------------------------------------------------------------------------- #

def test_rtp_parse_strips_extension_identity():
    pkt = _identity_packet(seq=30634)
    r = ing.rtp_parse(pkt)
    assert r is not None
    assert r["ext"] == 1
    assert r["pt"] == 8
    assert r["ssrc"] == IDENTITY_SSRC
    # The whole 48-byte extension must be excluded from the payload.
    assert len(r["payload"]) == 0, (
        f"identity packet payload should be 0 bytes, got {len(r['payload'])}"
    )


def test_naive_slice_would_include_extension_as_audio():
    """Demonstrate the bug the fix prevents: rtp[12:] keeps the 48 ext bytes."""
    pkt = _identity_packet(seq=30634)
    naive = pkt[12:]
    assert len(naive) == 48, (
        f"naive rtp[12:] gives {len(naive)} 'audio' bytes -- this is the bug "
        f"that created the phantom SSRC"
    )
    # The corrected parser must NOT see those bytes as payload.
    assert len(ing.rtp_parse(pkt)["payload"]) != len(naive)


# --------------------------------------------------------------------------- #
# 3: P1 valid-audio filter rejects the identity packet.
# --------------------------------------------------------------------------- #

def test_p1_filter_rejects_identity_packet():
    pkt = _identity_packet(seq=30634)
    r = ing.rtp_parse(pkt)
    passes_p1 = (r["pt"] == 8 and r["ssrc"] != 0 and len(r["payload"]) == 160)
    assert not passes_p1, "zero-payload identity packet must be filtered out"


def test_p1_filter_accepts_real_audio_packet():
    pkt = _audio_packet(seq=100, ts=1000, ssrc=0x1234)
    r = ing.rtp_parse(pkt)
    assert r["pt"] == 8 and r["ssrc"] == 0x1234 and len(r["payload"]) == 160


# --------------------------------------------------------------------------- #
# 4: end-to-end through collect() -- phantom SSRC must not inflate count.
# --------------------------------------------------------------------------- #

def test_phantom_ssrc_does_not_inflate_segment_count():
    # Build a SHORT-SSRC flow on (.118:49755 -> 5011) with 3 real talkers.
    # Each real SSRC is a separate transmission; the identity SSRC rides the
    # same flow and must be excluded.
    frames = []
    flow = ("192.168.233.118", "239.233.58.10")
    real_ssrcs = [0x11111111, 0x22222222, 0x33333333]
    for si, ssrc in enumerate(real_ssrcs):
        for p in range(10):                        # 10 packets per talker
            fr = _eth_ip_udp(_audio_packet(seq=1000 + p, ts=1000 + p * 160,
                                           ssrc=ssrc, marker=(p == 0)),
                             flow[0], flow[1], 49755, 5011)
            frames.append(fr)
    # Interleave the phantom identity packets on the same flow.
    for p in range(5):
        fr = _eth_ip_udp(_identity_packet(seq=30634 + p),
                         flow[0], flow[1], 49755, 5011)
        frames.append(fr)
    # Add a DIFFERENT flow (other port) so flow detection has >=2 to separate.
    for p in range(5):
        fr = _eth_ip_udp(_audio_packet(seq=2000 + p, ts=2000 + p * 160,
                                       ssrc=0xAAAAAAAA),
                         flow[0], flow[1], 55683, 5022)
        frames.append(fr)

    with tempfile.TemporaryDirectory() as td:
        pcap = os.path.join(td, "synthetic.pcap")
        _write_pcap(pcap, frames)
        pkts, flow_audio, flow_rtp = ing.collect(pcap)

    # P1-filtered audio count = 30 real + 5 other-flow = 35.
    assert len(pkts) == 35, f"expected 35 P1 audio packets, got {len(pkts)}"

    # The identity SSRC must NOT be in the P1-filtered packet set.
    ident_ssrcs = {r["ssrc"] for r in pkts if r["ssrc"] == IDENTITY_SSRC}
    assert not ident_ssrcs, "phantom identity SSRC leaked into P1 audio packets"

    # Per-flow SSRC diversity must equal the real talker count (3), not 4.
    flow_key = ("192.168.233.118", 49755, 5011)
    flow_ssrcs = {r["ssrc"] for r in pkts
                  if (r["src"], r["sport"], r["dport"]) == flow_key}
    assert len(flow_ssrcs) == 3, (
        f"expected 3 real SSRCs on the flow, got {len(flow_ssrcs)} "
        f"(phantom SSRC inflated it)"
    )

    # Segment via the SHORT-SSRC path -> 3 transmissions, not 4.
    fpkts = [r for r in pkts if (r["src"], r["sport"], r["dport"]) == flow_key]
    groups = ing.seg_by_ssrc(fpkts)
    assert len(groups) == 3, (
        f"expected 3 transmissions, got {len(groups)} (phantom SSRC added one)"
    )


# --------------------------------------------------------------------------- #
# Legacy .pcap magic-variant regression (WO-043 corrective fix).
# parse_legacy_pcap must recognise all four standard legacy pcap endianness /
# resolution combos. The defect was a duplicated magic branch (BE-micro used the
# LE-nano magic), so BE-micro raised ValueError and LE-nano was misparsed as
# BE-micro. This test pins the correct behaviour for all four.
# --------------------------------------------------------------------------- #

_MAGIC_CASES = {
    "LE micro": (b"\xd4\xc3\xb2\xa1", "<", False),
    "BE micro": (b"\xa1\xb2\xc3\xd4", ">", False),
    "LE nano":  (b"\x4d\x3c\xb2\xa1", "<", True),
    "BE nano":  (b"\xa1\xb2\x3c\x4d", ">", True),
}


def _write_pcap_variant(path, magic, endian, nano, nframes=2, ts_sec=1000,
                        ts_frac=1234567, frame=b"\xde\xad\xbe\xef" * 16):
    """Write a legacy .pcap with the given magic / byte-order / resolution."""
    with open(path, "wb") as f:
        f.write(magic)
        # version 2.4, thiszone=0, sigfigs=0, snaplen=65535, network=1 (Ethernet)
        f.write(struct.pack(endian + "HHIIII", 2, 4, 0, 0, 65535, 1))
        for _ in range(nframes):
            f.write(struct.pack(endian + "IIII", ts_sec, ts_frac,
                                len(frame), len(frame)))
            f.write(frame)


def test_legacy_pcap_all_four_magic_variants():
    for name, (magic, endian, nano) in _MAGIC_CASES.items():
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "variant.pcap")
            _write_pcap_variant(p, magic, endian, nano)
            frames = list(ing.parse_legacy_pcap(p))
            assert len(frames) == 2, f"{name}: expected 2 frames, got {len(frames)}"
            for t, fr, lt in frames:
                assert fr == b"\xde\xad\xbe\xef" * 16, f"{name}: frame mismatch"
                assert lt == 1, f"{name}: linktype {lt} != 1"
                exp = 1000 + 1234567 / (1e9 if nano else 1e6)
                assert abs(t - exp) < 1e-9, f"{name}: time {t} != {exp}"


# --------------------------------------------------------------------------- #
# Minimal __main__ runner so this is runnable without pytest.
# --------------------------------------------------------------------------- #

def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
