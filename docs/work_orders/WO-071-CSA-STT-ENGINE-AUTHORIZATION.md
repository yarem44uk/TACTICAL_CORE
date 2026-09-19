# WO-071 — CSA STT ENGINE AUTHORIZATION DECISION

**Work Order:** WO-071
**Repository:** `yarem44uk/TACTICAL_CORE` (`/opt/data/tactical_core_github`)
**Branch:** `wo-071-csa-stt-engine-authorization`
**Base:** `origin/main`
**Main baseline:** `4cddf848fa2ff959a13817002d684ee5320e06c1`
**Date:** 2026-09-19
**Status:** EVIDENCE PACKAGE COMPLETE — CSA AUTHORIZATION NOT RECORDED
**FINAL CLASSIFICATION:** `DECISION_PENDING`

---

## Scope and neutrality statement

This is a **decision/evidence document only**. It assembles existing evidence and
records the CSA authorization state. It does **not** select, rank, score, weight,
recommend, activate, register, configure, install, download, benchmark, or deploy
any production STT engine.

No winner, no "best", no preference, no recommendation is stated. No engine is
inferred from WER, CER, latency, RTF, memory, language support, model
availability, engineering preference, or apparent benchmark advantage.

The Chief Systems Architect (CSA) remains the sole decider. If no explicit CSA
authorization has been supplied, the correct state is `DECISION_PENDING`.

---

## 1. Executive summary

The WO-069 execution evidence and the WO-070B human-reference accuracy evidence
are both complete and internally consistent, and together they form a
self-contained descriptive evidence package for both candidate engines
(`faster_whisper`, `vosk`).

WO-069 executed both engines on an identical, integrity-verified dataset of 67
records with **0 failures and 0 timeouts**, and produced measured latency, RTF,
memory and reliability evidence.

WO-070B then scored the existing WO-069 hypotheses against **61 human-entered
reference transcripts** (the 6 remaining records are `NON_AUDIBLE`), producing
deterministic WER/CER for both engines. Both engines remain **authorized nowhere**:

* no explicit CSA authorization exists anywhere in the repository (all
  significance-bearing refs, all branches);
* WO-070A is an evidence package whose §14 is explicitly
  `CSA DECISION — NOT YET MADE`;
* WO-070B is accuracy evidence only and states a separate CSA decision is
  required (§23);
* `docs/benchmarks/stt/README.md` (all branches, including `main`) states
  "no production STT engine is authorized; the ADR-014 gate is NOT SATISFIED".

Accordingly the authorization state recorded by this WO is `DECISION_PENDING`.
**No production STT engine is authorized by this WO.** No engine was activated.

---

## 2. Evidence baseline

### 2.1 Forensic gate (read-only, executed before any change)

