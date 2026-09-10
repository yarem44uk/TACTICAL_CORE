"""WO-055 — UDP source flow isolation regression tests (CORR-02).

The production radio path previously held a single ``RtpStreamTracker`` and a
single ``TransmissionRecorder`` for the whole multicast socket, so two RTP
talkers sharing one group/port were multiplexed into shared state.  These tests
prove the WO-055 flow-isolation correction: each distinct UDP source flow owns
its own RTP tracker and recording pipeline, and ``A -> B -> A`` preserves A's
state.

Coverage:
  * TEST 1 — single flow produces the expected path (backward compat).
  * TEST 2 — two simultaneous flows on one group/port keep independent state.
  * TEST 3 — A -> B -> A preserves A's state.
  * TEST 4 — FlowKey determinism (same key -> same flow; different -> different).
  * TEST 5 — no accidental shared tracker between flows.
  * TEST 6 — cleanup / bounded state (no unbounded map growth).
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import time
from typing import Any

import pytest

from app.audio.alaw import alaw_encode_byte
from app.audio.audio_config import AudioConfig
from app.audio.flow_router import FlowKey, FlowRouter
from app.audio.recorder import TransmissionRecorder
from app.audio.recording_config import RecordingConfig
from app.audio.rtp_receiver import RtpReceiver
from app.audio.rtp_simulator import RtpSimulator, build_rtp_packet

SAMPLE_RATE = 8000
CHANNELS = 1
FRAME_SAMPLES = 160  # 20 ms at 8 kHz
FRAME_MS = 20

# A speech tone (RMS ~20000) and a background/silence level (RMS ~50).
SPEECH = 20000
SILENCE = 50


@pytest.fixture()
def archive() -> str:
    root = tempfile.mkdtemp(prefix="wo055_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _rtp_config(port: int, group: str = "239.255.0.1", **overrides: Any) -> AudioConfig:
    return AudioConfig(
        multicast_address=group,
        multicast_port=port,
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=8,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        source_name="radio",
        join_interface="127.0.0.1",
        network_interface="AUTO",
        frame_timeout=0.2,
        **overrides,
    )


def _pcm(value: int, samples: int = FRAME_SAMPLES) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _rtp_bytes(ssrc: int, seq: int, ts: int, value: int = 0x55, n: int = 160) -> bytes:
    """Build a raw RTP packet (PT=8, A-law payload)."""
    payload = bytes([value & 0xFF]) * n
    return build_rtp_packet(
        payload_type=8, sequence_number=seq, timestamp=ts, ssrc=ssrc, payload=payload
    )


def _speech_rtp(ssrc: int, seq: int, ts: int) -> bytes:
    """A-law payload that decodes to a loud speech tone (RMS ~20000)."""
    payload = bytes(alaw_encode_byte(SPEECH) for _ in range(FRAME_SAMPLES))
    return build_rtp_packet(
        payload_type=8, sequence_number=seq, timestamp=ts, ssrc=ssrc, payload=payload
    )


class _SpyRecorder:
    """A recorder stand-in that captures frames and records shutdown."""

    def __init__(self) -> None:
        self.frames: list[Any] = []
        self.shutdown_calls = 0

    def on_pcm(self, frame: Any) -> None:
        self.frames.append(frame)

    def on_shutdown(self) -> None:
        self.shutdown_calls += 1

    def snapshot(self) -> dict[str, Any]:
        return {"frames": len(self.frames), "shutdowns": self.shutdown_calls}


# ---------------------------------------------------------------------------
# TEST 4 — FlowKey determinism
# ---------------------------------------------------------------------------


def test_flow_key_determinism() -> None:
    a = FlowKey("10.0.0.1", 1000, 5033)
    b = FlowKey("10.0.0.1", 1000, 5033)
    assert a == b
    assert hash(a) == hash(b)
    # Same talker, different source port -> different flow.
    assert FlowKey("10.0.0.1", 1001, 5033) != a
    # Different talker (source IP) -> different flow.
    assert FlowKey("10.0.0.2", 1000, 5033) != a
    # Different destination port (channel) -> different flow.
    assert FlowKey("10.0.0.1", 1000, 5034) != a


# ---------------------------------------------------------------------------
# TEST 5 — no accidental shared tracker
# ---------------------------------------------------------------------------


def test_flows_have_distinct_trackers() -> None:
    router = FlowRouter(recorder_factory=lambda fk: None, max_flows=10)
    k_a = FlowKey("10.0.0.1", 1000, 5033)
    k_b = FlowKey("10.0.0.2", 2000, 5033)
    pa = router.get_or_create(k_a)
    pb = router.get_or_create(k_b)
    assert pa is not pb
    assert pa.tracker is not pb.tracker
    assert router.flow_count() == 2
    # Same key resolves to the same pipeline/tracker.
    assert router.get_or_create(k_a) is pa


# ---------------------------------------------------------------------------
# TEST 6 — cleanup / bounded state
# ---------------------------------------------------------------------------


def test_flow_router_bounded_eviction() -> None:
    shutdowns: list[FlowKey] = []

    def factory(fk: FlowKey) -> Any:
        rec = _SpyRecorder()
        orig_shutdown = rec.on_shutdown

        def _shutdown() -> None:
            shutdowns.append(fk)
            orig_shutdown()

        rec.on_shutdown = _shutdown
        return rec

    router = FlowRouter(recorder_factory=factory, max_flows=2)
    k1 = FlowKey("10.0.0.1", 1000, 5033)
    k2 = FlowKey("10.0.0.2", 2000, 5033)
    k3 = FlowKey("10.0.0.3", 3000, 5033)

    router.get_or_create(k1)
    router.get_or_create(k2)
    router.get_or_create(k3)

    # Bounded: the map never exceeds max_flows.
    assert router.flow_count() == 2
    assert router.has_flow(k3)
    assert router.has_flow(k2)
    # k1 was the least-recently-used flow and was evicted (its recorder finalized).
    assert not router.has_flow(k1)
    assert len(shutdowns) == 1
    assert shutdowns[0] == k1


def test_flow_router_shutdown_all_finalizes_recorders() -> None:
    recs: list[_SpyRecorder] = []

    def factory(fk: FlowKey) -> Any:
        rec = _SpyRecorder()
        recs.append(rec)
        return rec

    router = FlowRouter(recorder_factory=factory, max_flows=10)
    router.get_or_create(FlowKey("10.0.0.1", 1000, 5033))
    router.get_or_create(FlowKey("10.0.0.2", 2000, 5033))
    assert len(recs) == 2
    router.shutdown_all()
    assert all(r.shutdown_calls == 1 for r in recs)
    assert router.flow_count() == 0


# ---------------------------------------------------------------------------
# TEST 1 — single flow produces the expected path (backward compat)
# ---------------------------------------------------------------------------


def test_single_flow_single_source_path() -> None:
    cfg = _rtp_config(5033)
    router = FlowRouter(recorder_factory=lambda fk: None, max_flows=10)
    frames: list[Any] = []
    receiver = RtpReceiver(cfg, on_pcm=frames.append, flow_router=router)
    addr_a = ("10.0.0.1", 1000)

    for i in range(5):
        receiver._handle_payload(_rtp_bytes(0xAAAA, i, i * 160), addr_a)

    # All frames delivered in sequence to the downstream callback.
    assert len(frames) == 5
    assert [f.sequence_number for f in frames] == [0, 1, 2, 3, 4]
    assert all(f.ssrc == 0xAAAA for f in frames)
    assert router.flow_count() == 1


# ---------------------------------------------------------------------------
# TEST 2 — two simultaneous flows keep independent state
# ---------------------------------------------------------------------------


def test_two_flows_independent_state() -> None:
    cfg = _rtp_config(5033)
    router = FlowRouter(recorder_factory=lambda fk: _SpyRecorder(), max_flows=10)
    receiver = RtpReceiver(cfg, on_pcm=lambda f: None, flow_router=router)
    addr_a = ("10.0.0.1", 1000)
    addr_b = ("10.0.0.2", 2000)

    receiver._handle_payload(_rtp_bytes(0xAAAA, 1, 0), addr_a)
    receiver._handle_payload(_rtp_bytes(0xAAAA, 2, 160), addr_a)
    receiver._handle_payload(_rtp_bytes(0xBBBB, 100, 0), addr_b)
    receiver._handle_payload(_rtp_bytes(0xBBBB, 101, 160), addr_b)

    snap_a = router.get_or_create(FlowKey("10.0.0.1", 1000, 5033)).tracker.snapshot()
    snap_b = router.get_or_create(FlowKey("10.0.0.2", 2000, 5033)).tracker.snapshot()

    assert snap_a["current_ssrc"] == 0xAAAA
    assert snap_b["current_ssrc"] == 0xBBBB
    assert snap_a["packets_received"] == 2
    assert snap_b["packets_received"] == 2
    assert snap_a["last_sequence"] == 2
    assert snap_b["last_sequence"] == 101
    assert snap_a["sequence_gaps"] == 0
    assert snap_b["sequence_gaps"] == 0
    assert snap_a != snap_b


# ---------------------------------------------------------------------------
# TEST 3 — A -> B -> A preserves A's state
# ---------------------------------------------------------------------------


def test_a_b_a_preserves_a_state() -> None:
    cfg = _rtp_config(5033)
    router = FlowRouter(recorder_factory=lambda fk: _SpyRecorder(), max_flows=10)
    receiver = RtpReceiver(cfg, on_pcm=lambda f: None, flow_router=router)
    addr_a = ("10.0.0.1", 1000)
    addr_b = ("10.0.0.2", 2000)

    receiver._handle_payload(_rtp_bytes(0xAAAA, 1, 0), addr_a)  # A1
    receiver._handle_payload(_rtp_bytes(0xBBBB, 100, 0), addr_b)  # B1
    receiver._handle_payload(_rtp_bytes(0xAAAA, 2, 160), addr_a)  # A2

    snap_a = router.get_or_create(FlowKey("10.0.0.1", 1000, 5033)).tracker.snapshot()
    snap_b = router.get_or_create(FlowKey("10.0.0.2", 2000, 5033)).tracker.snapshot()

    # A's state survives B: A's tracker saw only A1, A2 in sequence.
    assert snap_a["current_ssrc"] == 0xAAAA
    assert snap_a["packets_received"] == 2
    assert snap_a["last_sequence"] == 2
    assert snap_a["sequence_gaps"] == 0
    assert snap_a["ssrc_transitions"] == 0
    # B never contaminated A.
    assert snap_b["packets_received"] == 1
    assert snap_b["last_sequence"] == 100
    assert snap_b["current_ssrc"] == 0xBBBB


def test_a_b_a_duplicate_detection_per_flow() -> None:
    """A duplicate of A is still detected after B interleaves (WO-039-A §5)."""
    cfg = _rtp_config(5033)
    router = FlowRouter(recorder_factory=lambda fk: _SpyRecorder(), max_flows=10)
    frames_a: list[Any] = []
    frames_b: list[Any] = []
    addr_a = ("10.0.0.1", 1000)
    addr_b = ("10.0.0.2", 2000)

    def _on_pcm(frame: Any) -> None:
        pass

    receiver = RtpReceiver(cfg, on_pcm=_on_pcm, flow_router=router)
    # Feed A seq 1, B seq 100, then a duplicate A seq 1 again.
    receiver._handle_payload(_rtp_bytes(0xAAAA, 1, 0), addr_a)
    receiver._handle_payload(_rtp_bytes(0xBBBB, 100, 0), addr_b)
    receiver._handle_payload(_rtp_bytes(0xAAAA, 1, 0), addr_a)

    snap_a = router.get_or_create(FlowKey("10.0.0.1", 1000, 5033)).tracker.snapshot()
    # The duplicate was suppressed (not emitted twice), not treated as INITIAL.
    assert snap_a["duplicates"] == 1
    assert snap_a["packets_received"] == 1
    assert snap_a["last_sequence"] == 1


# ---------------------------------------------------------------------------
# End-to-end: two talkers on one group/port via the production adapter
# ---------------------------------------------------------------------------


def _unique_port() -> int:
    import itertools

    if not hasattr(_unique_port, "n"):
        _unique_port.n = 0
    _unique_port.n += 1
    return 44000 + _unique_port.n * 2


def _wait_for_bind(receiver: RtpReceiver, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if receiver.is_bound():
            return
        time.sleep(0.02)
    time.sleep(0.05)


def test_two_talkers_same_group_port_produce_two_flows(archive) -> None:
    """Two RTP talkers on one group/port resolve to two distinct flows."""
    from app.audio.source_adapter import MulticastAudioSourceAdapter
    from app.event_sources.config.source_definition import SourceDefinition

    port = _unique_port()
    group = "239.255.6.0"
    definition = SourceDefinition(
        name="radio-rtp",
        adapter_type="multicast_audio",
        config={
            "protocol": "rtp",
            "multicast_address": group,
            "multicast_port": port,
            "codec": "pcm_alaw",
            "payload_type": 8,
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "source_name": "radio",
            "join_interface": "127.0.0.1",
            "vad_enabled": True,
            "vad_fixed_threshold": 2000.0,
            "audio_archive_root": archive,
            "mp3_enabled": False,
        },
    )
    adapter = MulticastAudioSourceAdapter(definition)
    assert adapter._flow_router is not None, "recording-enabled source must use flow isolation"
    adapter.start()
    sim_a: RtpSimulator | None = None
    sim_b: RtpSimulator | None = None
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline:
            recv = getattr(adapter, "_receiver", None)
            if recv is not None and recv.is_bound():
                break
            time.sleep(0.02)
        sim_a = RtpSimulator(adapter._config, ssrc=0xAAAA)
        sim_b = RtpSimulator(adapter._config, ssrc=0xBBBB)
        # Interleave speech from two talkers into the same group/port.
        for _ in range(40):
            sim_a.send_pcm(_pcm(SPEECH))
        for _ in range(40):
            sim_b.send_pcm(_pcm(SPEECH))
        deadline = time.time() + 5.0
        while time.time() < deadline and adapter._flow_router.flow_count() < 2:
            time.sleep(0.05)
        assert adapter._flow_router.flow_count() == 2, (
            "two talkers on one group/port must be split into two flows"
        )
    finally:
        adapter.stop()
        if sim_a is not None:
            sim_a.close()
        if sim_b is not None:
            sim_b.close()
