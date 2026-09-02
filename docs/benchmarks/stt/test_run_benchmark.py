"""WO-040 / WO-040-CORR — Benchmark-specific validation tests (§20/§21).

These tests validate the benchmark harness (``run_benchmark.py``) without
requiring any engine runtime or model, so they are offline and deterministic.
Fake runners are used where a real engine is absent; a fake runner is never
treated as real benchmark evidence.

They verify:

    * dataset manifest correctness and structural validity (NOT the ADR-014 gate);
    * audio readability (WAV masters open and report format);
    * ground-truth linkage (none available -> correctly empty);
    * candidate availability (both correctly reported absent offline);
    * metric calculation (WER / CER / callsign accuracy on known pairs);
    * latency / RTF / CPU / RAM / GPU / VRAM measurement;
    * failure / timeout / NOT_AVAILABLE accounting and denominator logic;
    * cold / warm distinction;
    * aggregation denominator rules;
    * results CSV LF output and stable columns;
    * candidate restriction;
    * ADR-014 mandatory gate (correctly NOT satisfied against the current fixtures);
    * offline execution (no network dependency in the harness).

Author: Tactical Core Engineering Team
Version: 1.1
"""

from __future__ import annotations

import csv
import os
import sys
import time
import wave

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import run_benchmark as rb  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def _make_wav(path: str, nframes: int = 800, sample_rate: int = 8000) -> str:
    """Write a minimal valid mono 16-bit 8 kHz WAV master (constant amplitude)."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for _ in range(nframes):
            frames += (1000).to_bytes(2, "little", signed=True)
        wf.writeframes(bytes(frames))
    return path


def _manifest_row(
    audio_id: str,
    wav_path: str,
    ground_truth: str = "",
    callsigns: str = "",
    provenance: str = "real radio transmission",
) -> dict:
    return {
        "audio_id": audio_id,
        "wav_path": wav_path,
        "ground_truth": ground_truth,
        "callsigns_present": callsigns,
        "usable": "true",
        "provenance": provenance,
        "real_transmission": "true" if provenance != "fixture" else "false",
    }


def _available_config(candidate: str = "faster_whisper") -> rb.CandidateConfig:
    return rb.CandidateConfig(
        candidate=candidate,
        runtime_installed=True,
        runtime_version="test-0.0",
        model_present=True,
        model_path="/tmp/test-model",
        language="uk",
        device="cpu",
        config={"language": "uk", "device": "cpu"},
        available=True,
        availability_reason="",
    )


def _fake_success(audio_path, audio_bytes, sample_rate, run_phase, config) -> str:
    return "alpha one bravo"


def _fake_failure(audio_path, audio_bytes, sample_rate, run_phase, config) -> str:
    raise RuntimeError("boom")


def _fake_timeout(audio_path, audio_bytes, sample_rate, run_phase, config) -> str:
    time.sleep(5)
    return "never returned"


# ---------------------------------------------------------------------------
# Candidate probe.
# ---------------------------------------------------------------------------
def test_probe_reports_candidates_absent():
    """Both recognised candidates are absent offline (WO-040 §8)."""
    probes = {p["engine"]: p for p in rb.probe_all()}
    assert set(probes) == {"faster_whisper", "vosk"}
    for p in probes.values():
        assert p["runtime_installed"] is False
        assert p["model_present"] is False


# ---------------------------------------------------------------------------
# Manifest: structural validity, NOT the ADR-014 gate.
# ---------------------------------------------------------------------------
def test_manifest_structure_is_valid():
    """The manifest is structurally valid (tooling invariant, not the gate).

    This asserts only structural properties of the tooling output.  It must NOT
    be read as the ADR-014 50-real-transmission gate, which is tested separately
    in ``test_adr014_dataset_gate``.
    """
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert isinstance(rows, list) and len(rows) >= 1
    required = {
        "audio_id", "wav_path", "source", "duration_s", "channels", "sampwidth",
        "sample_rate", "sha256", "ground_truth", "callsigns_present", "provenance",
        "usable", "real_transmission",
    }
    for r in rows:
        assert required.issubset(r.keys())
        assert r["source"] == "radio"
        assert r["sha256"] != ""
        assert r["usable"] in ("true", "false")
        assert r["real_transmission"] in ("true", "false")
    audio_ids = [r["audio_id"] for r in rows]
    assert len(audio_ids) == len(set(audio_ids)), "audio_id must be unique"


def test_manifest_format_compliance():
    """All discovered masters are mono 16-bit 8kHz (project-native)."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    for r in rows:
        assert (r["channels"], r["sampwidth"], r["sample_rate"]) == (1, 2, 8000)


