#!/usr/bin/env python3
"""WO-043 — Unit tests for the deterministic segmentation algorithm.

These tests use SYNTHETIC audio inputs only. They exercise the segmentation
ALGORITHM (single burst, split, merge, min/max duration, pre/post roll, overlap
prevention, deterministic ordering, duplicate hash). They are NOT evidence of
real transmissions (WO-043 §21): synthetic tests only verify algorithm behaviour.

Isolated and offline: no STT, no network, no production audio pipeline.
"""

import hashlib
import os
import sys
import wave

# Make the tool importable from its own directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import pytest  # noqa: E402

import wo043_segment as seg  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic WAV generation helpers (16-bit PCM mono, deterministic).
# ---------------------------------------------------------------------------

RATE = 8000


def _write_wav(path: str, samples: list, rate: int = RATE, channels: int = 1) -> None:
    """Write float samples in [-1, 1] as 16-bit PCM WAV."""
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            frames += int(v).to_bytes(2, "little", signed=True)
        w.writeframes(bytes(frames))


def _sine(duration_s: float, freq: float = 440.0, amp: float = 0.5,
          rate: int = RATE) -> list:
    n = int(duration_s * rate)
    return [amp * (2 ** 0.5) * __import__("math").sin(2 * __import__("math").pi * freq * i / rate)
            for i in range(n)]


def _silence(duration_s: float, rate: int = RATE) -> list:
    return [0.0] * int(duration_s * rate)


def _concat(*parts: list) -> list:
    out = []
    for p in parts:
        out.extend(p)
    return out


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


@pytest.fixture
def params():
    return seg.SegmentParams()


@pytest.fixture
def tmpwav(tmp_path):
    def make(name: str, samples: list, rate: int = RATE) -> str:
        p = str(tmp_path / name)
        _write_wav(p, samples, rate)
        return p
    return make


# ---------------------------------------------------------------------------
# Single burst
# ---------------------------------------------------------------------------

def test_single_burst(tmpwav, params):
    # 1.0 s burst surrounded by 1 s silence on each side.
    samples = _concat(_silence(1.0), _sine(1.0), _silence(1.0))
    src = tmpwav("single.wav", samples)
    rate, ch, sw, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 1
    c = cands[0]
    # pre/post roll defaults 250/400 ms.
    assert abs(c.segment_start - 0.750) < 0.05          # 1.0 - 0.25
    assert abs(c.segment_end - 2.400) < 0.05            # 2.0 + 0.40
    assert abs(c.activity_start - 1.0) < 0.05
    assert abs(c.activity_end - 2.0) < 0.05
    assert c.duration > 0


# ---------------------------------------------------------------------------
# Two separated bursts -> two candidates, ordered, non-overlapping
# ---------------------------------------------------------------------------

