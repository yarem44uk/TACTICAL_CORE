# WO-070B — HUMAN REFERENCE TRANSCRIPT DATASET & STT ACCURACY BENCHMARK

**Work Order:** WO-070B
**Branch:** `wo-070b-stt-human-reference-benchmark`
**Base:** `origin/main` @ `4cddf848fa2ff959a13817002d684ee5320e06c1`
**Date:** 2026-09-19
**FINAL CLASSIFICATION:** **BLOCKED**

---

## BLUF

The completed WO-068 human-reference transcript artifact is **not available to this
runtime**. No file anywhere on the execution environment contains a human-entered
reference transcript for the 67 benchmark messages. The repository/runtime
`human_review.csv` carries **categorical listening labels only** and does **not**
contain the WO-068 transcript column. Per WO-070B §4, §16, §19 and §20 the correct,
non-fabricating outcome is:

```
STATUS BLOCKED
REASON: completed human-reference transcript artifact unavailable to runtime
HUMAN_REFERENCE_DATASET = UNAVAILABLE
WER = NOT_MEASURABLE
CER = NOT_MEASURABLE
```

No dataset was constructed, no WER/CER was assigned, no engine was run, and no
engine was selected.

---

## 1. FORENSIC READ-ONLY GATE (recorded before any change)

Repository: `/opt/data/tactical_core_github`
Remote: `git@github.com:yarem44uk/TACTICAL_CORE.git`

Pre-existing worktree state (unchanged throughout this WO):

```
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
```

`?? 500` was **not** opened, read, hashed, stat-only, copied, moved, renamed,
deleted, modified or staged. The pre-existing ` M` bytecode-cache modification was
left exactly as found. Neither was reset, cleaned, stashed, restored or
checkout-over.

| Field | Value |
|---|---|
| Branch at start | `wo-070a-csa-stt-engine-selection` @ `a11d6d92a6d8e78035b5d046174c4a6a3a433102` |
| Baseline `origin/main` | `4cddf848fa2ff959a13817002d684ee5320e06c1` |
| Branch created | `wo-070b-stt-human-reference-benchmark` from `origin/main` |

---

## 2. WHY BLOCKED — EXACT CAUSE

WO-070B §5 permits a benchmark-only reference dataset to be built **only** from the
actual, completed WO-068 Excel artifact
(`WO-068-HUMAN-REVIEW-EXTENDED.xlsx`, library artifact
`file_00000000779c8210a4ec00da36c444dc`) and **only if that artifact is accessible
to the benchmark runtime**.

It is not accessible.

### 2.1 Exhaustive accessibility probe (read-only)

| Probe | Result |
|---|---|
| `find / -iname '*.xlsx'` (whole filesystem) | Only `RADIONOR_SETTINGS_FULL.xlsx`, `RADIONOR_ALL_SETTINGS.xlsx`, `cre2_full.xlsx`, `RADIONOR_CHANGE_SET.xlsx` — **none is WO-068** |
| `find / -iname '*.xls'` | none |
| `find / -iname '*WO-068*'` | only `.../wo068.../reports/WO-068-BENCHMARK-REPORT.md` and a skill reference — both are the WO-068 *report*, not the transcript artifact |
| `find / -iname '*EXTENDED*'` | no `*HUMAN-REVIEW-EXTENDED*` anywhere |
| `find / -iname '*file_00000000779c*'` | none — library artifact id resolves to nothing on disk |
| `find / -iname '*.zip'` → `zipfile.namelist()` | `WO-067-PRE-04-HUMAN-REVIEW-PACKAGE.zip` (80 entries) and `human_review_wo068_wo067.zip` (72 entries): audio `.wav` + `metadata/human_review.csv` + `metadata/messages.json` + `reports/` + `playlists/` + `README.md` + `hashes/`. **No `.xlsx`, no transcript column, no reference text** |
| OpenWebUI knowledge bases (`kb_list`, `kb_search`) | 4 KBs accessible (`НІСД`, `Верифікація`, `ALPH Guide`, `Зброєзнавча база знань`). Semantic search for `WO-068 human review transcript reference extended` → **no match**. Artifact absent from every accessible KB |
| Staged runtime uploads (`/opt/data/uploads/*/human_review.csv`) | 10 copies, header identical, **no transcript column** (see §3) |

**Conclusion:** the completed WO-068 artifact exists outside this runtime and has
not been supplied to it. This is an evidence-availability fact, not proof the
artifact does not exist elsewhere.

---

## 3. HUMAN-REVIEW EVIDENCE — WHAT IT ACTUALLY CONTAINS

The staged runtime copy `/opt/data/uploads/1789820783-96109905/human_review.csv`
(sha256 `21c470b613f1df215b2e71bd154e4237a19462293d68af43aa29a362320af1e5`) is
byte-referenced by WO-069/WO-070A. Header:

```
message_id;stream_id;start_time;end_time;duration_ms;audible_voice;intelligible;
radio_style;speaker;dialogue_candidate;voice_type;confidence;notes;reviewer;review_time
```

67 data rows, IDs `msg_0001`–`msg_0067`, streams S1 (44) / S2 (23).

### 3.1 Field-by-field separation: listening evidence vs. accuracy ground truth

| Field | Present? | Classification |
|---|---|---|
| human transcript | **NO** | — (no such column) |
| callsign | **NO** | — |
| intelligibility | yes (categorical) | human **listening** evidence |
| audible_voice | yes (categorical) | human **listening** evidence |
| radio_style | yes (categorical) | human **listening** evidence |
| speaker | yes (categorical) | human **listening** evidence |
| dialogue_candidate | yes (categorical) | human **listening** evidence |
| voice_type | yes (categorical) | human **listening** evidence |
| confidence | yes (`HIGH`) | reviewer **confidence label** — **not** STT accuracy |
| reviewer | yes (`OLEH`) | provenance of the *labels*, not of the audio |
| review_time | yes (`17:43`) | provenance of the *labels* |
| notes | column exists, **empty** for all 67 | — |
| provenance / RF provenance / transport provenance | **NO** | — |

`notes` is empty on every row. There is **no** human-entered transcript text
anywhere in this artifact. The `audible_voice = NO` rows are exactly the six
messages WO-070B §3 pre-identifies:

```
msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066   (6 records, audible_voice = NO)
```

Reviewer confidence (`HIGH`) is a subjective label and is **not** treated as STT
accuracy. No categorical field is converted into a transcript.

---

## 4. WO-068 / WO-069 EVIDENCE STATE (authoritative, unchanged)

The WO-068 benchmark report
(`/opt/data/wo068_real_radio_stt_benchmark_v1/reports/WO-068-BENCHMARK-REPORT.md`)
records `FINAL STATUS: BLOCKED / INCOMPLETE — ground truth UNAVAILABLE`. Its own
machine-readable sidecars confirm:

```
dataset/ground_truth/ground_truth.json :
  {"schema":"wo068-ground-truth-v1","status":"UNAVAILABLE",
   "reason":"No human listening review has been performed...","entries":[]}
results/dataset_gate.json :
  {"samples_total":67,"integrity_errors":[],"ground_truth_verified":0,
   "ground_truth_unavailable":67,"required_min":50,"dataset_gate":"FAIL"}
results/aggregate.csv  : all engines samples_processed=0,
  WER/CER/callsign_accuracy/RTF/RSS = NOT MEASURED, status = NOT EXECUTED
results/per_sample.csv : every row transcript_raw/transcript_normalized/wer/cer empty,
  note = "benchmark blocked: ground truth UNAVAILABLE (0/67 human-verified)"
```

WO-069 subsequently executed the engines against the same 67 WAVs and produced
hypotheses **but no reference**. Verified from the raw WO-069 outputs
(`/opt/data/wo069_runtime/raw_*.jsonl`, read-only):

| Engine | file records | SUCCESS | non-empty hypotheses | empty hypotheses |
|---|---|---|---|---|
| faster_whisper | 67 | 67 | **64** | **3** |
| vosk | 67 | 67 | **53** | **14** |

These match the WO-069 figures carried in WO-070A. **Empty hypotheses are valid
engine outputs and, had a reference existed, would be scored — not silently
dropped.** Hypothesis-only output cannot serve as a reference (§4, §7, §20).

No engine was re-run in WO-070B. `raw_*.jsonl` and all WO-069 evidence were
**not modified**.

---

## 5. WHY THE DATASET WAS NOT CONSTRUCTED

Per WO-070B §5, the normalized reference dataset may be built **only** from the
actual completed Excel artifact. With no artifact, the required per-message
`reference_transcript` / `reference_status` values cannot be established for any
record:

* Audible + transcript explicitly entered by human → **none exist** (no transcript field).
* Non-audible → 6 records are *identifiable* (audible_voice = NO), but
  `reference_status = NON_AUDIBLE` is only meaningful inside a dataset whose
  remaining rows could carry `HUMAN_VERIFIED` text; none can.
* Audible but no human transcript → **all remaining 61 records**.

No `docs/benchmarks/stt/wo070b/` dataset, script or test was created. Constructing
a reference file containing 67 empty/`NO_HUMAN_TRANSCRIPT` rows would be a
misleading artifact dressed as a benchmark input, so it was **not** produced.

Explicitly rejected (each is a prohibited fabrication per §4, §6, §9, §20):

* copying Faster-Whisper or Vosk output into `reference_transcript`
* using `callsign`, `dialogue_candidate`, `notes`, `speaker`, `voice_type`, `filename`
* inferring transcripts from memory or from the six known non-audible IDs
* generating pseudo-ground-truth or synthetic references
* computing WER/CER from categorical labels or reviewer confidence

---