```text
$ cd /opt/data/tactical_core_github
$ git status --short
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500

$ git branch --show-current   (at start)
wo-070b-stt-human-reference-benchmark

$ git rev-parse HEAD           (at start)
342ee7d77cf8a6acc5923a0996bdc2b8fbcba2c1

$ git rev-parse origin/main
4cddf848fa2ff959a13817002d684ee5320e06c1

$ git log --oneline --decorate -10
342ee7d (HEAD -> wo-070b-stt-human-reference-benchmark, origin/wo-070b-stt-human-reference-benchmark) WO-070B: measure STT accuracy from human reference transcripts
6d3d389 WO-070B: document human reference benchmark blocker (continuation re-check)
af19586 WO-070B: document human reference benchmark blocker
4cddf84 (origin/wo-066-end-to-end-verification, origin/main, origin/HEAD, wo-066-end-to-end-verification, main) WO-066: wire and verify end-to-end radio pipeline
01c8a13 (origin/wo-065-final-radio-event, wo-065-final-radio-event) WO-065: integrate final radio event into operational observation
b31815f (origin/wo-064-transcript-enrichment, wo-064-transcript-enrichment) WO-064: add deterministic transcript enrichment / callsign detection seam
aac270d (origin/wo-063-stt-processing-worker, origin/wo-063-stt-processing-worker) WO-063: add recording STT processing worker
ad7b230 (origin/wo-062-recording-evidence-access, origin/wo-062-recording-evidence-access) WO-062-C1: enforce mandatory recording SHA-256 verification
552d408 WO-062: add authenticated recording evidence access
34d0412 (origin/wo-061-chronological-wall, origin/wo-061-chronological-wall) WO-061: add chronological observation wall

$ git diff --name-only origin/main...HEAD   (at start, WO-070B branch)
docs/benchmarks/stt/wo070b/README.md
docs/benchmarks/stt/wo070b/WO-070B-STT-ACCURACY-REPORT.md
docs/benchmarks/stt/wo070b/__init__.py
docs/benchmarks/stt/wo070b/aggregate_results.csv
docs/benchmarks/stt/wo070b/human_reference_transcripts.csv
docs/benchmarks/stt/wo070b/per_message_results.csv
docs/benchmarks/stt/wo070b/test_wo070b_benchmark.py
docs/benchmarks/stt/wo070b/wo069_hypotheses_faster_whisper.jsonl
docs/benchmarks/stt/wo070b/wo069_hypotheses_vosk.jsonl
docs/benchmarks/stt/wo070b/wo070b_benchmark.py
docs/benchmarks/stt/wo070b/wo070b_metrics.py
docs/benchmarks/stt/wo070b/wo070b_normalize.py
docs/benchmarks/stt/wo070b/wo070b_reference.py
docs/benchmarks/stt/wo070b/wo070b_results.json
docs/work_orders/WO-070B-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
docs/work_orders/WO-070B-CONTINUE-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
```

The protected untracked `?? 500` was never opened, read, hashed, statted, copied,
moved, renamed, staged, deleted, cleaned or reset. The pre-existing ` M` bytecode
cache was left exactly as found and is not staged by this WO. No `git reset`,
`git clean`, `git restore`, file-level `git checkout`, `git rebase`,
`git commit --amend`, or force-push was executed.

### 2.2 Evidence sources inspected (read-only)

| Source | Location | Branch |
| --- | --- | --- |
| WO-069 real-radio STT benchmark evidence | `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/*` | `wo-069-real-radio-stt-benchmark` (`3c4f4be`) |
| WO-070A CSA engine-selection evidence package | `docs/work_orders/WO-070A-CSA-STT-ENGINE-SELECTION.md` | `wo-070a-csa-stt-engine-selection` (`a11d6d9`) |
| WO-070B human-reference accuracy report | `docs/benchmarks/stt/wo070b/WO-070B-STT-ACCURACY-REPORT.md` | `wo-070b-stt-human-reference-benchmark` (`342ee7d`) |
| STT benchmark gate statement | `docs/benchmarks/stt/README.md` | all branches incl. `main` |
| Production STT seam (not modified) | `backend/app/contracts/audio.py`, `backend/app/audio/stt_seam.py`, `stt_config.py`, `stt_worker.py` | `main` |

WO-070A's §0.1 forensic gate was re-confirmed: `git remote -v` →
`origin git@github.com:yarem44uk/TACTICAL_CORE.git`.

---

## 3. WO-069 execution evidence

Source: `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/*` (branch
`wo-069-real-radio-stt-benchmark`, `3c4f4be`), as carried into WO-070A §2/§3 and
§7. WO-069 is benchmark-execution evidence only; WER/CER were `NOT_MEASURABLE`
in WO-069 itself because no reference transcripts existed at that time.

Dataset: 67/67 records present and integrity-verified; total audio 136.36 s;
dataset hash `e0f2b39eea6bb4c87f5fd4adcf23bd35116fd37de86fb062d7569a7a054e52d9`;
human-reviewed rows 61.

