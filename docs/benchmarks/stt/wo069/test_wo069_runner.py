"""WO-069 — benchmark unit tests: engine execution, failure handling, serialization.

These tests never load a real model and never transcribe real audio.  They
exercise the runner's process isolation, failure classification and ledger
replay mechanics using throwaway stand-in workers (SYNTHETIC TEST FIXTURE).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo069_runner as R
from wo069_dataset import DatasetRecord

PROVISIONED_VENV = "/opt/data/wo067_runtime_gate_v1/venv/bin/python"
PROVISIONED_VOSK_MODEL = (
    "/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/vosk_uk/vosk-model-uk-v3"
)


def _records(count: int = 2) -> list[DatasetRecord]:
    return [
        DatasetRecord(
            message_id=f"msg_{i:04d}",
            stream_id="S1",
            wav_path=f"/fixture/msg_{i:04d}.wav",
            duration_seconds=1.0,
            dataset_sha256="0" * 64,
        )
        for i in range(1, count + 1)
    ]


def _fake_worker(tmpdir: str, body: str) -> str:
    """Write a throwaway stand-in worker and return its path."""
    path = os.path.join(tmpdir, "fake_worker.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(body))
    return path


def _spec(tmpdir: str, **overrides) -> R.EngineSpec:
    spec = R.EngineSpec(
        engine="vosk",
        display_name="fixture engine",
        model_path=tmpdir,
        venv_python=sys.executable,
        language="uk",
        sample_rate_policy="fixture",
    )
    for key, value in overrides.items():
        setattr(spec, key, value)
    return spec


# --- availability ------------------------------------------------------------


def test_missing_interpreter_is_reported_unavailable(tmp_path):
    records = _records(2)
    spec = _spec(str(tmp_path), venv_python="/nonexistent/python")
    result = R.run_engine(spec, records, workdir=str(tmp_path))
    assert result["engine_status"] == R.ENGINE_UNAVAILABLE
    assert "provisioned interpreter not found" in result["failure_reason"]
    assert all(r["status"] == "ENGINE_UNAVAILABLE" for r in result["records"])
    assert all(r["error"] for r in result["records"])


def test_missing_model_is_reported_unavailable(tmp_path):
    records = _records(1)
    spec = _spec(str(tmp_path), model_path=str(tmp_path / "absent-model"))
    result = R.run_engine(spec, records, workdir=str(tmp_path))
    assert result["engine_status"] == R.ENGINE_UNAVAILABLE
    assert "local model path missing" in result["failure_reason"]


def test_absent_engine_module_is_reported_unavailable(tmp_path):
    spec = _spec(str(tmp_path))
    availability = R.check_availability(spec)
    assert availability["ready"] is False
    assert "not importable" in availability["reason"]


# --- execution mechanics (stand-in workers) ---------------------------------


def _run_with_fake_worker(tmp_path, monkeypatch, body: str, records=None, **kwargs):
    records = records or _records(2)
    fake = _fake_worker(str(tmp_path), body)
    monkeypatch.setattr(R, "WORKER_PATH", fake)
    # Availability probing is exercised separately; here we exercise execution.
    monkeypatch.setattr(
        R,
        "check_availability",
        lambda spec: {
            "engine": spec.engine, "ready": True, "reason": "fixture",
            "interpreter_present": True, "module_present": True,
            "model_present": True, "model_path": spec.model_path,
        },
    )
    spec = _spec(str(tmp_path))
    return R.run_engine(spec, records, workdir=str(tmp_path), **kwargs)


def test_successful_session_replays_ledger(tmp_path, monkeypatch):
    body = """
        import argparse, json, os
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        jobs = json.load(open(args.jobs))
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "engine", "model_load_status": "READY",
                                 "cold_start_ms": 12.5, "error": None}) + "\\n")
            for r in jobs["records"]:
                fh.write(json.dumps({"type": "file", "message_id": r["message_id"],
                                     "wav_path": r["wav_path"], "status": "SUCCESS",
                                     "text": "тест", "latency_ms": 100.0, "rtf": 0.1,
                                     "cpu_user_s": 0.01, "cpu_sys_s": 0.0,
                                     "peak_rss_kb": 1234, "error": None}) + "\\n")
            fh.write(json.dumps({"type": "summary", "processed": len(jobs["records"])}) + "\\n")
    """
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    assert result["engine_status"] == R.ENGINE_COMPLETED
    assert result["model_load_status"] == "READY"
    assert result["cold_start_ms"] == 12.5
    assert [r["status"] for r in result["records"]] == ["SUCCESS", "SUCCESS"]
    assert result["records"][0]["text"] == "тест"


def test_model_load_failure_is_recorded(tmp_path, monkeypatch):
    body = """
        import argparse, json
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "engine", "model_load_status": "FAILED",
                                 "cold_start_ms": 3.0,
                                 "error": "ModelLoadError: boom"}) + "\\n")
        raise SystemExit(3)
    """
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    assert result["engine_status"] == R.ENGINE_FAILED
    assert "model load failed" in result["failure_reason"]
    assert all(r["status"] == "FAILED" for r in result["records"])


def test_partial_ledger_survives_crash(tmp_path, monkeypatch):
    body = """
        import argparse, json
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        jobs = json.load(open(args.jobs))
        first = jobs["records"][0]
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "engine", "model_load_status": "READY",
                                 "cold_start_ms": 1.0, "error": None}) + "\\n")
            fh.write(json.dumps({"type": "file", "message_id": first["message_id"],
                                 "wav_path": first["wav_path"], "status": "SUCCESS",
                                 "text": "ок", "latency_ms": 5.0, "rtf": 0.05,
                                 "error": None}) + "\\n")
        raise SystemExit(1)
    """
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    assert result["engine_status"] == R.ENGINE_FAILED
    assert result["records"][0]["status"] == "SUCCESS"
    assert result["records"][1]["status"] == "FAILED"
    assert result["records"][1]["error"]


def test_engine_session_timeout_is_recorded(tmp_path, monkeypatch):
    body = """
        import argparse, time
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        time.sleep(30)
    """
    result = _run_with_fake_worker(
        tmp_path, monkeypatch, body, timeout_seconds=1.0
    )
    assert result["engine_status"] == R.ENGINE_TIMEOUT
    assert all(r["status"] == "TIMEOUT" for r in result["records"])


def test_signal_death_is_reported_with_oom_evidence(tmp_path, monkeypatch):
    body = """
        import argparse, os, signal
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        os.kill(os.getpid(), signal.SIGKILL)
    """
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    assert result["engine_status"] == R.ENGINE_FAILED
    assert "SIGKILL" in result["oom_evidence"]
    assert all(r["status"] == "FAILED" for r in result["records"])


# --- deterministic result schema --------------------------------------------


def test_per_file_ledger_schema_is_deterministic(tmp_path, monkeypatch):
    body = """
        import argparse, json
        p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--jobs")
        args, _ = p.parse_known_args()
        jobs = json.load(open(args.jobs))
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "engine", "model_load_status": "READY",
                                 "cold_start_ms": 1.0, "error": None}) + "\\n")
            for r in jobs["records"]:
                fh.write(json.dumps({"type": "file", "message_id": r["message_id"],
                                     "wav_path": r["wav_path"], "status": "SUCCESS",
                                     "text": "", "latency_ms": 1.0, "rtf": 0.01,
                                     "error": None}) + "\\n")
            fh.write(json.dumps({"type": "summary", "processed": 2}) + "\\n")
    """
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    expected_keys = {
        "message_id", "wav_path", "audio_duration_seconds", "status", "text",
        "latency_ms", "rtf", "cpu_user_s", "cpu_sys_s", "peak_rss_kb", "error",
        "error_type",
    }
    for record in result["records"]:
        assert expected_keys <= set(record.keys())


def test_engine_result_keys_are_stable(tmp_path, monkeypatch):
    body = "import sys; sys.exit(0)"
    result = _run_with_fake_worker(tmp_path, monkeypatch, body)
    for key in ("engine", "engine_status", "engine_availability", "configuration",
                "failure_reason", "exit_code", "model_load_status", "cold_start_ms",
                "records", "oom_evidence"):
        assert key in result


# --- real provisioned environment (skipped when absent) ---------------------


@pytest.mark.skipif(
    not (os.path.exists(PROVISIONED_VENV) and os.path.isdir(PROVISIONED_VOSK_MODEL)),
    reason="provisioned engine venv/model not present on this host",
)
def test_provisioned_vosk_availability_is_detected():
    spec = R.EngineSpec(
        engine="vosk", display_name="vosk", model_path=PROVISIONED_VOSK_MODEL,
        venv_python=PROVISIONED_VENV, language="uk",
    )
    availability = R.check_availability(spec)
    assert availability["ready"] is True
    assert availability["module_present"] is True
