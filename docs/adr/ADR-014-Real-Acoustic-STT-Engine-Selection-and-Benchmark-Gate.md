# ADR-014 — STT Engine Selection and Production Architecture

**Date:** 2026-09-10
**Status:** Accepted — engine-agnostic STT architecture (Part 1)
**Production engine decision:** DEFERRED (Part 2)
**Production activation:** BLOCKED pending benchmark / data gate
**Deciders:** Chief Systems Architect

---

## Context

TACTICAL CORE has a complete, engine-neutral speech-to-text seam but **no
production engine**. The production STT subsystem is a seam, not a running
engine. This is established from repository evidence (WO-053), not assumption.

The production seam is:

```text
RTP -> PCM/VAD -> WAV master (authoritative audio)
     -> STT seam / ITranscriber
        -> AbstractSttAdapter -> engine-specific runtime -> model
        -> bounded SttWorker (background queue)
     -> derived transcript raw dict
     -> canonical event (content_id = <audio_recording_id>|transcript)
```

The five seam components (all in `backend/app/`):

1. **Contract** — `contracts/audio.py` defines `ITranscriber` (ABC):
   `model` property, `transcribe(audio_data, language=None) -> str`,
   `is_ready() -> bool`. The Core depends only on this interface.

2. **Test transcriber** — `audio/transcriber.py` defines
   `DeterministicTestTranscriber` plus the richer `transcribe_detailed` seam and
   `TranscriptResult`. It is a **deliberately non-acoustic** test transcriber that
   maps a controlled `content_id` to a known transcript via a configurable phrase
   table. It is NOT production speech recognition.

3. **Configuration** — `audio/stt_config.py` defines `SttConfig` (frozen
   dataclass: `enabled`, `engine`, `model_path`, `language`, `device`,
   `model_root`), `SUPPORTED_ENGINES = frozenset({"faster_whisper", "vosk"})`,
   `resolve_model_path()` (deterministic, path-traversal guarded, never reaches
   the network, never downloads a model, never executes the model as a program),
   and `SttConfigError`.

4. **Adapter seam** — `audio/stt_seam.py` defines `AbstractSttAdapter`
   (`ITranscriber` + the offline `initialize(config)` lifecycle hook behind the
   adapter boundary), `register_engine(engine_id, factory)`, and
   `build_transcriber(config)`, with `SttEngineError` / `SttEngineUnknownError` /
   `SttEngineUnavailableError`. **No engine is registered.** For a *recognised*
   engine with no registered adapter, `build_transcriber` raises
   `SttEngineUnavailableError` — there is never a silent fallback to
   `DeterministicTestTranscriber` in a production STT configuration.

5. **Worker** — `audio/stt_worker.py` defines `SttWorker` (bounded async queue on
   a dedicated daemon thread `wo039c-stt-worker`), `SttJob` (carries the
   recording reference, never the PCM payload), `build_transcript_raw` (derives
   the transcript raw dict with `content_id = <audio_recording_id>|transcript`,
   distinct from the source recording event), and `read_wav_readonly` (opens the
   WAV master read-only and computes its SHA-256). The worker is **fail-closed**:
   with no registered engine (`transcriber=None`) its state is `UNAVAILABLE`,
   every job is rejected and recorded as an observable `unavailable` failure, and
   it never fabricates a transcript.

**Integration** (`audio/source_adapter.py`): `_build_production_stt_worker` reads
the source `definition.config["stt"]` block, builds an `SttConfig`, calls
`build_transcriber`, and wraps the result in an `SttWorker`. The worker's
`on_transcript` hook queues the derived transcript raw dict into the adapter's
`read_events()` queue, from which it flows through the existing `EventFactory`
into the canonical Event path. The adapter exposes `stt_state()` returning
`DISABLED` / `UNAVAILABLE` / `AVAILABLE`. Per WO-041-CORR F-01/F-03, there is no
packet-level STT and no fallback to `DeterministicTestTranscriber`; the finalized
WAV master is the only STT input.

### WO-053 evidence (must be preserved)

WO-053 (`docs/benchmarks/stt/wo053/WO-053-STT-BENCHMARK-REPORT.md`, Status:
VERIFIED WITH FINDINGS) established:

