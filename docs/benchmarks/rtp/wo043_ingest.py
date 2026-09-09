#!/usr/bin/env python3
"""WO-043 universal RTP/G.711 multicast audio ingest (pcap -> per-transmission WAV).

Generalises the original WO-043 build script: instead of hard-coding the four
source addresses/ports and one fixed pcap path, this script

  * takes the pcap (and output dir) as CLI arguments,
  * auto-detects the multicast audio flows present in the capture,
  * classifies each flow by session shape:
        - CONTINUOUS-STREAM : a single SSRC across the capture -> boundaries are
          in WALL-CLOCK arrival (gap where ZERO packets arrive for > gap_s).
          Do NOT trust the RTP timestamp for boundaries (a generator keeps one
          SSRC + monotonic RTP counter across many separate transmissions).
        - SHORT-SSRC         : a new SSRC per transmission -> boundary = SSRC.
  * decodes G.711 A-law (PT=8) to PCM, reconstructs a WAV per transmission,
  * verifies ts/seq contiguity (delta 160 / delta 1) and frame counts,
  * writes a manifest CSV with SHA-256 per segment.

Usage:
    python3 wo043_ingest.py <capture.pcap|.pcapng> <outdir> [--gap 1.0]
                            [--min-payload 160] [--verify-ffmpeg] [--json]

Example:
    python3 wo043_ingest.py "/opt/data/uploads/<id>/gen traffic.pcap" \
            /opt/data/output/wo043_run1 --verify-ffmpeg
"""
import argparse, collections, csv, hashlib, json, os, struct, subprocess, sys, tempfile

SR = 8000          # G.711 mono
PACKET_MS = 20     # 160 samples / 8000 Hz
PAYLOAD_160 = 160  # bytes per audio packet (PT=8 G.711, 20 ms)


# ---------------------------------------------------------------- A-law ----
def alaw_decode(v):
    a = v ^ 0x55
    t = (a & 0x0F) << 4
    seg = (a & 0x70) >> 4
    if seg == 0:
        t += 8
    elif seg == 1:
        t += 0x108
    else:
        t += 0x108
        t <<= seg - 1
    return t if (a & 0x80) else -t


# ------------------------------------------------------------- RTP parse ---
def rtp_parse(rtp):
    """Return a dict for a valid RTP v2 packet, else None. Handles CSRC list
    and the RTP header extension (X bit) correctly."""
    if len(rtp) < 12:
        return None
    b0 = rtp[0]
    if (b0 >> 6) & 0x03 != 2:          # version != 2
        return None
    ext = (b0 >> 4) & 1
    cc = b0 & 0x0F
    hdrlen = 12 + cc * 4
    extlen = 0
    if ext:
        if len(rtp) < hdrlen + 4:
            return None
        w = struct.unpack(">H", rtp[hdrlen + 2:hdrlen + 4])[0]
        extlen = 4 + w * 4
    if len(rtp) < hdrlen + extlen:
        return None
    return dict(
        ext=ext,
        pt=rtp[1] & 0x7F,
        marker=(rtp[1] >> 7) & 1,
        seq=struct.unpack(">H", rtp[2:4])[0],
        ts=struct.unpack(">I", rtp[4:8])[0],
        ssrc=struct.unpack(">I", rtp[8:12])[0],
        payload=rtp[hdrlen + extlen:],
    )


# --------------------------------------------------------- capture parsing --
def parse_legacy_pcap(path):
    """Legacy .pcap (magic 0xa1b2c3d4 / 0xa1b23c4d micro/nano). Yields
    (time_seconds, packet_bytes)."""
    with open(path, "rb") as fh:
        data = fh.read()
    magic = data[:4]
    nano = False
    # 0xa1b2c3d4 = microsecond, 0xa1b23c4d = nanosecond
    if magic == b"\xd4\xc3\xb2\xa1":          # 0xa1b2c3d4 LE, micro
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":        # 0xa1b2c3d4 BE, micro
        endian = ">"
    elif magic == b"\x4d\x3c\xb2\xa1":        # 0xa1b23c4d LE, nano
        endian = "<"
        nano = True
    elif magic == b"\xa1\xb2\x3c\x4d":        # 0xa1b23c4d BE, nano
        endian = ">"
        nano = True
    else:
        raise ValueError(f"unrecognized pcap magic {magic!r}")
    # linktype
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    off = 24
    while off + 16 <= len(data):
        ts_sec, ts_frac, incl, orig = struct.unpack(
            endian + "IIII", data[off:off + 16])
        off += 16
        frame = data[off:off + incl]
        off += incl
        t = ts_sec + ts_frac / (1e9 if nano else 1e6)
        yield t, frame, linktype


