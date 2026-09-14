"""WO-067 — Engine runner adapters (benchmark-only, offline).

The benchmark must be able to drive a real engine *without* modifying the
production seam.  This module therefore defines a small benchmark-local engine
protocol plus two adapters that sit ON TOP of the production contract:

    benchmark CLS runner  ->  app.contracts.audio.ITranscriber
                          ->  app.audio.stt_seam.AbstractSttAdapter
                          ->  app.audio.stt_config.SttConfig (local model path)

Only the production *contract* and *offline-init lifecycle* are reused.  No
production file is modified, no engine is registered in the production
``_ENGINE_FACTORIES`` registry, and the benchmark never downloads a model.

Model discipline (WO-067 §12): a candidate engine is reported READY only when
its module is importable AND its configured local model path exists AND (for
Vosk) the model directory looks like a provisioned Vosk model.  Otherwise the
engine is BLOCKED with an explicit reason — never a silent skip.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import importlib.util
import os
import time
from dataclasses import dataclass, field

# Benchmark engine identifiers — must stay in step with the production seam's
# recognised set (app.audio.stt_config.SUPPORTED_ENGINES).
ENGINE_FASTER_WHISPER = "faster_whisper"
ENGINE_VOSK = "vosk"

BENCHMARK_ENGINES = (ENGINE_FASTER_WHISPER, ENGINE_VOSK)


@dataclass
class EngineConfig:
    """Documented, frozen benchmark configuration for one engine (WO-067 §12).

    Every candidate is transcribed with the same parameters for a given engine;
    parameters are never varied per candidate.
    """

    engine: str
    model_path: str | None
    language: str
    device: str = "cpu"
    quantization: str | None = None
    beam_size: int | None = None
    best_of: int | None = None
    temperature: float | None = None
    vad_filter: bool | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "model_path": self.model_path,
            "language": self.language,
            "device": self.device,
            "quantization": self.quantization,
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "temperature": self.temperature,
            "vad_filter": self.vad_filter,
            "extra": dict(self.extra),
        }


def _model_looks_like_vosk_dir(path: str) -> bool:
    """A provisioned Vosk model is a directory with an ``am/`` or ``conf/``."""
    if not os.path.isdir(path):
        return False
    entries = set(os.listdir(path))
    return bool({"am", "conf", "graph"} & entries) or any(
        e.startswith("am") for e in entries
    )


def check_engine_availability(cfg: EngineConfig) -> dict:
    """Report whether one engine can run, with an explicit reason.

    Returns a dict with ``ready`` (bool) and ``reason``.  Never downloads and
    never raises for a missing engine/model.
    """
    module_name = "faster_whisper" if cfg.engine == ENGINE_FASTER_WHISPER else cfg.engine
    if cfg.engine not in BENCHMARK_ENGINES:
        return {
            "engine": cfg.engine,
            "ready": False,
            "reason": f"unsupported benchmark engine {cfg.engine!r}",
            "module_present": False,
            "model_path": cfg.model_path,
            "model_present": False,
        }

    module_present = importlib.util.find_spec(module_name) is not None
    model_present = bool(cfg.model_path) and os.path.exists(cfg.model_path)

    if not module_present:
        return {
            "engine": cfg.engine,
            "ready": False,
            "reason": (
                f"engine module {module_name!r} is not installed locally "
                f"(offline rule: no download)"
            ),
            "module_present": False,
            "model_path": cfg.model_path,
            "model_present": model_present,
        }
    if not cfg.model_path or not str(cfg.model_path).strip():
        return {
            "engine": cfg.engine,
            "ready": False,
            "reason": "no local model path configured",
            "module_present": True,
            "model_path": cfg.model_path,
            "model_present": False,
        }
    if not model_present:
        return {
            "engine": cfg.engine,
            "ready": False,
            "reason": (
                f"local model path does not exist: {cfg.model_path!r} "
                f"(offline rule: no download)"
            ),
            "module_present": True,
            "model_path": cfg.model_path,
            "model_present": False,
        }
    if cfg.engine == ENGINE_VOSK and not _model_looks_like_vosk_dir(str(cfg.model_path)):
        return {
            "engine": cfg.engine,
            "ready": False,
            "reason": (
                f"path exists but does not look like a provisioned Vosk model "
                f"(expected am/ or conf/): {cfg.model_path!r}"
            ),
            "module_present": True,
            "model_path": cfg.model_path,
            "model_present": True,
        }
    return {
        "engine": cfg.engine,
        "ready": True,
        "reason": "module and local model present",
        "module_present": True,
        "model_path": cfg.model_path,
        "model_present": True,
    }


class BenchmarkEngineError(Exception):
    """Raised when a benchmark engine cannot be constructed or run."""


class BaseBenchmarkRunner:
    """Benchmark-local engine runner protocol.

    A concrete runner wraps a real offline engine.  It is deliberately NOT
    registered in the production seam registry — the benchmark drives engines
    through this adapter only.
    """

    engine_id = ""

    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg
        self._inner = None

    def prepare(self) -> None:
        """Load the local model (cold start). Must not touch the network."""
        raise NotImplementedError

    def transcribe_path(self, wav_path: str) -> str:
        """Transcribe a WAV file and return the raw hypothesis text."""
        raise NotImplementedError

    def close(self) -> None:
        """Release engine resources."""

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def build_production_adapter(cfg: EngineConfig):
        """Build the production ``AbstractSttAdapter`` for this config.

        Reuses the production seam for offline model-path validation and the
        ``initialize`` lifecycle.  The adapter is NOT registered globally.
        """
        from app.audio.stt_config import SttConfig
        from app.audio.stt_seam import build_transcriber

        stt_cfg = SttConfig(
            enabled=True,
            engine=cfg.engine,
            model_path=cfg.model_path,
            language=cfg.language,
            device=cfg.device,
        )
        return stt_cfg, build_transcriber


class FasterWhisperBenchmarkRunner(BaseBenchmarkRunner):
    """Faster-Whisper runner (constructed only when the module is present)."""

    engine_id = ENGINE_FASTER_WHISPER

    def prepare(self) -> None:
        import faster_whisper

        kwargs = {
            "device": self.cfg.device,
            "compute_type": self.cfg.quantization or "default",
        }
        self._inner = faster_whisper.WhisperModel(self.cfg.model_path, **kwargs)

    def transcribe_path(self, wav_path: str) -> str:
        if self._inner is None:
            raise BenchmarkEngineError("FasterWhisper runner not prepared")
        kwargs = {"language": self.cfg.language or None, "vad_filter": bool(self.cfg.vad_filter)}
        if self.cfg.beam_size is not None:
            kwargs["beam_size"] = self.cfg.beam_size
        if self.cfg.best_of is not None:
            kwargs["best_of"] = self.cfg.best_of
        if self.cfg.temperature is not None:
            kwargs["temperature"] = self.cfg.temperature
        segments, _info = self._inner.transcribe(wav_path, **kwargs)
        return " ".join(seg.text.strip() for seg in segments).strip()

    def close(self) -> None:
        self._inner = None


class VoskBenchmarkRunner(BaseBenchmarkRunner):
    """Vosk runner (constructed only when the module and model are present)."""

    engine_id = ENGINE_VOSK

    def prepare(self) -> None:
        import json
        import wave

        import vosk

        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self._json = json
        self._wave = wave
        self._inner = vosk.KaldiRecognizer(
            vosk.Model(self.cfg.model_path), 8000
        )

    def transcribe_path(self, wav_path: str) -> str:
        if self._inner is None:
            raise BenchmarkEngineError("Vosk runner not prepared")
        parts: list[str] = []
        with self._wave.open(wav_path, "rb") as wf:
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                if self._inner.AcceptWaveform(data):
                    parts.append(self._json.loads(self._inner.Result()).get("text", ""))
        parts.append(self._json.loads(self._inner.FinalResult()).get("text", ""))
        self._inner.Reset()
        return " ".join(p for p in parts if p).strip()

    def close(self) -> None:
        self._inner = None


RUNNERS = {
    ENGINE_FASTER_WHISPER: FasterWhisperBenchmarkRunner,
    ENGINE_VOSK: VoskBenchmarkRunner,
}


def build_runner(cfg: EngineConfig) -> BaseBenchmarkRunner:
    """Construct a benchmark runner. Raises when the engine is unsupported."""
    runner_cls = RUNNERS.get(cfg.engine)
    if runner_cls is None:
        raise BenchmarkEngineError(f"unsupported benchmark engine {cfg.engine!r}")
    return runner_cls(cfg)


def measure_cold_start(runner: BaseBenchmarkRunner) -> float:
    """Seconds spent loading the local model (cold start latency)."""
    start = time.perf_counter()
    runner.prepare()
    return time.perf_counter() - start