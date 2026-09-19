"""WO-069 — benchmark unit tests: evidence serialization + report rules.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo069_report as R
from wo069_dataset import DatasetRecord

EXPECTED_FILES = (
    "benchmark_results.csv",
    "transcript_comparison.csv",
    "callsign_results.csv",
    "runtime_metrics.csv",
    "resource_metrics.csv",
    "environment_manifest.json",
    "dataset_manifest.json",
    "WO-069-EVIDENCE-REPORT.md",
)


def _results(*, reference_available: bool = False, callsign_available: bool = False) -> dict:
    return {
        "benchmark_version": "wo069-benchmark-1.0",
        "work_order": "WO-069",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "status": "BENCHMARK EXECUTED",
        "dataset": {
            "dataset_root": "/fixture",
            "expected_record_count": 1,
            "record_count": 1,
            "completeness": "COMPLETE",
            "wav_count": 1,
            "total_duration_seconds": 1.0,
            "human_reviewed_count": 1,
            "human_review_pending_count": 0,
            "human_review_source_path": "/fixture/human_review.csv",
            "human_review_source_sha256": "a" * 64,
            "dataset_manifest_sha256": "b" * 64,
            "reference_transcript_count": 1 if reference_available else 0,
            "reference_transcript_status": "AVAILABLE" if reference_available else "UNAVAILABLE",
            "reference_transcript_reason": "",
            "reference_callsign_status": "AVAILABLE" if callsign_available else "UNAVAILABLE",
            "reference_callsign_count": 1 if callsign_available else 0,
            "artifact_resolution": {
                "named_in_work_order": "WO-068-HUMAN-REVIEW-EXTENDED.xlsx",
                "named_artifact_found": False,
                "dataset_manifest_present": True,
                "ground_truth_present": True,
                "human_review_csv_present": True,
            },
        },
        "environment": {"gpu": "NOT AVAILABLE", "repo_head": "deadbeef", "dataset_hash": "c" * 64},
        "engines": [
            {
                "engine": "fixture",
                "engine_status": "COMPLETED",
                "configuration": {"model_path": "/fixture/model", "device": "cpu",
                                  "compute_type": "int8", "sample_rate_policy": "native"},
                "cold_start_ms": 10.0,
                "exit_code": 0,
                "failure_reason": None,
                "oom_evidence": None,
                "aggregate": {
                    "timing": {"median_latency_seconds": 0.5, "p95_latency_seconds": 0.9,
                               "median_rtf": 0.5, "p95_rtf": 0.9},
                    "reliability": {"total_runs": 1, "successful_runs": 1, "failed_runs": 0,
                                    "timeout_runs": 0, "failure_rate": 0.0},
                    "resources": {"peak_rss_bytes_max": 2048,
                                  "cpu_user_seconds_total": 0.2},
                    "accuracy": {"wer_mean": "NOT_MEASURED", "cer_mean": "NOT_MEASURED",
                                 "ground_truth_scored_candidates": 0},
                },
                "callsign_accuracy": {"status": "NOT_MEASURED", "accuracy": "NOT_MEASURED"},
                "records": [
                    {
                        "message_id": "msg_0001",
                        "wav_path": "/fixture/msg_0001.wav",
                        "audio_duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "text": "привіт світ",
                        "latency_ms": 500.0,
                        "rtf": 0.5,
                        "cpu_user_s": 0.2,
                        "cpu_sys_s": 0.01,
                        "peak_rss_kb": 2048,
                        "error": None,
                        "error_type": None,
                    }
                ],
            }
        ],
    }


def _record(reference: str | None, callsign: str | None) -> DatasetRecord:
    record = DatasetRecord(
        message_id="msg_0001", stream_id="S1", wav_path="/fixture/msg_0001.wav",
        duration_seconds=1.0, dataset_sha256="0" * 64,
        human_review_status="REVIEWED", human_audible_voice="YES",
        human_intelligible="YES", human_voice_type="FEMALE",
    )
    record.human_reference_transcript = reference
    record.human_callsign = callsign
    record.reference_available = reference is not None
    record.callsign_reference_available = callsign is not None
    return record


def test_benchmark_results_schema_is_exact(tmp_path):
    records_by_id = {"msg_0001": _record(None, None)}
    tables = R.build_evidence_rows(_results(), records_by_id)
    row = tables["benchmark_results"][0]
    assert tuple(row.keys()) == R.BENCHMARK_RESULT_FIELDS
    assert row["engine"] == "fixture"
    assert row["reference_available"] is False
    assert row["wer"] == "NOT_MEASURED"
    assert row["cer"] == "NOT_MEASURED"


def test_wer_is_computed_only_with_a_reference(tmp_path):
    records_by_id = {"msg_0001": _record("привіт світ", None)}
    tables = R.build_evidence_rows(_results(reference_available=True), records_by_id)
    row = tables["benchmark_results"][0]
    assert row["wer"] == 0.0
    assert row["cer"] == 0.0


def test_callsign_rows_are_separate_and_not_measured_without_labels():
    records_by_id = {"msg_0001": _record(None, None)}
    tables = R.build_evidence_rows(_results(), records_by_id)
    callsign_row = tables["callsign_results"][0]
    assert callsign_row["callsign_outcome"] == "NOT_MEASURED"
    assert callsign_row["human_callsign"] == "UNAVAILABLE"
    assert "separate" in callsign_row["note"]


def test_callsign_outcome_computed_when_reference_present():
    records_by_id = {"msg_0001": _record(None, "ALPHA")}
    tables = R.build_evidence_rows(_results(callsign_available=True), records_by_id)
    # The engine produced "привіт світ" -> reference callsign ALPHA not found -> MISSED
    assert tables["callsign_results"][0]["human_callsign"] == "ALPHA"
    assert tables["callsign_results"][0]["callsign_reference_available"] is True
    assert tables["callsign_results"][0]["callsign_outcome"] == "MISSED"


def test_write_evidence_writes_every_required_file(tmp_path):
    records_by_id = {"msg_0001": _record(None, None)}
    paths = R.write_evidence(str(tmp_path), _results(), records_by_id)
    for name in EXPECTED_FILES:
        assert name in paths
        assert os.path.exists(paths[name])


def test_csv_header_order_is_deterministic(tmp_path):
    records_by_id = {"msg_0001": _record(None, None)}
    paths = R.write_evidence(str(tmp_path), _results(), records_by_id)
    with open(paths["benchmark_results.csv"], newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert tuple(header) == R.BENCHMARK_RESULT_FIELDS
    with open(paths["runtime_metrics.csv"], newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == [
            "engine", "model", "message_id", "status", "audio_duration_seconds",
            "processing_time_ms", "latency_seconds", "rtf", "cold_start_ms",
        ]


def test_report_never_declares_a_production_winner(tmp_path):
    records_by_id = {"msg_0001": _record(None, None)}
    text = R.render_report(_results(), records_by_id).lower()
    for forbidden in ("is the best", "selected for production", "we recommend",
                      "winner is"):
        assert forbidden not in text
    assert "not made" in text or "no production engine is selected" in text


def test_report_includes_failure_section():
    results = _results()
    results["engines"][0]["engine_status"] = "FAILED"
    results["engines"][0]["failure_reason"] = "model load failed: boom"
    results["engines"][0]["records"][0]["status"] = "FAILED"
    results["engines"][0]["records"][0]["error"] = "ModelLoadError: boom"
    records_by_id = {"msg_0001": _record(None, None)}
    text = R.render_report(results, records_by_id)
    assert "model load failed: boom" in text
    assert "msg_0001" in text