Host: Debian 13 / kernel `6.12.48+deb13-cloud-amd64`; CPU INTEL(R) XEON(R)
PLATINUM 8568Y+ (8 cores); RAM 16,774,946,816 B; cgroup memory.max
4,294,967,296 (4 GiB); GPU NOT_AVAILABLE.

### 3.1 Faster-Whisper

| Item | Value |
| --- | --- |
| Engine availability | Importable in engine runtime venv `/opt/data/wo067_runtime_gate_v1/venv` (1.2.1); **NOT** importable in the repository venv |
| Runtime environment | `faster-whisper==1.2.1`, `ctranslate2==4.8.2`, `numpy==2.5.3`, `onnxruntime==1.30.0` |
| Model | `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/faster_whisper` (486,216,320 B) |
| Model provenance | `model_version = "SHA256SUMS"` (bundle sha256 `8f023ea8…`, WO-068 §6); per-file digest **NOT AVAILABLE** |
| Language handling | language auto-detect (`language = null`, recorded) |
| Sample-rate handling | native 8 kHz — engine decodes natively, no resample (rc=0) |
| 67/67 execution status | `COMPLETED`, exit code 0; success / failed / timeout = 67 / 0 / 0; failure rate 0.0 |
| Non-empty hypotheses | **64 / 67** |
| Empty hypotheses | **3 / 67** |
| Cold start | 1162.0 ms |
| Median latency | 2.590306 s |
| p95 latency | 7.065627 s |
| RTF | median 1.611679; p95 7.297067 |
| Peak RSS | 1,278,345,216 B (CPU user total 371.32 s) |
| Accuracy status | **NOT MEASURED** (no reference at WO-069 time); scored in WO-070B (§4 below) |

### 3.2 Vosk

| Item | Value |
| --- | --- |
| Engine availability | Importable in engine runtime venv `/opt/data/wo067_runtime_gate_v1/venv` (0.3.45); **NOT** importable in the repository venv |
| Runtime environment | `vosk==0.3.45`, `cffi==2.1.1`, `numpy==2.5.3` |
| Model | `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/vosk_uk/vosk-model-uk-v3` (1,040,586,413 B) |
| Model provenance | `model_version = "UNKNOWN"`, `model_revision = "vosk-model-uk-v3"`; digest **NOT AVAILABLE** |
| Language handling | `language = "uk"` (Ukrainian-specific model only) |
| Sample-rate handling | native 8 kHz **FAILS** (`conf/mfcc.conf` hard-codes `sample-frequency=16000`); deterministic linear 8 kHz → 16 kHz upsample decodes rc=0; original 8 kHz WAV remains the input of record, never modified |
| 67/67 execution status | `COMPLETED`, exit code 0; success / failed / timeout = 67 / 0 / 0; failure rate 0.0 |
| Non-empty hypotheses | **53 / 67** |
| Empty hypotheses | **14 / 67** |
| Cold start | 2543.162 ms |
| Median latency | 0.147892 s |
| p95 latency | 0.908192 s |
| RTF | median 0.098067; p95 0.188797 |
| Peak RSS | 1,439,416,320 B (CPU user total 17.03 s) |
| Accuracy status | **NOT MEASURED** at WO-069 time; scored in WO-070B (§4 below) |

### 3.3 Vosk language/model limitations and runtime requirements

* The provisioned Ukrainian model is `vosk-model-uk-v3` (uk only). The catalogue
  RU (`vosk-model-ru-0.42`) and EN (`vosk-model-en-us-0.22`) models were
  **RESOURCE-LIMITED at the 4 GiB cgroup cap** (`rc=137`, OOM) in WO-067; only
  the uk model ran within the cap in WO-069.
* Native 8 kHz input is not accepted; a deterministic 8→16 kHz upsample is
  required (documented above). This is a module limitation carried into the
  runtime requirement.
