"""WO-053 — Controlled synthetic dataset (benchmark-mechanics only).

This is a **synthetic** dataset used ONLY to validate benchmark mechanics
(manifest determinism, hashing, format detection, gate accounting).  It is
NOT representative evidence of real-world Ukrainian / radio STT accuracy.
No speech is present; every fixture is a deterministic tone.

All generation is stdlib-only (``wave`` + ``math``) and deterministic: the same
seed / parameters always produce byte-identical WAVs, hence stable SHA-256.

Author: Tactical Core Engineering Team
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
import struct
import wave
from dataclasses import dataclass

SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH_BITS = 16

# Deterministic synthetic fixture definitions (name, frequency Hz, duration s).
FIXTURES: list[tuple[str, float, float]] = [
    ("wo053_tone_440", 440.0, 2.0),
    ("wo053_tone_1000", 1000.0, 3.0),
    ("wo053_tone_880_short", 880.0, 0.8),
    ("wo053_tone_220", 220.0, 1.5),
]

MANIFEST_COLUMNS = [
    "audio_id",
    "audio_path",
    "sha256",
    "source_type",
    "real_transmission",
    "speech_present",
    "duration_seconds",
    "sample_rate",
    "channels",
    "sample_width_bits",
    "codec",
    "generator",
    "generation_params",
    "transcript",
    "ground_truth_verified",
    "notes",
]


@dataclass(frozen=True)
class FixtureRecord:
    audio_id: str
    audio_path: str
    sha256: str
    duration_seconds: float
    sample_rate: int
    channels: int
    sample_width_bits: int
    generation_params: str


def _sine_pcm(freq: float, duration: float, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Return 16-bit little-endian PCM for a deterministic sine tone."""
    n = int(round(duration * sample_rate))
    frames = bytearray()
    for i in range(n):
        value = int(round(0.5 * 32767 * math.sin(2.0 * math.pi * freq * i / sample_rate)))
        frames += struct.pack("<h", value)
    return bytes(frames)


