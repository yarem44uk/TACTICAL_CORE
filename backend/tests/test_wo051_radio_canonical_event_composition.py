"""WO-051 — Radio -> canonical Event production composition.

Proves that the REAL radio production composition reaches the canonical
WO-050 ingestion boundary:

    REAL RADIO RTP
        -> RTP ingest           (RtpCaptureReader / RtpReceiver: parse + A-law)
        -> segmentation         (TransmissionRecorder: VAD -> segment -> WAV)
        -> RAW SourceEnvelope   (RecordingMetadata.to_event_raw)
        -> AdapterRuntime       (_process_raw)
        -> EventFactory.create_event()   (single canonical seam)
        -> canonical Event
        -> EventPipeline.process()        (boundary)

Discovery note (WO-051): the production radio path is composed by
``MulticastAudioSourceAdapter`` (app/audio/source_adapter.py), which wires
``RtpReceiver`` -> ``TransmissionRecorder`` -> RAW queue, NOT by
``AudioEventOrchestrator``.  ``AudioEventOrchestrator`` is the WO-038 TCA1
(test/compatibility) seam and is NOT part of the production radio composition.
This suite therefore exercises the real production radio-side components
(``RtpCaptureReader`` + ``TransmissionRecorder``) and the real canonical
boundary (``AdapterRuntime`` -> ``EventFactory`` -> ``EventPipeline``).

Scope: canonical composition only.  No durable-journal semantics, no database,
no STT, no checkpoint, no projection engine internals.  A controlled
``EventPipeline`` with a spy repository/projection observes the canonical
Event at the boundary (WO-051 §3, §WO-052 boundary).

Design: deterministic synthetic RTP captures (real G.711 A-law, real
``RtpCaptureReader`` parse) drive the production composition.  Where the real
capture fixture (``radio_rtp.pcapng``) is available it is also exercised.
"""

from __future__ import annotations

import ast
import os
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.audio.alaw import alaw_encode_byte
from app.audio.audio_config import AudioConfig
from app.audio.recording_config import RecordingConfig
from app.audio.recorder import TransmissionRecorder
from app.audio.rtp_capture import RtpCaptureReader
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.runtime.adapter_runtime import AdapterRuntime

# ---------------------------------------------------------------------------
# Constants / codec
# ---------------------------------------------------------------------------
SAMPLE_RATE = 8000
CHANNELS = 1
FRAME_SAMPLES = 160  # 20 ms at 8 kHz
SILENCE_BYTE = alaw_encode_byte(50)    # near-silence A-law (RMS ~50)
SPEECH_BYTE = alaw_encode_byte(20000)  # loud A-law (RMS ~20000)

# WO-043 / WO-044 known radio sources and multicast destinations.
SRC_10 = "172.19.4.10"
SRC_118 = "172.19.4.118"
GRP_10, PORT_10 = "239.233.58.10", 5011
GRP_118, PORT_118 = "239.233.58.20", 5022

# Real capture facts (WO-041, independently verified).
_GOLDEN = {
    "source_ip": "172.19.4.118",
    "dest_ip": "239.233.18.30",
    "port": 5033,
    "payload_type": 8,
    "sample_rate": 8000,
    "channels": 1,
}

_THIS_DIR = Path(__file__).resolve().parent
_APP_DIR = _THIS_DIR.parent / "app"


# ---------------------------------------------------------------------------
# Deterministic RTP / pcapng builders (reuse the WO-041 synthetic technique)
# ---------------------------------------------------------------------------


def _rtp_packet(seq: int, ssrc: int, ts: int, payload: bytes) -> bytes:
    """A minimal RFC 3550 RTP v2 datagram (PT=8, 160-byte payload)."""
    return (
        struct.pack(">BBHII", 0x80, 8, seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc & 0xFFFFFFFF)
        + payload
    )


