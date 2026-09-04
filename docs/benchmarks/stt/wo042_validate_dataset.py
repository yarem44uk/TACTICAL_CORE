#!/usr/bin/env python3
"""WO-042 — Real radio speech STT benchmark dataset validator (isolated, offline,
stdlib-only).

This is dataset *validation* tooling only (WO-042 §3.A, §13).  It is
deliberately:

    * isolated     — self-contained; does not touch the production STT seam,
                     the audio pipeline, or any STT engine;
    * offline      — uses only the Python standard library; never runs STT
                     inference, never downloads a model, never calls a network
                     API;
    * read-only    — opens WAV masters in ``rb`` and never writes to them;
    * engine-neutral — it does not favour faster_whisper or vosk and does not
                     select any STT engine (WO-042 §17).

It validates a WO-042 dataset manifest against the WO-042 dataset definition
(§7, §11, §12, §13):

    1. manifest field completeness (§7);
    2. WAV master validity (§11): exists, readable, valid WAV, duration > 0,
       sample rate / channels / sample width valid, and the declared audio
       properties match the actual file;
    3. real-transmission classification (§11): distinguishes ``real_transmission``
       from fixture / synthetic / tone using provenance and source_type, not
       filename or location;
    4. ground-truth requirement (§8): every counted real transmission must carry
       a non-empty manual transcript;
    5. callsign annotation schema (§9): ``callsigns_present`` must be a valid
       JSON array (empty ``[]`` when no callsign is audibly present);
    6. SHA-256 integrity and duplicate control (§6, §11): the declared SHA-256
       must match the file bytes; identical content counts once;
    7. independent verification (§10): every counted row must be flagged
       ``ground_truth_verified`` and ``independent_verification``;
    8. dataset gate (§12): valid independently verified real transmissions
       >= 50; fixtures / synthetic / duplicates do not count.

The counting formula (§12) is deterministic:

    valid_real_transmissions = sum(
        real_transmission
        and ground_truth_verified
        and independent_verification
        and not duplicate
        and provenance_valid
        and sha_valid
        and wav_valid
        and callsign_schema_valid
        for row in manifest
    )

A row with UNKNOWN provenance, a fixture/synthetic marker, a missing or
unverified transcript, a duplicate SHA, a SHA mismatch, an invalid WAV, or a
malformed callsign field is NOT counted.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import wave
from typing import Any

# ---------------------------------------------------------------------------
# WO-042 dataset definition constants (§7, §11, §12).
# ---------------------------------------------------------------------------

# Minimum number of valid independently verified real transmissions (§12).
MIN_REAL_TRANSMISSIONS = 50

# Stable, deterministic column order for the dataset manifest (§7).
MANIFEST_FIELDS = [
    "audio_id",
    "audio_path",
    "sha256",
    "source_type",
    "real_transmission",
    "capture_timestamp",
    "duration_seconds",
    "sample_rate",
    "channels",
    "sample_width_bits",
    "codec",
    "speaker_or_source",
    "transcript",
    "callsigns_present",
    "ground_truth_verified",
    "independent_verification",
    "verification_method",
    "provenance",
    "notes",
]

REQUIRED_FIELDS = set(MANIFEST_FIELDS)

# Provenance / source_type markers that identify a recording as NOT a real
# radio speech transmission (§11 exclusion rules).
NON_REAL_MARKERS = (
    "fixture",
    "unit-test",
    "unit test",
    "test fixture",
    "test tone",
    "no speech",
    "contains no speech",
    "not a real radio",
    "constant-amplitude",
    "synthetic",
    "tts",
    "generated speech",
    "carrier noise",
    "carrier signal",
)

# Recognized real-radio source types.  An UNKNOWN / fixture / synthetic
# source_type is not a valid provenance for a counted real transmission.
REAL_SOURCE_TYPES = {
    "radio",
    "sdr",
    "rtl-sdr",
    "rtlsdr",
    "receiver",
    "scanner",
    "capture",
    "airband",
    "vhf",
    "uhf",
    "hf",
    "handheld",
    "base station",
    "satcom",
}

# Values that are explicitly unknown and therefore cannot be proven.
UNKNOWN_LITERALS = {"", "unknown", "n/a", "none", "?"}


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def _normalize(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: str) -> str:
    """SHA-256 of the exact file bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_true(value: Any) -> bool:
    """Interpret a manifest field as a boolean ('' / 'false' / '0' -> False)."""
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes")


