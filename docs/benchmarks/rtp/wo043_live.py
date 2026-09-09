#!/usr/bin/env python3
"""WO-043 LIVE: real-time UDP multicast RTP/G.711 ingest -> per-transmission WAV.

This is the real-time analogue of wo043_ingest.py (offline pcap replay). It
shares the same core primitives (RTP parse w/ CSRC+extension, A-law decode,
CONTINUOUS vs SHORT-SSRC segmentation) but reads packets straight off a UDP
multicast socket instead of a capture file.

Implements the verified multicast receiver rules from the rtp-audio-ingest
skill:

  * one socket per (group, port)  -- never share a UDP port across groups with
    SO_REUSEADDR (Linux delivers BOTH groups to BOTH sockets and the per-source
    SSRC/sequence state gets mixed).
  * sender must set IP_MULTICAST_IF to the SAME interface the receiver joins,
    and IP_MULTICAST_LOOP=1 for loopback tests.
  * receiver exposes is_bound(); poll it before emitting packets in a test
    (startup race: packets sent right after start() are dropped before bind).
  * clear the running flag in the receive thread's finally (so is_active() does
    not lie and idempotent start() can restart after a stop()).
  * per-source isolation: each (group,port) has its OWN segmenter + WAV writer;
    no shared mutable recording state.
  * drive segmentation off the RTP timestamp / payload ordering, never off
    wall-clock arrival for continuous streams (a generator keeps one SSRC +
    monotonic RTP counter across many separate transmissions; the real
    boundaries are wall-clock gaps where ZERO packets arrive for > gap_s).

WO-044-CORR-01 corrections:
  * AUTO cold-start over-split: the first transmission of a SHORT-SSRC flow is
    no longer split by an internal wall-gap before a second SSRC is observed.
    The first logical transmission is buffered and its boundary decision is
    deferred until the flow's shape is known -- SHORT-SSRC (a second SSRC
    appears) flushes it as ONE transmission; CONTINUOUS (confirmed by idle or
    end-of-replay) flushes it split at the recorded wall-gap boundaries. This
    matches the offline semantics and keeps the clean-capture AUTO baseline
    (106 / 44+15+38+9) byte-identical.
  * socket/multicast source-flow isolation: the live socket mode keys the
    segmentation state by the full flow (src_ip, sport, dport), NOT by
    (group, port) alone, so two talkers sharing one multicast group:port
    (.10:5011 and .118:49755 both -> 239.x:5011) no longer share a segmenter.

Usage (receive live):
    python3 wo043_live.py --group 239.233.58.10 --port 5011 \
            --group 239.233.58.20 --port 5022 --outdir /opt/data/output/live \
            --gap 1.0 --interface 127.0.0.1

Usage (replay a pcap through the SAME live pipeline, for regression):
    python3 wo043_live.py --replay /path/to/gen_traffic.pcap
            --outdir /opt/data/output/live_replay
"""
import argparse, collections, hashlib, os, socket, struct, sys, threading, time
import csv

SR = 8000
PACKET_MS = 20
PAYLOAD_160 = 160


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
    if len(rtp) < 12:
        return None
    b0 = rtp[0]
    if (b0 >> 6) & 0x03 != 2:
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
    return dict(ext=ext, pt=rtp[1] & 0x7F, marker=(rtp[1] >> 7) & 1,
                seq=struct.unpack(">H", rtp[2:4])[0],
                ts=struct.unpack(">I", rtp[4:8])[0],
                ssrc=struct.unpack(">I", rtp[8:12])[0],
                payload=rtp[hdrlen + extlen:])


def rtp_parse_from_udp(udp, t):
    """udp = the full UDP datagram (sport/dport/RTP). Return dict or None."""
    if len(udp) < 8:
        return None
    sport, dport = struct.unpack(">HH", udp[0:4])
    r = rtp_parse(udp[8:])
    if not r:
        return None
    r.update(sport=sport, dport=dport, time=t)
    return r


def write_wav(path, samples):
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(samples) * 2))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", len(samples) * 2))
        f.write(b"".join(struct.pack("<h", s) for s in samples))


def rms(samples):
    return (sum(x * x for x in samples) / len(samples)) ** 0.5 if samples else 0.0