def parse_pcapng(path):
    """pcapng: sequence of blocks. Yields (time, packet_bytes, linktype)."""
    with open(path, "rb") as fh:
        data = fh.read()
    i = 0
    n = len(data)
    linktype = None
    resol = 1_000_000  # default micro
    while i + 12 <= n:
        btype, blen = struct.unpack("<II", data[i:i + 8])
        if blen == 0 or i + blen > n:
            break
        body = data[i + 8:i + blen]
        if btype == 0x0A0D0D0A:            # Section Header Block
            pass
        elif btype == 0x00000001:          # Interface Description Block
            if len(body) >= 8:
                linktype = struct.unpack("<H", body[0:2])[0]
                # options: if_tsresol code 9
                opt = 8
                while opt + 4 <= len(body):
                    code, olen = struct.unpack("<HH", body[opt:opt + 4])
                    if code == 9 and olen >= 1:
                        r = body[opt + 4]
                        resol = (2 ** (r & 0x7F)) if (r & 0x80) else (10 ** r)
                    opt += 4 + olen + (olen & 1)
        elif btype == 0x00000006:          # Enhanced Packet Block
            if len(body) >= 20:
                ts_high, ts_low = struct.unpack("<II", body[4:12])
                caplen = struct.unpack("<I", body[12:16])[0]
                pkt = body[20:20 + caplen]
                ticks = (ts_high << 32) | ts_low
                t = ticks / resol
                yield t, pkt, linktype
        elif btype == 0x00000003:          # Simple Packet Block
            if len(body) >= 4:
                caplen = struct.unpack("<I", body[0:4])[0]
                yield None, body[4:4 + caplen], linktype
        i += blen


def iter_frames(path):
    """Yield (time, frame, linktype) from either .pcap or .pcapng."""
    if path.endswith(".pcapng"):
        yield from parse_pcapng(path)
    else:
        yield from parse_legacy_pcap(path)


# ------------------------------------------------------- Ethernet/IP/UDP ----
def parse_ip_udp(frame, linktype):
    """Return (src_ip, dst_ip, sport, dport, rtp_bytes) or None."""
    if linktype == 1:                        # Ethernet II
        if len(frame) < 14:
            return None
        eth = frame[12:14]
        if eth == b"\x81\x00":               # VLAN
            if len(frame) < 18:
                return None
            eth = frame[16:18]
            ip_off = 18
        elif eth == b"\x08\x00":
            ip_off = 14
        else:
            return None
        ip = frame[ip_off:]
    elif linktype == 101:                    # raw IP
        ip = frame
    else:
        return None
    if len(ip) < 20:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if ip[9] != 17:                          # UDP only
        return None
    total = struct.unpack(">H", ip[2:4])[0]
    if total > len(ip):
        total = len(ip)
    src = ".".join(str(b) for b in ip[12:16])
    dst = ".".join(str(b) for b in ip[16:20])
    udp = ip[ihl:total]
    if len(udp) < 8:
        return None
    sport, dport = struct.unpack(">HH", udp[0:4])
    rtp = udp[8:]
    return src, dst, sport, dport, rtp


# ------------------------------------------------------------- flow detect --
def is_multicast(ip):
    return ip.startswith("224.") or ip.startswith("239.")


