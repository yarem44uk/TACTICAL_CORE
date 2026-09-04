"""WO-042 — dataset validator validation tests.

These tests exercise ``wo042_validate_dataset.py`` in isolation.  They use
deterministic synthetic TEST FIXTURES (generated WAV bytes / synthetic manifest
rows) ONLY to unit-test the validator logic (§15).  They are never treated as
real radio benchmark evidence, and they must not be used as proof that the
>= 50-real-transmission dataset gate has passed (WO-042 §19, §22).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import struct
import sys
import wave

import pytest

# Ensure the sibling validator module is importable regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wo042_validate_dataset import (  # noqa: E402
    MIN_REAL_TRANSMISSIONS,
    has_ground_truth,
    has_verified_ground_truth,
    is_provenance_valid,
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


def _write_wav(path: str, *, value: int = 1000, duration: float = DURATION) -> str:
    """Write a minimal valid mono 16-bit WAV (a constant-amplitude tone)."""
    frames = int(SAMPLE_RATE * duration)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{frames}h", *([value] * frames)))
    return path


def _sha(path: str) -> str:
    import hashlib

    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _real_row(
    audio_id: str,
    wav_path: str,
    *,
    sha256: str | None = None,
    transcript: str = "alpha one bravo",
    callsigns: str = "[]",
    source_type: str = "radio",
    provenance: str = "WO-042 real radio capture via SDR",
    gt_verified: str = "true",
    independent: str = "true",
    real: str = "true",
    duration: str = "1.0",
) -> dict[str, object]:
    """Build a WO-042 manifest row that is valid by default."""
    if sha256 is None:
        sha256 = _sha(wav_path)
    return {
        "audio_id": audio_id,
        "audio_path": wav_path,
        "sha256": sha256,
        "source_type": source_type,
        "real_transmission": real,
        "capture_timestamp": "2026-09-04T00:00:00Z",
        "duration_seconds": duration,
        "sample_rate": "8000",
        "channels": "1",
        "sample_width_bits": "16",
        "codec": "PCM",
        "speaker_or_source": "UNKNOWN",
        "transcript": transcript,
        "callsigns_present": callsigns,
        "ground_truth_verified": gt_verified,
        "independent_verification": independent,
        "verification_method": "human_reviewer",
        "provenance": provenance,
        "notes": "",
    }


def _fixture_row(audio_id: str, wav_path: str, *, sha256: str | None = None) -> dict[str, object]:
    """Build a non-real fixture row (WO-039-B/C test tone)."""
    return _real_row(
        audio_id,
        wav_path,
        sha256=sha256,
        real="false",
        provenance="WO-039-B/C unit-test fixture: constant-amplitude test tone",
        transcript="",
        callsigns="[]",
        gt_verified="false",
        independent="false",
        duration="1.0",
    )


# ---------------------------------------------------------------------------
# Test 1 — Real transmission counts (classification).
# ---------------------------------------------------------------------------
def test_real_transmission_counts(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "r.wav"))
    rows = [_real_row("RADIO-0001", p)]
    report = validate_dataset(rows)
    assert report["real_transmissions"] == 1
    assert report["verified_real_transmissions"] == 1


# ---------------------------------------------------------------------------
# Test 2 — Fixture does not count.
# ---------------------------------------------------------------------------
def test_fixture_does_not_count(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "f.wav"))
    rows = [_fixture_row("RADIO-0001", p)]
    report = validate_dataset(rows)
    assert report["fixture_rows"] == 1
    assert report["real_transmissions"] == 0
    assert report["verified_real_transmissions"] == 0


# ---------------------------------------------------------------------------
# Test 3 — Synthetic audio does not count.
# ---------------------------------------------------------------------------
def test_synthetic_audio_does_not_count(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "s.wav"))
    rows = [
        _real_row(
            "RADIO-0001",
            p,
            provenance="synthetic TTS-generated speech, not real radio audio",
        )
    ]
    report = validate_dataset(rows)
    assert report["real_transmissions"] == 0
    assert report["verified_real_transmissions"] == 0


# ---------------------------------------------------------------------------
# Test 4 — Duplicate SHA rejected.
# ---------------------------------------------------------------------------
def test_duplicate_sha_rejected(tmp_path: pytest.TempPathFactory) -> None:
    p1 = _write_wav(str(tmp_path / "a.wav"), value=1000)
    p2 = _write_wav(str(tmp_path / "b.wav"), value=1000)  # same content -> same SHA
    sha = _sha(p1)
    rows = [
        _real_row("RADIO-0001", p1, sha256=sha),
        _real_row("RADIO-0002", p2, sha256=sha),
    ]
    report = validate_dataset(rows)
    assert report["duplicates"] == 1
    assert report["real_transmissions"] == 2
    assert report["verified_real_transmissions"] == 1


# ---------------------------------------------------------------------------
# Test 5 — Missing transcript rejected.
# ---------------------------------------------------------------------------
def test_missing_transcript_rejected(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "m.wav"))
    rows = [_real_row("RADIO-0001", p, transcript="")]
    report = validate_dataset(rows)
    assert report["real_transmissions"] == 1
    assert report["verified_real_transmissions"] == 0
    assert report["missing_transcript_ids"] == ["RADIO-0001"]


# ---------------------------------------------------------------------------
# Test 6 — Unverified row rejected.
# ---------------------------------------------------------------------------
def test_unverified_row_rejected(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "u.wav"))
    # Not ground-truth-verified.
    rows = [_real_row("RADIO-0001", p, gt_verified="false")]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 0
    # Not independently verified.
    rows2 = [_real_row("RADIO-0001", p, independent="false")]
    report2 = validate_dataset(rows2)
    assert report2["verified_real_transmissions"] == 0


# ---------------------------------------------------------------------------
# Test 7 — Invalid WAV rejected.
# ---------------------------------------------------------------------------
def test_invalid_wav_rejected(tmp_path: pytest.TempPathFactory) -> None:
    rows = [
        _real_row(
            "RADIO-0001",
            str(tmp_path / "missing.wav"),
            sha256="a" * 64,
        )
    ]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 0
    assert report["missing_file_ids"] == ["RADIO-0001"]


def test_corrupt_wav_rejected(tmp_path: pytest.TempPathFactory) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"NOT A WAV FILE")
    rows = [_real_row("RADIO-0001", str(bad), sha256="a" * 64)]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 0
    assert report["invalid_wav_ids"] == ["RADIO-0001"]


# ---------------------------------------------------------------------------
# Test 8 — Callsign schema validated.
# ---------------------------------------------------------------------------
def test_callsign_schema_validated(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "c.wav"))
    # Valid empty list.
    ok = _real_row("RADIO-0001", p, callsigns="[]")
    assert validate_dataset([ok])["verified_real_transmissions"] == 1
    # Valid non-empty list.
    ok2 = _real_row("RADIO-0002", p, callsigns='["ALPHA-21"]')
    assert validate_dataset([ok2])["verified_real_transmissions"] == 1
    # Malformed schema is rejected.
    bad = _real_row("RADIO-0003", p, callsigns="not-a-list")
    report = validate_dataset([bad])
    assert report["verified_real_transmissions"] == 0
    assert report["invalid_callsign_ids"] == ["RADIO-0003"]


# ---------------------------------------------------------------------------
# Test 9 — SHA mismatch detected.
# ---------------------------------------------------------------------------
def test_sha_mismatch_detected(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "s.wav"))
    rows = [_real_row("RADIO-0001", p, sha256="0" * 64)]
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 0
    assert report["sha_mismatch_ids"] == ["RADIO-0001"]


# ---------------------------------------------------------------------------
# Test 10 — Exactly 50 valid rows -> PASS.
# ---------------------------------------------------------------------------
def test_50_valid_rows_pass(tmp_path: pytest.TempPathFactory) -> None:
    rows = []
    for i in range(50):
        p = _write_wav(str(tmp_path / f"r{i}.wav"), value=1000 + i)
        rows.append(_real_row(f"RADIO-{i:04d}", p))
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 50
    assert report["gate_satisfied"] is True


# ---------------------------------------------------------------------------
# Test 11 — 49 valid rows -> FAIL.
# ---------------------------------------------------------------------------
def test_49_valid_rows_fail(tmp_path: pytest.TempPathFactory) -> None:
    rows = []
    for i in range(49):
        p = _write_wav(str(tmp_path / f"r{i}.wav"), value=2000 + i)
        rows.append(_real_row(f"RADIO-{i:04d}", p))
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 49
    assert report["gate_satisfied"] is False


# ---------------------------------------------------------------------------
# Test 12 — 51 valid rows + 10 fixtures -> PASS with count 51, not 61.
# ---------------------------------------------------------------------------
def test_51_valid_plus_10_fixtures(tmp_path: pytest.TempPathFactory) -> None:
    rows = []
    for i in range(51):
        p = _write_wav(str(tmp_path / f"r{i}.wav"), value=3000 + i)
        rows.append(_real_row(f"RADIO-{i:04d}", p))
    for i in range(10):
        p = _write_wav(str(tmp_path / f"f{i}.wav"), value=9000 + i)
        rows.append(_fixture_row(f"FIX-{i:04d}", p))
    report = validate_dataset(rows)
    assert report["verified_real_transmissions"] == 51
    assert report["fixture_rows"] == 10
    assert report["real_transmissions"] == 51
    assert report["gate_satisfied"] is True


# ---------------------------------------------------------------------------
# Unit-level helpers.
# ---------------------------------------------------------------------------
def test_classification_and_provenance_helpers(tmp_path: pytest.TempPathFactory) -> None:
    p = _write_wav(str(tmp_path / "h.wav"))
    real = _real_row("RADIO-0001", p)
    assert is_real_transmission(real) is True
    assert is_provenance_valid(real) is True
    assert has_ground_truth(real) is True
    assert has_verified_ground_truth(real) is True

    fixture = _fixture_row("FIX-0001", p)
    assert is_real_transmission(fixture) is False
    assert has_ground_truth(fixture) is False


def test_load_manifest_roundtrip(tmp_path: pytest.TempPathFactory) -> None:
    import csv

    fields = [
        "audio_id", "audio_path", "sha256", "source_type", "real_transmission",
        "capture_timestamp", "duration_seconds", "sample_rate", "channels",
        "sample_width_bits", "codec", "speaker_or_source", "transcript",
        "callsigns_present", "ground_truth_verified", "independent_verification",
        "verification_method", "provenance", "notes",
    ]
    p = _write_wav(str(tmp_path / "m.wav"))
    csv_path = tmp_path / "m.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerow(_real_row("RADIO-0001", p))
    rows = load_manifest(str(csv_path))
    assert len(rows) == 1
    assert rows[0]["audio_id"] == "RADIO-0001"
