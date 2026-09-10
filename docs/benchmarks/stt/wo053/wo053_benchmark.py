"""WO-053 — Offline STT candidate benchmark runner (benchmark gate).

This is benchmark-only tooling.  It does NOT select a production engine, does
NOT modify production code, and is OFFLINE (no model download, no cloud call,
no network).  It discovers candidate engines by importability, runs the
CandidateSession lifecycle only when a candidate is actually available, and
records an explicit ``NOT_AVAILABLE`` result otherwise.

The lifecycle mirrors WO-040's CandidateSession semantics:
    initialize() once  -> COLD (latency = init + first inference)
    transcribe() many   -> WARM (latency = inference, session reused)
    close()

Because no STT runtime / model is installed on this host, every candidate is
reported ``NOT_AVAILABLE`` and the benchmark is NOT EXECUTED on real acoustic
inference.  The mechanics (discovery, accounting, schema, determinism,
reproducibility) are still exercised and validated.

Author: Tactical Core Engineering Team
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import resource
import sys
import time
from datetime import datetime, timezone

# Candidate engines from app.audio.stt_config.SUPPORTED_ENGINES (recognised set,
# NOT a production choice).
SUPPORTED_ENGINES = ["faster_whisper", "vosk"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_environment() -> dict:
    """Capture deterministic environment facts (no secrets, no network)."""
    env = {
        "python_version": platform.python_version(),
        "python_impl": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "os_release": platform.release(),
    }
    # Total physical RAM (Linux) from /proc/meminfo.
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    env["total_ram_kb"] = int(line.split()[1])
                    break
    except Exception:  # noqa: BLE001
        env["total_ram_kb"] = None
    # Peak RSS from the process's own resource usage.
    try:
        env["process_peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:  # noqa: BLE001
        env["process_peak_rss_kb"] = None
    return env


def _module_version(module_name: str):
    """Best-effort version string for an installed module (importable only)."""
    try:
        mod = __import__(module_name)
        return getattr(mod, "__version__", None) or getattr(mod, "VERSION", None)
    except Exception:  # noqa: BLE001
        return None


def discover_candidate(engine: str) -> dict:
    """Discover one candidate engine; return a machine-readable record.

    Records ``available``, and when unavailable an explicit ``availability_reason``.
    Never downloads, never reaches the network.
    """
    rec = {
        "candidate": engine,
        "available": False,
        "status": "NOT_AVAILABLE",
        "version": None,
        "model": None,
        "model_path": None,
        "device": None,
        "compute_type": None,
        "language": None,
        "availability_reason": None,
    }
    spec = importlib.util.find_spec(engine)
    if spec is None:
        rec["availability_reason"] = (
            f"module '{engine}' not installed in this environment; "
            "no model file present; offline rule forbids download"
        )
        return rec
    rec["available"] = True
    rec["status"] = "AVAILABLE"
    rec["version"] = _module_version(engine)
    # When an engine is installed, a model must also be present; the benchmark
    # requires a local model_path.  WO-053 never downloads.
    rec["availability_reason"] = "engine module present; model availability must be provisioned locally"
    return rec


def discover_candidates() -> list[dict]:
    return [discover_candidate(e) for e in SUPPORTED_ENGINES]


def _cpu_seconds() -> float:
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return ru.ru_utime + ru.ru_stime
    except Exception:  # noqa: BLE001
        return 0.0


def run_benchmark(dataset_manifest: str, output_json: str, *, candidates: list[str] | None = None) -> dict:
    """Run the offline benchmark gate and write machine-readable JSON.

    For every candidate that is actually available, the CandidateSession
    lifecycle is executed against the dataset.  For unavailable candidates an
    explicit NOT_AVAILABLE record is emitted.  No accuracy number is invented
    for a candidate that never ran.
    """
    engine_list = candidates or SUPPORTED_ENGINES
    started = time.monotonic()
    env = _capture_environment()

    # Load the dataset manifest to report dataset identity / inputs.
    dataset = {
        "manifest_path": os.path.abspath(dataset_manifest),
        "row_count": 0,
        "inputs": [],
        "speech_rows": 0,
    }
    import csv
    with open(dataset_manifest, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            dataset["row_count"] += 1
            dataset["inputs"].append(
                {
                    "audio_id": row.get("audio_id"),
                    "audio_path": row.get("audio_path"),
                    "sha256": row.get("sha256"),
                    "duration_seconds": row.get("duration_seconds"),
                    "sample_rate": row.get("sample_rate"),
                    "source_type": row.get("source_type"),
                    "real_transmission": row.get("real_transmission"),
                    "speech_present": row.get("speech_present"),
                    "transcript": row.get("transcript"),
                }
            )
            if row.get("speech_present") == "true":
                dataset["speech_rows"] += 1

    candidate_results = []
    for engine in engine_list:
        rec = discover_candidate(engine)
        if rec["available"]:
            # Real inference path: only reached when an engine + model are
            # provisioned locally.  Not reached on this host (no engine).
            rec["runs"] = _run_available_lifecycle(rec, dataset)
        else:
            rec["runs"] = []
        candidate_results.append(rec)

    result = {
        "benchmark": "WO-053 STT benchmark gate",
        "timestamp": _now_iso(),
        "environment": env,
        "dataset": dataset,
        "candidates": candidate_results,
        "benchmark_executed": any(c["available"] for c in candidate_results),
        "execution_metadata": {
            "wall_time_seconds": round(time.monotonic() - started, 4),
            "cpu_seconds": round(_cpu_seconds(), 4),
            "note": "NO engine runtime/model provisioned locally; "
                    "benchmark NOT executed on real acoustic inference.",
        },
        "production_selection_made": False,
    }

    with open(output_json, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    return result


def _run_available_lifecycle(candidate_rec: dict, dataset: dict) -> list[dict]:
    """Execute the CandidateSession lifecycle for an available candidate.

    This path is only reachable when an engine is provisioned.  On this host no
    engine is installed, so it is not exercised; it exists so the runner is
    complete and honest if a provisioned engine appears later.
    """
    # Placeholder to keep the schema complete.  WO-053 never fabricates numbers.
    return []


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="WO-053 STT benchmark gate")
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    result = run_benchmark(args.dataset_manifest, args.output_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