## 6. REQUIRED REPORT (WO-070B §17)

```
STATUS:                      BLOCKED
BRANCH:                      wo-070b-stt-human-reference-benchmark
HEAD:                        4cddf848fa2ff959a13817002d684ee5320e06c1  (pre-commit; see §9)
ORIGIN/MAIN:                 4cddf848fa2ff959a13817002d684ee5320e06c1

HUMAN_REFERENCE_SOURCE:      WO-068-HUMAN-REVIEW-EXTENDED.xlsx / file_00000000779c8210a4ec00da36c444dc
HUMAN_REFERENCE_ACCESSIBLE:  NO   (EVIDENCE NOT RUNTIME-AVAILABLE)
HUMAN_REFERENCE_COUNT:       0
HUMAN_TRANSCRIPT_COUNT:      0
NON_AUDIBLE_COUNT:           6    (msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066)
MISSING_TRANSCRIPT_COUNT:    67   (no transcript field in any accessible artifact)

FASTER_WHISPER:
  hypotheses:                67 file records, 67 SUCCESS, 64 non-empty, 3 empty
  evaluated:                 0
  WER:                       NOT_MEASURABLE
  CER:                       NOT_MEASURABLE

VOSK:
  hypotheses:                67 file records, 67 SUCCESS, 53 non-empty, 14 empty
  evaluated:                 0
  WER:                       NOT_MEASURABLE
  CER:                       NOT_MEASURABLE

NORMALIZATION:               NOT APPLIED — no reference to measure; no metric procedure
                             was executed, therefore none was invented.
                             (§6 normalization definition is moot without a reference.)
MATCHING:                    NOT PERFORMED — join by message_id is only meaningful once
                             references exist. Dataset side has 67 unique IDs, msg_0001..msg_0067.
MISMATCHES:                  NONE OBSERVED in the hypothesis set:
                             faster_whisper 67/67 IDs, vosk 67/67 IDs, no duplicates, no orphans.
                             (No reference set to join against.)

WO-069 EVIDENCE MODIFIED:    NO
PRODUCTION FILES MODIFIED:   NO
STT SEAM MODIFIED:           NO
ENGINE ACTIVATED:            NO
NETWORK USED:                NO
FABRICATED EVIDENCE:         NONE

TESTS:                       No WO-070B benchmark tests created — §13 tests presuppose a
                             reference dataset; fabricating tests against absent references
                             was refused.
REGRESSION TESTS:            NOT REQUIRED — no production file changed. Production STT/audio
                             suite left untouched (no code modified in this WO).

COMMIT:                      see §9
REMOTE_VERIFICATION:         see §9
FINAL_CLASSIFICATION:        BLOCKED
```

---

## 7. PRODUCTION SAFETY ATTESTATION

```
backend/app/contracts/audio.py            : NOT MODIFIED
backend/app/audio/stt_seam.py             : NOT MODIFIED
backend/app/audio/stt_config.py           : NOT MODIFIED
backend/app/audio/stt_worker.py           : NOT MODIFIED
_ENGINE_FACTORIES / engine registration   : NOT TOUCHED
EventFactory / EventPipeline / RadioEventIntegrator / Observation / Operator Wall / journal : NOT TOUCHED
callsign architecture / adapters / DB schema : NOT TOUCHED
models downloaded / dependencies installed   : NONE
production configuration modified            : NO
engine activated                             : NO
main modified                                : NO
wo-069 evidence modified                     : NO
?? 500                                       : preserved, untouched, unstaged
 M (pyc) pre-existing                        : preserved as found
```

---

## 8. WHAT WOULD UNBLOCK THIS (evidence still missing)

1. Provision of the **actual completed WO-068 artifact**
   (`WO-068-HUMAN-REVIEW-EXTENDED.xlsx` / library artifact
   `file_00000000779c8210a4ec00da36c444dc`) to the benchmark runtime, with a
   per-message human-entered transcript column and `reviewer` / `review_time`.
2. A stated mapping of that artifact's rows to `message_id` (`msg_0001`–`msg_0067`)
   so the join is by ID, not row number.
3. A CSA ruling on whether the CubicCore-sourced audio qualifies as real-radio
   evidence for a production decision (carried from WO-068 §10; transport
   provenance = synthetic generator, `real_transmission = UNRESOLVED` for all 67).

Until (1) and (2) are supplied, WER/CER remain `NOT_MEASURABLE` and the benchmark
cannot be constructed. This is an evidence state, not a failure.

---

## 9. GIT DISCIPLINE AND VERIFICATION

Only this file is created by WO-070B:

```
docs/work_orders/WO-070B-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
```

No dataset, script, test or production file is added or changed. Commit and remote
verification results are recorded in the WO-070B final report accompanying this
document.

---

**FINAL STATUS: BLOCKED.** No engine executed, no reference manufactured, no
engine selected. Awaiting provision of the completed human-reference artifact per
§8.