# ------------------------------------------------------------- segmenter ----
class TransmissionSegmenter:
    """Segments a single source-flow (src_ip, sport, dport) audio stream into
    transmissions and writes one WAV per transmission. Per-source state only.

    Boundary policy:
      - SHORT-SSRC: a new SSRC => new transmission.
      - CONTINUOUS (single SSRC): wall-clock gap where ZERO packets arrive for
        > gap_s => new transmission. RTP timestamp is NOT trusted for the
        boundary.

    AUTO cold-start (force_shape is None):
      The flow's shape is unknown until a SECOND distinct SSRC is observed.
      While only one SSRC has been seen, boundary decisions are DEFERRED: the
      first logical transmission is buffered (with wall-gap candidate
      boundaries recorded, not applied) so it can later be emitted either as
      ONE transmission (if a second SSRC appears => SHORT-SSRC) or split at the
      recorded wall-gaps (if the flow is confirmed CONTINUOUS). This prevents
      the previous cold-start over-split where a SHORT-SSRC flow's first
      transmission was split by an internal wall-gap before a second SSRC was
      seen (WO-044 finding).
    """

    def __init__(self, group, port, outdir, gap=1.0, flush_gap=2.0,
                 source=None, force_shape=None):
        self.group = group
        self.port = port
        self.source = source          # (src_ip, sport) of the talker, if known
        self.outdir = outdir
        self.gap = gap
        self.flush_gap = flush_gap   # close any open burst after this idle
        self.force_shape = force_shape  # None=AUTO, else "CONTINUOUS"/"SHORT-SSRC"
        self.ssrcs = set()
        self.lock = threading.Lock()
        self.count = 0
        self.cur_ssrc = None
        self.cur_burst = []          # list of rtp dicts (in arrival order)
        self.last_t = None
        self.manifest = []
        # AUTO cold-start deferral state:
        self._resolved = None        # None (unresolved) / "SHORT-SSRC" / "CONTINUOUS"
        self._pending_bounds = []    # indices into cur_burst where wall-gaps are
        os.makedirs(outdir, exist_ok=True)

    def _shape(self):
        """Return the segmenter's current effective boundary policy."""
        if self.force_shape is not None:
            return self.force_shape
        if self._resolved is not None:
            return self._resolved
        # UNRESOLVED: shape not yet determined. Deferred; no boundary applied.
        return "CONTINUOUS"

    def feed(self, r):
        with self.lock:
            self.ssrcs.add(r["ssrc"])
            t = r["time"]
            if self.force_shape is not None:
                self._feed_by_shape(r, t, self.force_shape)
            elif self._resolved is None:
                self._feed_unresolved(r, t)
            else:
                self._feed_by_shape(r, t, self._resolved)

    def _feed_unresolved(self, r, t):
        """AUTO cold-start: buffer the first logical transmission and defer the
        boundary decision until the flow's shape is known."""
        if len(self.ssrcs) >= 2:
            # A second distinct SSRC appeared => the flow is SHORT-SSRC. Flush
            # the buffered first transmission as ONE (any recorded wall-gap
            # candidate boundaries are discarded).
            self._resolved = "SHORT-SSRC"
            self._flush(shape="SHORT-SSRC")
            self.cur_ssrc = r["ssrc"]
            self.cur_burst = [r]
            self.last_t = t
            return
        # Still a single SSRC: buffer, and record (but do not apply) a wall-gap
        # candidate boundary so a later CONTINUOUS resolution can split here.
        if self.last_t is not None and (t - self.last_t) > self.gap:
            self._pending_bounds.append(len(self.cur_burst))
        self.cur_ssrc = r["ssrc"]
        self.cur_burst.append(r)
        self.last_t = t

    def _feed_by_shape(self, r, t, shape):
        if shape == "SHORT-SSRC":
            if r["ssrc"] != self.cur_ssrc:
                if self.cur_burst:
                    self._flush(shape="SHORT-SSRC")
                self.cur_ssrc = r["ssrc"]
                self.cur_burst = []
            self.cur_burst.append(r)
        else:  # CONTINUOUS
            if self.last_t is not None and (t - self.last_t) > self.gap:
                if self.cur_burst:
                    self._flush(shape="CONTINUOUS")
                self.cur_burst = []
            self.cur_burst.append(r)
            self.cur_ssrc = r["ssrc"]
        self.last_t = t

    def _resolve_continuous(self):
        """Confirm the flow is CONTINUOUS (single SSRC across the observed
        window). Flush the buffered first transmission, splitting at the
        recorded wall-gap candidate boundaries, then apply continuous policy."""
        if self._resolved is not None:
            return
        self._resolved = "CONTINUOUS"
        if not self.cur_burst:
            return
        burst = self.cur_burst
        bounds = self._pending_bounds
        self.cur_burst = []
        self._pending_bounds = []
        segs = []
        start = 0
        for b in bounds:
            segs.append(burst[start:b])
            start = b
        segs.append(burst[start:])
        for seg in segs:
            if seg:
                self._write_segment(seg, "CONTINUOUS")

    def maybe_flush_idle(self):
        """Called periodically; closes a burst that has gone quiet for
        flush_gap (so we don't hold a long tail in memory). In AUTO cold-start
        an idle with a single SSRC confirms the flow as CONTINUOUS."""
        with self.lock:
            if self.cur_burst and self.last_t is not None and \
               (time.time() - self.last_t) > self.flush_gap:
                if self._resolved is None:
                    self._resolve_continuous()
                else:
                    self._flush()

    def _flush(self, shape=None):
        """Flush the whole current burst as ONE transmission."""
        if not self.cur_burst:
            return
        if shape is None:
            shape = self._shape()
        burst = self.cur_burst
        self.cur_burst = []
        self._pending_bounds = []
        self._write_segment(burst, shape)

    def _write_segment(self, burst, shape):
        b = sorted(burst, key=lambda r: r["ts"])
        samples = []
        for r in b:
            for byte in r["payload"]:
                samples.append(alaw_decode(byte))
        self.count += 1
        seg_id = f"LIVE-{self.count:03d}"
        label = f"grp{self.port}"
        ssrc = b[0]["ssrc"]
        fn = f"{label}_ssrc{ssrc:08x}_{seg_id}.wav"
        write_wav(os.path.join(self.outdir, fn), samples)
        sha = hashlib.sha256(
            open(os.path.join(self.outdir, fn), "rb").read()).hexdigest()
        ts_bad = sum(1 for i in range(1, len(b))
                     if b[i]["ts"] - b[i - 1]["ts"] != 160)
        seq_bad = sum(1 for i in range(1, len(b))
                      if (b[i]["seq"] - b[i - 1]["seq"]) & 0xFFFF != 1)
        self.manifest.append(dict(
            seg=seg_id, group=self.group, mcast_port=self.port,
            source_ip=(self.source[0] if self.source else ""),
            source_port=(self.source[1] if self.source else ""),
            ssrc=hex(ssrc), n_pkts=len(b),
            t_start=round(min(r["time"] for r in b), 3),
            t_end=round(max(r["time"] for r in b), 3),
            dur_wall=round(max(r["time"] for r in b) - min(r["time"] for r in b), 3),
            audio_dur=round(len(samples) / SR, 3), rms=round(rms(samples), 1),
            shape=shape, ts_gaps=ts_bad, seq_gaps=seq_bad, wav=fn,
            sha256=sha))

    def write_manifest(self):
        with self.lock:
            if self._resolved is None:
                # Still single-SSRC at end-of-replay => CONTINUOUS.
                self._resolve_continuous()
            else:
                self._flush()
            rows = self.manifest
        # one manifest file per (talker, group) so two sources on the same
        # multicast port don't overwrite each other.
        if self.source:
            label = f"src{self.source[0].split('.')[-1]}_{self.source[1]}_grp{self.port}"
        else:
            label = f"grp{self.port}"
        path = os.path.join(self.outdir, f"live_manifest_{label}.csv")
        if rows:
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        return path