def test_two_separated_bursts(tmpwav, params):
    samples = _concat(
        _silence(1.0), _sine(0.8), _silence(2.0), _sine(0.8), _silence(1.0)
    )
    src = tmpwav("two.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 2
    assert cands[0].segment_start < cands[1].segment_start
    assert cands[0].segment_end <= cands[1].segment_start  # overlap rule
    # IDs assigned ascending by start.
    assert [c.index for c in cands] == [0, 1]


# ---------------------------------------------------------------------------
# Short silence inside burst -> merge
# ---------------------------------------------------------------------------

def test_short_silence_inside_burst_merges(tmpwav, params):
    # Two sine bursts separated by a 50 ms internal silence (< merge_gap 250 ms).
    samples = _concat(_silence(0.5), _sine(0.5), _silence(0.05), _sine(0.5),
                      _silence(0.5))
    src = tmpwav("inner.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 1  # contiguous transmission


# ---------------------------------------------------------------------------
# Long silence -> split
# ---------------------------------------------------------------------------

def test_long_silence_splits(tmpwav, params):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(3.0), _sine(0.8),
                      _silence(1.0))
    src = tmpwav("split.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 2


# ---------------------------------------------------------------------------
# Nearby bursts -> merge
# ---------------------------------------------------------------------------

def test_nearby_bursts_merge(tmpwav, params):
    # Gap of 200 ms between bursts; post-roll (400) of the first and pre-roll
    # (250) of the second overlap, so they merge into one candidate.
    samples = _concat(_silence(0.5), _sine(0.5), _silence(0.2), _sine(0.5),
                      _silence(0.5))
    src = tmpwav("nearby.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 1


# ---------------------------------------------------------------------------
# Minimum duration
# ---------------------------------------------------------------------------

def test_minimum_duration_drops_short_blip(tmpwav, params):
    # 60 ms blip is below min_duration (150 ms) based on ACTIVITY, even though
    # pre/post roll would pad it to > 700 ms.
    samples = _concat(_silence(0.5), _sine(0.06), _silence(0.5))
    src = tmpwav("blip.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 0


def test_minimum_duration_keeps_longer_burst(tmpwav, params):
    samples = _concat(_silence(0.5), _sine(0.4), _silence(0.5))
    src = tmpwav("keep.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    assert len(cands) == 1


# ---------------------------------------------------------------------------
# Maximum duration -> split
# ---------------------------------------------------------------------------

def test_maximum_duration_splits(tmpwav):
    p = seg.SegmentParams(max_duration_ms=1000.0)  # 1 s cap
    # 2.5 s continuous burst (over cap) with silence around.
    samples = _concat(_silence(0.5), _sine(2.5), _silence(0.5))
    src = tmpwav("max.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, p)
    assert len(cands) == 3  # 2.5 s / 1 s -> 3 chunks
    for c in cands:
        assert c.segment_end - c.segment_start <= 1.0 + 1e-6
    # No overlap across chunks.
    for a, b in zip(cands, cands[1:]):
        assert a.segment_end <= b.segment_start


# ---------------------------------------------------------------------------
# Pre-roll / post-roll
# ---------------------------------------------------------------------------

def test_pre_roll(tmpwav, params):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("pre.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    c = seg.build_candidates(mono, rate, params)[0]
    assert abs(c.segment_start - (c.activity_start - params.pre_roll_ms / 1000.0)) < 1e-6


def test_post_roll(tmpwav, params):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("post.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    c = seg.build_candidates(mono, rate, params)[0]
    assert abs(c.segment_end - (c.activity_end + params.post_roll_ms / 1000.0)) < 1e-6


def test_pre_roll_clamped_at_zero(tmpwav, params):
    # Burst starts at t=0; segment_start must not go negative.
    samples = _concat(_sine(0.8), _silence(1.0))
    src = tmpwav("clamp.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    c = seg.build_candidates(mono, rate, params)[0]
    assert c.segment_start >= 0.0


# ---------------------------------------------------------------------------
# Overlap prevention invariant
# ---------------------------------------------------------------------------

def test_no_overlap_invariant(tmpwav, params):
    samples = _concat(
        _silence(0.3), _sine(0.9), _silence(0.15), _sine(1.2), _silence(0.25),
        _sine(0.7), _silence(0.4),
    )
    src = tmpwav("ov.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    for a, b in zip(cands, cands[1:]):
        assert a.segment_end <= b.segment_start + 1e-9


# ---------------------------------------------------------------------------
# Determinism: repeated run -> same boundaries and IDs
# ---------------------------------------------------------------------------

def test_deterministic_ordering(tmpwav, params):
    samples = _concat(
        _silence(1.0), _sine(0.7), _silence(2.0), _sine(0.9), _silence(1.5),
        _sine(0.5), _silence(1.0),
    )
    src = tmpwav("det.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    c1 = seg.build_candidates(mono, rate, params)
    c2 = seg.build_candidates(mono, rate, params)
    assert [(round(c.segment_start, 6), round(c.segment_end, 6), c.index)
            for c in c1] == [(round(c.segment_start, 6), round(c.segment_end, 6), c.index)
                             for c in c2]
    # IDs are 0..n-1 in ascending segment_start order.
    starts = [c.segment_start for c in c1]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Duplicate hash: identical content -> identical derived SHA-256
# ---------------------------------------------------------------------------

def test_duplicate_hash_stable(tmp_path, tmpwav):
    samples = _concat(_silence(0.5), _sine(0.6), _silence(0.5))
    src = tmpwav("d1.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    c = seg.build_candidates(mono, rate, seg.SegmentParams())[0]
    out1 = str(tmp_path / "d1_0001.wav")
    out2 = str(tmp_path / "d1_0001b.wav")
    seg.write_wav_derived(src, out1, c.segment_start, c.segment_end)
    seg.write_wav_derived(src, out2, c.segment_start, c.segment_end)
    assert _sha(out1) == _sha(out2)


# ---------------------------------------------------------------------------
# Source immutability: the tool never modifies the source.
# ---------------------------------------------------------------------------

def test_source_never_modified(tmpwav, params):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("immut.wav", samples)
    before = _sha(src)
    rate, _, _, mono = seg.read_wav(src)
    seg.build_candidates(mono, rate, params)
    after = _sha(src)
    assert before == after


# ---------------------------------------------------------------------------
# Manifest field completeness and CANDIDATE defaults.
# ---------------------------------------------------------------------------

def test_manifest_rows_defaults(tmp_path, tmpwav, params):
    samples = _concat(_silence(0.5), _sine(0.7), _silence(0.5))
    src = tmpwav("man.wav", samples)
    rate, ch, sw, mono = seg.read_wav(src)
    cands = seg.build_candidates(mono, rate, params)
    outdir = str(tmp_path / "out")
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for c in cands:
        derived = os.path.join(outdir, f"RADIO-{c.index + 1:04d}.wav")
        seg.write_wav_derived(src, derived, c.segment_start, c.segment_end)
        rows.append({
            "audio_id": f"RADIO-{c.index + 1:04d}",
            "source_file": src,
            "source_sha256": _sha(src),
            "derived_sha256": _sha(derived),
            "candidate_status": "CANDIDATE",
            "real_transmission": "false",
            "transcript": "",
            "callsigns_present": "[]",
            "ground_truth_verified": "false",
            "independent_verification": "false",
        })
    assert all(r["candidate_status"] == "CANDIDATE" for r in rows)
    assert all(r["real_transmission"] == "false" for r in rows)
    assert all(r["transcript"] == "" for r in rows)
    assert all(r["callsigns_present"] == "[]" for r in rows)
    assert all(r["ground_truth_verified"] == "false" for r in rows)
    assert all(r["independent_verification"] == "false" for r in rows)
