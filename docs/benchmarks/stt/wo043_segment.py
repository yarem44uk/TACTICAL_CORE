#!/usr/bin/env python3
"""WO-043 — Deterministic real-radio transmission segmentation tool.

Isolated, offline, stdlib-only (mirrors the WO-042 tooling design):

    * isolated   — self-contained; does not touch the production STT seam, the
                   audio pipeline, or any STT engine;
    * offline    — uses only the Python standard library; never runs STT
                   inference, never downloads a model, never calls a network API;
    * read-only  — opens the source WAV in ``rb`` and never writes to it;
    * engine-neutral — does not select, invoke, or favour any STT engine.

Purpose (WO-043 §1)
-------------------
Given a real radio recording, segment it into individual *candidate*
transmissions, producing:

    REAL RADIO RECORDING
        -> candidate transmission detection
        -> exact start / end
        -> individual WAV masters
        -> stable RADIO-NNNN IDs
        -> SHA-256
        -> segmentation manifest
        -> manual verification by operator

Energy detection is used ONLY to propose candidate boundaries. It does NOT
classify a burst as speech or as a real transmission (WO-043 §4). Every emitted
candidate carries ``candidate_status=CANDIDATE`` until a human operator
verifies it. This tool never labels a candidate ``real_transmission``.

Design rules honoured
---------------------
* deterministic  — same source + same parameters => same segments, same IDs,
                   same hashes (WO-043 §9, §20);
* no overlap     — ``end[i] <= start[i+1]`` is guaranteed (WO-043 §7);
* activity vs segment boundaries kept separate (WO-043 §8, §17);
* parameters are configurable CLI options / constants, documented as proposed
  segmentation defaults (WO-043 §5, §6);
* derived masters are WAV and preserve the source native format (WO-043 §10);
* the original source is never modified (WO-043 §2).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import array
import csv
import hashlib
import math
import os
import sys
import wave
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Proposed segmentation defaults (WO-043 §6).
#
# These are *initial engineering defaults*, NOT production policy. They are
# documented as "proposed segmentation defaults" and are overridable via CLI.
# ---------------------------------------------------------------------------
DEFAULT_FRAME_MS = 20.0        # analysis frame length (ms)
DEFAULT_HOP_MS = 10.0          # analysis hop / step (ms)
DEFAULT_PRE_ROLL_MS = 250.0    # silence/pad added before the first active frame
DEFAULT_POST_ROLL_MS = 400.0   # silence/pad added after the last active frame
DEFAULT_MIN_DURATION_MS = 150.0
DEFAULT_MAX_DURATION_MS = 60000.0
DEFAULT_MERGE_GAP_MS = 250.0
# Energy threshold on the RMS of the mono signal normalised to [-1, 1].
# This is a proposed default; it is deliberately conservative and overridable.
DEFAULT_ENERGY_THRESHOLD = 0.01

# Stable manifest schema (WO-043 §12). Field order is fixed for reproducibility.
MANIFEST_FIELDS = [
    "audio_id",
    "source_file",
    "source_sha256",
    "segment_start_seconds",
    "segment_end_seconds",
    "activity_start_seconds",
    "activity_end_seconds",
    "duration_seconds",
    "derived_sha256",
    "sample_rate",
    "channels",
    "sample_width_bits",
    "candidate_status",
    "real_transmission",
    "speech_present",
    "transcript",
    "callsigns_present",
    "ground_truth_verified",
    "independent_verification",
    "notes",
]


@dataclass
class SegmentParams:
    """Configurable segmentation parameters (proposed defaults)."""

    frame_ms: float = DEFAULT_FRAME_MS
    hop_ms: float = DEFAULT_HOP_MS
    energy_threshold: float = DEFAULT_ENERGY_THRESHOLD
    pre_roll_ms: float = DEFAULT_PRE_ROLL_MS
    post_roll_ms: float = DEFAULT_POST_ROLL_MS
    min_duration_ms: float = DEFAULT_MIN_DURATION_MS
    max_duration_ms: float = DEFAULT_MAX_DURATION_MS
    merge_gap_ms: float = DEFAULT_MERGE_GAP_MS


@dataclass
class Candidate:
    """A candidate transmission with separate activity and segment bounds."""

    index: int
    activity_start: float  # seconds
    activity_end: float    # seconds
    segment_start: float   # seconds (includes pre-roll)
    segment_end: float     # seconds (includes post-roll)

    @property
    def duration(self) -> float:
        return self.segment_end - self.segment_start


# ---------------------------------------------------------------------------
# WAV reading (stdlib only).
# ---------------------------------------------------------------------------

def _norm_factor(sampwidth: int) -> float:
    """Return the divisor that maps integer samples to [-1, 1]."""
    return float(1 << (8 * sampwidth - 1))


def read_wav(path: str) -> Tuple[float, int, int, List[float]]:
    """Read a PCM WAV and return (sample_rate, channels, sampwidth, mono_samples).

    ``mono_samples`` is the signal down-mixed to mono and normalised to [-1, 1].
    The source file is opened read-only and never modified.
    """
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sampwidth not in (1, 2, 4):
        raise ValueError(f"unsupported sample width: {sampwidth} bytes")

    if sampwidth == 1:
        # 8-bit PCM is unsigned in WAV.
        samples = array.array("B", raw)
        ints = [int(s) - 128 for s in samples]
    elif sampwidth == 2:
        a = array.array("h", raw)
        ints = list(a)
    else:  # sampwidth == 4
        a = array.array("i", raw)
        ints = list(a)

    if channels == 1:
        mono = ints
    else:
        # Down-mix: average across channels per frame.
        frames = len(ints) // channels
        mono = []
        for i in range(frames):
            acc = 0
            for c in range(channels):
                acc += ints[i * channels + c]
            mono.append(acc / channels)

    norm = _norm_factor(sampwidth)
    return float(rate), channels, sampwidth, [s / norm for s in mono]


# ---------------------------------------------------------------------------
# RMS frame analysis.
# ---------------------------------------------------------------------------

def rms_frame_energy(
    mono: List[float], rate: float, frame_ms: float, hop_ms: float
) -> List[Tuple[float, float]]:
    """Compute per-hop RMS energy.

    Returns a list of ``(time_start_seconds, rms)`` for each analysis hop. The
    hop start is aligned to a fixed grid so the result is deterministic.
    """
    frame_len = max(1, int(round(rate * frame_ms / 1000.0)))
    hop_len = max(1, int(round(rate * hop_ms / 1000.0)))
    total = len(mono)
    result: List[Tuple[float, float]] = []
    start = 0
    while start < total:
        end = min(start + frame_len, total)
        window = mono[start:end]
        if window:
            sq = sum(s * s for s in window)
            rms = (sq / len(window)) ** 0.5
        else:
            rms = 0.0
        result.append((start / rate, rms))
        start += hop_len
    return result


# ---------------------------------------------------------------------------
# Activity / segmentation.
# ---------------------------------------------------------------------------

def detect_active(rms_frames: List[Tuple[float, float]], threshold: float) -> List[bool]:
    return [rms >= threshold for (_t, rms) in rms_frames]


def _active_runs(active: List[bool], hop_ms: float) -> List[Tuple[float, float]]:
    """Collapse the active hop mask into contiguous runs of active time.

    Returns (run_start_seconds, run_end_seconds) where end is the hop boundary
    after the last active hop of the run.
    """
    hop_len = hop_ms / 1000.0
    runs: List[Tuple[float, float]] = []
    i = 0
    n = len(active)
    while i < n:
        if not active[i]:
            i += 1
            continue
        # start time of this hop (reconstructed from the first active hop).
        # We reconstruct by counting hops; deterministic and offset-free.
        run_start = i * hop_len
        j = i
        while j < n and active[j]:
            j += 1
        run_end = j * hop_len
        runs.append((run_start, run_end))
        i = j
    return runs


def build_candidates(
    mono: List[float], rate: float, params: SegmentParams
) -> List[Candidate]:
    """Segment the mono signal into candidate transmissions.

    Pipeline (WO-043 §5): frame analysis -> energy/RMS -> activity threshold ->
    attack -> hangover/post-roll -> merge nearby fragments -> minimum duration ->
    (cap) maximum duration -> overlap prevention.
    """
    rms_frames = rms_frame_energy(mono, rate, params.frame_ms, params.hop_ms)
    active = detect_active(rms_frames, params.energy_threshold)
    runs = _active_runs(active, params.hop_ms)

    if not runs:
        return []

    # Convert activity runs to segments with pre/post roll.
    candidates: List[Candidate] = []
    for idx, (act_start, act_end) in enumerate(runs):
        seg_start = act_start - params.pre_roll_ms / 1000.0
        seg_end = act_end + params.post_roll_ms / 1000.0
        if seg_start < 0.0:
            seg_start = 0.0
        candidates.append(
            Candidate(idx, act_start, act_end, seg_start, seg_end)
        )

    # Merge nearby fragments (WO-043 §6): if the gap between two consecutive
    # segments is <= merge_gap, they are one contiguous transmission.
    merged: List[Candidate] = []
    for c in candidates:
        if merged and c.segment_start - merged[-1].segment_end <= params.merge_gap_ms / 1000.0:
            prev = merged[-1]
            merged[-1] = Candidate(
                prev.index,
                prev.activity_start,
                c.activity_end,
                prev.segment_start,
                c.segment_end,
            )
        else:
            merged.append(c)

    # Minimum duration (WO-043 §6): drop candidates whose *activity* is shorter
    # than min_duration. The pre/post roll is padding, so a brief blip padded
    # with 650 ms of roll must not survive a 150 ms minimum.
    filtered = [
        c for c in merged
        if (c.activity_end - c.activity_start) >= params.min_duration_ms / 1000.0
    ]

    # Maximum duration (WO-043 §6): cap. If a segment exceeds the cap, split it
    # into consecutive non-overlapping chunks of at most max_duration. A chunk
    # that contains no activity (pure pre/post-roll padding) is dropped.
    capped: List[Candidate] = []
    for c in filtered:
        dur = c.segment_end - c.segment_start
        max_dur = params.max_duration_ms / 1000.0
        if dur <= max_dur:
            capped.append(c)
            continue
        n_chunks = int(math.ceil(dur / max_dur))
        for k in range(n_chunks):
            seg_start = c.segment_start + k * max_dur
            seg_end = min(seg_start + max_dur, c.segment_end)
            # Activity is the intersection of the chunk range with the original
            # activity range; empty intersection means pure padding -> drop.
            act_start = max(c.activity_start, seg_start)
            act_end = min(c.activity_end, seg_end)
            if act_end <= act_start:
                continue
            capped.append(
                Candidate(c.index * 1000 + k, act_start, act_end, seg_start, seg_end)
            )

    # Overlap prevention (WO-043 §7): guarantee end[i] <= start[i+1].
    non_overlap: List[Candidate] = []
    for c in capped:
        if non_overlap and c.segment_start < non_overlap[-1].segment_end:
            c = Candidate(
                c.index,
                c.activity_start,
                c.activity_end,
                non_overlap[-1].segment_end,
                c.segment_end,
            )
        non_overlap.append(c)

    # Deterministic ordering by ascending segment_start (WO-043 §9).
    non_overlap.sort(key=lambda c: (c.segment_start, c.activity_start, c.index))

    # Reassign contiguous deterministic IDs in ascending segment_start order
    # (WO-043 §9): the final numbering is 1..N with no gaps, stable across runs.
    for i, c in enumerate(non_overlap):
        c.index = i

    return non_overlap


# ---------------------------------------------------------------------------
# Derived WAV writing + hashing.
# ---------------------------------------------------------------------------

def write_wav_derived(
    source_path: str,
    out_path: str,
    start_sec: float,
    end_sec: float,
) -> None:
    """Write a derived WAV slice, preserving the source native format.

    The slice is [start_sec, end_sec] in seconds. The source is opened
    read-only. The derived file keeps the same sample rate, channel count, and
    sample width as the source (WO-043 §10). No resampling or normalisation is
    performed in-place; the derived file is a direct byte slice.
    """
    with wave.open(source_path, "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        nframes = w.getnframes()
        start_frame = int(round(start_sec * rate))
        end_frame = int(round(end_sec * rate))
        if end_frame > nframes:
            end_frame = nframes
        if start_frame < 0:
            start_frame = 0
        if end_frame <= start_frame:
            raise ValueError(f"invalid slice: {start_sec}s -> {end_sec}s")
        w.setpos(start_frame)
        raw = w.readframes(end_frame - start_frame)

    with wave.open(out_path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(raw)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Manifest.
# ---------------------------------------------------------------------------

def write_manifest(path: str, rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def _fmt(s: float) -> str:
    return f"{s:.3f}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-043 deterministic radio transmission segmentation."
    )
    parser.add_argument("--input", required=True, help="source WAV path (read-only)")
    parser.add_argument("--output-dir", default=None,
                        help="directory for derived WAV masters (default: alongside --manifest)")
    parser.add_argument("--manifest", default=None,
                        help="path for the segmentation manifest CSV")
    parser.add_argument("--list", action="store_true",
                        help="print a candidate summary table without writing files")
    parser.add_argument("--no-write", action="store_true",
                        help="do not write derived WAV masters (analysis only)")
    parser.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)
    parser.add_argument("--hop-ms", type=float, default=DEFAULT_HOP_MS)
    parser.add_argument("--energy-threshold", type=float, default=DEFAULT_ENERGY_THRESHOLD)
    parser.add_argument("--pre-roll-ms", type=float, default=DEFAULT_PRE_ROLL_MS)
    parser.add_argument("--post-roll-ms", type=float, default=DEFAULT_POST_ROLL_MS)
    parser.add_argument("--min-duration-ms", type=float, default=DEFAULT_MIN_DURATION_MS)
    parser.add_argument("--max-duration-ms", type=float, default=DEFAULT_MAX_DURATION_MS)
    parser.add_argument("--merge-gap-ms", type=float, default=DEFAULT_MERGE_GAP_MS)
    args = parser.parse_args(argv)

    params = SegmentParams(
        frame_ms=args.frame_ms,
        hop_ms=args.hop_ms,
        energy_threshold=args.energy_threshold,
        pre_roll_ms=args.pre_roll_ms,
        post_roll_ms=args.post_roll_ms,
        min_duration_ms=args.min_duration_ms,
        max_duration_ms=args.max_duration_ms,
        merge_gap_ms=args.merge_gap_ms,
    )

    rate, channels, sampwidth, mono = read_wav(args.input)
    source_sha = sha256_file(args.input)

    candidates = build_candidates(mono, rate, params)

    if args.list or args.manifest is None:
        print(f"source: {args.input}")
        print(f"source_sha256: {source_sha}")
        print(f"source: rate={rate:.0f} Hz channels={channels} "
              f"sample_width={sampwidth * 8} bits")
        print(f"candidates: {len(candidates)}")
        for c in candidates:
            print(f"RADIO-{c.index + 1:04d}  "
                  f"{_fmt(c.segment_start)}s -> {_fmt(c.segment_end)}s  "
                  f"{_fmt(c.duration)}s  "
                  f"(activity {_fmt(c.activity_start)}s -> {_fmt(c.activity_end)}s)")

    rows: List[dict] = []
    if not args.no_write and args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        for c in candidates:
            audio_id = f"RADIO-{c.index + 1:04d}"
            derived_path = os.path.join(args.output_dir, f"{audio_id}.wav")
            write_wav_derived(args.input, derived_path, c.segment_start, c.segment_end)
            derived_sha = sha256_file(derived_path)
            rows.append({
                "audio_id": audio_id,
                "source_file": args.input,
                "source_sha256": source_sha,
                "segment_start_seconds": _fmt(c.segment_start),
                "segment_end_seconds": _fmt(c.segment_end),
                "activity_start_seconds": _fmt(c.activity_start),
                "activity_end_seconds": _fmt(c.activity_end),
                "duration_seconds": _fmt(c.duration),
                "derived_sha256": derived_sha,
                "sample_rate": int(rate),
                "channels": channels,
                "sample_width_bits": sampwidth * 8,
                "candidate_status": "CANDIDATE",
                "real_transmission": "false",
                "speech_present": "UNKNOWN",
                "transcript": "",
                "callsigns_present": "[]",
                "ground_truth_verified": "false",
                "independent_verification": "false",
                "notes": (
                    "candidate pending manual verification; energy-based "
                    "boundary only, not classified as real transmission"
                ),
            })

    if args.manifest and not args.no_write:
        write_manifest(args.manifest, rows)
        print(f"manifest: {args.manifest} ({len(rows)} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
