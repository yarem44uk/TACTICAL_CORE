"""WO-069 — Real radio STT benchmark: dataset layer (benchmark-only, READ-ONLY).

This module is the benchmark's read-only view of the WO-068 human-reviewed
dataset.  It never writes to, normalizes, or re-labels any input artifact.

Inputs (all treated as READ-ONLY evidence):

  * WO-068 frozen dataset root (manifest + WAV audio + ground-truth sidecar)
  * the human-review workbook/CSV produced by the human listening review

The human transcript, when present, is a human reference annotation supplied by
the human reviewer.  It is NOT proof of RF origin, real-world transmission,
operational callsign, speaker identity or transport provenance.

WO-069 §DATASET names the primary artifact as ``WO-068-HUMAN-REVIEW-EXTENDED.xlsx``.
This module resolves the artifact *that actually exists* and records the
discrepancy explicitly (``artifact_resolution``); it never fabricates the
missing artifact and never demands a format that is absent.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import hashlib
import os
import wave
from dataclasses import asdict, dataclass

# --- documented, external, read-only inputs ---------------------------------

DEFAULT_DATASET_ROOT = "/opt/data/wo068_real_radio_stt_benchmark_v1"
DEFAULT_MANIFEST_REL = "dataset/manifest.csv"
DEFAULT_AUDIO_DIR_REL = "dataset/audio"
DEFAULT_GROUND_TRUTH_REL = "dataset/ground_truth/ground_truth.json"
DEFAULT_HUMAN_REVIEW_CSV = "/opt/data/uploads/1789807255-6bf70d4b/human_review.csv"

#: Artifact the work order names, but which is absent from the environment.
WO068_HUMAN_REVIEW_EXTENDED_XLSX = "WO-068-HUMAN-REVIEW-EXTENDED.xlsx"

EXPECTED_RECORD_COUNT = 67

UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
NOT_MEASURED = "NOT_MEASURED"

REVIEWED = "REVIEWED"
PENDING = "PENDING"


class DatasetError(Exception):
    """Raised when the dataset cannot be located or is structurally invalid."""


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file, streamed (read-only)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class DatasetRecord:
    """One dataset message record joined with its human-review annotation."""

    message_id: str
    stream_id: str
    wav_path: str
    duration_seconds: float
    dataset_sha256: str

    # human-review annotation (categorical listening review)
    human_review_status: str = PENDING
    human_audible_voice: str = ""
    human_intelligible: str = ""
    human_radio_style: str = ""
    human_speaker: str = ""
    human_dialogue_candidate: str = ""
    human_voice_type: str = ""
    human_confidence: str = ""
    human_reviewer: str = ""
    human_review_time: str = ""
    human_language: str = UNKNOWN

    # human reference annotation — supplied by a human listener, or absent.
    human_reference_transcript: str | None = None
    human_callsign: str | None = None
    reference_available: bool = False
    callsign_reference_available: bool = False

    # integrity of the audio artifact
    integrity_ok: bool | None = None
    integrity_error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _read_csv_rows(path: str) -> list[dict]:
    """Read a CSV/SCSV table, sniffing the delimiter (',' or ';')."""
    with open(path, newline="", encoding="utf-8") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","
        return list(csv.DictReader(fh, delimiter=delimiter))


def load_manifest(dataset_root: str = DEFAULT_DATASET_ROOT) -> list[dict]:
    """Load the WO-068 dataset manifest rows (read-only)."""
    path = os.path.join(dataset_root, DEFAULT_MANIFEST_REL)
    if not os.path.exists(path):
        raise DatasetError(f"dataset manifest not found: {path}")
    rows = _read_csv_rows(path)
    if not rows:
        raise DatasetError(f"dataset manifest is empty: {path}")
    return rows


def load_human_review(csv_path: str | None = DEFAULT_HUMAN_REVIEW_CSV) -> dict[str, dict]:
    """Load the human listening review keyed by ``message_id`` (read-only).

    Returns an empty mapping when no human-review artifact is available; that is
    recorded upstream as ``DATASET INCOMPLETE`` rather than silently ignored.
    """
    if not csv_path or not os.path.exists(csv_path):
        return {}
    return {r.get("message_id", ""): r for r in _read_csv_rows(csv_path)}


def _is_set(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.upper() not in {
        UNAVAILABLE, UNKNOWN, "UNDETERMINED", "NONE", "PENDING", "N/A",
    }


def _resolve_wav_path(dataset_root: str, rel: str) -> str:
    """Resolve a manifest ``file`` entry to the real WAV path (read-only).

    The WO-068 dataset root holds the audio under ``dataset/`` (``file`` entries
    are relative to that directory).  Both layouts are tried; the actual,
    existing path wins.  A path that resolves nowhere is returned as the
    canonical ``dataset/``-relative form and later reported as MISSING_WAV.
    """
    if not rel:
        return ""
    direct = os.path.join(dataset_root, rel)
    if os.path.exists(direct):
        return direct
    nested = os.path.join(dataset_root, DEFAULT_AUDIO_DIR_REL, os.path.basename(rel))
    if os.path.exists(nested):
        return nested
    return os.path.join(dataset_root, DEFAULT_AUDIO_DIR_REL, os.path.basename(rel))


def build_records(
    dataset_root: str = DEFAULT_DATASET_ROOT,
    human_review_csv: str | None = DEFAULT_HUMAN_REVIEW_CSV,
) -> list[DatasetRecord]:
    """Build the benchmark record set: manifest joined with the human review.

    A reference transcript / callsign is populated ONLY when the human-review
    artifact itself carries one for that message.  Nothing is inferred.
    """
    review = load_human_review(human_review_csv)
    records: list[DatasetRecord] = []
    for row in load_manifest(dataset_root):
        message_id = row.get("sample_id") or row.get("message_id") or ""
        rel = row.get("file") or ""
        wav_path = _resolve_wav_path(dataset_root, rel)
        duration = float(row.get("duration_seconds") or 0.0)

        rev = review.get(message_id, {})
        reference_transcript = rev.get("transcript") or rev.get("reference_transcript")
        callsign = rev.get("callsign")
        language = row.get("language") or UNKNOWN
        if not _is_set(language):
            language = UNKNOWN

        reviewer = (rev.get("reviewer") or "").strip()
        rec = DatasetRecord(
            message_id=message_id,
            stream_id=row.get("source_id") or row.get("stream_id") or "",
            wav_path=wav_path,
            duration_seconds=duration,
            dataset_sha256=row.get("sha256") or "",
            human_review_status=REVIEWED if reviewer else PENDING,
            human_audible_voice=(rev.get("audible_voice") or "").strip(),
            human_intelligible=(rev.get("intelligible") or "").strip(),
            human_radio_style=(rev.get("radio_style") or "").strip(),
            human_speaker=(rev.get("speaker") or "").strip(),
            human_dialogue_candidate=(rev.get("dialogue_candidate") or "").strip(),
            human_voice_type=(rev.get("voice_type") or "").strip(),
            human_confidence=(rev.get("confidence") or "").strip(),
            human_reviewer=reviewer,
            human_review_time=(rev.get("review_time") or "").strip(),
            human_language=language,
            human_reference_transcript=(
                reference_transcript if _is_set(reference_transcript) else None
            ),
            human_callsign=callsign if _is_set(callsign) else None,
        )
        rec.reference_available = rec.human_reference_transcript is not None
        rec.callsign_reference_available = rec.human_callsign is not None
        records.append(rec)
    return records


def verify_wav_integrity(record: DatasetRecord, expected_rate: int = 8000) -> DatasetRecord:
    """Verify a WAV exists, matches its manifest SHA-256, and is 8 kHz PCM16 mono.

    Read-only: the audio file is opened for reading and never modified.
    """
    if not record.wav_path or not os.path.exists(record.wav_path):
        record.integrity_ok = False
        record.integrity_error = "MISSING_WAV"
        return record
    actual = sha256_file(record.wav_path)
    if record.dataset_sha256 and actual != record.dataset_sha256:
        record.integrity_ok = False
        record.integrity_error = "SHA256_MISMATCH"
        return record
    try:
        with wave.open(record.wav_path, "rb") as wav:
            fmt = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
    except Exception as exc:  # noqa: BLE001 - recorded, not raised
        record.integrity_ok = False
        record.integrity_error = f"MALFORMED_WAV: {type(exc).__name__}"
        return record
    if fmt[0] != expected_rate or fmt[1] != 1 or fmt[2] != 2:
        record.integrity_ok = False
        record.integrity_error = f"FORMAT_MISMATCH: rate={fmt[0]} ch={fmt[1]} width={fmt[2]}"
        return record
    record.integrity_ok = True
    record.integrity_error = None
    return record


def artifact_resolution(
    dataset_root: str = DEFAULT_DATASET_ROOT,
    human_review_csv: str | None = DEFAULT_HUMAN_REVIEW_CSV,
) -> dict:
    """Record exactly which artifacts exist, and which the WO names but are absent.

    This is evidence, not a workaround: a missing named artifact is reported.
    """
    manifest_path = os.path.join(dataset_root, DEFAULT_MANIFEST_REL)
    ground_truth_path = os.path.join(dataset_root, DEFAULT_GROUND_TRUTH_REL)
    xlsx_candidates = []
    search_roots = ("/opt/data", "/opt/data/uploads")
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if "/.git" in dirpath or "/site-packages" in dirpath:
                continue
            for name in filenames:
                if name.lower() == WO068_HUMAN_REVIEW_EXTENDED_XLSX.lower():
                    xlsx_candidates.append(os.path.join(dirpath, name))
    return {
        "named_in_work_order": WO068_HUMAN_REVIEW_EXTENDED_XLSX,
        "named_artifact_found": bool(xlsx_candidates),
        "named_artifact_paths": xlsx_candidates,
        "dataset_root": dataset_root,
        "dataset_manifest_path": manifest_path,
        "dataset_manifest_present": os.path.exists(manifest_path),
        "dataset_manifest_sha256": (
            sha256_file(manifest_path) if os.path.exists(manifest_path) else None
        ),
        "ground_truth_path": ground_truth_path,
        "ground_truth_present": os.path.exists(ground_truth_path),
        "ground_truth_sha256": (
            sha256_file(ground_truth_path) if os.path.exists(ground_truth_path) else None
        ),
        "human_review_csv_path": human_review_csv,
        "human_review_csv_present": bool(human_review_csv and os.path.exists(human_review_csv)),
        "human_review_csv_sha256": (
            sha256_file(human_review_csv)
            if human_review_csv and os.path.exists(human_review_csv)
            else None
        ),
    }


def dataset_manifest_document(
    records: list[DatasetRecord],
    *,
    dataset_root: str = DEFAULT_DATASET_ROOT,
    human_review_csv: str | None = DEFAULT_HUMAN_REVIEW_CSV,
    expected_count: int = EXPECTED_RECORD_COUNT,
) -> dict:
    """WO-069 DATASET MANIFEST (never guesses: unknown values are UNKNOWN)."""
    available = [r for r in records if not r.integrity_error or r.integrity_ok]
    wav_count = sum(1 for r in records if r.integrity_ok)
    total_duration = sum(r.duration_seconds for r in records)
    resolution = artifact_resolution(dataset_root, human_review_csv)
    reviewed = [r for r in records if r.human_review_status == REVIEWED]
    with_reference = [r for r in records if r.reference_available]
    with_callsign = [r for r in records if r.callsign_reference_available]

    completeness = "COMPLETE" if len(records) == expected_count else "DATASET INCOMPLETE"
    return {
        "schema": "wo069-dataset-manifest-v1",
        "dataset_name": "WO-068 real-radio STT benchmark dataset (human-reviewed)",
        "dataset_root": dataset_root,
        "dataset_version": "dataset-v1",
        "expected_record_count": expected_count,
        "record_count": len(records),
        "completeness": completeness,
        "message_ids": [r.message_id for r in records],
        "wav_count": wav_count,
        "wav_missing": [r.message_id for r in records if r.integrity_error == "MISSING_WAV"],
        "wav_integrity_failures": {
            r.message_id: r.integrity_error
            for r in records
            if r.integrity_ok is False
        },
        "total_duration_seconds": round(total_duration, 3),
        "dataset_manifest_sha256": resolution["dataset_manifest_sha256"],
        "ground_truth_sha256": resolution["ground_truth_sha256"],
        "human_review_source_path": human_review_csv,
        "human_review_source_sha256": resolution["human_review_csv_sha256"],
        "human_reviewed_count": len(reviewed),
        "human_review_pending_count": len(records) - len(reviewed),
        "reference_transcript_count": len(with_reference),
        "reference_callsign_count": len(with_callsign),
        "reference_transcript_status": (
            "AVAILABLE" if with_reference else UNAVAILABLE
        ),
        "reference_transcript_reason": (
            ""
            if with_reference
            else "the human listening review records categorical listening "
                 "labels only (audible_voice/intelligible/voice_type/...); "
                 "it carries no verbatim transcript for any message"
        ),
        "reference_callsign_status": "AVAILABLE" if with_callsign else UNAVAILABLE,
        "artifact_resolution": resolution,
        "provenance_note": (
            "Human transcript is a human reference annotation, not proof of RF "
            "origin, real-world transmission, operational callsign or speaker "
            "identity."
        ),
        "records": [r.to_dict() for r in records],
        "available_wav_count_reported": len(available),
    }


def write_json(path: str, document: dict) -> str:
    """Write a JSON document deterministically (never overwrites silently)."""
    import json
    from datetime import datetime, timezone

    target = path
    if os.path.exists(target):
        stem, ext = os.path.splitext(path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = f"{stem}.{stamp}{ext}"
    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    return target
