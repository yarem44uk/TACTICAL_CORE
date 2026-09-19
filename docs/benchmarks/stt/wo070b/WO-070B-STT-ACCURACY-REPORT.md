# WO-070B (CONTINUATION) — STT ACCURACY FROM HUMAN REFERENCE TRANSCRIPTS

**Work Order:** WO-070B (continuation)
**Branch:** `wo-070b-stt-human-reference-benchmark`
**Base:** `origin/main` @ `4cddf848fa2ff959a13817002d684ee5320e06c1`
**Date:** 2026-09-19
**FINAL CLASSIFICATION:** **VERIFIED**

---

## BLUF

The completed WO-068 human-review artifact `WO-068-HUMAN-REVIEW-EXTENDED.xlsx` is
now **runtime-accessible**. Human-entered reference transcripts were read directly
from its `Human Review` sheet — **61 of 67** records carry a human transcript; the
**6** `audible_voice = NO` records are `NON_AUDIBLE`; **0** records are
`NO_HUMAN_TRANSCRIPT`.

WER/CER were computed deterministically for both existing WO-069 hypothesis sets
against those 61 references. No engine was re-run, ranked, or selected; no
production file was touched.

**This WO produces accuracy evidence only.** Engine authorization remains a
separate CSA decision (§23).

---

## 1. REQUIRED REPORT FIELDS (WO-070B-CONTINUE §20)

```
STATUS:                      VERIFIED
BRANCH:                      wo-070b-stt-human-reference-benchmark
HEAD:                        6d3d38953d37174bdbd1d6aeca6e68adda385bc8
                             "WO-070B: document human reference benchmark blocker (continuation re-check)"
                             (branch tip BEFORE this WO's commit; see §11)
ORIGIN/MAIN:                 4cddf848fa2ff959a13817002d684ee5320e06c1

HUMAN_REFERENCE_SOURCE:      WO-068-HUMAN-REVIEW-EXTENDED.xlsx
                             (library file id file_00000000779c8210a4ec00da36c444dc,
                              library id libfile_542a5507ff7c8191a10e49c5dafdd408)
                             provisioned path:
                             /opt/data/uploads/1789821219-911209cd/WO-068-HUMAN-REVIEW-EXTENDED.xlsx
HUMAN_REFERENCE_ACCESSIBLE:  YES
XLSX_SHA256:                 2e4a0bb66a7309a077623bf49935b6493ef607d3dccbc2fe5eb1da342a88296d
XLSX_SIZE:                   16969 bytes
SHEETS:                      ['Human Review', 'Instructions']

TOTAL_RECORDS:               67
HUMAN_VERIFIED_TRANSCRIPTS:  61
NON_AUDIBLE:                 6
NO_HUMAN_TRANSCRIPT:         0
EMPTY_TRANSCRIPTS:           0
DUPLICATE_MESSAGE_IDS:       0
MISSING_MESSAGE_IDS:         0

MESSAGE_ID_MAPPING:          join key = message_id (never row position)
                             faster_whisper: 67 refs / 67 hypotheses / 67 matched
                             vosk:           67 refs / 67 hypotheses / 67 matched
DUPLICATES:                  none (reference and both hypothesis sets)
MISSING_IDS:                 none
ORPHANS:                     none (no orphan references, no orphan hypotheses)

NORMALIZATION:               wo070b-normalize-v1 (identical for reference and
                             hypothesis — see §5)

FASTER_WHISPER:
  hypotheses:                67 (67 SUCCESS, 64 non-empty, 3 empty)
  reference_count:           61
  evaluated:                 61
  empty_hypotheses:          2   (of the 3 empty hypotheses, 1 is a NON_AUDIBLE record)
  substitutions:             96
  deletions:                 9
  insertions:                47
  WER:                       1.062937   (152 ops / 143 reference words)
  CER:                       0.774924   (513 ops / 662 reference characters)

VOSK:
  hypotheses:                67 (67 SUCCESS, 53 non-empty, 14 empty)
  reference_count:           61
  evaluated:                 61
  empty_hypotheses:          9   (of the 14 empty hypotheses, 5 are NON_AUDIBLE records)
  substitutions:             43
  deletions:                 34
  insertions:                8
  WER:                       0.594406   (85 ops / 143 reference words)
  CER:                       0.498489   (330 ops / 662 reference characters)

TRANSPORT_PROVENANCE:        SYNTHETIC_TOPOLOGY — CubicCore traffic generator
                             v7.19.4 over a simulated L2/L3 topology; no RF/SDR
                             transport. UNCHANGED from WO-068/WO-069 evidence.
RF_PROVENANCE:               UNRESOLVED (independent RF provenance evidence absent)
REAL_TRANSMISSION:           UNRESOLVED — deliberately NOT converted to YES or NO

WO-069 EVIDENCE MODIFIED:    NO  (hypotheses read read-only; byte-identical
                                 snapshots added to this benchmark dir)
PRODUCTION FILES MODIFIED:   NO
STT SEAM MODIFIED:           NO
ENGINE ACTIVATED:            NO
NETWORK USED:                NO
FABRICATED EVIDENCE:         NONE

WO-070B TESTS:               23 passed in 0.07s
                             (env -u PYTHONPATH PYTHONNOUSERSITE=1
                              .venv/bin/python -m pytest docs/benchmarks/stt/wo070b
                              -q -p no:cacheprovider)
PRODUCTION REGRESSION:       150 passed in 4.31s
                             (test_wo039c_stt, test_wo041_corr_stt_boundary,
                              test_wo057_callsign_integration,
                              test_wo063_recording_stt_worker,
                              test_wo064_transcript_enrichment,
                              test_wo038_audio_pipeline, test_wo039b_recording)

COMMIT:                      see §11
REMOTE_VERIFICATION:         see §11

FINAL_CLASSIFICATION:        VERIFIED
```