```text
benchmark infrastructure:      VERIFIED   (offline, stdlib-only, deterministic,
                                           43 passing mechanics tests)
real acoustic benchmark:       NOT EXECUTED
real radio speech dataset:     NOT AVAILABLE
candidate engines available:   0 / 2  (faster_whisper, vosk)
real transmissions in dataset: 0   (dataset gate FAIL: minimum 50 required)
WER / CER:                     NOT COMPUTED  (no engine ran)
production STT selection:      NOT PERFORMED / NOT AUTHORIZED
```

Neither candidate engine is available on this host — `faster_whisper`, `vosk`,
`ctranslate2`, `whisper`, and `torch` are all absent from every Python
environment, and no model file (`.bin`, `.onnx`, `.ggml`, `.pt`, `.pth`,
`.tflite`) exists in the repository. Per the offline / no-network rule, neither
was downloaded. The only radio WAV masters on the host are the WO-039-B/C
unit-test fixtures: byte-identical constant-amplitude PCM **carrier tones** with
no speech, no words, and no callsigns. The controlled synthetic dataset is
**mechanics-only** and is explicitly not representative of real Ukrainian / radio
STT accuracy.

### WO-053 harness findings (preserved as known limitations)

The WO-053 benchmark harness is **infrastructure-ready but not yet a complete
production inference runner**. The following WO-053 findings are preserved here
as known limitations. They are documentation only — they are **not corrected in
WO-054** and are explicitly follow-up engineering work:

1. `benchmark_executed` is derived from candidate availability
   (`any(c["available"] ...)`) rather than from the actual run count. If a
   candidate module were importable, `benchmark_executed` would report `true`
   even when `runs == []`.
2. `_run_available_lifecycle` is a documented placeholder that always returns
   `[]`; it does not execute a real `CandidateSession` lifecycle
   (`initialize` once → COLD, `transcribe` many → WARM, `close`). The harness
   therefore cannot run acoustic inference even if a candidate module were
   installed.
3. Candidate availability is determined by module importability
   (`importlib.util.find_spec`) only, not by complete model readiness — an
   installed module with no provisioned model would be reported `AVAILABLE`.
4. Consequently, the harness validates benchmark mechanics (candidate
   discovery, NOT_AVAILABLE accounting, result schema) but is not yet a complete
   production inference runner.

These findings must be corrected by follow-up engineering work (explicitly **not**
within WO-054 scope) before the harness can produce trustworthy real acoustic
results.

## Problem

Binding the production runtime to a specific STT engine without objective,
reproducible, evidence-backed comparison would (a) discard the deliberately
engine-neutral seam, (b) create an unjustified technology lock-in, and (c) commit
the system to a technology choice made in the absence of measured evidence.
Because no real acoustic benchmark has been executed, there is currently **no
empirical basis** to choose between the recognized candidates.

## Decision

The architectural decision is made in two separable parts.

### Part 1 — Architecture (ratified now)

The production Core remains **engine-agnostic**. The Core depends only on
`ITranscriber`; a concrete STT engine is selected and instantiated exclusively
through configuration and factory registration. The protected architectural seam
is:

```text
ITranscriber
    |
    +-- AbstractSttAdapter
            |
            +-- FasterWhisperAdapter        (future)
            |
            +-- VoskAdapter                 (future)
            |
            +-- <future adapter>
```

The following are the protected architectural boundary, and the Core event
architecture MUST NOT depend on a concrete engine:

```text
ITranscriber
AbstractSttAdapter
register_engine()
build_transcriber()
SttWorker
```

Engine-specific implementation MUST be replaceable without changing: the
canonical Event model, `EventFactory`, `EventPipeline`, the durable journal,
radio source identity, radio segmentation, or the existing audio recording
architecture. The Core never hard-codes an engine.

### Part 2 — Engine selection (DEFERRED)

Production acoustic STT engine selection is **DEFERRED**. It is not made in this
ADR. There is insufficient evidence even for a conditional selection: neither
candidate has been evaluated (both are unavailable locally), no real radio speech
dataset or ground truth exists, and the architecture seam is deliberately neutral
and does not favor either candidate. Selecting or conditionally selecting an
engine now would be an assumption, not an evidence-based decision.

Production activation of any STT engine remains **blocked** until the production
activation gate (below) is satisfied. This ADR does NOT claim that any candidate
has won WER/CER testing, and it does NOT authorize implementation, registration,
or runtime integration of any engine.