def _is_unknown(value: Any) -> bool:
    v = _normalize(value).lower()
    return v in UNKNOWN_LITERALS or v == "unknown"


def _parse_callsigns(value: Any) -> tuple[bool, list[str]]:
    """Validate the callsign annotation schema (§9).

    ``callsigns_present`` must be a JSON array (e.g. ``[]`` or
    ``["ALPHA-21"]``).  An empty string is tolerated and normalised to ``[]``.
    Returns ``(ok, list)``; ``ok`` is False for a malformed value so the audit
    report can flag the schema error explicitly rather than guess.
    """
    raw = _normalize(value)
    if raw == "":
        return True, []
    if raw.upper() == "UNKNOWN":
        return False, []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False, []
    if not isinstance(parsed, list):
        return False, []
    if not all(isinstance(item, str) for item in parsed):
        return False, []
    return True, parsed


def _has_non_real_marker(provenance: Any) -> bool:
    prov = _normalize(provenance).lower()
    return any(m in prov for m in NON_REAL_MARKERS)


def is_real_transmission(row: dict[str, Any]) -> bool:
    """A row is a real transmission only when the manifest explicitly marks it
    real AND its provenance carries no fixture / synthetic marker.  Never
    inferred from filename or location alone (§11)."""
    if not _csv_true(row.get("real_transmission")):
        return False
    if _has_non_real_marker(row.get("provenance")):
        return False
    return True


def is_provenance_valid(row: dict[str, Any]) -> bool:
    """True when provenance is real, explicit and from a recognized source.

    A counted row must have a non-empty, non-UNKNOWN provenance, no
    fixture/synthetic marker, and a recognized real-radio source_type.
    """
    prov = _normalize(row.get("provenance"))
    src = _normalize(row.get("source_type")).lower()
    if _is_unknown(prov):
        return False
    if _has_non_real_marker(prov):
        return False
    if _is_unknown(src) or src == "":
        return False
    if src in ("fixture", "synthetic", "test", "tone", "unit-test", "generated"):
        return False
    if src not in REAL_SOURCE_TYPES:
        return False
    return True


def has_ground_truth(row: dict[str, Any]) -> bool:
    """True when the row carries a non-empty manual transcript (§8)."""
    return bool(_normalize(row.get("transcript")))


def has_verified_ground_truth(row: dict[str, Any]) -> bool:
    """True when the row carries a non-empty transcript AND is flagged as
    manually verified (§10)."""
    return has_ground_truth(row) and _csv_true(row.get("ground_truth_verified"))


def validate_wav(path: str) -> tuple[bool, dict[str, Any]]:
    """Validate a WAV master read-only (§11).

    Returns ``(ok, info)`` where ``info`` carries the measured metadata (in the
    WO-042 schema units, including ``sample_width_bits``) plus the file
    ``sha256``, or the failure reason.  Never raises for a bad file; it returns
    ``ok=False`` with the reason so the audit report records the failure
    explicitly.
    """
    info: dict[str, Any] = {"path": path, "ok": False}
    try:
        if not os.path.exists(path):
            info["reason"] = "file not found"
            return False, info
        if not os.path.isfile(path):
            info["reason"] = "not a regular file"
            return False, info
        if not os.access(path, os.R_OK):
            info["reason"] = "file not readable"
            return False, info
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            nframes = wf.getnframes()
            duration = nframes / sample_rate if sample_rate else 0.0
        if sample_rate <= 0:
            info["reason"] = "invalid sample rate"
            return False, info
        if channels <= 0:
            info["reason"] = "invalid channel count"
            return False, info
        if sampwidth <= 0:
            info["reason"] = "invalid sample width"
            return False, info
        if duration <= 0:
            info["reason"] = "zero duration"
            return False, info
        info.update(
            ok=True,
            channels=channels,
            sample_width_bits=sampwidth * 8,
            sample_rate=sample_rate,
            duration_seconds=round(duration, 4),
            frames=nframes,
            sha256=_sha256(path),
        )
        return True, info
    except wave.Error as exc:
        info["reason"] = f"invalid WAV: {exc}"
        return False, info
    except Exception as exc:  # noqa: BLE001 - record any failure explicitly
        info["reason"] = f"read error: {type(exc).__name__}: {exc}"
        return False, info


