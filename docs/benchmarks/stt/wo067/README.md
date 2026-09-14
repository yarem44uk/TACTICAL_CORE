# WO-067 — Real Radio STT Benchmark (tooling)

**Status:** benchmark implementation layer — measurement instrument only.

This directory holds the WO-067 benchmark layer. It is **benchmark-only**,
**offline** and **isolated**:

* it does NOT select, recommend or authorize a production STT engine;
* it does NOT modify any production file;
* it does NOT register an engine in the production seam registry;
* it does NOT download a model, contact a network service, or use cloud STT.

The production engine decision belongs to the Chief Systems Architect in
**WO-068**. See `ADR-014` for the architecture and the activation gate, and
`docs/benchmarks/stt/wo053/` for the preceding WO-053 dataset/benchmark gate.

## Provenance — two independent questions

```text
TRANSPORT PROVENANCE
  CubicCore traffic generator v7.19.4 over a simulated L2/L3 topology.
  Software test topology. No RF/SDR provenance. No real radio capture.

AUDIO CONTENT PROVENANCE
  Human speech — confirmed by the CSA human listening review of the
  WO-067-PRE-04 package. This is INDEPENDENT of the transport finding.
```

`transport = CubicCore` does **not** imply `audio = synthetic`.
`audio = human speech` does **not** imply `transport = real radio capture`.
This layer makes no claim of real-radio RF provenance.

## Evidence source

Authoritative input: `WO-067-PRE-04-HUMAN-REVIEW-PACKAGE.zip` (accepted).

* 67 candidate WAVs — S1: 44, S2: 23
* lossless PCM, 16-bit, mono, 8000 Hz, no denoise / normalization / gain /
  pitch / speed modification
* provenance linked to the source PCAP
  `0c9a0716d904d025079ecba00c585dfcac699351917dc804dffb0b4d4cd1eb20`
* the PRE-04 reconstruction correction is authoritative; the obsolete PRE-03
  S1 reconstruction is NOT used

The dataset lives **outside** the repository. No evidence audio is committed
and no Git LFS is used. `wo067_dataset_manifest.csv` records paths and SHA-256
digests only.

## Files

| File | Purpose |
| --- | --- |
| `wo067_normalize.py` | One deterministic transcript normalization for all candidates |
| `wo067_metrics.py` | WER / CER / exact-match / RTF / callsign metrics (pure functions) |
| `wo067_dataset.py` | Manifest loader, WAV integrity verifier, ground-truth loader |
| `wo067_engines.py` | Benchmark-local engine adapters (faster_whisper, vosk) + availability gate |
| `wo067_environment.py` | Environment capture + resource measurement (never invents GPU) |
| `wo067_benchmark.py` | Run accounting, aggregation, result serialization |
| `wo067_report.py` | Human-readable Markdown report generator |
| `wo067_cli.py` | Benchmark CLI (`dataset-gate`, `run`) |
| `wo067_dataset_manifest.csv` | The 67 accepted candidates + provenance + ground-truth state |
| `wo067_ground_truth.json` | Human ground-truth sidecar (empty; never auto-filled) |
| `test_wo067_*.py` | Deterministic mechanics tests (no engine, no model, no dataset) |

## Ground truth — human only

WER/CER and callsign accuracy are computed **only** against explicit human
ground truth entered in `wo067_ground_truth.json`. Model output is never used
as a substitute for human ground truth.

The PRE-04 CSV carries no transcripts, so until a human enters them:

```text
WER                    = NOT MEASURED
CER                    = NOT MEASURED
CALLSIGN ACCURACY      = NOT MEASURED
```

## Reproduce

Run from the repository root with the project `.venv` Python 3.13.5.

Dataset gate (read-only, no engine required — CI-safe):

```bash
.venv/bin/python docs/benchmarks/stt/wo067/wo067_cli.py dataset-gate \
    --manifest docs/benchmarks/stt/wo067/wo067_dataset_manifest.csv
```

Full benchmark (requires a locally provisioned engine **and** model; nothing is
downloaded):

```bash
.venv/bin/python docs/benchmarks/stt/wo067/wo067_cli.py run \
    --manifest docs/benchmarks/stt/wo067/wo067_dataset_manifest.csv \
    --ground-truth docs/benchmarks/stt/wo067/wo067_ground_truth.json \
    --engine faster_whisper --model-path /path/to/provisioned/model \
    --language uk --device cpu \
    --output docs/benchmarks/stt/wo067/wo067_benchmark_results.json

.venv/bin/python docs/benchmarks/stt/wo067/wo067_report.py \
    --results docs/benchmarks/stt/wo067/wo067_benchmark_results.json
```

Tests (no GPU, no model, no real dataset required; synthetic fixtures only):

```bash
.venv/bin/python -m pytest -q docs/benchmarks/stt/wo067/
```

## Measurement policy

* **RTF** is explicitly `RTF = processing_time / audio_duration`.
* **Timing:** per-file latency, median, p95 (nearest rank), min, max.
* **Reliability:** successful / failed / timeout / unavailable runs, exception
  count, failure rate. A failed run stays in the denominator.
* **Resources:** CPU user time, peak RSS, GPU / VRAM when present. With no GPU
  the value is `NOT_AVAILABLE` / `GPU = NOT AVAILABLE` — never invented.
* **Accuracy:** WER, CER, exact match; callsign accuracy only when human ground
  truth explicitly identifies a callsign (outcomes distinguished as exact /
  normalized / missed / false / not present).
* Model parameters are fixed per engine and never varied between candidates.
* Existing authoritative results are never overwritten — a versioned sibling is
  written instead.

## Scope boundaries — WO-067 modifies nothing in production

Not touched by this layer: `EventFactory`, `EventPipeline`,
`ObservationService`, `EventIdentityResolver`, recording identity, RTP
segmentation, VAD, `TransmissionRecorder`, the WAV writer, WO-062 playback /
evidence path, WO-064 enrichment, WO-065 final radio event, WO-066 production
E2E composition, the chronological wall, the durable journal, and production
observation semantics. The production STT seam is *reused* (contract +
offline-init lifecycle), never redesigned.

`500` is untouched.

## Synthetic fixtures

Every WAV produced by these tests is a **SYNTHETIC TEST FIXTURE** (a generated
constant-amplitude tone). Fixtures validate harness mechanics only and never
enter a real benchmark result. No TTS speech, synthetic radio speech, artificial
transcript or simulated engine timing is generated anywhere in this layer.