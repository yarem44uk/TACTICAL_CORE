# STT Engine Benchmark Area (WO-040 / WO-040-CORR)

This directory holds the benchmark evidence for the real acoustic speech-to-text
(STT) engine selection gate established by
[ADR-014](../../adr/ADR-014-Real-Acoustic-STT-Engine-Selection-and-Benchmark-Gate.md).

## Contents

| Artifact | Purpose |
| --- | --- |
| `run_benchmark.py` | Isolated, offline, stdlib-only benchmark harness. Probes candidate availability, builds the dataset manifest, executes a candidate over the manifest (measuring latency / RTF / CPU / RAM / GPU / VRAM, WER / CER / callsign accuracy, failures and timeouts), aggregates per-record results, and evaluates the ADR-014 mandatory gate. Does not register an engine, does not alter `SUPPORTED_ENGINES`, does not replace the deterministic test transcriber. |
| `test_run_benchmark.py` | Benchmark-specific validation tests (offline, deterministic; use fake runners, never treated as real evidence). |
| `dataset_manifest.csv` | The actual WAV masters discovered on the host, with format, SHA-256, provenance, ground-truth linkage, and a `real_transmission` marker. |
| `results.csv` | Benchmark results in the per-record result model. Currently `NOT_EXECUTED` — see the report. |
| `STT-ENGINE-BENCHMARK-REPORT.md` | The evidence report. |

## How to run

```bash
# Probe candidate engine + model availability (offline)
python3 run_benchmark.py probe

# Rebuild the dataset manifest from the discovered WAV roots
python3 run_benchmark.py manifest --out dataset_manifest.csv

# Execute the benchmark for one candidate over the manifest (offline)
python3 run_benchmark.py run --candidate faster_whisper --manifest dataset_manifest.csv \
    --out results.csv --phase warm --timeout 120

# Evaluate the ADR-014 mandatory dataset gate (>= 50 verified real transmissions)
python3 run_benchmark.py gate --manifest dataset_manifest.csv

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

Tooling status: the benchmark harness is implemented and validated
(`docs/benchmarks/stt/test_run_benchmark.py` passes). It is capable of
performing the benchmark when a local candidate runtime/model and a dataset of
real radio recordings are provisioned.

Benchmark execution status: **NOT EXECUTED**. On this host no candidate runtime
or model is installed and no real radio recording exists (the only WAV masters
are WO-039 unit-test fixtures). See `STT-ENGINE-BENCHMARK-REPORT.md` for the
documented blockers. The production STT decision remains `NOT_YET_JUSTIFIED`;
no production STT engine is authorized; the ADR-014 gate is **NOT SATISFIED**.