def _eth_frame(src_ip: str, dst_ip: str, sport: int, dport: int, rtp: bytes) -> bytes:
    eth = b"\x00" * 12 + struct.pack(">H", 0x0800)
    total_len = 20 + 8 + len(rtp)
    ip = struct.pack(
        ">BBHHHBBH4s4s", 0x45, 0, total_len, 0, 0, 64, 17, 0,
        bytes(int(x) for x in src_ip.split(".")),
        bytes(int(x) for x in dst_ip.split(".")),
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


def _write_capture(
    path: str,
    *,
    src_ip: str,
    dst_ip: str,
    sport: int,
    dport: int,
    ssrc: int,
    plan: list[tuple[str, int]],
) -> int:
    """Write a deterministic pcapng carrying one RTP stream.

    ``plan`` is a list of ``(kind, count)`` frames in time order, where ``kind``
    is ``"speech"`` or ``"silence"``.  Each frame is one 20 ms / 160-sample
    G.711 A-law packet (PT=8).  Returns the number of frames written.
    """
    frames: list[bytes] = []
    seq, ts = 1000, 1000
    for kind, count in plan:
        byte = SPEECH_BYTE if kind == "speech" else SILENCE_BYTE
        payload = bytes([byte]) * FRAME_SAMPLES
        for _ in range(count):
            rtp = _rtp_packet(seq, ssrc, ts, payload)
            frames.append(_eth_frame(src_ip, dst_ip, sport, dport, rtp))
            seq += 1
            ts += FRAME_SAMPLES
    data = _pcapng_shb() + _pcapng_idb() + b"".join(
        _pcapng_epb(f, i) for i, f in enumerate(frames)
    )
    with open(path, "wb") as fh:
        fh.write(data)
    return len(frames)


# Two separate transmissions separated by a 500 ms silence gap.
PLAN_TWO = [
    ("silence", 25),  # pre-roll background
    ("speech", 40),   # transmission A (800 ms)
    ("silence", 60),  # tail -> finalize A (1000 ms silence)
    ("silence", 25),  # inter-transmission gap (500 ms)
    ("speech", 40),   # transmission B (800 ms)
    ("silence", 60),  # tail -> finalize B (1000 ms silence)
]

# A single transmission (cold-start).
PLAN_ONE = [
    ("silence", 25),
    ("speech", 40),
    ("silence", 60),
]


# ---------------------------------------------------------------------------
# Spy / counting collaborators (canonical boundary observation only)
# ---------------------------------------------------------------------------


class _SpyRepository:
    def __init__(self) -> None:
        self.saved: list[Event] = []

    def save(self, event: Event) -> None:
        self.saved.append(event)


class _SpyProjection:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)


class _CountingFactory:
    """Wraps the real EventFactory and counts ``create_event`` invocations."""

    def __init__(self, inner: EventFactory) -> None:
        self._inner = inner
        self.calls = 0

    def create_event(self, *args, **kwargs) -> Event:
        self.calls += 1
        return self._inner.create_event(*args, **kwargs)


class _FakeAdapter:
    def start(self) -> None:  # pragma: no cover - unused by _process_raw
        return None

    def stop(self) -> None:  # pragma: no cover - unused
        return None

    def health(self) -> bool:  # pragma: no cover - unused
        return True

    def read_events(self) -> list[dict[str, Any]]:  # pragma: no cover - unused
        return []

    def source_name(self) -> str:  # pragma: no cover - unused
        return "radio"


def _audio_config(
    *,
    source_name: str,
    group: str,
    port: int,
) -> AudioConfig:
    return AudioConfig(
        multicast_address=group,
        multicast_port=port,
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=8,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        packetization_ms=20,
        source_name=source_name,
        join_interface="127.0.0.1",
        network_interface="AUTO",
        frame_timeout=0.2,
    )


def _compose(
    reader: RtpCaptureReader,
    audio_cfg: AudioConfig,
    archive_root: str,
    *,
    count_factory: bool = False,
) -> dict[str, Any]:
    """Run the full production radio-side composition + canonical boundary.

    Real radio RTP frames -> TransmissionRecorder (VAD/segment/WAV) -> RAW ->
    AdapterRuntime._process_raw -> EventFactory.create_event -> EventPipeline.
    """
    stream = reader.read()
    start = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    frames = reader.iter_frames(stream, start=start)

    raws: list[dict[str, Any]] = []
    recorder = TransmissionRecorder(
        audio_cfg,
        RecordingConfig(
            enabled=True,
            vad_enabled=True,
            vad_adaptive=False,
            vad_fixed_threshold=2000.0,
            pre_roll_ms=400,
            post_roll_ms=800,
            min_speech_ms=250,
            silence_timeout_ms=1000,
            max_segment_ms=60000,
            audio_archive_root=archive_root,
            mp3_enabled=False,
        ),
        on_recording=raws.append,
    )
    for frame in frames:
        recorder.on_pcm(frame)
    recorder.on_shutdown()

    pipeline = EventPipeline()
    repo = _SpyRepository()
    proj = _SpyProjection()
    pipeline.set_repository(repo)
    pipeline.set_projection(proj)

    inner = EventFactory(identity_resolver=EventIdentityResolver())
    factory: Any = inner
    if count_factory:
        factory = _CountingFactory(inner)
    runtime = AdapterRuntime(
        adapter=_FakeAdapter(),
        factory=factory,
        pipeline=pipeline,
        name=audio_cfg.source_name,
    )
    for raw in raws:
        runtime._process_raw(raw)

    return {
        "stream": stream,
        "frames": frames,
        "raws": raws,
        "events": repo.saved,
        "projected": proj.events,
        "factory_calls": factory.calls if count_factory else len(raws),
    }