# ------------------------------------------------------------- receivers ----
class FlowManager:
    """Routes datagrams to a per-source-flow TransmissionSegmenter keyed by
    (src_ip, sport, dport). A single multicast group:port can carry MULTIPLE
    talkers; keying the segmentation state by (group, port) alone would mix
    their SSRC state (WO-044 finding)."""

    def __init__(self, outdir, gap=1.0, flush_gap=2.0, force_shape=None):
        self.outdir = outdir
        self.gap = gap
        self.flush_gap = flush_gap
        self.force_shape = force_shape
        self.segmenters = {}   # (src_ip, sport, dport) -> TransmissionSegmenter
        self.all = []
        self.lock = threading.Lock()

    def get_or_create(self, src_ip, sport, dport, group):
        key = (src_ip, sport, dport)
        with self.lock:
            seg = self.segmenters.get(key)
            if seg is None:
                seg = TransmissionSegmenter(
                    group, dport, os.path.join(self.outdir, f"grp{dport}"),
                    gap=self.gap, flush_gap=self.flush_gap,
                    source=(src_ip, sport), force_shape=self.force_shape)
                self.segmenters[key] = seg
                self.all.append(seg)
            return seg

    def maybe_flush_idle(self):
        with self.lock:
            for seg in self.all:
                seg.maybe_flush_idle()

    def write_all_manifests(self):
        for seg in self.all:
            seg.write_manifest()

    def __len__(self):
        return len(self.all)


