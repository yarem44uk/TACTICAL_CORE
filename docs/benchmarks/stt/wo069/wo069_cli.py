#!/usr/bin/env python3
"""WO-069 — Benchmark CLI (benchmark-only, offline, read-only inputs).

Usage (from the repository root)::

    # 1. dataset gate (read-only, no engine required; CI-safe)
    python docs/benchmarks/stt/wo069/wo069_cli.py dataset-gate

    # 2. run the controlled benchmark (needs the provisioned engine venv)
    python docs/benchmarks/stt/wo069/wo069_cli.py run \
        --workdir /opt/data/wo069_runtime \
        --evidence docs/benchmarks/stt/wo069/WO-069-EVIDENCE

Exit codes: 0 = measured / clean gate, 2 = BLOCKED, 3 = usage error.

Hard rules: offline only; no model download; the human-review artifact is
read-only; no engine is registered in production; no production engine is
selected; no result is fabricated.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo069_report as R
from wo069_dataset import (
    DEFAULT_DATASET_ROOT,
    DEFAULT_HUMAN_REVIEW_CSV,
    EXPECTED_RECORD_COUNT,
    DatasetError,
    build_records,
    dataset_manifest_document,
    verify_wav_integrity,
)
from wo069_environment import environment_snapshot
from wo069_runner import EngineSpec, run_engine

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_USAGE = 3

DEFAULT_VENV = "/opt/data/wo067_runtime_gate_v1/venv/bin/python"
DEFAULT_FW_MODEL = "/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/faster_whisper"
DEFAULT_VOSK_MODEL = (
    "/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/vosk_uk/vosk-model-uk-v3"
)


def _repo_head() -> str:
    try:
        return subprocess.run(
            ["git", "-C", os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")),
             "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def default_specs(args) -> list[EngineSpec]:
    """Documented engine set: identical dataset, language condition and env."""
    return [
        EngineSpec(
            engine="faster_whisper",
            display_name="Faster-Whisper (CTranslate2)",
            model_path=args.fw_model,
            venv_python=args.venv_python,
            language=None,  # auto-detect recorded; identical input for both engines
            device="cpu",
            compute_type="int8",
            model_revision="bundled (WO-067 OFFLINE-BUNDLE)",
            sample_rate_policy="native 8 kHz (engine decodes natively)",
            notes=["beam_size default; vad_filter disabled (no preprocessing between engines)"],
        ),
        EngineSpec(
            engine="vosk",
            display_name="Vosk (Kaldi) — vosk-model-uk-v3",
            model_path=args.vosk_model,
            venv_python=args.venv_python,
            language="uk",
            device="cpu",
            compute_type="",
            model_revision="vosk-model-uk-v3",
            sample_rate_policy=(
                "deterministic linear 8 kHz -> 16 kHz upsample "
                "(model hard-codes 16 kHz); original 8 kHz WAV is the input of record"
            ),
            notes=["single-utterance FinalResult per file; recognizer reset per file"],
        ),
    ]


def cmd_dataset_gate(args) -> int:
    try:
        records = build_records(args.dataset_root, args.human_review_csv)
    except DatasetError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        return EXIT_BLOCKED
    for record in records:
        verify_wav_integrity(record)
    document = dataset_manifest_document(
        records,
        dataset_root=args.dataset_root,
        human_review_csv=args.human_review_csv,
        expected_count=args.expected_count,
    )
    print(json.dumps(
        {
            "record_count": document["record_count"],
            "expected": document["expected_record_count"],
            "completeness": document["completeness"],
            "wav_verified": document["wav_count"],
            "wav_integrity_failures": document["wav_integrity_failures"],
            "human_reviewed_count": document["human_reviewed_count"],
            "reference_transcript_count": document["reference_transcript_count"],
            "reference_transcript_status": document["reference_transcript_status"],
            "reference_callsign_status": document["reference_callsign_status"],
            "named_artifact_found": document["artifact_resolution"]["named_artifact_found"],
        },
        indent=2,
    ))
    return EXIT_OK


def cmd_run(args) -> int:
    records = build_records(args.dataset_root, args.human_review_csv)
    for record in records:
        verify_wav_integrity(record)
    records_by_id = {r.message_id: r for r in records}
    dataset_document = dataset_manifest_document(
        records, dataset_root=args.dataset_root,
        human_review_csv=args.human_review_csv, expected_count=args.expected_count,
    )
    if dataset_document["completeness"] != "COMPLETE":
        print(json.dumps({"status": "DATASET INCOMPLETE", "dataset": {
            "expected": dataset_document["expected_record_count"],
            "actual": dataset_document["record_count"],
        }}, indent=2))
        return EXIT_BLOCKED

    specs = default_specs(args)
    sel = set(args.engines.split(",")) if args.engines else None
    if sel:
        specs = [s for s in specs if s.engine in sel]

    env = environment_snapshot(
        specs=specs,
        dataset_paths=[
            os.path.join(args.dataset_root, "dataset/manifest.csv"),
            args.human_review_csv or "",
            os.path.join(args.dataset_root, "dataset/ground_truth/ground_truth.json"),
        ],
        repo_head=_repo_head(),
    )

    engine_results = []
    for spec in specs:
        print(f"[wo069] running engine: {spec.engine} …", file=sys.stderr)
        engine_result = run_engine(
            spec,
            records,
            workdir=args.workdir,
            timeout_seconds=args.engine_timeout,
            per_file_timeout=args.per_file_timeout,
        )
        aggregate = _aggregate(engine_result)
        engine_result["aggregate"] = aggregate
        engine_result["callsign_accuracy"] = _callsign_aggregate(engine_result)
        print(
            f"[wo069]   {spec.engine}: {engine_result['engine_status']} "
            f"({aggregate['reliability']['successful_runs']}/"
            f"{aggregate['reliability']['total_runs']} ok)",
            file=sys.stderr,
        )
        engine_results.append(engine_result)

    executed = [e for e in engine_results if e["engine_status"] == "COMPLETED"]
    status = "BENCHMARK EXECUTED" if executed else "BLOCKED"
    document = {
        "benchmark_version": "wo069-benchmark-1.0",
        "work_order": "WO-069",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "dataset": dataset_document,
        "environment": env,
        "engines": engine_results,
        "production_engine_selection": "NOT MADE — CSA DECISION REQUIRED (ADR-014 Part 2)",
        "production_engine_selection_note": (
            "This document is a measurement instrument. It does not select, "
            "recommend or authorize a production STT engine."
        ),
        "notes": [
            "Human-review artifact is READ-ONLY evidence; no transcript, callsign, "
            "language label or confidence value was modified or invented.",
            "No production file is imported, modified or registered by this layer.",
        ],
    }

    paths = R.write_evidence(args.evidence_dir, document, records_by_id)
    print(json.dumps({"status": status, "evidence": paths}, indent=2))
    return EXIT_OK if executed else EXIT_BLOCKED


def cmd_report(args) -> int:
    """Regenerate the evidence set from a saved result document (no engine run)."""
    with open(args.results_json, encoding="utf-8") as fh:
        document = json.load(fh)
    records = build_records(args.dataset_root, args.human_review_csv)
    for record in records:
        verify_wav_integrity(record)
    records_by_id = {r.message_id: r for r in records}
    if args.evidence_dir is None:
        args.evidence_dir = os.path.dirname(os.path.abspath(args.results_json))
    paths = R.write_evidence(args.evidence_dir, document, records_by_id)
    print(json.dumps({"status": document.get("status"), "evidence": paths}, indent=2))
    return EXIT_OK


def _aggregate(engine_result: dict) -> dict:
    records = engine_result["records"]
    successes = [r for r in records if r["status"] == "SUCCESS"]
    latencies = [r["latency_ms"] / 1000.0 for r in successes if r.get("latency_ms")]
    rtfs = [r["rtf"] for r in successes if r.get("rtf") is not None]
    rss = [r["peak_rss_kb"] for r in records if r.get("peak_rss_kb") is not None]
    cpu_user = [r["cpu_user_s"] for r in records if r.get("cpu_user_s") is not None]
    total = len(records)
    import wo069_metrics as M  # local import keeps the CLI import-light

    return {
        "timing": {
            "median_latency_seconds": M.median(latencies),
            "p95_latency_seconds": M.percentile(latencies, 95),
            "min_latency_seconds": min(latencies) if latencies else M.NOT_MEASURED,
            "max_latency_seconds": max(latencies) if latencies else M.NOT_MEASURED,
            "median_rtf": M.median(rtfs),
            "p95_rtf": M.percentile(rtfs, 95),
            "rtf_definition": "RTF = processing_time / audio_duration",
        },
        "reliability": {
            "total_runs": total,
            "successful_runs": len(successes),
            "failed_runs": len([r for r in records if r["status"] == "FAILED"]),
            "timeout_runs": len([r for r in records if r["status"] == "TIMEOUT"]),
            "malformed_input_runs": len(
                [r for r in records if (r.get("error") or "").startswith("MALFORMED")]
            ),
            "model_load_failures": 1 if engine_result["model_load_status"] == "FAILED" else 0,
            "failure_rate": round((total - len(successes)) / total, 6) if total else M.NOT_MEASURED,
        },
        "resources": {
            "peak_rss_bytes_max": max(rss) * 1024 if rss else M.NOT_MEASURED,
            "peak_rss_kb_max": max(rss) if rss else M.NOT_MEASURED,
            "cpu_user_seconds_total": round(sum(cpu_user), 6) if cpu_user else M.NOT_MEASURED,
        },
        "accuracy": {
            "ground_truth_scored_candidates": 0,
            "wer_mean": M.NOT_MEASURED,
            "cer_mean": M.NOT_MEASURED,
            "reason": "no human reference transcript exists for any message in the "
                      "human-review artifact; WER/CER are not computable and are NOT estimated",
        },
    }


def _callsign_aggregate(engine_result: dict) -> dict:
    return {
        "status": "NOT_MEASURED",
        "reason": "the human-review artifact records no callsign for any message; "
                  "callsign accuracy is therefore not computable",
        "scored_candidates": 0,
        "accuracy": "NOT_MEASURED",
        "note": "callsign evaluation remains architecturally separate from transcript WER/CER",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WO-069 benchmark CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--dataset-root", default=DEFAULT_DATASET_ROOT)
        p.add_argument("--human-review-csv", default=DEFAULT_HUMAN_REVIEW_CSV)
        p.add_argument("--expected-count", type=int, default=EXPECTED_RECORD_COUNT)

    gate = sub.add_parser("dataset-gate")
    add_common(gate)
    gate.set_defaults(func=cmd_dataset_gate)

    run = sub.add_parser("run")
    add_common(run)
    run.add_argument("--workdir", default="/opt/data/wo069_runtime")
    run.add_argument("--evidence-dir", default=os.path.join(_HERE, "WO-069-EVIDENCE"))
    run.add_argument("--venv-python", default=DEFAULT_VENV)
    run.add_argument("--fw-model", default=DEFAULT_FW_MODEL)
    run.add_argument("--vosk-model", default=DEFAULT_VOSK_MODEL)
    run.add_argument("--engines", default="")
    run.add_argument("--engine-timeout", type=float, default=0.0)
    run.add_argument("--per-file-timeout", type=float, default=120.0)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report")
    add_common(report)
    report.add_argument("--results-json", required=True)
    report.add_argument("--evidence-dir", default=None)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DatasetError as exc:
        print(f"DATASET ERROR: {exc}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
