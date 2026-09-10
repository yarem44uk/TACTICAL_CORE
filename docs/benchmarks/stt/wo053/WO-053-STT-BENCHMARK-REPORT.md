# WO-053 — STT Benchmark / Dataset Gate

**Work Order:** WO-053
**Date:** 2026-09-10
**Baseline:** `f7a6cba0dcdac80ca7f79c3e7d8e7f9d2daf1748` (accepted WO-052)
**Branch:** `wo-053-stt-benchmark-dataset-gate`
**Status:** **VERIFIED WITH FINDINGS** — benchmark gate tooling complete and
tested; real acoustic benchmark **NOT EXECUTED** because no STT engine / model
is provisioned on this host and the offline rule forbids download.

---

## Executive result

WO-053 established the STT benchmark **dataset gate** and **benchmark tooling**
(offline, stdlib-only, deterministic, reproducible), and discovered the actual
STT seam and candidate engines from repository evidence. It did **not** execute
a real acoustic benchmark, and it did **not** select a production STT engine.

The two recognised candidate engines — `faster_whisper` and `vosk` — are
**NOT AVAILABLE LOCALLY** on this host: neither module is installed in any
Python environment and no model file is present. Per the offline/no-network
rule, neither was downloaded. Consequently:

```
BENCHMARK EXECUTED (real acoustic inference): NO
CANDIDATES AVAILABLE:                         0 / 2
REAL TRANSMISSIONS IN DATASET:                0
ACCURACY (WER/CER):                           NOT COMPUTED (no engine ran)
PRODUCTION STT SELECTION:                     NOT AUTHORIZED IN WO-053
```

The benchmark **mechanics** — candidate discovery, NOT_AVAILABLE accounting,
dataset manifest determinism, WER/CER computation, result schema, offline
invariant, reproducibility — are implemented and validated by 43 passing tests.
The dataset **gate for real radio speech remains FAIL** (`0` real
transmissions, minimum `50`); the controlled **synthetic** dataset gate is PASS
**for mechanics only** and is explicitly not representative of real-world
Ukrainian/radio STT accuracy.

---

## Environment

Captured from `wo053_results.json` (live run, this host):

| Field | Value |
| --- | --- |
| Python | 3.13.5 (CPython) |
| Platform | Linux-6.12.48+deb13-cloud-amd64-x86_64-with-glibc2.41 |
| Machine | x86_64 |
| OS release | 6.12.48+deb13-cloud-amd64 |
| CPU count | 8 |
| Total RAM | 16,381,784 KB |
| Process peak RSS | 14,236 KB |

STT-relevant packages checked and **absent** in every environment
(`.venv`, `venv`, `tactical_core_venv`): `faster_whisper`, `ctranslate2`,
`vosk`, `whisper`, `torch`, `onnxruntime`, `soundfile`, `transformers`,
`librosa`, `ffmpeg-python`. No model file (`.bin`, `.onnx`, `.ggml`, `.pt`,
`.pth`, `.tflite`) exists anywhere in the repository.

---

## STT seam (discovered from repository evidence, not assumption)

The production STT subsystem is a **complete seam with NO production engine**:

1. Contract — `backend/app/contracts/audio.py` defines `ITranscriber`
   (`model`, `transcribe`, `is_ready`). The Core depends only on this.
2. Test transcriber — `backend/app/audio/transcriber.py` defines
   `DeterministicTestTranscriber`, a deliberately **non-acoustic** test
   transcriber (phrase-map by content id). It is the only `ITranscriber`
   present and is NOT production speech recognition.
3. Config — `backend/app/audio/stt_config.py` defines `SttConfig` and
   `SUPPORTED_ENGINES = {faster_whisper, vosk}`. Engine selection is
   explicitly `NOT_YET_JUSTIFIED`.
4. Adapter seam — `backend/app/audio/stt_seam.py` defines
   `AbstractSttAdapter`, `register_engine`, `build_transcriber`. **No engine is
   registered.** `build_transcriber` raises `SttEngineUnavailableError` for a
   recognised engine with no adapter — there is never a silent fallback to the
   test transcriber in a production STT configuration.
5. Worker — `backend/app/audio/stt_worker.py` defines `SttWorker` (bounded
   async queue). It is **fail-closed**: with no registered engine
   (`transcriber=None`) every job is rejected and recorded as `unavailable`; it
   never fabricates a transcript.