## Candidate evaluation

The recognized candidate set is `faster_whisper` and `vosk`
(`SUPPORTED_ENGINES` in `audio/stt_config.py`). Recognition as a candidate
carries no authorization to implement, register, or integrate the engine.

For every cell, `NOT ESTABLISHED` means there is no evidence in the repository or
environment; it is not a claim of absence of capability. No numerical score is
assigned because no empirical measurement exists.

| Dimension | faster_whisper | vosk |
| --- | --- | --- |
| Architecture | Whisper-family seq2seq / CTranslate2 decoder | Kaldi-based, streaming-capable HMM/GMM or neural |
| Local / offline | NOT ESTABLISHED | NOT ESTABLISHED |
| Ukrainian capability | NOT ESTABLISHED | NOT ESTABLISHED |
| Model availability (local) | NOT AVAILABLE (no model file, no download) | NOT AVAILABLE (no model file, no download) |
| Model size | NOT ESTABLISHED | NOT ESTABLISHED |
| CPU suitability | NOT ESTABLISHED | NOT ESTABLISHED |
| GPU suitability | NOT ESTABLISHED | NOT ESTABLISHED |
| Streaming suitability | NOT ESTABLISHED | NOT ESTABLISHED |
| Batch suitability | NOT ESTABLISHED | NOT ESTABLISHED |
| Expected latency | NOT ESTABLISHED | NOT ESTABLISHED |
| Expected accuracy | NOT ESTABLISHED | NOT ESTABLISHED |
| Licensing | NOT VERIFIED — requires authoritative source before production | NOT VERIFIED — requires authoritative source before production |
| Operational complexity | NOT ESTABLISHED | NOT ESTABLISHED |
| Evidence status | NOT_AVAILABLE locally (WO-053) | NOT_AVAILABLE locally (WO-053) |

### Evaluated dimensions

The matrix is evaluated against the following dimensions. Absent any local engine
or model, every cell is `NOT ESTABLISHED` (no evidence in the repository or
environment), not a claim of absent capability:

- **Accuracy:** Ukrainian WER, Ukrainian CER, radio/noise robustness, short
  utterances, tactical terminology, callsigns, digits/numbers, accented or
  distorted speech, fragmented transmissions.
- **Performance:** real-time factor, cold-start latency, warm inference latency,
  throughput, concurrency, sustained operation.
- **Resources:** CPU, RAM, GPU, VRAM, model size, disk/storage, startup cost.
- **Operational:** fully offline operation, licensing, reproducibility,
  installation complexity, model provisioning, upgrade procedure, rollback,
  observability, failure handling.
- **Tactical / field suitability:** degraded connectivity, complete offline
  operation, bounded resources, restart recovery, graceful degradation,
  predictable behaviour after failure.

No cell in any of these dimensions carries a measured value; no candidate is
recommended.

### Evidence vs assumption

The table above distinguishes **evidence** (facts from the repository, the
environment, or WO-053) from **assumption** (unmeasured). The only factually
established rows are `Evidence status` (both NOT_AVAILABLE, from WO-053) and
`Model availability` (no local model file). Every other row is NOT ESTABLISHED.
No candidate is recommended.

## Production activation gate

Production STT engine activation is **mandatorily gated**. A candidate may be
selected (or conditionally selected) for production only after ALL of the
following are satisfied:

### Dataset

A legitimate dataset containing **at least 50 verified real radio speech
transmissions**, with:

- documented provenance;
- authorization to use;
- a SHA-256 digest per audio file;
- manually verified ground-truth transcripts;
- Ukrainian / radio relevance;
- documented recording conditions (source, channel, noise, speaker).

Synthetic speech and clean speech alone are NOT acceptable. If fewer than 50
usable real recordings exist at execution time, the benchmark report must
explicitly document the limitation and must not silently redefine the
requirement.

### Measurement

The benchmark must measure, per candidate on identical dataset / language /
normalized audio format / hardware:

- **Accuracy:** WER (word error rate) and CER (character error rate) against the
  verified reference transcripts, broken out into substitution, deletion, and
  insertion counts.
- **Performance:** end-to-end latency; real-time factor
  (`RTF = processing time / audio duration`); cold-start latency (model load +
  first inference); warm inference latency (session reused); throughput;
  concurrent-session behaviour.
