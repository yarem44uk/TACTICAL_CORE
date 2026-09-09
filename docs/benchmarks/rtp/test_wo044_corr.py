#!/usr/bin/env python3
"""WO-044-CORR-01 regression tests: AUTO cold-start + socket source-flow isolation.

Two defects were corrected in wo043_live.py:

  FINDING 1 — AUTO cold-start over-split. The first transmission of a SHORT-SSRC
  flow was split by an internal wall-gap before a second SSRC was observed
  (AUTO gave 3 transmissions where offline/SHORT-SSRC gave 2). Fixed by deferring
  the first transmission's boundary decision until the flow shape is known.

  FINDING 2 — socket/multicast source-flow isolation. The live socket mode keyed
  the segmentation state by (group, port) alone, so two talkers sharing one
  multicast group:port (e.g. .10:5011 and .118:49755 both -> 239.x:5011) shared a
  single segmenter and mixed their SSRC state. Fixed by keying the per-source
  segmenter by the full flow (src_ip, sport, dport) via FlowManager.

These tests prove the OUTPUT (segment count + SSRC identity), not just internal
dict contents, so they fail if either fix is reverted.

Runs standalone:  python3 test_wo044_corr.py
"""

import csv
import os
import struct
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo043_live as live  # noqa: E402


# --------------------------------------------------------------------------- #
# Packet / pcap builders
# --------------------------------------------------------------------------- #

def _udp_rtp(sport, dport, seq, ts, ssrc, payload=None, src_ip=None):
    """Build a full UDP datagram (8-byte UDP header + RTP). The live receiver's
    rtp_parse_from_udp requires the 8-byte UDP header; a bare RTP packet would
    slice at offset 8 into the middle of the RTP header and be rejected."""
    if payload is None:
        payload = bytes(((i * 37 + ssrc) & 0xFF) for i in range(160))
    rtp = struct.pack(">BBHII", 0x80, 8, seq & 0xFFFF, ts & 0xFFFFFFFF,
                      ssrc & 0xFFFFFFFF) + payload
    udp = struct.pack(">HHHH", sport, dport, 8 + len(rtp), 0) + rtp
    return udp


def _eth_ip_udp_frame(udp, src_ip, dst_ip, sport, dport):
    """Wrap a UDP datagram in Ethernet + IPv4 for the offline pcap path."""
    eth = b"\x01\x00\x5e\x00\x00\x01" + b"\x00\x11\x22\x33\x44\x55" + b"\x08\x00"
    udp_len = len(udp)
    ip_len = 20 + udp_len
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, ip_len, 0, 0, 64, 17, 0,
                     bytes(int(x) for x in src_ip.split(".")),
                     bytes(int(x) for x in dst_ip.split(".")))
    return eth + ip + udp


def _write_pcap(path, frames):
    """Write a legacy LE-micro .pcap (linktype 1 = Ethernet)."""
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, fr in enumerate(frames):
            ts_sec, ts_frac = divmod(i * 20000, 1_000_000)
            f.write(struct.pack("<IIII", ts_sec, ts_frac, len(fr), len(fr)))
            f.write(fr)


# --------------------------------------------------------------------------- #
# FINDING 1 — AUTO cold-start
# --------------------------------------------------------------------------- #

def _build_coldstart_pcap(path):
    """SSRC A x5, 2.0 s gap, SSRC A x5, SSRC B x5 (one flow, default gap 1.0)."""
    records = []
    ts, seq = 1000, 1000
    src_ip = "192.168.233.118"
    dst_ip = "239.233.58.10"
    for i in range(5):
        udp = _udp_rtp(49755, 5011, seq + i, ts + i * 160, 0xAAAAAAAA)
        records.append((1000.000 + i * 0.020,
                        _eth_ip_udp_frame(udp, src_ip, dst_ip, 49755, 5011)))
    ts += 5 * 160; seq += 5
    for i in range(5):
        udp = _udp_rtp(49755, 5011, seq + i, ts + i * 160, 0xAAAAAAAA)
        records.append((1002.080 + i * 0.020,
                        _eth_ip_udp_frame(udp, src_ip, dst_ip, 49755, 5011)))
    ts += 5 * 160; seq += 5
    for i in range(5):
        udp = _udp_rtp(49755, 5011, seq + i, ts + i * 160, 0xBBBBBBBB)
        records.append((1004.000 + i * 0.020,
                        _eth_ip_udp_frame(udp, src_ip, dst_ip, 49755, 5011)))
    _write_pcap(path, [r[1] for r in records])