* Both engines are CPU-only (`device = cpu`, no GPU present), run fully offline
  from the local OFFLINE-BUNDLE, require no network, and require no credentials.

No WO-069 evidence was altered by this WO.

---

## 4. WO-070B human-reference accuracy evidence

Authoritative report:
`docs/benchmarks/stt/wo070b/WO-070B-STT-ACCURACY-REPORT.md`
(branch `wo-070b-stt-human-reference-benchmark`, `342ee7d77cf8a6acc5923a0996bdc2b8fbcba2c1`).
Reported verbatim, without reinterpretation.

### 4.1 Dataset

```text
67 total records
61 HUMAN_VERIFIED
6  NON_AUDIBLE
0  NO_HUMAN_TRANSCRIPT
```

Reference corpus:

```text
143 normalized reference words
662 normalized reference characters
```

Human reference source: `WO-068-HUMAN-REVIEW-EXTENDED.xlsx`
(XLSX sha256 `2e4a0bb66a7309a077623bf49935b6493ef607d3dccbc2fe5eb1da342a88296d`,
16,969 B, sheets `['Human Review','Instructions']`). Reference text was taken
only from the `transcript` column of the `Human Review` sheet; nothing was derived
from Faster-Whisper, Vosk, callsign, notes, dialogue_candidate, speaker, filename,
memory or inference; STT output was never promoted to a reference. Join key:
`message_id` (never row position). Normalization: `wo070b-normalize-v1` applied
identically to reference and hypothesis.

### 4.2 Faster-Whisper

```text
evaluated: 61

substitutions: 96
deletions:     9
insertions:    47

WER: 1.062937
CER: 0.774924
```

(152 ops / 143 reference words; 513 ops / 662 reference characters.)

### 4.3 Vosk

```text
evaluated: 61

substitutions: 43
deletions:     34
insertions:    8

WER: 0.594406
CER: 0.498489
```

(85 ops / 143 reference words; 330 ops / 662 reference characters.)

### 4.4 Provenance

```text
TRANSPORT_PROVENANCE:
SYNTHETIC_TOPOLOGY

RF_PROVENANCE:
UNRESOLVED

REAL_TRANSMISSION:
UNRESOLVED
```

### 4.5 Interpretation rule

These metrics are **valid benchmark measurements against human references**:
they were computed deterministically from an identical normalization applied to
both sides, over an identical 61-record reference corpus, and are reproducible
byte-for-byte. They are descriptive facts.

However, the corpus **does not independently establish RF provenance**: the
transport is a synthetic topology (CubicCore traffic generator v7.19.4 over a
simulated L2/L3 topology, no RF/SDR transport chain), `RF_PROVENANCE` is
`UNRESOLVED`, and `REAL_TRANSMISSION` is `UNRESOLVED` for all 67 records. No WER/CER
value is converted into an authorization or a suitability claim.

---

## 5. Factual engine comparison

Descriptive measurements only. No score, ranking, winner, best, recommendation or
preference is implied by this table or its row order.

