#!/usr/bin/env python3
"""WO-043 — Unit tests for the deterministic segmentation algorithm.

These tests use SYNTHETIC audio inputs only. They exercise the segmentation
ALGORITHM (single burst, split, merge, min/max duration, pre/post roll, overlap
prevention, deterministic ordering, duplicate hash). They are NOT evidence of
real transmissions (WO-043 §21): synthetic tests only verify algorithm behaviour.

Isolated and offline: no STT, no network, no production audio pipeline.
"""

import csv
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


# ===========================================================================
# WO-043-CORR-01 — C1 EOF clamp, C3 CLI / manifest / SHA integration.
#
# These are integration-style tests that drive the ACTUAL public CLI entrypoint
# (``wo043_segment.main``) end-to-end: it parses argv, writes real derived WAVs,
# writes a real manifest, and hashes the real output files.  They do NOT
# reconstruct ``main()`` behaviour in the test (WO-043-CORR-01 §15, §16).
# ===========================================================================


def _read_rows(path: str) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _run_cli(tmp_path, src, *, outdir=None, manifest="man.csv",
             wo042=None, extra=None):
    """Invoke the real CLI entrypoint with explicit args."""
    args = ["--input", src]
    if outdir is not None:
        args += ["--output-dir", str(outdir)]
    mpath = str(tmp_path / manifest)
    args += ["--manifest", mpath]
    if wo042:
        args += ["--wo042-manifest", str(tmp_path / wo042)]
    if extra:
        args += extra
    rc = seg.main(args)
    return rc, mpath


# ---------------------------------------------------------------------------
# C1 — EOF clamp: activity reaching EOF must clamp segment_end to source_duration,
# and the derived WAV duration must equal the manifest segment duration.
# ---------------------------------------------------------------------------