def test_auto_coldstart_no_oversplit():
    with tempfile.TemporaryDirectory() as td:
        pcap = os.path.join(td, "coldstart.pcap")
        _build_coldstart_pcap(pcap)

        out_auto = os.path.join(td, "auto")
        live.replay(pcap, out_auto, gap=1.0, force_shape=None)  # AUTO
        auto_manifest = []
        for root, _, files in os.walk(out_auto):
            for fn in files:
                if fn.startswith("live_manifest_"):
                    auto_manifest += list(csv.DictReader(open(os.path.join(root, fn))))

        # SSRC A (0xaaaaaaaa) must be ONE logical transmission (10 pkts), NOT 2.
        a_segs = [m for m in auto_manifest if m["ssrc"] == hex(0xAAAAAAAA)]
        b_segs = [m for m in auto_manifest if m["ssrc"] == hex(0xBBBBBBBB)]
        assert len(auto_manifest) == 2, (
            f"AUTO cold-start should give 2 transmissions, got {len(auto_manifest)} "
            f"(over-split of first SHORT-SSRC transmission)")
        assert len(a_segs) == 1, (
            f"SSRC A must be one logical transmission, got {len(a_segs)}")
        assert a_segs[0]["n_pkts"] == "10", (
            f"SSRC A should have 10 packets, got {a_segs[0]['n_pkts']}")
        assert len(b_segs) == 1 and b_segs[0]["n_pkts"] == "5"


def test_auto_coldstart_matches_short_ssrc():
    with tempfile.TemporaryDirectory() as td:
        pcap = os.path.join(td, "coldstart.pcap")
        _build_coldstart_pcap(pcap)

        live.replay(pcap, os.path.join(td, "auto"), gap=1.0, force_shape=None)
        live.replay(pcap, os.path.join(td, "ss"), gap=1.0, force_shape="SHORT-SSRC")

        def count(tag):
            total = 0
            for root, _, files in os.walk(os.path.join(td, tag)):
                for fn in files:
                    if fn.startswith("live_manifest_"):
                        total += len(list(csv.DictReader(open(os.path.join(root, fn)))))
            return total

        assert count("auto") == count("ss") == 2, (
            f"AUTO cold-start must equal SHORT-SSRC (2), got auto={count('auto')} "
            f"ss={count('ss')}")


# --------------------------------------------------------------------------- #
# FINDING 2 — socket / multicast source-flow isolation
# --------------------------------------------------------------------------- #