### 1.1 Correction to the aggregate WER denominator

The per-engine WER/CER in the block above are the **token-weighted, sum-aggregate**
values produced by `wo070b_benchmark.py` (`Σ ops / Σ reference units`), which is
what `aggregate_results.csv` contains:

| engine | Σ WER ops | Σ ref words | aggregate WER | Σ CER ops | Σ ref chars | aggregate CER |
|---|---|---|---|---|---|---|
| faster_whisper | 152 | 143 | 1.062937 | 513 | 662 | 0.774924 |
| vosk | 85 | 143 | 0.594406 | 330 | 662 | 0.498489 |

The reference corpus is identical for both engines (143 words / 662 characters
over the 61 scored records), so the two engines remain directly comparable.
No ranking is implied or performed.

---

## 2. FORENSIC GATE (read-only, before any modification)

```
$ cd /opt/data/tactical_core_github
$ git status --short
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
$ git branch --show-current
wo-070b-stt-human-reference-benchmark
$ git rev-parse HEAD
6d3d38953d37174bdbd1d6aeca6e68adda385bc8
$ git rev-parse origin/main
4cddf848fa2ff959a13817002d684ee5320e06c1
$ git log -1 --oneline
6d3d389 WO-070B: document human reference benchmark blocker (continuation re-check)
$ git diff --name-only origin/main...HEAD
docs/work_orders/WO-070B-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
docs/work_orders/WO-070B-CONTINUE-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
```

**Deviation from the WO header:** §1 states the expected branch HEAD as
`af19586d2292de0bf98205eb9735beab1bb25c0e`. The actual branch tip found was
`6d3d38953d37174bdbd1d6aeca6e68adda385bc8` (one commit later — the second
blocker document, WO-070B-CONTINUE). The branch name and `origin/main` match
exactly. No new branch was created, `main` was not modified, and no history was
rewritten. Recorded as found, not forced.

Pre-existing worktree state was preserved exactly. The protected untracked
`?? 500` was **never** opened, read, hashed, statted, copied, moved, renamed,
staged, deleted, cleaned or reset. The pre-existing bytecode-cache ` M` was left
as found and is **not** staged by this WO.

---

## 3. ARTIFACT ACCESSIBILITY CHECK (WO-070B-CONTINUE §2)

The workbook was located on the first targeted probe — it is staged in the runtime
upload batch:

```
/opt/data/uploads/1789821219-911209cd/WO-068-HUMAN-REVIEW-EXTENDED.xlsx   16969 bytes
```

This differs from the state recorded in the two earlier BLOCKED documents (that
batch did not contain the workbook). The artifact is now runtime-visible; the
continuation is unblocked.

---

## 4. WORKBOOK VERIFICATION (read-only, §4 and §5)

Opened with `openpyxl` in `data_only=True, read_only=True` mode. The workbook was
**not** written back, saved, or altered.

