# WO-069 — Real Radio STT Benchmark (controlled re-entry)

**Status:** benchmark implementation layer — measurement instrument only.
**Production engine decision:** NOT MADE (ADR-014 Part 2, Chief Systems Architect).

This directory is the WO-069 controlled re-entry of the real-radio STT
benchmark. It is **benchmark-only**, **offline**, **read-only on its inputs**
and **isolated from production**:

* it does NOT select, recommend or authorize a production STT engine;
* it does NOT modify, re-transcribe, re-label or normalize the human-review artifact;
* it does NOT import or modify any production file, and registers no engine in the
  production seam registry;
* it does NOT download a model, contact a network service or use cloud STT;
* it does NOT route audio through `EventFactory`, `EventPipeline`, `Observation`,
  the durable journal or the Operator Wall.

## Inputs (READ-ONLY)

| Input | Path (this environment) |
| --- | --- |
| WO-068 frozen dataset | `/opt/data/wo068_real_radio_stt_benchmark_v1` |
| Dataset manifest | `…/dataset/manifest.csv` |
| Audio | `…/dataset/audio/msg_0001.wav … msg_0067.wav` (8 kHz mono PCM16) |
| Ground-truth sidecar | `…/dataset/ground_truth/ground_truth.json` |
| Human listening review | `/opt/data/uploads/1789807255-6bf70d4b/human_review.csv` |

The work order names the dataset artifact `WO-068-HUMAN-REVIEW-EXTENDED.xlsx`.
That file is **absent** from this environment; the artifact that actually exists
is the human-review CSV above. The discrepancy is reported, never papered over —
see `artifact_resolution` in `dataset_manifest.json`
(`named_artifact_found: false`).

**Reference transcripts / callsigns:** the human-review artifact records
categorical listening labels only (`audible_voice`, `intelligible`,
`radio_style`, `speaker`, `dialogue_candidate`, `voice_type`, `confidence`). It
carries **no verbatim transcript and no callsign** for any message. Therefore
`reference_transcript_status = UNAVAILABLE` and WER / CER / callsign accuracy are
`NOT_MEASURED` — not estimated, not extrapolated, not substituted.

## Files

| File | Purpose |
| --- | --- |
| `wo069_dataset.py` | Read-only dataset + human-review loader, WAV integrity, dataset/artifact manifests |
| `wo069_metrics.py` | WER / CER / callsign / RTF / percentile (pure functions, one normalization) |
| `wo069_engine_worker.py` | Runs ONE engine in an isolated process; emits a JSONL per-file ledger |
| `wo069_runner.py` | Parent side: provisioning gate, process isolation, failure/OOM/timeout capture, ledger replay |
| `wo069_environment.py` | Environment + model + package capture for reproducibility |
| `wo069_report.py` | Evidence CSV/JSON writers + human-readable evidence report |
| `wo069_cli.py` | `dataset-gate` and `run` commands |
| `test_wo069_*.py` | Deterministic mechanics tests (no engine, no model, no real dataset) |
| `WO-069-EVIDENCE/` | Generated evidence set (see below) |

## Engines exercised

Both candidates are driven through the same dataset, the same language condition
and the same runtime, with no per-engine tuning apart from the documented
sample-rate parameterization:

1. **Faster-Whisper** (CTranslate2) — local bundled model, `cpu`, `compute_type=int8`,
   language auto-detect recorded, native 8 kHz input.
2. **Vosk** (Kaldi) — `vosk-model-uk-v3`, `cpu`, language `uk`, deterministic
   linear 8 kHz → 16 kHz upsample (the model hard-codes 16 kHz). The original
   8 kHz WAV remains the input of record and is never modified.

A candidate that cannot run is recorded `engine_status = FAILED` with the actual
reason. Nothing is faked.

## Reproduce

Dataset gate (read-only, no engine required — CI-safe):

```bash
python docs/benchmarks/stt/wo069/wo069_cli.py dataset-gate
```

Controlled benchmark (requires the provisioned engine venv and local models):

```bash
python docs/benchmarks/stt/wo069/wo069_cli.py run \
    --workdir /opt/data/wo069_runtime \
    --evidence-dir docs/benchmarks/stt/wo069/WO-069-EVIDENCE
```

Tests:

```bash
.venv/bin/python -m pytest -q docs/benchmarks/stt/wo069/
```

## Evidence set

```text
WO-069-EVIDENCE/
├── benchmark_results.csv        engine, model, message_id, status, reference_available,
│                                transcript_available, wer, cer, callsign_match,
│                                processing_time_ms, rtf, error
├── transcript_comparison.csv    human categorical label vs raw/normalized hypothesis
├── callsign_results.csv         callsign evaluation, SEPARATE from transcript WER/CER
├── runtime_metrics.csv          per-file latency, RTF, cold start (+ engine ALL rows)
├── resource_metrics.csv         peak RSS, CPU time, GPU/VRAM (NOT_AVAILABLE without a GPU)
├── environment_manifest.json    python, os, kernel, cpu, ram, gpu, package versions,
│                                model identity/size, dataset hash, timestamp, HEAD
├── dataset_manifest.json        record count, message ids, WAV count, total duration,
│                                dataset hash, reference counts, artifact resolution
├── benchmark_results.json       full machine-readable result document
└── WO-069-EVIDENCE-REPORT.md    human-readable evidence report
```

## Scope boundaries — WO-069 modifies nothing in production

Not touched by this layer: `backend/app/contracts/`, `audio/stt_seam.py`,
`audio/stt_config.py`, `audio/stt_worker.py`, `EventFactory`, `EventPipeline`,
the canonical Event / Observation models, the durable journal, the recording
architecture, `RadioEventIntegrator`, the Operator Wall, and the recurring
untracked `500`.

`500` is untouched.

## Synthetic fixtures

Every WAV produced by these tests is a **SYNTHETIC TEST FIXTURE** (a generated
constant-amplitude tone). Fixtures validate harness mechanics only and never
enter a real benchmark result. No TTS speech, artificial transcript or simulated
engine timing is generated anywhere in this layer.
