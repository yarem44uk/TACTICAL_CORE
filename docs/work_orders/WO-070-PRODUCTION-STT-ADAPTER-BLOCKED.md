# WO-070 — Production STT Adapter

**Branch:** `wo-070-production-stt-adapter`
**Baseline:** `main` = `4cddf848fa2ff959a13817002d684ee5320e06c1` (WO-066)
**Status:** **BLOCKED — PRODUCTION ENGINE SELECTION REQUIRED**
**Author:** Senior Software Engineer / AI Engineer
**Date:** 2026-09-19

---

## BLOCKING CONDITION

```text
BLOCKING CONDITION:
CSA production STT engine selection is not present in authoritative repository evidence.
```

WO-070 §5 requires an explicit authoritative production STT engine selection before
any engine adapter may be implemented. No such selection exists anywhere in the
repository or in the accepted ADR record. `docs/adr/ADR-014` Part 2 (`Engine
selection`) is `DEFERRED`; production activation is `BLOCKED`. WO-069 (the most
recent accepted benchmark evidence) records `production_engine_selection = NOT MADE —
CSA DECISION REQUIRED (ADR-014 Part 2)`.

Per WO-070 §5, implementation **STOPS** after the forensic/design inspection and the
blocker is documented instead of an engine being invented. This document is the
deliverable. No adapter was implemented, no engine was registered, no production file
was modified, and no benchmark evidence was fabricated.

---

## 1. Forensic gate (read-only, executed before any mutation)

```text
git status --short
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500

git branch --show-current            -> wo-069-real-radio-stt-benchmark
git rev-parse HEAD                   -> 3c4f4be9f0a0ff63857776491f2aae146082d71c
git rev-parse origin/main            -> 4cddf848fa2ff959a13817002d684ee5320e06c1
git remote -v                        -> origin git@github.com:yarem44uk/TACTICAL_CORE.git (fetch/push)

git ls-remote origin refs/heads/main refs/heads/wo-069-real-radio-stt-benchmark
4cddf848fa2ff959a13817002d684ee5320e06c1  refs/heads/main
3c4f4be9f0a0ff63857776491f2aae146082d71c  refs/heads/wo-069-real-radio-stt-benchmark
```

Repository identity and baseline matched the WO preamble exactly. The unrelated
worktree items (`?? 500`, `M .../__pycache__/plugin_manager.cpython-313.pyc`) were
left untouched.

`wo-070-production-stt-adapter` was created from the baseline `origin/main`
(`4cddf84`) so that `git diff main...HEAD` contains ONLY WO-070 paths.

---

## 2. Existing STT seam (authoritative, NOT modified)

The production STT subsystem is an **engine-neutral seam, not a running engine**
(ADR-014 Part 1). The five seam components, all under `backend/app/`:

| # | Component | Path | Role |
| --- | --- | --- | --- |
| 1 | Contract | `contracts/audio.py` | `ITranscriber` (ABC): `model` property, `transcribe(audio_data, language=None) -> str`, `is_ready() -> bool` |
| 2 | Test transcriber | `audio/transcriber.py` | `DeterministicTestTranscriber` + `transcribe_detailed` / `TranscriptResult`; deliberately non-acoustic, NOT production |
| 3 | Configuration | `audio/stt_config.py` | `SttConfig` (frozen: `enabled`, `engine`, `model_path`, `language`, `device`, `model_root`), `SUPPORTED_ENGINES = {"faster_whisper", "vosk"}`, `resolve_model_path()` (deterministic, traversal-guarded, offline, never downloads) |
| 4 | Adapter seam | `audio/stt_seam.py` | `AbstractSttAdapter` (+ `initialize(config)` lifecycle hook), `register_engine(engine_id, factory)`, `build_transcriber(config)`, errors `SttEngineError` / `SttEngineUnknownError` / `SttEngineUnavailableError` |
| 5 | Worker | `audio/stt_worker.py` | `SttWorker` (bounded queue, daemon thread `wo039c-stt-worker`), `SttJob`, `build_transcript_raw`, `read_wav_readonly` |

Production wiring: `audio/source_adapter.py` → `_build_production_stt_worker` reads
`definition.config["stt"]`, builds an `SttConfig`, calls `build_transcriber`, wraps in
`SttWorker`. Transcripts flow through `EventFactory` → canonical Event path →
`RadioEventIntegrator` → journal → `Observation` → Operator Wall. STT is an
enrichment capability; the WAV master is `AUDIO = SOURCE OF TRUTH` and the transcript
is derived.

The protected seams (`ITranscriber`, `AbstractSttAdapter`, `register_engine`,
`build_transcriber`, `SttWorker`) were inspected and are **unchanged** by WO-070.

### 2.1 Seam proven to have NO engine registered (executed probe)

```text
SUPPORTED_ENGINES = ['faster_whisper', 'vosk']
registered factories = []                       # _ENGINE_FACTORIES is empty
faster_whisper module importable: False
  build_transcriber -> SttConfigError model path does not exist: /nonexistent/model-xyz
vosk module importable: False
  build_transcriber -> SttConfigError model path does not exist: /nonexistent/model-xyz
```

