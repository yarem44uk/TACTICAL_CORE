#!/usr/bin/env python3
"""WO-042 — build a dataset manifest from real WAV masters (offline, stdlib-only).

This is dataset *tooling* only (WO-042 §3.A, §5).  It is deliberately:

    * isolated     — self-contained; does not touch the production STT seam,
                     the audio pipeline, or any STT engine;
    * offline      — uses only the Python standard library; never runs STT
                     inference, never downloads a model, never calls a network
                     API;
    * read-only    — opens WAV masters in ``rb`` and never writes to them;
    * engine-neutral — it does not favour faster_whisper or vosk and does not
                     select any STT engine.

For each real WAV master it computes (deterministically):

    * ``audio_id``           — stable ``RADIO-NNNN`` derived from sorted path order;
    * ``sha256``             — SHA-256 of the exact file bytes (§5, §6);
    * ``duration_seconds``   — from the WAV header (§5);
    * ``sample_rate``        — from the WAV header;
    * ``channels``           — from the WAV header;
    * ``sample_width_bits``  — from the WAV header (bits);
    * ``codec``              — ``PCM`` for a readable WAV;
    * duplicate detection    — a row whose SHA-256 equals an earlier row is
                               annotated ``DUPLICATE_SHA of <audio_id>``.

It does NOT decide real vs fixture: every emitted row defaults to
``real_transmission=false`` and ``provenance=UNKNOWN``.  After an operator
manually reviews the audio (listens for speech), fills in the manual ground-truth
transcript and the audible callsigns, and marks the row real + verified, the
manifest is re-validated with ``wo042_validate_dataset.py`` (§8, §9, §10).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import wave
from typing import Any

# Same stable column order as wo042_validate_dataset.py (§7).
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


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wav_meta(path: str) -> tuple[bool, dict[str, Any]]:
    """Read WAV header metadata read-only.  Returns (ok, info)."""
    info: dict[str, Any] = {}
    try:
        with wave.open(path, "rb") as wf:
            info["channels"] = wf.getnchannels()
            info["sample_width_bits"] = wf.getsampwidth() * 8
            info["sample_rate"] = wf.getframerate()
            info["duration_seconds"] = round(
                wf.getnframes() / wf.getframerate() if wf.getframerate() else 0.0,
                4,
            )
        if info["sample_rate"] <= 0 or info["channels"] <= 0 or info["duration_seconds"] <= 0:
            return False, info
        return True, info
    except Exception as exc:  # noqa: BLE001
        info["reason"] = f"{type(exc).__name__}: {exc}"
        return False, info


def build_rows(paths: list[str]) -> list[dict[str, Any]]:
    """Build manifest rows for the given WAV masters (sorted, deterministic)."""
    rows: list[dict[str, Any]] = []
    seen_sha: dict[str, str] = {}
    for idx, path in enumerate(sorted(paths), start=1):
        audio_id = f"RADIO-{idx:04d}"
        ok, info = _wav_meta(path)
        sha = _sha256(path) if os.path.exists(path) else ""

        dup_note = ""
        if sha and sha in seen_sha:
            dup_note = f"DUPLICATE_SHA of {seen_sha[sha]}"
        else:
            seen_sha[sha] = audio_id

        row: dict[str, Any] = {
            "audio_id": audio_id,
            "audio_path": path,
            "sha256": sha,
            "source_type": "UNKNOWN",
            "real_transmission": "false",
            "capture_timestamp": "UNKNOWN",
            "duration_seconds": str(info["duration_seconds"]) if ok else "UNKNOWN",
            "sample_rate": str(info["sample_rate"]) if ok else "UNKNOWN",
            "channels": str(info["channels"]) if ok else "UNKNOWN",
            "sample_width_bits": str(info["sample_width_bits"]) if ok else "UNKNOWN",
            "codec": "PCM" if ok else "UNKNOWN",
            "speaker_or_source": "UNKNOWN",
            "transcript": "",
            "callsigns_present": "[]",
            "ground_truth_verified": "false",
            "independent_verification": "false",
            "verification_method": "UNKNOWN",
            "provenance": "UNKNOWN",
            "notes": dup_note,
        }
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-042 manifest builder (offline, stdlib-only)"
    )
    parser.add_argument("paths", nargs="*", help="WAV master paths")
    parser.add_argument(
        "--scan-dir", default=None, help="directory to scan for *.wav masters"
    )
    parser.add_argument("--out", required=True, help="output manifest CSV path")
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if args.scan_dir:
        for root, _dirs, files in os.walk(args.scan_dir):
            for fn in sorted(files):
                if fn.lower().endswith(".wav"):
                    paths.append(os.path.join(root, fn))
    if not paths:
        print("no WAV masters supplied", file=sys.stderr)
        return 1

    rows = build_rows(paths)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