def test_manifest_ground_truth_absent():
    """No manually verified ground truth exists (WO-040 §5)."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert all(r["ground_truth"] == "" for r in rows)


def test_manifest_fixtures_not_relabeled_real():
    """The WO-039 fixtures must NOT be relabelled as real radio (WO-040-CORR §18)."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert all(r["real_transmission"] == "false" for r in rows)
    assert all(rb.is_real_radio_transmission(r) is False for r in rows)
    assert all(rb.has_verified_ground_truth(r) is False for r in rows)


def test_audio_readability():
    """Every referenced WAV master opens and reports a positive duration."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    for r in rows:
        assert float(r["duration_s"]) > 0.0


# ---------------------------------------------------------------------------
# Recognition metrics.
# ---------------------------------------------------------------------------
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
    assert rb.callsign_accuracy(["alpha one", "bravo"], hyp) == pytest.approx(1.0)
    assert rb.callsign_accuracy(["alpha1", "bravo"], hyp) == pytest.approx(0.5)
    assert rb.callsign_accuracy(["delta"], hyp) == pytest.approx(0.0)


def test_callsign_accuracy_word_boundary():
    """Word boundaries matter: alpha must not match alphabet or alpha1."""
    assert rb.callsign_accuracy(["alpha"], "the alphabet") == 0.0
    assert rb.callsign_accuracy(["alpha"], "alpha1 channel") == 0.0
    assert rb.callsign_accuracy(["alpha"], "standby alpha, over") == pytest.approx(1.0)


def test_callsign_accuracy_no_reference_is_nan():
    assert rb.callsign_accuracy([], "anything") != rb.callsign_accuracy([], "anything")


# ---------------------------------------------------------------------------
# Latency / RTF / resources.
# ---------------------------------------------------------------------------
def test_latency_and_rtf_measured(tmp_path):
    wav = _make_wav(str(tmp_path / "a.wav"))
    row = _manifest_row("a", wav, ground_truth="alpha one bravo", callsigns="alpha one, bravo")
    results = rb.execute_benchmark(
        [row], "faster_whisper", runner=_fake_success,
        config=_available_config(), run_phase=rb.PHASE_WARM,
    )
    assert len(results) == 1
    r = results[0]
    assert r.status == rb.STATUS_SUCCESS
    assert r.hypothesis == "alpha one bravo"
    assert r.latency_seconds is not None and r.latency_seconds >= 0.0
    assert r.rtf is not None and r.rtf >= 0.0
    duration = r.audio_duration_seconds
    assert duration is not None
    assert duration == pytest.approx(0.1, rel=0.05)
    # RTF = latency / audio_duration
    assert r.rtf == pytest.approx(r.latency_seconds / duration, rel=1e-6)


def test_resource_measurements_available_or_na(tmp_path):
    wav = _make_wav(str(tmp_path / "b.wav"))
    row = _manifest_row("b", wav, ground_truth="alpha", callsigns="alpha")
    results = rb.execute_benchmark(
        [row], "vosk", runner=_fake_success,
        config=_available_config("vosk"), run_phase=rb.PHASE_WARM,
    )
    r = results[0]
    assert r.cpu_usage is not None and r.cpu_usage >= 0.0
    # RAM is a documented RSS statistic; it must be a non-negative number when
    # available and never fabricated as 0 when unavailable.
    assert r.ram_usage is None or r.ram_usage >= 0.0
    # GPU/VRAM are observational and reported N/A when no GPU is present.
    assert r.gpu_usage in ("N/A",) or (r.gpu_usage is not None and r.gpu_usage != "")
    assert r.vram_usage in ("N/A",) or (r.vram_usage is not None and r.vram_usage != "")


def test_na_resources_not_zero():
    """An unavailable measurement must not be reported as 0."""
    gpu, vram = rb._gpu_usage()
    assert gpu == "N/A" or gpu != "0"
    assert vram == "N/A" or vram != "0"


# ---------------------------------------------------------------------------
# Failure / timeout / NOT_AVAILABLE accounting.
# ---------------------------------------------------------------------------
def test_failure_accounting(tmp_path):
    wav = _make_wav(str(tmp_path / "f.wav"))
    row = _manifest_row("f", wav, ground_truth="alpha", callsigns="alpha")
    results = rb.execute_benchmark(
        [row], "faster_whisper", runner=_fake_failure,
        config=_available_config(), run_phase=rb.PHASE_WARM,
    )
    r = results[0]
    assert r.status == rb.STATUS_FAILURE
    assert r.error != ""
    assert "boom" in r.error
    assert r.timeout is False


def test_timeout_accounting(tmp_path):
    wav = _make_wav(str(tmp_path / "t.wav"))
    row = _manifest_row("t", wav, ground_truth="alpha", callsigns="alpha")
    results = rb.execute_benchmark(
        [row], "faster_whisper", runner=_fake_timeout,
        config=_available_config(), timeout_seconds=0.1, run_phase=rb.PHASE_WARM,
    )
    r = results[0]
    assert r.status == rb.STATUS_TIMEOUT
    assert r.timeout is True
    assert r.error != ""


def test_not_available_state(tmp_path):
    wav = _make_wav(str(tmp_path / "n.wav"))
    row = _manifest_row("n", wav, ground_truth="alpha", callsigns="alpha")
    cfg = _available_config()
    cfg.available = False
    cfg.availability_reason = "runtime not installed"
    results = rb.execute_benchmark(
        [row], "faster_whisper", config=cfg, run_phase=rb.PHASE_WARM,
    )
    r = results[0]
    assert r.status == rb.STATUS_NOT_AVAILABLE
    assert "runtime not installed" in r.error


def test_aggregate_denominator_includes_all(tmp_path):
    """Failures/timeouts/NOT_AVAILABLE must remain in the denominator."""
    wav = _make_wav(str(tmp_path / "d.wav"))
    rows = [
        _manifest_row("s1", wav, ground_truth="alpha", callsigns="alpha"),
        _manifest_row("s2", wav, ground_truth="bravo", callsigns="bravo"),
        _manifest_row("f1", wav, ground_truth="charlie", callsigns="charlie"),
    ]
    cfg = _available_config()
    # s1/s2 success, f1 failure
    results = []
    for i, row in enumerate(rows):
        runner = _fake_failure if row["audio_id"] == "f1" else _fake_success
        results += rb.execute_benchmark([row], "faster_whisper", runner=runner,
                                        config=cfg, run_phase=rb.PHASE_WARM)
    agg = rb.aggregate_results(results)
    assert agg["total_inputs"] == 3
    assert agg["successful_inputs"] == 2
    assert agg["failed_inputs"] == 1
    assert agg["timed_out_inputs"] == 0
    assert agg["successful_inputs"] + agg["failed_inputs"] + agg["timed_out_inputs"] == agg["total_inputs"]
    assert agg["failure_rate"] == pytest.approx(1.0 / 3.0)
    assert agg["timeout_rate"] == pytest.approx(0.0)


def test_aggregate_denominator_includes_timeouts_and_na(tmp_path):
    wav = _make_wav(str(tmp_path / "e.wav"))
    cfg = _available_config()
    rows = [
        _manifest_row("ok", wav, ground_truth="alpha", callsigns="alpha"),
        _manifest_row("to", wav, ground_truth="bravo", callsigns="bravo"),
    ]
    results = []
    results += rb.execute_benchmark([rows[0]], "faster_whisper", runner=_fake_success,
                                    config=cfg, run_phase=rb.PHASE_WARM)
    results += rb.execute_benchmark([rows[1]], "faster_whisper", runner=_fake_timeout,
                                    config=cfg, timeout_seconds=0.1, run_phase=rb.PHASE_WARM)
    na_cfg = _available_config()
    na_cfg.available = False
    na_cfg.availability_reason = "no model"
    results += rb.execute_benchmark([rows[1]], "vosk", config=na_cfg, run_phase=rb.PHASE_WARM)
    agg = rb.aggregate_results(results)
    assert agg["total_inputs"] == 3
    assert agg["successful_inputs"] == 1
    assert agg["failed_inputs"] == 1  # NOT_AVAILABLE counts as a failure
    assert agg["timed_out_inputs"] == 1
    assert agg["successful_inputs"] + agg["failed_inputs"] + agg["timed_out_inputs"] == 3


def test_aggregate_recognition_denominator(tmp_path):
    """WER/CER/callsign aggregates use only records with a valid ref+hypothesis."""
    wav = _make_wav(str(tmp_path / "r.wav"))
    cfg = _available_config()
    rows = [
        _manifest_row("a", wav, ground_truth="alpha one", callsigns="alpha one"),
        _manifest_row("b", wav, ground_truth="bravo two", callsigns="bravo two"),
    ]
    results = rb.execute_benchmark(rows, "faster_whisper", runner=_fake_success,
                                   config=cfg, run_phase=rb.PHASE_WARM)
    agg = rb.aggregate_results(results)
    assert agg["mean_wer"] is not None and agg["mean_wer"] >= 0.0
    assert agg["mean_cer"] is not None and agg["mean_cer"] >= 0.0
    assert agg["callsign_accuracy"] is not None


def test_cold_warm_distinction(tmp_path):
    """run_phase must be recorded separately for cold and warm runs."""
    wav = _make_wav(str(tmp_path / "c.wav"))
    row = _manifest_row("c", wav, ground_truth="alpha", callsigns="alpha")
    cold = rb.execute_benchmark([row], "faster_whisper", runner=_fake_success,
                                config=_available_config(), run_phase=rb.PHASE_COLD)
    warm = rb.execute_benchmark([row], "faster_whisper", runner=_fake_success,
                                config=_available_config(), run_phase=rb.PHASE_WARM)
    assert cold[0].run_phase == rb.PHASE_COLD
    assert warm[0].run_phase == rb.PHASE_WARM


# ---------------------------------------------------------------------------
# Results CSV.
# ---------------------------------------------------------------------------
def test_results_csv_lf_and_columns(tmp_path):
    """results.csv uses LF line endings and a stable, complete column order."""
    wav = _make_wav(str(tmp_path / "x.wav"))
    row = _manifest_row("x", wav, ground_truth="alpha", callsigns="alpha")
    results = rb.execute_benchmark([row], "faster_whisper", runner=_fake_success,
                                   config=_available_config(), run_phase=rb.PHASE_WARM)
    out = str(tmp_path / "results.csv")
    rb.write_results_csv(results, out)
    raw = open(out, "rb").read()
    assert b"\r" not in raw, "results.csv must use LF line endings, not CRLF"
    with open(out, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == rb.RESULT_CSV_FIELDS
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["candidate"] == "faster_whisper"
    assert rows[0]["status"] == rb.STATUS_SUCCESS
    assert rows[0]["timeout"] == "false"
    assert rows[0]["failure"] == "false"
    assert rows[0]["gpu_usage"] == "N/A"


# ---------------------------------------------------------------------------
# Candidate restriction.
# ---------------------------------------------------------------------------
def test_candidate_restriction():
    """The harness must refuse candidates outside {faster_whisper, vosk}."""
    with pytest.raises(ValueError):
        rb.get_candidate_runner("whisper")
    with pytest.raises(ValueError):
        rb.execute_benchmark([], "whisper")
    with pytest.raises(ValueError):
        rb.get_candidate_config("whisper")


def test_candidate_runners_callable():
    """Both recognised candidates expose a benchmark-only runner."""
    for cand in rb.CANDIDATES:
        assert callable(rb.get_candidate_runner(cand))


# ---------------------------------------------------------------------------
# ADR-014 mandatory gate.
# ---------------------------------------------------------------------------
def test_adr014_dataset_gate():
    """Against the current fixtures the ADR-014 gate is NOT satisfied.

    There are 0 real, verified radio transmissions, so the mandatory >= 50 gate
    must be reported as NOT satisfied.  This test must NOT falsely pass as if
    the gate were met.
    """
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    gate = rb.adr014_gate(rows)
    assert gate["real_transmissions"] == 0
    assert gate["verified_transmissions"] == 0
    assert gate["minimum_required"] == 50
    assert gate["gate_satisfied"] is False


def test_adr014_gate_function_logic():
    """The gate function counts real+verified correctly (pure logic, not data).

    This is a logic test of the counting function only.  It is NOT benchmark
    evidence and does NOT satisfy the gate with real data.
    """
    rows = []
    for i in range(60):
        rows.append(_manifest_row(
            f"real{i}", "/tmp/x.wav", ground_truth="alpha", callsigns="alpha",
            provenance="real radio transmission",
        ))
    rows.append(_manifest_row("fixture", "/tmp/y.wav", provenance="fixture"))
    gate = rb.adr014_gate(rows)
    assert gate["real_transmissions"] == 60
    assert gate["verified_transmissions"] == 60
    assert gate["gate_satisfied"] is True


def test_manifest_count_not_a_gate():
    """The fixture count (36) is not itself the ADR-014 gate threshold."""
    rows = rb.build_manifest(rb.DEFAULT_WAV_ROOTS)
    assert len(rows) < rb.ADR014_MIN_REAL_TRANSMISSIONS
    assert len(rows) != rb.ADR014_MIN_REAL_TRANSMISSIONS


# ---------------------------------------------------------------------------
# Offline guarantee.
# ---------------------------------------------------------------------------
def test_harness_has_no_network_calls():
    """The harness source must not import urllib/socket/requests (offline §8)."""
    src = open(os.path.join(os.path.dirname(__file__), "run_benchmark.py")).read()
    for banned in ["import requests", "import urllib", "import socket", "urlopen", "http"]:
        assert banned not in src
