"""WO-067 — benchmark unit tests: dataset manifest + WAV integrity.

All fixtures here are SYNTHETIC TEST FIXTURE — generated WAVs that exist only to
exercise manifest parsing and integrity mechanics.  They are never used as
benchmark evidence and never enter a real result document.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import hashlib
import os
import struct
import sys
import tempfile
import wave

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from wo067_dataset import (
    EXPECTED_SOURCE_PCAP_SHA256,
    DatasetError,
    apply_ground_truth,
    load_ground_truth,
    load_manifest,
    sha256_file,
    verify_dataset_integrity,
    verify_wav_integrity,
)

# SYNTHETIC TEST FIXTURE anchor — NOT the real PRE-04 PCAP digest.
FIXTURE_PCAP_SHA = EXPECTED_SOURCE_PCAP_SHA256


def _write_wav(path: str, *, frames: int = 8000, rate: int = 8000, channels: int = 1,
               width: int = 2, value: int = 100) -> None:
    """SYNTHETIC TEST FIXTURE: a constant-amplitude tone file."""
    with wave.open(path, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<h", value) * frames)


def _manifest_row(**overrides) -> dict:
    row = {
        "candidate_id": "msg_0001",
        "stream_id": "S1",
        "ssrc": "0x42c7218e",
        "audio_path": "",
        "wav_sha256": "",
        "source_pcap_sha256": FIXTURE_PCAP_SHA,
        "packet_start": "1",
        "packet_end": "9",
        "rtp_timestamp_start": "0",
        "rtp_timestamp_end": "1600",
        "start_time_ms": "0.0",
        "end_time_ms": "200.0",
        "duration_ms": "200",
        "sample_rate_hz": "8000",
        "channels": "1",
        "sample_width_bits": "16",
        "codec": "PCM_S16LE_G711_ALAW_DECODED",
        "lossless": "true",
        "human_review": "HUMAN_REVIEWED_ACCEPTED",
        "human_speech_confirmed": "true",
        "ground_truth_transcript": "",
        "ground_truth_callsign": "",
        "ground_truth_status": "NOT_PROVIDED",
        "notes": "",
    }
    row.update(overrides)
    return row


def _write_manifest(path: str, rows: list[dict]) -> None:
    cols = list(_manifest_row().keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in cols})


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory(prefix="wo067_test_") as d:
        yield d


def test_manifest_parses_valid_row(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav, frames=8000)
    row = _manifest_row(audio_path=wav, wav_sha256=sha256_file(wav))
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])

    ds = load_manifest(mf)
    assert ds.count == 1
    c = ds.candidates[0]
    assert c.candidate_id == "msg_0001"
    assert c.stream_id == "S1"
    assert c.duration_ms == 200
    assert c.lossless is True
    assert c.human_speech_confirmed is True
    assert c.has_ground_truth_transcript is False


def test_manifest_deterministic_ordering(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav)
    digest = sha256_file(wav)
    rows = [
        _manifest_row(candidate_id="msg_0003", audio_path=wav, wav_sha256=digest),
        _manifest_row(candidate_id="msg_0001", audio_path=wav, wav_sha256=digest),
        _manifest_row(candidate_id="msg_0002", audio_path=wav, wav_sha256=digest),
    ]
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, rows)
    ds = load_manifest(mf)
    assert [c.candidate_id for c in ds.candidates] == ["msg_0001", "msg_0002", "msg_0003"]


def test_duplicate_candidate_ids_rejected(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav)
    digest = sha256_file(wav)
    rows = [
        _manifest_row(candidate_id="msg_0001", audio_path=wav, wav_sha256=digest),
        _manifest_row(candidate_id="msg_0001", audio_path=wav, wav_sha256=digest),
    ]
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, rows)
    with pytest.raises(DatasetError, match="duplicate candidate_id"):
        load_manifest(mf)


def test_missing_manifest_rejected(workdir) -> None:
    with pytest.raises(DatasetError, match="manifest not found"):
        load_manifest(os.path.join(workdir, "nope.csv"))


def test_missing_columns_rejected(workdir) -> None:
    mf = os.path.join(workdir, "m.csv")
    with open(mf, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["candidate_id", "stream_id"])
        writer.writerow(["msg_0001", "S1"])
    with pytest.raises(DatasetError, match="missing required columns"):
        load_manifest(mf)


def test_non_integer_field_rejected(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav)
    row = _manifest_row(
        audio_path=wav, wav_sha256=sha256_file(wav), packet_start="not-a-number"
    )
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    with pytest.raises(DatasetError, match="packet_start"):
        load_manifest(mf)


def test_wrong_source_pcap_digest_rejected(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav)
    row = _manifest_row(
        audio_path=wav,
        wav_sha256=sha256_file(wav),
        source_pcap_sha256="deadbeef" * 8,
    )
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    with pytest.raises(DatasetError, match="source_pcap_sha256"):
        load_manifest(mf)


def test_inconsistent_ground_truth_status_rejected(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav)
    row = _manifest_row(
        audio_path=wav,
        wav_sha256=sha256_file(wav),
        ground_truth_status="NOT_PROVIDED",
        ground_truth_transcript="щось",
    )
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    with pytest.raises(DatasetError, match="inconsistent record"):
        load_manifest(mf)


def test_integrity_ok(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav, frames=1600)  # 1600/8000 = 200 ms
    row = _manifest_row(audio_path=wav, wav_sha256=sha256_file(wav), duration_ms="200")
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    ds = load_manifest(mf)
    report = verify_wav_integrity(ds.candidates[0])
    assert report["ok"] is True
    assert report["sha256_match"] is True
    assert report["format_ok"] is True
    assert report["duration_ok"] is True
    assert report["problems"] == []


def test_integrity_detects_missing_wav(workdir) -> None:
    row = _manifest_row(
        audio_path=os.path.join(workdir, "absent.wav"), wav_sha256="ab" * 32
    )
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    ds = load_manifest(mf)
    report = verify_wav_integrity(ds.candidates[0])
    assert report["ok"] is False
    assert any("missing on disk" in p for p in report["problems"])


def test_integrity_detects_changed_wav(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav, frames=1600, value=100)
    row = _manifest_row(audio_path=wav, wav_sha256=sha256_file(wav), duration_ms="200")
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    ds = load_manifest(mf)

    # Alter the audio on disk -> digest must no longer match.
    _write_wav(wav, frames=1600, value=200)
    report = verify_wav_integrity(ds.candidates[0])
    assert report["ok"] is False
    assert report["sha256_match"] is False
    assert any("does not match the manifest" in p for p in report["problems"])


def test_integrity_detects_wrong_format(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav, frames=1600, rate=16000)  # wrong sample rate
    row = _manifest_row(audio_path=wav, wav_sha256=sha256_file(wav), duration_ms="100")
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [row])
    ds = load_manifest(mf)
    report = verify_wav_integrity(ds.candidates[0])
    assert report["format_ok"] is False
    assert report["ok"] is False


def test_dataset_integrity_lists_exclusions(workdir) -> None:
    good = os.path.join(workdir, "good.wav")
    _write_wav(good, frames=1600)
    rows = [
        _manifest_row(candidate_id="msg_0001", audio_path=good,
                      wav_sha256=sha256_file(good), duration_ms="200"),
        _manifest_row(candidate_id="msg_0002",
                      audio_path=os.path.join(workdir, "gone.wav"),
                      wav_sha256="cd" * 32),
    ]
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, rows)
    ds = load_manifest(mf)
    report = verify_dataset_integrity(ds)
    assert report["checked"] == 2
    assert report["ok"] == 1
    assert report["included_ids"] == ["msg_0001"]
    assert report["excluded_ids"] == ["msg_0002"]
    assert report["exclusions"][0]["candidate_id"] == "msg_0002"


def test_ground_truth_missing_file(workdir) -> None:
    with pytest.raises(DatasetError, match="ground-truth file not found"):
        load_ground_truth(os.path.join(workdir, "none.json"))


def test_ground_truth_malformed_json(workdir) -> None:
    p = os.path.join(workdir, "gt.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    with pytest.raises(DatasetError, match="not valid JSON"):
        load_ground_truth(p)


def test_ground_truth_wrong_shape(workdir) -> None:
    p = os.path.join(workdir, "gt.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{"entries": {"msg_0001": "x"}}')
    with pytest.raises(DatasetError, match="must be a list"):
        load_ground_truth(p)


def test_ground_truth_duplicate_ids(workdir) -> None:
    p = os.path.join(workdir, "gt.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(
            '{"entries": [{"candidate_id": "msg_0001", "transcript": "a"},'
            ' {"candidate_id": "msg_0001", "transcript": "b"}]}'
        )
    with pytest.raises(DatasetError, match="duplicate ground-truth"):
        load_ground_truth(p)


def test_ground_truth_empty_transcript_is_none(workdir) -> None:
    p = os.path.join(workdir, "gt.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{"entries": [{"candidate_id": "msg_0001", "transcript": ""}]}')
    gt = load_ground_truth(p)
    assert gt["entries"]["msg_0001"]["transcript"] is None


def test_apply_ground_truth_marks_status_and_warns_unknown(workdir) -> None:
    wav = os.path.join(workdir, "a.wav")
    _write_wav(wav, frames=1600)
    mf = os.path.join(workdir, "m.csv")
    _write_manifest(mf, [_manifest_row(audio_path=wav, wav_sha256=sha256_file(wav),
                                      duration_ms="200")])
    ds = load_manifest(mf)
    gt = {
        "entries": {
            "msg_0001": {"candidate_id": "msg_0001", "transcript": "привіт", "callsign": None},
            "msg_9999": {"candidate_id": "msg_9999", "transcript": "x", "callsign": None},
        }
    }
    updated = apply_ground_truth(ds, gt)
    c = updated.candidates[0]
    assert c.ground_truth_transcript == "привіт"
    assert c.ground_truth_status == "PROVIDED"
    assert any("unknown candidate ids" in w for w in updated.warnings)


def test_sha256_file_matches_hashlib(workdir) -> None:
    p = os.path.join(workdir, "blob.bin")
    payload = b"wo067" * 1000
    with open(p, "wb") as fh:
        fh.write(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()