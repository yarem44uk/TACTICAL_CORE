"""WO-067 — Benchmark environment capture + resource measurement.

Benchmark-only, offline, stdlib-only (plus optional ``/proc`` reads on Linux).
Nothing here downloads, installs or imports an STT engine.

Environment capture (WO-067 §11) must be complete enough for the benchmark
result to be reproducible.  Resource measurement (WO-067 §10) never invents
GPU/VRAM values: when no GPU is present it reports
``GPU = NOT AVAILABLE``.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import asdict, dataclass


def _module_version(name: str) -> str | None:
    """Version of an installed module, or None when it is not importable.

    Uses ``importlib.metadata``/``find_spec`` only — the module is never
    imported, so no engine is loaded and no model is touched.
    """
    if importlib.util.find_spec(name) is None:
        return None
    try:
        from importlib.metadata import version

        try:
            return version(name)
        except Exception:  # noqa: BLE001 - distribution name may differ
            return _version_from_module(name)
    except Exception:  # noqa: BLE001 - metadata unavailable
        return _version_from_module(name)


def _version_from_module(name: str) -> str:
    """``module.__version__`` without running inference; 'unknown' if absent."""
    try:
        return getattr(__import__(name), "__version__", "unknown")
    except Exception:  # noqa: BLE001 - importable by spec but not by import
        return "unknown"


def _cpu_model() -> str | None:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _ram_bytes() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def ffmpeg_version() -> str | None:
    """First line of ``ffmpeg -version``, or None when ffmpeg is absent."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, timeout=15, check=False
        )
        first = (proc.stdout or "").splitlines()
        return first[0].strip() if first else None
    except Exception:  # noqa: BLE001
        return None


def gpu_info() -> dict:
    """Detect a GPU without inventing one.

    Returns ``{"available": False, "backend": None, ...}`` when nothing is
    present.  NVIDIA is probed via ``nvidia-smi`` when that binary exists.
    """
    info: dict = {
        "available": False,
        "backend": None,
        "devices": [],
        "vram_total_bytes": None,
        "note": "GPU = NOT AVAILABLE",
    }
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            proc = subprocess.run(
                [
                    smi,
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if lines and proc.returncode == 0:
                devices = []
                total = 0
                for ln in lines:
                    parts = [p.strip() for p in ln.split(",")]
                    name = parts[0] if parts else "unknown"
                    mem_mib = None
                    try:
                        mem_mib = int(float(parts[1]))
                        total += mem_mib * 1024 * 1024
                    except (IndexError, ValueError):
                        mem_mib = None
                    devices.append(
                        {
                            "name": name,
                            "vram_total_bytes": mem_mib * 1024 * 1024 if mem_mib else None,
                            "driver": parts[2] if len(parts) > 2 else None,
                        }
                    )
                info.update(
                    {
                        "available": True,
                        "backend": "cuda",
                        "devices": devices,
                        "vram_total_bytes": total or None,
                        "note": "GPU present (nvidia-smi)",
                    }
                )
        except Exception:  # noqa: BLE001 - absence is reported, not raised
            return info
    return info


def environment_snapshot(*, language: str, device: str) -> dict:
    """Capture the full reproducible environment description (WO-067 §11)."""
    gpu = gpu_info()
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "platform": sysconfig.get_platform(),
        "cpu_model": _cpu_model(),
        "cpu_core_count": os.cpu_count(),
        "ram_bytes": _ram_bytes(),
        "gpu": gpu,
        "gpu_available": gpu["available"],
        "vram_total_bytes": gpu.get("vram_total_bytes"),
        "ffmpeg_version": ffmpeg_version(),
        "packages": {
            "faster_whisper": _module_version("faster_whisper"),
            "vosk": _module_version("vosk"),
            "ctranslate2": _module_version("ctranslate2"),
            "onnxruntime": _module_version("onnxruntime"),
            "whisper": _module_version("whisper"),
            "torch": _module_version("torch"),
            "numpy": _module_version("numpy"),
        },
        "language": language,
        "device": device,
        "hostname_recorded": False,
    }


# ---------------------------------------------------------------------------
# Resource measurement during a run
# ---------------------------------------------------------------------------

@dataclass
class ResourceSample:
    """One resource sample taken around an inference."""

    cpu_user_seconds: float | None
    cpu_system_seconds: float | None
    wall_seconds: float
    peak_rss_bytes: int | None
    gpu_utilization_pct: float | None = None
    vram_used_bytes: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def read_peak_rss_bytes() -> int | None:
    """Peak RSS of this process in bytes, or None when unavailable."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is KiB on Linux, bytes on macOS.
        if sys.platform == "darwin":
            return int(usage.ru_maxrss)
        return int(usage.ru_maxrss) * 1024
    except Exception:  # noqa: BLE001
        return None


def read_cpu_times() -> tuple[float, float] | None:
    """(user, system) CPU seconds for this process, or None when unavailable."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return float(usage.ru_utime), float(usage.ru_stime)
    except Exception:  # noqa: BLE001
        return None


def sample_gpu_utilization() -> tuple[float | None, int | None]:
    """(utilization %, vram used bytes) or (None, None) when no GPU.

    Never fabricates a value; absence is reported as None and the aggregate
    reports GPU = NOT AVAILABLE.
    """
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None, None
    try:
        proc = subprocess.run(
            [
                smi,
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None, None
        first = next((ln for ln in proc.stdout.splitlines() if ln.strip()), None)
        if not first:
            return None, None
        parts = [p.strip() for p in first.split(",")]
        util = float(parts[0]) if parts and parts[0] not in ("", "N/A") else None
        used = (
            int(float(parts[1]) * 1024 * 1024)
            if len(parts) > 1 and parts[1] not in ("", "N/A")
            else None
        )
        return util, used
    except Exception:  # noqa: BLE001
        return None, None