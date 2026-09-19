#!/usr/bin/env python3
"""WO-069 — Engine worker: run ONE engine in an isolated process.

The worker is executed by ``wo069_runner`` inside the *provisioned* engine
virtualenv (the only environment where the engine package and its model are
installed).  It:

  * loads the local model exactly once and measures the cold-start time;
  * transcribes each WAV in the job list, emitting one JSONL record per file;
  * measures per-file latency, CPU time, peak RSS and RTF;
  * captures per-file failure / timeout in the record (never raises out).

It NEVER downloads a model, never touches the network and never fabricates a
transcript.  If the model cannot be loaded it emits an explicit engine-level
FAILED record and exits non-zero, so the parent records the true cause.

Usage::

    python wo069_engine_worker.py --engine vosk \
        --model-path /path/to/model --jobs jobs.json --out out.jsonl

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import array
import json
import os
import signal
import sys
import time
import wave

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_TIMEOUT = "TIMEOUT"

_PEAK_RSS_KB = None


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def peak_rss_kb() -> int | None:
    """Peak resident set size of this process (Linux ``VmHWM``)."""
    global _PEAK_RSS_KB
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    _PEAK_RSS_KB = int(line.split()[1])
                    return _PEAK_RSS_KB
    except OSError:
        pass
    return _PEAK_RSS_KB


def cpu_times() -> tuple[float, float]:
    times = os.times()
    return times.user, times.system


def read_wav_frames(path: str) -> tuple[int, int, bytes]:
    """Read a PCM WAV read-only; returns (rate, channels, frames)."""
    with wave.open(path, "rb") as wav:
        return wav.getframerate(), wav.getnchannels(), wav.readframes(wav.getnframes())


def resample_linear(frames: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Deterministic linear-interpolation resample between PCM16 mono rates.

    Documented preprocessing: applied ONLY where an engine cannot consume the
    native rate (Vosk's Ukrainian model hard-codes 16 kHz).  The original WAV is
    never modified and the native file is the benchmark input of record.
    """
    if src_rate == dst_rate:
        return frames
    source = array.array("h")
    source.frombytes(frames)
    n = len(source)
    if n == 0:
        return frames
    ratio = dst_rate / float(src_rate)
    out_len = int(n * ratio)
    out = array.array("h", [0] * out_len)
    for i in range(out_len):
        x = i / ratio
        i0 = int(x)
        frac = x - i0
        i1 = min(i0 + 1, n - 1)
        s0 = source[i0]
        out[i] = int(s0 + (source[i1] - s0) * frac)
    return out.tobytes()


class ModelLoadError(Exception):
    """Raised when the local model cannot be loaded (no download is attempted)."""


def load_engine(engine: str, model_path: str, device: str, compute_type: str):
    """Load the local model once; returns an engine session object."""
    if engine == "vosk":
        import vosk

        vosk.SetLogLevel(-1)
        if not os.path.isdir(model_path):
            raise ModelLoadError(f"vosk model path is not a directory: {model_path!r}")
        try:
            model = vosk.Model(model_path)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            raise ModelLoadError(f"vosk.Model failed: {type(exc).__name__}: {exc}") from exc
        return {"engine": "vosk", "model": model, "vosk": vosk, "target_rate": 16000}

    if engine == "faster_whisper":
        from faster_whisper import WhisperModel

        try:
            model = WhisperModel(model_path, device=device, compute_type=compute_type)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            raise ModelLoadError(
                f"faster_whisper.WhisperModel failed: {type(exc).__name__}: {exc}"
            ) from exc
        return {
            "engine": "faster_whisper",
            "model": model,
            "target_rate": None,
        }

    raise ModelLoadError(f"unsupported engine {engine!r}")