| Property | Faster-Whisper | Vosk | Evidence source |
| --- | --- | --- | --- |
| evaluated records | 61 | 61 | WO-070B `aggregate_results.csv` |
| WER | 1.062937 | 0.594406 | WO-070B `aggregate_results.csv` |
| CER | 0.774924 | 0.498489 | WO-070B `aggregate_results.csv` |
| substitutions | 96 | 43 | WO-070B `aggregate_results.csv` |
| deletions | 9 | 34 | WO-070B `aggregate_results.csv` |
| insertions | 47 | 8 | WO-070B `aggregate_results.csv` |
| empty hypotheses | 3 / 67 overall (2 within the 61 scored records) | 14 / 67 overall (9 within the 61 scored records) | WO-070B §7; WO-069 `hypothesis_availability_matrix.csv` |
| median latency | 2.590306 s | 0.147892 s | WO-069 `runtime_metrics.csv` / evidence report §3 |
| p95 latency | 7.065627 s | 0.908192 s | WO-069 `runtime_metrics.csv` / evidence report §3 |
| median RTF | 1.611679 | 0.098067 | WO-069 `runtime_metrics.csv` / evidence report §3 |
| p95 RTF | 7.297067 | 0.188797 | WO-069 `runtime_metrics.csv` / evidence report §3 |
| peak RSS | 1,278,345,216 B | 1,439,416,320 B | WO-069 `resource_metrics.csv` |
| sample-rate handling | native 8 kHz decode (rc=0), no resample | native 8 kHz FAILS; deterministic linear 8→16 kHz upsample required | WO-067/WO-069 evidence report §3 |
| language/model characteristics | language auto-detect; model = bundled `faster_whisper` (486,216,320 B), int8, cpu; per-file digest NOT AVAILABLE | `uk`-specific model `vosk-model-uk-v3` (1,040,586,413 B), cpu; RU/EN catalogue models RESOURCE-LIMITED (rc=137) at 4 GiB; digest NOT AVAILABLE | WO-069 `environment_manifest.json`; WO-067 |
| runtime availability | NOT importable in repo venv; importable in engine runtime venv (1.2.1) | NOT importable in repo venv; importable in engine runtime venv (0.3.45) | Runtime probe (WO-070A §1) |
| provenance limitations | RF provenance UNRESOLVED; transport synthetic; `real_transmission` UNRESOLVED | same | WO-068 §2.1; WO-069 `dataset/manifest.csv` |

Both engines: `COMPLETED` 67/67, 0 failures, 0 timeouts, CPU-only, offline
operable, no network, no credentials. Neither engine is registered;
`_ENGINE_FACTORIES = {}`.

---

## 6. Provenance limitations

| Dimension | Classification | Basis |
| --- | --- | --- |
| Transport provenance | SYNTHETIC_TOPOLOGY — VERIFIED (synthetic) | CubicCore traffic generator v7.19.4 over a simulated L2/L3 topology; no RF/SDR transport chain |
| RF provenance | UNAVAILABLE / UNRESOLVED | WO-068 §2.1: "No RF/SDR provenance. No real radio capture." |
| `real_transmission` flag | UNRESOLVED for all 67 | `dataset/manifest.csv`; workbook columns empty; Instructions: "Do not infer from speech alone." |
| Source identity | PARTIALLY VERIFIED | `stream_id` S1 (44) / S2 (23) recorded; identity beyond stream id NOT AVAILABLE |
| Capture conditions | UNKNOWN | no documented source/channel/noise/speaker conditions |

The WO-070B accuracy figures are therefore measurements against human references
but are **not** independently established as real-radio measurements. RF
provenance was not treated as a blocker for computing WER/CER; it remains an open
CSA production-decision issue. WO-070A §5.2 also records an unresolved
documentation contradiction (`wo067/README.md` vs WO-067-PRE-04 `human_confirmed`)
for CSA resolution.

---

## 7. Production architecture constraints

The production STT subsystem is an **engine-neutral, fail-closed seam, not a
running engine** (ADR-014 Part 1). `ITranscriber` is the Core contract;
`AbstractSttAdapter` adds the offline `initialize(config)` lifecycle hook;
`build_transcriber(config)` validates config and dispatches via
`_ENGINE_FACTORIES`, which is **empty**, so a recognised engine raises
`SttEngineUnavailableError` — there is no silent fallback.

Current production STT state: `UNAVAILABLE` (fail-closed). No engine is
registered. ADR-014 Part 2 (activation gate) is DEFERRED and **not satisfied**:
no ground-truth campaign at activation scale, no verified real-radio provenance,
and the accuracy figures are from a synthetic-transport corpus.

Constraints on any future authorization:

* No engine identifier, seam file, `_ENGINE_FACTORIES`, `SttConfig`, production
  configuration, deployment file, model file, or runtime dependency was changed
  by this WO.