class MulticastReceiver:
    """One UDP socket per (group, port). Binds, joins the group, and feeds each
    datagram to the per-source-flow segmenter (via FlowManager) from a receive
    thread."""

    def __init__(self, group, port, flow_manager, interface="0.0.0.0",
                 family=socket.AF_INET):
        self.group = group
        self.port = port
        self.flow_manager = flow_manager
        self.interface = interface
        self.family = family
        self.sock = None
        self.running = False
        self._bound = threading.Event()
        self._thread = None

    def start(self):
        if self.running:
            return False
        self.sock = socket.socket(self.family, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", self.port))
        # join the group on the chosen interface
        mreq = socket.inet_aton(self.group) + socket.inet_aton(
            self.interface if self.interface != "0.0.0.0" else "0.0.0.0")
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._bound.set()
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"mcast-{self.group}:{self.port}")
        self._thread.start()
        return True

    def is_bound(self):
        return self._bound.is_set()

    def is_active(self):
        return self.running

    def _run(self):
        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(65535)
                except socket.timeout:
                    self.flow_manager.maybe_flush_idle()
                    continue
                t = time.time()
                r = rtp_parse_from_udp(data, t)
                if r and r["pt"] == 8 and r["ssrc"] != 0 and \
                   len(r["payload"]) == PAYLOAD_160:
                    src_ip = addr[0]
                    seg = self.flow_manager.get_or_create(
                        src_ip, r["sport"], r["dport"], self.group)
                    seg.feed(r)
        finally:
            # CRITICAL: clear running here so is_active() doesn't lie and
            # idempotent start() can restart this source after stop().
            self.running = False
            if self.sock:
                self.sock.close()

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
        if self._thread:
            self._thread.join(timeout=2)


# ------------------------------------------------------------- pcap replay --
def iter_frames(path):
    """Reuse the offline parser: yields (time, frame, linktype)."""
    if path.endswith(".pcapng"):
        yield from parse_pcapng(path)
    else:
        yield from parse_legacy_pcap(path)