def transcribe(session: dict, wav_path: str, language: str | None) -> str:
    """Transcribe one WAV and return the raw hypothesis text."""
    rate, _channels, frames = read_wav_frames(wav_path)
    if session["engine"] == "vosk":
        import json as _json

        target = session["target_rate"]
        payload = resample_linear(frames, rate, target) if target else frames
        recognizer = session["vosk"].KaldiRecognizer(session["model"], target or rate)
        recognizer.AcceptWaveform(payload)
        return _json.loads(recognizer.FinalResult()).get("text", "").strip()

    model = session["model"]
    kwargs: dict = {"vad_filter": False}
    if language:
        kwargs["language"] = language
    segments, _info = model.transcribe(wav_path, **kwargs)
    return " ".join(seg.text.strip() for seg in segments).strip()


class _FileTimeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise _FileTimeout("per-file timeout exceeded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WO-069 engine worker")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default="")
    parser.add_argument("--per-file-timeout", type=float, default=0.0)
    args = parser.parse_args(argv)

    with open(args.jobs, encoding="utf-8") as fh:
        job = json.load(fh)
    records = job.get("records", [])
    language = args.language or None

    out_fh = open(args.out, "a", encoding="utf-8")

    def emit(obj: dict) -> None:
        out_fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out_fh.flush()

    started = _now_ms()
    try:
        session = load_engine(args.engine, args.model_path, args.device, args.compute_type)
    except Exception as exc:  # noqa: BLE001 - explicit engine-level failure
        emit(
            {
                "type": "engine",
                "engine": args.engine,
                "model_path": args.model_path,
                "model_load_status": "FAILED",
                "cold_start_ms": round(_now_ms() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
                "error_type": type(exc).__name__,
            }
        )
        out_fh.close()
        return 3

    emit(
        {
            "type": "engine",
            "engine": args.engine,
            "model_path": args.model_path,
            "model_load_status": "READY",
            "cold_start_ms": round(_now_ms() - started, 3),
            "error": None,
            "error_type": None,
        }
    )

    use_alarm = args.per_file_timeout > 0 and hasattr(signal, "SIGALRM")
    processed = 0
    for entry in records:
        message_id = entry["message_id"]
        wav_path = entry["wav_path"]
        audio_seconds = float(entry.get("duration_seconds") or 0.0)
        cpu_before = cpu_times()
        started_file = _now_ms()
        record = {
            "type": "file",
            "message_id": message_id,
            "wav_path": wav_path,
            "audio_duration_seconds": audio_seconds,
            "status": STATUS_FAILED,
            "text": None,
            "latency_ms": None,
            "rtf": None,
            "cpu_user_s": None,
            "cpu_sys_s": None,
            "peak_rss_kb": None,
            "error": None,
            "error_type": None,
        }
        if use_alarm:
            signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, args.per_file_timeout)
        try:
            text = transcribe(session, wav_path, language)
            elapsed = (_now_ms() - started_file) / 1000.0
            cpu_after = cpu_times()
            record.update(
                status=STATUS_SUCCESS,
                text=text,
                latency_ms=round(elapsed * 1000.0, 3),
                rtf=round(elapsed / audio_seconds, 6) if audio_seconds > 0 else None,
                cpu_user_s=round(cpu_after[0] - cpu_before[0], 6),
                cpu_sys_s=round(cpu_after[1] - cpu_before[1], 6),
                peak_rss_kb=peak_rss_kb(),
            )
        except _FileTimeout as exc:
            record.update(
                status=STATUS_TIMEOUT,
                latency_ms=round((_now_ms() - started_file), 3),
                error=f"{type(exc).__name__}: {exc}",
                error_type=type(exc).__name__,
                peak_rss_kb=peak_rss_kb(),
            )
        except Exception as exc:  # noqa: BLE001 - recorded as a failed file
            record.update(
                status=STATUS_FAILED,
                latency_ms=round((_now_ms() - started_file), 3),
                error=f"{type(exc).__name__}: {exc}",
                error_type=type(exc).__name__,
                peak_rss_kb=peak_rss_kb(),
            )
        finally:
            if use_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
        emit(record)
        processed += 1

    emit(
        {
            "type": "summary",
            "engine": args.engine,
            "processed": processed,
            "total_ms": round(_now_ms() - started, 3),
            "peak_rss_kb": peak_rss_kb(),
        }
    )
    out_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