def _synthetic_reader(
    path: str,
    *,
    src_ip: str,
    dst_ip: str,
    sport: int,
    dport: int,
) -> RtpCaptureReader:
    return RtpCaptureReader(
        path, source_ip=src_ip, dest_ip=dst_ip, udp_port=dport, payload_type=8
    )


def _find_real_capture() -> str | None:
    candidates = [
        os.environ.get("WO041_PCAP"),
        "/opt/data/wo041_evidence/radio_rtp.pcapng",
        "/opt/data/uploads/1788382671-3d155d40/test.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    if os.path.isdir("/opt/data/uploads"):
        for name in os.listdir("/opt/data/uploads"):
            p = os.path.join("/opt/data/uploads", name, "test.pcapng")
            if os.path.exists(p):
                return p
    return None


# ---------------------------------------------------------------------------
# TEST-01 — Real radio capture reaches the canonical pipeline
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _find_real_capture() is None,
    reason="real radio capture fixture (radio_rtp.pcapng) not available",
)
def test_real_radio_capture_composes_to_canonical_events(tmp_path) -> None:
    """The REAL captured radio stream (.118) composes into canonical Events."""
    capture = _find_real_capture()
    assert capture is not None, "real capture must be present (skipif guards this)"
    reader = RtpCaptureReader(
        capture,
        source_ip=_GOLDEN["source_ip"],
        dest_ip=_GOLDEN["dest_ip"],
        udp_port=_GOLDEN["port"],
        payload_type=_GOLDEN["payload_type"],
    )
    cfg = _audio_config(source_name="radio", group=_GOLDEN["dest_ip"], port=_GOLDEN["port"])
    result = _compose(reader, cfg, str(tmp_path / "archive"), count_factory=True)

    assert len(result["events"]) >= 1, "real capture must produce a canonical Event"
    assert all(isinstance(e, Event) for e in result["events"]), "all canonical Events"
    assert result["factory_calls"] == len(result["raws"]) == len(result["events"])
    assert len(result["projected"]) == len(result["events"])
    # Source identity preserved.
    assert all(e.source == "radio" for e in result["events"])


# ---------------------------------------------------------------------------
# TEST-02 / TEST-06 — Radio segment reaches the canonical pipeline
# ---------------------------------------------------------------------------


def test_radio_segment_reaches_canonical_pipeline(tmp_path) -> None:
    """One valid radio transmission -> one RAW -> one canonical Event at the
    EventPipeline boundary, projected, source-identified."""
    pcap = str(tmp_path / "one.pcapng")
    _write_capture(
        pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
        ssrc=0x11111111, plan=PLAN_ONE,
    )
    reader = _synthetic_reader(pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)
    cfg = _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118)
    result = _compose(reader, cfg, str(tmp_path / "archive"), count_factory=True)

    assert len(result["raws"]) == 1
    assert len(result["events"]) == 1
    assert isinstance(result["events"][0], Event), "canonical Event, not RAW dict"
    assert result["events"][0].source == "radio-118"
    assert result["projected"][0].event_id == result["events"][0].event_id


# ---------------------------------------------------------------------------
# TEST-03 / TEST-05 — one segment -> one RAW -> one factory call -> one Event
# ---------------------------------------------------------------------------


def test_one_segment_one_raw_one_factory_one_event(tmp_path) -> None:
    """2 valid transmissions -> 2 RAW -> exactly 2 EventFactory calls -> 2 Events."""
    pcap = str(tmp_path / "two.pcapng")
    _write_capture(
        pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
        ssrc=0x22222222, plan=PLAN_TWO,
    )
    reader = _synthetic_reader(pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)
    cfg = _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118)
    result = _compose(reader, cfg, str(tmp_path / "archive"), count_factory=True)

    assert len(result["raws"]) == 2, "2 valid segments -> 2 RAW envelopes"
    assert result["factory_calls"] == 2, "RAW crosses EventFactory exactly once per segment"
    assert len(result["events"]) == 2, "2 RAW -> 2 canonical Events"
    assert len(result["projected"]) == 2
    assert all(isinstance(e, Event) for e in result["events"])


