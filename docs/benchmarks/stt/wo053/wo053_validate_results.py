"""WO-053 — Validate the machine-readable benchmark result (schema + invariants).

The validator is deterministic and stdlib-only.  It confirms the result artifact
contains the fields needed to reconstruct candidate / dataset / input /
configuration / accuracy / latency / RTF / resource observations /
success-failure / environment / timestamp, and that no production selection was
made.

Author: Tactical Core Engineering Team
"""

from __future__ import annotations

import json
import os

REQUIRED_TOP = [
    "benchmark",
    "timestamp",
    "environment",
    "dataset",
    "candidates",
    "benchmark_executed",
    "execution_metadata",
    "production_selection_made",
]

REQUIRED_CANDIDATE = [
    "candidate",
    "available",
    "status",
    "availability_reason",
    "runs",
]

REQUIRED_DATASET = ["manifest_path", "row_count", "inputs", "speech_rows"]

REQUIRED_INPUT = [
    "audio_id",
    "audio_path",
    "sha256",
    "duration_seconds",
    "sample_rate",
    "source_type",
    "real_transmission",
    "speech_present",
    "transcript",
]

REQUIRED_ENV = ["python_version", "platform", "machine", "cpu_count"]


def validate_results(path: str) -> dict:
    errors: list[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": [f"invalid JSON: {e}"]}

    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"missing top-level key: {key}")

    if "production_selection_made" in data and data["production_selection_made"] is not False:
        errors.append("production_selection_made must be false (WO-053 makes no selection)")

    if "dataset" in data:
        ds = data["dataset"]
        for key in REQUIRED_DATASET:
            if key not in ds:
                errors.append(f"dataset missing key: {key}")
        for inp in ds.get("inputs", []):
            for key in REQUIRED_INPUT:
                if key not in inp:
                    errors.append(f"input missing key: {key}")

    if "candidates" in data:
        for cand in data["candidates"]:
            for key in REQUIRED_CANDIDATE:
                if key not in cand:
                    errors.append(f"candidate {cand.get('candidate')} missing key: {key}")
            if cand.get("available") and cand.get("status") != "AVAILABLE":
                errors.append(f"candidate {cand.get('candidate')} available but status != AVAILABLE")
            if not cand.get("available") and cand.get("status") != "NOT_AVAILABLE":
                errors.append(f"candidate {cand.get('candidate')} not available but status != NOT_AVAILABLE")
            if not cand.get("available") and not cand.get("availability_reason"):
                errors.append(f"candidate {cand.get('candidate')} NOT_AVAILABLE without reason")

    if "environment" in data:
        for key in REQUIRED_ENV:
            if key not in data["environment"]:
                errors.append(f"environment missing key: {key}")

    return {"valid": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Validate WO-053 benchmark results")
    parser.add_argument("--results", required=True)
    args = parser.parse_args(argv)
    res = validate_results(args.results)
    print(json.dumps(res, indent=2))
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
