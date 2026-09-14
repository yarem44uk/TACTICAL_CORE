"""WO-067 — Benchmark core: run accounting, aggregation, result serialization.

This is the measurement instrument.  It NEVER selects a production engine and
NEVER fabricates a measurement: every accuracy, timing and resource value is
either measured or explicitly reported as NOT MEASURED / NOT AVAILABLE.

Failure accounting is explicit and denominator-preserving (WO-067 §10): a
failed, timed-out or unavailable run is recorded, never dropped from the
per-file ledger.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone

import wo067_metrics as M
from wo067_dataset import Candidate
from wo067_engines import EngineConfig, check_engine_availability
from wo067_environment import (
    read_cpu_times,
    read_peak_rss_bytes,
    sample_gpu_utilization,
)

BENCHMARK_VERSION = "wo067-benchmark-1.0"

# Run outcome taxonomy (WO-067 §10 reliability).
RUN_SUCCESS = "SUCCESS"
RUN_FAILED = "FAILED"
RUN_TIMEOUT = "TIMEOUT"
RUN_UNAVAILABLE = "UNAVAILABLE"

NOT_MEASURED = "NOT_MEASURED"
NOT_AVAILABLE = "NOT_AVAILABLE"


def _wav_duration_seconds(candidate: Candidate) -> float:
    return candidate.duration_ms / 1000.0


def run_candidate(
    runner,
    candidate: Candidate,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    """Transcribe one candidate and return a complete per-file ledger record.

    A failure is captured in the record, never raised, so the candidate always
    stays in the denominator.
    """
    record: dict = {
        "candidate_id": candidate.candidate_id,
        "stream_id": candidate.stream_id,
        "audio_path": candidate.audio_path,
        "wav_sha256": candidate.wav_sha256,
        "audio_duration_seconds": _wav_duration_seconds(candidate),
        "run_status": RUN_FAILED,
        "error": None,
        "error_type": None,
        "latency_seconds": None,
        "rtf": None,
        "cpu_user_seconds": None,
        "cpu_system_seconds": None,
        "peak_rss_bytes": None,
        "gpu_utilization_pct": None,
        "vram_used_bytes": None,
        "hypothesis": None,
        "wer": NOT_MEASURED,
        "cer": NOT_MEASURED,
        "exact_match": NOT_MEASURED,
        "callsign_outcome": NOT_MEASURED,
        "ground_truth_status": candidate.ground_truth_status,
    }

    cpu_before = read_cpu_times()
    gpu_util, vram_used = sample_gpu_utilization()
    started = time.perf_counter()
    try:
        hypothesis = runner.transcribe_path(candidate.audio_path)
    except Exception as exc:  # noqa: BLE001 - recorded as a failed run
        elapsed = time.perf_counter() - started
        record["latency_seconds"] = elapsed
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["error_type"] = type(exc).__name__
        record["run_status"] = RUN_FAILED
        record["peak_rss_bytes"] = read_peak_rss_bytes()
        return record
    elapsed = time.perf_counter() - started

    cpu_after = read_cpu_times()
    record["run_status"] = RUN_SUCCESS
    record["latency_seconds"] = elapsed
    record["hypothesis"] = hypothesis
    record["peak_rss_bytes"] = read_peak_rss_bytes()
    record["gpu_utilization_pct"] = gpu_util
    record["vram_used_bytes"] = vram_used
    if cpu_before and cpu_after:
        record["cpu_user_seconds"] = cpu_after[0] - cpu_before[0]
        record["cpu_system_seconds"] = cpu_after[1] - cpu_before[1]

    duration = record["audio_duration_seconds"]
    record["rtf"] = M.real_time_factor(elapsed, duration)

    # Accuracy is computed ONLY against explicit human ground truth.
    if candidate.has_ground_truth_transcript:
        record["wer"] = M.wer(candidate.ground_truth_transcript, hypothesis)
        record["cer"] = M.cer(candidate.ground_truth_transcript, hypothesis)
        record["exact_match"] = M.exact_match(candidate.ground_truth_transcript, hypothesis)
    if candidate.has_ground_truth_callsign:
        record["callsign_outcome"] = M.callsign_outcome(
            candidate.ground_truth_callsign, hypothesis
        )
    return record


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (deterministic, no interpolation ambiguity).

    Rank = ceil(pct/100 * N), clamped to [1, N]; the value at that rank in the
    ascending order is returned (1-indexed).
    """
    if not values:
        return None
    ordered = sorted(values)
    import math

    rank = math.ceil(pct / 100.0 * len(ordered))
    rank = max(1, min(len(ordered), rank))
    return ordered[rank - 1]


