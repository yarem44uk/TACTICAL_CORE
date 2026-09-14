#!/usr/bin/env python3
"""WO-067 — Benchmark CLI (benchmark-only, offline).

Usage (run from the repository root, project ``.venv`` Python)::

    # 1. dataset gate only (no engine needed; CI-safe)
    .venv/bin/python docs/benchmarks/stt/wo067/wo067_cli.py dataset-gate \
        --manifest docs/benchmarks/stt/wo067/wo067_dataset_manifest.csv

    # 2. full benchmark (requires a locally provisioned engine + model)
    .venv/bin/python docs/benchmarks/stt/wo067/wo067_cli.py run \
        --manifest docs/benchmarks/stt/wo067/wo067_dataset_manifest.csv \
        --ground-truth docs/benchmarks/stt/wo067/wo067_ground_truth.json \
        --engine faster_whisper --model-path /path/to/model \
        --language uk --output docs/benchmarks/stt/wo067/wo067_benchmark_results.json

Hard rules enforced by this CLI:
    * completely offline — no download, no cloud, no telemetry;
    * a missing local model is an explicit BLOCKED outcome, never a silent skip;
    * ground truth is never invented; without it WER/CER stay NOT MEASURED;
    * the report never names a production engine.

Exit codes: 0 = measured or clean gate, 2 = BLOCKED, 3 = usage error.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# Allow the production seam to be imported when running from the repo root.
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_BACKEND = os.path.join(_REPO, "backend")
if os.path.isdir(_BACKEND) and _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import wo067_benchmark as B
from wo067_dataset import (
    DatasetError,
    apply_ground_truth,
    load_ground_truth,
    load_manifest,
    verify_dataset_integrity,
)
from wo067_engines import (
    BENCHMARK_ENGINES,
    EngineConfig,
    build_runner,
    check_engine_availability,
    measure_cold_start,
)
from wo067_environment import environment_snapshot

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_USAGE = 3


def _default_engine_config(engine: str, model_path: str | None, language: str, device: str) -> EngineConfig:
    """Documented benchmark configuration, identical for every candidate.

    Parameters are fixed per engine and are never varied between candidates.
    """
    if engine == "faster_whisper":
        return EngineConfig(
            engine=engine,
            model_path=model_path,
            language=language,
            device=device,
            quantization=None,
            beam_size=5,
            vad_filter=False,
        )
    return EngineConfig(
        engine=engine,
        model_path=model_path,
        language=language,
        device=device,
    )


def _load_and_verify(args) -> tuple:
    dataset = load_manifest(args.manifest)
    gt_status = "NOT_PROVIDED"
    if getattr(args, "ground_truth", None):
        ground_truth = load_ground_truth(args.ground_truth)
        dataset = apply_ground_truth(dataset, ground_truth)
        gt_status = "LOADED"
    integrity = verify_dataset_integrity(dataset)
    return dataset, integrity, gt_status


def cmd_dataset_gate(args) -> int:
    """Read-only dataset gate: manifest parse + WAV integrity. No engine."""
    try:
        dataset, integrity, gt_status = _load_and_verify(args)
    except DatasetError as exc:
        print(f"DATASET GATE: BLOCKED — {exc}")
        return EXIT_BLOCKED

    print("WO-067 DATASET GATE")
    print(f"manifest            : {dataset.manifest_path}")
    print(f"candidates          : {dataset.count}")
    print(f"stream distribution : {dataset.stream_counts()}")
    print(f"verified WAVs       : {integrity['ok']}/{integrity['checked']}")
    print(f"excluded            : {integrity['excluded_ids'] or 'none'}")
    print(f"ground truth        : {gt_status}")
    print(f"with transcript GT  : {len(dataset.with_ground_truth_transcript())}")
    print(f"with callsign GT    : {len(dataset.with_ground_truth_callsign())}")

    if integrity["failed"]:
        print("\nINTEGRITY PROBLEMS:")
        for ex in integrity["exclusions"]:
            print(f"  {ex['candidate_id']}: {'; '.join(ex['problems'])}")
        print("\nDATASET GATE: BLOCKED")
        return EXIT_BLOCKED

    print("\nDATASET GATE: PASS (read-only; no engine invoked)")
    return EXIT_OK


def cmd_run(args) -> int:
    """Execute the real benchmark against locally provisioned engines."""
    try:
        dataset, integrity, gt_status = _load_and_verify(args)
    except DatasetError as exc:
        print(f"BENCHMARK: BLOCKED — {exc}")
        return EXIT_BLOCKED

    if integrity["failed"]:
        print("BENCHMARK: BLOCKED — dataset integrity failure")
        for ex in integrity["exclusions"]:
            print(f"  {ex['candidate_id']}: {'; '.join(ex['problems'])}")
        return EXIT_BLOCKED

    engines = args.engine if args.engine else list(BENCHMARK_ENGINES)
    environment = environment_snapshot(language=args.language, device=args.device)

    dataset_meta = {
        "manifest_path": dataset.manifest_path,
        "candidate_count": dataset.count,
        "included_ids": integrity["included_ids"],
        "excluded_ids": integrity["excluded_ids"],
        "exclusion_reasons": integrity["exclusions"],
        "stream_distribution": dataset.stream_counts(),
        "ground_truth_status": gt_status,
        "ground_truth_transcript_count": len(dataset.with_ground_truth_transcript()),
        "ground_truth_callsign_count": len(dataset.with_ground_truth_callsign()),
        "wav_integrity_verified": integrity["checked"],
        "human_review_accepted": True,
        "human_review_note": (
            "PRE-04 human audio review ACCEPTED by the Chief Systems Architect: "
            "the 67 candidates are confirmed human speech."
        ),
        "evidence_package": "WO-067-PRE-04-HUMAN-REVIEW-PACKAGE.zip",
    }

    engine_results: list[dict] = []
    blocked = []
    notes: list[str] = []

    for engine in engines:
        model_path = args.model_path if len(engines) == 1 else None
        cfg = _default_engine_config(engine, model_path, args.language, args.device)
        availability = check_engine_availability(cfg)
        if not availability["ready"]:
            blocked.append(f"{engine}: {availability['reason']}")
            engine_results.append(
                B.build_engine_result(cfg, dataset_meta, [], cold_start_seconds=None)
            )
            continue

        print(f"[{engine}] preparing model (cold start)...")
        try:
            runner = build_runner(cfg)
            cold = measure_cold_start(runner)
        except Exception as exc:  # noqa: BLE001 - reported as BLOCKED
            blocked.append(f"{engine}: engine construction failed — {type(exc).__name__}: {exc}")
            engine_results.append(
                B.build_engine_result(cfg, dataset_meta, [], cold_start_seconds=None)
            )
            continue

        records = []
        timed_out = False
        for candidate in dataset.candidates:
            rec = B.run_candidate(runner, candidate, timeout_seconds=args.timeout)
            records.append(rec)
            if rec["latency_seconds"] is not None:
                print(
                    f"  {candidate.candidate_id} {rec['run_status']}"
                    f" {rec['latency_seconds']:.3f}s"
                )
            else:
                print(f"  {candidate.candidate_id} {rec['run_status']}")
        try:
            runner.close()
        except Exception as exc:  # noqa: BLE001 - teardown must not mask results
            print(f"  [{engine}] runner.close() failed: {type(exc).__name__}: {exc}")

        engine_results.append(
            B.build_engine_result(
                cfg, dataset_meta, records, cold_start_seconds=cold, timed_out=timed_out
            )
        )

    if gt_status != "LOADED":
        notes.append(
            "No human ground-truth transcript was supplied, so WER/CER and callsign "
            "accuracy remain NOT MEASURED for every engine. Model output is never "
            "used as a substitute for human ground truth."
        )
    if blocked:
        notes.append("Blocked engines: " + " | ".join(blocked))

    document = B.build_result_document(
        dataset_meta=dataset_meta,
        environment=environment,
        engine_results=engine_results,
        notes=notes,
    )

    out = args.output or os.path.join(_HERE, "wo067_benchmark_results.json")
    written = B.write_result_document(document, out)
    print(f"\nresults written: {written}")

    if blocked and not any(r["benchmark_executed"] for r in engine_results):
        print("\nBENCHMARK: BLOCKED — no engine could be executed")
        for b in blocked:
            print(f"  {b}")
        return EXIT_BLOCKED

    print("\nBENCHMARK: EXECUTED (see report; engine selection remains a CSA decision)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wo067_cli",
        description="WO-067 real radio STT benchmark (offline, benchmark-only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("dataset-gate", help="read-only dataset integrity gate")
    gate.add_argument("--manifest", required=True)
    gate.add_argument("--ground-truth", default=None)
    gate.set_defaults(func=cmd_dataset_gate)

    run = sub.add_parser("run", help="execute the benchmark on local engines")
    run.add_argument("--manifest", required=True)
    run.add_argument("--ground-truth", default=None)
    run.add_argument("--engine", action="append", choices=list(BENCHMARK_ENGINES), default=None)
    run.add_argument("--model-path", default=None)
    run.add_argument("--language", default="uk")
    run.add_argument("--device", default="cpu")
    run.add_argument("--timeout", type=float, default=None)
    run.add_argument("--output", default=None)
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())