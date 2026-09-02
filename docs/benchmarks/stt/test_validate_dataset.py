"""WO-041 — dataset validator validation tests.

These tests exercise ``validate_dataset.py`` in isolation.  They use
deterministic synthetic TEST FIXTURES (generated WAV bytes / synthetic manifest
rows) ONLY to unit-test the validator logic.  They are never treated as real
radio benchmark evidence, and they must not be used as proof that the
>= 50-real-transmission dataset gate has passed (WO-041 §22, §24).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import struct
import tempfile
import wave

import pytest

from validate_dataset import (
    MIN_REAL_TRANSMISSIONS,
    has_ground_truth,
    has_verified_ground_truth,
    is_real_transmission,
    load_manifest,
    validate_dataset,
    validate_wav,
)

# ---------------------------------------------------------------------------
# Helpers: synthetic test fixtures (deterministic; NOT real radio evidence).
# ---------------------------------------------------------------------------
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit
DURATION = 1.0


def _write_wav(path: str, *, duration: float = DURATION, value: int = 1000) -> str:
    """Write a minimal valid mono 16-bit WAV (a constant-amplitude tone)."""
    frames = int(SAMPLE_RATE * duration)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{frames}h", *([value] * frames)))
    return path


def _row(**overrides: object) -> dict[str, object]:
    """Build a synthetic manifest row with defaults (a non-real fixture)."""
    base: dict[str, object] = {
        "audio_id": "audio_000",
        "wav_path": "",
        "duration_seconds": "1.0",
        "sample_rate": "8000",
        "channels": "1",
        "sample_width": "2",
        "sha256": "",
        "source": "radio",
        "provenance": "WO-039-B/C unit-test fixture: constant-amplitude test tone",
        "ground_truth": "",
        "callsigns_present": "",
        "real_transmission": "false",
        "ground_truth_verified": "false",
        "independent_verification": "false",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Real-transmission classification (§16).
# ---------------------------------------------------------------------------
def test_fixture_provenance_is_not_real() -> None:
    row = _row(real_transmission="true")
    assert is_real_transmission(row) is False


def test_real_requires_explicit_real_flag() -> None:
    row = _row(real_transmission="false", provenance="real radio capture")
    assert is_real_transmission(row) is False


def test_real_transmission_classified() -> None:
    row = _row(real_transmission="true", provenance="WO-041 real radio capture")
    assert is_real_transmission(row) is True


def test_real_never_inferred_from_filename() -> None:
    # Filename alone must not make a row real (§16).
    row = _row(real_transmission="false", provenance="")
    assert is_real_transmission(row) is False


# ---------------------------------------------------------------------------
# Ground truth requirement (§10, §12).
# ---------------------------------------------------------------------------
def test_ground_truth_required() -> None:
    assert has_ground_truth(_row(ground_truth="alpha one bravo")) is True
    assert has_ground_truth(_row(ground_truth="")) is False


def test_verified_ground_truth_requires_verification_flag() -> None:
    row = _row(ground_truth="alpha one bravo", ground_truth_verified="false")
    assert has_verified_ground_truth(row) is False
    row = _row(ground_truth="alpha one bravo", ground_truth_verified="true")
    assert has_verified_ground_truth(row) is True


# ---------------------------------------------------------------------------
# WAV validity (§15).
# ---------------------------------------------------------------------------
def test_invalid_wav_rejected(tmp_path: "pytest.TempPathFactory") -> None:
    ok, info = validate_wav(str(tmp_path / "missing.wav"))
    assert ok is False
    assert "not found" in info["reason"]


def test_invalid_wav_header_rejected(tmp_path: "pytest.TempPathFactory") -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"NOT A WAV FILE")
    ok, info = validate_wav(str(bad))
    assert ok is False
    assert "invalid WAV" in info["reason"]


def test_valid_wav_accepted(tmp_path: "pytest.TempPathFactory") -> None:
    path = _write_wav(str(tmp_path / "ok.wav"))
    ok, info = validate_wav(path)
    assert ok is True
    assert info["sample_rate"] == SAMPLE_RATE
    assert info["channels"] == CHANNELS
    assert info["sample_width"] == SAMPLE_WIDTH
    assert info["duration_seconds"] > 0


# ---------------------------------------------------------------------------
# Duplicate control (§14).
# ---------------------------------------------------------------------------
def test_duplicate_sha256_detected(tmp_path: "pytest.TempPathFactory") -> None:
    p1 = _write_wav(str(tmp_path / "a.wav"))
    p2 = _write_wav(str(tmp_path / "b.wav"))
    import hashlib

    sha = hashlib.sha256(open(p1, "rb").read()).hexdigest()
    rows = [
        _row(audio_id="a", wav_path=p1, sha256=sha, real_transmission="true",
             provenance="real", ground_truth="x", ground_truth_verified="true"),
        _row(audio_id="b", wav_path=p2, sha256=sha, real_transmission="true",
             provenance="real", ground_truth="x", ground_truth_verified="true"),
    ]
    report = validate_dataset(rows)
    assert report["duplicate_rows"] == 1
    # Duplicate content must count as ONE real transmission (§14).
    assert report["real_transmissions"] == 1
    assert report["verified_real_transmissions"] == 1


# ---------------------------------------------------------------------------
# Dataset gate (§18).
# ---------------------------------------------------------------------------
def test_gate_fails_below_50(tmp_path: "pytest.TempPathFactory") -> None:
    p = _write_wav(str(tmp_path / "r.wav"))
    import hashlib

    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    rows = [
        _row(audio_id=f"r{i}", wav_path=p, sha256=f"{sha}{i:02d}",
             real_transmission="true", provenance="real capture",
             ground_truth="alpha one bravo", ground_truth_verified="true")
        for i in range(10)
    ]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 10
    assert report["gate_satisfied"] is False


def test_gate_passes_at_50(tmp_path: "pytest.TempPathFactory") -> None:
    p = _write_wav(str(tmp_path / "r.wav"))
    import hashlib

    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    rows = [
        _row(audio_id=f"r{i}", wav_path=p, sha256=f"{sha}{i:02d}",
             real_transmission="true", provenance="real capture",
             ground_truth="alpha one bravo", ground_truth_verified="true")
        for i in range(50)
    ]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 50
    assert report["gate_satisfied"] is True


def test_gate_does_not_count_fixtures(tmp_path: "pytest.TempPathFactory") -> None:
    # 60 fixture rows must not satisfy the gate.
    p = _write_wav(str(tmp_path / "f.wav"))
    import hashlib

    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    rows = [
        _row(audio_id=f"f{i}", wav_path=p, sha256=f"{sha}{i:02d}")
        for i in range(60)
    ]
    report = validate_dataset(rows)
    assert report["fixture_rows"] == 60
    assert report["real_transmissions"] == 0
    assert report["verified_real_transmissions"] == 0
    assert report["gate_satisfied"] is False


# ---------------------------------------------------------------------------
# Manifest field completeness (§17).
# ---------------------------------------------------------------------------
def test_manifest_has_required_fields(tmp_path: "pytest.TempPathFactory") -> None:
    p = _write_wav(str(tmp_path / "ok.wav"))
    import hashlib

    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    row = _row(audio_id="ok", wav_path=p, sha256=sha, real_transmission="true",
               provenance="real", ground_truth="x", ground_truth_verified="true")
    # The validator must not require anything beyond the documented fields.
    report = validate_dataset([row])
    assert report["verified_real_transmissions"] == 1
    assert report["missing_ground_truth"] == 0


def test_missing_ground_truth_recorded(tmp_path: "pytest.TempPathFactory") -> None:
    p = _write_wav(str(tmp_path / "ok.wav"))
    import hashlib

    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    row = _row(audio_id="ok", wav_path=p, sha256=sha, real_transmission="true",
               provenance="real", ground_truth="")
    report = validate_dataset([row])
    assert report["missing_ground_truth"] == 1
    assert report["verified_real_transmissions"] == 0


def test_load_manifest_roundtrip(tmp_path: "pytest.TempPathFactory") -> None:
    import csv

    fields = [
        "audio_id", "wav_path", "duration_seconds", "sample_rate", "channels",
        "sample_width", "sha256", "source", "provenance", "ground_truth",
        "callsigns_present", "real_transmission", "ground_truth_verified",
        "independent_verification",
    ]
    csv_path = tmp_path / "m.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerow({
            "audio_id": "a", "wav_path": "/x.wav", "duration_seconds": "1.0",
            "sample_rate": "8000", "channels": "1", "sample_width": "2",
            "sha256": "abc", "source": "radio", "provenance": "real",
            "ground_truth": "x", "callsigns_present": "", "real_transmission": "true",
            "ground_truth_verified": "true", "independent_verification": "false",
        })
    rows = load_manifest(str(csv_path))
    assert len(rows) == 1
    assert rows[0]["audio_id"] == "a"


# ---------------------------------------------------------------------------
# Invalid WAV in a real row -> not counted (§15).
# ---------------------------------------------------------------------------
def test_invalid_wav_real_row_not_counted(tmp_path: "pytest.TempPathFactory") -> None:
    row = _row(audio_id="bad", wav_path=str(tmp_path / "nope.wav"),
               real_transmission="true", provenance="real capture",
               ground_truth="x", ground_truth_verified="true")
    report = validate_dataset([row])
    assert report["invalid_files"] == 1
    assert report["verified_real_transmissions"] == 0
