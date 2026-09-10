"""WO-058 — Production radio recording/VAD/WAV composition activation tests.

WO-058 activates the already-implemented radio recording pipeline in the
production source composition.  Before this change the production catalog
registered ``multicast_audio`` with recording DISABLED (no ``vad_enabled``),
so the production-composed radio adapter never engaged the existing

    RTP -> FlowRouter -> per-flow recorder -> VAD -> WAV -> recording-raw
    -> existing canonical pipeline

path.  These tests prove the production catalog itself activates recording, and
that the resulting recording raw flows through the canonical boundary
(``AdapterRuntime`` -> ``EventFactory`` -> ``EventPipeline``) into the durable
journal.

They do NOT construct ``MulticastAudioSourceAdapter`` directly for the primary
production-composition tests: the adapter is built by the production factory
from the production catalog through the real registration path.  STT is
intentionally left disabled (no ``stt`` block), so no transcript is fabricated
and no test transcriber becomes a production fallback.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any

import pytest

import app.database.session as session_mod
from app.audio.flow_router import FlowKey
from app.audio.rtp_capture import RtpCaptureReader
from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.bootstrap import create_production_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event_sources.config.production_source_config import (
    PRODUCTION_SOURCE_CATALOG,
    build_production_adapter_factory,
    build_production_source_provider,
)
import backend.main as main

SAMPLE_RATE = 8000
CHANNELS = 1

# Verified real-capture facts (from the WO-041 golden capture).  The production
# catalog uses the SAME multicast group/port as the golden capture, so the
# recording raw carries the production multicast identity.
GOLDEN = {
    "source_ip": "172.19.4.118",
    "dest_ip": "239.233.18.30",
    "port": 5033,
    "payload_type": 8,
    "ssrc": 536816391,
    "packet_count": 1772,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str):
    """Configure the canonical GLOBAL session manager to a fresh file SQLite."""
    manager = configure_session_manager(f"sqlite:///{db_path}")
    yield manager
    session_mod._session_manager = None


@pytest.fixture()
def runtime(session_manager):
    """The REAL production bootstrap runtime against the configured DB."""
    return create_production_runtime()


@pytest.fixture()
def archive_root() -> str:
    root = tempfile.mkdtemp(prefix="wo058_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_capture() -> str | None:
    candidates = [
        os.environ.get("WO041_PCAP"),
        "/opt/data/wo041_evidence/radio_rtp.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _real_frames() -> list[Any]:
    """Return the decoded PCM frames from the REAL radio RTP capture."""
    path = _find_capture()
    if path is None:
        pytest.skip("real radio RTP capture not available")
    reader = RtpCaptureReader(
        path,
        source_ip=GOLDEN["source_ip"],
        dest_ip=GOLDEN["dest_ip"],
        udp_port=GOLDEN["port"],
        payload_type=GOLDEN["payload_type"],
    )
    stream = reader.read()
    start = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    frames = list(reader.iter_frames(stream, start=start))
    assert len(frames) == GOLDEN["packet_count"], "real capture frame count drifted"
    return frames


def _production_radio(runtime):
    """Register the production catalog radio source into ``runtime``.

    The adapter is built by the production factory from the production catalog
    through the real registration path — the test does NOT construct
    ``MulticastAudioSourceAdapter`` directly.

    Returns ``(adapter, aruntime)``.
    """
    provider = build_production_source_provider()
    factory = build_production_adapter_factory()
    registered = main.register_sources(runtime, provider, factory)
    assert registered == ["radio"]
    assert runtime.supervisor.list_runtimes() == ["radio"]
    aruntime = runtime.supervisor.get_runtime("radio")
    adapter = aruntime._adapter
    assert isinstance(adapter, MulticastAudioSourceAdapter)
    return adapter, aruntime


def _feed_capture_and_finalize(adapter, archive_root: str) -> list[dict[str, Any]]:
    """Feed the real RTP capture through the production-composed adapter.

    Redirects the recorder archive root to ``archive_root`` so the WAV/MP3
    artifacts are written outside the repository working tree (the production
    catalog uses the documented default ``audio_archive_root="audio"``).  The
    adapter itself is untouched; only the storage location is redirected.

    Returns the recording raw dicts queued by the adapter.
    """
    adapter._running = True
    rec = adapter._recorder
    assert rec is not None, "production recording must engage the recorder"
    rec._archive_root = archive_root
    for frame in _real_frames():
        adapter._on_pcm(frame)
    rec.on_shutdown()
    return adapter.read_events()


# ---------------------------------------------------------------------------
# WO058-01 — production recording activation
# ---------------------------------------------------------------------------


def test_wo058_01_production_recording_activation(runtime) -> None:
    """The production catalog activates recording on the radio adapter."""
    adapter, _ = _production_radio(runtime)
    try:
        assert adapter._recording_enabled is True
        # Recording activation engages the existing WO-055 FlowRouter.
        assert adapter._flow_router is not None
        # The recorder is available (created lazily on access).
        assert adapter._recorder is not None
        # STT remains disabled (no 'stt' block in the production catalog).
        assert adapter.stt_state == "DISABLED"
        assert adapter._stt_worker is None
    finally:
        adapter.stop()


def test_wo058_01b_production_catalog_declares_recording() -> None:
    """The production catalog source declares ``vad_enabled`` explicitly."""
    matches = [d for d in PRODUCTION_SOURCE_CATALOG if d.adapter_type == "multicast_audio"]
    assert matches, "production catalog must declare a multicast_audio source"
    definition = matches[0]
    assert definition.config.get("vad_enabled") is True


# ---------------------------------------------------------------------------
# WO058-02 — real RTP reaches the recording path
# ---------------------------------------------------------------------------


def test_wo058_02_real_rtp_produces_recording(runtime, archive_root) -> None:
    """The production-composed adapter turns real RTP into a finalized WAV."""
    adapter, _ = _production_radio(runtime)
    try:
        raws = _feed_capture_and_finalize(adapter, archive_root)
        assert raws, "production-composed adapter must produce at least one recording raw"
        for raw in raws:
            assert "recording" in raw, "a recording raw must carry a 'recording' block"
            rec = raw["recording"]
            assert rec["wav_path"], "a finalized WAV path must be present"
            assert os.path.exists(rec["wav_path"]), "the WAV master must be written"
            assert len(rec["sha256"]) == 64, "the WAV must be SHA-256 hashed"
            # The capture is a continuous speech stream that is force-finalized
            # at recorder shutdown (no natural silence-timeout within the
            # capture), so ``complete`` is False and the reason is
            # ``source_shutdown``.  That is correct fail-closed recording
            # behaviour, not a defect: the WAV master is still written/hashed.
            assert rec["complete"] is False
            assert rec["finalize_reason"] == "source_shutdown"
            assert rec["sample_rate"] == SAMPLE_RATE
            assert rec["channels"] == CHANNELS
            # Production multicast identity is preserved on the recording.
            assert rec["multicast_address"] == "239.233.18.30"
            assert rec["udp_port"] == 5033
    finally:
        adapter.stop()


# ---------------------------------------------------------------------------
# WO058-03 — canonical durable path
# ---------------------------------------------------------------------------


def test_wo058_03_recording_reaches_durable_journal(runtime, archive_root) -> None:
    """The recording raw crosses the canonical boundary into the durable journal."""
    repo = runtime.event_runtime.pipeline._repository
    adapter, aruntime = _production_radio(runtime)
    try:
        raws = _feed_capture_and_finalize(adapter, archive_root)
        assert raws, "production-composed adapter must produce at least one recording raw"
        for raw in raws:
            # Drive through the ONE existing canonical boundary (no direct Event
            # construction, no direct repository insert).
            aruntime._process_raw(raw)

        assert repo.count() >= 1, "at least one recording event must be durable"
        events = repo.list_all()
        assert all(isinstance(e, Event) for e in events)
        assert all(e.source == "radio" for e in events)
        # At least one durable event carries the recording payload.
        assert any("recording" in e.payload for e in events)
    finally:
        adapter.stop()


# ---------------------------------------------------------------------------
# WO058-04 — STT remains disabled
# ---------------------------------------------------------------------------


def test_wo058_04_stt_remains_disabled(runtime, archive_root) -> None:
    """Activating recording does NOT activate STT or fabricate a transcript."""
    adapter, _ = _production_radio(runtime)
    try:
        # No production STT engine is introduced/activated by the catalog.
        assert adapter.stt_state == "DISABLED"
        assert adapter._stt_worker is None

        raws = _feed_capture_and_finalize(adapter, archive_root)
        # Recording activation produces recording raws only — no transcript raw.
        assert raws, "recording activation must still produce a recording raw"
        for raw in raws:
            assert "recording" in raw
            assert "transcript" not in raw, "recording activation must not fabricate a transcript"
            assert "detected_callsigns" not in raw
    finally:
        adapter.stop()


# ---------------------------------------------------------------------------
# WO058-05 — flow isolation remains active
# ---------------------------------------------------------------------------


def test_wo058_05_flow_isolation_active(runtime) -> None:
    """Production recording activation engages the existing FlowRouter (WO-055)."""
    adapter, _ = _production_radio(runtime)
    try:
        assert adapter._flow_router is not None, \
            "recording-enabled production source must use flow isolation"
        router = adapter._flow_router

        # Two distinct UDP source flows resolve to two distinct per-flow
        # pipelines with independent RTP trackers (WO-055 contract).
        k_a = FlowKey("10.0.0.1", 1000, 5033)
        k_b = FlowKey("10.0.0.2", 2000, 5033)
        pa = router.get_or_create(k_a)
        pb = router.get_or_create(k_b)
        assert pa is not pb
        assert pa.tracker is not pb.tracker
        assert router.flow_count() == 2

        # A -> B -> A preserves A's independent state.
        pa2 = router.get_or_create(k_a)
        assert pa2 is pa
    finally:
        adapter.stop()