def collect(path, min_payload=PAYLOAD_160):
    """Parse a capture and return:
      - pkts: list of dicts (time, src, dst, sport, dport, rtp fields) that pass
              the P1 valid-audio filter (RTP v2 + PT=8 + SSRC!=0 + payload==160),
      - flows: ordered dict of detected audio flows keyed (src, sport, dport),
      - raw: per-flow count of ALL RTP packets seen (incl. control/phantom).
    """
    pkts = []
    flow_rtp = collections.Counter()   # all RTP v2 packets, before P1
    flow_audio = collections.Counter() # P1-filtered
    for t, frame, linktype in iter_frames(path):
        parsed = parse_ip_udp(frame, linktype)
        if not parsed:
            continue
        src, dst, sport, dport, rtp = parsed
        r = rtp_parse(rtp)
        if not r:
            continue
        key = (src, sport, dport)
        flow_rtp[key] += 1
        # P1: v2 (already), PT=8, SSRC!=0, 160-byte payload
        if r["pt"] == 8 and r["ssrc"] != 0 and len(r["payload"]) == min_payload:
            r.update(time=t, src=src, dst=dst, sport=sport, dport=dport)
            pkts.append(r)
            flow_audio[key] += 1
    return pkts, flow_audio, flow_rtp


# ------------------------------------------------------------- segmentation -
def seg_by_wallgap(pkts, gap):
    """Split a continuous-stream flow into bursts on wall-clock arrival gap
    (ZERO packets for > gap seconds). Return list of lists, sorted by time."""
    pkts = sorted(pkts, key=lambda r: r["time"])
    if not pkts:
        return []
    bursts = [[pkts[0]]]
    for i in range(1, len(pkts)):
        if pkts[i]["time"] - pkts[i - 1]["time"] > gap:
            bursts.append([pkts[i]])
        else:
            bursts[-1].append(pkts[i])
    return bursts


def seg_by_ssrc(pkts):
    """Split a short-SSRC flow into per-SSRC groups."""
    groups = collections.defaultdict(list)
    for r in pkts:
        groups[r["ssrc"]].append(r)
    return list(groups.values())


def verify_contiguous(pkts_sorted):
    """Return (ts_bad, seq_bad): number of transitions where ts delta != 160
    or seq delta != 1."""
    ts_bad = sum(1 for i in range(1, len(pkts_sorted))
                 if pkts_sorted[i]["ts"] - pkts_sorted[i - 1]["ts"]# 160
                 != 160)
    seq_bad = sum(1 for i in range(1, len(pkts_sorted))
                  if (pkts_sorted[i]["seq"] - pkts_sorted[i - 1]["seq"]) & 0xFFFF
                  != 1)
    return ts_bad, seq_bad


def decode(payloads):
    s = []
    for p in payloads:
        for b in p:
            s.append(alaw_decode(b))
    return s


def rms(samples):
    return (sum(x * x for x in samples) / len(samples)) ** 0.5 if samples else 0.0


def write_wav(path, samples):
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(samples) * 2))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", len(samples) * 2))
        f.write(b"".join(struct.pack("<h", s) for s in samples))


def ffmpeg_decode_alaw(alaws):
    """Reference decode via ffmpeg; return list of int16 samples."""
    with tempfile.NamedTemporaryFile(suffix=".alaw", delete=False) as f:
        f.write(alaws)
        ap = f.name
    subprocess.run(
        ["ffmpeg", "-y", "-f", "alaw", "-ar", str(SR), "-ac", "1",
         "-i", ap, "-f", "s16le", "-acodec", "pcm_s16le", "/tmp/_chk.s16le"],
        capture_output=True)
    raw = open("/tmp/_chk.s16le", "rb").read()
    os.unlink(ap)
    return [struct.unpack("<h", raw[i:i + 2])[0] for i in range(0, len(raw), 2)]