def _build_two_flows_on_one_group():
    """Return a list of (src_ip, sport, dport, rtp_dict) for two talkers that
    both send into the SAME multicast group:port (239.233.58.10:5011).

      Flow A: .10:5011 -> :5011  single SSRC 0xAAAA, CONTINUOUS (2 transmissions
              separated by a >1 s wall-gap).
      Flow B: .118:49755 -> :5011 two SSRCs 0xBBBB/0xCCCC, SHORT-SSRC.

    If the segmenter were keyed by (group, port) alone, A and B would share one
    segmenter, their SSRC sets would mix (len>=2 => SHORT-SSRC), and A's two
    transmissions would collapse into one.
    """
    packets = []
    # Flow A: 5 pkts SSRC A, 1.5 s gap, 5 pkts SSRC A  (continuous, 2 segments)
    ts, seq = 1000, 1000
    for i in range(5):
        udp = _udp_rtp(5011, 5011, seq + i, ts + i * 160, 0xAAAA)
        r = live.rtp_parse_from_udp(udp, 1000.000 + i * 0.020)
        packets.append(("192.168.233.10", 5011, 5011, r))
    ts += 5 * 160; seq += 5
    for i in range(5):
        udp = _udp_rtp(5011, 5011, seq + i, ts + i * 160, 0xAAAA)
        r = live.rtp_parse_from_udp(udp, 1001.580 + i * 0.020)  # gap 1.58 s
        packets.append(("192.168.233.10", 5011, 5011, r))
    # Flow B: SSRC 0xBBBB x5, then SSRC 0xCCCC x5 (short-ssrc, 2 segments)
    ts, seq = 5000, 5000
    for i in range(5):
        udp = _udp_rtp(49755, 5011, seq + i, ts + i * 160, 0xBBBB)
        r = live.rtp_parse_from_udp(udp, 1000.000 + i * 0.020)
        packets.append(("192.168.233.118", 49755, 5011, r))
    ts += 5 * 160; seq += 5
    for i in range(5):
        udp = _udp_rtp(49755, 5011, seq + i, ts + i * 160, 0xCCCC)
        r = live.rtp_parse_from_udp(udp, 1002.000 + i * 0.020)
        packets.append(("192.168.233.118", 49755, 5011, r))
    return packets


def test_socket_source_flow_isolation():
    packets = _build_two_flows_on_one_group()
    with tempfile.TemporaryDirectory() as td:
        fm = live.FlowManager(os.path.join(td, "out"), gap=1.0)
        group = "239.233.58.10"
        # Route each datagram to its per-source-flow segmenter, exactly as the
        # MulticastReceiver does.
        for src_ip, sport, dport, r in packets:
            seg = fm.get_or_create(src_ip, sport, dport, group)
            seg.feed(r)
        fm.write_all_manifests()

        # Two independent source-flows on the same group:port.
        assert len(fm) == 2, (
            f"two talkers on one group:port must yield TWO segmenters, got {len(fm)} "
            f"(reverted to one segmenter per group/port?)")
        keys = set(fm.segmenters.keys())
        assert ("192.168.233.10", 5011, 5011) in keys
        assert ("192.168.233.118", 49755, 5011) in keys

        seg_a = fm.segmenters[("192.168.233.10", 5011, 5011)]
        seg_b = fm.segmenters[("192.168.233.118", 49755, 5011)]
        # State must be independent.
        assert seg_a is not seg_b
        assert seg_a.ssrcs == {0xAAAA}, f"Flow A SSRC set {seg_a.ssrcs} not isolated"
        assert seg_b.ssrcs == {0xBBBB, 0xCCCC}, f"Flow B SSRC set {seg_b.ssrcs} mixed"

        # OUTPUT-level proof: segment counts and SSRC identity.
        man_a = [m for m in seg_a.manifest]
        man_b = [m for m in seg_b.manifest]
        # Flow A is a single-SSRC CONTINUOUS flow -> 2 transmissions.
        assert len(man_a) == 2, (
            f"Flow A should be 2 continuous transmissions, got {len(man_a)}")
        assert all(m["ssrc"] == hex(0xAAAA) for m in man_a), "Flow A SSRC leaked"
        assert sum(int(m["n_pkts"]) for m in man_a) == 10, "Flow A packet count wrong"
        # Flow B is SHORT-SSRC -> 2 transmissions, one per SSRC.
        assert len(man_b) == 2, (
            f"Flow B should be 2 SHORT-SSRC transmissions, got {len(man_b)}")
        assert {m["ssrc"] for m in man_b} == {hex(0xBBBB), hex(0xCCCC)}, \
            "Flow B SSRCs not separated"
        assert sum(int(m["n_pkts"]) for m in man_b) == 10, "Flow B packet count wrong"


# --------------------------------------------------------------------------- #
# Minimal __main__ runner
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