def test_eof_clamp_segment_end_equals_source(tmp_path, tmpwav):
    # source_duration = 1.800 s; last 0.8 s is active and reaches EOF.
    samples = _concat(_silence(1.0), _sine(0.8))
    src = tmpwav("eof.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    src_dur = len(mono) / rate
    c = seg.build_candidates(mono, rate, seg.SegmentParams())[0]
    assert c.segment_start >= 0.0
    assert c.segment_end <= src_dur + 1e-9
    assert abs(c.segment_end - src_dur) < 1e-6          # clamped to source
    assert c.segment_end > c.segment_start


def test_eof_clamp_manifest_timing_matches_derived_wav(tmp_path, tmpwav):
    samples = _concat(_silence(1.0), _sine(0.8))
    src = tmpwav("eof_cli.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    src_dur = len(mono) / rate
    outdir = tmp_path / "eof_out"
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    rows = _read_rows(mpath)
    assert len(rows) == 1
    row = rows[0]
    derived = os.path.join(str(outdir), row["audio_id"] + ".wav")
    assert os.path.exists(derived)
    # manifest timing must equal the actual derived WAV interval (C1 §5, §8).
    assert abs(_wav_duration(derived) - float(row["duration_seconds"])) < 1e-3
    assert float(row["segment_start_seconds"]) >= 0.0
    assert float(row["segment_end_seconds"]) <= src_dur + 1e-9
    assert abs(float(row["segment_end_seconds"]) - src_dur) < 1e-6
    assert _file_sha(derived) == row["derived_sha256"]


# ---------------------------------------------------------------------------
# C1 — t=0 clamp: a burst at the very start must never produce a negative start.
# ---------------------------------------------------------------------------

def test_t0_clamp_manifest(tmp_path, tmpwav):
    samples = _concat(_sine(0.8), _silence(1.0))
    src = tmpwav("t0.wav", samples)
    outdir = tmp_path / "t0_out"
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    rows = _read_rows(mpath)
    assert len(rows) == 1
    assert float(rows[0]["segment_start_seconds"]) >= 0.0


# ---------------------------------------------------------------------------
# C3 — Actual CLI execution: return code, manifest, derived WAV, SHA, duration,
# boundaries — all verified from the real files written by the CLI.
# ---------------------------------------------------------------------------

def test_cli_integration_single_burst(tmp_path, tmpwav):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("cli.wav", samples)
    outdir = tmp_path / "cli_out"
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    assert os.path.exists(mpath)
    rows = _read_rows(mpath)
    assert len(rows) == 1
    row = rows[0]
    assert row["audio_id"] == "RADIO-0001"
    derived = os.path.join(str(outdir), "RADIO-0001.wav")
    assert os.path.exists(derived)
    # SHA recomputed from the actual output file bytes (C3 §16).
    assert _file_sha(derived) == row["derived_sha256"]
    # duration matches the derived WAV.
    assert abs(_wav_duration(derived) - float(row["duration_seconds"])) < 1e-3
    # segment boundaries.
    assert float(row["segment_start_seconds"]) >= 0.0
    assert float(row["segment_end_seconds"]) > float(row["segment_start_seconds"])
    assert row["candidate_status"] == "CANDIDATE"
    assert row["real_transmission"] == "false"


# ---------------------------------------------------------------------------
# C3 — manifest / file consistency over ALL rows, not just the first.
# ---------------------------------------------------------------------------

def test_manifest_file_consistency_all_rows(tmp_path, tmpwav):
    samples = _concat(
        _silence(1.0), _sine(0.7), _silence(2.0), _sine(0.8), _silence(2.0),
        _sine(0.9), _silence(1.0),
    )
    src = tmpwav("cons.wav", samples)
    rate, _, _, mono = seg.read_wav(src)
    src_dur = len(mono) / rate
    outdir = tmp_path / "cons_out"
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    rows = _read_rows(mpath)
    assert len(rows) == 3
    for row in rows:
        derived = os.path.join(str(outdir), row["audio_id"] + ".wav")
        assert os.path.exists(derived)
        assert _file_sha(derived) == row["derived_sha256"]
        assert abs(_wav_duration(derived) - float(row["duration_seconds"])) < 1e-3
        assert float(row["segment_start_seconds"]) >= 0.0
        assert float(row["segment_end_seconds"]) <= src_dur + 1e-9
        assert float(row["segment_end_seconds"]) > float(row["segment_start_seconds"])
    # no-overlap across rows (C1 §21).
    starts = [float(r["segment_start_seconds"]) for r in rows]
    ends = [float(r["segment_end_seconds"]) for r in rows]
    for a, b in zip(zip(starts, ends), zip(starts[1:], ends[1:])):
        assert a[1] <= b[0] + 1e-9


# ---------------------------------------------------------------------------
# C3 — stale-output isolation: a pre-existing stale RADIO-0004.wav must not
# contaminate the manifest of a 3-candidate run.
# ---------------------------------------------------------------------------

def test_stale_output_isolation(tmp_path, tmpwav):
    samples = _concat(
        _silence(1.0), _sine(0.8), _silence(2.0), _sine(0.8), _silence(2.0),
        _sine(0.8), _silence(1.0),
    )
    src = tmpwav("stale.wav", samples)
    outdir = tmp_path / "stale_out"
    outdir.mkdir(parents=True, exist_ok=True)
    # pre-place a stale derived file that is NOT part of the current run.
    _write_wav(str(outdir / "RADIO-0004.wav"), _sine(0.5))
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    rows = _read_rows(mpath)
    ids = [r["audio_id"] for r in rows]
    assert ids == ["RADIO-0001", "RADIO-0002", "RADIO-0003"]
    assert "RADIO-0004" not in ids


# ---------------------------------------------------------------------------
# C3 — `--manifest` without `--output-dir` must not silently produce a
# header-only manifest (WO-043-CORR-01 C3 §17): derived masters land alongside
# the manifest and the manifest is populated.
# ---------------------------------------------------------------------------

def test_manifest_without_output_dir_is_populated(tmp_path, tmpwav):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(2.0), _sine(0.8),
                      _silence(1.0))
    src = tmpwav("nodir.wav", samples)
    rc, mpath = _run_cli(tmp_path, src, outdir=None)
    assert rc == 0
    rows = _read_rows(mpath)
    assert len(rows) == 2
    for row in rows:
        # derived WAV lives alongside the manifest (same directory).
        derived = os.path.join(os.path.dirname(mpath), row["audio_id"] + ".wav")
        assert os.path.exists(derived)
        assert _file_sha(derived) == row["derived_sha256"]


# ---------------------------------------------------------------------------
# C3 — determinism: two full CLI runs on the same input must yield
# byte-identical manifests and identical derived SHA values.
# ---------------------------------------------------------------------------

def test_cli_determinism_byte_identical(tmp_path, tmpwav):
    samples = _concat(
        _silence(1.0), _sine(0.7), _silence(2.0), _sine(0.9), _silence(1.5),
        _sine(0.5), _silence(1.0),
    )
    src = tmpwav("detcl.wav", samples)
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    rc1, m1 = _run_cli(tmp_path, src, outdir=out1, manifest="m1.csv")
    rc2, m2 = _run_cli(tmp_path, src, outdir=out2, manifest="m2.csv")
    assert rc1 == 0 and rc2 == 0
    assert open(m1, "rb").read() == open(m2, "rb").read()
    # derived SHA values identical across runs.
    r1 = _read_rows(m1)
    r2 = _read_rows(m2)
    assert [r["derived_sha256"] for r in r1] == [r["derived_sha256"] for r in r2]


# ---------------------------------------------------------------------------
# C3 — source immutability through the full CLI path.
# ---------------------------------------------------------------------------

def test_cli_source_immutability(tmp_path, tmpwav):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("immut_cli.wav", samples)
    before = _file_sha(src)
    outdir = tmp_path / "immut_out"
    rc, _mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    assert _file_sha(src) == before


# ---------------------------------------------------------------------------
# C2 — WO-042 canonical schema compatibility: the converted manifest must be
# loadable by the WO-042 validator, carry every required field, and keep every
# row an unverified candidate (real_transmission=false), so the dataset gate
# stays FAIL (WO-043-CORR-01 C2 §13, §14).
# ---------------------------------------------------------------------------

def test_wo042_schema_compatibility(tmp_path, tmpwav):
    samples = _concat(_silence(1.0), _sine(0.8), _silence(2.0), _sine(0.8),
                      _silence(1.0))
    src = tmpwav("wo042.wav", samples)
    outdir = tmp_path / "wo042_out"
    rc, _mpath = _run_cli(tmp_path, src, outdir=outdir, wo042="wo042.csv")
    assert rc == 0
    wo042_path = str(tmp_path / "wo042.csv")
    assert os.path.exists(wo042_path)

    import wo042_validate_dataset as wv

    rows = wv.load_manifest(wo042_path)
    assert len(rows) == 2
    assert all(f in rows[0] for f in wv.REQUIRED_FIELDS)
    report = wv.validate_dataset(rows)
    # Candidates are never auto-promoted to real transmissions (§14).
    assert report["fixture_rows"] == 2
    assert report["real_transmissions"] == 0
    assert report["verified_real_transmissions"] == 0
    assert report["gate_satisfied"] is False
    assert report["invalid_rows"] == 0
    for r in rows:
        assert r["real_transmission"] == "false"
        assert r["ground_truth_verified"] == "false"
        assert r["independent_verification"] == "false"
        assert r["transcript"] == ""
        assert r["callsigns_present"] == "[]"
        derived = r["audio_path"]
        assert os.path.exists(derived)
        assert _file_sha(derived) == r["sha256"]


def test_convert_to_wo042_preserves_forensic_fields(tmp_path, tmpwav):
    """Segmentation evidence (segment bounds, source_sha256, derived_sha256) must
    survive into the segmentation manifest; the WO-042 conversion is additive and
    never destroys them (WO-043-CORR-01 §12)."""
    samples = _concat(_silence(1.0), _sine(0.8), _silence(1.0))
    src = tmpwav("forensic.wav", samples)
    outdir = tmp_path / "forensic_out"
    rc, mpath = _run_cli(tmp_path, src, outdir=outdir)
    assert rc == 0
    rows = _read_rows(mpath)
    row = rows[0]
    for field in ("segment_start_seconds", "segment_end_seconds",
                  "activity_start_seconds", "activity_end_seconds",
                  "source_sha256", "derived_sha256", "candidate_status"):
        assert field in row
    # WO-042 conversion keeps audio_id and derived SHA, mapping to canonical names.
    wv_rows = seg.convert_to_wo042(rows, str(outdir))
    assert wv_rows[0]["audio_id"] == row["audio_id"]
    assert wv_rows[0]["sha256"] == row["derived_sha256"]
    assert wv_rows[0]["real_transmission"] == "false"
    # segmentation manifest still has its own source_sha256 evidence.
    assert row["source_sha256"] != ""