**Assessment (based on evidence):** STT is currently a seam, not a running
production engine. The engine decision is the province of WO-054 / ADR-014.

---

## Dataset

### Real radio dataset (Priority A)

**REAL RADIO SPEECH TRANSMISSION = NONE.** The only radio WAV masters on the
host are under `/opt/data/wo041_evidence/` and are the WO-039-B/C **unit-test
fixtures**: byte-identical constant-amplitude PCM **carrier tones** with no
speech, no words, no callsigns (SHA-256 `bccc3048...`, see WO-042). The
WO-041 real RTP capture (`radio_rtp.pcapng`) decoded to carrier noise/hiss, not
intelligible speech. This is a finding already documented by WO-042 and WO-043.

```
REAL TRANSMISSIONS:               0
UKRAINIAN RADIO RELEVANCE:        NOT ESTABLISHED by any dataset on this host
DATASET GATE (real):              FAIL  (minimum 50 required)
```

No real transcript / ground truth was fabricated.

### Controlled synthetic dataset (Priority B — mechanics only)

A deterministic synthetic set was generated solely to validate benchmark
mechanics. **It is not representative evidence of real-world Ukrainian/radio
STT accuracy.** Every fixture is a sine tone; no speech.

| audio_id | freq | duration | SHA-256 |
| --- | --- | --- | --- |
| wo053_tone_440 | 440 Hz | 2.0 s | `fbdb8188668684055f8a7cfe482e435b2a30bc5dddff13db26a83866bbf21a34` |
| wo053_tone_1000 | 1000 Hz | 3.0 s | `51894d3fc07961f3d56feba56b530a1e0665d355a1f1667434548b522317744d` |
| wo053_tone_880_short | 880 Hz | 0.8 s | `4c9685020b8990e5d1e6217076787a66e2c260894db5bab929694e9b670275d5` |
| wo053_tone_220 | 220 Hz | 1.5 s | `bfb8f0edf7a1a6f25090413365d84366f13c1517c7b95ed2c16dbb2155bc5b94` |

Generation: `wo053_dataset.write_synthetic_wav`, WAV/PCM/mono/16-bit/8000 Hz,
stdlib `wave` + `math`. Audio lives **external to Git** at
`/opt/data/wo053_audio/` (consistent with the WO-042/WO-043 convention); only
the manifest, tooling, results and report are committed. `real_transmission=false`,
`speech_present=false`, `transcript=""`, `ground_truth_verified=false`.

Dataset mechanics gate: **PASS** (4/4 valid, 0 real, 0 speech, no duplicate SHA).

---

## Method

1. **Normalization** — one deterministic policy used for every candidate:
   NFKC → casefold → keep letters (incl. Ukrainian, Unicode `L`), digits (`N`),
   apostrophe (`'`/`’`); hyphens and all other punctuation/symbol → space;
   collapse whitespace; trim. Documented in `wo053_normalize.py`.
2. **Metrics** — `WER = (S+D+I)/len(ref_words)` (word-level Levenshtein
   alignment), `CER = char_edit_distance/len(ref_char_stream)` (space-free char
   stream), `exact_match` (normalized equality). Defined in `wo053_metrics.py`.
3. **Dataset** — controlled synthetic manifest with SHA-256, format metadata,
   explicit synthetic/real/speech flags (`wo053_dataset.py`).
4. **Benchmark** — candidate discovery by importability; per candidate a
   `CandidateSession` lifecycle (`initialize` once → COLD = init + first
   inference; `transcribe` many → WARM = inference, session reused; `close`).
   An unavailable candidate is recorded `NOT_AVAILABLE` with an explicit reason.
   Machine-readable JSON is emitted (`wo053_benchmark.py`).
5. **Validation** — result schema + invariants checked by
   `wo053_validate_results.py` (candidate/dataset/input/environment presence,
   `production_selection_made == false`, availability-status consistency).

---

## Candidates

| Candidate | Available | Version | Model | Reason |
| --- | --- | --- | --- | --- |
| `faster_whisper` | **NO** | — | — | module not installed; no model file; offline rule forbids download |
| `vosk` | **NO** | — | — | module not installed; no model file; offline rule forbids download |

No candidate could be initialized or run. No accuracy, latency, RTF, or
resource measurement was produced for any candidate — none was fabricated.

---

## Results

**No acoustic inference was executed.** Therefore there is no WER, CER, exact
match, latency, RTF, cold load, warm inference, or GPU/VRAM result. The
machine-readable artifact (`wo053_results.json`) records:

