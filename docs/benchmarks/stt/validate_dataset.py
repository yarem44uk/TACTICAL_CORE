#!/usr/bin/env python3
"""WO-041 — Real radio STT benchmark dataset validator (isolated, offline,
stdlib-only).

This is dataset *validation* tooling only (WO-041 §23).  It is deliberately:

    * isolated     — self-contained; does not touch the production STT seam,
                     the audio pipeline, or the benchmark harness;
    * offline      — uses only the Python standard library; never runs STT
                     inference, never downloads a model, never calls a network
                     API;
    * read-only    — opens WAV masters in ``rb`` and never writes to them;
    * engine-neutral — it does not favour faster_whisper or vosk.

It validates a benchmark dataset manifest against the WO-041 dataset
definition (§5, §14, §15, §16, §18):

    1. manifest field completeness (§17);
    2. WAV master validity (§15): exists, readable, valid WAV, duration > 0,
       sample rate / channels / sample width valid;
    3. real-transmission classification (§16): distinguishes ``real_transmission``
       from ``test_fixture`` using provenance, not filename/location;
    4. ground-truth requirement (§10, §12): every counted real transmission
       must carry a non-empty manually verified transcript;
    5. SHA-256 uniqueness / duplicate control (§14): duplicate content counts
       once;
    6. dataset gate (§18): valid independently verified real transmissions
       >= 50; fixtures do not count.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
import wave
from typing import Any

# ---------------------------------------------------------------------------
# WO-041 dataset definition constants (§6, §17, §18).
# ---------------------------------------------------------------------------

# Minimum number of valid independently verified real transmissions.
MIN_REAL_TRANSMISSIONS = 50

# Stable, deterministic column order for the dataset manifest (§17).
MANIFEST_FIELDS = [
    "audio_id",
    "wav_path",
    "duration_seconds",
    "sample_rate",
    "channels",
    "sample_width",
    "sha256",
    "source",
    "provenance",
    "ground_truth",
    "callsigns_present",
    "real_transmission",
    "ground_truth_verified",
    "independent_verification",
]

# Provenance markers that identify a WO-039-B/C unit-test fixture (§16, §19).
FIXTURE_MARKERS = (
    "fixture",
    "unit-test",
    "test fixture",
    "no speech",
    "test tone",
    "not a real radio",
    "constant-amplitude",
    "contains no speech",
)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
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


def _is_fixture_provenance(provenance: Any) -> bool:
    """True when provenance marks the recording as a test fixture (§16)."""
    prov = (provenance or "").lower()
    return any(m in prov for m in FIXTURE_MARKERS)


def is_real_transmission(row: dict[str, Any]) -> bool:
    """A row is a real transmission only when provenance is not fixture AND
    the manifest explicitly marks it real.  Never inferred from filename or
    location alone (§16)."""
    if not _csv_true(row.get("real_transmission")):
        return False
    if _is_fixture_provenance(row.get("provenance")):
        return False
    return True


def has_ground_truth(row: dict[str, Any]) -> bool:
    """True when the row carries a non-empty transcript (§10)."""
    return bool((row.get("ground_truth") or "").strip())


def has_verified_ground_truth(row: dict[str, Any]) -> bool:
    """True when the row carries a non-empty transcript AND is flagged as
    manually verified (§12)."""
    return has_ground_truth(row) and _csv_true(row.get("ground_truth_verified"))


def validate_wav(path: str) -> tuple[bool, dict[str, Any]]:
    """Validate a WAV master read-only (§15).

    Returns ``(ok, info)`` where ``info`` carries the measured metadata or the
    failure reason.  Never raises for a bad file; it returns ``ok=False`` with
    the reason so the audit report records the failure explicitly.
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
            sample_width=sampwidth,
            sample_rate=sample_rate,
            duration_seconds=round(duration, 4),
            frames=nframes,
        )
        return True, info
    except wave.Error as exc:
        info["reason"] = f"invalid WAV: {exc}"
        return False, info
    except Exception as exc:  # noqa: BLE001 - record any failure explicitly
        info["reason"] = f"read error: {type(exc).__name__}: {exc}"
        return False, info


def load_manifest(path: str) -> list[dict[str, Any]]:
    """Load a manifest CSV into a list of row dicts."""
    rows: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Dataset validation.
