"""WO-069 — Environment capture for reproducibility.

Records the ACTUAL environment: interpreter, OS/kernel, CPU, RAM, GPU presence,
engine package versions, model identity/size and dataset digests.  Values that
cannot be measured are reported ``UNKNOWN`` — never invented.  GPU is reported
``NOT AVAILABLE`` when no GPU tooling exists.

Nothing here imports an engine into the harvester process: engine package
versions are queried in the provisioned interpreter via a short subprocess.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone

UNKNOWN = "UNKNOWN"
NOT_AVAILABLE = "NOT_AVAILABLE"

_PACKAGES_OF_INTEREST = (
    "faster_whisper",
    "ctranslate2",
    "vosk",
    "cffi",
    "numpy",
    "onnxruntime",
    "av",
    "tokenizers",
)


def _read_first(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or UNKNOWN


def memory_total_bytes() -> int | str:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return UNKNOWN


def cgroup_memory_max() -> str:
    value = _read_first("/sys/fs/cgroup/memory.max")
    return value if value else UNKNOWN


def gpu_snapshot() -> dict:
    """GPU / VRAM presence. Never invents a GPU."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"gpu": NOT_AVAILABLE, "gpu_memory": NOT_AVAILABLE,
                "gpu_evidence": "nvidia-smi not found"}
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total",
                              "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return {"gpu": out.stdout.strip(), "gpu_memory": out.stdout.strip(),
                    "gpu_evidence": "nvidia-smi"}
    except Exception as exc:  # noqa: BLE001
        return {"gpu": NOT_AVAILABLE, "gpu_memory": NOT_AVAILABLE,
                "gpu_evidence": f"nvidia-smi failed: {type(exc).__name__}"}
    return {"gpu": NOT_AVAILABLE, "gpu_memory": NOT_AVAILABLE, "gpu_evidence": "nvidia-smi empty"}


def interpreter_snapshot(python_path: str) -> dict:
    """Interpreter version + package versions inside a provisioned interpreter."""
    if not python_path or not os.path.exists(python_path):
        return {"python_path": python_path, "python_version": UNKNOWN, "package_versions": {}}
    probe = (
        "import importlib.util,json,sys\n"
        "out={'python_version':sys.version.split()[0]}\n"
        "names=%r\n"
        "pkg={}\n"
        "for n in names:\n"
        "    try:\n"
        "        from importlib.metadata import version\n"
        "        pkg[n]=version(n)\n"
        "    except Exception:\n"
        "        pkg[n]=None\n"
        "out['package_versions']=pkg\n"
        "print(json.dumps(out))\n"
    ) % (_PACKAGES_OF_INTEREST,)
    try:
        proc = subprocess.run(
            [python_path, "-c", probe],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONPATH": "", "PYTHONNOUSERSITE": "1"},
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            data["python_path"] = python_path
            return data
    except Exception as exc:  # noqa: BLE001
        return {"python_path": python_path, "python_version": UNKNOWN,
                "package_versions": {}, "error": f"{type(exc).__name__}: {exc}"}
    return {"python_path": python_path, "python_version": UNKNOWN, "package_versions": {}}


def model_snapshot(model_path: str | None) -> dict:
    """Model identity and on-disk size. No download, no execution."""
    if not model_path or not os.path.exists(str(model_path)):
        return {"model_path": model_path, "model_present": False,
                "model_version": UNKNOWN, "model_size_bytes": UNKNOWN}
    total = 0
    revision = None
    if os.path.isdir(model_path):
        for dirpath, _dirnames, filenames in os.walk(model_path):
            for name in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    pass
        for marker in ("SHA256SUMS", "version", "MODEL_PROVENANCE.md", "README.md"):
            candidate = os.path.join(model_path, marker)
            if os.path.exists(candidate):
                revision = marker
                break
    else:
        total = os.path.getsize(model_path)
    return {
        "model_path": str(model_path),
        "model_present": True,
        "model_version": revision or UNKNOWN,
        "model_size_bytes": total,
    }


def dataset_hash(paths: list[str]) -> str:
    """Deterministic composite digest over the dataset inputs (read-only)."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not path or not os.path.exists(path):
            digest.update(b"|absent|")
            digest.update(str(path).encode("utf-8"))
            continue
        digest.update(str(path).encode("utf-8"))
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()


def environment_snapshot(
    *,
    specs: list,
    dataset_paths: list[str],
    repo_head: str | None = None,
) -> dict:
    """Full reproducibility snapshot for the benchmark run."""
    gpu = gpu_snapshot()
    interpreters = {}
    engines = []
    for spec in specs:
        interpreters[spec.engine] = interpreter_snapshot(spec.venv_python)
        model = model_snapshot(spec.model_path)
        engines.append(
            {
                "engine": spec.engine,
                "display_name": spec.display_name,
                "device": spec.device,
                "compute_type": spec.compute_type,
                "language": spec.language,
                "python_path": interpreters[spec.engine].get("python_path"),
                "model": model,
                "model_revision": spec.model_revision or UNKNOWN,
                "package_versions": interpreters[spec.engine].get("package_versions", {}),
            }
        )
    return {
        "schema": "wo069-environment-manifest-v1",
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "kernel": _read_first("/proc/sys/kernel/osrelease") or platform.release() or UNKNOWN,
        "cpu": cpu_model(),
        "cpu_count": os.cpu_count(),
        "ram": memory_total_bytes(),
        "cgroup_memory_max": cgroup_memory_max(),
        "gpu": gpu["gpu"],
        "gpu_memory": gpu["gpu_memory"],
        "gpu_evidence": gpu["gpu_evidence"],
        "engine": [e["engine"] for e in engines],
        "model": [e["model"]["model_path"] for e in engines],
        "model_revision": [e["model_revision"] for e in engines],
        "package_versions": {e["engine"]: e["package_versions"] for e in engines},
        "engines": engines,
        "interpreter_python_paths": {
            e["engine"]: e["python_path"] for e in engines
        },
        "dataset_hash": dataset_hash(dataset_paths),
        "benchmark_timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_head": repo_head or UNKNOWN,
    }