def aggregate_records(records: list[dict]) -> dict:
    """Aggregate per-file records into timing, reliability, resource, accuracy.

    Every aggregate that cannot be computed is reported NOT_MEASURED rather than
    defaulted to a number.
    """
    total = len(records)
    successes = [r for r in records if r["run_status"] == RUN_SUCCESS]
    failed = [r for r in records if r["run_status"] == RUN_FAILED]
    timeouts = [r for r in records if r["run_status"] == RUN_TIMEOUT]
    unavailable = [r for r in records if r["run_status"] == RUN_UNAVAILABLE]
    exceptions = [r for r in failed if r["error_type"]]

    latencies = [r["latency_seconds"] for r in successes if r["latency_seconds"] is not None]
    rtfs = [r["rtf"] for r in successes if r["rtf"] is not None]

    timing = {
        "per_file_latency_seconds": {
            r["candidate_id"]: r["latency_seconds"] for r in records
        },
        "median_latency_seconds": statistics.median(latencies) if latencies else NOT_MEASURED,
        "p95_latency_seconds": _percentile(latencies, 95) if latencies else NOT_MEASURED,
        "min_latency_seconds": min(latencies) if latencies else NOT_MEASURED,
        "max_latency_seconds": max(latencies) if latencies else NOT_MEASURED,
        "median_rtf": statistics.median(rtfs) if rtfs else NOT_MEASURED,
        "p95_rtf": _percentile(rtfs, 95) if rtfs else NOT_MEASURED,
        "rtf_definition": "RTF = processing_time / audio_duration",
    }

    reliability = {
        "total_runs": total,
        "successful_runs": len(successes),
        "failed_runs": len(failed),
        "timeout_runs": len(timeouts),
        "unavailable_runs": len(unavailable),
        "exception_count": len(exceptions),
        "failure_rate": (
            round((total - len(successes)) / total, 6) if total else NOT_MEASURED
        ),
    }

    rss = [r["peak_rss_bytes"] for r in successes if r["peak_rss_bytes"] is not None]
    cpu_user = [r["cpu_user_seconds"] for r in successes if r["cpu_user_seconds"] is not None]
    gpu_utils = [
        r["gpu_utilization_pct"] for r in successes if r["gpu_utilization_pct"] is not None
    ]
    vrams = [r["vram_used_bytes"] for r in successes if r["vram_used_bytes"] is not None]
    resources = {
        "cpu_user_seconds_total": sum(cpu_user) if cpu_user else NOT_MEASURED,
        "cpu_user_seconds_median_per_file": (
            statistics.median(cpu_user) if cpu_user else NOT_MEASURED
        ),
        "peak_rss_bytes_max": max(rss) if rss else NOT_MEASURED,
        "gpu_utilization_pct": (
            statistics.median(gpu_utils) if gpu_utils else NOT_AVAILABLE
        ),
        "vram_used_bytes_max": max(vrams) if vrams else NOT_AVAILABLE,
    }

    scored = [r for r in successes if r["wer"] != NOT_MEASURED]
    if scored:
        wers = [r["wer"] for r in scored]
        cers = [r["cer"] for r in scored]
        accuracy = {
            "ground_truth_scored_candidates": len(scored),
            "wer_mean": sum(wers) / len(wers),
            "wer_median": statistics.median(wers),
            "cer_mean": sum(cers) / len(cers),
            "cer_median": statistics.median(cers),
            "exact_match_count": sum(1 for r in scored if r["exact_match"] is True),
            "exact_match_rate": sum(1 for r in scored if r["exact_match"] is True)
            / len(scored),
        }
    else:
        accuracy = {
            "ground_truth_scored_candidates": 0,
            "wer_mean": NOT_MEASURED,
            "wer_median": NOT_MEASURED,
            "cer_mean": NOT_MEASURED,
            "cer_median": NOT_MEASURED,
            "exact_match_count": NOT_MEASURED,
            "exact_match_rate": NOT_MEASURED,
            "reason": "no candidate has a human ground-truth transcript",
        }

    return {
        "timing": timing,
        "reliability": reliability,
        "resources": resources,
        "accuracy": accuracy,
    }