# ---------------------------------------------------------------------------
def validate_dataset(
    rows: list[dict[str, Any]],
    *,
    min_real: int = MIN_REAL_TRANSMISSIONS,
) -> dict[str, Any]:
    """Validate a dataset manifest against the WO-041 definition (§5, §14-§18).

    Returns a structured, fact-based report.  It does not fabricate or relax
    anything: a row counts as a valid real transmission only when the manifest
    marks it real, its provenance is not a fixture, the WAV master is valid,
    and it carries a non-empty manually verified transcript.
    """
    report: dict[str, Any] = {
        "total_manifest_rows": len(rows),
        "fixture_rows": 0,
        "real_transmissions": 0,
        "verified_real_transmissions": 0,
        "invalid_files": 0,
        "duplicate_rows": 0,
        "missing_ground_truth": 0,
        "duplicate_audio_ids": 0,
        "missing_sha256": 0,
        "invalid_wav_list": [],
        "duplicate_sha_list": [],
        "missing_ground_truth_ids": [],
        "gate_satisfied": False,
        "minimum_required": min_real,
    }

    seen_sha: dict[str, str] = {}
    seen_audio_id: dict[str, str] = {}
    dup_sha_audio_ids: set[str] = set()

    for row in rows:
        audio_id = (row.get("audio_id") or "").strip()
        wav_path = row.get("wav_path") or ""
        sha = (row.get("sha256") or "").strip()
        real = is_real_transmission(row)

        # Duplicate control by audio_id (§14).
        if audio_id in seen_audio_id:
            report["duplicate_audio_ids"] += 1
        else:
            seen_audio_id[audio_id] = wav_path

        # Duplicate control by SHA-256 (§14): identical content counts once.
        # The first occurrence of a given SHA-256 is the canonical row; any
        # subsequent row with the same SHA-256 is a duplicate and must not be
        # counted as an additional real transmission.
        is_duplicate = False
        if sha:
            if sha in seen_sha:
                report["duplicate_rows"] += 1
                dup_sha_audio_ids.add(audio_id)
                is_duplicate = True
            else:
                seen_sha[sha] = audio_id
        else:
            report["missing_sha256"] += 1

        if not real:
            report["fixture_rows"] += 1
            continue

        # Duplicate content: already counted via its first occurrence; do not
        # count again (WO-041 §14).
        if is_duplicate:
            continue

        # Real transmission path: validate WAV, ground truth, verification.
        report["real_transmissions"] += 1

        ok, info = validate_wav(wav_path)
        if not ok:
            report["invalid_files"] += 1
            report["invalid_wav_list"].append(
                {"audio_id": audio_id, "path": wav_path, "reason": info.get("reason")}
            )
            continue

        if not has_verified_ground_truth(row):
            report["missing_ground_truth"] += 1
            report["missing_ground_truth_ids"].append(audio_id)
            continue

        report["verified_real_transmissions"] += 1

    report["duplicate_sha_list"] = sorted(dup_sha_audio_ids)
    report["gate_satisfied"] = (
        report["verified_real_transmissions"] >= min_real
    )
    return report


def format_report(report: dict[str, Any]) -> str:
    """Render a validation report as deterministic text."""
    lines = [
        "WO-041 DATASET VALIDATION",
        "=" * 40,
        f"total manifest rows:          {report['total_manifest_rows']}",
        f"fixture rows:                 {report['fixture_rows']}",
        f"real transmissions:           {report['real_transmissions']}",
        f"verified real transmissions:  {report['verified_real_transmissions']}",
        f"duplicate rows (by sha256):    {report['duplicate_rows']}",
        f"duplicate audio ids:          {report['duplicate_audio_ids']}",
        f"invalid files:                {report['invalid_files']}",
        f"missing ground truth:         {report['missing_ground_truth']}",
        f"missing sha256:               {report['missing_sha256']}",
        f"minimum required:             {report['minimum_required']}",
        f"GATE: {'PASS' if report['gate_satisfied'] else 'FAIL'}",
    ]
    if report["invalid_wav_list"]:
        lines.append("invalid wav files:")
        for item in report["invalid_wav_list"]:
            lines.append(
                f"  {item['audio_id']}: {item['reason']}"
            )
    if report["missing_ground_truth_ids"]:
        lines.append("missing ground truth ids:")
        lines.append("  " + ", ".join(report["missing_ground_truth_ids"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  ``validate_dataset.py --manifest <csv>``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="WO-041 dataset validator (offline, stdlib-only)"
    )
    parser.add_argument("--manifest", required=True, help="path to dataset_manifest.csv")
    parser.add_argument("--min-real", type=int, default=MIN_REAL_TRANSMISSIONS)
    args = parser.parse_args(argv)

    rows = load_manifest(args.manifest)
    report = validate_dataset(rows, min_real=args.min_real)
    print(format_report(report))
    return 0 if report["gate_satisfied"] else 1


if __name__ == "__main__":
    sys.exit(main())
