"""WO-053 — Tests for the benchmark runner mechanics.

These tests validate the RUNNER MECHANICS only: candidate discovery accounting,
NOT_AVAILABLE honesty, machine-readable schema, offline/no-network invariant,
determinism, and reproducibility.  No real STT accuracy is claimed and no engine
is invoked.

Author: Tactical Core Engineering Team
"""

import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from wo053_benchmark import (  # noqa: E402
    SUPPORTED_ENGINES,
    discover_candidate,
    discover_candidates,
    run_benchmark,
)
from wo053_validate_results import validate_results  # noqa: E402
from wo053_dataset import (  # noqa: E402
    generate_synthetic_audio,
    build_manifest,
)


FORBIDDEN_NETWORK = [
    "import requests",
    "import urllib",
    "from urllib",
    "import httpx",
    "from httpx",
    "import socket",
    "urlopen",
    "import http",
    "from http",
]


def _make_manifest():
    d = tempfile.mkdtemp(prefix="wo053_bm_")
    generate_synthetic_audio(d)
    m = os.path.join(d, "manifest.csv")
    build_manifest(d, m)
    return d, m


def test_supported_engines_are_recognised_set():
    assert set(SUPPORTED_ENGINES) == {"faster_whisper", "vosk"}


def test_discover_candidate_reports_not_available_with_reason():
    rec = discover_candidate("definitely_not_a_real_engine_xyz")
    assert rec["available"] is False
    assert rec["status"] == "NOT_AVAILABLE"
    assert rec["availability_reason"]


def test_discover_candidate_schema():
    rec = discover_candidate("faster_whisper")
    for key in ["candidate", "available", "status", "version", "model",
                "model_path", "device", "compute_type", "language", "availability_reason"]:
        assert key in rec


def test_discover_candidates_returns_list():
    cands = discover_candidates()
    assert isinstance(cands, list)
    assert len(cands) == len(SUPPORTED_ENGINES)


def test_run_benchmark_produces_valid_schema():
    d, m = _make_manifest()
    out = os.path.join(d, "results.json")
    run_benchmark(m, out)
    res = validate_results(out)
    assert res["valid"] is True
    assert res["errors"] == []


def test_run_benchmark_no_production_selection_and_not_executed():
    d, m = _make_manifest()
    out = os.path.join(d, "results.json")
    run_benchmark(m, out)
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["production_selection_made"] is False
    # On this host no engine is provisioned, so the benchmark is not executed.
    assert data["benchmark_executed"] is False
    for cand in data["candidates"]:
        assert cand["status"] in ("AVAILABLE", "NOT_AVAILABLE")
        if not cand["available"]:
            assert cand["availability_reason"]


def test_results_contains_dataset_and_inputs():
    d, m = _make_manifest()
    out = os.path.join(d, "results.json")
    run_benchmark(m, out)
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["dataset"]["row_count"] >= 4
    assert len(data["dataset"]["inputs"]) == data["dataset"]["row_count"]
    assert data["dataset"]["speech_rows"] == 0


def test_results_reproducible_except_timestamp_and_runtime():
    d, m = _make_manifest()
    o1 = os.path.join(d, "r1.json")
    o2 = os.path.join(d, "r2.json")
    run_benchmark(m, o1)
    run_benchmark(m, o2)
    with open(o1, encoding="utf-8") as fh:
        a = json.load(fh)
    with open(o2, encoding="utf-8") as fh:
        b = json.load(fh)
    # Strip nondeterministic runtime-only fields.
    for obj in (a, b):
        obj.pop("timestamp", None)
        obj["execution_metadata"].pop("wall_time_seconds", None)
        obj["execution_metadata"].pop("cpu_seconds", None)
        obj["environment"].pop("process_peak_rss_kb", None)
    assert a == b


def test_validate_results_detects_missing_field():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"benchmark": "x"}, fh)
        path = fh.name
    res = validate_results(path)
    assert res["valid"] is False
    assert res["errors"]
    os.unlink(path)


def _tooling_sources():
    """Return the non-test wo053 tooling .py files (excludes test_*.py)."""
    here = os.path.dirname(__file__)
    return [
        os.path.join(here, fn)
        for fn in sorted(os.listdir(here))
        if fn.endswith(".py") and fn.startswith("wo053_")
    ]


def test_no_network_imports_in_wo053_source():
    """The benchmark tooling must stay offline (mirrors WO-040 invariant)."""
    offenders = []
    for path in _tooling_sources():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for tok in FORBIDDEN_NETWORK:
            if tok in src:
                offenders.append((os.path.basename(path), tok))
    assert offenders == [], f"network-import offenders: {offenders}"


def test_no_download_or_model_fetch_in_source():
    download_fns = [
        "urlretrieve",
        "hf_hub_download",
        "snapshot_download",
        "requests.get",
        "urlopen",
        "urllib.request",
    ]
    for path in _tooling_sources():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "huggingface" not in src.lower(), f"huggingface ref in {os.path.basename(path)}"
        assert not re.search(r"https?://", src), f"URL in {os.path.basename(path)}"
        for tok in download_fns:
            assert tok not in src, f"download call {tok!r} in {os.path.basename(path)}"
