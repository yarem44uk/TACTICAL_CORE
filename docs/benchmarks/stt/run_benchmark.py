#!/usr/bin/env python3
"""WO-040 — Real acoustic STT benchmark harness (isolated, offline, stdlib-only).

This is benchmark *tooling* only (WO-040 §19).  It is deliberately:

    * isolated        — self-contained, does not touch the production STT seam;
    * deterministic   — pure functions, reproducible output;
    * offline         — uses only the Python standard library, never downloads
                        a model or runtime package, never calls a network API;
    * read-only       — opens WAV masters in ``rb`` and never writes to them.

What it does (WO-040 §3/§8/§20):

    1. probe    — detect whether a candidate engine runtime/model is present
                  locally (faster_whisper / vosk).  If absent, that is the
                  documented technical inability to execute the benchmark
                  offline (WO-040 §7/§8).
    2. manifest — scan the configured WAV master roots, build
                  ``dataset_manifest.csv`` with real metadata (sha256, format,
                  duration) and provenance, and detect the presence of
                  ground-truth transcripts.
    3. metrics  — compute WER / CER / callsign accuracy from a reference
                  transcript and a hypothesis transcript.  Provided so the
                  measurement is defined reproducibly when real engine output
                  exists.  (Nothing is measured here because no engine output
                  exists.)

The harness NEVER registers an engine, NEVER alters ``SUPPORTED_ENGINES``,
NEVER replaces the deterministic test transcriber, and NEVER modifies
production configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import wave
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Candidate engines that must be benchmarked (WO-040 §7).
# ---------------------------------------------------------------------------
CANDIDATES = ["faster_whisper", "vosk"]

# Default WAV master roots discovered during WO-040 discovery (§3).  These are
# the locations where the actual WO-039 pipeline wrote finalized radio WAV
# masters on this host.
DEFAULT_WAV_ROOTS = [
    "/tmp/tmp830mejt0/2026/09/02/radio",
    "/tmp/hv_nw8kok3b/2026/09/02/radio",
    "/tmp/aud_a03080ty/2026/09/02/radio",
]

# Provenance annotation for these recordings (established in WO-040 discovery):
# they are WO-039-B/C unit-test fixtures — constant-amplitude PCM values fed
# through the real RTP -> VAD -> recorder -> WAV pipeline to exercise the
# VAD / segmentation / recording logic.  They are NOT real radio speech.
TEST_FIXTURE_PROVENANCE = (
    "WO-039-B/C unit-test fixture: constant-amplitude PCM value fed through the "
    "real RTP->VAD->recorder->WAV pipeline; contains no speech, no words, no "
    "callsigns (VAD/segmentation test tone, not a real radio transmission)."
)


# ---------------------------------------------------------------------------
# Candidate availability probe (WO-040 §8).
# ---------------------------------------------------------------------------
def probe_candidate(engine: str) -> dict[str, Any]:
    """Return availability of one candidate engine and its local model.

    This never imports a missing module as a fatal error; it reports the
    absence so the benchmark can honestly document the technical inability to
    run offline (WO-040 §7/§8).  No download, no network.
    """
    result: dict[str, Any] = {
        "engine": engine,
        "runtime_installed": False,
        "runtime_version": None,
        "import_error": None,
        "model_present": False,
        "model_path": None,
    }
    try:
        if engine == "faster_whisper":
            import faster_whisper  # noqa: F401
            result["runtime_installed"] = True
            result["runtime_version"] = getattr(faster_whisper, "__version__", None)
        elif engine == "vosk":
            import vosk  # noqa: F401
            result["runtime_installed"] = True
            result["runtime_version"] = getattr(vosk, "__version__", None)
    except Exception as exc:  # noqa: BLE001 - report absence, not crash
        result["import_error"] = f"{type(exc).__name__}: {exc}"

    # Model presence: search a small set of well-known local model roots only.
    # We deliberately do not scan the whole filesystem in the harness; the
    # discovery step already established that no model exists on this host.
    for root in ["/opt/models", "/models", "/opt/data/models", "/opt/data/tactical_core_github/models"]:
        if os.path.isdir(root):
            for entry in os.listdir(root):
                if engine.replace("_", "-") in entry.lower() or engine in entry.lower():
                    result["model_present"] = True
                    result["model_path"] = os.path.join(root, entry)
    return result


def probe_all() -> list[dict[str, Any]]:
    return [probe_candidate(e) for e in CANDIDATES]


# ---------------------------------------------------------------------------
# WAV master scanning + dataset manifest (WO-040 §4/§5/§6/§11).
# ---------------------------------------------------------------------------
def read_wav_info(path: str) -> dict[str, Any]:
    """Read WAV metadata read-only, computing sha256 over the exact bytes."""
    with open(path, "rb") as fh:
        data = fh.read()
    digest = hashlib.sha256(data).hexdigest()
    with wave.open(os.path.join(os.path.dirname(path), os.path.basename(path)), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        nframes = wf.getnframes()
        duration = nframes / sample_rate if sample_rate else 0.0
    return {
        "sha256": digest,
        "channels": channels,
        "sampwidth": sampwidth,
        "sample_rate": sample_rate,
        "nframes": nframes,
        "duration": round(duration, 4),
        "data_bytes": len(data),
    }


def build_manifest(roots: list[str]) -> list[dict[str, Any]]:
    """Build the dataset manifest from the given WAV master roots."""
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if not name.lower().endswith(".wav"):
                continue
            path = os.path.join(root, name)
            try:
                info = read_wav_info(path)
            except Exception as exc:  # noqa: BLE001 - record unreadable file
                rows.append({
                    "audio_id": os.path.splitext(name)[0],
                    "wav_path": path,
                    "source": "radio",
                    "duration_s": "",
                    "channels": "",
                    "sampwidth": "",
                    "sample_rate": "",
                    "sha256": "",
                    "ground_truth": "",
                    "callsigns_present": "",
                    "provenance": f"UNREADABLE: {exc}",
                    "usable": "false",
                })
                continue
            # WO-039-C3 requires mono 16-bit 8kHz for the WAV master.
            usable = (info["channels"] == 1 and info["sampwidth"] == 2 and info["sample_rate"] == 8000)
            rows.append({
                "audio_id": os.path.splitext(name)[0],
                "wav_path": path,
                "source": "radio",
                "duration_s": info["duration"],
                "channels": info["channels"],
                "sampwidth": info["sampwidth"],
                "sample_rate": info["sample_rate"],
                "sha256": info["sha256"],
                "ground_truth": "",  # none exists (WO-040 §5)
                "callsigns_present": "",  # none exist
                "provenance": TEST_FIXTURE_PROVENANCE,
                "usable": "true" if usable else "false",
            })
    return rows


# ---------------------------------------------------------------------------
# Metric definitions (WO-040 §9/§10/§12) — deterministic, reproducible.
# ---------------------------------------------------------------------------
def _normalize(text: str) -> list[str]:
    """Lowercase and split on whitespace (word tokenization for WER)."""
    return [t for t in text.lower().split() if t]


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate = (S + D + I) / N using Levenshtein on words."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    n = len(ref)
    if n == 0:
        return float("nan")
    # Levenshtein distance (words)
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / n


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate = Levenshtein distance on characters / ref length."""
    ref = reference.lower()
    hyp = hypothesis.lower()
    n = len(ref)
    if n == 0:
        return float("nan")
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / n