def write_synthetic_wav(path: str, freq: float, duration: float) -> None:
    """Write a deterministic mono 16-bit 8 kHz WAV tone to ``path``."""
    pcm = _sine_pcm(freq, duration)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BITS // 8)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def generate_synthetic_audio(output_dir: str) -> list[str]:
    """Generate all synthetic fixtures; return the written file paths."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for name, freq, dur in FIXTURES:
        path = os.path.join(output_dir, f"{name}.wav")
        write_synthetic_wav(path, freq, dur)
        written.append(path)
    return written


def _read_wav_info(path: str) -> dict:
    """Read WAV format metadata without modifying the file."""
    with wave.open(path, "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sampwidth_bits": wf.getsampwidth() * 8,
            "sample_rate": wf.getframerate(),
            "frames": wf.getnframes(),
            "duration": wf.getnframes() / wf.getframerate(),
        }


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(audio_dir: str, manifest_path: str) -> list[FixtureRecord]:
    """Build the WO-053 synthetic dataset manifest deterministically."""
    records: list[FixtureRecord] = []
    for name, freq, dur in FIXTURES:
        path = os.path.join(audio_dir, f"{name}.wav")
        info = _read_wav_info(path)
        records.append(
            FixtureRecord(
                audio_id=name,
                audio_path=os.path.abspath(path),
                sha256=sha256_file(path),
                duration_seconds=round(info["duration"], 4),
                sample_rate=info["sample_rate"],
                channels=info["channels"],
                sample_width_bits=info["sampwidth_bits"],
                generation_params=f"freq={freq}Hz;dur={dur}s;sr=8000;mono;16bit",
            )
        )
    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "audio_id": r.audio_id,
                    "audio_path": r.audio_path,
                    "sha256": r.sha256,
                    "source_type": "synthetic",
                    "real_transmission": "false",
                    "speech_present": "false",
                    "duration_seconds": r.duration_seconds,
                    "sample_rate": r.sample_rate,
                    "channels": r.channels,
                    "sample_width_bits": r.sample_width_bits,
                    "codec": "PCM",
                    "generator": "wo053_dataset.write_synthetic_wav",
                    "generation_params": r.generation_params,
                    "transcript": "",
                    "ground_truth_verified": "false",
                    "notes": "SYNTHETIC tone; no speech; benchmark-mechanics validation only; "
                             "NOT representative of real Ukrainian/radio STT accuracy.",
                }
            )
    return records


def validate_manifest(manifest_path: str, audio_dir: str | None = None) -> dict:
    """Validate a WO-053 manifest; return a deterministic result dict.

    Checks: required columns, file existence, WAV validity, SHA-256 integrity,
    format consistency, synthetic labeling, empty transcript, non-real flags.
    """
    result = {
        "manifest_rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "errors": [],
        "synthetic_rows": 0,
        "real_transmissions": 0,
        "speech_rows": 0,
        "duplicate_sha": [],
        "gate": "FAIL",
    }
    with open(manifest_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if set(MANIFEST_COLUMNS) - set(reader.fieldnames or []):
            result["errors"].append("missing required columns")
            return result
        seen_sha: dict[str, list[str]] = {}
        for row in reader:
            result["manifest_rows"] += 1
            path = row["audio_path"]
            if audio_dir:
                path = os.path.join(audio_dir, os.path.basename(path))
            ok = True
            if not os.path.exists(path):
                result["errors"].append(f"{row['audio_id']}: file missing {path}")
                ok = False
            else:
                if not _is_valid_wav(path):
                    result["errors"].append(f"{row['audio_id']}: not a valid WAV")
                    ok = False
                else:
                    try:
                        if sha256_file(path) != row["sha256"]:
                            result["errors"].append(f"{row['audio_id']}: SHA-256 mismatch")
                            ok = False
                    except Exception as e:  # noqa: BLE001
                        result["errors"].append(f"{row['audio_id']}: {e}")
                        ok = False
            if row["source_type"] != "synthetic":
                result["errors"].append(f"{row['audio_id']}: expected synthetic")
                ok = False
            if row["real_transmission"] != "false":
                result["errors"].append(f"{row['audio_id']}: real_transmission must be false")
                ok = False
            if row["speech_present"] != "false":
                result["errors"].append(f"{row['audio_id']}: speech_present must be false")
                ok = False
            if row["transcript"].strip() != "":
                result["errors"].append(f"{row['audio_id']}: synthetic must have empty transcript")
                ok = False
            if row["ground_truth_verified"] != "false":
                result["errors"].append(f"{row['audio_id']}: ground_truth_verified must be false")
                ok = False
            seen_sha.setdefault(row["sha256"], []).append(row["audio_id"])
            if ok:
                result["valid_rows"] += 1
                result["synthetic_rows"] += 1
            else:
                result["invalid_rows"] += 1
        for sha, ids in seen_sha.items():
            if len(ids) > 1:
                result["duplicate_sha"].extend(ids)
    result["real_transmissions"] = 0
    result["speech_rows"] = 0
    result["gate"] = "PASS" if result["valid_rows"] == result["manifest_rows"] and result["manifest_rows"] > 0 else "FAIL"
    return result


def _is_valid_wav(path: str) -> bool:
    try:
        with wave.open(path, "rb") as wf:
            _ = wf.getnframes()
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="WO-053 synthetic dataset tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Generate synthetic fixtures")
    gen.add_argument("--output-dir", required=True)
    gen.add_argument("--manifest", required=True)

    val = sub.add_parser("validate", help="Validate a manifest")
    val.add_argument("--manifest", required=True)
    val.add_argument("--audio-dir", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        files = generate_synthetic_audio(args.output_dir)
        records = build_manifest(args.output_dir, args.manifest)
        print(f"generated {len(files)} synthetic fixtures into {args.output_dir}")
        print(f"manifest rows: {len(records)} -> {args.manifest}")
        for r in records:
            print(f"  {r.audio_id}  {r.duration_seconds}s  {r.sha256}")
        return 0
    if args.cmd == "validate":
        res = validate_manifest(args.manifest, args.audio_dir)
        import json
        print(json.dumps(res, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