def load_manifest(path: str) -> list[dict[str, Any]]:
    """Load a WO-042 manifest CSV into a list of row dicts."""
    rows: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows


def _missing_fields(row: dict[str, Any]) -> list[str]:
    return [f for f in REQUIRED_FIELDS if f not in row]


# ---------------------------------------------------------------------------
# Dataset validation.
# ---------------------------------------------------------------------------
def validate_dataset(
    rows: list[dict[str, Any]],
    *,
    min_real: int = MIN_REAL_TRANSMISSIONS,
) -> dict[str, Any]:
    """Validate a WO-042 dataset manifest (§7, §8, §9, §10, §11, §12).

    Returns a structured, fact-based report.  It does not fabricate or relax
    anything: a row counts as a valid real transmission only when it is
    explicitly marked real, its provenance is valid, its WAV master exists and
    is valid with matching SHA-256 and audio properties, it carries a non-empty
    manual transcript, a valid callsign schema, and is flagged as both
    ground-truth-verified and independently verified, and it is not a duplicate
    of earlier content.
    """
    report: dict[str, Any] = {
        "manifest_rows": len(rows),
        "real_transmissions": 0,
        "fixture_rows": 0,
        "duplicates": 0,
        "verified_real_transmissions": 0,
        "invalid_rows": 0,
        "invalid_audio_ids": [],
        "duplicate_audio_ids": [],
        "duplicate_sha_ids": [],
        "missing_fields_rows": [],
        "missing_transcript_ids": [],
        "sha_mismatch_ids": [],
        "invalid_wav_ids": [],
        "missing_file_ids": [],
        "invalid_callsign_ids": [],
        "provenance_invalid_ids": [],
        "unverified_ids": [],
        "duplicate_audio_id_count": 0,
        "gate_satisfied": False,
        "minimum_required": min_real,
    }

    seen_sha: dict[str, str] = {}
    seen_audio_id: dict[str, str] = {}

    for row in rows:
        audio_id = _normalize(row.get("audio_id"))
        path = row.get("audio_path") or ""
        sha = _normalize(row.get("sha256"))
        real = is_real_transmission(row)

        # audio_id uniqueness.
        if audio_id in seen_audio_id:
            report["duplicate_audio_id_count"] += 1
            report["duplicate_audio_ids"].append(audio_id)
        else:
            seen_audio_id[audio_id] = path

        # Duplicate content by SHA-256 (§6, §11): identical content counts once.
        is_duplicate = False
        if sha:
            if sha in seen_sha:
                report["duplicates"] += 1
                report["duplicate_sha_ids"].append(audio_id)
                is_duplicate = True
            else:
                seen_sha[sha] = audio_id

        if not real:
            report["fixture_rows"] += 1
            continue

        # ---- Real transmission path: every check must pass to count. ----
        report["real_transmissions"] += 1
        row_invalid = False

        if _missing_fields(row):
            report["missing_fields_rows"].append(audio_id)
            row_invalid = True

        if not is_provenance_valid(row):
            report["provenance_invalid_ids"].append(audio_id)
            row_invalid = True

        if is_duplicate:
            row_invalid = True

        if not row_invalid:
            ok, info = validate_wav(path)
            if not ok:
                if info.get("reason") == "file not found":
                    report["missing_file_ids"].append(audio_id)
                else:
                    report["invalid_wav_ids"].append(audio_id)
                row_invalid = True
            else:
                # SHA-256 integrity (§13): declared hash must match file bytes.
                if sha and info.get("sha256") != sha:
                    report["sha_mismatch_ids"].append(audio_id)
                    row_invalid = True

                # Audio properties (§13): declared values must match the file.
                if not row_invalid:
                    if _normalize(row.get("sample_rate")) != str(info["sample_rate"]):
                        row_invalid = True
                    elif _normalize(row.get("channels")) != str(info["channels"]):
                        row_invalid = True
                    elif _normalize(row.get("sample_width_bits")) != str(
                        info["sample_width_bits"]
                    ):
                        row_invalid = True
                    elif abs(
                        float(_normalize(row.get("duration_seconds")) or "0")
                        - info["duration_seconds"]
                    ) > 0.01:
                        row_invalid = True

        if not row_invalid:
            cok, _clist = _parse_callsigns(row.get("callsigns_present"))
            if not cok:
                report["invalid_callsign_ids"].append(audio_id)
                row_invalid = True

        if not row_invalid:
            if not has_ground_truth(row):
                report["missing_transcript_ids"].append(audio_id)
                row_invalid = True

        if not row_invalid:
            if not _csv_true(row.get("ground_truth_verified")):
                report["unverified_ids"].append(audio_id)
                row_invalid = True
            elif not _csv_true(row.get("independent_verification")):
                report["unverified_ids"].append(audio_id)
                row_invalid = True

        if row_invalid:
            report["invalid_rows"] += 1
            report["invalid_audio_ids"].append(audio_id)
        else:
            report["verified_real_transmissions"] += 1

    report["gate_satisfied"] = (
        report["verified_real_transmissions"] >= min_real
    )
    return report


