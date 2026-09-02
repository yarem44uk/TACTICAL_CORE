"""WO-040 — Benchmark-specific validation tests (§20).

These tests validate the benchmark harness (``run_benchmark.py``) without
requiring any engine runtime or model, so they are offline and deterministic.

They verify:

    * dataset manifest correctness;
    * audio readability (WAV masters open and report format);
    * ground-truth linkage (none available -> correctly empty);
    * candidate availability (both correctly reported absent offline);
    * metric calculation (WER / CER / callsign accuracy on known pairs);
    * offline execution (no network dependency in the harness).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import run_benchmark as rb  # noqa: E402


def test_probe_reports_candidates_absent():
    """Both recognised candidates are absent offline (WO-040 §8)."""
    probes = {p["engine"]: p for p in rb.probe_all()}
    assert set(probes) == {"faster_whisper", "vosk"}
    for p in probes.values():
        assert p["runtime_installed"] is False
        assert p["model_present"] is False


def test_manifest_builds_from_real_wav_roots():
    """The manifest is built from the discovered WAV master roots."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert len(rows) >= 30
    for r in rows:
        assert r["source"] == "radio"
        assert r["ground_truth"] == ""
        assert r["callsigns_present"] == ""
        assert r["usable"] in ("true", "false")
        assert r["sha256"] != ""


def test_manifest_format_compliance():
    """All discovered masters are mono 16-bit 8kHz (project-native)."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    for r in rows:
        assert (r["channels"], r["sampwidth"], r["sample_rate"]) == (1, 2, 8000)


def test_manifest_ground_truth_absent():
    """No manually verified ground truth exists (WO-040 §5)."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert all(r["ground_truth"] == "" for r in rows)


def test_audio_readability():
    """Every referenced WAV master opens and reports a positive duration."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    for r in rows:
        assert float(r["duration_s"]) > 0.0


def test_wer_perfect_match_zero():
    assert rb.wer("alpha bravo charlie", "alpha bravo charlie") == 0.0


def test_wer_one_substitution():
    assert rb.wer("alpha bravo charlie", "alpha bravo delta") == pytest.approx(1.0 / 3.0)


def test_wer_insertion():
    assert rb.wer("alpha bravo", "alpha extra bravo") == pytest.approx(1.0 / 2.0)


def test_cer_perfect_match_zero():
    assert rb.cer("alpha", "alpha") == 0.0


def test_cer_one_char_error():
    assert rb.cer("alpha", "alphi") == pytest.approx(1.0 / 5.0)


def test_callsign_accuracy_verbatim():
    """A callsign is correct only if it appears verbatim (ADR-014)."""
    hyp = "approach alpha one bravo, confirm"
    # "alpha one" appears verbatim as a contiguous token; "bravo" too.
    assert rb.callsign_accuracy(["alpha one", "bravo"], hyp) == pytest.approx(1.0)
    # "alpha1" is a distinct token from "alpha one" and does not appear.
    assert rb.callsign_accuracy(["alpha1", "bravo"], hyp) == pytest.approx(0.5)
    # "delta" does not appear at all.
    assert rb.callsign_accuracy(["delta"], hyp) == pytest.approx(0.0)


def test_callsign_accuracy_no_reference_is_nan():
    assert rb.callsign_accuracy([], "anything") != rb.callsign_accuracy([], "anything")


def test_harness_has_no_network_calls():
    """The harness source must not import urllib/socket/requests (offline §8)."""
    src = open(os.path.join(os.path.dirname(__file__), "run_benchmark.py")).read()
    for banned in ["import requests", "import urllib", "import socket", "urlopen", "http"]:
        assert banned not in src
