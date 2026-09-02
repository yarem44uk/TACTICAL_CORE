# STT Engine Benchmark Area (WO-040)

This directory holds the benchmark evidence for the real acoustic speech-to-text
(STT) engine selection gate established by
[ADR-014](../../adr/ADR-014-Real-Acoustic-STT-Engine-Selection-and-Benchmark-Gate.md).

## Contents

| Artifact | Purpose |
| --- | --- |
| `run_benchmark.py` | Isolated, offline, stdlib-only benchmark harness. Probes candidate availability, builds the dataset manifest, and defines the WER / CER / callsign-accuracy metrics. Does not register an engine, does not alter `SUPPORTED_ENGINES`, does not replace the deterministic test transcriber. |
| `test_run_benchmark.py` | Benchmark-specific validation tests (offline, deterministic). |
| `dataset_manifest.csv` | The actual WAV masters discovered on the host, with format, SHA-256, provenance and ground-truth linkage. |
| `results.csv` | Benchmark results. Empty / `NOT_EXECUTED` — see the report. |
| `STT-ENGINE-BENCHMARK-REPORT.md` | The evidence report. |

## How to run

```bash
# Probe candidate engine + model availability (offline)
python3 run_benchmark.py probe

# Rebuild the dataset manifest from the discovered WAV roots
python3 run_benchmark.py manifest --out dataset_manifest.csv

# Compute metrics on a (reference, hypothesis) pair, with callsigns
python3 run_benchmark.py metrics --reference "alpha one bravo" \
    --hypothesis "alpha one bravo" --callsigns "alpha one" bravo

# Run the validation tests
python3 -m pytest test_run_benchmark.py -q
```

The harness requires only the Python standard library. It never downloads a
model, never installs a runtime package, never calls a network API, and opens
WAV masters read-only.

## Current status

The benchmark could **not** be executed on this host. See
`STT-ENGINE-BENCHMARK-REPORT.md` for the documented blockers. The production STT
decision remains `NOT_YET_JUSTIFIED`; no production STT engine is authorized.