def parse_legacy_pcap(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic = data[:4]
    nano = False
    if magic == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    elif magic == b"\x4d\x3c\xb2\xa1":
        endian = "<"; nano = True
    elif magic == b"\xa1\xb2\x3c\x4d":
        endian = ">"; nano = True
    else:
        raise ValueError(f"unrecognized pcap magic {magic!r}")
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    off = 24
    while off + 16 <= len(data):
        ts_sec, ts_frac, incl, orig = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        frame = data[off:off + incl]
        off += incl
        t = ts_sec + ts_frac / (1e9 if nano else 1e6)
        yield t, frame, linktype


def parse_pcapng(path):
    with open(path, "rb") as fh:
        data = fh.read()
    i, n = 0, len(data)
    linktype = None
    resol = 1_000_000
    while i + 12 <= n:
        btype, blen = struct.unpack("<II", data[i:i + 8])
        if blen == 0 or i + blen > n:
            break
        body = data[i + 8:i + blen]
        if btype == 0x0A0D0D0A:
            pass
        elif btype == 0x00000001:
            if len(body) >= 8:
                linktype = struct.unpack("<H", body[0:2])[0]
                opt = 8
                while opt + 4 <= len(body):
                    code, olen = struct.unpack("<HH", body[opt:opt + 4])
                    if code == 9 and olen >= 1:
                        r = body[opt + 4]
                        resol = (2 ** (r & 0x7F)) if (r & 0x80) else (10 ** r)
                    opt += 4 + olen + (olen & 1)
        elif btype == 0x00000006:
            if len(body) >= 20:
                ts_high, ts_low = struct.unpack("<II", body[4:12])
                caplen = struct.unpack("<I", body[12:16])[0]
                ticks = (ts_high << 32) | ts_low
                yield ticks / resol, body[20:20 + caplen], linktype
        elif btype == 0x00000003:
            if len(body) >= 4:
                caplen = struct.unpack("<I", body[0:4])[0]
                yield None, body[4:4 + caplen], linktype
        i += blen


def parse_ip_udp(frame, linktype):
    if linktype == 1:
        if len(frame) < 14:
            return None
        eth = frame[12:14]
        if eth == b"\x81\x00":
            if len(frame) < 18:
                return None
            ip_off = 18
        elif eth == b"\x08\x00":
            ip_off = 14
        else:
            return None
        ip = frame[ip_off:]
    elif linktype == 101:
        ip = frame
    else:
        return None
    if len(ip) < 20:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if ip[9] != 17:
        return None
    total = struct.unpack(">H", ip[2:4])[0]
    if total > len(ip):
        total = len(ip)
    src = ".".join(str(b) for b in ip[12:16])
    udp = ip[ihl:total]
    if len(udp) < 8:
        return None
    sport, dport = struct.unpack(">HH", udp[0:4])
    return src, sport, dport, udp


def replay(path, outdir, gap=1.0, force_shape=None):
    """Feed a pcap through the live pipeline (same segmenters) for regression."""
    segs = collections.defaultdict(lambda: None)
    total = 0
    for t, frame, linktype in iter_frames(path):
        parsed = parse_ip_udp(frame, linktype)
        if not parsed:
            continue
        src, sport, dport, udp = parsed
        r = rtp_parse_from_udp(udp, t)
        if not (r and r["pt"] == 8 and r["ssrc"] != 0 and
                len(r["payload"]) == PAYLOAD_160):
            continue
        # Key by the full talker flow (src, sport, dport), NOT just dport:
        # a multicast group port can carry more than one talker (e.g. two
        # sources -> 5011 in the generated capture).
        key = (src, sport, dport)
        if segs[key] is None:
            segs[key] = TransmissionSegmenter(src, dport,
                                              os.path.join(outdir, f"grp{dport}"),
                                              gap=gap, source=(src, sport),
                                              force_shape=force_shape)
        segs[key].feed(r)
    for key, seg in sorted(segs.items()):
        m = seg.write_manifest()
        total += len(seg.manifest)
        print(f"[replay] {key[0]}:{key[1]}->:{key[2]}: "
              f"{len(seg.manifest)} transmissions -> {m}")
    print(f"[replay] TOTAL transmissions: {total}")


# ------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", action="append", type=str, default=[],
                    help="multicast group (repeatable); pairs with --port")
    ap.add_argument("--port", action="append", type=int, default=[],
                    help="UDP port (repeatable); one per group")
    ap.add_argument("--replay", type=str, default=None,
                    help="replay a .pcap/.pcapng through the live pipeline")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--gap", type=float, default=1.0)
    ap.add_argument("--interface", type=str, default="0.0.0.0",
                    help="interface IP to join multicast on")
    ap.add_argument("--runtime", type=float, default=None,
                    help="run for N seconds then stop (default: until Ctrl-C)")
    ap.add_argument("--shape", type=str, default=None,
                    choices=["auto", "continuous", "short-ssrc"],
                    help="force the per-flow boundary policy instead of inferring "
                         "it dynamically. Use 'short-ssrc' when a source emits one "
                         "SSRC per transmission (known) to avoid the cold-start "
                         "misclassification. Default: auto (dynamic).")
    args = ap.parse_args()

    force_shape = None if (args.shape in (None, "auto")) else args.shape.upper()

    if args.replay:
        replay(args.replay, args.outdir, args.gap, force_shape)
        return

    if len(args.group) != len(args.port) or not args.group:
        ap.error("--group and --port must be provided in matching pairs")

    os.makedirs(args.outdir, exist_ok=True)
    flow_manager = FlowManager(args.outdir, gap=args.gap, force_shape=force_shape)
    receivers = []
    for g, p in zip(args.group, args.port):
        recv = MulticastReceiver(g, p, flow_manager, interface=args.interface)
        recv.start()
        receivers.append(recv)
        print(f"[live] listening on {g}:{p} (bound={recv.is_bound()})")

    # wait for all to bind before signalling ready
    for recv in receivers:
        recv._bound.wait(timeout=3)

    stop = threading.Event()
    start_t = time.time()
    try:
        if args.runtime:
            stop.wait(args.runtime)
        else:
            while True:
                time.sleep(1)
                flow_manager.maybe_flush_idle()
                if args.runtime and time.time() - start_t >= args.runtime:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        for recv in receivers:
            recv.stop()
        flow_manager.write_all_manifests()
        for seg in flow_manager.all:
            print(f"[live] {seg.group}:{seg.port} src={seg.source} -> "
                  f"{len(seg.manifest)} transmissions")


if __name__ == "__main__":
    main()
