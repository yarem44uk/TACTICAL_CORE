#!/usr/bin/env python3
"""WO-040 / WO-040-CORR — Real acoustic STT benchmark harness (isolated, offline,
stdlib-only).

This is benchmark *tooling* only (WO-040 §19, WO-040-CORR §1).  It is
deliberately:

    * isolated        — self-contained, does not touch the production STT seam;
    * deterministic   — pure functions, reproducible output;
    * offline         — uses only the Python standard library, never downloads
                        a model or runtime package, never calls a network API;
    * read-only       — opens WAV masters in ``rb`` and never writes to them.

WO-040-CORR extends the harness with the actual measurement/accounting required
by ADR-014 so that, when a candidate runtime/model and real radio recordings
are provisioned locally, the benchmark can be executed:

    1. probe    — detect whether a candidate engine runtime/model is present
                  locally (faster_whisper / vosk).  Absence is recorded as an
                  explicit result, never substituted or fabricated.
    2. manifest — scan the configured WAV master roots, build
                  ``dataset_manifest.csv`` with real metadata (sha256, format,
                  duration), provenance, and ground-truth linkage.
    3. run      — execute the benchmark for one candidate over the manifest.
                  Each candidate/input execution yields an explicit
                  ``CandidateResult`` record with status SUCCESS / FAILURE /
                  TIMEOUT / NOT_AVAILABLE, measured latency, RTF, CPU, RAM,
                  GPU, VRAM, WER, CER, callsign accuracy, and error/timeout
                  accounting.  Failures and timeouts remain in the denominator.
    4. metrics  — compute WER / CER / callsign accuracy from a reference and a
                  hypothesis transcript.
    5. gate     — ADR-014 mandatory gate: >= 50 independently verified real
                  radio transmissions.

The harness NEVER registers an engine, NEVER alters ``SUPPORTED_ENGINES``,
NEVER replaces the deterministic test transcriber, and NEVER modifies
production configuration.  Benchmark execution is isolated behind a candidate
runner boundary (WO-040-CORR §5).

WO-040-CORR-02 makes ``COLD`` and ``WARM`` genuine, behaviorally distinct
execution phases instead of labels.  A ``CandidateSession`` lifecycle is used:

    create session
        -> initialize()      (COLD: runtime/model initialization, once)
        -> transcribe #1     (COLD: latency = initialization + inference)
        -> transcribe #2..N  (WARM: latency = inference only, model reused)
        -> close()

The candidate model is initialized exactly once and reused for every warm
inference; it is never reconstructed per warm input.  This is benchmark-only
(WO-040-CORR-02 §4/§10).

Author: Tactical Core Engineering Team
Version: 1.2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import signal
import statistics
import sys
import threading
import time
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Candidate engines that must be benchmarked (WO-040 §7).
# ---------------------------------------------------------------------------
CANDIDATES = ["faster_whisper", "vosk"]

# Explicit result states (WO-040-CORR §12/§16).  NOT_AVAILABLE is a candidate
# that cannot be executed at all (runtime or model absent) — it is a distinct,
# honest state, not a fabricated SUCCESS or a hidden failure.
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"

# Run phases (WO-040-CORR §15).
PHASE_COLD = "cold"
PHASE_WARM = "warm"

# Default WAV master roots discovered during WO-040 discovery (§3).  These are
# the locations where the actual WO-039 pipeline wrote finalized radio WAV
# masters on this host.
DEFAULT_WAV_ROOTS = [
    "/tmp/tmp830mejt0/2026/09/02/radio",
    "/tmp/hv_nw8kok3b/2026/09/02/radio",
    "/tmp/aud_a03080ty/2026/09/02/radio",
]

# Provenance annotation for these recordings (established in WO-040 discovery):
# they are WO-039-B/C unit-test fixtures — constant-amplitude PCM values fed
# through the real RTP -> VAD -> recorder -> WAV pipeline to exercise the
# VAD / segmentation / recording logic.  They are NOT real radio speech.
TEST_FIXTURE_PROVENANCE = (
    "WO-039-B/C unit-test fixture: constant-amplitude PCM value fed through the "
    "real RTP->VAD->recorder->WAV pipeline; contains no speech, no words, no "
    "callsigns (VAD/segmentation test tone, not a real radio transmission)."
)

# ADR-014 mandatory minimum number of independently verified real radio
# transmissions.
ADR014_MIN_REAL_TRANSMISSIONS = 50

# Stable column ordering for results persistence (WO-040-CORR §19).
RESULT_CSV_FIELDS = [
    "candidate",
    "audio_id",
    "run_phase",
    "status",
    "audio_duration_seconds",
    "reference",
    "hypothesis",
    "wer",
    "cer",
    "callsign_accuracy",
    "callsigns_total",
    "callsigns_correct",
    "processing_time_seconds",
    "latency_seconds",
    "rtf",
    "cpu_usage",
    "ram_usage",
    "gpu_usage",
    "vram_usage",
    "failure",
    "timeout",
    "error",
]


# ---------------------------------------------------------------------------
# Exceptions.
# ---------------------------------------------------------------------------
class BenchmarkTimeoutError(Exception):
    """Raised when a candidate execution exceeds the configured timeout."""


class CandidateUnavailable(Exception):
    """Raised when a candidate runtime/model cannot be executed at all."""


# ---------------------------------------------------------------------------
# Result / configuration models (WO-040-CORR §4/§16).
# ---------------------------------------------------------------------------
@dataclass
class CandidateResult:
    """Explicit per-candidate, per-input benchmark result record."""

    audio_id: str
    candidate: str
    audio_duration_seconds: float | None
    status: str
    hypothesis: str
    reference: str
    callsigns_total: int
    callsigns_correct: int
    wer: float | None
    cer: float | None
    callsign_accuracy: float | None
    processing_time_seconds: float | None
    latency_seconds: float | None
    rtf: float | None
    cpu_usage: float | None
    ram_usage: float | None
    gpu_usage: str | None
    vram_usage: str | None
    error: str
    timeout: bool
    run_phase: str


@dataclass
class CandidateConfig:
    """Configuration/availability record for a benchmark candidate."""

    candidate: str
    runtime_installed: bool
    runtime_version: str | None
    model_present: bool
    model_path: str | None
    language: str
    device: str
    config: dict[str, Any]
    available: bool
    availability_reason: str


# ---------------------------------------------------------------------------
# Candidate availability probe (WO-040 §8, WO-040-CORR §16).
# ---------------------------------------------------------------------------
def probe_candidate(engine: str) -> dict[str, Any]:
    """Return availability of one candidate engine and its local model.

    This never imports a missing module as a fatal error; it reports the
    absence so the benchmark can honestly document the technical inability to
    run offline (WO-040 §7/§8).  No download, no network.
    """
    result: dict[str, Any] = {
        "engine": engine,
        "runtime_installed": False,
        "runtime_version": None,
        "import_error": None,
        "model_present": False,
        "model_path": None,
    }
    try:
        if engine == "faster_whisper":
            import faster_whisper  # noqa: F401
            result["runtime_installed"] = True
            result["runtime_version"] = getattr(faster_whisper, "__version__", None)
        elif engine == "vosk":
            import vosk  # noqa: F401
            result["runtime_installed"] = True
            result["runtime_version"] = getattr(vosk, "__version__", None)
    except Exception as exc:  # noqa: BLE001 - report absence, not crash
        result["import_error"] = f"{type(exc).__name__}: {exc}"

    # Model presence: search a small set of well-known local model roots only.
    # We deliberately do not scan the whole filesystem in the harness; the
    # discovery step already established that no model exists on this host.
    for root in ["/opt/models", "/models", "/opt/data/models", "/opt/data/tactical_core_github/models"]:
        if os.path.isdir(root):
            for entry in os.listdir(root):
                if engine.replace("_", "-") in entry.lower() or engine in entry.lower():
                    result["model_present"] = True
                    result["model_path"] = os.path.join(root, entry)
    return result


def probe_all() -> list[dict[str, Any]]:
    return [probe_candidate(e) for e in CANDIDATES]


def get_candidate_config(
    candidate: str,
    language: str | None = None,
    device: str | None = None,
) -> CandidateConfig:
    """Build the benchmark-only configuration/availability record for a candidate."""
    if candidate not in CANDIDATES:
        raise ValueError(f"candidate {candidate!r} not in {CANDIDATES}")
    probe = probe_candidate(candidate)
    available = probe["runtime_installed"] and probe["model_present"]
    if not probe["runtime_installed"]:
        reason = f"runtime not installed ({probe['import_error'] or 'unknown'})"
    elif not probe["model_present"]:
        reason = "no local model present"
    else:
        reason = ""
    lang = language or "uk"
    dev = device or "cpu"
    return CandidateConfig(
        candidate=candidate,
        runtime_installed=probe["runtime_installed"],
        runtime_version=probe["runtime_version"],
        model_present=probe["model_present"],
        model_path=probe["model_path"],
        language=lang,
        device=dev,
        config={"language": lang, "device": dev},
        available=available,
        availability_reason=reason,
    )


# ---------------------------------------------------------------------------
# WAV master scanning + dataset manifest (WO-040 §4/§5/§6/§11, WO-040-CORR §18).
# ---------------------------------------------------------------------------
def read_wav_info(path: str) -> dict[str, Any]:
    """Read WAV metadata read-only, computing sha256 over the exact bytes."""
    with open(path, "rb") as fh:
        data = fh.read()
    digest = hashlib.sha256(data).hexdigest()
    with wave.open(os.path.join(os.path.dirname(path), os.path.basename(path)), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        nframes = wf.getnframes()
        duration = nframes / sample_rate if sample_rate else 0.0
    return {
        "sha256": digest,
        "channels": channels,
        "sampwidth": sampwidth,
        "sample_rate": sample_rate,
        "nframes": nframes,
        "duration": round(duration, 4),
        "data_bytes": len(data),
    }


def _is_real_radio_provenance(provenance: str) -> bool:
    """Return True when provenance does not mark the recording as a test fixture.

    The only provenance used by the WO-039 fixtures is TEST_FIXTURE_PROVENANCE,
    which is explicitly a unit-test fixture.  Any other provenance is treated as
    an unverified recording; the gate additionally requires verified ground
    truth before counting it as a real, verified transmission.
    """
    prov = (provenance or "").lower()
    fixture_markers = ("fixture", "unit-test", "test fixture", "no speech", "test tone", "not a real radio")
    return not any(m in prov for m in fixture_markers)


def build_manifest(roots: list[str]) -> list[dict[str, Any]]:
    """Build the dataset manifest from the given WAV master roots."""
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if not name.lower().endswith(".wav"):
                continue
            path = os.path.join(root, name)
            try:
                info = read_wav_info(path)
            except Exception as exc:  # noqa: BLE001 - record unreadable file
                rows.append({
                    "audio_id": os.path.splitext(name)[0],
                    "wav_path": path,
                    "source": "radio",
                    "duration_s": "",
                    "channels": "",
                    "sampwidth": "",
                    "sample_rate": "",
                    "sha256": "",
                    "ground_truth": "",
                    "callsigns_present": "",
                    "provenance": f"UNREADABLE: {exc}",
                    "usable": "false",
                    "real_transmission": "false",
                })
                continue
            # WO-039-C3 requires mono 16-bit 8kHz for the WAV master.
            usable = (info["channels"] == 1 and info["sampwidth"] == 2 and info["sample_rate"] == 8000)
            provenance = TEST_FIXTURE_PROVENANCE
            real = "true" if _is_real_radio_provenance(provenance) else "false"
            rows.append({
                "audio_id": os.path.splitext(name)[0],
                "wav_path": path,
                "source": "radio",
                "duration_s": info["duration"],
                "channels": info["channels"],
                "sampwidth": info["sampwidth"],
                "sample_rate": info["sample_rate"],
                "sha256": info["sha256"],
                "ground_truth": "",  # none exists (WO-040 §5)
                "callsigns_present": "",  # none exist
                "provenance": provenance,
                "usable": "true" if usable else "false",
                "real_transmission": real,
            })
    return rows


def load_manifest(path: str) -> list[dict[str, Any]]:
    """Load a manifest CSV into a list of row dicts."""
    rows: list[dict[str, Any]] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Metric definitions (WO-040 §9/§10/§12) — deterministic, reproducible.
# ---------------------------------------------------------------------------
def _normalize(text: str) -> list[str]:
    """Lowercase and split on whitespace (word tokenization for WER)."""
    return [t for t in text.lower().split() if t]


def _count_correct_callsigns(reference_callsigns: list[str], hypothesis: str) -> int:
    """Count ground-truth callsigns that appear verbatim in the hypothesis.

    ADR-014 exact-match rule: a callsign is correct only if it appears as a
    contiguous token on word boundaries (``alpha`` matches only standalone
    ``alpha``, not ``alpha1`` or ``alphabet``).
    """
    hyp = hypothesis.lower()
    correct = 0
    for cs in reference_callsigns:
        norm = cs.lower().strip()
        if not norm:
            continue
        if re.search(r"\b" + re.escape(norm) + r"\b", hyp):
            correct += 1
    return correct


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate = (S + D + I) / N using Levenshtein on words."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    n = len(ref)
    if n == 0:
        return float("nan")
    # Levenshtein distance (words)
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / n


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate = Levenshtein distance on characters / ref length."""
    ref = reference.lower()
    hyp = hypothesis.lower()
    n = len(ref)
    if n == 0:
        return float("nan")
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / n


