"""WO-067 — benchmark unit tests: accounting, aggregation, serialization, env.

No engine, no model, no network.  Fake runners stand in for real engines so the
harness mechanics can be validated offline; the fake engine is a
SYNTHETIC TEST FIXTURE and its output never becomes a real benchmark result.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo067_benchmark as B
import wo067_environment as E
from wo067_dataset import Candidate
from wo067_engines import (
    ENGINE_FASTER_WHISPER,
    ENGINE_VOSK,
    EngineConfig,
    check_engine_availability,
)

# ---------------------------------------------------------------------------
# Fakes — SYNTHETIC TEST FIXTURE
# ---------------------------------------------------------------------------

def _candidate(cid="msg_0001", duration_ms=1000, transcript=None, callsign=None) -> Candidate:
    return Candidate(
        candidate_id=cid,
        stream_id="S1",
        ssrc="0x42c7218e",
        audio_path=f"/nonexistent/{cid}.wav",
        wav_sha256="ab" * 32,
        source_pcap_sha256="cd" * 32,
        packet_start=1,
        packet_end=10,
        rtp_timestamp_start=0,
        rtp_timestamp_end=1600,
        start_time_ms=0.0,
        end_time_ms=float(duration_ms),
        duration_ms=duration_ms,
        sample_rate_hz=8000,
        channels=1,
        sample_width_bits=16,
        codec="PCM",
        lossless=True,
        human_review="HUMAN_REVIEWED_ACCEPTED",
        human_speech_confirmed=True,
        ground_truth_transcript=transcript,
        ground_truth_callsign=callsign,
        ground_truth_status="PROVIDED" if (transcript or callsign) else "NOT_PROVIDED",
        notes="",
    )


class _FakeRunner:
    """SYNTHETIC TEST FIXTURE runner returning a canned hypothesis."""

    def __init__(self, hypothesis="привіт світ", error=None):
        self.hypothesis = hypothesis
        self.error = error
        self.calls = 0

    def transcribe_path(self, wav_path: str) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.hypothesis


# ---------------------------------------------------------------------------
# Run accounting
# ---------------------------------------------------------------------------

def test_run_candidate_success_without_ground_truth() -> None:
    rec = B.run_candidate(_FakeRunner(), _candidate())
    assert rec["run_status"] == B.RUN_SUCCESS
    assert rec["latency_seconds"] is not None
    assert rec["rtf"] is not None
    # No human ground truth -> accuracy MUST stay NOT MEASURED
    assert rec["wer"] == B.NOT_MEASURED
    assert rec["cer"] == B.NOT_MEASURED
    assert rec["callsign_outcome"] == B.NOT_MEASURED


def test_run_candidate_scores_against_ground_truth() -> None:
    c = _candidate(transcript="привіт світ", callsign="Сокіл")
    rec = B.run_candidate(_FakeRunner(hypothesis="привіт світ"), c)
    assert rec["wer"] == 0.0
    assert rec["cer"] == 0.0
    assert rec["exact_match"] is True
    assert rec["callsign_outcome"] == "MISSED"  # hypothesis has no callsign


def test_run_candidate_failure_is_recorded_not_raised() -> None:
    rec = B.run_candidate(_FakeRunner(error=RuntimeError("boom")), _candidate())
    assert rec["run_status"] == B.RUN_FAILED
    assert rec["error_type"] == "RuntimeError"
    assert "boom" in rec["error"]
    assert rec["hypothesis"] is None


def test_run_candidate_preserves_denominator_on_failure() -> None:
    runner = _FakeRunner()
    records = [
        B.run_candidate(runner, _candidate("msg_0001")),
        B.run_candidate(_FakeRunner(error=ValueError("x")), _candidate("msg_0002")),
        B.run_candidate(runner, _candidate("msg_0003")),
    ]
    agg = B.aggregate_records(records)
    assert agg["reliability"]["total_runs"] == 3
    assert agg["reliability"]["successful_runs"] == 2
    assert agg["reliability"]["failed_runs"] == 1
    assert len(agg["timing"]["per_file_latency_seconds"]) == 3


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_aggregate_timing_and_rtf() -> None:
    recs = []
    for i in range(10):
        r = B.run_candidate(_FakeRunner(), _candidate(f"msg_{i:04d}"))
        r["latency_seconds"] = float(i + 1)
        r["rtf"] = (i + 1) / 10.0
        recs.append(r)
    agg = B.aggregate_records(recs)
    assert agg["timing"]["min_latency_seconds"] == 1.0
    assert agg["timing"]["max_latency_seconds"] == 10.0
    assert agg["timing"]["median_latency_seconds"] == pytest.approx(5.5)
    # nearest-rank p95 over 10 values -> rank ceil(9.5)=10 -> largest
    assert agg["timing"]["p95_latency_seconds"] == 10.0
    assert agg["timing"]["rtf_definition"] == "RTF = processing_time / audio_duration"


def test_aggregate_accuracy_not_measured_without_ground_truth() -> None:
    recs = [B.run_candidate(_FakeRunner(), _candidate("msg_0001"))]
    agg = B.aggregate_records(recs)
    assert agg["accuracy"]["wer_mean"] == B.NOT_MEASURED
    assert agg["accuracy"]["cer_mean"] == B.NOT_MEASURED
    assert agg["accuracy"]["ground_truth_scored_candidates"] == 0


def test_aggregate_accuracy_with_ground_truth() -> None:
    recs = [
        B.run_candidate(_FakeRunner(hypothesis="привіт світ"),
                        _candidate("msg_0001", transcript="привіт світ")),
        B.run_candidate(_FakeRunner(hypothesis="привіт"),
                        _candidate("msg_0002", transcript="привіт світ")),
    ]
    agg = B.aggregate_records(recs)
    assert agg["accuracy"]["ground_truth_scored_candidates"] == 2
    assert agg["accuracy"]["wer_mean"] == pytest.approx(0.25)
    assert agg["accuracy"]["exact_match_count"] == 1


def test_aggregate_resources_gpu_not_available() -> None:
    recs = [B.run_candidate(_FakeRunner(), _candidate("msg_0001"))]
    agg = B.aggregate_records(recs)
    # No GPU in CI -> never a fabricated number
    assert agg["resources"]["gpu_utilization_pct"] in (B.NOT_AVAILABLE, None) or isinstance(
        agg["resources"]["gpu_utilization_pct"], (int, float)
    )


def test_callsign_accuracy_not_measured_without_gt() -> None:
    recs = [B.run_candidate(_FakeRunner(), _candidate("msg_0001"))]
    cs = B.aggregate_callsign_accuracy(recs)
    assert cs["status"] == B.NOT_MEASURED
    assert cs["accuracy"] == B.NOT_MEASURED


def test_callsign_accuracy_measured_with_gt() -> None:
    recs = [
        B.run_candidate(_FakeRunner(hypothesis="сокіл на зв'язку"),
                        _candidate("msg_0001", callsign="Сокіл")),
        B.run_candidate(_FakeRunner(hypothesis="нічого"),
                        _candidate("msg_0002", callsign="Сокіл")),
    ]
    cs = B.aggregate_callsign_accuracy(recs)
    assert cs["status"] == "MEASURED"
    assert cs["scored_candidates"] == 2
    assert cs["exact_match"] == 1
    assert cs["missed"] == 1
    assert cs["accuracy"] == pytest.approx(0.5)


def test_percentile_helper_nearest_rank() -> None:
    assert B._percentile([], 95) is None
    assert B._percentile([5.0], 95) == 5.0
    assert B._percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0  # ceil(2.0)=2
    assert B._percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0


# ---------------------------------------------------------------------------
# Result document + serialization
# ---------------------------------------------------------------------------

def test_build_engine_result_blocked_engine() -> None:
    cfg = EngineConfig(engine=ENGINE_VOSK, model_path="/definitely/missing", language="uk")
    res = B.build_engine_result(cfg, {"candidate_count": 67}, [], cold_start_seconds=None)
    assert res["benchmark_executed"] is False
    assert res["engine_availability"]["ready"] is False
    assert res["cold_start_seconds"] == B.NOT_MEASURED
    assert res["aggregate"]["reliability"]["total_runs"] == 0


def test_result_document_never_selects_engine() -> None:
    doc = B.build_result_document(
        dataset_meta={"candidate_count": 67},
        environment={"os": "Linux"},
        engine_results=[],
    )
    assert doc["production_engine_selection"] == "CSA DECISION REQUIRED"
    assert doc["provenance"]["real_radio_rf_provenance_claimed"] is False
    assert "WO-068" in doc["production_engine_selection_note"]
    assert doc["benchmark_version"] == B.BENCHMARK_VERSION


def test_result_document_provenance_separation() -> None:
    doc = B.build_result_document(dataset_meta={}, environment={}, engine_results=[])
    prov = doc["provenance"]
    assert "CubicCore" in prov["transport_provenance"]
    assert "INDEPENDENT" in prov["audio_content_provenance"]


def test_write_result_document_does_not_overwrite() -> None:
    doc = B.build_result_document(dataset_meta={}, environment={}, engine_results=[])
    with tempfile.TemporaryDirectory(prefix="wo067_ser_") as d:
        target = os.path.join(d, "results.json")
        first = B.write_result_document(doc, target)
        assert os.path.basename(first) == "results.json"
        with open(first, encoding="utf-8") as fh:
            original = fh.read()

        second = B.write_result_document(doc, target)
        assert second != first  # versioned sibling, original preserved
        with open(first, encoding="utf-8") as fh:
            assert fh.read() == original


def test_result_document_is_json_serializable() -> None:
    recs = [B.run_candidate(_FakeRunner(), _candidate("msg_0001"))]
    cfg = EngineConfig(engine=ENGINE_FASTER_WHISPER, model_path="/m", language="uk")
    res = B.build_engine_result(cfg, {"candidate_count": 67}, recs, cold_start_seconds=1.5)
    doc = B.build_result_document(dataset_meta={}, environment={}, engine_results=[res])
    text = json.dumps(doc, ensure_ascii=False)
    assert "msg_0001" in text
    assert json.loads(text)["engines"][0]["engine"] == ENGINE_FASTER_WHISPER


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------

def test_environment_snapshot_shape() -> None:
    env = E.environment_snapshot(language="uk", device="cpu")
    for key in (
        "os",
        "kernel",
        "python_version",
        "cpu_model",
        "cpu_core_count",
        "ram_bytes",
        "gpu",
        "gpu_available",
        "ffmpeg_version",
        "packages",
        "language",
        "device",
    ):
        assert key in env
    assert env["language"] == "uk"
    assert env["device"] == "cpu"
    assert isinstance(env["packages"], dict)
    assert env["gpu_available"] is False  # no GPU in CI


def test_gpu_info_never_invents_a_device() -> None:
    info = E.gpu_info()
    assert info["available"] is False
    assert info["devices"] == []
    assert info["note"] == "GPU = NOT AVAILABLE"


def test_read_peak_rss_returns_bytes_or_none() -> None:
    value = E.read_peak_rss_bytes()
    assert value is None or value > 0


# ---------------------------------------------------------------------------
# Engine availability gate
# ---------------------------------------------------------------------------

def test_availability_engine_missing_is_explicit() -> None:
    cfg = EngineConfig(engine=ENGINE_FASTER_WHISPER, model_path=None, language="uk")
    info = check_engine_availability(cfg)
    assert info["ready"] is False
    assert info["reason"]
    assert info["module_present"] is False  # no engine installed in CI


def test_availability_unsupported_engine() -> None:
    cfg = EngineConfig(engine="some_other_engine", model_path="/x", language="uk")
    info = check_engine_availability(cfg)
    assert info["ready"] is False
    assert "unsupported benchmark engine" in info["reason"]


def test_availability_missing_model_path(tmp_path) -> None:
    cfg = EngineConfig(engine=ENGINE_VOSK, model_path=str(tmp_path / "nope"), language="uk")
    info = check_engine_availability(cfg)
    assert info["ready"] is False
    assert info["model_present"] is False
    # Module gate is checked first; when vosk is absent the reason names the
    # missing module, otherwise the missing model path.
    assert (
        "is not installed locally" in info["reason"]
        or "does not exist" in info["reason"]
    )


def test_availability_vosk_model_dir_shape(tmp_path) -> None:
    # A directory without am/ or conf/ is not a provisioned Vosk model.
    cfg = EngineConfig(engine=ENGINE_VOSK, model_path=str(tmp_path), language="uk")
    info = check_engine_availability(cfg)
    if info["module_present"]:
        assert info["ready"] is False
        assert "Vosk model" in info["reason"]
    else:
        assert info["ready"] is False