- **Resources:** CPU and RAM usage; GPU / VRAM usage where applicable;
  model / storage footprint.
- **Reliability:** failure rate; crash rate; timeout rate; malformed-input
  handling; restart / recovery behaviour; repeatability (deterministic re-runs).

A failed transcription must not be allowed to disappear from the benchmark
denominator. No network-dependent model download may be required by benchmark
execution.

### Decision rule

The benchmark result must lead to one of:

1. Candidate A selected;
2. Candidate B selected;
3. neither candidate passes the mandatory gate — in which case:

```text
NO PRODUCTION STT ENGINE AUTHORIZED
```

The decision process does not force a winner. A candidate is authorized only
after the benchmark is executed, the report is recorded, the mandatory gate is
passed, and the production engine decision is accepted by the Chief Systems
Architect.

## Architecture

The production architecture is engine-agnostic and is already present in the
seam. The preferred boundary:

```text
Audio recording
      |
      v
STT seam / ITranscriber
      |
      +---- Engine Adapter
      |
      +---- Engine-specific runtime
      |
      +---- Model
```

STT output remains **downstream** of audio acquisition and recording:

```text
RTP -> PCM/VAD -> recording -> STT -> transcription result
      -> canonical event enrichment / related event
```

This ADR does NOT redefine radio segmentation, does NOT move STT upstream of RTP
source-flow isolation, and does NOT modify `RtpReceiver`, `FlowRouter`,
`RtpStreamTracker`, `TransmissionRecorder`, or `TransmissionSegmenter`.
WO-055/CORR-02 remains the authoritative direction for source-flow isolation.

## Failure semantics

STT is an **enrichment capability** and MUST NOT become a single point of failure
for the underlying audio recording or the durable event path. The Core event and
audio-recording paths MUST remain operational and durable regardless of STT
state; an STT failure is observable and the system degrades gracefully, it does
not lose the recording or the canonical event.

When STT is unavailable, the model is missing, model load fails, inference fails,
times out, exceeds resource limits, returns an empty transcript, crashes /
restarts, or the queue is full, the required behavior is:

- **STT failure MUST NOT destroy the underlying audio recording.** The finalized
  WAV master is the authoritative audio (`AUDIO = SOURCE OF TRUTH`); the
  transcript is derived data and is never the source of truth.
- The system MUST retain the recording / event path even when transcription is
  unavailable.
- With no registered engine (`transcriber=None`), the worker is `UNAVAILABLE`
  (fail-closed): every job is rejected and recorded as an observable
  `unavailable` failure; no fake transcript is produced and no fallback to
  `DeterministicTestTranscriber` occurs.
- The queue is bounded (`maxsize`); when full the newest job is dropped and the
  drop is observable, while the WAV master remains authoritative.
- Per-job failure is isolated: a failed STT never loses the recording and never
  crashes the Core / RTP receiver.
- Duplicate `audio_recording_id` submission is suppressed deterministically.
- Processing is gated on `ITranscriber.is_ready()`: a not-ready transcriber does
  not silently fall back, it records an observable failure.
- When STT is enabled but no authorized engine is registered, the source adapter
  reports `UNAVAILABLE` and never fabricates a transcript.

These are the documented contract. This WO documents them; it does not implement
new changes.

## Model lifecycle

The ADR defines the required model-management contract. Models live **outside
Git** and are provisioned locally; model weights are never committed.

- **Location:** models live at a local, configured path (`SttConfig.model_path`),
  optionally confined to `model_root` (path-traversal guard).
- **Provisioning:** offline, no network download, no cloud dependency. A missing
  local model fails clearly (`SttConfigError`) — there is no fallback download.
- **Identity / version:** each model has a recorded identity / version; the
  engine adapter reports the model name (via `ITranscriber.model`) which is
  carried into the derived transcript payload.
- **Integrity:** model files are verified by SHA-256 before use; the configured
  path is canonicalized and verified to exist.
- **Offline deployment:** models are delivered out-of-band and staged locally.
- **Upgrade / rollback:** a new model is provisioned under a distinct identity
  and validated before being selected; rollback restores a previously verified
  model.
- **Compatibility:** the model must be compatible with the engine adapter and
  runtime; incompatibility fails clearly.
