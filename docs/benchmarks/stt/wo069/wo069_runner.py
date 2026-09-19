"""WO-069 — Benchmark runner: drive real engines through isolated processes.

The runner is the parent side of the benchmark.  Each engine runs in its own
subprocess, in the *provisioned* engine virtualenv, via
``wo069_engine_worker.py``.  Isolation is deliberate:

  * a model-load failure, crash, OOM-kill or hang affects only that engine;
  * the parent captures the real exit code and stderr tail as evidence;
  * no engine exception can terminate the harness or erase the ledger.

Fail-closed accounting: an engine that cannot run is reported
``engine_status = FAILED`` with the actual reason.  A file that never returns is
``TIMEOUT``.  Nothing is estimated, extrapolated or substituted.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VENV_PYTHON = "/opt/data/wo067_runtime_gate_v1/venv/bin/python"
WORKER_PATH = os.path.join(_HERE, "wo069_engine_worker.py")

# engine session outcomes
ENGINE_COMPLETED = "COMPLETED"
ENGINE_FAILED = "FAILED"
ENGINE_TIMEOUT = "TIMEOUT"
ENGINE_UNAVAILABLE = "UNAVAILABLE"
ENGINE_NOT_EXECUTED = "NOT_EXECUTED"

NOT_MEASURED = "NOT_MEASURED"


@dataclass
class EngineSpec:
    """Documented benchmark configuration for one engine.

    Parameters are fixed per engine and never varied between messages, so the
    comparison is like-for-like.
    """

    engine: str
    display_name: str
    model_path: str | None
    venv_python: str = DEFAULT_VENV_PYTHON
    language: str | None = None
    device: str = "cpu"
    compute_type: str = "int8"
    model_revision: str | None = None
    sample_rate_policy: str = "native"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def check_availability(spec: EngineSpec) -> dict:
    """Report whether an engine can run, with an explicit reason (no download)."""
    python_present = bool(spec.venv_python) and os.path.exists(spec.venv_python)
    model_present = bool(spec.model_path) and os.path.exists(str(spec.model_path))
    module_present = False
    if python_present and model_present:
        module = "faster_whisper" if spec.engine == "faster_whisper" else spec.engine
        probe = subprocess.run(
            [spec.venv_python, "-c", f"import importlib.util,sys;"
             f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": "", "PYTHONNOUSERSITE": "1"},
        )
        module_present = probe.returncode == 0

    if not python_present:
        reason = f"provisioned interpreter not found: {spec.venv_python!r}"
    elif not model_present:
        reason = f"local model path missing: {spec.model_path!r} (offline rule: no download)"
    elif not module_present:
        reason = f"engine module {spec.engine!r} not importable in {spec.venv_python!r}"
    else:
        reason = "provisioned interpreter, engine module and local model present"

    ready = python_present and model_present and module_present
    return {
        "engine": spec.engine,
        "ready": ready,
        "reason": reason,
        "interpreter_present": python_present,
        "module_present": module_present,
        "model_present": model_present,
        "model_path": spec.model_path,
    }


def _empty_record(message_id: str, wav_path: str, duration: float, status: str, error: str) -> dict:
    return {
        "message_id": message_id,
        "wav_path": wav_path,
        "audio_duration_seconds": duration,
        "status": status,
        "text": None,
        "latency_ms": None,
        "rtf": None,
        "cpu_user_s": None,
        "cpu_sys_s": None,
        "peak_rss_kb": None,
        "error": error,
        "error_type": None,
    }


def _parse_stderr_tail(stderr: str, limit: int = 600) -> str:
    text = (stderr or "").strip()
    return text[-limit:] if text else ""


def run_engine(
    spec: EngineSpec,
    records: list,
    *,
    workdir: str,
    timeout_seconds: float = 0.0,
    per_file_timeout: float = 0.0,
) -> dict:
    """Execute one engine over every record; always returns a complete ledger.

    ``records`` is a list of :class:`wo069_dataset.DatasetRecord`.
    """
    availability = check_availability(spec)
    jobs_path = os.path.join(workdir, f"jobs_{spec.engine}.json")
    out_path = os.path.join(workdir, f"raw_{spec.engine}.jsonl")
    for stale in (out_path,):
        if os.path.exists(stale):
            os.remove(stale)

    jobs = {
        "records": [
            {
                "message_id": r.message_id,
                "wav_path": r.wav_path,
                "duration_seconds": r.duration_seconds,
            }
            for r in records
        ]
    }
    os.makedirs(workdir, exist_ok=True)
    with open(jobs_path, "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, indent=2, ensure_ascii=False)

    ledger: dict[str, dict] = {
        r.message_id: _empty_record(
            r.message_id, r.wav_path, r.duration_seconds, "NOT_EXECUTED", "engine not executed"
        )
        for r in records
    }

    result = {
        "engine": spec.engine,
        "display_name": spec.display_name,
        "configuration": spec.to_dict(),
        "engine_availability": availability,
        "engine_status": ENGINE_NOT_EXECUTED,
        "failure_reason": None,
        "exit_code": None,
        "model_load_status": NOT_MEASURED,
        "cold_start_ms": NOT_MEASURED,
        "stderr_tail": "",
        "oom_evidence": None,
        "interrupted": False,
        "records": [],
    }

    if not availability["ready"]:
        result["engine_status"] = ENGINE_UNAVAILABLE
        result["failure_reason"] = availability["reason"]
        for record in ledger.values():
            record["status"] = "ENGINE_UNAVAILABLE"
            record["error"] = availability["reason"]
        result["records"] = [ledger[r.message_id] for r in records]
        return result

    cmd = [
        spec.venv_python,
        WORKER_PATH,
        "--engine", spec.engine,
        "--model-path", str(spec.model_path),
        "--jobs", jobs_path,
        "--out", out_path,
        "--device", spec.device,
        "--compute-type", spec.compute_type,
        "--language", spec.language or "",
        "--per-file-timeout", str(per_file_timeout),
    ]
    env = {**os.environ, "PYTHONPATH": "", "PYTHONNOUSERSITE": "1", "HF_HUB_OFFLINE": "1"}
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
            cwd=workdir,
            env=env,
        )
        exit_code = proc.returncode
        stderr_tail = _parse_stderr_tail(proc.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stderr_tail = _parse_stderr_tail(
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
        for record in ledger.values():
            record["status"] = "TIMEOUT"
            record["error"] = f"engine session exceeded {timeout_seconds}s"

    result["exit_code"] = exit_code
    result["stderr_tail"] = stderr_tail

    # Replay the JSONL ledger emitted so far (crash-safe: keep partial results).
    engine_line = None
    summary_line = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "engine":
                    engine_line = obj
                elif obj.get("type") == "summary":
                    summary_line = obj
                elif obj.get("type") == "file":
                    message_id = obj["message_id"]
                    if message_id in ledger:
                        merged = dict(ledger[message_id])
                        merged.update({k: v for k, v in obj.items() if k != "type"})
                        ledger[message_id] = merged

    if engine_line is not None:
        result["model_load_status"] = engine_line.get("model_load_status", NOT_MEASURED)
        result["cold_start_ms"] = engine_line.get("cold_start_ms", NOT_MEASURED)
        if engine_line.get("model_load_status") == "FAILED":
            result["engine_status"] = ENGINE_FAILED
            result["failure_reason"] = (
                f"model load failed: {engine_line.get('error')}"
            )

    if timed_out:
        result["engine_status"] = ENGINE_TIMEOUT
        result["failure_reason"] = f"engine session timeout after {timeout_seconds}s"
    elif exit_code is not None and exit_code < 0:
        result["engine_status"] = ENGINE_FAILED
        result["oom_evidence"] = (
            "SIGKILL (signal 9) — consistent with the 4 GiB cgroup memory ceiling"
            if exit_code == -9
            else f"terminated by signal {-exit_code}"
        )
        result["failure_reason"] = (
            f"engine process killed by signal {-exit_code} "
            f"({result['oom_evidence']})"
        )
    elif result["engine_status"] != ENGINE_FAILED:
        if exit_code == 0 and summary_line is not None:
            result["engine_status"] = ENGINE_COMPLETED
        elif exit_code == 0:
            result["engine_status"] = ENGINE_COMPLETED
            result["failure_reason"] = (
                "engine exited 0 but emitted no summary line; per-file ledger replayed"
            )
        else:
            result["engine_status"] = ENGINE_FAILED
            result["failure_reason"] = (
                f"engine exited {exit_code}; stderr tail: {stderr_tail or '(empty)'}"
            )

    # Mark any file that produced no ledger line at all.
    for record in ledger.values():
        if record["status"] == "NOT_EXECUTED":
            record["status"] = "FAILED" if result["engine_status"] != ENGINE_COMPLETED else "MISSING_OUTPUT"
            if not record["error"]:
                record["error"] = result["failure_reason"] or "no per-file record emitted"

    result["records"] = [ledger[r.message_id] for r in records]
    if summary_line is not None:
        result["summary"] = summary_line
    return result


def build_runner(*args, **kwargs):  # pragma: no cover - convenience alias
    return run_engine(*args, **kwargs)


def _self_test() -> int:  # pragma: no cover - manual smoke helper
    print(json.dumps({"worker": WORKER_PATH, "exists": os.path.exists(WORKER_PATH)}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_self_test())