# ---------------------------------------------------------------------------
# TEST-07 / TEST-08 / TEST-09 — metadata, source identity, artifact reference
# ---------------------------------------------------------------------------


def test_radio_metadata_and_artifact_preserved(tmp_path) -> None:
    """Radio recording metadata + audio artifact reference survive into the
    canonical Event (no unexplained metadata loss)."""
    pcap = str(tmp_path / "one.pcapng")
    _write_capture(
        pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
        ssrc=0x33333333, plan=PLAN_ONE,
    )
    reader = _synthetic_reader(pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)
    cfg = _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118)
    result = _compose(reader, cfg, str(tmp_path / "archive"))

    ev = result["events"][0]
    raw = result["raws"][0]
    rec = raw["recording"]

    assert ev.source == "radio-118", "source identity preserved"
    assert ev.payload["content_id"] == raw["content_id"]
    assert ev.payload["audio_recording_id"] == raw["audio_recording_id"]
    # Recording metadata block survives into the canonical payload.
    assert ev.payload["recording"]["source"] == "radio-118"
    assert ev.payload["recording"]["multicast_address"] == GRP_118
    assert ev.payload["recording"]["udp_port"] == PORT_118
    assert ev.payload["recording"]["sha256"] == rec["sha256"]
    assert ev.payload["recording"]["wav_path"] == rec["wav_path"]
    # Audio artifact reference preserved (WAV written + reference carried).
    assert os.path.exists(rec["wav_path"]), "WAV master written"
    assert len(rec["sha256"]) == 64


# ---------------------------------------------------------------------------
# TEST-10 / TEST-11 — .10 / .118 source isolation at the canonical layer
# ---------------------------------------------------------------------------


def test_source_isolation_10_and_118(tmp_path) -> None:
    """.10 and .118 sources produce distinct canonical Events with isolated
    source identity; neither leaks into the other."""
    pcap_10 = str(tmp_path / "s10.pcapng")
    pcap_118 = str(tmp_path / "s118.pcapng")
    _write_capture(pcap_10, src_ip=SRC_10, dst_ip=GRP_10, sport=PORT_10, dport=PORT_10,
                   ssrc=0xAAAAAAAA, plan=PLAN_ONE)
    _write_capture(pcap_118, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
                   ssrc=0xBBBBBBBB, plan=PLAN_ONE)

    r10 = _synthetic_reader(pcap_10, src_ip=SRC_10, dst_ip=GRP_10, sport=PORT_10, dport=PORT_10)
    r118 = _synthetic_reader(pcap_118, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)

    res10 = _compose(r10, _audio_config(source_name="radio-10", group=GRP_10, port=PORT_10),
                     str(tmp_path / "a10"))
    res118 = _compose(r118, _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118),
                      str(tmp_path / "a118"))

    assert len(res10["events"]) == 1 and len(res118["events"]) == 1
    # .10 -> Event representing .10.
    assert res10["events"][0].source == "radio-10"
    assert res10["events"][0].payload["recording"]["multicast_address"] == GRP_10
    assert res10["events"][0].payload["recording"]["udp_port"] == PORT_10
    # .118 -> Event representing .118.
    assert res118["events"][0].source == "radio-118"
    assert res118["events"][0].payload["recording"]["multicast_address"] == GRP_118
    assert res118["events"][0].payload["recording"]["udp_port"] == PORT_118
    # No cross-contamination.
    assert res10["events"][0].source != "radio-118"
    assert res118["events"][0].source != "radio-10"
    assert res10["events"][0].payload["recording"]["multicast_address"] != GRP_118
    assert res118["events"][0].payload["recording"]["multicast_address"] != GRP_10


# ---------------------------------------------------------------------------
# TEST-12 — cold start (first valid segment, no prior state)
# ---------------------------------------------------------------------------


def test_cold_start_first_valid_segment(tmp_path) -> None:
    """A fresh recorder (no prior segment/session state) produces the first
    valid segment and its canonical Event correctly."""
    pcap = str(tmp_path / "cold.pcapng")
    _write_capture(
        pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
        ssrc=0x44444444, plan=PLAN_ONE,
    )
    reader = _synthetic_reader(pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)
    cfg = _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118)
    result = _compose(reader, cfg, str(tmp_path / "archive"), count_factory=True)

    # No warm-up: the very first transmission in the stream is the first Event.
    assert len(result["events"]) == 1
    assert result["factory_calls"] == 1
    assert result["events"][0].payload["content_id"] == result["raws"][0]["content_id"]
    # The first event's timestamp derives from the first segment start.
    assert result["events"][0].timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# TEST-13 — sequential segments map one-to-one, no merge / duplicate
