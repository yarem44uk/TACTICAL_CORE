"""WO-067 — Benchmark dataset manifest loader + WAV integrity verification.

Benchmark-only, offline, stdlib-only.  Read-only on the evidence dataset: the
accepted PRE-04 WAVs are never modified, re-encoded or copied.

The manifest is the single deterministic source of the candidate set.  Loading
is strict: malformed rows, duplicate candidate ids, missing WAVs, changed WAVs
and unverifiable provenance are all hard, reported failures — never silently
skipped.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import wave
from dataclasses import dataclass, field


class DatasetError(Exception):
    """Raised when the benchmark dataset or manifest is unusable."""


# WO-067 §5: the accepted PRE-04 reconstruction format.
EXPECTED_SAMPLE_RATE_HZ = 8000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH_BITS = 16

# WO-067 §4 / §3: the authoritative PRE-04 provenance anchor.
EXPECTED_SOURCE_PCAP_SHA256 = (
    "0c9a0716d904d025079ecba00c585dfcac699351917dc804dffb0b4d4cd1eb20"
)

REQUIRED_COLUMNS = (
    "candidate_id",
    "stream_id",
    "ssrc",
    "audio_path",
    "wav_sha256",
    "source_pcap_sha256",
    "packet_start",
    "packet_end",
    "rtp_timestamp_start",
    "rtp_timestamp_end",
    "start_time_ms",
    "end_time_ms",
    "duration_ms",
    "sample_rate_hz",
    "channels",
    "sample_width_bits",
    "codec",
    "lossless",
    "human_review",
    "human_speech_confirmed",
    "ground_truth_transcript",
    "ground_truth_callsign",
    "ground_truth_status",
    "notes",
)


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file, streamed (never loads the whole file into memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_int(value: object, field_name: str, candidate_id: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise DatasetError(
            f"candidate {candidate_id!r}: field {field_name!r} is not an integer: "
            f"{value!r}"
        ) from exc


def _as_float(value: object, field_name: str, candidate_id: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise DatasetError(
            f"candidate {candidate_id!r}: field {field_name!r} is not a number: "
            f"{value!r}"
        ) from exc


@dataclass(frozen=True)
class Candidate:
    """One benchmark candidate: one PRE-04 human-reviewed audio fragment."""

    candidate_id: str
    stream_id: str
    ssrc: str
    audio_path: str
    wav_sha256: str
    source_pcap_sha256: str
    packet_start: int
    packet_end: int
    rtp_timestamp_start: int
    rtp_timestamp_end: int
    start_time_ms: float
    end_time_ms: float
    duration_ms: int
    sample_rate_hz: int
    channels: int
    sample_width_bits: int
    codec: str
    lossless: bool
    human_review: str
    human_speech_confirmed: bool
    ground_truth_transcript: str | None
    ground_truth_callsign: str | None
    ground_truth_status: str
    notes: str

    @property
    def has_ground_truth_transcript(self) -> bool:
        return bool(self.ground_truth_transcript and self.ground_truth_transcript.strip())

    @property
    def has_ground_truth_callsign(self) -> bool:
        return bool(self.ground_truth_callsign and self.ground_truth_callsign.strip())


@dataclass
class Dataset:
    """A loaded, deterministically ordered candidate set."""

    candidates: list[Candidate]
    manifest_path: str
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.candidates)

    def stream_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.candidates:
            counts[c.stream_id] = counts.get(c.stream_id, 0) + 1
        return dict(sorted(counts.items()))

    def with_ground_truth_transcript(self) -> list[Candidate]:
        return [c for c in self.candidates if c.has_ground_truth_transcript]

    def with_ground_truth_callsign(self) -> list[Candidate]:
        return [c for c in self.candidates if c.has_ground_truth_callsign]


def load_manifest(manifest_path: str) -> Dataset:
    """Load and validate the benchmark manifest.

    Deterministic ordering: candidates are sorted by ``candidate_id``.

    Raises:
        DatasetError: missing file, missing columns, duplicate ids, malformed
            values, or an inconsistent RTP/duration encoding.
    """
    if not os.path.isfile(manifest_path):
        raise DatasetError(f"manifest not found: {manifest_path}")

    warnings: list[str] = []
    with open(manifest_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing_cols:
            raise DatasetError(
                f"manifest {manifest_path} is missing required columns: {missing_cols}"
            )
        rows = list(reader)

    if not rows:
        raise DatasetError(f"manifest {manifest_path} contains no candidates")

    candidates: list[Candidate] = []
    seen: dict[str, int] = {}
    for lineno, row in enumerate(rows, start=2):
        cid = (row.get("candidate_id") or "").strip()
        if not cid:
            raise DatasetError(f"manifest line {lineno}: empty candidate_id")
        if cid in seen:
            raise DatasetError(
                f"duplicate candidate_id {cid!r} at manifest lines "
                f"{seen[cid]} and {lineno}"
            )
        seen[cid] = lineno

        candidate = Candidate(
            candidate_id=cid,
            stream_id=(row.get("stream_id") or "").strip(),
            ssrc=(row.get("ssrc") or "").strip(),
            audio_path=(row.get("audio_path") or "").strip(),
            wav_sha256=(row.get("wav_sha256") or "").strip().lower(),
            source_pcap_sha256=(row.get("source_pcap_sha256") or "").strip().lower(),
            packet_start=_as_int(row.get("packet_start"), "packet_start", cid),
            packet_end=_as_int(row.get("packet_end"), "packet_end", cid),
            rtp_timestamp_start=_as_int(
                row.get("rtp_timestamp_start"), "rtp_timestamp_start", cid
            ),
            rtp_timestamp_end=_as_int(
                row.get("rtp_timestamp_end"), "rtp_timestamp_end", cid
            ),
            start_time_ms=_as_float(row.get("start_time_ms"), "start_time_ms", cid),
            end_time_ms=_as_float(row.get("end_time_ms"), "end_time_ms", cid),
            duration_ms=_as_int(row.get("duration_ms"), "duration_ms", cid),
            sample_rate_hz=_as_int(row.get("sample_rate_hz"), "sample_rate_hz", cid),
            channels=_as_int(row.get("channels"), "channels", cid),
            sample_width_bits=_as_int(
                row.get("sample_width_bits"), "sample_width_bits", cid
            ),
            codec=(row.get("codec") or "").strip(),
            lossless=_as_bool(row.get("lossless", "")),
            human_review=(row.get("human_review") or "").strip(),
            human_speech_confirmed=_as_bool(row.get("human_speech_confirmed", "")),
            ground_truth_transcript=(row.get("ground_truth_transcript") or "").strip()
            or None,
            ground_truth_callsign=(row.get("ground_truth_callsign") or "").strip()
            or None,
            ground_truth_status=(row.get("ground_truth_status") or "").strip(),
            notes=(row.get("notes") or "").strip(),
        )

        if not candidate.wav_sha256:
            raise DatasetError(f"candidate {cid}: empty wav_sha256")
        if candidate.packet_end < candidate.packet_start:
            raise DatasetError(
                f"candidate {cid}: packet_end < packet_start "
                f"({candidate.packet_end} < {candidate.packet_start})"
            )
        if candidate.rtp_timestamp_end < candidate.rtp_timestamp_start:
            raise DatasetError(
                f"candidate {cid}: rtp_timestamp_end < rtp_timestamp_start"
            )
        if candidate.duration_ms <= 0:
            raise DatasetError(f"candidate {cid}: non-positive duration_ms")
        if candidate.source_pcap_sha256 != EXPECTED_SOURCE_PCAP_SHA256:
            raise DatasetError(
                f"candidate {cid}: source_pcap_sha256 does not match the "
                f"authoritative PRE-04 PCAP digest: {candidate.source_pcap_sha256!r}"
            )
        if candidate.ground_truth_status == "NOT_PROVIDED" and (
            candidate.has_ground_truth_transcript
            or candidate.has_ground_truth_callsign
        ):
            raise DatasetError(
                f"candidate {cid}: ground_truth_status is NOT_PROVIDED but ground "
                f"truth text is present — inconsistent record"
            )

        candidates.append(candidate)

    candidates.sort(key=lambda c: c.candidate_id)
    return Dataset(candidates=candidates, manifest_path=manifest_path, warnings=warnings)


def verify_wav_integrity(candidate: Candidate) -> dict:
    """Verify one candidate WAV against the manifest and the PRE-04 format.

    Read-only.  Returns a report dict; never raises for a data problem — the
    caller decides policy.  ``ok`` is True only when path, digest, container
    format and duration all agree with the manifest.
    """
    report: dict = {
        "candidate_id": candidate.candidate_id,
        "path": candidate.audio_path,
        "exists": False,
        "sha256": None,
        "sha256_expected": candidate.wav_sha256,
        "sha256_match": False,
        "format_ok": False,
        "duration_ok": False,
        "problems": [],
    }

    if not os.path.isfile(candidate.audio_path):
        report["problems"].append(f"WAV missing on disk: {candidate.audio_path}")
        report["ok"] = False
        return report

    report["exists"] = True
    actual = sha256_file(candidate.audio_path)
    report["sha256"] = actual
    report["sha256_match"] = actual == candidate.wav_sha256
    if not report["sha256_match"]:
        report["problems"].append(
            "WAV SHA-256 does not match the manifest (candidate altered?)"
        )

    try:
        with wave.open(candidate.audio_path, "rb") as wav:
            channels = wav.getnchannels()
            width_bytes = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            comptype = wav.getcomptype()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        report["problems"].append(f"cannot open as RIFF/WAVE: {exc}")
        report["ok"] = False
        return report

    width_bits = width_bytes * 8
    fmt_ok = (
        channels == EXPECTED_CHANNELS
        and rate == EXPECTED_SAMPLE_RATE_HZ
        and width_bits == EXPECTED_SAMPLE_WIDTH_BITS
        and comptype == "NONE"
    )
    report["format_ok"] = fmt_ok
    report["format"] = {
        "channels": channels,
        "sample_rate_hz": rate,
        "sample_width_bits": width_bits,
        "compression": comptype,
        "frames": frames,
    }
    if not fmt_ok:
        report["problems"].append(
            "WAV format is not the accepted lossless PCM 16-bit mono 8000 Hz"
        )

    actual_ms = round(frames / float(rate) * 1000) if rate else None
    report["duration_ms_actual"] = actual_ms
    report["duration_ms_expected"] = candidate.duration_ms
    # Tolerate 1 ms of integer rounding in the PRE-04 manifest.
    report["duration_ok"] = (
        actual_ms is not None and abs(actual_ms - candidate.duration_ms) <= 1
    )
    if not report["duration_ok"]:
        report["problems"].append(
            f"duration mismatch: disk {actual_ms} ms vs manifest "
            f"{candidate.duration_ms} ms"
        )

    report["ok"] = (
        report["sha256_match"] and report["format_ok"] and report["duration_ok"]
    )
    return report


def verify_dataset_integrity(dataset: Dataset) -> dict:
    """Verify every candidate WAV; return a report + included/excluded lists."""
    per_candidate = [verify_wav_integrity(c) for c in dataset.candidates]
    failures = [r for r in per_candidate if not r["ok"]]
    included = [c.candidate_id for c, r in zip(dataset.candidates, per_candidate) if r["ok"]]
    excluded = [r["candidate_id"] for r in failures]
    return {
        "checked": len(per_candidate),
        "ok": len(per_candidate) - len(failures),
        "failed": len(failures),
        "included_ids": included,
        "excluded_ids": excluded,
        "exclusions": [
            {"candidate_id": r["candidate_id"], "problems": r["problems"]}
            for r in failures
        ],
        "per_candidate": per_candidate,
    }


def load_ground_truth(path: str) -> dict:
    """Load a human ground-truth sidecar (JSON) keyed by candidate id.

    Shape::

        {"version": "...", "source": "...", "entries": [
            {"candidate_id": "msg_0001", "transcript": "...", "callsign": "..."},
        ]}

    Ground truth MUST come from explicit human review.  An entry with an empty
    transcript is treated as ``transcript = None`` (not yet entered), never as
    an empty-string reference.

    Raises:
        DatasetError: missing file, invalid JSON, wrong shape, duplicate ids.
    """
    if not os.path.isfile(path):
        raise DatasetError(f"ground-truth file not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"ground-truth file is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "entries" not in payload:
        raise DatasetError("ground-truth file must be an object with an 'entries' list")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise DatasetError("ground-truth 'entries' must be a list")

    out: dict[str, dict] = {}
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise DatasetError(f"ground-truth entry {idx} is not an object")
        cid = str(entry.get("candidate_id", "")).strip()
        if not cid:
            raise DatasetError(f"ground-truth entry {idx} has no candidate_id")
        if cid in out:
            raise DatasetError(f"duplicate ground-truth candidate_id: {cid}")
        transcript = entry.get("transcript")
        callsign = entry.get("callsign")
        out[cid] = {
            "candidate_id": cid,
            "transcript": (str(transcript).strip() or None) if transcript is not None else None,
            "callsign": (str(callsign).strip() or None) if callsign is not None else None,
            "reviewer": entry.get("reviewer"),
            "review_time": entry.get("review_time"),
        }
    return {
        "version": payload.get("version"),
        "source": payload.get("source"),
        "entries": out,
    }


def apply_ground_truth(dataset: Dataset, ground_truth: dict) -> Dataset:
    """Return a dataset whose candidates carry the supplied human ground truth.

    Unknown candidate ids in the ground truth are reported as warnings, not
    silently dropped.  Candidates without an entry keep ``NOT_PROVIDED``.
    """
    entries = ground_truth.get("entries", {})
    warnings = list(dataset.warnings)
    known = {c.candidate_id for c in dataset.candidates}
    unknown = sorted(set(entries) - known)
    if unknown:
        warnings.append(
            f"ground truth references unknown candidate ids: {unknown}"
        )

    updated: list[Candidate] = []
    for c in dataset.candidates:
        entry = entries.get(c.candidate_id)
        if entry is None:
            updated.append(c)
            continue
        transcript = entry.get("transcript")
        callsign = entry.get("callsign")
        has_any = bool(transcript or callsign)
        status = "PROVIDED" if has_any else "NOT_PROVIDED"
        updated.append(
            Candidate(
                **{
                    **c.__dict__,
                    "ground_truth_transcript": transcript,
                    "ground_truth_callsign": callsign,
                    "ground_truth_status": status,
                }
            )
        )
    return Dataset(
        candidates=updated,
        manifest_path=dataset.manifest_path,
        warnings=warnings,
    )