```
XLSX_PATH:    /opt/data/uploads/1789821219-911209cd/WO-068-HUMAN-REVIEW-EXTENDED.xlsx
XLSX_SHA256:  2e4a0bb66a7309a077623bf49935b6493ef607d3dccbc2fe5eb1da342a88296d
XLSX_SIZE:    16969
SHEETS:       ['Human Review', 'Instructions']
```

* structurally valid OOXML workbook — opens cleanly;
* required sheets `Instructions` **and** `Human Review` both exist;
* `Human Review` holds a header row + **67** data rows, `msg_0001` … `msg_0067`.

Column set (23 columns, original `human_review.csv` columns preserved plus new
review/transcript columns):

```
message_id, stream_id, start_time, end_time, duration_ms, audible_voice,
intelligible, radio_style, speaker, dialogue_candidate, voice_type, confidence,
notes, reviewer, review_time, transcript, callsign, language, human_confirmed,
ground_truth_status, real_transmission, RF_provenance, transport_provenance
```

The exact column holding the human-entered transcript is **`transcript`**. Per the
`Instructions` sheet: *"Human-entered transcript only. Never copy STT/model
output."* The source column was **not** renamed.

---

## 5. HUMAN TRANSCRIPT VALIDATION AND NORMALIZATION (§6, §7, §8, §12)

### 5.1 Where the reference text comes from

`reference_transcript` is taken **only** from the `transcript` cell of the
workbook's `Human Review` sheet. Nothing was derived from Faster-Whisper, Vosk,
callsign, notes, `dialogue_candidate`, speaker, filename, memory or inference.

* `audible_voice = YES` (61 records) — every one carries a non-empty
  human-entered `transcript` → `reference_status = HUMAN_VERIFIED`.
* `audible_voice = NO` (6 records) — no transcript invented →
  `reference_status = NON_AUDIBLE`, `reference_transcript = ""`.
* Audible with no transcript → `NO_HUMAN_TRANSCRIPT`: **0 records** (this
  classification is implemented and tested, but no record falls into it).

### 5.2 The six non-audible records — actual vs. expected

Expected by the WO: `msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066`.

Actual, read from the workbook:

```
msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066     (6 records, audible_voice = NO)
```

**Match — the expected list is confirmed by the artifact itself.**

`reviewer` is populated (`OLEH`) for the 61 audible records and empty for the six
non-audible records. `review_time` is `17:43:00` except for `msg_0001`, whose
`review_time` cell is empty. Both are recorded verbatim in the dataset; neither is
inferred.

### 5.3 Normalization procedure — `wo070b-normalize-v1`

Implemented in `docs/benchmarks/stt/wo070b/wo070b_normalize.py`, applied
identically to reference and hypothesis (no branch favours either side):

1. `None` / non-string → `""`.
2. Unicode normalization: **NFC**.
3. Case handling: `str.casefold()` (locale-independent).
4. Ukrainian / typographic apostrophes: U+2019, U+2018, U+02BC, U+0060, U+00B4,
   U+02B9, U+2032 → ASCII `'` (U+0027).
5. Punctuation / symbols: every character that is not a letter, a digit, an
   ASCII apostrophe or whitespace → a single space. Covers `. , … - _ ? ! " « »`
   and ellipses (a bare `..` or `…` collapses to whitespace, never to a token).
6. Tokenization on whitespace; edge apostrophes stripped per token; empty tokens
   dropped.
7. Whitespace normalization: tokens rejoined with exactly one ASCII space.
8. Digits: **preserved as digits** — no number-to-word expansion (script-agnostic).
9. Empty string is a valid, meaningful normalization result, not an error.

No semantic correction, no manual hypothesis improvement, no alteration of human
transcripts.

### 5.4 Reference dataset (`docs/benchmarks/stt/wo070b/human_reference_transcripts.csv`)

Columns: `message_id, stream_id, reference_transcript, reference_status,
reviewer, review_time` — 67 rows, IDs `msg_0001`…`msg_0067` in order.
`reference_status` ∈ {`HUMAN_VERIFIED` (61), `NON_AUDIBLE` (6)}.

---

## 6. METRIC IMPLEMENTATION (WO-070B §14)

Implemented in `docs/benchmarks/stt/wo070b/wo070b_metrics.py` — a benchmark-local
unit-cost Levenshtein alignment. **No production dependency was introduced** and
none was needed.