# ------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", help="path to .pcap or .pcapng")
    ap.add_argument("outdir", help="output directory for WAVs + manifest")
    ap.add_argument("--gap", type=float, default=1.0,
                    help="wall-clock gap (s) separating transmissions (default 1.0)")
    ap.add_argument("--min-payload", type=int, default=PAYLOAD_160,
                    help="required audio payload bytes (default 160)")
    ap.add_argument("--verify-ffmpeg", action="store_true",
                    help="cross-check A-law decode against ffmpeg on a sample")
    ap.add_argument("--json", action="store_true",
                    help="also emit a machine-readable summary JSON")
    ap.add_argument("--boundary-eps", type=float, default=0.001,
                    help="wall-clock tolerance (s) for detecting a segment that "
                         "touches the capture start/end boundary (default 0.001)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    pkts, flow_audio, flow_rtp = collect(args.capture, args.min_payload)

    # Capture boundary. A segment whose first packet is within boundary-eps of the
    # capture's FIRST packet is provably truncated at the start (the capture began
    # mid-burst). A segment whose last packet is within boundary-eps of the
    # capture's LAST packet *may* be truncated at EOF (completeness unknown). These
    # are flagged but never silently removed -- see the boundary report below.
    cap_start = min(r["time"] for r in pkts)
    cap_end = max(r["time"] for r in pkts)

    print(f"[capture] {args.capture}")
    print(f"[capture] P1-filtered audio packets: {len(pkts)}")
    print(f"[capture] flows (src:port -> dport) | rtp_all / audio_ok | "
          f"session shape")
    flows = collections.OrderedDict()
    for key in sorted(flow_audio, key=lambda k: (k[0], k[2], k[1])):
        src, sport, dport = key
        n_all = flow_rtp[key]
        n_audio = flow_audio[key]
        # shape by SSRC diversity among audio packets
        ssrcs = {r["ssrc"] for r in pkts if (r["src"], r["sport"], r["dport"]) == key}
        shape = "CONTINUOUS" if len(ssrcs) == 1 else "SHORT-SSRC"
        flows[key] = dict(ssrcs=ssrcs, shape=shape)
        print(f"  {src}:{sport} -> :{dport} | {n_all:5d} / {n_audio:5d} | {shape}"
              f" ({len(ssrcs)} ssrc)")

    # optional ffmpeg cross-check on the first flow's first 100 audio packets
    if args.verify_ffmpeg and pkts:
        first_key = next(iter(flows))
        sample = sorted([r for r in pkts
                         if (r["src"], r["sport"], r["dport"]) == first_key],
                        key=lambda r: r["ts"])[:100]
        ours = decode([r["payload"] for r in sample])
        ref = ffmpeg_decode_alaw(b"".join(r["payload"] for r in sample))
        print(f"[ffmpeg] {first_key[0]}:{first_key[1]}->:{first_key[2]} "
              f"n={len(sample)} ours={len(ours)} ffmpeg={len(ref)} "
              f"match={ours == ref}")

    manifest = []
    idx = 0
    for key in sorted(flows, key=lambda k: (k[0], k[2], k[1])):
        src, sport, dport = key
        fpkts = [r for r in pkts if (r["src"], r["sport"], r["dport"]) == key]
        shape = flows[key]["shape"]
        label = f"src{src.split('.')[-1]}_{sport}_grp{dport}"
        if shape == "CONTINUOUS":
            bursts = seg_by_wallgap(fpkts, args.gap)
            for bi, burst in enumerate(bursts, 1):
                b = sorted(burst, key=lambda r: r["ts"])
                samples = decode([r["payload"] for r in b])
                ts_bad, seq_bad = verify_contiguous(b)
                idx += 1
                seg_id = f"WALL-{idx:03d}"
                fn = f"{label}_b{bi:02d}_{idx:03d}.wav"
                write_wav(os.path.join(args.outdir, fn), samples)
                manifest.append(_mk(src, sport, dport, b, seg_id, fn, samples,
                                    ts_bad, seq_bad, "wallgap>%.1fs" % args.gap,
                                    cap_start, cap_end, args.boundary_eps))
        else:
            groups = seg_by_ssrc(fpkts)
            for g in groups:
                g = sorted(g, key=lambda r: r["ts"])
                samples = decode([r["payload"] for r in g])
                ts_bad, seq_bad = verify_contiguous(g)
                idx += 1
                seg_id = f"SSRC-{idx:03d}"
                ssrc = g[0]["ssrc"]
                fn = f"{label}_ssrc{ssrc:08x}_{idx:03d}.wav"
                write_wav(os.path.join(args.outdir, fn), samples)
                manifest.append(_mk(src, sport, dport, g, seg_id, fn, samples,
                                    ts_bad, seq_bad, "SSRC",
                                    cap_start, cap_end, args.boundary_eps))

    # SHA-256
    for m in manifest:
        with open(os.path.join(args.outdir, m["wav"]), "rb") as f:
            m["sha256"] = hashlib.sha256(f.read()).hexdigest()

    fields = list(manifest[0].keys()) if manifest else []
    mpath = os.path.join(args.outdir, "wo043_manifest.csv")
    with open(mpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(manifest)

    print(f"\n[TOTAL] segments (raw P1): {len(manifest)}")
    bysrc = collections.Counter((m["source_ip"], m["mcast_port"]) for m in manifest)
    for k, v in sorted(bysrc.items()):
        print(f"  {k[0]}:{k[1]} -> {v}")
    # Boundary report. This number is RAW P1: it does NOT exclude segments that
    # touch the capture boundary. A capture-start segment is provably truncated
    # (the capture began mid-burst); a capture-end segment may be incomplete at
    # EOF. The tool flags these rather than silently subtracting them, because
    # auto-removal would need a policy decision (which burst is "really" the
    # boundary one) that is dataset-specific.
    bstart = [m for m in manifest if m["boundary_class"] == "capture-start"]
    bend = [m for m in manifest if m["boundary_class"] == "capture-end"]
    print(f"[boundary] capture-start (truncated at capture start): {len(bstart)}")
    for m in bstart:
        print(f"   {m['seg']:10s} {m['source_ip']}:{m['mcast_port']} "
              f"t_start={m['t_start']} n={m['n_pkts']}")
    print(f"[boundary] capture-end (completeness unknown at EOF): {len(bend)}")
    for m in bend:
        print(f"   {m['seg']:10s} {m['source_ip']}:{m['mcast_port']} "
              f"t_end={m['t_end']} n={m['n_pkts']}")
    if bstart:
        print(f"[boundary] adjusted (excluding {len(bstart)} capture-start "
              f"truncation): {len(manifest) - len(bstart)}")
    bad = [m for m in manifest if m["ts_gaps"] != 0 or m["seq_gaps"] != 0]
    print(f"[integrity] segments with ts/seq gaps: {len(bad)}")
    for m in bad:
        print("   ", m["seg"], m["wav"], "ts_gaps=", m["ts_gaps"], "seq_gaps=", m["seq_gaps"])
    for m in manifest:
        exp = m["n_pkts"] * (PACKET_MS / 1000.0)
        if abs(m["audio_dur"] - exp) > 0.001:
            print("   AUDIO_DUR MISMATCH", m["seg"], m["audio_dur"], "expected", exp)
    print("[integrity] audio_dur check done")
    print(f"[manifest] {mpath}")

    if args.json:
        jpath = os.path.join(args.outdir, "wo043_report.json")
        with open(jpath, "w") as f:
            json.dump({"capture": args.capture, "total_segments": len(manifest),
                       "manifest": manifest}, f, indent=2, ensure_ascii=False)
        print(f"[json] {jpath}")


def _mk(src, sport, dport, b, seg_id, fn, samples, ts_bad, seq_bad, boundary,
        cap_start=None, cap_end=None, eps=0.001):
    t0 = min(r["time"] for r in b)
    t1 = max(r["time"] for r in b)
    # Boundary classification (general, not hard-coded to any dataset):
    #   capture-start -> the burst began at/before the capture's first packet, so
    #                    its true start is NOT in the capture (truncated tail).
    #   capture-end   -> the burst ends at/after the capture's last packet, so its
    #                    completeness at EOF is UNKNOWN.
    #   internal      -> neither; a clean, fully-captured burst.
    if cap_start is not None and t0 <= cap_start + eps:
        bnd = "capture-start"
    elif cap_end is not None and t1 >= cap_end - eps:
        bnd = "capture-end"
    else:
        bnd = "internal"
    return dict(
        seg=seg_id, source_ip=src, source_port=sport, mcast_port=dport,
        ssrc=hex(b[0]["ssrc"]), n_pkts=len(b),
        t_start=round(t0, 3),
        t_end=round(t1, 3),
        dur_wall=round(t1 - t0, 3),
        audio_dur=round(len(samples) / SR, 3), rms=round(rms(samples), 1),
        boundary=boundary, boundary_class=bnd, ts_gaps=ts_bad, seq_gaps=seq_bad,
        wav=fn, sha256="")


if __name__ == "__main__":
    main()