def callsign_accuracy(reference_callsigns: list[str], hypothesis: str) -> float:
    """Fraction of ground-truth callsigns that appear verbatim in the hypothesis.

    ADR-014: a callsign is correct only if it appears verbatim in the transcript.
    The documented exact-match rule used here: the callsign is normalised to
    lowercase and must appear as a contiguous token in the hypothesis, matched
    on word boundaries (so a callsign ``alpha`` is correct only as a standalone
    word, and ``alpha1`` is a distinct token from ``alpha one``).
    """
    import re

    hyp = hypothesis.lower()
    if not reference_callsigns:
        return float("nan")
    correct = 0
    for cs in reference_callsigns:
        norm = cs.lower().strip()
        if not norm:
            continue
        if re.search(r"\b" + re.escape(norm) + r"\b", hyp):
            correct += 1
    return correct / len(reference_callsigns)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WO-040 STT benchmark harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="detect candidate engine/model availability")
    p.add_argument("--out", default=None)

    m = sub.add_parser("manifest", help="build dataset_manifest.csv")
    m.add_argument("--roots", nargs="*", default=DEFAULT_WAV_ROOTS)
    m.add_argument("--out", default="dataset_manifest.csv")

    met = sub.add_parser("metrics", help="compute WER/CER/callsign from a pair")
    met.add_argument("--reference", required=True)
    met.add_argument("--hypothesis", required=True)
    met.add_argument("--callsigns", nargs="*", default=[])

    args = parser.parse_args(argv)

    if args.cmd == "probe":
        probes = probe_all()
        print(json.dumps(probes, indent=2))
        if args.out:
            with open(args.out, "w") as fh:
                json.dump(probes, fh, indent=2)
        return 0

    if args.cmd == "manifest":
        rows = build_manifest(args.roots)
        with open(args.out, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "audio_id", "wav_path", "source", "duration_s", "channels",
                "sampwidth", "sample_rate", "sha256", "ground_truth",
                "callsigns_present", "provenance", "usable",
            ], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"manifest rows: {len(rows)} -> {args.out}")
        return 0

    if args.cmd == "metrics":
        print(json.dumps({
            "wer": wer(args.reference, args.hypothesis),
            "cer": cer(args.reference, args.hypothesis),
            "callsign_accuracy": callsign_accuracy(args.callsigns, args.hypothesis),
        }, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