- **Startup validation:** on `initialize(config)`, the adapter validates the
  local model exists and loads it, transitioning to ready; a missing or
  incompatible model fails clearly and leaves the worker fail-closed.

This WO does not download, add, or commit any model file.

## Security / offline requirements

Production STT MUST:

- operate fully offline;
- make no external API calls;
- have no mandatory Internet dependency;
- not leak audio or transcripts externally;
- have bounded resource consumption;
- fail closed when unavailable;
- expose health / readiness state (`stt_state()` and the worker snapshot);
- preserve evidence / audio when transcription fails;
- never execute a model file as a program;
- never download a model at runtime.

No compliance certification is claimed; none is asserted here.

## Consequences

Positive:

- no premature engine lock-in;
- reproducible, evidence-backed production selection;
- preserves the engine-neutral seam and the core event architecture;
- auditable production selection;
- offline, no cloud dependency;
- failure of STT never loses audio or canonical events.

Negative:

- production acoustic STT implementation is delayed until the benchmark gate
  passes;
- representative real radio recordings and manual ground truth are required
  before any engine can be selected;
- no engine is available today, so no transcription beyond the deterministic
  test seam is possible yet.

## Rejected alternatives

- **Hard-coding an engine into the Core** — rejected: violates engine-neutrality
  and the protected seam; would create a technology lock-in without evidence.
- **Conditionally selecting a candidate without evidence** — rejected: the
  architecture seam is deliberately neutral and does not favor either candidate;
  no empirical measurement exists, so any conditional preference would be an
  assumption.
- **Selecting based on synthetic or clean-speech tests** — rejected: the WO-053
  synthetic dataset is mechanics-only and not representative of real
  Ukrainian / radio STT accuracy. Synthetic results must not be converted into
  STT accuracy evidence.
- **Online / cloud STT** — rejected: violates the mandatory offline and
  no-external-leak requirements.
- **Deferring the architecture decision** — not rejected; the architecture (Part
  1) is ratified now, while only engine selection (Part 2) is deferred.

## Evidence

- `docs/benchmarks/stt/wo053/WO-053-STT-BENCHMARK-REPORT.md` — benchmark
  infrastructure VERIFIED; real acoustic benchmark NOT EXECUTED; real radio
  speech dataset NOT AVAILABLE; 0/2 candidates available; no WER/CER; production
  selection NOT PERFORMED.
- `docs/benchmarks/stt/wo053/README.md` — benchmark-only, offline,
  no production selection; selection belongs to WO-054 / ADR-014.
- `backend/app/contracts/audio.py` — `ITranscriber` contract.
- `backend/app/audio/transcriber.py` — `DeterministicTestTranscriber` (test
  transcriber, not production).
- `backend/app/audio/stt_config.py` — `SttConfig`, `SUPPORTED_ENGINES`,
  `resolve_model_path`.
- `backend/app/audio/stt_seam.py` — `AbstractSttAdapter`, `register_engine`,
  `build_transcriber`.
- `backend/app/audio/stt_worker.py` — `SttWorker`, `SttJob`,
  `build_transcript_raw`, `read_wav_readonly`.
- `backend/app/audio/source_adapter.py` — production wiring, `stt_state()`,
  WO-041-CORR F-01/F-03.
- Environment check (this host): `faster_whisper`, `vosk`, `ctranslate2`,
  `whisper`, `torch` all absent; no model file tracked in the repository.

## Open conditions

Before production activation of any STT engine, the following remain open:

1. A real radio speech dataset (≥50 verified transmissions with provenance,
   authorization, SHA-256, ground-truth transcripts, documented conditions).
2. An engine and model provisioned locally (offline), with verified SHA-256.
3. A benchmark executed on the real dataset measuring WER, CER, latency, RTF,
   cold-start, warm inference, CPU, RAM, GPU/VRAM, failure rate, repeatability.
4. A benchmark report recorded and the mandatory gate passed.
5. A production engine decision accepted by the Chief Systems Architect.
6. Licensing of the selected engine and model verified from authoritative
   documentation.
7. Engine adapter implementation (e.g. `FasterWhisperAdapter` / `VoskAdapter`)
   registered via `register_engine`, within the protected seam.

Until these are satisfied, the production STT state remains `UNAVAILABLE`
(fail-closed) and no production engine is authorized.