def callsign_accuracy(reference_callsigns: list[str], hypothesis: str) -> float:
    """Fraction of ground-truth callsigns that appear verbatim in the hypothesis.

    ADR-014: a callsign is correct only if it appears verbatim in the transcript
    on word boundaries.  Returns NaN when there are no reference callsigns.
    """
    if not reference_callsigns:
        return float("nan")
    return _count_correct_callsigns(reference_callsigns, hypothesis) / len(reference_callsigns)


def _parse_callsigns(raw: str | None) -> list[str]:
    """Parse a comma/space separated callsign field into a clean list."""
    if not raw:
        return []
    parts = re.split(r"[,\s]+", raw)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Timeout guard (WO-040-CORR §13).
# ---------------------------------------------------------------------------
def _alarm_handler(signum: int, frame: Any) -> None:
    raise BenchmarkTimeoutError(f"candidate execution exceeded timeout (signal {signum})")


class timeout_guard:
    """Context manager enforcing a wall-clock timeout via SIGALRM (main thread).

    Off the main thread, or when ``seconds <= 0``, it is a no-op guard (the
    runner is expected to cooperate or the caller has chosen no timeout).  The
    alarm is always restored in ``finally`` so the guard never leaks state.
    """

    def __init__(self, seconds: float | None) -> None:
        self.seconds = seconds
        self._old_handler: Any = None

    def __enter__(self) -> "timeout_guard":
        if self.seconds is None or self.seconds <= 0:
            return self
        if threading.current_thread() is not threading.main_thread():
            return self
        self._old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._old_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._old_handler)
            self._old_handler = None
        return False


