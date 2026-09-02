# STT Engine Benchmark Area (WO-040 / WO-040-CORR)

This directory holds the benchmark evidence for the real acoustic speech-to-text
(STT) engine selection gate established by
[ADR-014](../../adr/ADR-014-Real-Acoustic-STT-Engine-Selection-and-Benchmark-Gate.md).

## Contents

| Artifact | Purpose |
| --- | --- |
| `run_benchmark.py` | Isolated, offline, stdlib-only benchmark harness. Probes candidate availability, builds the dataset manifest, executes a candidate over the manifest using a genuine COLD/WARM session lifecycle (measuring latency / RTF / CPU / RAM / GPU / VRAM, WER / CER / callsign accuracy, failures and timeouts), aggregates per-record results, and evaluates the ADR-014 mandatory gate. Does not register an engine, does not alter `SUPPORTED_ENGINES`, does not replace the deterministic test transcriber. |
| `test_run_benchmark.py` | Benchmark-specific validation tests (offline, deterministic; use fake runners/sessions, never treated as real evidence). |
| `dataset_manifest.csv` | The actual WAV masters discovered on the host, with format, SHA-256, provenance, ground-truth linkage, and a `real_transmission` marker. WO-041 regenerated this to the WO-041 schema; all 36 rows are WO-039 unit-test fixtures (`real_transmission=false`, empty ground truth). |
| `results.csv` | Benchmark results in the per-record result model. Currently `NOT_EXECUTED` — see the report. |
| `validate_dataset.py` | WO-041 offline dataset validator. Validates manifest integrity, real-transmission classification, ground-truth presence, SHA-256 uniqueness, WAV validity, and the >=50 real-transmission dataset gate. Engine-neutral, stdlib-only, read-only, no STT inference. |
| `test_validate_dataset.py` | WO-041 dataset-validator validation tests (offline, deterministic, synthetic fixtures — never treated as real evidence). |
| `STT-DATASET-REPORT.md` | WO-041 dataset report. Gate result: FAIL — 0 valid real transmissions. |
| `STT-ENGINE-BENCHMARK-REPORT.md` | The evidence report. |

## How to run

```bash
# Probe candidate engine + model availability (offline)
python3 run_benchmark.py probe

# Rebuild the dataset manifest from the discovered WAV roots
python3 run_benchmark.py manifest --out dataset_manifest.csv

# Execute the benchmark for one candidate over the manifest (offline).
# This runs a genuine COLD/WARM lifecycle: the first record is executed as COLD
# (candidate initialization + inference) and the remaining records as WARM
# (inference only, reusing the already-initialized candidate session).
python3 run_benchmark.py run --candidate faster_whisper --manifest dataset_manifest.csv \
    --out results.csv --timeout 120

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

## COLD vs WARM lifecycle semantics

The harness executes each candidate through a session lifecycle
(WO-040-CORR-02):

```text
create session
    -> initialize()          (COLD: runtime/model initialization, exactly once)
    -> transcribe #1         (COLD: latency = initialization + inference)
    -> transcribe #2..N      (WARM: latency = inference only, model reused)
    -> close()
```

- **COLD** includes candidate/runtime/model initialization plus one inference.
  Cold latency = initialization time + inference time.
- **WARM** reuses the already-initialized candidate/session; it runs inference
  only and never reconstructs the model. Warm latency = inference time.

For `faster_whisper`, the `WhisperModel` is constructed once in `initialize()`
and reused for every warm transcription. For `vosk`, the `Model` is constructed
once and reused; only a per-input `KaldiRecognizer` (whose state must be reset
per audio sample) is created, while the expensive model object is shared.

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