```
WER = (substitutions + deletions + insertions) / reference_word_count
CER = (substitutions + deletions + insertions) / reference_character_count
```

* Units: WER on normalized **word tokens**; CER on normalized **characters with
  whitespace removed**.
* Costs are unit costs, so `S + D + I` equals the plain edit distance.
* Determinism: the DP cost matrix is computed first, then the S/D/I split is
  recovered by a single backtrack with a **fixed preference order** —
  match > substitution > deletion > insertion. Unit-cost alignments are not
  unique; this fixed order is what makes every reported number reproducible.
* Empty reference denominator (0 words / 0 chars) → metric `None` and the record
  is **excluded**, never scored as 0 or 1.
* Empty hypothesis with a valid reference → scored (a deletions-only record),
  never silently dropped.

Normalization applied to both sides before alignment; reference and hypothesis
pass through the *same* function.

---

## 7. SCORING SCOPE AND METHOD (WO-070B §10, §11, §13)

* Join key: `message_id`, strictly. **Not** row position. Verified by a dedicated
  test that feeds hypotheses in the reverse order keyed by id.
* Scored: `reference_status == HUMAN_VERIFIED` **and** non-empty reference → 61
  records per engine.
* Excluded: `NON_AUDIBLE` (6) and `NO_HUMAN_TRANSCRIPT` (0). An empty engine
  hypothesis on a scored record was **not** excluded.
* Hypotheses: the existing WO-069 outputs, snapshot byte-for-byte into the
  benchmark directory:
  * `wo069_hypotheses_faster_whisper.jsonl` — sha256 `a9bb9bb392b9fae737e025904dafc86c0de1fc8d473a19e609c0d257f2311b0e`
  * `wo069_hypotheses_vosk.jsonl` — sha256 `489a8c4525068e59104e5ca672c32a35459f8b269b0801e49f2794aca3efedcf`
  * source `/opt/data/wo069_runtime/raw_*.jsonl` — read-only, unmodified.
* Neither engine was re-run. Neither engine is ranked, labelled "best", or
  selected.

Empty-hypothesis reconciliation against the WO-069 headline figures:

* faster_whisper: 3 empty over all 67 (`msg_0031`, `msg_0044`, `msg_0058`) → **2**
  fall inside the 61 scored records (`msg_0044` is `NON_AUDIBLE`).
* vosk: 14 empty over all 67 → **9** fall inside the 61 scored records
  (`msg_0001`, `msg_0023`, `msg_0044`, `msg_0049`, `msg_0066` are `NON_AUDIBLE`).
* The 67/67 SUCCESS, 64/53 non-empty headline counts are unchanged and reproduce
  exactly from the raw evidence.

---

## 8. RESULTS

`aggregate_results.csv` (sum-aggregate, `Σ ops / Σ reference units`):

```
engine,hypotheses,reference_count,evaluated_count,empty_hypothesis_count,substitutions,deletions,insertions,WER,CER
faster_whisper,67,61,61,2,96,9,47,1.062937,0.774924
vosk,67,61,61,9,43,34,8,0.594406,0.498489
```

Per-message results (`per_message_results.csv`, columns `message_id, engine,
reference_transcript, hypothesis, wer, cer`) — 122 rows (61 records × 2 engines).
Examples:

```
msg_0002  faster_whisper  "Канал один"        vs "канал «Один»."   wer 0.0    cer 0.0
msg_0003  faster_whisper  "Канал два канал три" vs "канал 2 канал 3" wer 0.5  cer 0.375
msg_0007  faster_whisper  "… чуєш Дід"        vs "Слышь его."      wer 1.0    cer 1.0
```

Machine-readable roll-up: `wo070b_results.json`
(`normalization_id = wo070b-normalize-v1`, `metrics_id = wo070b-levenshtein-v1`).

Neither engine is ranked here and no production-engine conclusion is drawn.

---

## 9. TESTS (WO-070B §16)

`docs/benchmarks/stt/wo070b/test_wo070b_benchmark.py` — 23 tests covering all 14
required cases: exact match, substitution, insertion, deletion, empty hypothesis,
empty reference handling, non-audible exclusion, missing reference exclusion,
message_id join (reverse-order proof), duplicate message_id detection,
normalization (casefold, apostrophe variants, punctuation/ellipsis, digits, None),
CER, WER, and deterministic output (byte-identical reruns of all three output
files), plus reference-dataset well-formedness.