# ---------------------------------------------------------------------------
# Resource measurement (WO-040-CORR §9/§10/§11).
# ---------------------------------------------------------------------------
def _current_rss_mb() -> float | None:
    """Current process resident set size (RSS) in MB, from /proc/self/statm.

    Returns None when the metric is unavailable (non-Linux or unreadable).  None
    is distinct from 0.0 — an unavailable measurement is never reported as zero.
    """
    try:
        with open("/proc/self/statm") as fh:
            parts = fh.read().split()
        resident_pages = int(parts[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
        return resident_pages * page_size / (1024 * 1024)
    except Exception:  # noqa: BLE001 - measurement unavailable
        return None


def _gpu_usage() -> tuple[str, str]:
    """Return (gpu_percent, vram_mb) as strings.

    GPU/VRAM are observational (WO-040-CORR §11).  When no GPU monitor is
    available (pynvml absent / no GPU), returns ("N/A", "N/A") — never a
    fabricated number.  Nothing is installed and nothing remote is contacted.
    """
    try:
        import pynvml  # noqa: F401
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        gpu = f"{util.gpu:.1f}"
        vram = f"{mem.used / (1024 * 1024):.1f}"
        return gpu, vram
    except Exception:  # noqa: BLE001 - no GPU / no monitor
        return "N/A", "N/A"


# ---------------------------------------------------------------------------
# Candidate session lifecycle (WO-040-CORR-02 §4/§5/§6).
#
# A session is created once, initialized once (COLD), and reused for every
# subsequent inference (WARM).  The model is never reconstructed per warm
# input.  This is benchmark-only; it never registers into the production seam.
# ---------------------------------------------------------------------------
class CandidateSession:
    """Lifecycle abstraction: initialize once, transcribe many, reuse.

    ``initialize()`` performs the expensive runtime/model load and returns the
    measured initialization time (seconds).  ``transcribe()`` runs inference on
    an already-initialized session.  ``close()`` releases resources (only if
    required).  ``transcribe()`` must not re-initialize the model.
    """

    def initialize(self) -> float:
        raise NotImplementedError

    def transcribe(self, audio_path: str, audio_bytes: bytes, sample_rate: int) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class FasterWhisperSession(CandidateSession):
    """Benchmark-only faster_whisper lifecycle (WO-040-CORR-02 §5).

    COLD: ``initialize()`` constructs ``WhisperModel`` once.  WARM:
    ``transcribe()`` reuses the already-initialized ``WhisperModel`` instance;
    it never constructs a new model for a warm input.
    """

    def __init__(self, config: CandidateConfig) -> None:
        self.config = config
        self._model: Any = None
        self._initialized = False
        self.initialize_seconds: float | None = None

    def initialize(self) -> float:
        if self._initialized:
            return 0.0
        try:
            from faster_whisper import WhisperModel  # noqa: N813
        except Exception as exc:  # noqa: BLE001
            raise CandidateUnavailable(f"faster_whisper runtime not installed: {exc}") from exc
        if not self.config.model_path:
            raise CandidateUnavailable("faster_whisper model not present locally")
        t0 = time.perf_counter()
        self._model = WhisperModel(self.config.model_path, device=self.config.device)
        dt = time.perf_counter() - t0
        self.initialize_seconds = dt
        self._initialized = True
        return dt

    def transcribe(self, audio_path: str, audio_bytes: bytes, sample_rate: int) -> str:
        if not self._initialized:
            raise RuntimeError("FasterWhisperSession not initialized; call initialize() first")
        segments, _info = self._model.transcribe(audio_path, language=self.config.language, beam_size=5)
        return "".join(seg.text for seg in segments).strip()

    def close(self) -> None:
        self._model = None
        self._initialized = False


class VoskSession(CandidateSession):
    """Benchmark-only vosk lifecycle (WO-040-CORR-02 §6).

    COLD: ``initialize()`` constructs ``Model`` once.  WARM: ``transcribe()``
    reuses the initialized ``Model``; it creates only a per-input
    ``KaldiRecognizer`` (whose state must be reset per audio sample) while
    reusing the expensive model object.  The model is never reloaded per warm
    input.
    """

    def __init__(self, config: CandidateConfig) -> None:
        self.config = config
        self._model: Any = None
        self._initialized = False
        self.initialize_seconds: float | None = None

    def initialize(self) -> float:
        if self._initialized:
            return 0.0
        try:
            from vosk import Model, SetLogLevel  # noqa: N813
        except Exception as exc:  # noqa: BLE001
            raise CandidateUnavailable(f"vosk runtime not installed: {exc}") from exc
        if not self.config.model_path:
            raise CandidateUnavailable("vosk model not present locally")
        SetLogLevel(-1)
        t0 = time.perf_counter()
        self._model = Model(self.config.model_path)
        dt = time.perf_counter() - t0
        self.initialize_seconds = dt
        self._initialized = True
        return dt

    def transcribe(self, audio_path: str, audio_bytes: bytes, sample_rate: int) -> str:
        if not self._initialized:
            raise RuntimeError("VoskSession not initialized; call initialize() first")
        from vosk import KaldiRecognizer  # noqa: N813
        rec = KaldiRecognizer(self._model, sample_rate)
        rec.AcceptWaveform(audio_bytes)
        result = rec.FinalResult()
        import json as _json
        return (_json.loads(result).get("text", "") or "").strip()

    def close(self) -> None:
        self._model = None
        self._initialized = False


def create_candidate_session(candidate: str, config: CandidateConfig) -> CandidateSession:
    """Return the benchmark-only lifecycle session for a candidate."""
    if candidate == "faster_whisper":
        return FasterWhisperSession(config)
    if candidate == "vosk":
        return VoskSession(config)
    raise ValueError(f"candidate {candidate!r} not in {CANDIDATES}")


# ---------------------------------------------------------------------------
# Candidate runner boundary (WO-040-CORR §5/§6/§16).
#
# A runner takes (audio_path, audio_bytes, sample_rate, run_phase, config) and
# returns a hypothesis string.  It is the isolated benchmark-only execution
# boundary.  It NEVER registers into the production STT seam.
# ---------------------------------------------------------------------------
def _run_faster_whisper(
    audio_path: str,
    audio_bytes: bytes,
    sample_rate: int,
    run_phase: str,
    config: CandidateConfig,
) -> str:
    """Single-shot benchmark-only faster_whisper runner (never registered in production).

    This is the legacy single-shot compat path.  It creates a
    ``FasterWhisperSession``, initializes it, transcribes once, and closes it.
    The genuine benchmark path (``execute_benchmark_lifecycle``) uses a
    reusable session so the model is initialized exactly once across cold+warm
    inputs (WO-040-CORR-02 §5).
    """
    session = FasterWhisperSession(config)
    try:
        session.initialize()
        return session.transcribe(audio_path, audio_bytes, sample_rate)
    finally:
        session.close()


def _run_vosk(
    audio_path: str,
    audio_bytes: bytes,
    sample_rate: int,
    run_phase: str,
    config: CandidateConfig,
) -> str:
    """Single-shot benchmark-only vosk runner (never registered in production).

    Legacy single-shot compat path (see ``_run_faster_whisper``); the genuine
    benchmark path reuses a ``VoskSession`` across warm inputs (WO-040-CORR-02 §6).
    """
    session = VoskSession(config)
    try:
        session.initialize()
        return session.transcribe(audio_path, audio_bytes, sample_rate)
    finally:
        session.close()


def get_candidate_runner(candidate: str) -> Callable[..., str]:
    """Return the benchmark-only runner for a candidate (raises if unknown)."""
    if candidate == "faster_whisper":
        return _run_faster_whisper
    if candidate == "vosk":
        return _run_vosk
    raise ValueError(f"candidate {candidate!r} not in {CANDIDATES}")


# ---------------------------------------------------------------------------
# Benchmark execution (WO-040-CORR §6/§7/§8/§12/§15).
# ---------------------------------------------------------------------------
def _load_wav(path: str) -> tuple[bytes, int, int, int, float]:
    """Load a WAV master read-only; return (bytes, sample_rate, channels, sampwidth, duration)."""
    with open(path, "rb") as fh:
        audio_bytes = fh.read()
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        nframes = wf.getnframes()
        duration = nframes / sample_rate if sample_rate else 0.0
    return audio_bytes, sample_rate, channels, sampwidth, duration


def _run_one(
    audio_id: str,
    candidate: str,
    audio_path: str,
    audio_bytes: bytes,
    sample_rate: int,
    audio_duration: float,
    reference: str,
    callsigns: list[str],
    runner: Callable[..., str],
    config: CandidateConfig,
    timeout_seconds: float,
    run_phase: str,
    session: CandidateSession | None = None,
    init_time: float | None = None,
) -> CandidateResult:
    """Execute one candidate on one input with timing, failure and timeout accounting.

    When ``session`` is provided, inference runs through the reused
    ``session.transcribe`` (WO-040-CORR-02).  ``init_time`` is the measured
    cold-start initialization time; when non-None it is added to the measured
    inference time so cold latency = initialization + inference, while warm
    latency (``init_time=None``) is inference only (WO-040-CORR-02 §7).
    """
    wall_t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    ram_before = _current_rss_mb()
    error = ""
    timeout = False
    status = STATUS_SUCCESS
    hypothesis = ""
    try:
        with timeout_guard(timeout_seconds):
            if session is not None:
                hypothesis = session.transcribe(audio_path, audio_bytes, sample_rate)
            else:
                hypothesis = runner(audio_path, audio_bytes, sample_rate, run_phase, config)
    except BenchmarkTimeoutError as exc:
        status = STATUS_TIMEOUT
        timeout = True
        error = str(exc)
    except CandidateUnavailable as exc:
        status = STATUS_FAILURE
        error = f"candidate unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001 - record the failure, keep it in the denominator
        status = STATUS_FAILURE
        error = f"{type(exc).__name__}: {exc}"
    finally:
        wall_t1 = time.perf_counter()
        cpu_t1 = time.process_time()
        ram_after = _current_rss_mb()

    inference_time = wall_t1 - wall_t0
    cpu_time = cpu_t1 - cpu_t0
    # Cold latency includes initialization; warm latency is inference only.
    latency = (init_time + inference_time) if init_time is not None else inference_time
    cpu_usage = (cpu_time / inference_time * 100.0) if inference_time > 0 else None
    ram_usage = (
        max(ram_before, ram_after)
        if (ram_before is not None and ram_after is not None)
        else None
    )
    rtf = (latency / audio_duration) if audio_duration and audio_duration > 0 else None

    # Recognition metrics: only when a hypothesis and a reference are available.
    wer_v: float | None = None
    cer_v: float | None = None
    cs_acc: float | None = None
    cs_correct = 0
    if status == STATUS_SUCCESS and reference and hypothesis:
        wer_v = wer(reference, hypothesis)
        cer_v = cer(reference, hypothesis)
    if status == STATUS_SUCCESS and callsigns and hypothesis:
        cs_correct = _count_correct_callsigns(callsigns, hypothesis)
        cs_acc = cs_correct / len(callsigns)

    gpu, vram = _gpu_usage()
    return CandidateResult(
        audio_id=audio_id,
        candidate=candidate,
        audio_duration_seconds=audio_duration,
        status=status,
        hypothesis=hypothesis,
        reference=reference,
        callsigns_total=len(callsigns),
        callsigns_correct=cs_correct,
        wer=wer_v,
        cer=cer_v,
        callsign_accuracy=cs_acc,
        processing_time_seconds=cpu_time,
        latency_seconds=latency,
        rtf=rtf,
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        gpu_usage=gpu,
        vram_usage=vram,
        error=error,
        timeout=timeout,
        run_phase=run_phase,
    )


def execute_benchmark(
    manifest_rows: list[dict[str, Any]],
    candidate: str,
    runner: Callable[..., str] | None = None,
    config: CandidateConfig | None = None,
    timeout_seconds: float = 120.0,
    run_phase: str = PHASE_WARM,
) -> list[CandidateResult]:
    """Run the benchmark for one candidate over the manifest rows.

    Every manifest row yields exactly one CandidateResult; failures and timeouts
    remain in the denominator (WO-040-CORR §12/§13/§14).
    """
    if candidate not in CANDIDATES:
        raise ValueError(f"candidate {candidate!r} not in {CANDIDATES}")
    if run_phase not in (PHASE_COLD, PHASE_WARM):
        raise ValueError(f"run_phase {run_phase!r} not in ({PHASE_COLD!r}, {PHASE_WARM!r})")
    if runner is None:
        runner = get_candidate_runner(candidate)
    if config is None:
        config = get_candidate_config(candidate)

    results: list[CandidateResult] = []
    for row in manifest_rows:
        audio_id = row.get("audio_id", "")
        audio_path = row.get("wav_path", "")
        reference = row.get("ground_truth", "") or ""
        callsigns = _parse_callsigns(row.get("callsigns_present", ""))

        # Input contract: load + verify the WAV master read-only (WO-040-CORR §6).
        try:
            audio_bytes, sample_rate, _channels, _sampwidth, audio_duration = _load_wav(audio_path)
        except Exception as exc:  # noqa: BLE001 - unreadable input -> failure, kept in denominator
            results.append(CandidateResult(
                audio_id=audio_id,
                candidate=candidate,
                audio_duration_seconds=None,
                status=STATUS_FAILURE,
                hypothesis="",
                reference=reference,
                callsigns_total=len(callsigns),
                callsigns_correct=0,
                wer=None,
                cer=None,
                callsign_accuracy=None,
                processing_time_seconds=None,
                latency_seconds=None,
                rtf=None,
                cpu_usage=None,
                ram_usage=None,
                gpu_usage="N/A",
                vram_usage="N/A",
                error=f"WAV unreadable: {exc}",
                timeout=False,
                run_phase=run_phase,
            ))
            continue

        # Candidate availability (WO-040-CORR §16): absent -> explicit NOT_AVAILABLE.
        if not config.available:
            results.append(CandidateResult(
                audio_id=audio_id,
                candidate=candidate,
                audio_duration_seconds=audio_duration,
                status=STATUS_NOT_AVAILABLE,
                hypothesis="",
                reference=reference,
                callsigns_total=len(callsigns),
                callsigns_correct=0,
                wer=None,
                cer=None,
                callsign_accuracy=None,
                processing_time_seconds=None,
                latency_seconds=None,
                rtf=None,
                cpu_usage=None,
                ram_usage=None,
                gpu_usage="N/A",
                vram_usage="N/A",
                error=config.availability_reason or "candidate unavailable",
                timeout=False,
                run_phase=run_phase,
            ))
            continue

        results.append(_run_one(
            audio_id=audio_id,
            candidate=candidate,
            audio_path=audio_path,
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            audio_duration=audio_duration,
            reference=reference,
            callsigns=callsigns,
            runner=runner,
            config=config,
            timeout_seconds=timeout_seconds,
            run_phase=run_phase,
        ))
    return results


# ---------------------------------------------------------------------------
# Genuine COLD/WARM lifecycle benchmark (WO-040-CORR-02 §4/§7/§8/§10/§12/§13).
# ---------------------------------------------------------------------------
def _build_result(
    audio_id: str,
    candidate: str,
    audio_duration_seconds: float | None,
    status: str,
    hypothesis: str = "",
    reference: str = "",
    callsigns_total: int = 0,
    callsigns_correct: int = 0,
    wer: float | None = None,
    cer: float | None = None,
    callsign_accuracy: float | None = None,
    processing_time_seconds: float | None = None,
    latency_seconds: float | None = None,
    rtf: float | None = None,
    cpu_usage: float | None = None,
    ram_usage: float | None = None,
    gpu_usage: str = "N/A",
    vram_usage: str = "N/A",
    error: str = "",
    timeout: bool = False,
    run_phase: str = PHASE_WARM,
) -> CandidateResult:
    """Construct a CandidateResult with documented defaults for special states."""
    return CandidateResult(
        audio_id=audio_id,
        candidate=candidate,
        audio_duration_seconds=audio_duration_seconds,
        status=status,
        hypothesis=hypothesis,
        reference=reference,
        callsigns_total=callsigns_total,
        callsigns_correct=callsigns_correct,
        wer=wer,
        cer=cer,
        callsign_accuracy=callsign_accuracy,
        processing_time_seconds=processing_time_seconds,
        latency_seconds=latency_seconds,
        rtf=rtf,
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        gpu_usage=gpu_usage,
        vram_usage=vram_usage,
        error=error,
        timeout=timeout,
        run_phase=run_phase,
    )


def execute_benchmark_lifecycle(
    manifest_rows: list[dict[str, Any]],
    candidate: str,
    config: CandidateConfig | None = None,
    timeout_seconds: float = 120.0,
    session: CandidateSession | None = None,
    session_factory: Callable[[], CandidateSession] | None = None,
) -> list[CandidateResult]:
    """Run the benchmark for one candidate using a genuine COLD/WARM lifecycle.

    Lifecycle (WO-040-CORR-02 §4/§10):

        create session
          -> initialize()          (COLD: runtime/model init, once)
          -> transcribe #1         (COLD: latency = init + inference)
          -> transcribe #2..N      (WARM: latency = inference only)
          -> close()

    The session is created and initialized exactly once and reused for every
    warm inference; the model is never reconstructed per warm input.  The first
    manifest row is executed as COLD and the remaining rows as WARM.  A failure
    during initialization is recorded as a failure of the cold phase; a failure
    or timeout during warm inference is recorded on that warm record and does
    not tear down or recreate the session (WO-040-CORR-02 §12).  An absent
    candidate runtime/model remains an explicit NOT_AVAILABLE (WO-040-CORR-02 §13).
    """
    if candidate not in CANDIDATES:
        raise ValueError(f"candidate {candidate!r} not in {CANDIDATES}")
    if config is None:
        config = get_candidate_config(candidate)

    # Create the session once (only needed when the candidate is available).
    init_time: float | None = None
    init_error: str | None = None
    if config.available:
        if session is None:
            factory = session_factory or (lambda: create_candidate_session(candidate, config))
            session = factory()
        # Initialize once (COLD).  A failure here is a failure of the cold phase.
        try:
            init_time = session.initialize()
        except Exception as exc:  # noqa: BLE001
            init_error = f"{type(exc).__name__}: {exc}"

    results: list[CandidateResult] = []
    for i, row in enumerate(manifest_rows):
        phase = PHASE_COLD if i == 0 else PHASE_WARM
        audio_id = row.get("audio_id", "")
        audio_path = row.get("wav_path", "")
        reference = row.get("ground_truth", "") or ""
        callsigns = _parse_callsigns(row.get("callsigns_present", ""))

        # Input contract: load + verify the WAV master read-only (WO-040-CORR §6).
        try:
            audio_bytes, sample_rate, _channels, _sampwidth, audio_duration = _load_wav(audio_path)
        except Exception as exc:  # noqa: BLE001 - unreadable input -> failure, kept in denominator
            results.append(_build_result(
                audio_id=audio_id, candidate=candidate,
                audio_duration_seconds=None, status=STATUS_FAILURE,
                reference=reference, callsigns_total=len(callsigns),
                error=f"WAV unreadable: {exc}", run_phase=phase,
            ))
            continue

        # Candidate unavailable -> explicit NOT_AVAILABLE (WO-040-CORR §16).
        if not config.available:
            results.append(_build_result(
                audio_id=audio_id, candidate=candidate,
                audio_duration_seconds=audio_duration, status=STATUS_NOT_AVAILABLE,
                reference=reference, callsigns_total=len(callsigns),
                error=config.availability_reason or "candidate unavailable",
                run_phase=phase,
            ))
            continue

        # Initialization failed -> no usable session; every record is a failure.
        if init_error is not None:
            results.append(_build_result(
                audio_id=audio_id, candidate=candidate,
                audio_duration_seconds=audio_duration, status=STATUS_FAILURE,
                reference=reference, callsigns_total=len(callsigns),
                error=init_error, run_phase=phase,
            ))
            continue

        # Cold latency includes initialization; warm latency is inference only.
        cold_init = init_time if phase == PHASE_COLD else None
        results.append(_run_one(
            audio_id=audio_id, candidate=candidate, audio_path=audio_path,
            audio_bytes=audio_bytes, sample_rate=sample_rate,
            audio_duration=audio_duration, reference=reference, callsigns=callsigns,
            runner=get_candidate_runner(candidate), config=config,
            timeout_seconds=timeout_seconds, run_phase=phase,
            session=session, init_time=cold_init,
        ))

    # Session cleanup (only if required).
    if session is not None:
        close_fn = getattr(session, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:  # noqa: BLE001 - cleanup must not mask results
                pass
    return results


# ---------------------------------------------------------------------------
# Aggregation (WO-040-CORR §14).
# ---------------------------------------------------------------------------
def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def aggregate_results(results: list[CandidateResult]) -> dict[str, Any]:
    """Aggregate per-record outcomes into candidate-level statistics.

    Reliability denominators include every record (failures/timeouts never
    disappear).  Recognition metrics use only records where a hypothesis and a
    reference are both available, unless a metric policy says otherwise.
    """
    total = len(results)
    success = sum(1 for r in results if r.status == STATUS_SUCCESS)
    failed = sum(1 for r in results if r.status in (STATUS_FAILURE, STATUS_NOT_AVAILABLE))
    timed_out = sum(1 for r in results if r.status == STATUS_TIMEOUT)

    latencies = [r.latency_seconds for r in results if r.latency_seconds is not None]
    rtfs = [r.rtf for r in results if r.rtf is not None]
    wers = [r.wer for r in results if r.wer is not None]
    cers = [r.cer for r in results if r.cer is not None]
    cs_total = sum(r.callsigns_total for r in results)
    cs_correct = sum(r.callsigns_correct for r in results)

    return {
        "total_inputs": total,
        "successful_inputs": success,
        "failed_inputs": failed,
        "timed_out_inputs": timed_out,
        "failure_rate": (failed / total) if total else None,
        "timeout_rate": (timed_out / total) if total else None,
        "mean_latency": _mean(latencies),
        "median_latency": _median(latencies),
        "mean_rtf": _mean(rtfs),
        "median_rtf": _median(rtfs),
        "mean_wer": _mean(wers),
        "mean_cer": _mean(cers),
        "callsign_accuracy": (cs_correct / cs_total) if cs_total else None,
        "callsigns_total": cs_total,
        "callsigns_correct": cs_correct,
    }


# ---------------------------------------------------------------------------
# ADR-014 mandatory gate (WO-040-CORR §17/§18).
# ---------------------------------------------------------------------------
def is_real_radio_transmission(row: dict[str, Any]) -> bool:
    """A row is a real radio transmission when provenance is not a test fixture.

    This deliberately does NOT count the WO-039 unit-test fixtures as real.  It
    is conservative: a recording must not be marked as a fixture by provenance.
    """
    provenance = row.get("provenance", "") or ""
    usable = str(row.get("usable", "")).lower() == "true"
    return usable and _is_real_radio_provenance(provenance)


def has_verified_ground_truth(row: dict[str, Any]) -> bool:
    """A row has a manually verified reference transcript (non-empty)."""
    return bool((row.get("ground_truth", "") or "").strip())


def adr014_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the ADR-014 mandatory dataset gate.

    A real, verified transmission must be a real radio recording (not a fixture)
    AND carry a manually verified reference transcript.
    """
    real = [r for r in rows if is_real_radio_transmission(r)]
    verified = [r for r in real if has_verified_ground_truth(r)]
    n_real = len(real)
    n_verified = len(verified)
    gate_satisfied = n_verified >= ADR014_MIN_REAL_TRANSMISSIONS
    return {
        "real_transmissions": n_real,
        "verified_transmissions": n_verified,
        "minimum_required": ADR014_MIN_REAL_TRANSMISSIONS,
        "gate_satisfied": gate_satisfied,
    }


# ---------------------------------------------------------------------------
# Results CSV persistence (WO-040-CORR §19) — deterministic, LF line endings.
# ---------------------------------------------------------------------------
def _csv_val(v: Any) -> str:
    """Serialize a value for CSV: None -> empty, float -> repr, bool -> true/false."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _result_to_row(r: CandidateResult) -> dict[str, Any]:
    failure = "true" if r.status in (STATUS_FAILURE, STATUS_NOT_AVAILABLE) else "false"
    return {
        "candidate": r.candidate,
        "audio_id": r.audio_id,
        "run_phase": r.run_phase,
        "status": r.status,
        "audio_duration_seconds": _csv_val(r.audio_duration_seconds),
        "reference": r.reference,
        "hypothesis": r.hypothesis,
        "wer": _csv_val(r.wer),
        "cer": _csv_val(r.cer),
        "callsign_accuracy": _csv_val(r.callsign_accuracy),
        "callsigns_total": r.callsigns_total,
        "callsigns_correct": r.callsigns_correct,
        "processing_time_seconds": _csv_val(r.processing_time_seconds),
        "latency_seconds": _csv_val(r.latency_seconds),
        "rtf": _csv_val(r.rtf),
        "cpu_usage": _csv_val(r.cpu_usage),
        "ram_usage": _csv_val(r.ram_usage),
        "gpu_usage": r.gpu_usage if r.gpu_usage is not None else "N/A",
        "vram_usage": r.vram_usage if r.vram_usage is not None else "N/A",
        "failure": failure,
        "timeout": "true" if r.timeout else "false",
        "error": r.error,
    }


def write_results_csv(results: list[CandidateResult], path: str) -> None:
    """Write per-record results to CSV using stable column order and LF endings."""
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for r in results:
            writer.writerow(_result_to_row(r))


def _not_executed_row(candidate: str) -> dict[str, Any]:
    """A NOT_EXECUTED placeholder row for the committed results file."""
    return {
        "candidate": candidate,
        "audio_id": "",
        "run_phase": "",
        "status": "NOT_EXECUTED",
        "audio_duration_seconds": "",
        "reference": "",
        "hypothesis": "",
        "wer": "",
        "cer": "",
        "callsign_accuracy": "",
        "callsigns_total": 0,
        "callsigns_correct": 0,
        "processing_time_seconds": "",
        "latency_seconds": "",
        "rtf": "",
        "cpu_usage": "",
        "ram_usage": "",
        "gpu_usage": "N/A",
        "vram_usage": "N/A",
        "failure": "false",
        "timeout": "false",
        "error": "Benchmark not executed: no real radio dataset and no local candidate runtime/model (WO-040-CORR §20).",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WO-040 STT benchmark harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="detect candidate engine/model availability")
    p.add_argument("--out", default=None)

    m = sub.add_parser("manifest", help="build dataset_manifest.csv")
    m.add_argument("--roots", nargs="*", default=DEFAULT_WAV_ROOTS)
    m.add_argument("--out", default="dataset_manifest.csv")

    r = sub.add_parser("run", help="execute the benchmark for one candidate (cold+warm lifecycle)")
    r.add_argument("--candidate", required=True, choices=CANDIDATES)
    r.add_argument("--manifest", default="dataset_manifest.csv")
    r.add_argument("--out", default="results.csv")
    r.add_argument("--timeout", type=float, default=120.0)
    r.add_argument("--language", default=None)
    r.add_argument("--device", default=None)

    met = sub.add_parser("metrics", help="compute WER/CER/callsign from a pair")
    met.add_argument("--reference", required=True)
    met.add_argument("--hypothesis", required=True)
    met.add_argument("--callsigns", nargs="*", default=[])

    gate = sub.add_parser("gate", help="evaluate the ADR-014 mandatory dataset gate")
    gate.add_argument("--manifest", default="dataset_manifest.csv")

    args = parser.parse_args(argv)

    if args.cmd == "probe":
        probes = probe_all()
        print(json.dumps(probes, indent=2))
        if args.out:
            with open(args.out, "w") as fh:
                json.dump(probes, fh, indent=2)
        return 0

    if args.cmd == "manifest":
        rows = build_manifest(args.roots)
        with open(args.out, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "audio_id", "wav_path", "source", "duration_s", "channels",
                "sampwidth", "sample_rate", "sha256", "ground_truth",
                "callsigns_present", "provenance", "usable", "real_transmission",
            ], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"manifest rows: {len(rows)} -> {args.out}")
        return 0

    if args.cmd == "run":
        rows = load_manifest(args.manifest)
        config = get_candidate_config(args.candidate, language=args.language, device=args.device)
        results = execute_benchmark_lifecycle(
            rows,
            args.candidate,
            config=config,
            timeout_seconds=args.timeout,
        )
        write_results_csv(results, args.out)
        agg = aggregate_results(results)
        print(json.dumps({
            "candidate": args.candidate,
            "config": asdict(config),
            "results_written": args.out,
            "records": len(results),
            "aggregate": agg,
        }, indent=2))
        return 0

    if args.cmd == "metrics":
        print(json.dumps({
            "wer": wer(args.reference, args.hypothesis),
            "cer": cer(args.reference, args.hypothesis),
            "callsign_accuracy": callsign_accuracy(args.callsigns, args.hypothesis),
        }, indent=2))
        return 0

    if args.cmd == "gate":
        rows = load_manifest(args.manifest)
        print(json.dumps(adr014_gate(rows), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
