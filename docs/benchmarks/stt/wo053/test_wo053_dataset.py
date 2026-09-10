"""WO-053 — Tests for the controlled synthetic dataset mechanics.

These tests validate the DATASET MECHANICS only: deterministic generation,
byte-identical manifest across runs, SHA-256 integrity, format detection,
synthetic labeling, and the gate accounting.  No real STT accuracy is claimed.

Author: Tactical Core Engineering Team
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from wo053_dataset import (  # noqa: E402
    FIXTURES,
    generate_synthetic_audio,
    build_manifest,
    validate_manifest,
    sha256_file,
    write_synthetic_wav,
)


def _make_tmpdir():
    return tempfile.mkdtemp(prefix="wo053_ds_")


def test_fixture_definitions_present():
    assert len(FIXTURES) >= 4


def test_generation_writes_valid_wavs():
    d = _make_tmpdir()
    files = generate_synthetic_audio(d)
    assert len(files) == len(FIXTURES)
    for f in files:
        assert os.path.exists(f)
        assert os.path.getsize(f) > 44  # at least the WAV header
        assert sha256_file(f)  # non-empty digest


def test_manifest_is_deterministic():
    d = _make_tmpdir()
    m1 = os.path.join(d, "m1.csv")
    m2 = os.path.join(d, "m2.csv")
    generate_synthetic_audio(d)
    build_manifest(d, m1)
    build_manifest(d, m2)
    with open(m1, "rb") as fh:
        b1 = fh.read()
    with open(m2, "rb") as fh:
        b2 = fh.read()
    assert b1 == b2  # byte-identical manifest across runs


def test_manifest_sha_matches_file():
    d = _make_tmpdir()
    m = os.path.join(d, "m.csv")
    generate_synthetic_audio(d)
    build_manifest(d, m)
    res = validate_manifest(m, d)
    assert res["valid_rows"] == res["manifest_rows"]
    assert res["invalid_rows"] == 0
    assert res["synthetic_rows"] == len(FIXTURES)


def test_manifest_gate_pass_for_synthetic():
    d = _make_tmpdir()
    m = os.path.join(d, "m.csv")
    generate_synthetic_audio(d)
    build_manifest(d, m)
    res = validate_manifest(m, d)
    assert res["gate"] == "PASS"
    assert res["real_transmissions"] == 0
    assert res["speech_rows"] == 0


def test_validate_detects_sha_mismatch():
    d = _make_tmpdir()
    m = os.path.join(d, "m.csv")
    generate_synthetic_audio(d)
    build_manifest(d, m)
    # Corrupt a file so its SHA no longer matches.
    import glob
    wav = sorted(glob.glob(os.path.join(d, "*.wav")))[0]
    with open(wav, "ab") as fh:
        fh.write(b"\x00")
    res = validate_manifest(m, d)
    assert res["invalid_rows"] >= 1
    assert res["gate"] == "FAIL"
    assert any("SHA-256 mismatch" in e for e in res["errors"])


def test_validate_detects_missing_file():
    d = _make_tmpdir()
    m = os.path.join(d, "m.csv")
    generate_synthetic_audio(d)
    build_manifest(d, m)
    import glob
    wav = sorted(glob.glob(os.path.join(d, "*.wav")))[0]
    os.remove(wav)
    res = validate_manifest(m, d)
    assert res["invalid_rows"] >= 1
    assert any("file missing" in e for e in res["errors"])


def test_write_synthetic_wav_format():
    d = _make_tmpdir()
    p = os.path.join(d, "tone.wav")
    write_synthetic_wav(p, 440.0, 1.0)
    import wave
    with wave.open(p, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 8000
        assert abs(wf.getnframes() / 8000.0 - 1.0) < 1e-6
