"""WO-069 — benchmark unit tests: dataset loading, references, integrity.

All audio fixtures here are SYNTHETIC TEST FIXTURE (generated constant-amplitude
tones).  They exercise harness mechanics only and never enter a real benchmark
result or provide any real ground truth.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import os
import struct
import sys
import tempfile
import wave

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from wo069_dataset import (
    EXPECTED_RECORD_COUNT,
    DatasetError,
    DatasetRecord,
    artifact_resolution,
    build_records,
    dataset_manifest_document,
    load_human_review,
    load_manifest,
    sha256_file,
    verify_wav_integrity,
)


def _write_wav(path: str, frames: int = 800, rate: int = 8000, channels: int = 1,
               width: int = 2, value: int = 100) -> None:
    """SYNTHETIC TEST FIXTURE: a constant-amplitude tone."""
    with wave.open(path, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<h", value) * frames)


def _make_dataset(root: str, count: int = 3, rate: int = 8000) -> None:
    audio = os.path.join(root, "dataset", "audio")
    os.makedirs(audio, exist_ok=True)
    os.makedirs(os.path.join(root, "dataset", "ground_truth"), exist_ok=True)
    rows = []
    for i in range(1, count + 1):
        message_id = f"msg_{i:04d}"
        wav_path = os.path.join(audio, f"{message_id}.wav")
        _write_wav(wav_path, rate=rate)
        rows.append(
            {
                "sample_id": message_id,
                "source_id": "S1",
                "file": f"audio/{message_id}.wav",
                "sha256": sha256_file(wav_path),
                "sample_rate": str(rate),
                "channels": "1",
                "sample_width_bits": "16",
                "duration_seconds": "0.1",
                "language": "UNDETERMINED",
                "ground_truth_status": "UNAVAILABLE",
            }
        )
    with open(os.path.join(root, "dataset", "manifest.csv"), "w", newline="",
              encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(root, "dataset", "ground_truth", "ground_truth.json"),
              "w", encoding="utf-8") as fh:
        fh.write('{"entries": []}\n')


def _make_review(path: str, message_ids: list[str], *, reviewer: str = "TESTER",
                 with_transcript: bool = False, with_callsign: bool = False) -> None:
    fields = [
        "message_id", "stream_id", "audible_voice", "intelligible", "radio_style",
        "speaker", "dialogue_candidate", "voice_type", "confidence", "transcript",
        "callsign", "notes", "reviewer", "review_time",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for message_id in message_ids:
            writer.writerow(
                {
                    "message_id": message_id,
                    "stream_id": "S1",
                    "audible_voice": "YES",
                    "intelligible": "YES",
                    "radio_style": "YES",
                    "speaker": "UNKNOWN",
                    "dialogue_candidate": "YES",
                    "voice_type": "FEMALE",
                    "confidence": "HIGH",
                    "transcript": "тест" if with_transcript else "",
                    "callsign": "ALPHA" if with_callsign else "",
                    "notes": "",
                    "reviewer": reviewer,
                    "review_time": "12:00",
                }
            )


# --- manifest loading --------------------------------------------------------


def test_load_manifest_reads_rows():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 3)
        rows = load_manifest(root)
        assert len(rows) == 3
        assert rows[0]["sample_id"] == "msg_0001"


def test_load_manifest_missing_raises():
    with tempfile.TemporaryDirectory() as root:
        with pytest.raises(DatasetError):
            load_manifest(root)


def test_build_records_maps_manifest_fields():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 2)
        review = os.path.join(root, "human_review.csv")
        _make_review(review, ["msg_0001", "msg_0002"])
        records = build_records(root, review)
        assert [r.message_id for r in records] == ["msg_0001", "msg_0002"]
        assert records[0].stream_id == "S1"
        assert records[0].duration_seconds == pytest.approx(0.1)
        assert records[0].human_language == "UNKNOWN"  # UNDETERMINED -> UNKNOWN
        assert records[0].human_review_status == "REVIEWED"


# --- reference transcripts / callsigns --------------------------------------


def test_missing_reference_transcript_is_not_invented():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        review = os.path.join(root, "human_review.csv")
        _make_review(review, ["msg_0001"], with_transcript=False)
        records = build_records(root, review)
        assert records[0].reference_available is False
        assert records[0].human_reference_transcript is None
        assert records[0].callsign_reference_available is False


def test_reference_transcript_is_loaded_when_present():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        review = os.path.join(root, "human_review.csv")
        _make_review(review, ["msg_0001"], with_transcript=True, with_callsign=True)
        records = build_records(root, review)
        assert records[0].reference_available is True
        assert records[0].human_reference_transcript == "тест"
        assert records[0].callsign_reference_available is True
        assert records[0].human_callsign == "ALPHA"


def test_absent_human_review_artifact_yields_empty_mapping():
    assert load_human_review("/nonexistent/human_review.csv") == {}


def test_pending_rows_are_not_marked_reviewed():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        review = os.path.join(root, "human_review.csv")
        _make_review(review, ["msg_0001"], reviewer="")
        records = build_records(root, review)
        assert records[0].human_review_status == "PENDING"


# --- integrity ---------------------------------------------------------------


def test_verify_wav_integrity_ok():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        record = build_records(root, None)[0]
        verified = verify_wav_integrity(record)
        assert verified.integrity_ok is True
        assert verified.integrity_error is None


def test_missing_wav_is_recorded_not_skipped():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        record = build_records(root, None)[0]
        os.remove(record.wav_path)
        verified = verify_wav_integrity(record)
        assert verified.integrity_ok is False
        assert verified.integrity_error == "MISSING_WAV"


def test_sha256_mismatch_is_detected():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        record = build_records(root, None)[0]
        _write_wav(record.wav_path, value=222)  # tamper the fixture
        verified = verify_wav_integrity(record)
        assert verified.integrity_ok is False
        assert verified.integrity_error == "SHA256_MISMATCH"


def test_format_mismatch_is_detected():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1, rate=16000)
        record = build_records(root, None)[0]
        verified = verify_wav_integrity(record)
        assert verified.integrity_ok is False
        assert str(verified.integrity_error).startswith("FORMAT_MISMATCH")


# --- dataset manifest document ----------------------------------------------


def test_manifest_document_counts_and_completeness():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 3)
        review = os.path.join(root, "human_review.csv")
        _make_review(review, ["msg_0001", "msg_0002", "msg_0003"])
        records = build_records(root, review)
        for record in records:
            verify_wav_integrity(record)
        document = dataset_manifest_document(
            records, dataset_root=root, human_review_csv=review, expected_count=3
        )
        assert document["record_count"] == 3
        assert document["completeness"] == "COMPLETE"
        assert document["wav_count"] == 3
        assert document["human_reviewed_count"] == 3
        assert document["reference_transcript_count"] == 0
        assert document["reference_transcript_status"] == "UNAVAILABLE"


def test_manifest_document_reports_dataset_incomplete():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 2)
        records = build_records(root, None)
        document = dataset_manifest_document(
            records, dataset_root=root, human_review_csv=None,
            expected_count=EXPECTED_RECORD_COUNT,
        )
        assert document["completeness"] == "DATASET INCOMPLETE"
        assert document["record_count"] == 2


def test_artifact_resolution_reports_named_artifact_absence():
    with tempfile.TemporaryDirectory() as root:
        _make_dataset(root, 1)
        resolution = artifact_resolution(root, None)
        # The WO-named xlsx does not exist in the fixture environment either.
        assert resolution["named_in_work_order"].endswith(".xlsx")
        assert resolution["dataset_manifest_present"] is True
        assert resolution["human_review_csv_present"] is False
