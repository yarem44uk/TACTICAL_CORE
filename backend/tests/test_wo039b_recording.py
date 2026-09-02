"""WO-039-B tests — VAD + per-transmission WAV master + MP3 derivative.

These tests exercise the real recording path (W-039-B §35):

    REAL RTP/PCM -> REAL VAD -> REAL segment state -> REAL WAV writer
        -> REAL finalized file -> SHA-256 -> MP3

and cover the required cases A–O (W-039-B §34).  Unit tests exercise individual
components; the integration tests drive the complete pipeline from real RTP
(W-039-A) and the real ``test.pcapng`` capture.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import time
import wave
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.audio.alaw import alaw_to_pcm
from app.audio.audio_config import AudioConfig
from app.audio.recorder import (
    TransmissionRecorder,
    build_recording_paths,
    sanitize_source,
)
from app.audio.recording_config import RecordingConfig
from app.audio.rtp_receiver import RtpReceiver
from app.audio.rtp_simulator import RtpSimulator
from app.audio.segmenter import FinalizeReason, SegmentState, TransmissionSegmenter
from app.audio.vad import EnergyVad, VadConfig, pcm_rms
from app.audio.wav_writer import WavWriteError, write_wav_atomic

SAMPLE_RATE = 8000
CHANNELS = 1
FRAME_SAMPLES = 160  # 20 ms at 8 kHz
FRAME_MS = 20
FRAME_BYTES = FRAME_SAMPLES * 2  # S16LE mono

# A speech tone (RMS ~20000) and a background/silence level (RMS ~50).
SPEECH = 20000
SILENCE = 50


def _pcm(value: int, samples: int = FRAME_SAMPLES) -> bytes:
    return struct.pack(f"<{samples}h", *([value] * samples))


def _frame(value: int, t: datetime, samples: int = FRAME_SAMPLES) -> SimpleNamespace:
    return SimpleNamespace(pcm=_pcm(value, samples), received_at=t)


def _feed(recorder: TransmissionRecorder, values: list[int], t0: datetime) -> datetime:
    """Feed one frame per value, advancing the clock by ``FRAME_MS``."""
    cur = t0
    for value in values:
        recorder.on_pcm(_frame(value, cur))
        cur += timedelta(milliseconds=FRAME_MS)
    return cur


def _mkcfg(
    root: str,
    *,
    source: str = "radio",
    vad_adaptive: bool = False,
    fixed: float = 2000.0,
    **overrides,
) -> tuple[AudioConfig, RecordingConfig]:
    audio = AudioConfig(
        multicast_address="239.255.0.1",
        multicast_port=5033,
        protocol="rtp",
        codec="pcm_alaw",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        source_name=source,
    )
    base = dict(
        enabled=True,
        vad_enabled=True,
        vad_adaptive=vad_adaptive,
        vad_fixed_threshold=fixed if not vad_adaptive else None,
        pre_roll_ms=400,
        post_roll_ms=800,
        min_speech_ms=250,
        silence_timeout_ms=1000,
        max_segment_ms=60000,
        audio_archive_root=root,
        mp3_enabled=False,
    )
    base.update(overrides)
    rec = RecordingConfig(**base)
    return audio, rec


def _mkrecorder(
    root: str,
    *,
    source: str = "radio",
    vad_adaptive: bool = False,
    fixed: float = 2000.0,
    **overrides,
) -> tuple[TransmissionRecorder, list[dict]]:
    audio, rec = _mkcfg(
        root, source=source, vad_adaptive=vad_adaptive, fixed=fixed, **overrides
    )
    captured: list[dict] = []
    recorder = TransmissionRecorder(audio, rec, on_recording=captured.append)
    return recorder, captured


def _read_wav(path: str) -> tuple[int, int, int, list[int]]:
    """Return ``(channels, sample_rate, sampwidth, samples)`` for a WAV."""
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        width = wf.getsampwidth()
        nframes = wf.getnframes()
        data = wf.readframes(nframes)
    samples = list(struct.unpack(f"<{len(data)//2}h", data))
    return channels, rate, width, samples


@pytest.fixture()
def archive() -> str:
    root = tempfile.mkdtemp(prefix="wo039b_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# A — Silence: no recording
# ---------------------------------------------------------------------------


def test_a_silence_produces_no_recording(archive) -> None:
    rec, captured = _mkrecorder(archive)
    _feed(rec, [SILENCE] * 100, datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc))
    assert rec.snapshot()["segments_completed"] == 0
    assert captured == []


# ---------------------------------------------------------------------------
# B — Single transmission: exactly one WAV
# ---------------------------------------------------------------------------


def test_b_single_transmission_one_wav(archive) -> None:
    rec, captured = _mkrecorder(archive)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)  # 500 ms pre-roll background
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))  # 800 ms speech
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))  # 1200 ms tail
    assert rec.snapshot()["segments_completed"] == 1
    assert len(captured) == 1
    ev = captured[0]
    wav = ev["recording"]["wav_path"]
    assert os.path.exists(wav)
    channels, rate, width, samples = _read_wav(wav)
    assert channels == 1
    assert rate == SAMPLE_RATE
    assert width == 2
    # duration ~= 400 pre-roll + 800 speech + 1000 post-roll
    assert abs(len(samples) / SAMPLE_RATE - 2.2) < 0.05


# ---------------------------------------------------------------------------
# C — Pre-roll: the beginning is preserved
# ---------------------------------------------------------------------------


def test_c_pre_roll_preserved(archive) -> None:
    rec, captured = _mkrecorder(archive, pre_roll_ms=400)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)  # 500 ms background -> pre-roll is silence
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    wav = captured[0]["recording"]["wav_path"]
    _, _, _, samples = _read_wav(wav)
    pre_samples = int(0.4 * SAMPLE_RATE)  # 400 ms pre-roll
    # The first 400 ms must be the low-amplitude (pre-roll) background.
    assert all(abs(s) <= SILENCE for s in samples[:pre_samples])
    # The speech region must be high-amplitude.
    assert all(abs(s) > 10000 for s in samples[pre_samples : pre_samples + 2000])


# ---------------------------------------------------------------------------
# D — Post-roll: the ending is preserved
# ---------------------------------------------------------------------------


def test_d_post_roll_preserved(archive) -> None:
    rec, captured = _mkrecorder(archive, post_roll_ms=800)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    wav = captured[0]["recording"]["wav_path"]
    _, _, _, samples = _read_wav(wav)
    # The last 800 ms must be the post-roll silence (low amplitude).
    post_samples = int(0.8 * SAMPLE_RATE)
    assert all(abs(s) <= SILENCE for s in samples[-post_samples:])


# ---------------------------------------------------------------------------
# E — Short pause: speech resumes before timeout -> one transmission
# ---------------------------------------------------------------------------


def test_e_short_pause_one_transmission(archive) -> None:
    rec, captured = _mkrecorder(archive, silence_timeout_ms=1000)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))  # 800 ms speech
    _feed(rec, [SILENCE] * 25, t0 + timedelta(seconds=1.3))  # 500 ms pause < 1000
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=1.8))  # speech resumes
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=2.6))  # finalize
    assert rec.snapshot()["segments_completed"] == 1
    assert len(captured) == 1
    # ~400 pre-roll + 800 + 500 + 800 speech + 1000 post-roll = 3500 ms
    wav = captured[0]["recording"]["wav_path"]
    _, _, _, samples = _read_wav(wav)
    assert abs(len(samples) / SAMPLE_RATE - 3.5) < 0.05


# ---------------------------------------------------------------------------
# F — Transmission end: long silence finalizes
# ---------------------------------------------------------------------------


def test_f_silence_finalizes(archive) -> None:
    rec, captured = _mkrecorder(archive, silence_timeout_ms=1000)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    assert captured[0]["recording"]["finalize_reason"] == "silence_timeout"


# ---------------------------------------------------------------------------
# G — Max segment: long speech finalized at max_segment_ms
# ---------------------------------------------------------------------------


def test_g_max_segment_finalized(archive) -> None:
    rec, captured = _mkrecorder(archive, max_segment_ms=2000)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    # Feed continuous speech for ~4 s (> max_segment 2 s): the long stream is
    # split/finalized at max_segment_ms (W-039-B §12).
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 200, t0 + timedelta(seconds=0.5))
    assert rec.snapshot()["segments_completed"] >= 1
    assert captured[0]["recording"]["finalize_reason"] == "max_segment"
    duration = captured[0]["recording"]["duration_ms"]
    assert abs(duration - 2000) < 100


# ---------------------------------------------------------------------------
# H — Noise: no endless recordings
# ---------------------------------------------------------------------------


def test_h_noise_configured_threshold_no_recording(archive) -> None:
    # Noise below a configured threshold is never speech.
    rec, captured = _mkrecorder(archive, fixed=2000.0)
    _feed(rec, [500] * 200, datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc))
    assert rec.snapshot()["segments_completed"] == 0
    assert captured == []


def test_h_noise_adaptive_no_endless_recording(archive) -> None:
    # Adaptive VAD: constant high energy converges to non-speech (floor rises).
    rec, captured = _mkrecorder(archive, vad_adaptive=True)
    _feed(rec, [15000] * 200, datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc))
    assert rec.snapshot()["segments_completed"] == 0
    assert captured == []
    # The adaptive noise floor should have risen close to the noise energy.
    assert rec.snapshot()["vad_noise_floor"] > 10000


# ---------------------------------------------------------------------------
# I — Multiple sources: independent recordings, no cross-contamination
# ---------------------------------------------------------------------------


def test_i_multiple_sources_independent(archive) -> None:
    rec_a, cap_a = _mkrecorder(archive, source="alpha")
    rec_b, cap_b = _mkrecorder(archive, source="bravo")
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec_a, [SILENCE] * 25, t0)
    _feed(rec_a, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec_a, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    _feed(rec_b, [SILENCE] * 25, t0)
    _feed(rec_b, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec_b, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    assert rec_a.snapshot()["segments_completed"] == 1
    assert rec_b.snapshot()["segments_completed"] == 1
    assert cap_a[0]["recording"]["source"] == "alpha"
    assert cap_b[0]["recording"]["source"] == "bravo"
    assert cap_a[0]["recording"]["wav_path"] != cap_b[0]["recording"]["wav_path"]
    # Independent VAD state.
    assert rec_a.snapshot()["current_recording_id"] is None
    assert rec_b.snapshot()["current_recording_id"] is None


# ---------------------------------------------------------------------------
# J — Disk/write failure: Core stays alive, failure observable
# ---------------------------------------------------------------------------


def test_j_disk_failure_observable(archive) -> None:
    # Make the archive root unusable by placing a regular file where a directory
    # is required: os.makedirs() then fails with NotADirectoryError.
    blocker = os.path.join(archive, "blocker")
    with open(blocker, "w") as fh:
        fh.write("x")
    bad_root = os.path.join(blocker, "sub")
    rec, captured = _mkrecorder(bad_root)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    # The failure is observable, not a crash.
    assert rec.snapshot()["segments_failed"] >= 1
    assert rec.snapshot()["last_error"] is not None
    assert captured == []  # no event for a recording that could not be written


# ---------------------------------------------------------------------------
# K — Restart: completed recordings survive; no temp files masquerade
# ---------------------------------------------------------------------------


def test_k_restart_preserves_completed(archive) -> None:
    rec, captured = _mkrecorder(archive, mp3_enabled=False)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    wav = captured[0]["recording"]["wav_path"]
    # A "restart": a fresh recorder on the same archive root.
    rec2, _ = _mkrecorder(archive)
    assert os.path.exists(wav)
    channels, rate, width, samples = _read_wav(wav)
    assert channels == 1 and rate == SAMPLE_RATE and width == 2
    assert len(samples) > 0
    # No leftover .tmp file that could be mistaken for a valid recording.
    tmp = wav + ".tmp"
    assert not os.path.exists(tmp)


# ---------------------------------------------------------------------------
# L — MP3: generated only after WAV finalization
# ---------------------------------------------------------------------------


def test_l_mp3_only_after_wav(archive) -> None:
    audio, rec = _mkcfg(archive, mp3_enabled=True, mp3_bitrate="64k")
    captured: list[dict] = []
    wav_existed_at_callback: list[bool] = []

    def on_recording(raw):
        captured.append(raw)
        wav_existed_at_callback.append(os.path.exists(raw["recording"]["wav_path"]))

    recorder = TransmissionRecorder(audio, rec, on_recording=on_recording)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(recorder, [SILENCE] * 25, t0)
    _feed(recorder, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(recorder, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    assert recorder.wait_for_mp3(timeout=20)
    # The WAV already existed when the event was emitted (WAV finalized first).
    assert wav_existed_at_callback == [True]
    mp3 = captured[0]["recording"]["mp3_path"]
    assert mp3 is not None
    assert os.path.exists(mp3)
    assert os.path.getsize(mp3) > 0


def test_l_mp3_skipped_on_wav_failure(archive) -> None:
    # When the WAV cannot be written, no MP3 is generated (no orphan derivative).
    blocker = os.path.join(archive, "blocker")
    with open(blocker, "w") as fh:
        fh.write("x")
    bad_root = os.path.join(blocker, "sub")
    rec, captured = _mkrecorder(bad_root, mp3_enabled=True)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    assert captured == []


# ---------------------------------------------------------------------------
# M — WAV SHA-256: matches exact final bytes
# ---------------------------------------------------------------------------


def test_m_wav_sha256_matches(archive) -> None:
    rec, captured = _mkrecorder(archive)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    _feed(rec, [SILENCE] * 25, t0)
    _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
    _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
    wav = captured[0]["recording"]["wav_path"]
    import hashlib

    with open(wav, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    assert digest == captured[0]["recording"]["sha256"]


# ---------------------------------------------------------------------------
# Unit-level: WAV writer atomicity + integrity
# ---------------------------------------------------------------------------


def test_wav_writer_atomic_and_hash(archive) -> None:
    path = os.path.join(archive, "out", "x.wav")
    pcm = struct.pack("<1600h", *([1000] * 1600))
    result = write_wav_atomic(pcm, path, SAMPLE_RATE, CHANNELS)
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    assert result.sample_count == 1600
    assert abs(result.duration_ms - 200.0) < 0.1
    import hashlib

    with open(path, "rb") as fh:
        assert result.sha256 == hashlib.sha256(fh.read()).hexdigest()


def test_wav_writer_rejects_non_frame_multiple(archive) -> None:
    with pytest.raises(WavWriteError):
        write_wav_atomic(b"\x00\x01\x02", os.path.join(archive, "bad.wav"), SAMPLE_RATE, 1)


def test_wav_writer_invalid_params(archive) -> None:
    with pytest.raises(WavWriteError):
        write_wav_atomic(b"", os.path.join(archive, "x.wav"), 0, 1)


# ---------------------------------------------------------------------------
# Unit-level: VAD
# ---------------------------------------------------------------------------


def test_vad_energy_and_detect() -> None:
    vad = EnergyVad(VadConfig(fixed_threshold=2000.0))
    assert pcm_rms(_pcm(20000)) == pytest.approx(20000.0)
    assert vad.detect(_pcm(20000)) is True
    assert vad.detect(_pcm(50)) is False
    assert vad.name == "energy-rms-adaptive"


def test_vad_adaptive_noise_floor_rises() -> None:
    vad = EnergyVad(VadConfig(adaptive=True, noise_percentile=20.0))
    for _ in range(100):
        vad.detect(_pcm(15000))
    assert vad.noise_floor > 10000
    assert vad.detect(_pcm(15000)) is False


# ---------------------------------------------------------------------------
# Unit-level: segmenter state machine
# ---------------------------------------------------------------------------


def test_segmenter_short_pause_keeps_one_segment() -> None:
    seg = TransmissionSegmenter()
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    cur = t0
    # speech
    for _ in range(20):
        seg.process(_pcm(SPEECH), True, cur)
        cur += timedelta(milliseconds=FRAME_MS)
    # short pause (non-speech) < silence timeout
    for _ in range(10):
        seg.process(_pcm(SILENCE), False, cur)
        cur += timedelta(milliseconds=FRAME_MS)
    # speech resumes
    for _ in range(20):
        seg.process(_pcm(SPEECH), True, cur)
        cur += timedelta(milliseconds=FRAME_MS)
    assert seg.state == SegmentState.RECORDING


def test_segmenter_force_finalize_on_shutdown() -> None:
    seg = TransmissionSegmenter()
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    cur = t0
    for _ in range(20):
        seg.process(_pcm(SPEECH), True, cur)
        cur += timedelta(milliseconds=FRAME_MS)
    result = seg.force_finalize(FinalizeReason.SOURCE_SHUTDOWN)
    assert result is not None
    assert result.reason == FinalizeReason.SOURCE_SHUTDOWN
    assert len(result.pcm) > 0
    assert seg.state == SegmentState.IDLE


# ---------------------------------------------------------------------------
# Unit-level: source sanitisation + path confinement
# ---------------------------------------------------------------------------


def test_sanitize_source() -> None:
    assert sanitize_source("radio") == "radio"
    assert sanitize_source("../../etc") == "etc"
    assert sanitize_source("Радіо-1") == "1"
    assert sanitize_source("..") == "source"


def test_build_recording_paths_confined(archive) -> None:
    started = datetime(2026, 9, 2, 10, 30, 0, tzinfo=timezone.utc)
    wav, mp3 = build_recording_paths(archive, "radio", started, "ab" * 32)
    real = os.path.realpath(wav)
    assert real.startswith(os.path.realpath(archive) + os.sep)
    assert wav.endswith(".wav")
    assert mp3.endswith(".mp3")


# ---------------------------------------------------------------------------
# N — Real RTP input: WO-039-A receiver feeds the recorder
# ---------------------------------------------------------------------------


def _unique_port() -> int:
    import itertools

    if not hasattr(_unique_port, "n"):
        _unique_port.n = 0
    _unique_port.n += 1
    return 42000 + _unique_port.n * 2


def _wait_for_bind(receiver: RtpReceiver, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if receiver.is_bound():
            return
        time.sleep(0.02)
    time.sleep(0.05)


def test_n_real_rtp_feeds_recorder(archive) -> None:
    port = _unique_port()
    group = "239.255.3.0"
    audio = AudioConfig(
        multicast_address=group,
        multicast_port=port,
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=8,
        sample_rate=SAMPLE_RATE,
        channels=1,
        source_name="radio",
        join_interface="127.0.0.1",
        network_interface="AUTO",
        frame_timeout=0.2,
    )
    rec = RecordingConfig(
        enabled=True,
        vad_enabled=True,
        vad_fixed_threshold=2000.0,
        audio_archive_root=archive,
        mp3_enabled=False,
    )
    captured: list[dict] = []
    recorder = TransmissionRecorder(audio, rec, on_recording=captured.append)
    receiver = RtpReceiver(audio, on_pcm=recorder.on_pcm)
    receiver.start()
    sim: RtpSimulator | None = None
    try:
        _wait_for_bind(receiver)
        sim = RtpSimulator(audio, ssrc=0x12345678)
        # 40 speech packets (A-law of a loud tone) + 60 silence packets.
        for _ in range(40):
            sim.send_pcm(_pcm(SPEECH))
        for _ in range(60):
            sim.send_silence(n=1, samples=160)
        deadline = time.time() + 8.0
        while time.time() < deadline and not captured:
            time.sleep(0.05)
        assert captured, "no recording produced from real RTP input"
        wav = captured[0]["recording"]["wav_path"]
        assert os.path.exists(wav)
        channels, rate, width, samples = _read_wav(wav)
        assert channels == 1 and rate == SAMPLE_RATE and width == 2
    finally:
        receiver.stop()
        if sim is not None:
            sim.close()


# ---------------------------------------------------------------------------
# O — Real PCAP-derived PCM can be segmented/recorded
# ---------------------------------------------------------------------------


def _find_pcap() -> str | None:
    candidates = [
        os.environ.get("WO039_PCAP"),
        "/opt/data/uploads/1788366527-b0f355db/test.pcapng",
        "/opt/data/uploads/1788367988-5b6e6318/test.pcapng",
        os.path.join(os.path.dirname(__file__), "..", "..", "test.pcapng"),
        "test.pcapng",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _iter_pcap_rtp(path: str):
    """Yield RTP packets from the real radio flow (UDP port 5033)."""
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
def test_o_real_pcap_segmented_and_recorded(archive) -> None:
    path = _find_pcap()
    assert path is not None
    audio = AudioConfig(
        multicast_address="239.233.18.30",
        multicast_port=5033,
        protocol="rtp",
        codec="pcm_alaw",
        payload_type=8,
        sample_rate=SAMPLE_RATE,
        channels=1,
        source_name="radio",
    )
    rec = RecordingConfig(
        enabled=True,
        vad_enabled=True,
        vad_fixed_threshold=2000.0,
        pre_roll_ms=400,
        post_roll_ms=800,
        min_speech_ms=250,
        silence_timeout_ms=1000,
        max_segment_ms=60000,
        audio_archive_root=archive,
        mp3_enabled=False,
    )
    captured: list[dict] = []
    recorder = TransmissionRecorder(audio, rec, on_recording=captured.append)
    t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    cur = t0
    frames = 0
    for rtp in _iter_pcap_rtp(path):
        from app.audio.rtp import parse_rtp_packet

        try:
            packet = parse_rtp_packet(rtp)
        except ValueError:
            continue
        if packet.payload_len != 160:
            continue
        pcm = alaw_to_pcm(packet.payload)
        recorder.on_pcm(_frame(0, cur) if False else SimpleNamespace(pcm=pcm, received_at=cur))
        cur += timedelta(milliseconds=FRAME_MS)
        frames += 1
    assert frames > 0, "no radio RTP packets found in pcap"
    # The recorder may finalize the last segment on shutdown.
    recorder.on_shutdown("source_shutdown")
    assert captured, "no transmission was segmented/recorded from the real PCAP"
    wav = captured[0]["recording"]["wav_path"]
    assert os.path.exists(wav)
    channels, rate, width, _ = _read_wav(wav)
    assert channels == 1 and rate == SAMPLE_RATE and width == 2


# ---------------------------------------------------------------------------
# Event linkage: a finalized recording maps to a canonical Event
# ---------------------------------------------------------------------------


def test_event_linkage_to_canonical_event(archive) -> None:
    from app.database.session import DatabaseSessionManager
    from app.event.event import Event
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )
    from app.event_sources.factory.event_factory import EventFactory

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        sm = DatabaseSessionManager(database_url=f"sqlite:///{db_path}", echo=False)
        sm.initialize()
        repo = SQLAlchemyEventRepository(session_manager=sm)
        repo.initialize()
        factory = EventFactory()

        rec, captured = _mkrecorder(archive)
        t0 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        _feed(rec, [SILENCE] * 25, t0)
        _feed(rec, [SPEECH] * 40, t0 + timedelta(seconds=0.5))
        _feed(rec, [SILENCE] * 60, t0 + timedelta(seconds=1.3))
        raw = captured[0]
        event = factory.create_event(raw, source_name="radio")
        assert isinstance(event, Event)
        repo.save(event)
        assert repo.exists(event.event_id)
        restored = repo.get(event.event_id)
        assert restored.payload["recording"]["sha256"] == raw["recording"]["sha256"]
        assert restored.payload["recording"]["source"] == "radio"
        # The canonical event's timestamp is the recording occurrence time
        # (the raw timestamp was UTC; the durable layer may round-trip it).
        assert restored.timestamp is not None
        assert restored.source == "radio"
        sm.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ---------------------------------------------------------------------------
# Adapter integration: recording enabled source queues recording raw events
# ---------------------------------------------------------------------------


def test_adapter_recording_integration(archive) -> None:
    from app.audio.source_adapter import MulticastAudioSourceAdapter
    from app.event_sources.config.source_definition import SourceDefinition

    port = _unique_port()
    group = "239.255.4.0"
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
    adapter.start()
    sim: RtpSimulator | None = None
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline:
            receiver = getattr(adapter, "_receiver", None)
            if receiver is not None and receiver.is_bound():
                break
            time.sleep(0.02)
        sim = RtpSimulator(adapter._config, ssrc=0xABCD)
        for _ in range(40):
            sim.send_pcm(_pcm(SPEECH))
        for _ in range(60):
            sim.send_silence(n=1, samples=160)
        deadline = time.time() + 8.0
        raw_events: list[dict] = []
        while time.time() < deadline:
            raw_events = adapter.read_events()
            if any("audio_recording_id" in e for e in raw_events):
                break
            time.sleep(0.05)
        assert raw_events, "adapter produced no recording raw event"
        rec_events = [e for e in raw_events if "audio_recording_id" in e]
        assert rec_events, "no recording raw event in adapter queue"
        assert rec_events[0]["recording"]["source"] == "radio"
        assert os.path.exists(rec_events[0]["recording"]["wav_path"])
    finally:
        adapter.stop()
        if sim is not None:
            sim.close()