def format_report(report: dict[str, Any]) -> str:
    """Render a validation report as deterministic text (§13 example)."""
    lines = [
        "VALIDATION RESULT",
        "=" * 30,
        f"manifest_rows: {report['manifest_rows']}",
        f"real_transmissions: {report['real_transmissions']}",
        f"fixture_rows: {report['fixture_rows']}",
        f"duplicates: {report['duplicates']}",
        f"verified_real_transmissions: {report['verified_real_transmissions']}",
        f"invalid_rows: {report['invalid_rows']}",
        "",
        "DATASET GATE:",
        "PASS" if report["gate_satisfied"] else "FAIL",
        "",
        f"minimum_required: {report['minimum_required']}",
        f"valid_real_transmissions: {report['verified_real_transmissions']}",
    ]

    def _detail(label: str, ids: list[str]) -> None:
        if ids:
            lines.append(f"{label}:")
            lines.append("  " + ", ".join(sorted(set(ids))))

    _detail("invalid audio ids", report["invalid_audio_ids"])
    _detail("missing fields ids", report["missing_fields_rows"])
    _detail("provenance invalid ids", report["provenance_invalid_ids"])
    _detail("duplicate sha ids", report["duplicate_sha_ids"])
    _detail("missing file ids", report["missing_file_ids"])
    _detail("invalid wav ids", report["invalid_wav_ids"])
    _detail("sha mismatch ids", report["sha_mismatch_ids"])
    _detail("invalid callsign ids", report["invalid_callsign_ids"])
    _detail("missing transcript ids", report["missing_transcript_ids"])
    _detail("unverified ids", report["unverified_ids"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  ``wo042_validate_dataset.py --manifest <csv>``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="WO-042 dataset validator (offline, stdlib-only)"
    )
    parser.add_argument("--manifest", required=True, help="path to wo042_dataset_manifest.csv")
    parser.add_argument("--min-real", type=int, default=MIN_REAL_TRANSMISSIONS)
    args = parser.parse_args(argv)

    rows = load_manifest(args.manifest)
    report = validate_dataset(rows, min_real=args.min_real)
    print(format_report(report))
    return 0 if report["gate_satisfied"] else 1


if __name__ == "__main__":
    sys.exit(main())