Not one engine adapter is registered and neither engine module is importable in the
repository venv. This is the documented fail-closed state: with a *recognised* engine
and no registered adapter, `build_transcriber` raises `SttEngineUnavailableError`
(here the missing-model check fires first) — there is never a silent fallback to
`DeterministicTestTranscriber`.

---

## 3. Available engines

`SUPPORTED_ENGINES = {"faster_whisper", "vosk"}` is the **recognised candidate set**,
not a production choice (ADR-014: "Recognition as a candidate carries no
authorization to implement, register, or integrate the engine").

- `faster_whisper` — not registered; not importable in the repository venv.
- `vosk` — not registered; not importable in the repository venv.

No engine is installed, imported, registered, or authorized in this repository state.

---

## 4. WO-069 benchmark status (accepted evidence, cited — not reinterpreted)

`docs/benchmarks/stt/wo069/` (branch `wo-069-real-radio-stt-benchmark`, HEAD
`3c4f4be`; independent forensic review: `FINAL_CLASSIFICATION: VERIFIED`):

```text
67 WAV inputs
64/67 non-empty Faster-Whisper hypotheses
53/67 non-empty Vosk hypotheses
134 engine rows
human reference transcript count = 0 in runtime benchmark input
WER = NOT_MEASURABLE
CER = NOT_MEASURABLE
ground truth sidecar = UNAVAILABLE
production_engine_selection = NOT MADE — CSA DECISION REQUIRED (ADR-014 Part 2)
```

A **hypothesis is never promoted to a reference**; no callsign repairs a transcript;
no WER/CER value is estimated. WO-069 is a *measurement instrument* and explicitly
does not select, recommend, or authorize a production engine.

The external human-review artifact `WO-068-HUMAN-REVIEW-EXTENDED.xlsx` is NOT a Git
source file; its absence from Git is intentional and is NOT a defect.

---

## 5. Why no production engine can be selected automatically

1. ADR-014 Part 2 (`Engine selection`) is **DEFERRED**. Part 2 is the *only*
   authoritative place a production engine decision may originate, and there is no
   amendment or superseding ADR recording it.
2. The WO-069 benchmark that would inform the decision measured **no accuracy**: WER
   and CER are `NOT_MEASURABLE` (0 human reference transcripts). There is no
   empirical basis to prefer either candidate.
3. The ADR-014 **production activation gate** is not satisfied: no ≥50-transmission
   verified real-radio dataset with ground-truth transcripts, no executed accuracy/
   latency/RTF/resource benchmark on real data, no accepted gate pass, no verified
   licensing.
4. The architecture is deliberately engine-neutral; the seam does not favour either
   candidate, so inferring a winner from raw hypothesis counts (64/67 vs 53/67) would
   be an **assumption**, not evidence. Hypothesis availability is not accuracy.
5. WO-070 §5 forbids selecting, recommending, or inferring an engine automatically.

Conflicting green-looking artifacts were checked and none authorizes an engine:

- `docs/benchmarks/stt/STT-DATASET-REPORT.md` — `PRODUCTION STT ENGINE AUTHORIZED: NO`
- `docs/benchmarks/stt/STT-ENGINE-BENCHMARK-REPORT.md` — `NO PRODUCTION STT ENGINE AUTHORIZED`
- `docs/benchmarks/stt/WO-042-REAL-RADIO-DATASET.md` — `STT ENGINE SELECTED: NO`
- `docs/benchmarks/rtp/WO-041-REAL-RTP-CAPTURE-INTEGRATION.md` — `no STT engine selected`
- `docs/benchmarks/stt/wo053/WO-053-STT-BENCHMARK-REPORT.md` — `PRODUCTION STT SELECTION: NOT AUTHORIZED IN WO-053`
- `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/WO-069-EVIDENCE-REPORT.md` — `production engine selected: NO`

---

## 6. Exact CSA decision required

The Chief Systems Architect must record, in an authoritative artifact (an ADR-014
Part 2 amendment, a new accepted ADR, or an equivalent CSA directive), a decision of
exactly one of:

1. **Candidate A selected** — `faster_whisper` is the authorized production engine; or
2. **Candidate B selected** — `vosk` is the authorized production engine; or
3. **Neither candidate passes the mandatory gate** — literal outcome
   `NO PRODUCTION STT ENGINE AUTHORIZED`.

Each branch additionally requires the ADR-014 activation-gate evidence: a legitimate
≥50-transmission verified real-radio dataset with ground-truth transcripts, an
executed real-data benchmark (WER/CER + latency/RTF/resource/reliability), a recorded
report, the gate passed, and verified engine/model licensing. Only then may an engine
adapter be implemented and registered. This is a **CSA decision**, not an engineering
inference.

---

## 7. Proposed adapter interface (definable WITHOUT selecting an engine)

The adapter shape is already fully determined by the existing seam and is identical
for either candidate. It can be specified now and implemented only after §6 resolves.
No contract change is required and none is proposed.

```text
ITranscriber                       (contracts/audio.py — UNCHANGED)
    |
    +-- AbstractSttAdapter          (audio/stt_seam.py — UNCHANGED)
            |
            +-- <Engine>Adapter     (WO-070, future: audio/stt_<engine>_adapter.py)
```

Required shape of `<Engine>Adapter(AbstractSttAdapter)`:

| Member | Contract |
| --- | --- |
| `__init__(config: SttConfig)` | inherited; holds the validated `SttConfig`, starts `_ready=False` |
| `initialize(config: SttConfig) -> None` | load the **local, provisioned** model via `config.resolved_model_path()`; on success set ready; on missing/incompatible model raise `SttConfigError`/`SttEngineError` — NO download, NO network |
| `model -> str` | model identity (carried into the derived transcript payload) |
| `is_ready() -> bool` | `True` only after a successful `initialize` |
| `transcribe(audio_data: bytes, language: str | None) -> str` | run inference on the given PCM/decoded audio; return the transcript string (contract-defined empty string for no-speech); NEVER fabricate, NEVER reuse another message's transcript, NEVER use callsign metadata as fallback, NEVER swallow an engine error into a "successful" empty transcript |

Registration: `register_engine("<engine_id>", lambda config: <Engine>Adapter(config))`
with `<engine_id> in SUPPORTED_ENGINES`. `build_transcriber(config)` then performs
`config.validate()` (offline model-path check) and calls `initialize(config)`.

Fail-closed obligations the implementation MUST honour (WO-070 §7/§8/§11/§12):

- missing audio / invalid audio → deterministic error (raise), no transcript;
- engine init failure / model unavailable → error, worker stays `UNAVAILABLE`;
- inference exception / malformed engine result → raise (`SttWorkerError` path), counted as an observable `failed` job;
- timeout (if the engine supports one) → bounded, deterministic error;
- no direct writes to the event journal, no `EventFactory`/`EventPipeline`/
  `RadioEventIntegrator` bypass — the adapter returns text ONLY; `SttWorker` builds the
  derived raw dict and routes it through the existing canonical path;
- evidence WAV opened read-only; never mutated;
- no second STT seam, no second event model, no second database;
- no runtime model download; no hard-coded machine paths or credentials;
- no uncontrolled worker/process/thread proliferation (the adapter is called from the
  existing single `wo039c-stt-worker` thread).

The empty / no-speech representation is the existing contract representation (the
`str` returned by `transcribe`; `SttWorker.build_transcript_raw` writes it verbatim).
No new metadata fields are introduced; engine/model identity and timing already flow
through `build_transcript_raw`.

---

## 8. What WO-070 did NOT do

- No production STT engine was selected, recommended, or registered.
- No adapter was implemented (engine selection is absent — §5 STOP).
- No production file was modified: `contracts/audio.py`, `audio/stt_seam.py`,
  `audio/stt_config.py`, `audio/stt_worker.py` are unchanged.
- No `EventFactory`, `EventPipeline`, `RadioEventIntegrator`, `Observation`,
  durable-journal, Operator-Wall, or production-STT-selection change.
- No second STT seam, no second event pipeline, no journal bypass, no DB change.
- No WER/CER was manufactured; no WO-068 artifact was imported into Git.
- No runtime model download behaviour introduced.

---

## 9. Verification executed in WO-070

Focused WO-070 adapter tests: **N/A — no adapter exists (BLOCKED)**.

Relevant existing STT / audio / callsign seam tests (executed, real output):

```bash
cd backend && env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  ../.venv/bin/python -m pytest \
  tests/test_wo039c_stt.py tests/test_wo041_corr_stt_boundary.py \
  tests/test_wo057_callsign_integration.py tests/test_wo063_recording_stt_worker.py \
  tests/test_wo064_transcript_enrichment.py -q -p no:cacheprovider
```

```text
98 passed in 2.98s
```

Environment probe (executed): `registered factories = []`; `faster_whisper`/`vosk`
not importable in the repository venv (see §2.1).

---

## 10. Unblocking path

1. CSA records the engine decision (§6) in an authoritative artifact.
2. Satisfy the ADR-014 activation gate (real ≥50-transmission dataset with verified
   ground truth; executed real-data benchmark; recorded report; verified licensing).
3. Provision the selected engine + model locally (offline; no network download).
4. Implement `<Engine>Adapter` per §7, register it via `register_engine`, and add the
   focused contract/failure/safety/configuration/integration tests of WO-070 §13.
5. Re-run WO-070 with an actual engine selection present.

Detailed blocker findings are also recorded out-of-band (non-Git) per the readiness
evidence convention.

---

## References

- `docs/adr/ADR-014-Real-Acoustic-STT-Engine-Selection-and-Benchmark-Gate.md`
- `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/WO-069-EVIDENCE-REPORT.md`
- `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/benchmark_results.json`
- `docs/benchmarks/stt/wo053/WO-053-STT-BENCHMARK-REPORT.md`
- `backend/app/contracts/audio.py`
- `backend/app/audio/stt_seam.py`
- `backend/app/audio/stt_config.py`
- `backend/app/audio/stt_worker.py`
- `backend/app/audio/source_adapter.py`