# ---------------------------------------------------------------------------


def test_sequential_segments_map_one_to_one(tmp_path) -> None:
    """Segment A and segment B map to corresponding canonical Events A and B;
    no merge, no duplicate, no canonical-level split/merge."""
    pcap = str(tmp_path / "seq.pcapng")
    _write_capture(
        pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118,
        ssrc=0x55555555, plan=PLAN_TWO,
    )
    reader = _synthetic_reader(pcap, src_ip=SRC_118, dst_ip=GRP_118, sport=PORT_118, dport=PORT_118)
    cfg = _audio_config(source_name="radio-118", group=GRP_118, port=PORT_118)
    result = _compose(reader, cfg, str(tmp_path / "archive"))

    assert len(result["events"]) == 2, "exactly 2 events for 2 segments"
    a, b = result["events"]
    # Distinct content identity (no duplicate).
    assert a.event_id != b.event_id
    assert a.payload["content_id"] != b.payload["content_id"]
    # Chronological ordering preserved (A before B), no merge.
    assert a.timestamp <= b.timestamp
    # No canonical-level split/merge: one Event per segment.
    assert result["raws"][0]["recording"]["source"] == "radio-118"
    assert result["raws"][1]["recording"]["source"] == "radio-118"


# ---------------------------------------------------------------------------
# TEST-14 — bypass / second-path audit (radio/audio production producers)
# ---------------------------------------------------------------------------

_RADIO_AUDIO_PROD = [
    _APP_DIR / "audio" / "orchestrator.py",
    _APP_DIR / "audio" / "source_adapter.py",
    _APP_DIR / "audio" / "recorder.py",
    _APP_DIR / "audio" / "segmenter.py",
    _APP_DIR / "audio" / "rtp_receiver.py",
    _APP_DIR / "audio" / "rtp_capture.py",
    _APP_DIR / "event_sources" / "adapters" / "radio_source_adapter.py",
    _APP_DIR / "event_sources" / "adapters" / "radio_parser.py",
]


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _calls_attr(tree: ast.Module, attr: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
    ]


def _constructs(tree: ast.Module, name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
    ]


def test_no_radio_audio_bypass_path() -> None:
    """The radio/audio production producers are producer-only: no canonical
    Event construction, no EventFactory.create_event, no EventPipeline, no
    direct persistence, no projection/checkpoint ownership.  The single
    production create_event caller must remain AdapterRuntime."""
    forbidden = ("event_pipeline", "event_repository", "repositories", "projection", "checkpoint", "durable")
    for path in _RADIO_AUDIO_PROD:
        tree = _parse(path)
        assert tree is not None, f"{path.name}: radio/audio producer must be valid Python"
        # No canonical Event layer import.
        ev_imports = [i for i in _imports(tree) if i == "app.event" or i.startswith("app.event.")]
        assert not ev_imports, f"{path.name}: imports canonical Event layer {ev_imports}"
        # No direct Event construction.
        assert not _constructs(tree, "Event"), f"{path.name}: constructs canonical Event"
        # No EventFactory.create_event caller.
        assert not _calls_attr(tree, "create_event"), f"{path.name}: calls EventFactory.create_event"
        # No EventPipeline instantiation.
        assert not _constructs(tree, "EventPipeline"), f"{path.name}: instantiates EventPipeline"
        # No direct persistence / projection / checkpoint ownership.
        bad_imports = [i for i in _imports(tree) if any(frag in i for frag in forbidden)]
        assert not bad_imports, f"{path.name}: owns lifecycle component {bad_imports}"
        assert not _calls_attr(tree, "save"), f"{path.name}: calls repository.save() directly"

    # Single production create_event caller remains the canonical AdapterRuntime.
    runtime_path = _APP_DIR / "event_sources" / "runtime" / "adapter_runtime.py"
    runtime_tree = _parse(runtime_path)
    assert runtime_tree is not None
    assert _calls_attr(runtime_tree, "create_event"), (
        "AdapterRuntime must be the single production create_event caller"
    )
    callers = []
    for p in sorted(_APP_DIR.rglob("*.py")):
        if p.name == "__init__.py":
            continue
        t = _parse(p)
        if t is None:
            continue
        if _calls_attr(t, "create_event"):
            callers.append(str(p.relative_to(_APP_DIR)))
    assert callers == ["event_sources/runtime/adapter_runtime.py"], (
        f"exactly one production create_event caller required, got {callers}"
    )