```
benchmark_executed:        false
production_selection_made: false
candidates:                2  (both NOT_AVAILABLE)
runs per candidate:        0
```

The metric **mechanics** are validated in isolation by the test suite (e.g. a
one-word substitution yields WER 1/3; a one-char substitution yields CER 1/3;
punctuation-only difference yields WER 0), which is not evidence of real STT
accuracy.

### Reliability / determinism

* Tooling determinism: the dataset manifest is **byte-identical across runs**;
  the benchmark result is reproducible except for timestamp and runtime-only
  counters (asserted by tests).
* Inference determinism: **NOT ESTABLISHED** (no engine ran).
* Failures/timeouts/empty outputs: **N/A** (no inference).

---

## Limitations

1. **No STT engine / model provisioned** on this host; the benchmark could not
   run on any acoustic candidate.
2. **No real radio speech dataset.** The only real capture decodes to carrier
   tone, not intelligible speech. Real dataset gate is **FAIL** (0/50).
3. **Synthetic dataset is not representative.** It contains no speech and cannot
   establish any Ukrainian/radio STT relevance. This must not be extrapolated to
   operational accuracy.
4. **No ground truth** exists for real radio speech; none was invented.
5. Accuracy, latency, RTF and resource measurements are **absent** because no
   candidate executed — they are not merely "low", they were never measured.

---

## Reproducibility

Commands (run from `/opt/data/tactical_core_github`, `.venv` Python 3.13.5):

```bash
# 1. Generate synthetic dataset + manifest (audio external, in /opt/data/wo053_audio/)
.venv/bin/python docs/benchmarks/stt/wo053/wo053_dataset.py \
    generate --output-dir /opt/data/wo053_audio \
    --manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv

# 2. Validate the dataset manifest
.venv/bin/python docs/benchmarks/stt/wo053/wo053_dataset.py \
    validate --manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv \
    --audio-dir /opt/data/wo053_audio

# 3. Run the benchmark gate -> machine-readable JSON
.venv/bin/python docs/benchmarks/stt/wo053/wo053_benchmark.py \
    --dataset-manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv \
    --output-json docs/benchmarks/stt/wo053/wo053_results.json

# 4. Validate the result schema
.venv/bin/python docs/benchmarks/stt/wo053/wo053_validate_results.py \
    --results docs/benchmarks/stt/wo053/wo053_results.json

# 5. Run the mechanics tests
.venv/bin/python -m pytest -q \
    docs/benchmarks/stt/wo053/test_wo053_metrics.py \
    docs/benchmarks/stt/wo053/test_wo053_dataset.py \
    docs/benchmarks/stt/wo053/test_wo053_benchmark.py
```

All tooling is stdlib-only and offline (asserted by `test_no_network_imports`
and `test_no_download_or_model_fetch_in_source`).

---

## Architectural implications (evidence-based)

* STT is a well-formed seam (`ITranscriber` → `AbstractSttAdapter` →
  `build_transcriber`) with a fail-closed worker. No production code change is
  required to run a benchmark; the seam is ready for a provisioned engine.
* Candidate engines are currently **not available**; any WO-054 decision would
  need a provisioned, locally-present engine + model before a real benchmark is
  possible.
* The ADR-014 gate (50 verified real transmissions) is **NOT SATISFIED** — the
  dataset prerequisite (real radio speech + ground truth) is still unmet.

## Production recommendation

**NO PRODUCTION ENGINE SELECTION IS MADE IN WO-053.** The evidence does not
support choosing between `faster_whisper` and `vosk`: neither is available
locally and no real speech dataset exists to benchmark them. The selection is
the province of **WO-054 / ADR-014** and must wait until an engine + model is
provisioned locally and a real, verified radio dataset (≥50 real transmissions
with manual ground truth) exists.

---

## Scope gates

| Gate | Result |
| --- | --- |
| Production code (`backend/`) modified | **NO** |
| Production architecture modified | **NO** |
| WO-042 / WO-043 / WO-044 artifacts modified | **NO** |
| WO-050 artifacts modified | **NO** |
| WO-052 (`backend/tests/test_wo052_durable_journal.py`) modified | **NO** |
| Protected artifact `500` touched / modified / hashed | **NO** |
| `git diff --check` | PASS |
| Production STT selection | **NOT AUTHORIZED IN WO-053** |
| WO-054 readiness | **NO** (no engine, no real dataset) |