def aggregate_callsign_accuracy(records: list[dict]) -> dict:
    """Callsign accuracy, only over candidates with explicit human callsign GT."""
    relevant = [
        r for r in records
        if r["run_status"] == RUN_SUCCESS and r["callsign_outcome"] != NOT_MEASURED
    ]
    if not relevant:
        return {
            "status": NOT_MEASURED,
            "reason": "human ground truth contains no callsign for any candidate",
            "exact_match": 0,
            "normalized_match": 0,
            "missed": 0,
            "false": 0,
            "not_present": 0,
            "scored_candidates": 0,
            "accuracy": NOT_MEASURED,
        }
    counts = {k: 0 for k in (M.EXACT_MATCH, M.NORMALIZED_MATCH, M.MISSED, M.FALSE, M.NOT_PRESENT)}
    for r in relevant:
        counts[r["callsign_outcome"]] = counts.get(r["callsign_outcome"], 0) + 1
    correct = counts[M.EXACT_MATCH] + counts[M.NORMALIZED_MATCH]
    return {
        "status": "MEASURED",
        "scored_candidates": len(relevant),
        "exact_match": counts[M.EXACT_MATCH],
        "normalized_match": counts[M.NORMALIZED_MATCH],
        "missed": counts[M.MISSED],
        "false": counts[M.FALSE],
        "not_present": counts[M.NOT_PRESENT],
        "accuracy": correct / len(relevant),
        "normalization_policy": (
            "NORMALIZED_MATCH = alphanumeric-only casefold substring match of the "
            "human callsign within the normalized hypothesis"
        ),
    }


def build_engine_result(
    cfg: EngineConfig,
    dataset_meta: dict,
    records: list[dict],
    *,
    cold_start_seconds: float | None,
    timed_out: bool = False,
) -> dict:
    """Assemble the complete result block for one engine."""
    availability = check_engine_availability(cfg)
    aggregate = aggregate_records(records)
    return {
        "engine": cfg.engine,
        "engine_availability": availability,
        "model": {
            "model_id": cfg.model_path,
            "local_model_path": cfg.model_path,
            "model_version": cfg.extra.get("model_version"),
            "model_size_bytes": cfg.extra.get("model_size_bytes"),
            "quantization": cfg.quantization,
            "device": cfg.device,
            "language": cfg.language,
        },
        "configuration": cfg.to_dict(),
        "cold_start_seconds": (
            cold_start_seconds if cold_start_seconds is not None else NOT_MEASURED
        ),
        "runs": records,
        "aggregate": aggregate,
        "callsign_accuracy": aggregate_callsign_accuracy(records),
        "benchmark_executed": bool(records),
        "timed_out": timed_out,
        "dataset_reference": dataset_meta,
    }


def build_result_document(
    *,
    dataset_meta: dict,
    environment: dict,
    engine_results: list[dict],
    notes: list[str] | None = None,
) -> dict:
    """Assemble the top-level machine-readable benchmark result document."""
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "work_order": "WO-067",
        "stage": "PRE-05",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_platform": platform.platform(),
        "dataset": dataset_meta,
        "environment": environment,
        "engines": engine_results,
        "production_engine_selection": "CSA DECISION REQUIRED",
        "production_engine_selection_note": (
            "This document is a measurement instrument only. It does not select, "
            "recommend or authorize a production STT engine. Engine selection "
            "belongs to WO-068 and remains a Chief Systems Architect decision."
        ),
        "provenance": {
            "transport_provenance": (
                "CubicCore traffic generator v7.19.4 over a simulated L2/L3 "
                "topology; no RF/SDR provenance."
            ),
            "audio_content_provenance": (
                "Human speech, confirmed by CSA human listening of the PRE-04 "
                "package. Audio-content provenance is INDEPENDENT of transport "
                "provenance: synthetic transport does not imply synthetic audio, "
                "and human audio does not imply a real radio capture."
            ),
            "real_radio_rf_provenance_claimed": False,
            "evidence_package": "WO-067-PRE-04-HUMAN-REVIEW-PACKAGE.zip",
            "source_pcap_sha256": (
                "0c9a0716d904d025079ecba00c585dfcac699351917dc804dffb0b4d4cd1eb20"
            ),
        },
        "notes": notes or [],
    }


def write_result_document(document: dict, path: str) -> str:
    """Write the result document deterministically; never overwrite silently.

    If ``path`` already exists it is preserved and a versioned sibling is
    written instead (WO-067 §17: never overwrite previous authoritative
    results).
    """
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