* Recording / event / journal / Operator Wall paths remain operational and are
  unaffected; STT is an enrichment capability behind a fail-closed boundary.

---

## 8. CSA authorization state

```text
CSA_DECISION: DECISION_PENDING
```

Repository-wide search for an explicit authorization
(`AUTHORIZE_FASTER_WHISPER`, `AUTHORIZE_VOSK`,
`AUTHORIZE_NO_PRODUCTION_STT_ENGINE`, `CSA … AUTHOR`, `STT … AUTHORIZATION`)
across `docs/work_orders` and `docs/benchmarks/stt`, and across all branches and
all significant refs, returned **no explicit CSA authorization decision**. The
authoritative WO-070A document records `§14 CSA DECISION — NOT YET MADE`; WO-070B
records its output as accuracy evidence requiring a separate CSA decision.
Authorization has therefore **not** been supplied, and this WO does not infer one.

```text
DECISION_PENDING
```

---

## 9. Explicit statement

```text
NO PRODUCTION STT ENGINE IS AUTHORIZED BY THIS WO.
```

This is not a failure: the evidence package is complete but human CSA
authorization has not yet been recorded. No engine was selected, activated,
registered, configured, installed, downloaded, benchmarked or deployed.

---

## 10. Next WO boundary

A **separate production implementation WO** is required before any change to the
existing STT seam or the registration of an engine. Specifically:

* The engine must first be explicitly authorized by the CSA (one of
  `AUTHORIZE_FASTER_WHISPER`, `AUTHORIZE_VOSK`, or
  `AUTHORIZE_NO_PRODUCTION_STT_ENGINE`).
* Only after that authorization may a separate implementation WO implement the
  corresponding `AbstractSttAdapter`, register it via
  `register_engine(engine_id, factory)`, and supply the existing `SttConfig`.
* The implementation WO must not be inferred from this document, from WO-070A, or
  from any WER/CER, latency, RTF or memory figure.

---

## 11. Production safety attestation (WO-071)

```text
STT adapter implemented                     : NO
Production engine registered                : NO
_ENGINE_FACTORIES modified                  : NO (still {})
STT seam modified                           : NO
backend/app/contracts/audio.py              : NOT MODIFIED
backend/app/audio/stt_seam.py               : NOT MODIFIED
backend/app/audio/stt_config.py             : NOT MODIFIED
backend/app/audio/stt_worker.py             : NOT MODIFIED
Production configuration modified           : NO
EventFactory / EventPipeline changed        : NO
RadioEventIntegrator / Observation changed  : NO
Journal / Operator Wall changed             : NO
Adapters / DB schema / deployment changed   : NO
Model downloaded / installed                : NO
Dependencies installed / modified           : NO
Engine activated                            : NO
Production radio / network traffic run      : NO
WO-069 re-run                               : NO
WO-070B re-run                              : NO
main modified                               : NO
?? 500                                      : preserved, untouched, unstaged
 M (pyc) pre-existing                       : preserved as found, unstaged
Fabricated evidence                         : NONE
```

## 12. Read-only validation executed

```text
Repository identity / branch / HEAD / origin/main   : CONFIRMED (§2.1)
Authoritative WO-070A report located and read       : CONFIRMED (§14 = NOT YET MADE)
Authoritative WO-070B report located and read       : CONFIRMED
WO-069 execution evidence located and read          : CONFIRMED
Repository-wide explicit-authorization search       : NO AUTHORIZATION FOUND
git diff --check                                    : clean (no whitespace errors)
Required document sections present                  : CONFIRMED (§1–§10)
Changed file set (origin/main...HEAD)               : WO-071 document only
```

`python -m py_compile` is not applicable to a Markdown target (it would raise a
SyntaxError, not compile it); per WO-071 §13 no artificial test was fabricated and
the documentation was validated with `git diff --check` and required-section
verification instead.