```
$ env -u PYTHONPATH PYTHONNOUSERSITE=1 .venv/bin/python -m pytest \
      docs/benchmarks/stt/wo070b -q -p no:cacheprovider
.......................                                                  [100%]
23 passed in 0.07s
```

---

## 10. PRODUCTION REGRESSION (WO-070B §17) AND SAFETY ATTESTATION (§18)

```
$ cd backend
$ env -u PYTHONPATH PYTHONNOUSERSITE=1 ../.venv/bin/python -m pytest \
    tests/test_wo039c_stt.py tests/test_wo041_corr_stt_boundary.py \
    tests/test_wo057_callsign_integration.py tests/test_wo063_recording_stt_worker.py \
    tests/test_wo064_transcript_enrichment.py tests/test_wo038_audio_pipeline.py \
    tests/test_wo039b_recording.py -q -p no:cacheprovider
collected 150 items
............................. [100%]
150 passed in 4.31s
```

Safety attestation:

```
backend/app/contracts/audio.py             : NOT MODIFIED
backend/app/audio/stt_seam.py              : NOT MODIFIED
backend/app/audio/stt_config.py            : NOT MODIFIED
backend/app/audio/stt_worker.py            : NOT MODIFIED
_ENGINE_FACTORIES / engine registration    : NOT TOUCHED
EventFactory / EventPipeline / RadioEventIntegrator / Observation /
Operator Wall / journal / adapters / DB schema / production config : NOT TOUCHED
models downloaded / dependencies installed : NONE
network used                              : NO
engine activated                          : NO
main modified                             : NO
WO-069 evidence modified                  : NO
?? 500                                    : preserved, untouched, unstaged
 M (pyc) pre-existing                     : preserved as found, unstaged
```

---

## 11. PROVENANCE (WO-070B §19) AND GIT (WO-070B-CONTINUE §22)

```
TRANSPORT_PROVENANCE: SYNTHETIC_TOPOLOGY — CubicCore traffic generator v7.19.4
                      over a simulated L2/L3 topology; no RF/SDR transport chain.
                      (WO-068 report §2.1; unchanged.)
RF_PROVENANCE:        UNRESOLVED — no independent RF provenance evidence in hand.
REAL_TRANSMISSION:    UNRESOLVED for all 67 — the workbook's own
                      `real_transmission` / `RF_provenance` / `transport_provenance`
                      columns are empty for every row, and its `Instructions` sheet
                      states "Do not infer from speech alone. YES requires separate
                      evidence." Deliberately NOT converted to YES or NO.
```

RF provenance was **not** treated as a blocker for WER/CER; it remains a separate
CSA production-decision issue.

Files added by this WO (benchmark-only, all under `docs/benchmarks/stt/wo070b/`):

```
__init__.py
wo070b_normalize.py
wo070b_metrics.py
wo070b_reference.py
wo070b_benchmark.py
test_wo070b_benchmark.py
human_reference_transcripts.csv
wo069_hypotheses_faster_whisper.jsonl
wo069_hypotheses_vosk.jsonl
per_message_results.csv
aggregate_results.csv
wo070b_results.json
WO-070B-STT-ACCURACY-REPORT.md
README.md
```

Only these are staged. `?? 500` and the pre-existing `.pyc` modification remain
untouched and unstaged. Commit message:

```
WO-070B: measure STT accuracy from human reference transcripts
```

Push target: `origin/wo070b-stt-human-reference-benchmark` only. `main` is not
pushed. Live commit/remote SHAs are captured at execution time via
`git rev-parse` / `git ls-remote` in the run transcript and are not self-referenced
inside this document (a commit cannot record its own SHA).

---

## 12. FINAL CLASSIFICATION

**VERIFIED.**

The actual WO-068 Excel artifact was accessed; human transcripts were extracted
directly from its `Human Review` sheet; the `message_id` mapping is valid and
complete (67/67, no duplicates, no orphans); WER/CER were calculated
deterministically from an identical normalization applied to both sides and are
reproducible byte-for-byte; no fabrication occurred; no engine was activated,
ranked or selected; no production file changed.

Per §23 this is **accuracy evidence only**. A separate CSA decision must determine
whether and how it is used for production engine authorization.
